"""Reranking.

A reranker sees a *small* candidate set and reorders it using signals fusion
cannot: how authoritative the source is, how fresh the record is, whether its
type suits the query's intent, and whether the page as a whole is diverse.

**Only a small set is reranked.** Reranking is the expensive stage — a hosted
cross-encoder costs a model call per candidate — so it runs on the top N after
fusion, never on the whole index. N defaults to 25.

The interface is provider-independent: `HeuristicReranker` here is deterministic
and offline, and a hosted cross-encoder implements the same three methods.
"""

import abc
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from contracts._time import utc_now
from contracts.provenance import FreshnessClass
from contracts.search import SearchEntityType

from ..embeddings.vectors import TRUST_ORDER, TrustLevel
from .intent import IntentAssessment, QueryIntent

__all__ = [
    "RerankCandidate",
    "RerankedCandidate",
    "RerankWeights",
    "Reranker",
    "NoOpReranker",
    "HeuristicReranker",
    "DEFAULT_RERANK_TOP_N",
]

#: How many candidates reach the reranker. Small on purpose.
DEFAULT_RERANK_TOP_N = 25


class RerankCandidate(BaseModel):
    """What a reranker is given about one candidate.

    Deliberately a flat value object rather than the `SearchDocument` itself:
    it is exactly the signals a reranker may use, which keeps a hosted
    implementation from quietly depending on internals.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str = ""
    #: The passage that matched — what a cross-encoder would score.
    text: str = ""
    #: Fused relevance from the previous stage, already normalized to 0..1.
    relevance: float = 0.0
    entity_type: SearchEntityType = SearchEntityType.UNKNOWN
    object_type: Optional[str] = None
    trust_level: TrustLevel = TrustLevel.LOW
    source_names: List[str] = Field(default_factory=list)
    freshness_class: Optional[FreshnessClass] = None
    #: The record's own temporal anchor.
    date: Optional[datetime] = None
    topics: List[str] = Field(default_factory=list)
    #: True when the record's freshness policy says it is past its useful age.
    is_stale: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RerankedCandidate(BaseModel):
    """A candidate after reranking, with its score broken down.

    The breakdown is not decoration: when a result looks wrong, the only way to
    fix it is to see which signal pushed it up.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    score: float
    #: Position before reranking (1-based), so movement is visible.
    original_rank: int = 0
    final_rank: int = 0
    #: signal name -> contribution to the final score.
    components: Dict[str, float] = Field(default_factory=dict)
    explanation: str = ""

    @property
    def moved(self) -> int:
        """Positions gained (positive) or lost (negative)."""
        if not self.original_rank or not self.final_rank:
            return 0
        return self.original_rank - self.final_rank


