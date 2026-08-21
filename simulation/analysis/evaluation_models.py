"""Records for a mission evaluation.

A score with no working shown is a verdict, and a verdict teaches nothing. Every
criterion here carries what was measured, the band it was measured against, how
many points it was worth and how many it earned — so a category score of 56 can
always be decomposed into the specific numbers that produced it.
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["EvaluationCriterion", "EvaluationCategory", "MissionEvaluation"]


class EvaluationCriterion(BaseModel):
    """One measurable thing, scored against a band."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    #: What the flight actually produced.
    measured: float
    unit: str = ""
    #: The acceptable band. Either bound may be absent for a one-sided limit.
    good_min: Optional[float] = None
    good_max: Optional[float] = None
    #: Points this criterion contributes to its category.
    weight: float = Field(gt=0)
    #: Points earned, between 0 and `weight`.
    earned: float = Field(ge=0)
    passed: bool
    #: Why this criterion exists, in one sentence.
    note: str = ""
    #: What to change, when it did not pass.
    recommendation: Optional[str] = None


class EvaluationCategory(BaseModel):
    """A group of criteria, scored out of 100."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    score: int = Field(ge=0, le=100)
    summary: str
    #: True when the flight never exercised this category — a vehicle with no
    #: recovery system should not be marked down for not deploying a parachute.
    not_applicable: bool = False
    criteria: List[EvaluationCriterion] = Field(default_factory=list)


class MissionEvaluation(BaseModel):
    """The complete report."""

    model_config = ConfigDict(extra="forbid")

    overall_score: int = Field(ge=0, le=100)
    categories: List[EvaluationCategory] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    #: What this report cannot see. Stated, because an evaluation that implies
    #: it covers everything is misleading.
    limitations: List[str] = Field(default_factory=list)

    def to_dict(self) -> dict:
        """JSON-safe form, for the API envelope."""
        return self.model_dump(mode="json")
