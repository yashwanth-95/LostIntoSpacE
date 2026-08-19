"""Fusion, reranking and the hybrid pipeline.

    Candidate fusion -> Score normalization -> Reranking -> Final results
"""

from .fusion import (
    RRF_K,
    FusedCandidate,
    NormalizationMethod,
    RetrieverResult,
    normalize_scores,
    reciprocal_rank_fusion,
    weighted_score_fusion,
)
from .hybrid import HybridSearch, HybridTrace
from .intent import TEMPORAL_MARKERS, IntentAssessment, QueryIntent, classify_intent
from .reranker import (
    DEFAULT_RERANK_TOP_N,
    HeuristicReranker,
    NoOpReranker,
    RerankCandidate,
    RerankedCandidate,
    Reranker,
    RerankWeights,
)

__all__ = [
    # fusion
    "reciprocal_rank_fusion",
    "weighted_score_fusion",
    "normalize_scores",
    "NormalizationMethod",
    "RetrieverResult",
    "FusedCandidate",
    "RRF_K",
    # intent
    "classify_intent",
    "QueryIntent",
    "IntentAssessment",
    "TEMPORAL_MARKERS",
    # reranking
    "Reranker",
    "HeuristicReranker",
    "NoOpReranker",
    "RerankCandidate",
    "RerankedCandidate",
    "RerankWeights",
    "DEFAULT_RERANK_TOP_N",
    # pipeline
    "HybridSearch",
    "HybridTrace",
]
