"""Recommendation contracts.

`Recommendation` is rendered by the frontend and produced by P4.

Two fields are required rather than optional, and both for the same reason: a
recommendation the user cannot evaluate is not useful. `reason` says *why this,
for you, now* in plain language, and `score` says how strongly. A recommender
that returns a ranked list with no explanation trains people to ignore it.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._time import utc_now
from .provenance import SourceReference

__all__ = [
    "RecommendationKind",
    "LearnerLevel",
    "RecommendationSignal",
    "Recommendation",
    "RecommendationSet",
]


class RecommendationKind(str, Enum):
    """What kind of thing is being recommended."""

    LESSON = "LESSON"
    COURSE = "COURSE"
    CONCEPT = "CONCEPT"
    MISSION = "MISSION"
    SPACE_OBJECT = "SPACE_OBJECT"
    ROCKET_COMPONENT = "ROCKET_COMPONENT"
    EXPERIMENT = "EXPERIMENT"
    REFERENCE = "REFERENCE"
    #: A change to the user's own design, suggested from their project.
    DESIGN_CHANGE = "DESIGN_CHANGE"


class LearnerLevel(str, Enum):
    """How much the user already knows. Drives difficulty matching."""

    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"
    #: Wants primary sources and technical documents rather than lessons.
    RESEARCHER = "RESEARCHER"


class RecommendationSignal(BaseModel):
    """One reason a recommendation scored what it did.

    Kept individually rather than collapsed into a number, so a surprising
    recommendation can be traced to the signal that produced it.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    #: Contribution to the final score. May be negative.
    weight: float
    detail: str = ""


class Recommendation(BaseModel):
    """One recommended item."""

    model_config = ConfigDict(extra="forbid")

    #: Canonical id of the recommended record.
    id: str
    kind: RecommendationKind
    title: str
    #: 0..1. Comparable within one result set, not across sets.
    score: float = Field(ge=0.0, le=1.0)
    #: Plain-language justification. Required.
    reason: str = Field(min_length=1)
    signals: List[RecommendationSignal] = Field(default_factory=list)

    summary: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    difficulty: Optional[str] = None
    url: Optional[str] = None
    #: Provenance, when the recommendation rests on sourced material rather
    #: than on the user's own activity.
    sources: List[SourceReference] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> "Recommendation":
        if not self.reason.strip():
            raise ValueError(
                "a recommendation must explain itself; an unexplained "
                "suggestion cannot be evaluated by the person receiving it"
            )
        return self


class RecommendationSet(BaseModel):
    """A ranked set of recommendations, with the context that produced them."""

    model_config = ConfigDict(extra="forbid")

    items: List[Recommendation] = Field(default_factory=list)
    #: What the recommender understood about the request.
    profile_summary: str = ""
    #: Items deliberately excluded, and why — e.g. already completed.
    excluded: Dict[str, str] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=utc_now)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.items

    def by_kind(self, kind: RecommendationKind) -> List[Recommendation]:
        return [item for item in self.items if item.kind is kind]

    def top(self, limit: int = 3) -> List[Recommendation]:
        return self.items[:limit]
