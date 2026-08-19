"""Shared cross-team contracts.

Single source of truth for interfaces between frontend, backend, simulation and
AI. Any change here requires agreement from the affected team members (see
`packages/contracts/README.md`).

Python modules live in this package; the TypeScript mirrors live alongside in
`packages/contracts/src/*.ts`.
"""

from ._time import as_utc, utc_now
from .ai import (
    AIResponse,
    AnswerLimitation,
    Citation,
    ClaimType,
    ConfidenceLevel,
    Conversation,
    ConversationTurn,
    ContextItem,
    DataOrigin,
)
from .analysis import (
    FailureAnalysis,
    FailureSeverity,
    MissionSummary,
    MissionTimelineEntry,
    Mitigation,
    ScientificExplanation,
    SimulationObservation,
    SourceConflict,
    SubsystemKind,
)
from .recommendations import (
    LearnerLevel,
    Recommendation,
    RecommendationKind,
    RecommendationSet,
    RecommendationSignal,
)
from .provenance import REDACTION_MARKER, FreshnessClass, SourceReference, SourceType
from .search import (
    MatchType,
    ResultProvenance,
    SearchEntityType,
    SearchFacet,
    SearchQuery,
    SearchResponse,
    SearchResult,
    SearchStatus,
    SortOrder,
)

__all__ = [
    "as_utc",
    "utc_now",
    # provenance
    "FreshnessClass",
    "SourceReference",
    "SourceType",
    "REDACTION_MARKER",
    # search
    "SearchQuery",
    "SearchResult",
    "SearchResponse",
    "SearchEntityType",
    "SearchStatus",
    "MatchType",
    "SortOrder",
    "SearchFacet",
    "ResultProvenance",
    # ai
    "AIResponse",
    "Citation",
    "ContextItem",
    "ClaimType",
    "ConfidenceLevel",
    "DataOrigin",
    "AnswerLimitation",
    "Conversation",
    "ConversationTurn",
    # analysis
    "FailureAnalysis",
    "SimulationObservation",
    "ScientificExplanation",
    "Mitigation",
    "FailureSeverity",
    "SubsystemKind",
    "MissionSummary",
    "MissionTimelineEntry",
    "SourceConflict",
    # recommendations
    "Recommendation",
    "RecommendationSet",
    "RecommendationKind",
    "RecommendationSignal",
    "LearnerLevel",
]
