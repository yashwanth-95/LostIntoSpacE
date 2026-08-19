"""Grounded scientific RAG.

    Question -> classification -> hybrid search -> retrieval -> reranking
             -> context selection -> AI -> citation validation -> response

Three behaviours carry most of the weight:

**Insufficient evidence is an answer.** If retrieval abstains, or the selected
context is empty, no model call is made at all. Calling a model with nothing to
ground on and hoping it declines is not a control.

**Time-sensitive questions do not settle for embeddings.** When the classifier
marks a question as being about the present, a live resolver is consulted. If
live data cannot be obtained, the answer still goes out — but flagged, with a
limitation saying so and `data_origin` set to what it actually is. What must
never happen is a cached element set answering "where is it right now" without
saying that it is not now.

**Citations are validated after generation, not trusted.** A fabricated
reference downgrades the response and is reported; it never reaches the caller
as though it were grounded.
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field

from contracts._time import utc_now
from contracts.ai import (
    AIResponse,
    AnswerLimitation,
    Citation,
    ConfidenceLevel,
    ContextItem,
    DataOrigin,
)
from contracts.provenance import FreshnessClass
from contracts.search import SearchQuery, SearchResponse, SearchStatus

from ..prompts.scientific import (
    INSUFFICIENT_EVIDENCE_TEMPLATE,
    SCIENTIFIC_SYSTEM_PROMPT,
    build_user_prompt,
)
from ..providers.base import (
    AIMessage,
    AIProvider,
    AIProviderError,
    AIRequest,
    Role,
)
from .citations import CitationValidator, ValidationResult
from .context import ContextBuilder, ContextSelection

__all__ = [
    "LiveDataResolver",
    "NullLiveResolver",
    "RAGResult",
    "GroundedRAG",
    "REFUSAL_MARKERS",
]

#: Phrases a model uses when it declines. Matched only on answers that cite
#: nothing — a well-cited answer containing "does not cover the mass of X" is
#: a qualification, not a refusal, and must not be discarded as one.
REFUSAL_MARKERS = (
    "do not contain",
    "does not contain",
    "do not cover",
    "does not cover",
    "not covered by",
    "no information",
    "cannot answer",
    "can't answer",
    "cannot be answered",
    "unable to answer",
    "insufficient",
    "not enough information",
    "not present in the",
    "no relevant",
    "not available in the",
    "do not include",
    "does not include",
    "not specified in",
    "no usable answer",
)


def _is_refusal(text: str, validation) -> bool:
    """Whether the model declined rather than answered."""
    if validation.citations:
        return False
    body = str(text or "").strip().lower()
    if not body:
        return True
    #: Only the opening matters. A long answer that happens to mention a gap
    #: near the end is still an answer.
    opening = body[:240]
    return any(marker in opening for marker in REFUSAL_MARKERS)


class LiveDataResolver(Protocol):
    """Fetches current data for a time-sensitive question.

    Implemented against real sources in `data/` (CelesTrak for element sets,
    EONET for events). The protocol keeps the RAG layer from knowing which.
    """

    def resolve(self, question: str, intent: Any) -> List[ContextItem]:
        ...


class NullLiveResolver:
    """Resolves nothing. The default.

    Its existence is the point: with no live resolver configured, a
    time-sensitive question still gets an answer, but one that says plainly it
    is not based on current data. The alternative — silently serving cached
    elements — is the failure this design exists to prevent.
    """

    def resolve(self, question: str, intent: Any) -> List[ContextItem]:
        return []


class RAGResult(BaseModel):
    """The response plus the pipeline's working, for tests and diagnostics."""

    model_config = ConfigDict(extra="forbid")

    response: AIResponse
    search_response: Optional[SearchResponse] = None
    selection: Optional[ContextSelection] = None
    validation: Optional[ValidationResult] = None
    stage_ms: Dict[str, float] = Field(default_factory=dict)

    @property
    def answered(self) -> bool:
        return not self.response.insufficient_evidence


