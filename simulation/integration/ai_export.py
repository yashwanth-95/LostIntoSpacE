from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simulation.contracts import MissionState, SimConfig, SimEvent, SimResult


@dataclass(frozen=True)
class ReportedQuantity:
    key: str
    label: str
    value: float
    unit: str
    description: str


@dataclass(frozen=True)
class ReportedMoment:
    t_s: float
    type: str
    severity: str
    description: str
    altitude_m: float
    speed_ms: float


@dataclass(frozen=True)
class ModelLimitations:
    not_modelled: list[str] = field(default_factory=list)
    simplifications: list[str] = field(default_factory=list)
    caveat: str = "This is an educational simulation with simplified physics assumptions."


@dataclass(frozen=True)
class MissionReport:
    report_version: str = "1.0.0"
    mission: dict[str, Any] = field(default_factory=dict)
    vehicle: dict[str, Any] = field(default_factory=dict)
    outcome: dict[str, Any] = field(default_factory=dict)
    measurements: list[ReportedQuantity] = field(default_factory=list)
    delta_v_budget: dict[str, Any] = field(default_factory=dict)
    timeline: list[ReportedMoment] = field(default_factory=list)
    failures: list[Any] = field(default_factory=list)
    preflight_warnings: list[str] = field(default_factory=list)
    model_limitations: ModelLimitations = field(default_factory=ModelLimitations)


def quantity(key: str, label: str, value: float, unit: str, description: str) -> ReportedQuantity:
    return ReportedQuantity(
        key=key,
        label=label,
        value=value,
        unit=unit,
        description=description,
    )


def _default_model_limitations() -> ModelLimitations:
    return ModelLimitations(
        not_modelled=[
            "Earth rotation and local environment variation",
            "Complex thermal and structural dynamics",
            "Detailed aerodynamic lift and control loops",
        ],
        simplifications=[
            "Single-coefficient drag model",
            "Instantaneous stage assumptions",
            "Simplified guidance and no active control dynamics",
        ],
        caveat=(
            "This is an educational simulation. The models are simplified approximations "
            "chosen to teach real physics relationships and may not reflect a specific vehicle."
        ),
    )


def build_mission_report(result: SimResult, config: SimConfig) -> MissionReport:
    summary = result.summary
    timeline = [
        ReportedMoment(
            t_s=point.t,
            type=event.type,
            severity=event.severity.value,
            description=event.description,
            altitude_m=point.altitude_m,
            speed_ms=point.speed_ms,
        )
        for point, event in zip(result.telemetry[: min(len(result.telemetry), 10)], result.events[: min(len(result.events), 10)])
    ]

    if not timeline and result.events:
        timeline = [
            ReportedMoment(
                t_s=event.t,
                type=event.type,
                severity=event.severity.value,
                description=event.description,
                altitude_m=result.telemetry[-1].altitude_m if result.telemetry else 0.0,
                speed_ms=result.telemetry[-1].speed_ms if result.telemetry else 0.0,
            )
            for event in result.events[:10]
        ]

    measurements = [
        quantity("maxAltitude", "Maximum altitude", summary.max_altitude_m, "m", "Highest altitude reached."),
        quantity("apogeeTime", "Time of apogee", summary.apogee_time_s, "s", "When the vehicle stopped climbing."),
        quantity("maxSpeed", "Maximum speed", summary.max_speed_ms, "m/s", "Peak speed reached."),
        quantity("flightTime", "Flight time", summary.flight_time_s, "s", "Total simulated flight duration."),
    ]

    accounted = summary.delta_v_achieved_ms + summary.gravity_loss_ms + summary.drag_loss_ms
    unaccounted = summary.delta_v_ideal_ms - accounted

    return MissionReport(
        mission={
            "name": config.mission.name,
            "objective": config.mission.objective,
            "targetAltitude_km": config.mission.target.target_altitude_km,
            "missionType": config.mission.target.type.value,
            "launchSite": config.mission.launch_site.name,
            "guidanceMode": config.guidance.mode.value,
        },
        vehicle={
            "name": config.vehicle.name,
            "stageCount": len(config.vehicle.stages),
            "launchMass_kg": config.vehicle.launch_mass_kg,
            "payloadMass_kg": config.vehicle.payload_mass_kg,
            "idealDeltaV_ms": summary.delta_v_ideal_ms,
            "liftoffTWR": 0.0,
            "stabilityMargin_cal": config.vehicle.stability_margin_wet_cal,
        },
        outcome={
            "result": result.outcome.value,
            "succeeded": result.success,
            "finalMissionState": result.final_state.value,
            "terminationReason": result.termination_reason,
            "flightTime_s": result.flight_time_s,
        },
        measurements=measurements,
        delta_v_budget={
            "ideal_ms": summary.delta_v_ideal_ms,
            "achieved_ms": summary.delta_v_achieved_ms,
            "gravityLoss_ms": summary.gravity_loss_ms,
            "dragLoss_ms": summary.drag_loss_ms,
            "unaccounted_ms": unaccounted,
            "explanation": "Velocity budget across ideal, achieved, gravity, and drag losses.",
        },
        timeline=timeline,
        failures=[failure.model_dump(mode="json") for failure in result.failures],
        preflight_warnings=[],
        model_limitations=_default_model_limitations(),
    )
