"""AI response contracts — shared between backend, frontend and the AI layer.

`AIResponse` is what every AI endpoint returns and what the frontend renders.
Several of its fields exist to make specific failure modes impossible to hide:

* `citations` is required for any answer making a factual claim, and each
  citation points at a retrieved context item — so a citation cannot be written
  by the model out of thin air.
* `data_origin` forces every answer to declare whether it came from live data,
  cache, static content, a simulation, or the model's own weights. A UI that
  shows this cannot accidentally present cached data as current.
* `claim_type` on each statement separates an observation from a measured
  value, a derived value, an estimate, a theory, a simulation result and an AI
  inference. Collapsing those is the central scientific-safety risk in the
  product.
* `limitations` is not optional decoration. An answer that cannot state its own
  limits is not a scientific answer.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._time import as_utc, utc_now
from .provenance import FreshnessClass, SourceReference, SourceType

__all__ = [
    "DataOrigin",
    "ConfidenceLevel",
    "ClaimType",
    "Citation",
    "ContextItem",
    "AnswerLimitation",
    "AIResponse",
    "ConversationTurn",
    "Conversation",
]


class DataOrigin(str, Enum):
    """Where the substance of an answer came from.

    The UI must show this. It is the difference between "the ISS is at this
    altitude" and "the ISS was at this altitude when we last fetched it".
    """

    #: Fetched from a live source during this request.
    LIVE = "LIVE"
    #: Served from cache, within its freshness policy.
    CACHED = "CACHED"
    #: Curated or bundled content that does not change.
    STATIC = "STATIC"
    #: Produced by the educational simulator. Not a real-world observation.
    SIMULATED = "SIMULATED"
    #: The language model's own training data, with no retrieved support.
    #: Answers relying on this must say so.
    MODEL_KNOWLEDGE = "MODEL_KNOWLEDGE"
    #: More than one of the above. The per-citation origins carry the detail.
    MIXED = "MIXED"


class ConfidenceLevel(str, Enum):
    """How much the system trusts its own answer."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    #: Not a low-confidence answer — a refusal to answer. The response body
    #: says what was missing.
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ClaimType(str, Enum):
    """What kind of statement a claim is.

    Conflating these is how a simulator's output becomes "a fact" and a model's
    guess becomes "a measurement".
    """

    #: Something an instrument recorded.
    OBSERVATION = "OBSERVATION"
    #: A published measured quantity, with units and uncertainty.
    MEASURED_VALUE = "MEASURED_VALUE"
    #: Computed from measured values.
    DERIVED_VALUE = "DERIVED_VALUE"
    #: An approximate or order-of-magnitude figure.
    ESTIMATE = "ESTIMATE"
    #: An accepted explanatory framework.
    THEORY = "THEORY"
    #: Output of the educational simulator.
    SIMULATION = "SIMULATION"
    #: The model's own reasoning, not supported by a retrieved source.
    AI_INFERENCE = "AI_INFERENCE"


class ContextItem(BaseModel):
    """One piece of retrieved evidence handed to the model.

    Every field here is required reading for the citation validator: an answer
    may only cite context that was actually supplied, and the validator checks
    each citation against these ids.
    """

    model_config = ConfigDict(extra="forbid")

    #: Short handle the model uses to cite this item, e.g. "S1".
    ref: str
    #: Canonical id of the underlying record.
    canonical_id: str
    title: str
    #: The text the model may use.
    content: str
    source: SourceReference
    source_type: SourceType = SourceType.UNKNOWN
    url: Optional[str] = None
    #: When the underlying content is about, not when it was fetched.
    timestamp: Optional[datetime] = None
    retrieved_at: Optional[datetime] = None
    freshness_class: Optional[FreshnessClass] = None
    #: Retrieval score, so the model can weigh strong against weak evidence.
    relevance: float = 0.0
    #: Whether this item may be described as current.
    may_present_as_live: bool = False
    #: Set when the item is stale for its policy; the answer must say so.
    staleness_note: Optional[str] = None

    @field_validator("timestamp", "retrieved_at")
    @classmethod
    def _utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return as_utc(value)

    def citation_label(self) -> str:
        return "[{0}]".format(self.ref)


