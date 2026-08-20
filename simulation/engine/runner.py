"""
Simulation runner — the flight loop.

This is the canonical LostIntoSpacE flight simulation. It replaces the
placeholder that shipped with the first prototype scaffolding, which integrated
a quantity that was not an acceleration and modelled neither gravity nor drag
nor staging. See docs/simulation/ARCHITECTURE.md for the migration record.

The loop, in order
------------------
1. **Sequencing** — ignite, cut off, and separate stages whose time has come.
2. **Guidance** — compute the commanded attitude.
3. **Forces** — evaluate thrust, drag, and gravity.
4. **Integrate** — advance position and velocity with the configured integrator.
5. **Mass** — deplete propellant analytically (see :mod:`simulation.models.integrator`).
6. **Failures** — run detection rules and scripted injections.
7. **Mission state** — advance the state machine and emit its events.
8. **Telemetry** — sample if the interval elapsed or an event fired.
9. **Termination** — check the stop conditions.

Frame
-----
Integration happens in the launch-centred ENU frame (see
:mod:`simulation.models.frames`). Orbital elements are computed in ECI-aligned
axes, because inclination measured against the launch site's horizon would be
meaningless.

Determinism
-----------
No wall-clock reads, no :mod:`random`. A run is a pure function of its config,
and ``simulation/tests/test_engine.py`` asserts that.

Fidelity
--------
This is a transparent educational simulation, not flight-certified engineering
software. Every approximation is listed in docs/simulation/ASSUMPTIONS.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from simulation.contracts import (
    EventSeverity,
    FailureDetail,
    FlightPhase,
    MissionState,
    SimConfig,
    SimEvent,
    SimOutcome,
    SimResult,
    SimSummary,
    StageStatus,
    TelemetryPoint,
)
from simulation.engine.failures import (
    DetectionInputs,
    FailureEffects,
    check_injections,
    combined_effects,
    detect_failures,
    failure_event_type,
)
from simulation.engine.forces import compute_forces, ground_constrained_acceleration
from simulation.engine.guidance import (
    GuidanceCommand,
    angle_of_attack,
    compute_guidance,
    initial_command,
    local_up_vector,
)
from simulation.engine.mission_state import (
    STATE_DESCRIPTIONS,
    TransitionContext,
    advance_mission_state,
    is_terminal_state,
)
from simulation.models.atmosphere import atmosphere
from simulation.models.constants import G0, R_EARTH
from simulation.models.frames import (
    altitude_from_enu,
    downrange_from_enu,
    enu_basis,
    enu_position_to_eci,
    enu_vector_to_eci,
    SiteLocation,
)
from simulation.models.gravity import Vec3, dot, magnitude, scale, vec3
from simulation.models.integrator import KinematicState, get_integrator
from simulation.models.orbital import orbital_elements
from simulation.models.thrust import (
    mass_flow_rate,
    specific_impulse_at_pressure,
    thrust_at_pressure,
)

#: Altitude above which orbital elements start being reported. Below this the
#: two-body solution describes a trajectory that intersects the ground and drag
#: dominates anyway, so the numbers would be noise. The Karman line is a
#: conventional and defensible place to draw it. Unit: m.
ORBIT_REPORTING_ALTITUDE_M = 100_000.0

#: Altitude below which a descending vehicle counts as having reached the
#: surface. Not exactly zero: the integrator lands between steps, so a small
#: band avoids a vehicle skipping from +3 m to -40 m without ever registering.
SURFACE_BAND_M = 0.5


@dataclass
class _StageRuntime:
    """Mutable per-stage state during a run."""

    index: int
    status: StageStatus = StageStatus.STOWED
    propellant_remaining_kg: float = 0.0
    ignition_time_s: Optional[float] = None
    cutoff_time_s: Optional[float] = None
    separation_time_s: Optional[float] = None


@dataclass
class _FlightState:
    """Everything that changes during a run."""

    t: float = 0.0
    position: Vec3 = field(default_factory=lambda: vec3(0.0, 0.0, 0.0))
    velocity: Vec3 = field(default_factory=lambda: vec3(0.0, 0.0, 0.0))
    mission_state: MissionState = MissionState.PREPARATION
    active_stage: int = 0
    stages: List[_StageRuntime] = field(default_factory=list)
    command: Optional[GuidanceCommand] = None
    has_lifted_off: bool = False
    payload_deployed: bool = False
    peak_q_Pa: float = 0.0
    stage_just_separated: bool = False
    burn_time_on_pad_s: float = 0.0
    #: Set once the osculating orbit clears the mission's target altitude, so
    #: guidance can command cutoff on the next step.
    target_orbit_reached: bool = False


def _wet_mass_above(config: SimConfig, stage_index: int) -> float:
    """Total wet mass of every stage above the given one.

    Payload is deliberately NOT added: ``payload_mass_kg`` is reported for
    information, but the payload's mass is already inside the dry mass of the
    stage that carries it. This matches `core/vehicle.ts::currentMass` in the
    TypeScript engine — adding it again inflates launch mass and can push a
    healthy vehicle's liftoff TWR below 1.
    """
    return sum(
        s.dry_mass_kg + s.propellant_mass_kg
        for s in config.vehicle.stages
        if s.stage_number > stage_index
    )


def _current_mass(config: SimConfig, state: _FlightState) -> float:
    """
    Total vehicle mass right now.

    Separated stages contribute nothing; the active stage contributes its dry
    mass plus whatever propellant it has left; stages above contribute their
    full wet mass because they have not fired yet.
    """
    total = 0.0
    for stage_rt in state.stages:
        if stage_rt.status == StageStatus.SEPARATED:
            continue
        stage = config.vehicle.stages[stage_rt.index]
        total += stage.dry_mass_kg + max(0.0, stage_rt.propellant_remaining_kg)
    return total


def _initial_state(config: SimConfig) -> _FlightState:
    """Build the on-the-pad state."""
    stages = [
        _StageRuntime(
            index=i,
            status=StageStatus.STOWED,
            propellant_remaining_kg=stage.propellant_mass_kg,
        )
        for i, stage in enumerate(config.vehicle.stages)
    ]
    return _FlightState(
        t=-abs(config.settings.countdown_s),
        position=vec3(0.0, 0.0, 0.0),
        velocity=vec3(0.0, 0.0, 0.0),
        mission_state=MissionState.PREPARATION,
        stages=stages,
        command=initial_command(config.guidance),
    )


def _make_event(
    t: float,
    event_type: str,
    description: str,
    *,
    severity: EventSeverity = EventSeverity.INFO,
    data: Optional[dict] = None,
    failure: Optional[FailureDetail] = None,
) -> SimEvent:
    return SimEvent(
        t=t,
        type=event_type,
        severity=severity,
        description=description,
        data=data or {},
        failure=failure,
    )


def run_simulation(config: SimConfig) -> SimResult:
    """
    Run a complete flight and return its telemetry, events, and summary.

    Args:
        config: The immutable simulation configuration.

    Returns:
        The finished :class:`~simulation.contracts.SimResult`.
    """
    site = SiteLocation(
        latitude_deg=config.mission.launch_site.latitude_deg,
        longitude_deg=config.mission.launch_site.longitude_deg,
        altitude_m=config.mission.launch_site.altitude_m,
    )
    basis = enu_basis(site)
    integrate = get_integrator(config.settings.integrator.value)

    state = _initial_state(config)
    telemetry: List[TelemetryPoint] = []
    events: List[SimEvent] = []
    failures: List[FailureDetail] = []
    fired_modes: set = set()

    target_altitude_m = config.mission.target.target_altitude_km * 1000.0

    # Running maxima for the summary.
    max_altitude_m = 0.0
    max_speed_ms = 0.0
    max_accel_g = 0.0
    max_q_Pa = 0.0
    max_q_altitude_m = 0.0
    max_mach = 0.0
    max_downrange_m = 0.0
    apogee_time_s = 0.0
    gravity_loss_ms = 0.0
    drag_loss_ms = 0.0
    propellant_used_kg = 0.0

    launch_mass_kg = _current_mass(config, state)
    next_sample_t = 0.0
    termination_reason = "maximum simulation time reached"
    steps = 0
    last_telemetry: Optional[TelemetryPoint] = None

    while steps < config.settings.max_steps and state.t < config.settings.max_time_s:
        steps += 1
        state.stage_just_separated = False

        effects = combined_effects(failures)
        engine_on = False
        dt = config.settings.dt_powered_s

        # --- 1. Sequencing ---------------------------------------------------
        stage_rt = state.stages[state.active_stage] if state.active_stage < len(state.stages) else None
        stage = (
            config.vehicle.stages[state.active_stage]
            if state.active_stage < len(config.vehicle.stages)
            else None
        )

        if stage_rt is not None and stage is not None:
            if stage_rt.status == StageStatus.STOWED and state.t >= stage.ignition_delay_s:
                if stage.can_fire:
                    stage_rt.status = StageStatus.BURNING
                    stage_rt.ignition_time_s = state.t
                    events.append(
                        _make_event(
                            state.t,
                            "STAGE_IGNITION",
                            f"Stage {state.active_stage + 1} ignition",
                            data={"stage": float(state.active_stage)},
                        )
                    )
                else:
                    stage_rt.status = StageStatus.FAILED

            if stage_rt.status == StageStatus.BURNING:
                # Guidance cutoff on reaching the target orbit. Real vehicles
                # do exactly this: upper-stage cutoff is commanded when the
                # guidance computer sees the target orbit achieved, not when
                # the tanks run dry. Without it an over-performing vehicle
                # burns its whole load into a wildly elliptical orbit instead
                # of the circular one the mission asked for.
                if (
                    config.guidance.cutoff_on_target_orbit
                    and state.target_orbit_reached
                    and stage_rt.propellant_remaining_kg > 0.0
                ):
                    stage_rt.status = StageStatus.SHUTDOWN
                    stage_rt.cutoff_time_s = state.t
                    events.append(
                        _make_event(
                            state.t,
                            "GUIDANCE_CUTOFF",
                            f"Stage {state.active_stage + 1} cutoff on target orbit",
                            data={"stage": float(state.active_stage)},
                        )
                    )
                elif stage_rt.propellant_remaining_kg <= 0.0:
                    stage_rt.status = StageStatus.SHUTDOWN
                    stage_rt.cutoff_time_s = state.t
                    events.append(
                        _make_event(
                            state.t,
                            "STAGE_CUTOFF",
                            f"Stage {state.active_stage + 1} propellant depleted",
                            data={"stage": float(state.active_stage)},
                        )
                    )
                else:
                    engine_on = True

            # Separate a spent stage and move to the next one.
            if (
                stage_rt.status == StageStatus.SHUTDOWN
                and not effects.staging_failed
                and state.active_stage + 1 < len(state.stages)
                and stage_rt.cutoff_time_s is not None
                and state.t >= stage_rt.cutoff_time_s + stage.separation_delay_s
            ):
                stage_rt.status = StageStatus.SEPARATED
                stage_rt.separation_time_s = state.t
                state.active_stage += 1
                state.stage_just_separated = True
                events.append(
                    _make_event(
                        state.t,
                        "STAGE_SEPARATED",
                        f"Stage {stage_rt.index + 1} separated",
                        data={"stage": float(stage_rt.index)},
                    )
                )

        if not engine_on:
            # Coast steps are coarse, but only outside the atmosphere. Inside
            # it, drag and dynamic pressure change fast, and a 0.5 s step lets
            # a descending vehicle jump tens of metres past the ground before
            # impact is noticed. Unpowered atmospheric flight keeps the fine
            # step; a vacuum coast does not need it.
            in_atmosphere = altitude_from_enu(state.position, site.altitude_m) < 100_000.0
            dt = (
                config.settings.dt_powered_s
                if in_atmosphere and state.has_lifted_off
                else config.settings.dt_coast_s
            )

        # --- 2. Guidance -----------------------------------------------------
        altitude_m = altitude_from_enu(state.position, site.altitude_m)
        up = local_up_vector(state.position, site.altitude_m)
        command = compute_guidance(
            altitude_m=altitude_m,
            velocity=state.velocity,
            local_up=up,
            guidance_failed=effects.guidance_failed,
            last_command=state.command,
            config=config.guidance,
        )
        state.command = command

        # --- 3. Thrust magnitude at this altitude ----------------------------
        atm_here = atmosphere(altitude_m)
        thrust_N = 0.0
        mdot_kgs = 0.0
        if engine_on and stage is not None:
            if config.settings.use_altitude_compensation:
                thrust_N = thrust_at_pressure(
                    stage.thrust_vacuum_N,
                    stage.thrust_sea_level_N,
                    atm_here.pressure_Pa,
                )
                isp_s = specific_impulse_at_pressure(
                    stage.isp_vacuum_s, stage.isp_sea_level_s, atm_here.pressure_Pa
                )
            else:
                thrust_N = stage.thrust_sea_level_N
                isp_s = stage.isp_sea_level_s

            thrust_N *= effects.thrust_multiplier
            mdot_kgs = mass_flow_rate(thrust_N, isp_s) * effects.mass_flow_multiplier

        mass_kg = _current_mass(config, state)

        # --- 4. Forces and integration ---------------------------------------
        # Mass is evaluated analytically inside the closure rather than being
        # carried in the integrator state: propellant flow is constant across a
        # step, so m(t) is exactly linear and folding it in would add error.
        def acceleration(tau: float, p: Vec3, v: Vec3) -> Vec3:
            elapsed = max(0.0, tau - state.t)
            m = max(mass_kg - mdot_kgs * elapsed, 1e-3)
            f = compute_forces(
                position=p,
                velocity=v,
                mass_kg=m,
                thrust_N=thrust_N,
                thrust_direction=command.thrust_direction,
                drag_coefficient=config.vehicle.drag_coefficient,
                reference_area_m2=config.vehicle.reference_area_m2,
                site_altitude_m=site.altitude_m,
                use_mach_drag_rise=config.settings.use_mach_drag_rise,
            )
            return ground_constrained_acceleration(
                f.acceleration, p, v, site.altitude_m
            )

        forces = compute_forces(
            position=state.position,
            velocity=state.velocity,
            mass_kg=mass_kg,
            thrust_N=thrust_N,
            thrust_direction=command.thrust_direction,
            drag_coefficient=config.vehicle.drag_coefficient,
            reference_area_m2=config.vehicle.reference_area_m2,
            site_altitude_m=site.altitude_m,
            use_mach_drag_rise=config.settings.use_mach_drag_rise,
        )

        # Velocity-loss accounting. Both terms integrate the component of the
        # relevant acceleration acting *against* the direction of travel, which
        # is what makes them comparable with the ideal delta-v.
        #
        # `forces.gravity` is already an acceleration here (unlike the
        # TypeScript engine, where it is a force), so there is no division by
        # mass in the gravity term.
        speed_now = magnitude(state.velocity)
        if speed_now > 1.0:
            heading = scale(state.velocity, 1.0 / speed_now)
            gravity_loss_ms += -dot(forces.gravity, heading) * dt
            drag_loss_ms += (forces.drag_N / max(mass_kg, 1e-6)) * dt

        if state.t >= 0.0:
            advanced = integrate(
                KinematicState(state.position, state.velocity), state.t, dt, acceleration
            )
            state.position = advanced.position
            state.velocity = advanced.velocity

            # --- 5. Mass depletion -------------------------------------------
            if engine_on and stage_rt is not None and mdot_kgs > 0:
                burned = min(mdot_kgs * dt, stage_rt.propellant_remaining_kg)
                stage_rt.propellant_remaining_kg -= burned
                # Accumulated per step, not derived from the mass difference:
                # subtracting final from launch mass would count every
                # jettisoned stage's dry mass as propellant.
                propellant_used_kg += burned

        state.t += dt

        altitude_m = altitude_from_enu(state.position, site.altitude_m)
        speed_ms = magnitude(state.velocity)
        if altitude_m > SURFACE_BAND_M:
            state.has_lifted_off = True

        # --- 6. Failures ------------------------------------------------------
        accel_mag = magnitude(forces.acceleration)
        # Load factor is what an accelerometer reads: non-gravitational forces
        # only. A vehicle in free fall reads zero g, however fast it is
        # accelerating toward the ground.
        g_load = (forces.thrust_N + forces.drag_N) / max(mass_kg, 1e-9) / G0
        twr = forces.thrust_N / max(mass_kg * G0, 1e-9)

        if engine_on and not state.has_lifted_off:
            state.burn_time_on_pad_s += dt

        new_failures = detect_failures(
            DetectionInputs(
                t=state.t,
                stage_index=state.active_stage,
                altitude_m=altitude_m,
                speed_ms=speed_ms,
                g_load_g=g_load,
                dynamic_pressure_Pa=forces.dynamic_pressure_Pa,
                twr=twr,
                mass_kg=mass_kg,
                thrust_N=forces.thrust_N,
                engine_on=engine_on,
                has_lifted_off=state.has_lifted_off,
                burn_time_on_pad_s=state.burn_time_on_pad_s,
                max_dynamic_pressure_Pa=config.vehicle.max_dynamic_pressure_Pa,
            ),
            config.failures,
            fired_modes,
        )
        new_failures.extend(check_injections(state.t - dt, dt, config.failures, fired_modes))

        for failure in new_failures:
            fired_modes.add(failure.mode_id)
            failures.append(failure)
            events.append(
                _make_event(
                    failure.t,
                    failure_event_type(failure),
                    failure.failure_mode,
                    severity=failure.severity,
                    data={"stage": float(failure.stage_index or 0)},
                    failure=failure,
                )
            )

        effects = combined_effects(failures)

        # --- 7. Orbital state and mission state ------------------------------
        elements = None
        in_orbit = False
        if altitude_m > ORBIT_REPORTING_ALTITUDE_M:
            eci_position = enu_position_to_eci(state.position, basis)
            eci_velocity = enu_vector_to_eci(state.velocity, basis)
            try:
                elements = orbital_elements(eci_position, eci_velocity)
                in_orbit = elements.is_stable_orbit
                # "Target orbit" means the periapsis has been raised clear of
                # the atmosphere AND the apoapsis is at least the requested
                # altitude — an apoapsis alone is just a ballistic arc.
                if (
                    in_orbit
                    and elements.periapsis_altitude_m >= ORBIT_REPORTING_ALTITUDE_M
                    and elements.apoapsis_altitude_m >= target_altitude_m
                ):
                    state.target_orbit_reached = True
            except ValueError:
                elements = None

        state.peak_q_Pa = max(state.peak_q_Pa, forces.dynamic_pressure_Pa)

        any_propellant = any(
            s.propellant_remaining_kg > 0
            for s in state.stages
            if s.status != StageStatus.SEPARATED
        )

        next_state = advance_mission_state(
            state.mission_state,
            TransitionContext(
                t=state.t,
                altitude_m=altitude_m,
                vertical_speed_ms=state.velocity.z,
                speed_ms=speed_ms,
                dynamic_pressure_Pa=forces.dynamic_pressure_Pa,
                peak_dynamic_pressure_Pa=state.peak_q_Pa,
                engine_on=engine_on,
                any_propellant_remaining=any_propellant,
                stage_index=state.active_stage,
                stage_just_separated=state.stage_just_separated,
                in_stable_orbit=in_orbit,
                target_altitude_m=target_altitude_m,
                fatal_failure=effects.terminal,
                countdown_complete=state.t >= 0.0,
                payload_deployed=state.payload_deployed,
            ),
        )
        if next_state is not None and next_state != state.mission_state:
            state.mission_state = next_state
            # Prefixed so a mission-state change can never be confused with a
            # hardware event: STATE_IGNITION (the mission entered the ignition
            # phase) is a different fact from STAGE_IGNITION (an engine lit).
            events.append(
                _make_event(
                    state.t,
                    f"STATE_{next_state.value}",
                    STATE_DESCRIPTIONS.get(next_state, next_state.value),
                    severity=(
                        EventSeverity.FATAL
                        if next_state == MissionState.FAILURE
                        else EventSeverity.INFO
                    ),
                )
            )
            if next_state == MissionState.ORBIT:
                state.payload_deployed = True

        # --- 8. Telemetry -----------------------------------------------------
        if altitude_m > max_altitude_m:
            max_altitude_m = altitude_m
            apogee_time_s = state.t
        max_speed_ms = max(max_speed_ms, speed_ms)
        max_accel_g = max(max_accel_g, g_load)
        if forces.dynamic_pressure_Pa > max_q_Pa:
            max_q_Pa = forces.dynamic_pressure_Pa
            max_q_altitude_m = altitude_m
        max_mach = max(max_mach, forces.mach)
        downrange_m = downrange_from_enu(state.position, site.altitude_m)
        max_downrange_m = max(max_downrange_m, downrange_m)

        if state.t >= next_sample_t or new_failures or (next_state is not None):
            point = _build_telemetry(
                config=config,
                state=state,
                stage_rt=stage_rt,
                altitude_m=altitude_m,
                downrange_m=downrange_m,
                speed_ms=speed_ms,
                accel_mag=accel_mag,
                g_load=g_load,
                mass_kg=mass_kg,
                thrust_N=forces.thrust_N,
                mdot_kgs=mdot_kgs,
                twr=twr,
                forces=forces,
                command=command,
                elements=elements,
                in_orbit=in_orbit,
                engine_on=engine_on,
            )
            telemetry.append(point)
            last_telemetry = point
            if state.t >= next_sample_t:
                next_sample_t += config.settings.telemetry_sample_interval_s

        # --- 9. Termination ---------------------------------------------------
        if effects.terminal and config.termination.on_fatal_failure:
            termination_reason = "fatal failure"
            state.mission_state = MissionState.FAILURE
            break

        if (
            config.termination.on_impact
            and state.has_lifted_off
            and altitude_m <= SURFACE_BAND_M
        ):
            termination_reason = "vehicle returned to the surface"
            state.mission_state = MissionState.SURFACE
            break

        if config.termination.on_stable_orbit and in_orbit and not engine_on:
            termination_reason = "stable orbit achieved"
            break

        if config.termination.on_target_altitude and altitude_m >= target_altitude_m:
            termination_reason = "target altitude reached"
            break

        if config.termination.on_mission_complete and is_terminal_state(state.mission_state):
            termination_reason = f"mission reached terminal state {state.mission_state.value}"
            break

    # --- Outcome -------------------------------------------------------------
    reached_target = max_altitude_m >= target_altitude_m
    had_fatal = any(f.is_terminal for f in failures)

    if had_fatal:
        outcome = SimOutcome.FAILURE
        success = False
    elif reached_target:
        outcome = SimOutcome.SUCCESS
        success = True
    elif max_altitude_m > target_altitude_m * 0.5:
        outcome = SimOutcome.PARTIAL
        success = False
    else:
        outcome = SimOutcome.FAILURE
        success = False

    final_mass = _current_mass(config, state)
    ideal_dv = 0.0
    for i, stage in enumerate(config.vehicle.stages):
        wet = stage.dry_mass_kg + stage.propellant_mass_kg + _wet_mass_above(config, i)
        dry = stage.dry_mass_kg + _wet_mass_above(config, i)
        if dry > 0 and wet > dry:
            ideal_dv += stage.isp_vacuum_s * G0 * math.log(wet / dry)

    summary = SimSummary(
        max_altitude_m=max_altitude_m,
        max_speed_ms=max_speed_ms,
        max_acceleration_g=max_accel_g,
        max_dynamic_pressure_Pa=max_q_Pa,
        max_q_altitude_m=max_q_altitude_m,
        max_mach=max_mach,
        flight_time_s=max(0.0, state.t),
        apogee_time_s=apogee_time_s,
        max_downrange_m=max_downrange_m,
        impact_speed_ms=(
            magnitude(state.velocity)
            if state.mission_state == MissionState.SURFACE
            else None
        ),
        stages_separated=sum(
            1 for s in state.stages if s.status == StageStatus.SEPARATED
        ),
        propellant_used_kg=propellant_used_kg,
        delta_v_achieved_ms=max_speed_ms,
        delta_v_ideal_ms=ideal_dv,
        gravity_loss_ms=gravity_loss_ms,
        drag_loss_ms=drag_loss_ms,
    )

    return SimResult(
        success=success,
        outcome=outcome,
        final_state=state.mission_state,
        termination_reason=termination_reason,
        telemetry=telemetry,
        events=events,
        failures=failures,
        summary=summary,
        total_steps=steps,
        flight_time_s=max(0.0, state.t),
    )


def _build_telemetry(
    *,
    config: SimConfig,
    state: _FlightState,
    stage_rt: Optional[_StageRuntime],
    altitude_m: float,
    downrange_m: float,
    speed_ms: float,
    accel_mag: float,
    g_load: float,
    mass_kg: float,
    thrust_N: float,
    mdot_kgs: float,
    twr: float,
    forces,
    command: GuidanceCommand,
    elements,
    in_orbit: bool,
    engine_on: bool,
) -> TelemetryPoint:
    """Assemble one telemetry sample from the current flight state."""
    horizontal = math.sqrt(
        state.velocity.x * state.velocity.x + state.velocity.y * state.velocity.y
    )
    stage_propellant = stage_rt.propellant_remaining_kg if stage_rt else 0.0
    stage_capacity = (
        config.vehicle.stages[stage_rt.index].propellant_mass_kg if stage_rt else 0.0
    )

    return TelemetryPoint(
        t=state.t,
        altitude_m=altitude_m,
        downrange_m=downrange_m,
        position_x_m=state.position.x,
        position_y_m=state.position.y,
        position_z_m=state.position.z,
        speed_ms=speed_ms,
        vertical_speed_ms=state.velocity.z,
        horizontal_speed_ms=horizontal,
        acceleration_ms2=accel_mag,
        g_load_g=g_load,
        mass_kg=mass_kg,
        fuel_remaining_kg=stage_propellant,
        fuel_fraction=(stage_propellant / stage_capacity) if stage_capacity > 0 else 0.0,
        thrust_N=thrust_N,
        mass_flow_kgs=mdot_kgs,
        twr=twr,
        drag_N=forces.drag_N,
        dynamic_pressure_Pa=forces.dynamic_pressure_Pa,
        mach=forces.mach,
        air_density_kgm3=forces.atmosphere.density_kgm3,
        ambient_pressure_Pa=forces.atmosphere.pressure_Pa,
        pitch_rad=command.pitch_rad,
        yaw_rad=command.yaw_rad,
        angle_of_attack_rad=angle_of_attack(state.velocity, command.thrust_direction),
        semi_major_axis_m=elements.semi_major_axis_m if elements else 0.0,
        eccentricity=elements.eccentricity if elements else 0.0,
        periapsis_altitude_m=elements.periapsis_altitude_m if elements else 0.0,
        apoapsis_altitude_m=(
            elements.apoapsis_altitude_m
            if elements and math.isfinite(elements.apoapsis_altitude_m)
            else 0.0
        ),
        inclination_rad=elements.inclination_rad if elements else 0.0,
        in_orbit=in_orbit,
        stage=state.active_stage,
        stage_status=stage_rt.status if stage_rt else StageStatus.STOWED,
        engine_on=engine_on,
        mission_state=state.mission_state,
        phase=_phase_for(state.mission_state, engine_on),
    )


def _phase_for(mission_state: MissionState, engine_on: bool) -> FlightPhase:
    """Coarse flight phase, derived from the mission state."""
    if mission_state in (MissionState.PREPARATION, MissionState.COUNTDOWN):
        return FlightPhase.PRELAUNCH
    if mission_state in (MissionState.FAILURE, MissionState.SURFACE, MissionState.COMPLETE):
        return FlightPhase.TERMINATED
    if mission_state in (MissionState.ENTRY, MissionState.DESCENT, MissionState.LANDING):
        return FlightPhase.DESCENT
    return FlightPhase.POWERED if engine_on else FlightPhase.COAST
