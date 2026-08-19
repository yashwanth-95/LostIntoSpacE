"""Grounding: context selection, citation validation, and the RAG pipeline."""

from .citations import (
    CITATION_PATTERN,
    CitationIssue,
    CitationProblem,
    CitationValidator,
    ValidationResult,
)
from .context import ContextBudget, ContextBuilder, ContextSelection
from .live_sources import EVENT_PATTERNS, SATELLITE_PATTERNS, LiveSourceResolver
from .rag import GroundedRAG, LiveDataResolver, NullLiveResolver, RAGResult

__all__ = [
    "GroundedRAG",
    "RAGResult",
    "LiveDataResolver",
    "NullLiveResolver",
    "LiveSourceResolver",
    "SATELLITE_PATTERNS",
    "EVENT_PATTERNS",
    "ContextBuilder",
    "ContextBudget",
    "ContextSelection",
    "CitationValidator",
    "ValidationResult",
    "CitationIssue",
    "CitationProblem",
    "CITATION_PATTERN",
]