class GroundedRAG:
    """The retrieval-augmented answering pipeline."""

    def __init__(
        self,
        retriever: Any,
        provider: AIProvider,
        context_builder: Optional[ContextBuilder] = None,
        validator: Optional[CitationValidator] = None,
        live_resolver: Optional[Any] = None,
        max_results: int = 8,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ):
        self.retriever = retriever
        self.provider = provider
        self.context = context_builder or ContextBuilder()
        self.validator = validator or CitationValidator()
        self.live_resolver = live_resolver or NullLiveResolver()
        self.max_results = max_results
        self.max_tokens = max_tokens
        #: Low by default. This layer explains retrieved evidence; creative
        #: variation is a liability, not a feature.
        self.temperature = temperature

    # -- pipeline ----------------------------------------------------------
    async def answer(
        self,
        question: str,
        extra_context: Optional[Sequence[ContextItem]] = None,
        **query_kwargs
    ) -> RAGResult:
        """Answer `question`, or explain why it cannot be answered.

        `extra_context` carries items the caller has already resolved and
        authorized — project configuration, simulation output. They join the
        retrieved evidence on the same footing: fenced, cited, and validated.
        """
        started = time.time()
        stages: Dict[str, float] = {}
        supplied = list(extra_context or [])

        from search.ranking.intent import classify_intent

        mark = time.time()
        intent = classify_intent(question)
        stages["classify"] = (time.time() - mark) * 1000.0

        mark = time.time()
        query = SearchQuery(text=question, limit=self.max_results, **query_kwargs)
        search_response = self.retriever.search(query)
        stages["retrieve"] = (time.time() - mark) * 1000.0

        mark = time.time()
        live_items = self._resolve_live(question, intent)
        stages["live"] = (time.time() - mark) * 1000.0

        #: Caller-supplied context counts as evidence for the abstention
        #: decision. "Why did my rocket fail?" is answerable from the
        #: simulation run even when the corpus has nothing matching the words.
        prepended = supplied + live_items

        if search_response.status is not SearchStatus.OK and not prepended:
            #: Retrieval already decided there is no reliable evidence. Calling
            #: the model here would be asking it to answer from its weights.
            return RAGResult(
                response=self._insufficient(
                    question,
                    search_response.explanation
                    or "no relevant records were retrieved.",
                    intent,
                    started,
                ),
                search_response=search_response,
                stage_ms=stages,
            )

        mark = time.time()
        selection = self.context.build(
            search_response.results if search_response.status is SearchStatus.OK
            else [],
            live_items=prepended,
        )
        stages["context"] = (time.time() - mark) * 1000.0

        if selection.is_empty:
            detail = "Retrieval returned {0} result(s), but none could be used: " \
                     "{1}".format(
                         len(search_response.results),
                         "; ".join(sorted(set(selection.excluded.values())))
                         or "no usable content",
                     )
            return RAGResult(
                response=self._insufficient(question, detail, intent, started),
                search_response=search_response,
                selection=selection,
                stage_ms=stages,
            )

        mark = time.time()
        try:
            completion = await self._generate(question, selection)
        except AIProviderError as exc:
            return RAGResult(
                response=self._provider_failure(question, exc, selection, started),
                search_response=search_response,
                selection=selection,
                stage_ms=stages,
            )
        stages["generate"] = (time.time() - mark) * 1000.0

        mark = time.time()
        validation = self.validator.validate(
            completion.text,
            selection.items,
            quarantined_refs=selection.quarantined,
        )
        stages["validate"] = (time.time() - mark) * 1000.0

        #: The model may decline even when retrieval succeeded — the entity was
        #: found but the specific fact it was asked for is not in the context.
        #: Retrieval cannot detect that case (measured: a lexical coverage check
        #: does not separate it from a well-phrased answerable question), so the
        #: model's judgement is the only signal, and the response must reflect
        #: it rather than presenting a refusal as an answer.
        if _is_refusal(completion.text, validation):
            return RAGResult(
                response=self._insufficient(
                    question,
                    "The retrieved records were about the right subject but did "
                    "not contain the specific information requested.",
                    intent,
                    started,
                ),
                search_response=search_response,
                selection=selection,
                validation=validation,
                stage_ms=stages,
            )

        response = self._assemble(
            question, completion, selection, validation, intent, live_items, started
        )
        response.diagnostics["stage_ms"] = stages
        return RAGResult(
            response=response,
            search_response=search_response,
            selection=selection,
            validation=validation,
            stage_ms=stages,
        )

    # -- stages ------------------------------------------------------------
    def _resolve_live(self, question: str, intent) -> List[ContextItem]:
        """Fetch current data when the question is about the present."""
        if not getattr(intent, "is_time_sensitive", False):
            return []
        try:
            return list(self.live_resolver.resolve(question, intent) or [])
        except Exception:  # noqa: BLE001 - a live-source outage must not fail the answer
            #: Reported through the limitations on the response rather than
            #: raised: an unavailable live source degrades the answer, it does
            #: not invalidate the retrieved evidence.
            return []

    async def _generate(self, question: str, selection: ContextSelection):
        request = AIRequest(
            system=SCIENTIFIC_SYSTEM_PROMPT,
            messages=[
                AIMessage(
                    role=Role.USER,
                    content=build_user_prompt(question, selection.items),
                )
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return await self.provider.generate(request)

    # -- response assembly -------------------------------------------------
    def _assemble(
        self, question, completion, selection, validation, intent, live_items, started
    ) -> AIResponse:
        limitations: List[AnswerLimitation] = []
        data_origin = self._data_origin(selection, live_items)

        if getattr(intent, "is_time_sensitive", False) and not live_items:
            limitations.append(
                AnswerLimitation(
                    kind="not_current",
                    detail=(
                        "This question asks about the present, but no live source "
                        "was available. The answer is based on stored data and "
                        "may not reflect the current state."
                    ),
                )
            )

        for canonical_id in selection.stale_items:
            item = next(
                (i for i in selection.items if i.canonical_id == canonical_id), None
            )
            if item and item.staleness_note:
                limitations.append(
                    AnswerLimitation(kind="stale_data", detail=item.staleness_note)
                )

        if selection.injection_findings:
            limitations.append(
                AnswerLimitation(
                    kind="untrusted_content",
                    detail=(
                        "{0} retrieved item(s) contained text resembling "
                        "instructions to the assistant. Such text was treated as "
                        "data; {1} item(s) were withheld entirely.".format(
                            len(selection.injection_findings),
                            len(selection.quarantined),
                        )
                    ),
                )
            )

        if validation.fabricated_refs:
            limitations.append(
                AnswerLimitation(
                    kind="unverified_citation",
                    detail=(
                        "The model cited {0} reference(s) that were not supplied "
                        "({1}); they have been removed and this answer should not "
                        "be treated as fully grounded.".format(
                            len(validation.fabricated_refs),
                            ", ".join(validation.fabricated_refs),
                        )
                    ),
                )
            )

        if validation.uncited_claims:
            limitations.append(
                AnswerLimitation(
                    kind="uncited_claims",
                    detail="{0} statement(s) in this answer carry no citation.".format(
                        len(validation.uncited_claims)
                    ),
                )
            )

        if completion.was_truncated:
            limitations.append(
                AnswerLimitation(
                    kind="truncated",
                    detail="The answer reached the output limit and may be "
                           "incomplete, including its citations.",
                )
            )

        conflicts = self._detect_conflicts(selection)
        if conflicts:
            limitations.append(
                AnswerLimitation(kind="source_conflict", detail=conflicts)
            )

        freshness = selection.weakest_freshness()
        response = AIResponse(
            answer=validation.cleaned_answer or completion.text,
            confidence=self._confidence(selection, validation, intent, live_items),
            data_origin=data_origin,
            citations=validation.citations,
            sources=selection.source_references(),
            context_items=list(selection.items),
            freshness=freshness,
            freshness_note=self._freshness_note(selection, live_items, intent),
            limitations=limitations,
            related_topics=self._related_topics(selection),
            suggested_questions=self._suggested_questions(selection),
            model_id=completion.model_id,
            latency_ms=(time.time() - started) * 1000.0,
            diagnostics={
                "intent": getattr(intent, "intent", None)
                and intent.intent.value,
                "time_sensitive": getattr(intent, "is_time_sensitive", False),
                "context_items": len(selection.items),
                "excluded": len(selection.excluded),
                "quarantined": selection.quarantined,
                "citation_coverage": round(validation.citation_coverage, 3),
                "unused_refs": validation.unused_refs,
                "live_items": len(live_items),
            },
        )
        return response

    def _data_origin(self, selection, live_items) -> DataOrigin:
        if live_items and len(live_items) == len(selection.items):
            return DataOrigin.LIVE
        if live_items:
            return DataOrigin.MIXED

        types = {item.source_type.value for item in selection.items}
        if len(types) > 1:
            return DataOrigin.MIXED
        if types == {"SIMULATION"}:
            return DataOrigin.SIMULATED
        #: Editorial, bundled reference and the user's own stored configuration
        #: are all "does not change under us" — distinct from cached external
        #: data, which does.
        if types & {"EDITORIAL", "BUNDLED_REFERENCE", "USER_PROVIDED"}:
            return DataOrigin.STATIC
        return DataOrigin.CACHED

    def _confidence(self, selection, validation, intent, live_items) -> ConfidenceLevel:
        """Confidence reflects the evidence, not the model's fluency."""
        if validation.fabricated_refs:
            return ConfidenceLevel.LOW
        if not validation.citations:
            return ConfidenceLevel.LOW
        if getattr(intent, "is_time_sensitive", False) and not live_items:
            #: The answer may be well-sourced and still wrong about *now*.
            return ConfidenceLevel.LOW
        if selection.has_stale_content:
            return ConfidenceLevel.MEDIUM

        strong = [
            item for item in selection.items
            if item.source_type.value in
            ("PRIMARY_SCIENTIFIC", "AGENCY_PUBLIC_API", "LITERATURE")
        ]
        best = max((item.relevance for item in selection.items), default=0.0)
        if strong and best > 0.3 and len(validation.citations) >= 2:
            return ConfidenceLevel.HIGH
        if best > 0.2:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    def _freshness_note(self, selection, live_items, intent) -> Optional[str]:
        if live_items:
            return "Includes data fetched live for this question."
        if getattr(intent, "is_time_sensitive", False):
            return (
                "No live source was consulted; this reflects stored data, not the "
                "current state."
            )
        retrieved = [item.retrieved_at for item in selection.items if item.retrieved_at]
        if not retrieved:
            return None
        return "Based on data retrieved at {0}.".format(min(retrieved).isoformat())

    def _detect_conflicts(self, selection: ContextSelection) -> Optional[str]:
        """Note when two sources describe the same entity.

        A weak signal deliberately: this reports that a disagreement is
        *possible* and names the sources. Deciding which is right is the data
        quality engine's job, and asserting a winner here would duplicate — and
        eventually contradict — it.
        """
        by_entity: Dict[str, List[str]] = {}
        for item in selection.items:
            by_entity.setdefault(item.canonical_id, []).append(item.source.source_name)
        contested = {
            entity: sorted(set(names))
            for entity, names in by_entity.items()
            if len(set(names)) > 1
        }
        if not contested:
            return None
        return (
            "More than one source describes {0}; where their values differ the "
            "answer should present both rather than choosing.".format(
                ", ".join(sorted(contested))
            )
        )

    def _related_topics(self, selection: ContextSelection) -> List[str]:
        topics: List[str] = []
        for item in selection.items:
            for topic in item.source.source_name.split():
                pass
        seen: List[str] = []
        for item in selection.items:
            if item.title and item.title not in seen:
                seen.append(item.title)
        return seen[:5]

    def _suggested_questions(self, selection: ContextSelection) -> List[str]:
        """Follow-ups grounded in what was actually retrieved.

        Generated from retrieved titles rather than invented, so a suggestion
        always leads somewhere the corpus can answer.
        """
        suggestions = []
        for item in selection.items[:3]:
            if item.title:
                suggestions.append("Tell me more about {0}".format(item.title))
        return suggestions

    # -- refusals ----------------------------------------------------------
    def _insufficient(self, question, detail, intent, started) -> AIResponse:
        return AIResponse(
            answer=INSUFFICIENT_EVIDENCE_TEMPLATE.format(detail=detail),
            confidence=ConfidenceLevel.INSUFFICIENT_EVIDENCE,
            data_origin=DataOrigin.STATIC,
            insufficient_evidence=True,
            evidence_gap=detail,
            latency_ms=(time.time() - started) * 1000.0,
            diagnostics={
                "intent": getattr(intent, "intent", None) and intent.intent.value,
                "time_sensitive": getattr(intent, "is_time_sensitive", False),
            },
        )

    def _provider_failure(self, question, error, selection, started) -> AIResponse:
        """A provider outage is reported, never papered over with a guess."""
        return AIResponse(
            answer=(
                "The answer could not be generated: the AI provider is "
                "unavailable ({0}). Retrieved sources are listed below and can "
                "be read directly.".format(error.__class__.__name__)
            ),
            confidence=ConfidenceLevel.INSUFFICIENT_EVIDENCE,
            data_origin=DataOrigin.STATIC,
            insufficient_evidence=True,
            evidence_gap="AI provider error: {0}".format(error),
            sources=selection.source_references(),
            context_items=list(selection.items),
            limitations=[
                AnswerLimitation(
                    kind="provider_unavailable",
                    detail="Generation failed; no answer text was produced.",
                )
            ],
            latency_ms=(time.time() - started) * 1000.0,
        )
