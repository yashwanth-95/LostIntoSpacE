"""
Mission state machine.

Ported from packages/simulation-engine/src/sim/mission-state.ts.

The state machine is what turns a stream of numbers into a mission narrative.
It is deliberately separate from the physics: the flight loop integrates, then
hands the resulting state here and asks "what phase is this?". Nothing in this
module influences the trajectory.

Transitions are evaluated in priority order, and only one fires per step. A
terminal state (``COMPLETE``, ``FAILURE``, ``SURFACE``) never transitions out.
"""

from __future__ import annotations

from typing import NamedTuple, Optional

from simulation.contracts import MissionState

#: States from which no transition is possible.
TERMINAL_STATES = frozenset(
    {MissionState.COMPLETE, MissionState.FAILURE, MissionState.SURFACE}
)

#: Altitude band around max-Q within which the MAX_Q state is announced. Unit: Pa.
_MAX_Q_DECAY_FRACTION = 0.95


class TransitionContext(NamedTuple):
    """Everything the state machine is allowed to look at."""

    t: float
    altitude_m: float
    vertical_speed_ms: float
    speed_ms: float
    dynamic_pressure_Pa: float
    peak_dynamic_pressure_Pa: float
    engine_on: bool
    any_propellant_remaining: bool
    stage_index: int
    stage_just_separated: bool
    in_stable_orbit: bool
    target_altitude_m: float
    fatal_failure: bool
    countdown_complete: bool
    payload_deployed: bool


def is_terminal_state(state: MissionState) -> bool:
    """Whether a state can still transition."""
    return state in TERMINAL_STATES


def advance_mission_state(
    current: MissionState, ctx: TransitionContext
) -> Optional[MissionState]:
    """
    Decide the next mission state, or ``None`` to stay put.

    Args:
        current: The state the mission is in now.
        ctx: The flight state to evaluate against.

    Returns:
        The state to move to, or ``None`` if no transition fires.
    """
    if is_terminal_state(current):
        return None

    # A fatal failure pre-empts every other transition.
    if ctx.fatal_failure:
        return MissionState.FAILURE

    # Impact ends the mission from any airborne state.
    if ctx.altitude_m <= 0.5 and current not in (
        MissionState.PREPARATION,
        MissionState.COUNTDOWN,
        MissionState.IGNITION,
    ):
        return MissionState.SURFACE

    if current == MissionState.PREPARATION:
        return MissionState.COUNTDOWN

    if current == MissionState.COUNTDOWN:
        if ctx.countdown_complete:
            return MissionState.IGNITION
        return None

    if current == MissionState.IGNITION:
        # Liftoff is clearing the pad, not merely lighting the engine.
        if ctx.altitude_m > 0.5 and ctx.vertical_speed_ms > 0.1:
            return MissionState.LIFTOFF
        return None

    if current == MissionState.LIFTOFF:
        if ctx.altitude_m > 100.0:
            return MissionState.ASCENT
        return None

    if current == MissionState.ASCENT:
        # Max-Q is announced once dynamic pressure has clearly peaked and begun
        # to fall, which is the only way to know the peak has passed.
        if (
            ctx.peak_dynamic_pressure_Pa > 1000.0
            and ctx.dynamic_pressure_Pa < ctx.peak_dynamic_pressure_Pa * _MAX_Q_DECAY_FRACTION
        ):
            return MissionState.MAX_Q
        if ctx.stage_just_separated:
            return MissionState.STAGE_SEPARATION
        if not ctx.engine_on:
            return MissionState.ENGINE_CUTOFF
        return None

    if current == MissionState.MAX_Q:
        if ctx.stage_just_separated:
            return MissionState.STAGE_SEPARATION
        if not ctx.engine_on:
            return MissionState.ENGINE_CUTOFF
        return None

    if current == MissionState.ENGINE_CUTOFF:
        if ctx.stage_just_separated:
            return MissionState.STAGE_SEPARATION
        if ctx.in_stable_orbit:
            return MissionState.ORBIT_INSERTION
        if ctx.vertical_speed_ms < 0:
            return MissionState.DESCENT
        return None

    # Upper-stage flight re-enters ASCENT rather than a distinct SECOND_STAGE
    # state. The shared contract (and the TypeScript engine) defines 19 states
    # and SECOND_STAGE is not among them; the stage index in telemetry already
    # says which stage is flying, so adding a state would break the cross-engine
    # contract to express something already expressed. Recorded in
    # docs/simulation/ASSUMPTIONS.md.
    if current == MissionState.STAGE_SEPARATION:
        if ctx.engine_on:
            return MissionState.ASCENT
        if ctx.in_stable_orbit:
            return MissionState.ORBIT_INSERTION
        return None

    if current == MissionState.ORBIT_INSERTION:
        if ctx.in_stable_orbit and not ctx.engine_on:
            return MissionState.ORBIT
        return None

    if current == MissionState.ORBIT:
        if ctx.payload_deployed:
            return MissionState.PAYLOAD_DEPLOYMENT
        if not ctx.in_stable_orbit:
            return MissionState.DESCENT
        return None

    if current == MissionState.PAYLOAD_DEPLOYMENT:
        return MissionState.COMPLETE

    if current == MissionState.DESCENT:
        if ctx.altitude_m < 100_000.0 and ctx.speed_ms > 2000.0:
            return MissionState.ENTRY
        return None

    if current == MissionState.ENTRY:
        if ctx.altitude_m < 10_000.0:
            return MissionState.LANDING
        return None

    if current == MissionState.LANDING:
        if ctx.altitude_m <= 0.5:
            return MissionState.SURFACE
        return None

    return None


#: Human-readable descriptions emitted with each state-change event.
STATE_DESCRIPTIONS = {
    MissionState.PREPARATION: "Vehicle on the pad, systems nominal",
    MissionState.COUNTDOWN: "Terminal count under way",
    MissionState.IGNITION: "Engine ignition",
    MissionState.LIFTOFF: "Liftoff — vehicle has cleared the pad",
    MissionState.ASCENT: "Powered ascent",
    MissionState.MAX_Q: "Maximum dynamic pressure",
    MissionState.ENGINE_CUTOFF: "Engine cutoff",
    MissionState.STAGE_SEPARATION: "Stage separation",
    MissionState.ORBIT_INSERTION: "Orbital insertion",
    MissionState.ORBIT: "Stable orbit achieved",
    MissionState.MANEUVER: "Orbital manoeuvre",
    MissionState.PAYLOAD_DEPLOYMENT: "Payload deployed",
    MissionState.TRANSFER: "Transfer burn",
    MissionState.ENTRY: "Atmospheric entry",
    MissionState.DESCENT: "Descent",
    MissionState.LANDING: "Landing",
    MissionState.SURFACE: "Vehicle is down",
    MissionState.FAILURE: "Mission failure",
    MissionState.COMPLETE: "Mission complete",
}
