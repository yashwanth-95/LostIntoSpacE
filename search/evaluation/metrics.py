"""Retrieval metrics.

Standard definitions, written out rather than imported, so the exact
convention used is visible and auditable:

* **Precision@K** — of the top K returned, what fraction are relevant. Divided
  by K, not by the number returned: a system returning two results, both
  relevant, has not achieved Precision@5 of 1.0.
* **Recall@K** — of the relevant records that exist, what fraction appear in
  the top K.
* **MRR** — mean over queries of 1/rank of the first relevant result, and 0
  when none appears. Rewards putting the right answer first.

Queries that should return nothing are scored separately: for those, success is
*abstaining*, and averaging them into precision would reward silence.
"""

from typing import Dict, Iterable, List, Optional, Sequence, Set

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
    "average_precision",
    "QueryOutcome",
    "MetricSummary",
]


def _relevant_flags(retrieved: Sequence[str], relevant: Set[str]) -> List[bool]:
    return [item in relevant for item in retrieved]


def precision_at_k(retrieved: Sequence[str], relevant: Set[str], k: int) -> float:
    """Fraction of the top K that are relevant."""
    if k <= 0:
        raise ValueError("k must be positive")
    if not relevant:
        return 0.0
    hits = sum(_relevant_flags(retrieved[:k], relevant))
    return hits / float(k)


def recall_at_k(retrieved: Sequence[str], relevant: Set[str], k: int) -> float:
    """Fraction of all relevant records that appear in the top K."""
    if k <= 0:
        raise ValueError("k must be positive")
    if not relevant:
        return 0.0
    hits = sum(_relevant_flags(retrieved[:k], relevant))
    return hits / float(len(relevant))


def reciprocal_rank(retrieved: Sequence[str], relevant: Set[str]) -> float:
    """1 / rank of the first relevant result, or 0 when there is none."""
    for index, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def average_precision(retrieved: Sequence[str], relevant: Set[str]) -> float:
    """Mean of the precision values at each relevant hit."""
    if not relevant:
        return 0.0
    hits = 0
    total = 0.0
    for index, item in enumerate(retrieved, start=1):
        if item in relevant:
            hits += 1
            total += hits / float(index)
    return total / float(len(relevant))


class QueryOutcome(BaseModel):
    """Per-query result, kept so a bad average can be traced to its cause."""

    model_config = ConfigDict(extra="forbid")

    query_id: str
    text: str
    #: Empty for a query that should correctly return nothing.
    relevant: List[str] = Field(default_factory=list)
    retrieved: List[str] = Field(default_factory=list)
    #: True when the system declined to answer.
    abstained: bool = False
    #: True when abstaining was the right call.
    expects_no_answer: bool = False
    precision_at_k: Dict[int, float] = Field(default_factory=dict)
    recall_at_k: Dict[int, float] = Field(default_factory=dict)
    reciprocal_rank: float = 0.0
    average_precision: float = 0.0
    explanation: Optional[str] = None

    @property
    def is_correct_abstention(self) -> bool:
        return self.expects_no_answer and self.abstained

    @property
    def is_false_answer(self) -> bool:
        """Answered a question the corpus cannot support — the worst failure."""
        return self.expects_no_answer and not self.abstained

    @property
    def is_missed(self) -> bool:
        """Abstained on a question the corpus does cover."""
        return (not self.expects_no_answer) and self.abstained

    def summary(self) -> str:
        if self.expects_no_answer:
            verdict = "correctly abstained" if self.abstained else "WRONGLY ANSWERED"
            return "{0}: {1}".format(self.query_id, verdict)
        top = self.retrieved[0] if self.retrieved else "-"
        return "{0}: rr={1:.2f} top={2}".format(self.query_id, self.reciprocal_rank, top)


class MetricSummary(BaseModel):
    """Aggregate metrics over an evaluation run."""

    model_config = ConfigDict(extra="forbid")

    queries: int = 0
    answerable_queries: int = 0
    unanswerable_queries: int = 0

    precision_at_k: Dict[int, float] = Field(default_factory=dict)
    recall_at_k: Dict[int, float] = Field(default_factory=dict)
    mean_reciprocal_rank: float = 0.0
    mean_average_precision: float = 0.0

    #: Of the queries that should return nothing, how many correctly did.
    abstention_precision: float = 0.0
    #: Answers given to questions the corpus cannot support.
    false_answers: int = 0
    #: Abstentions on questions the corpus does cover.
    missed_answers: int = 0

    outcomes: List[QueryOutcome] = Field(default_factory=list)

    def describe(self) -> str:
        lines = [
            "Retrieval evaluation over {0} queries ({1} answerable, {2} expected "
            "to return nothing)".format(
                self.queries, self.answerable_queries, self.unanswerable_queries
            ),
            "  MRR  {0:.3f}    MAP {1:.3f}".format(
                self.mean_reciprocal_rank, self.mean_average_precision
            ),
        ]
        for k in sorted(self.precision_at_k):
            lines.append(
                "  P@{0:<3d} {1:.3f}   R@{0:<3d} {2:.3f}".format(
                    k, self.precision_at_k[k], self.recall_at_k.get(k, 0.0)
                )
            )
        lines.append(
            "  correct abstentions {0:.3f}   false answers {1}   missed {2}".format(
                self.abstention_precision, self.false_answers, self.missed_answers
            )
        )
        return "\n".join(lines)

    def failures(self) -> List[QueryOutcome]:
        """Queries worth looking at: no relevant hit, or a wrong abstention."""
        return [
            outcome
            for outcome in self.outcomes
            if outcome.is_false_answer
            or outcome.is_missed
            or (not outcome.expects_no_answer and outcome.reciprocal_rank == 0.0)
        ]