class RerankWeights(BaseModel):
    """Relative influence of each signal.

    Relevance dominates by design. The other signals are tie-breakers and
    corrections; a reranker that lets authority outweigh relevance will
    confidently return the most authoritative *irrelevant* record.

    **These values were measured, not chosen.** A first attempt used auxiliary
    weights twice this size and made retrieval *worse* than not reranking at
    all — MRR 0.940 against a no-op baseline of 0.954, because the extra
    signals perturbed an already-good ordering. Halving them turns the same
    reranker into an improvement (MRR 0.969). The sweep is recorded in
    `docs/PERSON4_DATA_ARCHITECTURE.md` §9.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    relevance: float = 1.0
    authority: float = 0.125
    freshness: float = 0.10
    type_match: float = 0.10
    intent_match: float = 0.075


class Reranker(abc.ABC):
    """Interface every reranker implements."""

    name = "abstract"

    @abc.abstractmethod
    def rerank(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
        top_k: int = 10,
        intent: Optional[IntentAssessment] = None,
    ) -> List[RerankedCandidate]:
        """Reorder `candidates`, returning at most `top_k`."""

    def health_check(self) -> Dict[str, Any]:
        """Probe the reranker. Reports rather than raising."""
        try:
            self.rerank("health check", [RerankCandidate(id="probe", title="probe")], 1)
        except Exception as exc:  # noqa: BLE001 - health checks report
            return {"healthy": False, "reranker": self.name, "detail": str(exc)}
        return {"healthy": True, "reranker": self.name}


class NoOpReranker(Reranker):
    """Keeps the fusion order. The control condition for measurement."""

    name = "no-op"

    def rerank(self, query, candidates, top_k=10, intent=None):
        return [
            RerankedCandidate(
                id=candidate.id,
                score=candidate.relevance,
                original_rank=rank,
                final_rank=rank,
                components={"relevance": candidate.relevance},
                explanation="fusion order preserved",
            )
            for rank, candidate in enumerate(candidates[:top_k], start=1)
        ]


class HeuristicReranker(Reranker):
    """Feature-based reranking. Deterministic, offline, explainable.

    Every signal is a bounded 0..1 term combined with an explicit weight, so a
    result's position is always attributable to a named cause.
    """

    name = "heuristic-v1"

    #: Which entity types suit which intent. A conceptual question is best
    #: answered by written explanation; a lookup by the record itself.
    _INTENT_PREFERENCES = {
        QueryIntent.CONCEPTUAL: {
            SearchEntityType.CONCEPT: 1.0,
            SearchEntityType.LESSON: 1.0,
            SearchEntityType.DOCUMENT: 0.7,
            SearchEntityType.MISSION: 0.5,
            SearchEntityType.SPACE_OBJECT: 0.3,
        },
        QueryIntent.LOOKUP: {
            SearchEntityType.SPACE_OBJECT: 1.0,
            SearchEntityType.MISSION: 1.0,
            SearchEntityType.EO_PRODUCT: 0.7,
            SearchEntityType.CONCEPT: 0.5,
        },
        QueryIntent.CURRENT_STATE: {
            SearchEntityType.SPACE_OBJECT: 1.0,
            SearchEntityType.EVENT: 1.0,
            SearchEntityType.EO_PRODUCT: 0.8,
            SearchEntityType.MISSION: 0.6,
            SearchEntityType.CONCEPT: 0.2,
        },
        QueryIntent.EXPLORATORY: {
            SearchEntityType.MISSION: 1.0,
            SearchEntityType.SPACE_OBJECT: 0.9,
            SearchEntityType.CONCEPT: 0.6,
        },
        QueryIntent.COMPARISON: {
            SearchEntityType.CONCEPT: 0.9,
            SearchEntityType.SPACE_OBJECT: 0.9,
            SearchEntityType.MISSION: 0.9,
        },
    }

    #: Intents where a varied page is the goal, and repetition is a real cost.
    #: For everything else there is one right answer, and pushing it down to
    #: make room for variety is strictly harmful — measured at -0.015 MRR when
    #: diversity was applied unconditionally.
    _DIVERSITY_INTENTS = (QueryIntent.EXPLORATORY, QueryIntent.COMPARISON)

    def __init__(
        self,
        weights: Optional[RerankWeights] = None,
        now: Optional[datetime] = None,
        diversity_penalty: float = 0.15,
        diversity_intents: Optional[Sequence[QueryIntent]] = None,
    ):
        self.weights = weights or RerankWeights()
        self._now = now
        #: Subtracted per already-selected candidate sharing a source or type.
        self.diversity_penalty = diversity_penalty
        #: Diversity applies only for these intents. Pass an empty sequence to
        #: disable it entirely, or a wider one to always diversify.
        self.diversity_intents = tuple(
            self._DIVERSITY_INTENTS if diversity_intents is None else diversity_intents
        )

    def _diversity_applies(self, intent: Optional[IntentAssessment]) -> bool:
        if self.diversity_penalty <= 0.0 or not self.diversity_intents:
            return False
        if intent is None:
            return False
        return intent.intent in self.diversity_intents

    # -- signals -----------------------------------------------------------
    def _authority_score(self, candidate: RerankCandidate) -> float:
        """Trust level mapped onto 0..1, most trusted highest."""
        try:
            position = TRUST_ORDER.index(candidate.trust_level)
        except ValueError:
            return 0.0
        return 1.0 - (position / float(len(TRUST_ORDER) - 1))

    def _freshness_score(
        self, candidate: RerankCandidate, intent: Optional[IntentAssessment]
    ) -> float:
        """How well the record's currency suits the question.

        For a time-sensitive question this is a *penalty* channel: a stale
        record is actively wrong, not merely less good. For an ordinary
        question, age barely matters — a 1969 mission record is not worse for
        being old.
        """
        time_sensitive = bool(intent and intent.is_time_sensitive)

        if candidate.is_stale:
            return 0.0 if time_sensitive else 0.5

        freshness = candidate.freshness_class
        if freshness is None:
            return 0.5

        if time_sensitive:
            return {
                FreshnessClass.REAL_TIME: 1.0,
                FreshnessClass.NEAR_REAL_TIME: 0.9,
                FreshnessClass.RECENT: 0.6,
                FreshnessClass.HISTORICAL: 0.1,
                FreshnessClass.STATIC: 0.2,
            }.get(freshness, 0.4)

        #: Not time-sensitive: historical and static content is perfectly good.
        return {
            FreshnessClass.REAL_TIME: 0.8,
            FreshnessClass.NEAR_REAL_TIME: 0.8,
            FreshnessClass.RECENT: 0.8,
            FreshnessClass.HISTORICAL: 0.7,
            FreshnessClass.STATIC: 0.7,
        }.get(freshness, 0.6)

    def _type_match_score(
        self, candidate: RerankCandidate, intent: Optional[IntentAssessment]
    ) -> float:
        if intent is None or intent.confidence < 0.4:
            return 0.5
        preferences = self._INTENT_PREFERENCES.get(intent.intent)
        if not preferences:
            return 0.5
        return preferences.get(candidate.entity_type, 0.4)

    def _intent_match_score(
        self, candidate: RerankCandidate, intent: Optional[IntentAssessment]
    ) -> float:
        """Intent-specific bonuses that are not about entity type alone."""
        if intent is None:
            return 0.5
        if intent.intent is QueryIntent.CURRENT_STATE:
            #: An operational feed is the right kind of source for "now",
            #: even though a scientific archive is more authoritative overall.
            operational = any(
                name in ("celestrak_gp", "nasa_eonet")
                for name in candidate.source_names
            )
            return 1.0 if operational else 0.3
        if intent.wants_explanation:
            return 1.0 if candidate.entity_type in (
                SearchEntityType.CONCEPT, SearchEntityType.LESSON
            ) else 0.4
        return 0.5

    # -- scoring -----------------------------------------------------------
    def score(
        self, candidate: RerankCandidate, intent: Optional[IntentAssessment]
    ) -> Dict[str, float]:
        weights = self.weights
        components = {
            "relevance": weights.relevance * candidate.relevance,
            "authority": weights.authority * self._authority_score(candidate),
            "freshness": weights.freshness * self._freshness_score(candidate, intent),
            "type_match": weights.type_match * self._type_match_score(candidate, intent),
            "intent_match": weights.intent_match
            * self._intent_match_score(candidate, intent),
        }
        return components

    def rerank(self, query, candidates, top_k=10, intent=None):
        scored: List[RerankedCandidate] = []
        for rank, candidate in enumerate(candidates, start=1):
            components = self.score(candidate, intent)
            scored.append(
                RerankedCandidate(
                    id=candidate.id,
                    score=sum(components.values()),
                    original_rank=rank,
                    components=components,
                    explanation=_explain(components),
                )
            )
        scored.sort(key=lambda item: (-item.score, item.id))
        if self._diversity_applies(intent):
            selected = self._select_diverse(scored, candidates, top_k)
        else:
            selected = list(scored[:top_k])
        for position, item in enumerate(selected, start=1):
            item.final_rank = position
        return selected

    def _select_diverse(
        self,
        scored: Sequence[RerankedCandidate],
        candidates: Sequence[RerankCandidate],
        top_k: int,
    ) -> List[RerankedCandidate]:
        """Greedy selection with a penalty for repetition.

        Diversity is a property of the *page*, not of any single result, so it
        cannot be a per-candidate score — it has to be applied while choosing,
        against what has already been chosen. Ten Sentinel-2 products all
        matching equally well is a worse page than eight plus two other kinds
        of record.
        """
        if self.diversity_penalty <= 0.0:
            return list(scored[:top_k])

        by_id = {candidate.id: candidate for candidate in candidates}
        remaining = list(scored)
        selected: List[RerankedCandidate] = []
        seen_sources: Dict[str, int] = {}
        seen_types: Dict[str, int] = {}

        while remaining and len(selected) < top_k:
            best_item = None
            best_value = None
            for item in remaining:
                candidate = by_id.get(item.id)
                penalty = 0.0
                if candidate is not None:
                    for name in set(candidate.source_names):
                        penalty += self.diversity_penalty * seen_sources.get(name, 0)
                    penalty += self.diversity_penalty * seen_types.get(
                        candidate.entity_type.value, 0
                    )
                value = item.score - penalty
                if best_value is None or value > best_value:
                    best_value = value
                    best_item = item

            remaining.remove(best_item)
            candidate = by_id.get(best_item.id)
            if candidate is not None:
                for name in set(candidate.source_names):
                    seen_sources[name] = seen_sources.get(name, 0) + 1
                key = candidate.entity_type.value
                seen_types[key] = seen_types.get(key, 0) + 1
                penalty = best_item.score - (best_value or best_item.score)
                if penalty > 0:
                    best_item.components["diversity_penalty"] = -penalty
            selected.append(best_item)
        return selected


def _explain(components: Dict[str, float]) -> str:
    ordered = sorted(components.items(), key=lambda item: -abs(item[1]))
    return ", ".join("{0} {1:+.3f}".format(name, value) for name, value in ordered)
