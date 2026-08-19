"""Read-models for project data owned by Person 2.

**These are not database models.** P2 owns the schema and the persistence; these
describe the shape P4 expects to *receive* from P2's HTTP API, so the AI layer
has something typed to work with. Fields are optional almost throughout,
because P4 must degrade rather than fail when P2's payload differs — a missing
field is a smaller problem than a crash in the answer path.

Every one of these carries `owner_user_id`, and every one is constructed only
from a response P2 returned to the *caller's own* bearer token. That is the
authorization boundary: P4 holds no privileged credential and therefore cannot
read data the user could not read themselves.

Needs P2 sign-off before the frontend depends on it.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from contracts._time import utc_now

__all__ = [
    "ProjectContextKind",
    "ProjectSummary",
    "MissionConfiguration",
    "VehicleConfiguration",
    "VehicleStage",
    "VehicleComponent",
    "SimulationSummary",
    "LearningProgress",
    "UserNote",
    "ProjectContext",
]


class ProjectContextKind(str, Enum):
    """The kinds of project data the assistant can draw on.

    Named so context selection can say *which* kinds a question needs, and so a
    test can assert that an unrelated kind was not fetched.
    """

    PROJECT = "PROJECT"
    REQUIREMENTS = "REQUIREMENTS"
    MISSION_CONFIG = "MISSION_CONFIG"
    VEHICLE_CONFIG = "VEHICLE_CONFIG"
    SIMULATION_RESULT = "SIMULATION_RESULT"
    FAILURE_EVENT = "FAILURE_EVENT"
    TELEMETRY = "TELEMETRY"
    LEARNING_PROGRESS = "LEARNING_PROGRESS"
    USER_NOTES = "USER_NOTES"


class _Owned(BaseModel):
    """Base for anything belonging to a user.

    `owner_user_id` is not decoration: the isolation check compares it against
    the requesting user before any of this reaches a prompt.
    """

    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    owner_user_id: Optional[str] = None
    project_id: Optional[str] = None


class ProjectSummary(_Owned):
    """A project, as `/projects/{id}` returns it."""

    name: Optional[str] = None
    description: Optional[str] = None
    #: Free-text requirements the user wrote for their design.
    requirements: List[str] = Field(default_factory=list)
    target: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class VehicleComponent(BaseModel):
    """One component on a stage."""

    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    name: Optional[str] = None
    component_type: Optional[str] = None
    mass_kg: Optional[float] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class VehicleStage(BaseModel):
    """One stage of a launch vehicle."""

    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    index: Optional[int] = None
    name: Optional[str] = None
    dry_mass_kg: Optional[float] = None
    propellant_mass_kg: Optional[float] = None
    thrust_n: Optional[float] = None
    specific_impulse_s: Optional[float] = None
    burn_time_s: Optional[float] = None
    engine_count: Optional[int] = None
    components: List[VehicleComponent] = Field(default_factory=list)

    def mass_ratio(self) -> Optional[float]:
        """Wet over dry mass. `None` when either is missing or implausible."""
        if not self.dry_mass_kg or self.propellant_mass_kg is None:
            return None
        if self.dry_mass_kg <= 0:
            return None
        return (self.dry_mass_kg + self.propellant_mass_kg) / self.dry_mass_kg


class VehicleConfiguration(_Owned):
    """A launch vehicle, as `/vehicles/{id}` returns it."""

    name: Optional[str] = None
    mission_id: Optional[str] = None
    stages: List[VehicleStage] = Field(default_factory=list)
    total_mass_kg: Optional[float] = None
    payload_mass_kg: Optional[float] = None

    @property
    def stage_count(self) -> int:
        return len(self.stages)

    def describe(self) -> str:
        """A compact description for a prompt."""
        parts = ["{0} ({1} stage(s))".format(self.name or "vehicle",
                                             self.stage_count)]
        for stage in self.stages:
            bits = ["stage {0}".format(stage.index if stage.index is not None
                                       else "?")]
            if stage.dry_mass_kg is not None:
                bits.append("dry {0:g} kg".format(stage.dry_mass_kg))
            if stage.propellant_mass_kg is not None:
                bits.append("propellant {0:g} kg".format(stage.propellant_mass_kg))
            if stage.thrust_n is not None:
                bits.append("thrust {0:g} N".format(stage.thrust_n))
            if stage.specific_impulse_s is not None:
                bits.append("Isp {0:g} s".format(stage.specific_impulse_s))
            parts.append("  " + ", ".join(bits))
        return "\n".join(parts)


class MissionConfiguration(_Owned):
    """A mission, as `/missions/{id}` returns it."""

    name: Optional[str] = None
    objective: Optional[str] = None
    target_orbit: Optional[str] = None
    target_altitude_km: Optional[float] = None
    payload_mass_kg: Optional[float] = None
    launch_site: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)

    def describe(self) -> str:
        bits = [self.name or "mission"]
        if self.objective:
            bits.append("objective: {0}".format(self.objective))
        if self.target_orbit:
            bits.append("target: {0}".format(self.target_orbit))
        if self.target_altitude_km is not None:
            bits.append("altitude {0:g} km".format(self.target_altitude_km))
        if self.payload_mass_kg is not None:
            bits.append("payload {0:g} kg".format(self.payload_mass_kg))
        return "; ".join(bits)


class SimulationSummary(_Owned):
    """A simulation run, as `/simulations/{id}` returns it.

    Kept loose on purpose: Person 3 owns the real `SimulationResult` shape, and
    Task 24 binds to it properly. This is what the *API* returns about a run.
    """

    mission_id: Optional[str] = None
    vehicle_id: Optional[str] = None
    status: Optional[str] = None
    succeeded: Optional[bool] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    #: Terminal outcome in the engine's own words.
    outcome: Optional[str] = None
    max_altitude_km: Optional[float] = None
    max_velocity_ms: Optional[float] = None
    #: Event and failure payloads exactly as the API returned them.
    events: List[Dict[str, Any]] = Field(default_factory=list)
    failures: List[Dict[str, Any]] = Field(default_factory=list)
    engine_version: Optional[str] = None

    @property
    def failed(self) -> bool:
        if self.succeeded is not None:
            return not self.succeeded
        return bool(self.failures)


class LearningProgress(_Owned):
    """A user's learning state, from `/learning/progress`."""

    completed_lesson_slugs: List[str] = Field(default_factory=list)
    in_progress_lesson_slugs: List[str] = Field(default_factory=list)
    #: Topic -> a 0..1 mastery estimate, when P2 supplies one.
    topic_mastery: Dict[str, float] = Field(default_factory=dict)
    level: Optional[str] = None
    last_activity_at: Optional[datetime] = None

    def weakest_topics(self, limit: int = 3) -> List[str]:
        return [
            topic for topic, _ in
            sorted(self.topic_mastery.items(), key=lambda item: item[1])[:limit]
        ]


