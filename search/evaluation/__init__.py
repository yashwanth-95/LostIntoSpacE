"""Retrieval quality measurement.

Precision@K, Recall@K and MRR over a labelled query set, plus abstention
accuracy — because a retriever feeding an AI layer must be judged on when it
declines to answer, not only on what it returns.
"""

from .dataset import EVALUATION_QUERIES, EvaluationQuery, answerable, unanswerable
from .metrics import (
    MetricSummary,
    QueryOutcome,
    average_precision,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from .runner import DEFAULT_K_VALUES, evaluate

__all__ = [
    "evaluate",
    "DEFAULT_K_VALUES",
    "EVALUATION_QUERIES",
    "EvaluationQuery",
    "answerable",
    "unanswerable",
    "MetricSummary",
    "QueryOutcome",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
    "average_precision",
]
