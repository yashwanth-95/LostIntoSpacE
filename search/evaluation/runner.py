"""Running an evaluation.

Takes any object with `.search(SearchQuery) -> SearchResponse` — the semantic
searcher, the keyword index, or a future hybrid — so the same set can compare
retrievers on equal terms.
"""

from typing import Any, Iterable, List, Optional, Sequence

from contracts.search import SearchQuery, SearchStatus

from .dataset import EVALUATION_QUERIES, EvaluationQuery
from .metrics import (
    MetricSummary,
    QueryOutcome,
    average_precision,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

__all__ = ["evaluate", "DEFAULT_K_VALUES"]

DEFAULT_K_VALUES = (1, 3, 5, 10)


def evaluate(
    retriever: Any,
    queries: Optional[Sequence[EvaluationQuery]] = None,
    k_values: Sequence[int] = DEFAULT_K_VALUES,
    limit: Optional[int] = None,
) -> MetricSummary:
    """Score `retriever` over the labelled set."""
    queries = list(queries if queries is not None else EVALUATION_QUERIES)
    if not queries:
        raise ValueError("an evaluation needs at least one query")
    top_k = limit or max(k_values)

    outcomes: List[QueryOutcome] = []
    for query in queries:
        response = retriever.search(SearchQuery(text=query.text, limit=top_k))
        retrieved = [result.id for result in response.results]
        abstained = (
            response.status is not SearchStatus.OK or not response.results
        )
        relevant = set(query.relevant)

        outcome = QueryOutcome(
            query_id=query.id,
            text=query.text,
            relevant=list(query.relevant),
            retrieved=retrieved,
            abstained=abstained,
            expects_no_answer=query.expects_no_answer,
            explanation=response.explanation,
        )
        if not query.expects_no_answer:
            outcome.precision_at_k = {
                k: precision_at_k(retrieved, relevant, k) for k in k_values
            }
            outcome.recall_at_k = {
                k: recall_at_k(retrieved, relevant, k) for k in k_values
            }
            outcome.reciprocal_rank = reciprocal_rank(retrieved, relevant)
            outcome.average_precision = average_precision(retrieved, relevant)
        outcomes.append(outcome)

    return _summarize(outcomes, k_values)


def _summarize(outcomes: Sequence[QueryOutcome], k_values: Sequence[int]) -> MetricSummary:
    scored = [outcome for outcome in outcomes if not outcome.expects_no_answer]
    abstaining = [outcome for outcome in outcomes if outcome.expects_no_answer]

    summary = MetricSummary(
        queries=len(outcomes),
        answerable_queries=len(scored),
        unanswerable_queries=len(abstaining),
        outcomes=list(outcomes),
    )

    if scored:
        for k in k_values:
            summary.precision_at_k[k] = sum(
                outcome.precision_at_k.get(k, 0.0) for outcome in scored
            ) / float(len(scored))
            summary.recall_at_k[k] = sum(
                outcome.recall_at_k.get(k, 0.0) for outcome in scored
            ) / float(len(scored))
        summary.mean_reciprocal_rank = sum(
            outcome.reciprocal_rank for outcome in scored
        ) / float(len(scored))
        summary.mean_average_precision = sum(
            outcome.average_precision for outcome in scored
        ) / float(len(scored))

    if abstaining:
        correct = sum(1 for outcome in abstaining if outcome.abstained)
        summary.abstention_precision = correct / float(len(abstaining))
        summary.false_answers = len(abstaining) - correct

    summary.missed_answers = sum(1 for outcome in scored if outcome.abstained)
    return summary
