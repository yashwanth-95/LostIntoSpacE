from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simulation.contracts import (
    FailureDetail,
    MissionState,
    SimConfig,
    SimEvent,
    SimResult,
    SimSummary,
    StageStatus,
    TelemetryPoint,
)


@dataclass
class EngineState:
    time_s: float = 0.0
    altitude_m: float = 0.0
    velocity_ms: float = 0.0
    acceleration_ms2: float = 0.0
    mass_kg: float = 0.0
    thrust_N: float = 0.0
    drag_N: float = 0.0
    mission_state: MissionState = MissionState.PREPARATION
    stage: int = 0
    stage_status: StageStatus = StageStatus.STOWED
    engine_on: bool = False


def _initial_engine_state(config: SimConfig) -> EngineState:
    launch_mass = config.vehicle.launch_mass_kg
    return EngineState(
        mass_kg=launch_mass,
        thrust_N=config.vehicle.stages[0].thrust_sea_level_N,
        stage=0,
        stage_status=StageStatus.IGNITING,
        engine_on=True,
    )


def _build_telemetry(config: SimConfig, state: EngineState) -> TelemetryPoint:
    return TelemetryPoint(
        t=state.time_s,
        altitude_m=state.altitude_m,
        downrange_m=0.0,
        position_x_m=0.0,
        position_y_m=0.0,
        position_z_m=state.altitude_m,
        speed_ms=state.velocity_ms,
        vertical_speed_ms=state.velocity_ms,
        horizontal_speed_ms=0.0,
        acceleration_ms2=state.acceleration_ms2,
        g_load_g=state.acceleration_ms2 / 9.80665,
        mass_kg=state.mass_kg,
        fuel_remaining_kg=max(0.0, config.vehicle.stages[0].propellant_mass_kg),
        fuel_fraction=1.0,
        thrust_N=state.thrust_N,
        mass_flow_kgs=0.0,
        twr=state.thrust_N / (state.mass_kg * 9.80665),
        drag_N=state.drag_N,
        dynamic_pressure_Pa=0.0,
        mach=0.0,
        air_density_kgm3=0.0,
        ambient_pressure_Pa=101_325.0,
        pitch_rad=0.0,
        yaw_rad=0.0,
        angle_of_attack_rad=0.0,
        semi_major_axis_m=0.0,
        eccentricity=0.0,
        periapsis_altitude_m=0.0,
        apoapsis_altitude_m=0.0,
        inclination_rad=0.0,
        in_orbit=False,
        stage=state.stage,
        stage_status=state.stage_status,
        engine_on=state.engine_on,
        mission_state=state.mission_state,
        phase="powered",
    )


def _build_event(t: float, event_type: str, description: str, *, severity: str = "info") -> SimEvent:
    return SimEvent(
        t=t,
        type=event_type,
        severity=severity,
        description=description,
        data={"event": event_type},
        failure=None,
    )


def run_simulation(config: SimConfig) -> SimResult:
    """Run a minimal but deterministic educational simulation.

    This implementation intentionally prioritizes correctness of the integration boundary,
    not full aerospace fidelity. It is designed to be extended incrementally while keeping
    the TypeScript renderer and frontend untouched.
    """
    state = _initial_engine_state(config)
    telemetry: list[TelemetryPoint] = []
    events: list[SimEvent] = []
    failures: list[FailureDetail] = []
    max_altitude_m = 0.0

    for step in range(int(config.settings.max_time_s / max(config.settings.dt_powered_s, 1e-3)) + 1):
        state.time_s = step * config.settings.dt_powered_s
        state.acceleration_ms2 = max(0.0, state.thrust_N / max(state.mass_kg, 1.0)) / max(state.mass_kg, 1.0)
        state.velocity_ms += state.acceleration_ms2 * config.settings.dt_powered_s
        state.altitude_m += state.velocity_ms * config.settings.dt_powered_s
        state.mass_kg = max(0.0, state.mass_kg - (state.thrust_N / (280.0 * 9.80665)) * config.settings.dt_powered_s)

        if state.altitude_m > max_altitude_m:
            max_altitude_m = state.altitude_m

        if step == 0:
            events.append(_build_event(0.0, "IGNITION", "Engine ignition started"))
            state.mission_state = MissionState.IGNITION
        elif step >= 1 and state.altitude_m > 0.0:
            state.mission_state = MissionState.ASCENT
            if not events or events[-1].type != "LIFTOFF":
                events.append(_build_event(state.time_s, "LIFTOFF", "Vehicle lifted off"))

        if state.altitude_m >= config.mission.target.target_altitude_km * 1000.0:
            state.mission_state = MissionState.ORBIT_INSERTION
            events.append(_build_event(state.time_s, "ORBIT_INSERTION", "Target altitude reached"))
            break

        if state.velocity_ms <= 0.0 and state.altitude_m <= 0.0:
            state.mission_state = MissionState.FAILURE
            break

        telemetry.append(_build_telemetry(config, state))

    summary = SimSummary(
        max_altitude_m=max_altitude_m,
        max_speed_ms=max(state.velocity_ms, 0.0),
        max_acceleration_g=max(state.acceleration_ms2 / 9.80665, 0.0),
        max_dynamic_pressure_Pa=0.0,
        max_q_altitude_m=0.0,
        max_mach=0.0,
        flight_time_s=state.time_s,
        apogee_time_s=state.time_s,
        max_downrange_m=0.0,
        impact_speed_ms=None,
        stages_separated=0,
        propellant_used_kg=max(0.0, config.vehicle.launch_mass_kg - state.mass_kg),
        delta_v_achieved_ms=state.velocity_ms,
        delta_v_ideal_ms=state.velocity_ms,
        gravity_loss_ms=0.0,
        drag_loss_ms=0.0,
    )

    return SimResult(
        success=state.altitude_m >= config.mission.target.target_altitude_km * 1000.0,
        outcome="success" if state.altitude_m >= config.mission.target.target_altitude_km * 1000.0 else "partial",
        final_state=state.mission_state,
        termination_reason="target altitude reached" if state.altitude_m >= config.mission.target.target_altitude_km * 1000.0 else "max time reached",
        telemetry=telemetry,
        events=events,
        failures=failures,
        summary=summary,
        total_steps=step + 1,
        flight_time_s=state.time_s,
    )
