"""The MVP recommendation engine.

**Rules plus semantic similarity, deliberately.** No learned ranker, no
collaborative filtering, no embedding of user behaviour. Three reasons:

1. There is no interaction data yet. A learned recommender with nothing to
   learn from is a random one with extra machinery.
2. Every recommendation has to explain itself, and a rule states its own
   reason. "You have not covered specific impulse, which staging builds on" is
   both the rule and the explanation.
3. The failure modes are the ones that matter here — recommending something
   already completed, or something whose prerequisites are missing — and those
   are exactly what rules handle well.

Similarity supplies breadth (what else is like what you are looking at); rules
supply correctness (what you are ready for, and what you have not already
done). The two are combined with explicit weights rather than tuned.
"""

import time
from typing import Any, Dict, List, Optional, Sequence, Set

from pydantic import BaseModel, ConfigDict, Field

from contracts.recommendations import (
    LearnerLevel,
    Recommendation,
    RecommendationKind,
    RecommendationSet,
    RecommendationSignal,
)
from contracts.search import SearchEntityType, SearchQuery, SearchStatus

__all__ = ["RecommendationRequest", "RecommendationEngine", "SIGNAL_WEIGHTS"]

#: Contribution of each signal. Similarity is the largest single term, but the
#: rule signals together outweigh it — a highly similar item the user has
#: already completed should not win.
SIGNAL_WEIGHTS: Dict[str, float] = {
    "similarity": 0.40,
    "topic_match": 0.25,
    "level_match": 0.20,
    "prerequisite_ready": 0.15,
    "project_relevance": 0.25,
    "weak_topic": 0.20,
    # -- penalties -------------------------------------------------------
    "already_completed": -1.0,
    "prerequisite_missing": -0.5,
    "level_mismatch": -0.15,
}

#: Which entity types satisfy which recommendation kind.
_KIND_BY_ENTITY = {
    SearchEntityType.CONCEPT: RecommendationKind.CONCEPT,
    SearchEntityType.LESSON: RecommendationKind.LESSON,
    SearchEntityType.MISSION: RecommendationKind.MISSION,
    SearchEntityType.SPACE_OBJECT: RecommendationKind.SPACE_OBJECT,
    SearchEntityType.DOCUMENT: RecommendationKind.REFERENCE,
}

#: Difficulty ordering, for level matching.
_DIFFICULTY_ORDER = ("INTRODUCTORY", "INTERMEDIATE", "ADVANCED")

#: What each learner level should mostly be shown.
_LEVEL_PREFERENCES: Dict[LearnerLevel, Dict[str, Any]] = {
    LearnerLevel.BEGINNER: {
        "difficulty": "INTRODUCTORY",
        "kinds": (RecommendationKind.LESSON, RecommendationKind.CONCEPT),
        "avoid": (RecommendationKind.REFERENCE,),
    },
    LearnerLevel.INTERMEDIATE: {
        "difficulty": "INTERMEDIATE",
        "kinds": (RecommendationKind.CONCEPT, RecommendationKind.LESSON,
                  RecommendationKind.MISSION),
        "avoid": (),
    },
    LearnerLevel.ADVANCED: {
        "difficulty": "ADVANCED",
        "kinds": (RecommendationKind.CONCEPT, RecommendationKind.MISSION,
                  RecommendationKind.REFERENCE),
        "avoid": (),
    },
    LearnerLevel.RESEARCHER: {
        "difficulty": "ADVANCED",
        #: A researcher wants primary sources, not tutorials.
        "kinds": (RecommendationKind.REFERENCE, RecommendationKind.SPACE_OBJECT,
                  RecommendationKind.MISSION),
        "avoid": (RecommendationKind.LESSON,),
    },
}


