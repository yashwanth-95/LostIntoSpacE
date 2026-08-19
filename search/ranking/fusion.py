"""Candidate fusion and score normalization.

**The rule this module exists to enforce: never add raw scores from different
retrievers.** A keyword score of 0.7 and a cosine similarity of 0.7 are not the
same quantity. One is a squashed sum of IDF-weighted field matches; the other is
an angle between unit vectors. Their distributions differ, their scales differ,
and their meanings differ. Summing them produces a number with no
interpretation, dominated by whichever retriever happens to use a wider range.

Two safe ways to combine, both provided:

* **Reciprocal rank fusion** (default) — combines *ranks*, discarding scores
  entirely. Nothing to normalize, nothing to mis-scale, and it is robust when
  one retriever is badly calibrated.
* **Normalized score blending** — min-max or z-score each retriever's scores
  onto a common scale *first*, then take a weighted sum. More expressive than
  RRF, since it preserves the margin between a great match and a mediocre one,
  but it needs enough candidates for the normalization to be meaningful.
"""

import math
from enum import Enum
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "NormalizationMethod",
    "normalize_scores",
    "RetrieverResult",
    "FusedCandidate",
    "reciprocal_rank_fusion",
    "weighted_score_fusion",
    "RRF_K",
]

#: Reciprocal-rank-fusion constant, from the original RRF work. It damps the
#: difference between ranks 1 and 2 enough that one retriever cannot dominate
#: on a single confident guess.
RRF_K = 60.0


class NormalizationMethod(str, Enum):
    """How to put one retriever's scores onto a common scale."""

    #: Map [min, max] onto [0, 1]. Simple and bounded, but sensitive to a
    #: single outlier and destroys absolute meaning.
    MIN_MAX = "MIN_MAX"
    #: Centre on the mean, scale by standard deviation, then squash through a
    #: logistic. Robust to outliers; keeps relative margins.
    Z_SCORE = "Z_SCORE"
    #: Leave scores untouched. Only valid when every retriever already emits
    #: the same quantity on the same scale.
    NONE = "NONE"


def normalize_scores(
    scores: Sequence[float], method: NormalizationMethod = NormalizationMethod.MIN_MAX
) -> List[float]:
    """Put `scores` onto a comparable 0..1 scale."""
    values = [float(score) for score in scores]
    if not values:
        return []
    if method is NormalizationMethod.NONE:
        return values

    if method is NormalizationMethod.MIN_MAX:
        lowest = min(values)
        highest = max(values)
        spread = highest - lowest
        if spread <= 0.0:
            #: Every score identical. Mapping them all to 1.0 would assert
            #: perfect confidence in a set that expressed no preference at all,
            #: so they collapse to the neutral midpoint instead.
            return [0.5 for _ in values]
        return [(value - lowest) / spread for value in values]

    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    deviation = math.sqrt(variance)
    if deviation <= 0.0:
        return [0.5 for _ in values]
    #: Logistic squash keeps the output bounded without clipping, so an
    #: outlier stays ranked highest instead of being flattened to the cap.
    return [1.0 / (1.0 + math.exp(-((value - mean) / deviation))) for value in values]


class RetrieverResult(BaseModel):
    """One retriever's ranked output, as fusion input."""

    model_config = ConfigDict(extra="forbid")

    #: Retriever name, e.g. "keyword" or "vector". Recorded on the fused
    #: candidate so a result can say what found it.
    retriever: str
    #: Document ids, best first.
    ids: List[str] = Field(default_factory=list)
    #: Raw scores, parallel to `ids`. Never combined without normalization.
    scores: List[float] = Field(default_factory=list)
    #: Relative influence of this retriever in the fused ranking.
    weight: float = 1.0

    def ranks(self) -> Dict[str, int]:
        return {item: rank for rank, item in enumerate(self.ids, start=1)}

    def score_map(self) -> Dict[str, float]:
        return dict(zip(self.ids, self.scores))


class FusedCandidate(BaseModel):
    """One document after fusion, with the evidence kept intact."""

    model_config = ConfigDict(extra="forbid")

    id: str
    #: The fused ranking score. Ordering device only — not a probability, and
    #: not comparable across queries.
    fused_score: float = 0.0
    #: retriever -> rank it assigned (1-based).
    ranks: Dict[str, int] = Field(default_factory=dict)
    #: retriever -> the score it assigned, unmodified.
    raw_scores: Dict[str, float] = Field(default_factory=dict)
    #: retriever -> its score after normalization.
    normalized_scores: Dict[str, float] = Field(default_factory=dict)

    @property
    def found_by(self) -> List[str]:
        return sorted(self.ranks)

    @property
    def retriever_count(self) -> int:
        return len(self.ranks)

    @property
    def best_rank(self) -> int:
        return min(self.ranks.values()) if self.ranks else 0

    def explain(self) -> str:
        parts = [
            "{0}#{1}({2:.3f})".format(name, rank, self.raw_scores.get(name, 0.0))
            for name, rank in sorted(self.ranks.items())
        ]
        return "{0}: {1} -> {2:.5f}".format(self.id, ", ".join(parts), self.fused_score)


def _collect(results: Sequence[RetrieverResult]) -> Dict[str, FusedCandidate]:
    candidates: Dict[str, FusedCandidate] = {}
    for result in results:
        ranks = result.ranks()
        scores = result.score_map()
        for document_id in result.ids:
            candidate = candidates.setdefault(
                document_id, FusedCandidate(id=document_id)
            )
            candidate.ranks[result.retriever] = ranks[document_id]
            if document_id in scores:
                candidate.raw_scores[result.retriever] = scores[document_id]
    return candidates


def reciprocal_rank_fusion(
    results: Sequence[RetrieverResult], k: float = RRF_K
) -> List[FusedCandidate]:
    """Fuse by rank. Scores are recorded but never arithmetically combined.

    A document absent from a retriever's list contributes nothing from it,
    rather than a zero — absence is "not retrieved", not "scored zero", and
    treating it as a score would penalise documents unfairly.
    """
    candidates = _collect(results)
    weights = {result.retriever: result.weight for result in results}

    for candidate in candidates.values():
        candidate.fused_score = sum(
            weights.get(name, 1.0) / (k + rank)
            for name, rank in candidate.ranks.items()
        )
    return sorted(
        candidates.values(), key=lambda item: (-item.fused_score, item.id)
    )


def weighted_score_fusion(
    results: Sequence[RetrieverResult],
    method: NormalizationMethod = NormalizationMethod.MIN_MAX,
) -> List[FusedCandidate]:
    """Fuse by normalized score.

    Each retriever's scores are normalized within its own result list first,
    which is what makes the weighted sum meaningful. A document missing from a
    retriever contributes nothing from it.
    """
    candidates = _collect(results)
    weights = {result.retriever: result.weight for result in results}

    for result in results:
        if not result.ids:
            continue
        normalized = normalize_scores(result.scores, method)
        for document_id, value in zip(result.ids, normalized):
            candidates[document_id].normalized_scores[result.retriever] = value

    for candidate in candidates.values():
        candidate.fused_score = sum(
            weights.get(name, 1.0) * value
            for name, value in candidate.normalized_scores.items()
        )
    return sorted(
        candidates.values(), key=lambda item: (-item.fused_score, item.id)
    )
