"""Grounding: context selection, citation validation, and the RAG pipeline."""

from .citations import (
    CITATION_PATTERN,
    CitationIssue,
    CitationProblem,
    CitationValidator,
    ValidationResult,
)
from .context import ContextBudget, ContextBuilder, ContextSelection
from .rag import GroundedRAG, LiveDataResolver, NullLiveResolver, RAGResult

__all__ = [
    "GroundedRAG",
    "RAGResult",
    "LiveDataResolver",
    "NullLiveResolver",
    "ContextBuilder",
    "ContextBudget",
    "ContextSelection",
    "CitationValidator",
    "ValidationResult",
    "CitationIssue",
    "CitationProblem",
    "CITATION_PATTERN",
]
