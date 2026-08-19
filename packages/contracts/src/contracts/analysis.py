"""Analysis contracts — failure analysis and mission intelligence.

Rendered by the frontend, produced by P4.

The shape of `FailureAnalysis` encodes the rule that matters most here: it has
**two separate field groups**, one for what the simulator did and one for the
physics that explains it. They cannot be conflated by accident, because they
are different fields with different provenance:

* `observations` — what the run actually produced. Source: the simulator.
  These are true statements about a model, not about the world.
* `explanation` — why that happens physically. Source: cited scientific and
  engineering references.

A UI can render the first as "your simulation showed…" and the second as
"this happens because…", and no amount of prompt drift can swap them.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._time import utc_now
from .ai import Citation, ConfidenceLevel, ContextItem
from .provenance import SourceReference

__all__ = [
    "FailureSeverity",
    "SubsystemKind",
    "SimulationObservation",
    "ScientificExplanation",
    "Mitigation",
    "FailureAnalysis",
    "MissionSummary",
    "MissionTimelineEntry",
    "SourceConflict",
]


class FailureSeverity(str, Enum):
    """Severity as the simulation engine's documented rules define it."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    FATAL = "fatal"


class SubsystemKind(str, Enum):
    """Which part of the vehicle or flight a finding concerns."""

    PROPULSION = "PROPULSION"
    STRUCTURE = "STRUCTURE"
    AERODYNAMICS = "AERODYNAMICS"
    GUIDANCE = "GUIDANCE"
    STAGING = "STAGING"
    MASS_PROPERTIES = "MASS_PROPERTIES"
    TRAJECTORY = "TRAJECTORY"
    STABILITY = "STABILITY"
    UNKNOWN = "UNKNOWN"


class SimulationObservation(BaseModel):
    """Something the simulation run produced.

    A statement about the model, never about the world. `is_model_output` is
    hard-coded true and cannot be unset — the field exists so a renderer can
    assert on it rather than infer from context.
    """

    model_config = ConfigDict(extra="forbid")

    #: What was observed, in the run's own terms.
    statement: str
    #: Seconds since ignition, when the run recorded one.
    time_s: Optional[float] = None
    #: The engine's own event or failure identifier.
    event_type: Optional[str] = None
    severity: Optional[FailureSeverity] = None
    #: Measured values from the run, with units, e.g. {"acceleration_ms2": 91.4}.
    values: Dict[str, Any] = Field(default_factory=dict)
    phase: Optional[str] = None

    @property
    def is_model_output(self) -> bool:
        """Always true. Present so a UI can assert rather than assume."""
        return True


class ScientificExplanation(BaseModel):
    """Why the observed behaviour happens physically.

    Must carry citations. An explanation with no source is the model's own
    inference and is labelled as such rather than presented as established.
    """

    model_config = ConfigDict(extra="forbid")

    statement: str
    citations: List[Citation] = Field(default_factory=list)
    #: True when nothing in the corpus supported this and it is the model's
    #: own reasoning. Rendered differently by the UI.
    is_inference: bool = False

    @model_validator(mode="after")
    def _check(self) -> "ScientificExplanation":
        if not self.citations and not self.is_inference:
            raise ValueError(
                "a scientific explanation must either carry citations or be "
                "marked as an inference; an uncited claim presented as "
                "established is the failure this field exists to prevent"
            )
        return self


class Mitigation(BaseModel):
    """A change that might address the failure."""

    model_config = ConfigDict(extra="forbid")

    action: str
    rationale: str = ""
    subsystem: SubsystemKind = SubsystemKind.UNKNOWN
    #: Cited support, when the suggestion rests on a reference rather than on
    #: general reasoning.
    citations: List[Citation] = Field(default_factory=list)
    #: Honest about whether this is a rule of thumb or a sourced practice.
    is_heuristic: bool = True


class FailureAnalysis(BaseModel):
    """The full analysis of one simulation failure."""

    model_config = ConfigDict(extra="forbid")

    simulation_id: Optional[str] = None
    #: One-line summary of what happened.
    summary: str = ""

    #: What the simulator did. Source: the simulation engine.
    observations: List[SimulationObservation] = Field(default_factory=list)
    #: Why it happens physically. Source: cited references.
    explanation: List[ScientificExplanation] = Field(default_factory=list)

    likely_cause: Optional[str] = None
    #: How sure the analysis is about the cause.
    cause_confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    affected_subsystems: List[SubsystemKind] = Field(default_factory=list)
    #: Named components from the vehicle configuration, when identifiable.
    affected_components: List[str] = Field(default_factory=list)
    consequences: List[str] = Field(default_factory=list)
    mitigations: List[Mitigation] = Field(default_factory=list)

    #: What is genuinely uncertain about this analysis.
    uncertainty: List[str] = Field(default_factory=list)
    #: Which simulator approximations bear on this conclusion. Required.
    simulation_limitations: List[str] = Field(default_factory=list)

    sources: List[SourceReference] = Field(default_factory=list)
    context_items: List[ContextItem] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> "FailureAnalysis":
        if self.explanation and not self.simulation_limitations:
            raise ValueError(
                "an analysis that explains simulator behaviour must state which "
                "simulator approximations bear on it; the engine is an "
                "educational model and must never be presented as reproducing "
                "reality exactly"
            )
        return self

    @property
    def is_grounded(self) -> bool:
        """True when every explanation is cited rather than inferred."""
        return bool(self.explanation) and all(
            item.citations for item in self.explanation
        )

    def observation_statements(self) -> List[str]:
        return [item.statement for item in self.observations]


class MissionTimelineEntry(BaseModel):
    """One dated event in a mission's history."""

    model_config = ConfigDict(extra="forbid")

    label: str
    date: Optional[datetime] = None
    #: Free-text when only a year or a phase is known.
    when: Optional[str] = None
    description: Optional[str] = None
    citations: List[Citation] = Field(default_factory=list)


class SourceConflict(BaseModel):
    """Two sources disagreeing about a mission fact."""

    model_config = ConfigDict(extra="forbid")

    field: str
    #: source name -> what it says.
    values: Dict[str, str] = Field(default_factory=dict)
    note: str = ""


class MissionSummary(BaseModel):
    """Mission intelligence assembled from authoritative sources."""

    model_config = ConfigDict(extra="forbid")

    canonical_id: Optional[str] = None
    name: str
    summary: str = ""
    agency: Optional[str] = None
    scientific_objectives: List[str] = Field(default_factory=list)
    timeline: List[MissionTimelineEntry] = Field(default_factory=list)
    spacecraft: List[str] = Field(default_factory=list)
    launch_vehicle: Optional[str] = None
    destinations: List[str] = Field(default_factory=list)
    major_events: List[str] = Field(default_factory=list)
    outcome: Optional[str] = None
    scientific_findings: List[str] = Field(default_factory=list)

    citations: List[Citation] = Field(default_factory=list)
    sources: List[SourceReference] = Field(default_factory=list)
    #: Where sources disagree. Shown, never silently resolved.
    conflicts: List[SourceConflict] = Field(default_factory=list)
    #: Fields the sources did not cover. Stated rather than filled in.
    unknown_fields: List[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    generated_at: datetime = Field(default_factory=utc_now)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)