class Citation(BaseModel):
    """A claim in the answer, tied to the context item supporting it."""

    model_config = ConfigDict(extra="forbid")

    #: Matches a `ContextItem.ref` that was actually supplied.
    ref: str
    canonical_id: Optional[str] = None
    #: The sentence or clause this citation supports.
    claim: str = ""
    claim_type: ClaimType = ClaimType.OBSERVATION
    source: Optional[SourceReference] = None
    url: Optional[str] = None
    #: False when validation could not tie this citation to supplied context.
    #: A response carrying an unverified citation must not be shown as grounded.
    verified: bool = True

    @property
    def is_trustworthy(self) -> bool:
        return self.verified and self.source is not None


class AnswerLimitation(BaseModel):
    """Something the answer cannot do or does not cover."""

    model_config = ConfigDict(extra="forbid")

    #: Short machine-readable kind, e.g. "stale_data", "simulation_fidelity".
    kind: str
    detail: str


class AIResponse(BaseModel):
    """What every AI endpoint returns."""

    model_config = ConfigDict(extra="forbid")

    answer: str
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    data_origin: DataOrigin = DataOrigin.STATIC

    #: Claims tied to evidence. Required whenever the answer asserts facts.
    citations: List[Citation] = Field(default_factory=list)
    #: Deduplicated sources behind the citations, for a credit line.
    sources: List[SourceReference] = Field(default_factory=list)
    #: The context actually supplied to the model, for audit and for the UI's
    #: "show sources" affordance.
    context_items: List[ContextItem] = Field(default_factory=list)

    #: Freshness of the *answer*, driven by its least-fresh load-bearing source.
    freshness: Optional[FreshnessClass] = None
    #: Human-readable currency statement, e.g. "orbital elements from 3h ago".
    freshness_note: Optional[str] = None

    limitations: List[AnswerLimitation] = Field(default_factory=list)
    related_topics: List[str] = Field(default_factory=list)
    suggested_questions: List[str] = Field(default_factory=list)

    #: Set when the system declined to answer. `answer` then explains why.
    insufficient_evidence: bool = False
    #: What evidence was missing, when it was.
    evidence_gap: Optional[str] = None

    model_id: Optional[str] = None
    generated_at: datetime = Field(default_factory=utc_now)
    latency_ms: Optional[float] = None
    #: Non-authoritative diagnostics: timings, retrieval counts, trace ids.
    diagnostics: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> "AIResponse":
        if self.insufficient_evidence:
            if self.confidence is not ConfidenceLevel.INSUFFICIENT_EVIDENCE:
                raise ValueError(
                    "a response marked insufficient_evidence must carry "
                    "ConfidenceLevel.INSUFFICIENT_EVIDENCE"
                )
            if self.citations:
                raise ValueError(
                    "a response that declined to answer must not carry citations"
                )
        #: A citation must point at context that was actually supplied.
        #: Enforced here so a fabricated reference cannot survive serialization.
        supplied = {item.ref for item in self.context_items}
        if supplied:
            for citation in self.citations:
                if citation.ref not in supplied and citation.verified:
                    raise ValueError(
                        "citation {0!r} is marked verified but refers to context "
                        "that was never supplied; supplied refs are {1}".format(
                            citation.ref, sorted(supplied)
                        )
                    )
        return self

    @property
    def is_grounded(self) -> bool:
        """True when every citation was verified against supplied context."""
        return bool(self.citations) and all(
            citation.verified for citation in self.citations
        )

    @property
    def unverified_citations(self) -> List[Citation]:
        return [citation for citation in self.citations if not citation.verified]

    @property
    def may_present_as_current(self) -> bool:
        """Whether the UI may use present-tense language about this answer."""
        if self.data_origin is DataOrigin.LIVE:
            return True
        if not self.context_items:
            return False
        return all(item.may_present_as_live for item in self.context_items)

    def source_names(self) -> List[str]:
        seen: List[str] = []
        for source in self.sources:
            if source.source_name not in seen:
                seen.append(source.source_name)
        return seen


class ConversationTurn(BaseModel):
    """One question and its answer."""

    model_config = ConfigDict(extra="forbid")

    id: Optional[str] = None
    role: str = "user"
    content: str = ""
    response: Optional[AIResponse] = None
    created_at: datetime = Field(default_factory=utc_now)


class Conversation(BaseModel):
    """A sequence of turns.

    P4 defines the shape; **P2 owns persistence**. This model is what crosses
    the API boundary, not a database schema.
    """

    model_config = ConfigDict(extra="forbid")

    id: Optional[str] = None
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    title: Optional[str] = None
    turns: List[ConversationTurn] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None

    def last_user_message(self) -> Optional[str]:
        for turn in reversed(self.turns):
            if turn.role == "user":
                return turn.content
        return None
