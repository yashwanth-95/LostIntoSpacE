"""P4's read-view of Person 3's simulation output.

**Status of P3's contracts, checked at the time of writing.** They are
specified in detail in `docs/simulation/SIMULATION.md` — state vector, event
types, failure-detection rules, severity levels, SI units — but the
`simulation/` package contains only `.gitkeep` files. There is no
`SimulationResult`, `MissionEvent`, `FailureEvent` or `Telemetry` class to
import.

So this module maps from the **documented specification**, not from an
imagined API. It parses whatever dict shapes arrive, accepts the documented
field names and a few obvious aliases, and reports what it could not
understand rather than guessing. When P3's classes land, this becomes a thin
adapter over them; nothing above it changes.

Nothing in `simulation/` is touched, and no physics is reimplemented here.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from contracts.analysis import FailureSeverity, SubsystemKind

__all__ = [
    "MODEL_FIDELITY",
    "DOCUMENTED_EVENT_TYPES",
    "FAILURE_RULES",
    "TelemetrySample",
    "SimulationEventView",
    "SimulationResultView",
    "parse_simulation_result",
]

#: From `docs/simulation/SIMULATION.md`. Every one of these is an
#: approximation, and an analysis that leans on a model must say which.
#: This is the source of the `simulation_limitations` a `FailureAnalysis`
#: is required to carry.
MODEL_FIDELITY: Dict[str, str] = {
    "gravity": "inverse-square g(h) = g0(R/(R+h))^2 — an analytical "
               "approximation; no oblateness, no third-body effects",
    "atmosphere": "US Standard Atmosphere 1976 — a static average profile; no "
                  "weather, no seasonal or latitude variation, no winds",
    "drag": "Fd = 0.5*rho*v^2*Cd*A with a fixed Cd — no Mach-dependent drag "
            "rise, no angle-of-attack dependence",
    "thrust": "F = Isp*g0*mdot, constant per stage — no throttling, no "
              "altitude compensation of nozzle performance",
    "mass": "linear propellant depletion during burn — no residuals, no "
            "boil-off, no ullage",
    "trajectory": "RK4 integration, 3 degrees of freedom — translation only; "
                  "no rotational dynamics, so real attitude coupling is absent",
    "stability": "Barrowman centre-of-pressure and centre-of-gravity "
                 "calculation — a subsonic slender-body approximation",
}

#: Event identifiers the engine documents. Anything else is passed through
#: unrecognised rather than dropped.
DOCUMENTED_EVENT_TYPES = (
    "ignition", "liftoff", "max_q", "meco", "staging", "apogee",
    "supersonic", "impact",
)

#: The documented failure-detection rules, and what each implies. The mapping
#: to a subsystem is what lets an analysis name the affected part without the
#: language model guessing.
FAILURE_RULES: Dict[str, Dict[str, Any]] = {
    "insufficient_twr": {
        "condition": "thrust/weight < 1.0 at ignition",
        "severity": FailureSeverity.FATAL,
        "subsystem": SubsystemKind.PROPULSION,
        "concepts": ["concept:staging", "concept:specific-impulse",
                     "concept:delta-v-budget"],
        "plain": "the vehicle could not lift its own weight",
    },
    "excessive_q": {
        "condition": "dynamic pressure exceeded the configured threshold",
        "severity": FailureSeverity.CRITICAL,
        "subsystem": SubsystemKind.AERODYNAMICS,
        "concepts": ["concept:max-q"],
        "plain": "aerodynamic pressure exceeded what the airframe was given as "
                 "its limit",
    },
    "structural_overload": {
        "condition": "acceleration exceeded the configured g-limit",
        "severity": FailureSeverity.CRITICAL,
        "subsystem": SubsystemKind.STRUCTURE,
        "concepts": ["concept:max-q", "concept:staging"],
        "plain": "acceleration exceeded the structural limit given for the "
                 "vehicle",
    },
    "instability": {
        "condition": "centre of pressure ahead of centre of gravity "
                     "(static margin < 0)",
        "severity": FailureSeverity.CRITICAL,
        "subsystem": SubsystemKind.STABILITY,
        "concepts": ["concept:orbital-mechanics"],
        "plain": "the vehicle was aerodynamically unstable",
    },
    "trajectory_divergence": {
        "condition": "horizontal velocity far from the expected profile",
        "severity": FailureSeverity.WARNING,
        "subsystem": SubsystemKind.TRAJECTORY,
        "concepts": ["concept:orbital-mechanics", "concept:delta-v-budget"],
        "plain": "the flight path departed from the intended profile",
    },
    "fuel_exhaustion": {
        "condition": "propellant depleted earlier than expected",
        "severity": FailureSeverity.CRITICAL,
        "subsystem": SubsystemKind.PROPULSION,
        "concepts": ["concept:delta-v-budget", "concept:specific-impulse",
                     "concept:staging"],
        "plain": "the stage ran out of propellant before its job was done",
    },
}

#: Aliases seen in the wild for each documented field. Kept explicit so an
#: unexpected payload is diagnosable rather than silently half-parsed.
_TIME_KEYS = ("time_s", "t", "time", "timestamp_s", "mission_time_s")
_TYPE_KEYS = ("event_type", "type", "kind", "name", "id")
_SEVERITY_KEYS = ("severity", "level")
_PHASE_KEYS = ("phase", "flight_phase", "stage_phase")
_MESSAGE_KEYS = ("message", "description", "detail", "reason", "summary")


def _first(payload: Dict[str, Any], keys: Sequence[str]) -> Optional[Any]:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


class TelemetrySample(BaseModel):
    """One telemetry snapshot, per the documented state vector.

    All SI, matching the engine's units convention. Every field is optional:
    a sampler that omits a channel must not break the analysis.
    """

    model_config = ConfigDict(extra="allow")

    time_s: Optional[float] = None
    altitude_m: Optional[float] = None
    velocity_ms: Optional[float] = None
    acceleration_ms2: Optional[float] = None
    mass_kg: Optional[float] = None
    dynamic_pressure_pa: Optional[float] = None
    mach: Optional[float] = None
    thrust_n: Optional[float] = None
    drag_n: Optional[float] = None
    stage: Optional[int] = None
    phase: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "TelemetrySample":
        if not isinstance(payload, dict):
            return cls()
        data: Dict[str, Any] = dict(payload)
        mapped = {
            "time_s": _first(payload, _TIME_KEYS),
            "altitude_m": _first(payload, ("altitude_m", "altitude", "alt_m", "h")),
            "velocity_ms": _first(payload, ("velocity_ms", "velocity", "speed_ms",
                                            "v")),
            "acceleration_ms2": _first(payload, ("acceleration_ms2",
                                                 "acceleration", "accel_ms2", "a")),
            "mass_kg": _first(payload, ("mass_kg", "mass")),
            "dynamic_pressure_pa": _first(payload, ("dynamic_pressure_pa",
                                                    "dynamic_pressure", "q", "q_pa")),
            "mach": _first(payload, ("mach", "mach_number")),
            "thrust_n": _first(payload, ("thrust_n", "thrust")),
            "drag_n": _first(payload, ("drag_n", "drag")),
            "stage": _first(payload, ("stage", "stage_index")),
            "phase": _first(payload, _PHASE_KEYS),
        }
        data.update({k: v for k, v in mapped.items() if v is not None})
        return cls.model_validate(data)


class SimulationEventView(BaseModel):
    """One event or failure from a run."""

    model_config = ConfigDict(extra="allow")

    event_type: str = "unknown"
    time_s: Optional[float] = None
    severity: FailureSeverity = FailureSeverity.INFO
    phase: Optional[str] = None
    message: Optional[str] = None
    component: Optional[str] = None
    values: Dict[str, Any] = Field(default_factory=dict)
    #: True when `event_type` is not one the engine documents. Recorded rather
    #: than dropped: an unrecognised event may be the important one.
    is_recognised: bool = True

    @property
    def is_failure(self) -> bool:
        return self.severity in (
            FailureSeverity.CRITICAL, FailureSeverity.FATAL
        ) or self.event_type.startswith("failure")

    @property
    def rule_key(self) -> Optional[str]:
        """The documented failure rule this event corresponds to, if any."""
        normalized = self.event_type.lower().replace("failure_", "").replace(
            "-", "_"
        )
        if normalized in FAILURE_RULES:
            return normalized
        for key in FAILURE_RULES:
            if key in normalized or normalized in key:
                return key
        return None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "SimulationEventView":
        if not isinstance(payload, dict):
            return cls(event_type="unknown", message=str(payload))

        raw_type = _first(payload, _TYPE_KEYS) or "unknown"
        event_type = str(raw_type).strip().lower().replace(" ", "_")

        raw_severity = _first(payload, _SEVERITY_KEYS)
        severity = FailureSeverity.INFO
        if raw_severity is not None:
            try:
                severity = FailureSeverity(str(raw_severity).strip().lower())
            except ValueError:
                #: Unknown severity is treated as a warning rather than as
                #: info: an unparseable severity is more likely to be a
                #: problem than routine.
                severity = FailureSeverity.WARNING

        known = event_type in DOCUMENTED_EVENT_TYPES or event_type.startswith(
            "failure"
        )
        values = {
            key: value for key, value in payload.items()
            if isinstance(value, (int, float)) and key not in _TIME_KEYS
        }

        return cls(
            event_type=event_type,
            time_s=_coerce_float(_first(payload, _TIME_KEYS)),
            severity=severity,
            phase=_first(payload, _PHASE_KEYS),
            message=_first(payload, _MESSAGE_KEYS),
            component=_first(payload, ("component", "subsystem", "part")),
            values=values,
            is_recognised=known,
        )


class SimulationResultView(BaseModel):
    """A whole run, as P4 reads it."""

    model_config = ConfigDict(extra="allow")

    simulation_id: Optional[str] = None
    succeeded: Optional[bool] = None
    outcome: Optional[str] = None
    termination_reason: Optional[str] = None
    events: List[SimulationEventView] = Field(default_factory=list)
    telemetry: List[TelemetrySample] = Field(default_factory=list)
    engine_version: Optional[str] = None
    #: Fields present in the payload that this view did not understand.
    unparsed_keys: List[str] = Field(default_factory=list)

    @property
    def failed(self) -> bool:
        if self.succeeded is not None:
            return not self.succeeded
        return any(event.is_failure for event in self.events)

    def failure_events(self) -> List[SimulationEventView]:
        return [event for event in self.events if event.is_failure]

    def first_failure(self) -> Optional[SimulationEventView]:
        """The earliest failure. Usually the cause; the rest are consequences.

        Ordering by time matters: a structural overload at t+62 followed by an
        impact at t+95 is one failure with an aftermath, not two failures, and
        analysing the impact would explain the wrong thing.
        """
        failures = sorted(
            self.failure_events(),
            key=lambda event: (event.time_s is None, event.time_s or 0.0),
        )
        return failures[0] if failures else None

    def peak(self, field: str) -> Optional[float]:
        """Maximum recorded value of a telemetry channel."""
        values = [
            getattr(sample, field, None) for sample in self.telemetry
        ]
        present = [value for value in values if isinstance(value, (int, float))]
        return max(present) if present else None

    def sample_at(self, time_s: Optional[float]) -> Optional[TelemetrySample]:
        """The telemetry sample nearest a given time."""
        if time_s is None or not self.telemetry:
            return None
        timed = [s for s in self.telemetry if s.time_s is not None]
        if not timed:
            return None
        return min(timed, key=lambda sample: abs(sample.time_s - time_s))


def _coerce_float(value) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def parse_simulation_result(payload: Dict[str, Any]) -> SimulationResultView:
    """Build a view from whatever P3's API returned.

    Tolerant by design. A payload shape this does not recognise yields a view
    with `unparsed_keys` populated, not an exception — the analysis degrades
    to what it could read, and says so.
    """
    if not isinstance(payload, dict):
        raise ValueError("a simulation result must be a mapping")

    known_keys = {
        "id", "simulation_id", "succeeded", "success", "status", "outcome",
        "termination_reason", "termination", "events", "failures", "telemetry",
        "samples", "engine_version", "version", "summary",
    }

    events_raw = list(payload.get("events") or [])
    events_raw.extend(payload.get("failures") or [])
    telemetry_raw = payload.get("telemetry") or payload.get("samples") or []

    succeeded = payload.get("succeeded")
    if succeeded is None:
        succeeded = payload.get("success")
    if succeeded is None and payload.get("status"):
        status = str(payload["status"]).lower()
        if status in ("success", "succeeded", "completed_success"):
            succeeded = True
        elif status in ("failed", "failure", "aborted"):
            succeeded = False

    return SimulationResultView(
        simulation_id=payload.get("simulation_id") or payload.get("id"),
        succeeded=succeeded,
        outcome=payload.get("outcome") or (payload.get("summary") or {}).get(
            "outcome"
        ) if isinstance(payload.get("summary"), dict) else payload.get("outcome"),
        termination_reason=payload.get("termination_reason")
        or payload.get("termination"),
        events=[SimulationEventView.from_payload(item) for item in events_raw],
        telemetry=[TelemetrySample.from_payload(item) for item in telemetry_raw],
        engine_version=payload.get("engine_version") or payload.get("version"),
        unparsed_keys=sorted(set(payload) - known_keys),
    )