class RecommendationRequest(BaseModel):
    """What the recommender knows about the user and the moment."""

    model_config = ConfigDict(extra="forbid")

    #: What the user is looking at now. The strongest signal.
    current_topic: Optional[str] = None
    #: The record they are currently on, if any.
    current_item_id: Optional[str] = None
    level: LearnerLevel = LearnerLevel.BEGINNER

    completed_ids: List[str] = Field(default_factory=list)
    in_progress_ids: List[str] = Field(default_factory=list)
    #: Recently viewed records, most recent first.
    recent_ids: List[str] = Field(default_factory=list)
    #: topic -> 0..1 mastery, when learning progress supplies it.
    topic_mastery: Dict[str, float] = Field(default_factory=dict)

    #: Free-text description of the user's project, when one is in scope.
    project_context: Optional[str] = None
    #: Subsystems the project touches, e.g. from a failure analysis.
    project_subsystems: List[str] = Field(default_factory=list)

    kinds: List[RecommendationKind] = Field(default_factory=list)
    limit: int = Field(default=6, ge=1, le=50)

    def profile_summary(self) -> str:
        parts = ["level {0}".format(self.level.value.lower())]
        if self.current_topic:
            parts.append("looking at {0!r}".format(self.current_topic))
        if self.completed_ids:
            parts.append("{0} item(s) completed".format(len(self.completed_ids)))
        if self.project_context:
            parts.append("has a project in scope")
        weak = self.weak_topics()
        if weak:
            parts.append("weakest topics: {0}".format(", ".join(weak)))
        return "; ".join(parts)

    def weak_topics(self, threshold: float = 0.5) -> List[str]:
        return sorted(
            topic for topic, score in self.topic_mastery.items()
            if score < threshold
        )