class UserNote(_Owned):
    """A note the user wrote.

    Untrusted input. It is user-authored text that reaches a prompt, so it is
    sanitized on the same path as any retrieved document.
    """

    title: Optional[str] = None
    body: str = ""
    created_at: Optional[datetime] = None


class ProjectContext(BaseModel):
    """Everything fetched about one project for one question."""

    model_config = ConfigDict(extra="forbid")

    #: The user the data was fetched *for*. Every contained record must match.
    user_id: Optional[str] = None
    project: Optional[ProjectSummary] = None
    mission: Optional[MissionConfiguration] = None
    vehicle: Optional[VehicleConfiguration] = None
    simulation: Optional[SimulationSummary] = None
    learning: Optional[LearningProgress] = None
    notes: List[UserNote] = Field(default_factory=list)

    #: Which kinds were requested, and which were actually obtained.
    requested_kinds: List[ProjectContextKind] = Field(default_factory=list)
    fetched_kinds: List[ProjectContextKind] = Field(default_factory=list)
    #: kind -> why it was not fetched (not relevant, forbidden, unavailable).
    skipped: Dict[str, str] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=utc_now)

    @property
    def is_empty(self) -> bool:
        return not any(
            (self.project, self.mission, self.vehicle, self.simulation,
             self.learning, self.notes)
        )

    def owned_records(self) -> List[Any]:
        """Every record carrying an owner, for the isolation check."""
        records: List[Any] = []
        for item in (self.project, self.mission, self.vehicle, self.simulation,
                     self.learning):
            if item is not None:
                records.append(item)
        records.extend(self.notes)
        return records
