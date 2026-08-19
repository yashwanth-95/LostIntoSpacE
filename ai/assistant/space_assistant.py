"""The space AI assistant.

Sits on top of `GroundedRAG` and adds the domain decisions RAG has no basis to
make: which sources are authoritative for this kind of question, whether to
prefer a written explanation or an archive record, and how the answer should be
qualified.

Three answer strategies, chosen from intent and topic:

* **Factual** — retrieve first, then generate. Never the reverse. The model
  never sees the question without evidence attached.
* **Time-sensitive** — prefer live data; if none is available, say so and drop
  confidence rather than answering from stored elements as though they were
  current.
* **Scientific** — prefer authoritative archives over operational feeds and
  editorial content, and surface disagreement rather than resolving it silently.

The three product rules are enforced here rather than trusted to the prompt:
no fabricated answers (no evidence means no answer), no fabricated citations
(validated after generation), and simulation output never presented as
observation (`ClaimType.SIMULATION` is preserved and labelled).
"""

import time
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from contracts.ai import (
    AIResponse,
    AnswerLimitation,
    ClaimType,
    ConfidenceLevel,
    DataOrigin,
)
from contracts.provenance import SourceType
from contracts.search import SearchQuery

from ..grounding.rag import GroundedRAG, RAGResult
from .topics import Topic, TopicAssessment, classify_topic

__all__ = ["AnswerStrategy", "AssistantPlan", "SpaceAssistant"]


class AnswerStrategy(str, Enum):
    """How a question will be answered."""

    #: Retrieve evidence, then generate from it.
    FACTUAL = "FACTUAL"
    #: Prefer live data; degrade explicitly when unavailable.
    TIME_SENSITIVE = "TIME_SENSITIVE"
    #: Prefer authoritative scientific archives.
    SCIENTIFIC = "SCIENTIFIC"
    #: Prefer written explanation over archive records.
    EXPLANATORY = "EXPLANATORY"
    #: Recognised as outside the product's subject area.
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"
    #: In-domain, but reaching past what the stored data can support — a
    #: prediction far beyond any element set's validity window.
    BEYOND_DATA_VALIDITY = "BEYOND_DATA_VALIDITY"


class AssistantPlan(BaseModel):
    """The routing decision, exposed so an answer can explain its own shape."""

    model_config = ConfigDict(extra="forbid")

    strategy: AnswerStrategy
    topic: TopicAssessment
    #: Intent name, from the search layer's classifier.
    intent: Optional[str] = None
    is_time_sensitive: bool = False
    #: Source types this question should prefer, best first.
    preferred_source_types: List[str] = Field(default_factory=list)
    reason: str = ""


#: Source authority per strategy, best first. Not a single global ranking:
#: an operational feed is the *right* source for "where is it now" and the
#: wrong one for "what is its mass".
_PREFERRED_SOURCES: Dict[AnswerStrategy, List[str]] = {
    AnswerStrategy.SCIENTIFIC: [
        SourceType.PRIMARY_SCIENTIFIC.value,
        SourceType.LITERATURE.value,
        SourceType.AGENCY_PUBLIC_API.value,
        SourceType.BUNDLED_REFERENCE.value,
    ],
    AnswerStrategy.TIME_SENSITIVE: [
        SourceType.SECONDARY_OPERATIONAL.value,
        SourceType.AGENCY_PUBLIC_API.value,
        SourceType.PRIMARY_SCIENTIFIC.value,
    ],
    AnswerStrategy.EXPLANATORY: [
        SourceType.EDITORIAL.value,
        SourceType.LITERATURE.value,
        SourceType.BUNDLED_REFERENCE.value,
    ],
    AnswerStrategy.FACTUAL: [
        SourceType.PRIMARY_SCIENTIFIC.value,
        SourceType.AGENCY_PUBLIC_API.value,
        SourceType.BUNDLED_REFERENCE.value,
        SourceType.EDITORIAL.value,
    ],
}