class RecommendationEngine:
    """Rules plus semantic similarity."""

    def __init__(
        self,
        retriever: Any,
        record_store: Optional[Any] = None,
        weights: Optional[Dict[str, float]] = None,
        candidate_pool: int = 30,
    ):
        self.retriever = retriever
        self.record_store = record_store
        self.weights = dict(SIGNAL_WEIGHTS)
        if weights:
            self.weights.update(weights)
        self.candidate_pool = candidate_pool

    # ------------------------------------------------------------------
    def recommend(self, request: RecommendationRequest) -> RecommendationSet:
        """Produce a ranked, explained set of recommendations."""
        started = time.time()
        result = RecommendationSet(profile_summary=request.profile_summary())

        candidates = self._candidates(request)
        if not candidates:
            result.diagnostics["reason"] = "no candidates retrieved"
            return result

        scored: List[Recommendation] = []
        seen: Set[str] = set()

        for candidate in candidates:
            if candidate.id in seen:
                continue
            seen.add(candidate.id)

            kind = _KIND_BY_ENTITY.get(
                candidate.entity_type, RecommendationKind.REFERENCE
            )
            if request.kinds and kind not in request.kinds:
                continue

            if candidate.id in request.completed_ids:
                result.excluded[candidate.id] = "already completed"
                continue
            if candidate.id == request.current_item_id:
                result.excluded[candidate.id] = "currently open"
                continue

            signals = self._score(candidate, kind, request)
            total = sum(signal.weight for signal in signals)
            if total <= 0.0:
                result.excluded[candidate.id] = (
                    "scored {0:.2f}; no positive signal".format(total)
                )
                continue

            scored.append(
                Recommendation(
                    id=candidate.id,
                    kind=kind,
                    title=candidate.title,
                    score=min(1.0, total),
                    reason=self._reason(signals, candidate, request),
                    signals=signals,
                    summary=candidate.summary,
                    topics=list(candidate.topics),
                    difficulty=self._difficulty(candidate.id),
                    url=candidate.url,
                    sources=list(candidate.provenance.sources),
                    metadata={"entity_type": candidate.entity_type.value},
                )
            )

        scored.sort(key=lambda item: (-item.score, item.title))
        result.items = scored[:request.limit]
        result.diagnostics.update({
            "candidates": len(candidates),
            "scored": len(scored),
            "latency_ms": (time.time() - started) * 1000.0,
        })
        return result

    # -- candidate generation ----------------------------------------------
    def _candidates(self, request: RecommendationRequest):
        """Gather candidates from similarity and from the user's weak topics.

        Two sources, because they answer different questions. Similarity to the
        current topic gives "more like this". Weak topics give "what you are
        avoiding", which similarity will never surface precisely because the
        user has not been looking at it.
        """
        candidates = []
        queries = []

        if request.current_topic:
            queries.append(request.current_topic)
        if request.project_context:
            queries.append(request.project_context)
        for topic in request.weak_topics():
            queries.append(topic)
        for subsystem in request.project_subsystems:
            queries.append(subsystem.replace("_", " ").lower())

        if not queries:
            #: Nothing known about the user. Fall back to browsing the
            #: introductory material rather than returning nothing.
            queries.append("introduction to rocketry and orbital mechanics")

        per_query = max(3, self.candidate_pool // max(1, len(queries)))
        for text in queries:
            response = self.retriever.search(
                SearchQuery(text=text, limit=per_query)
            )
            if response.status is SearchStatus.OK:
                candidates.extend(response.results)
        return candidates

    # -- scoring -----------------------------------------------------------
    def _score(self, candidate, kind, request) -> List[RecommendationSignal]:
        signals: List[RecommendationSignal] = []

        def add(name, multiplier=1.0, detail=""):
            weight = self.weights.get(name, 0.0) * multiplier
            if weight:
                signals.append(
                    RecommendationSignal(name=name, weight=weight, detail=detail)
                )

        #: Retrieval score stands in for semantic similarity.
        if candidate.score > 0:
            add("similarity", candidate.score,
                "similar to what you are looking at")

        topics = {topic.lower() for topic in candidate.topics}
        if request.current_topic and request.current_topic.lower() in topics:
            add("topic_match", 1.0,
                "covers {0}".format(request.current_topic))

        weak = {topic.lower() for topic in request.weak_topics()}
        overlap = topics & weak
        if overlap:
            add("weak_topic", 1.0,
                "addresses {0}, where your progress is lowest".format(
                    ", ".join(sorted(overlap))
                ))

        difficulty = self._difficulty(candidate.id)
        preference = _LEVEL_PREFERENCES[request.level]
        if difficulty:
            if difficulty == preference["difficulty"]:
                add("level_match", 1.0,
                    "matches your {0} level".format(request.level.value.lower()))
            elif _too_advanced(difficulty, preference["difficulty"]):
                add("level_mismatch", 1.0,
                    "harder than your current level")

        if kind in preference["kinds"]:
            add("level_match", 0.5, "the kind of material suited to your level")
        if kind in preference["avoid"]:
            add("level_mismatch", 1.0,
                "not the kind of material your level usually wants")

        ready, missing = self._prerequisites(candidate.id, request)
        if missing:
            add("prerequisite_missing", 1.0,
                "builds on {0}, which you have not covered".format(
                    ", ".join(missing)
                ))
        elif ready:
            add("prerequisite_ready", 1.0,
                "you have covered its prerequisites")

        if request.project_subsystems:
            subsystems = {
                item.replace("_", " ").lower()
                for item in request.project_subsystems
            }
            if topics & subsystems:
                add("project_relevance", 1.0,
                    "relevant to your project's {0}".format(
                        ", ".join(sorted(topics & subsystems))
                    ))

        return signals

    def _prerequisites(self, canonical_id, request):
        """Whether the user has covered what this item builds on.

        Only meaningful for content that declares prerequisites; everything
        else returns `(False, [])` and neither gains nor loses.
        """
        record = self._record(canonical_id)
        prerequisites = list(getattr(record, "prerequisites", []) or [])
        if not prerequisites:
            return (False, [])
        covered = set(request.completed_ids)
        missing = [item for item in prerequisites if item not in covered]
        return (not missing, [_readable(item) for item in missing])

    def _difficulty(self, canonical_id) -> Optional[str]:
        record = self._record(canonical_id)
        value = getattr(record, "difficulty", None)
        return value.value if value is not None else None

    def _record(self, canonical_id):
        if self.record_store is None:
            return None
        getter = getattr(self.record_store, "get", None)
        return getter(canonical_id) if getter else None

    # -- explanation -------------------------------------------------------
    def _reason(self, signals, candidate, request) -> str:
        """Plain-language justification, built from the strongest signals.

        Assembled from the signals rather than generated, so the explanation
        cannot drift from the arithmetic that produced the ranking.
        """
        #: "similar to what you are looking at" is true of every candidate and
        #: therefore tells the reader nothing. It is ranked last so a specific
        #: reason — a weak topic, a prerequisite met, a project connection —
        #: is what the user actually sees, even when similarity scored higher.
        positive = sorted(
            [signal for signal in signals if signal.weight > 0 and signal.detail],
            key=lambda signal: (signal.name == "similarity", -signal.weight),
        )
        if not positive:
            return "Related to what you are working on."

        parts = [signal.detail for signal in positive[:2]]
        reason = parts[0][0].upper() + parts[0][1:]
        if len(parts) > 1:
            reason += ", and {0}".format(parts[1])
        return reason + "."


def _too_advanced(difficulty: str, target: str) -> bool:
    try:
        return _DIFFICULTY_ORDER.index(difficulty) > _DIFFICULTY_ORDER.index(target)
    except ValueError:
        return False


def _readable(canonical_id: str) -> str:
    return str(canonical_id).split(":", 1)[-1].replace("-", " ")