class SpaceAssistant:
    """Domain-aware answering over the grounded RAG pipeline."""

    def __init__(
        self,
        rag: GroundedRAG,
        max_results: int = 8,
        project_client: Optional[Any] = None,
    ):
        self.rag = rag
        self.max_results = max_results
        #: A `ProjectDataClient` bound to one user's token, or `None` for
        #: anonymous use. There is no way to supply a token per call: a client
        #: shared across users is exactly how project data leaks.
        self.project_client = project_client

    # -- planning ----------------------------------------------------------
    def plan(self, question: str) -> AssistantPlan:
        """Decide how to answer, before any retrieval happens."""
        from search.ranking.intent import QueryIntent, classify_intent

        intent = classify_intent(question)
        topic = classify_topic(question)

        if not topic.is_in_domain:
            return AssistantPlan(
                strategy=AnswerStrategy.OUT_OF_DOMAIN,
                topic=topic,
                intent=intent.intent.value,
                reason="no space-science subject matter detected in the question",
            )

        if intent.asks_beyond_data_validity:
            return AssistantPlan(
                strategy=AnswerStrategy.BEYOND_DATA_VALIDITY,
                topic=topic,
                intent=intent.intent.value,
                reason=(
                    "the question asks about {0}, far beyond the validity of any "
                    "stored orbital element set or ephemeris".format(
                        intent.far_future_year
                    )
                ),
            )

        if intent.is_time_sensitive:
            strategy = AnswerStrategy.TIME_SENSITIVE
            reason = "the question asks about the present state of something"
        elif intent.wants_explanation or topic.is_engineering:
            strategy = AnswerStrategy.EXPLANATORY
            reason = "the question asks how or why something works"
        elif topic.is_scientific:
            strategy = AnswerStrategy.SCIENTIFIC
            reason = "the question asks for scientific values or records"
        else:
            strategy = AnswerStrategy.FACTUAL
            reason = "a factual lookup"

        return AssistantPlan(
            strategy=strategy,
            topic=topic,
            intent=intent.intent.value,
            is_time_sensitive=intent.is_time_sensitive,
            preferred_source_types=_PREFERRED_SOURCES.get(strategy, []),
            reason=reason,
        )

    # -- answering ---------------------------------------------------------
    async def ask(
        self,
        question: str,
        project_id: Optional[str] = None,
        mission_id: Optional[str] = None,
        simulation_id: Optional[str] = None,
        **query_kwargs
    ) -> AIResponse:
        """Answer a question. Never raises for content reasons.

        Project ids are opt-in scope, not authorization: supplying one does not
        grant access. P2 decides whether the caller's token may read it.
        """
        started = time.time()
        plan = self.plan(question)

        if plan.strategy is AnswerStrategy.OUT_OF_DOMAIN:
            return self._out_of_domain(question, plan, started)

        if plan.strategy is AnswerStrategy.BEYOND_DATA_VALIDITY:
            return self._beyond_validity(question, plan, started)

        project_items, project_note = await self._project_context(
            question, project_id, mission_id, simulation_id
        )
        if project_items:
            query_kwargs = dict(query_kwargs)
            query_kwargs["extra_context"] = project_items

        outcome = await self.rag.answer(question, **query_kwargs)
        if project_note:
            outcome.response.diagnostics["project_context"] = project_note
        response = outcome.response
        self._apply_domain_rules(response, plan, outcome)
        response.diagnostics["strategy"] = plan.strategy.value
        response.diagnostics["topic"] = plan.topic.primary.value
        response.diagnostics["topic_terms"] = plan.topic.matched_terms
        return response

    async def _project_context(
        self,
        question: str,
        project_id: Optional[str],
        mission_id: Optional[str],
        simulation_id: Optional[str],
    ):
        """Fetch project data, but only what the question justifies.

        Returns `(context_items, diagnostic_note)`. A failure to reach P2
        degrades the answer to a general one; it never fails the request, and
        it never falls back to a privileged read.
        """
        from ..context.render import render_project_context
        from ..context.selection import select_project_context

        if self.project_client is None:
            return ([], None)

        request = select_project_context(
            question,
            has_project=bool(project_id or mission_id),
            has_simulation=bool(simulation_id),
        )
        if not request.needs_project_data:
            #: The common case, and the important one: a general question about
            #: physics must not pull a user's private design into the prompt.
            return ([], {"fetched": False, "reason": request.reason})

        try:
            context = await self.project_client.fetch(
                request.kinds,
                project_id=project_id,
                mission_id=mission_id,
                simulation_id=simulation_id,
            )
        except Exception as exc:  # noqa: BLE001 - degrade, never fail the answer
            return (
                [],
                {
                    "fetched": False,
                    "reason": "project API unavailable: {0}".format(
                        exc.__class__.__name__
                    ),
                },
            )

        items = render_project_context(context)
        return (
            items,
            {
                #: True only when something actually reached the prompt. A
                #: fetch that was attempted and yielded nothing is a failure to
                #: fetch, and reporting it as success would hide an outage.
                "fetched": bool(items),
                "attempted": True,
                "reason": request.reason,
                "kinds": [kind.value for kind in context.fetched_kinds],
                "skipped": context.skipped,
                "items": len(items),
            },
        )

    def _apply_domain_rules(
        self, response: AIResponse, plan: AssistantPlan, outcome: RAGResult
    ) -> None:
        """Post-generation domain checks, applied to the assembled response."""
        if response.insufficient_evidence:
            return

        self._enforce_simulation_labelling(response)
        self._note_source_authority(response, plan)
        self._enrich_topics(response, plan)

    def _enforce_simulation_labelling(self, response: AIResponse) -> None:
        """Simulation output is never presented as a real-world observation.

        If any cited item came from the simulator, the response says so, its
        origin becomes `SIMULATED` or `MIXED`, and the affected citations are
        retyped. The model is asked to do this in the prompt; this makes it
        true regardless of whether it complied.
        """
        simulated_refs = [
            item.ref
            for item in response.context_items
            if item.source_type is SourceType.SIMULATION
        ]
        if not simulated_refs:
            return

        for citation in response.citations:
            if citation.ref in simulated_refs:
                citation.claim_type = ClaimType.SIMULATION

        if len(simulated_refs) == len(response.context_items):
            response.data_origin = DataOrigin.SIMULATED
        else:
            response.data_origin = DataOrigin.MIXED

        response.limitations.append(
            AnswerLimitation(
                kind="simulation_not_reality",
                detail=(
                    "Part of this answer comes from the educational simulator "
                    "({0}). Simulator output is a model result, not a real-world "
                    "observation, and the simulator does not reproduce reality "
                    "exactly.".format(", ".join(simulated_refs))
                ),
            )
        )

    def _note_source_authority(self, response: AIResponse, plan: AssistantPlan) -> None:
        """Record when a scientific question was answered from weaker sources."""
        if plan.strategy is not AnswerStrategy.SCIENTIFIC:
            return
        preferred = set(plan.preferred_source_types)
        used = {item.source_type.value for item in response.context_items}
        if used and not (used & preferred):
            response.limitations.append(
                AnswerLimitation(
                    kind="weaker_source",
                    detail=(
                        "This is a scientific question, but no primary archive "
                        "source was available; the answer rests on {0}.".format(
                            ", ".join(sorted(used))
                        )
                    ),
                )
            )
            if response.confidence is ConfidenceLevel.HIGH:
                response.confidence = ConfidenceLevel.MEDIUM

    def _enrich_topics(self, response: AIResponse, plan: AssistantPlan) -> None:
        """Add subject-area topics alongside the retrieved titles."""
        extra = [topic.value for topic in plan.topic.topics[:3]]
        for value in extra:
            if value not in response.related_topics:
                response.related_topics.append(value)

    def _beyond_validity(self, question, plan, started) -> AIResponse:
        """Decline a question reaching past what the data can support.

        Orbital element sets and ephemerides are valid near their epoch; the
        canonical models record that explicitly. Propagating one across
        centuries and presenting the result would be a fabrication dressed up
        as a calculation, and retrieval cannot catch it because the records for
        the object are genuinely present and genuinely relevant.
        """
        return AIResponse(
            answer=(
                "That question reaches far beyond what the available data can "
                "support. Orbital element sets and ephemerides are only valid "
                "near their epoch — typically days to years, not centuries — and "
                "atmospheric drag, solar activity and station-keeping make a "
                "prediction that far ahead impossible from stored elements. "
                "Answering it would mean inventing a number."
            ),
            confidence=ConfidenceLevel.INSUFFICIENT_EVIDENCE,
            data_origin=DataOrigin.STATIC,
            insufficient_evidence=True,
            evidence_gap=plan.reason,
            limitations=[
                AnswerLimitation(
                    kind="beyond_data_validity",
                    detail=plan.reason,
                )
            ],
            latency_ms=(time.time() - started) * 1000.0,
            diagnostics={
                "strategy": plan.strategy.value,
                "topic": plan.topic.primary.value,
            },
        )

    def _out_of_domain(self, question, plan, started) -> AIResponse:
        return AIResponse(
            answer=(
                "This assistant covers space science, missions, spacecraft, "
                "rockets, propulsion, orbital mechanics and related engineering. "
                "That question falls outside those subjects, so there is no "
                "sourced material here to answer it from."
            ),
            confidence=ConfidenceLevel.INSUFFICIENT_EVIDENCE,
            data_origin=DataOrigin.STATIC,
            insufficient_evidence=True,
            evidence_gap="question is outside the assistant's subject area",
            suggested_questions=[
                "What causes Max-Q?",
                "How does a gravity assist work?",
                "Which spacecraft explored Jupiter?",
            ],
            latency_ms=(time.time() - started) * 1000.0,
            diagnostics={
                "strategy": plan.strategy.value,
                "topic": plan.topic.primary.value,
            },
        )
