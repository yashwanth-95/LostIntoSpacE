"""
Failure system — detection rules and scripted injections.

Ported from packages/simulation-engine/src/sim/failures.ts.

Two ways a flight can go wrong:

- **Detection** — a rule notices the vehicle has exceeded a physical limit
  (structural load, g-load, insufficient thrust to leave the pad). These are
  consequences of the configuration the user chose, which is what makes them
  educational rather than arbitrary.
- **Injection** — the mission author scripts a failure at a given time, to
  demonstrate a specific mode. Deterministic and reproducible.

Every failure carries machine-readable fields *and* an explanation, because the
AI assistant consumes these records directly to answer "why did my rocket
fail?". The explanation text states what the model actually computed; it never
claims to reproduce a real-world accident.

Determinism
-----------
Randomised failure probabilities use a seeded LCG, never :mod:`random`. Two runs
of the same config produce byte-identical failure sequences, which
``simulation/tests/test_engine.py`` asserts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, NamedTuple, Optional

from simulation.contracts import (
    EventSeverity,
    FailureConfig,
    FailureDetail,
    FailureSubsystem,
)


class SeededRandom:
    """
    A small linear congruential generator.

    Numerical Recipes parameters. Used instead of :mod:`random` so a run is a
    pure function of its config — the module-level RNG would leak state between
    runs and break determinism.
    """

    def __init__(self, seed: int = 1) -> None:
        self._state = seed & 0xFFFFFFFF

    def next(self) -> float:
        """Next value in [0, 1)."""
        self._state = (1664525 * self._state + 1013904223) & 0xFFFFFFFF
        return self._state / 0x100000000


class FailureEffects(NamedTuple):
    """How active failures modify the vehicle's behaviour."""

    #: Multiplier applied to thrust. 0 means the engine is dead.
    thrust_multiplier: float = 1.0
    #: Multiplier applied to mass flow (a leak burns propellant faster).
    mass_flow_multiplier: float = 1.0
    #: Guidance has failed; the last attitude command is held.
    guidance_failed: bool = False
    #: Staging has failed; no further separation is possible.
    staging_failed: bool = False
    #: The flight is over.
    terminal: bool = False


@dataclass(frozen=True)
class DetectionInputs:
    """The flight state the detection rules are evaluated against."""

    t: float
    stage_index: int
    altitude_m: float
    speed_ms: float
    g_load_g: float
    dynamic_pressure_Pa: float
    twr: float
    mass_kg: float
    thrust_N: float
    engine_on: bool
    has_lifted_off: bool
    #: How long the engine has been burning while still on the pad. Unit: s.
    burn_time_on_pad_s: float
    max_dynamic_pressure_Pa: float


def _detail(
    *,
    mode_id: str,
    subsystem: FailureSubsystem,
    failure_mode: str,
    severity: EventSeverity,
    t: float,
    stage_index: Optional[int],
    trigger_condition: str,
    measured_value: float,
    threshold_value: float,
    unit: str,
    trigger_state: dict,
    contributing_factors: List[str],
    consequence: str,
    educational_explanation: str,
    recommended_fix: str,
    related_lessons: List[str],
    is_terminal: bool,
) -> FailureDetail:
    """Build a FailureDetail with a stable, reproducible id."""
    return FailureDetail(
        id=f"{mode_id}-{t:.3f}",
        mode_id=mode_id,
        subsystem=subsystem,
        failure_mode=failure_mode,
        severity=severity,
        t=t,
        stage_index=stage_index,
        trigger_condition=trigger_condition,
        measured_value=measured_value,
        threshold_value=threshold_value,
        unit=unit,
        trigger_state=trigger_state,
        contributing_factors=contributing_factors,
        consequence=consequence,
        educational_explanation=educational_explanation,
        recommended_fix=recommended_fix,
        related_lessons=related_lessons,
        is_terminal=is_terminal,
    )


def detect_failures(
    inputs: DetectionInputs, config: FailureConfig, already_fired: set
) -> List[FailureDetail]:
    """
    Run every detection rule against the current state.

    Args:
        inputs: Current flight state.
        config: Failure configuration, including thresholds.
        already_fired: Mode ids that have already fired, so a rule that stays
            true does not fire on every step.

    Returns:
        Newly triggered failures, possibly empty.
    """
    if not config.enabled or not config.detection_enabled:
        return []

    found: List[FailureDetail] = []
    th = config.thresholds

    # --- Insufficient thrust to leave the pad ---------------------------------
    # Only meaningful once the engine has been burning for a moment: thrust
    # takes a finite time to build and the vehicle is briefly held by its own
    # weight even on a healthy launch. A TWR below 1 later in flight is normal
    # (an upper stage is often well under 1 g).
    if (
        "INSUFFICIENT_THRUST" not in already_fired
        and inputs.engine_on
        and not inputs.has_lifted_off
        and inputs.burn_time_on_pad_s > 2.0
        and inputs.mass_kg > 0
        and inputs.twr < th.min_liftoff_twr
    ):
        found.append(
            _detail(
                mode_id="INSUFFICIENT_THRUST",
                subsystem=FailureSubsystem.PROPULSION,
                failure_mode="Insufficient thrust for liftoff",
                severity=EventSeverity.CRITICAL,
                t=inputs.t,
                stage_index=inputs.stage_index,
                trigger_condition="thrust-to-weight ratio below 1 at ignition",
                measured_value=inputs.twr,
                threshold_value=th.min_liftoff_twr,
                unit="dimensionless",
                trigger_state={"twr": inputs.twr, "altitude_m": inputs.altitude_m},
                contributing_factors=[
                    "First-stage thrust is lower than the vehicle's weight on the pad",
                    "Launch mass may be too high for the selected engine",
                ],
                consequence="The vehicle cannot leave the pad and the mission ends at T+0.",
                educational_explanation=(
                    "A rocket lifts off only when thrust exceeds weight, i.e. when "
                    "T/(m*g) > 1. This vehicle's computed ratio is "
                    f"{inputs.twr:.2f}, so the net vertical force is downward. Real "
                    "launch vehicles are designed for a liftoff TWR of roughly 1.2 "
                    "to 1.5 — enough margin to climb briskly without wasting "
                    "propellant fighting drag low in the atmosphere."
                ),
                recommended_fix=(
                    "Add engines, choose a higher-thrust engine, or reduce propellant "
                    "and payload mass until the liftoff TWR is at least 1.2."
                ),
                related_lessons=["propulsion-basics", "thrust-to-weight"],
                is_terminal=True,
            )
        )

    # --- Dynamic pressure limit ----------------------------------------------
    max_q_limit = th.max_dynamic_pressure_Pa or inputs.max_dynamic_pressure_Pa
    if (
        "MAX_Q_EXCEEDED" not in already_fired
        and max_q_limit > 0
        and inputs.dynamic_pressure_Pa > max_q_limit
    ):
        found.append(
            _detail(
                mode_id="MAX_Q_EXCEEDED",
                subsystem=FailureSubsystem.AERODYNAMICS,
                failure_mode="Dynamic pressure exceeded limit",
                severity=EventSeverity.FATAL,
                t=inputs.t,
                stage_index=inputs.stage_index,
                trigger_condition="dynamic pressure above the vehicle's rated limit",
                measured_value=inputs.dynamic_pressure_Pa,
                threshold_value=max_q_limit,
                unit="Pa",
                trigger_state={
                    "altitude_m": inputs.altitude_m,
                    "speed_ms": inputs.speed_ms,
                },
                contributing_factors=[
                    "Vehicle accelerated too hard while still in dense air",
                ],
                consequence="Aerodynamic loads exceed what the vehicle can survive.",
                educational_explanation=(
                    "Dynamic pressure q = rho*v^2/2 peaks partway through ascent, as "
                    "rising speed competes with falling air density. This flight "
                    f"reached {inputs.dynamic_pressure_Pa:,.0f} Pa against a limit of "
                    f"{max_q_limit:,.0f} Pa."
                ),
                recommended_fix=(
                    "Reduce thrust during the transonic phase or pitch over earlier so "
                    "the vehicle gains speed at higher altitude."
                ),
                related_lessons=["aerodynamics", "max-q"],
                is_terminal=True,
            )
        )

    # --- Excessive g-load -----------------------------------------------------
    if "EXCESSIVE_G_LOAD" not in already_fired and inputs.g_load_g > th.max_g_load_g:
        found.append(
            _detail(
                mode_id="EXCESSIVE_G_LOAD",
                subsystem=FailureSubsystem.STRUCTURE,
                failure_mode="Acceleration exceeded g-load limit",
                severity=EventSeverity.CRITICAL,
                t=inputs.t,
                stage_index=inputs.stage_index,
                trigger_condition="g-load above configured maximum",
                measured_value=inputs.g_load_g,
                threshold_value=th.max_g_load_g,
                unit="g",
                trigger_state={"altitude_m": inputs.altitude_m, "speed_ms": inputs.speed_ms},
                contributing_factors=[
                    "Thrust stayed high as propellant burned off and mass dropped",
                ],
                consequence="Payload and structure experience more acceleration than rated.",
                educational_explanation=(
                    "Acceleration rises through a burn because thrust is roughly "
                    "constant while mass falls. This flight reached "
                    f"{inputs.g_load_g:.1f} g against a {th.max_g_load_g:.1f} g limit. "
                    "Crewed vehicles throttle down to stay near 3 g."
                ),
                recommended_fix="Throttle down late in the burn, or stage earlier.",
                related_lessons=["propulsion-basics", "structures"],
                is_terminal=False,
            )
        )

    # --- Aerodynamic heating --------------------------------------------------
    if (
        "THERMAL_LIMIT" not in already_fired
        and inputs.altitude_m < th.heating_altitude_ceiling_m
        and inputs.speed_ms > th.max_atmospheric_speed_ms
    ):
        found.append(
            _detail(
                mode_id="THERMAL_LIMIT",
                subsystem=FailureSubsystem.THERMAL,
                failure_mode="Aerodynamic heating exceeded limit",
                severity=EventSeverity.CRITICAL,
                t=inputs.t,
                stage_index=inputs.stage_index,
                trigger_condition="high speed while still in dense air",
                measured_value=inputs.speed_ms,
                threshold_value=th.max_atmospheric_speed_ms,
                unit="m/s",
                trigger_state={
                    "altitude_m": inputs.altitude_m,
                    "dynamic_pressure_Pa": inputs.dynamic_pressure_Pa,
                },
                contributing_factors=[
                    f"Altitude {inputs.altitude_m:,.0f} m, where the air is still dense",
                    "Heating rate rises roughly with the cube of speed",
                ],
                consequence="Skin temperature exceeds what the structure can survive.",
                educational_explanation=(
                    "Aerodynamic heating scales roughly with the cube of speed and "
                    "with air density, so going fast low down is far more punishing "
                    f"than going fast high up. This flight reached {inputs.speed_ms:,.0f} "
                    f"m/s at {inputs.altitude_m:,.0f} m, against a modelled limit of "
                    f"{th.max_atmospheric_speed_ms:,.0f} m/s below "
                    f"{th.heating_altitude_ceiling_m:,.0f} m. The threshold is a simple "
                    "stand-in for a real thermal analysis, not a computed skin temperature."
                ),
                recommended_fix=(
                    "Pitch over earlier so the vehicle climbs out of the dense air "
                    "before building speed, or reduce thrust low in the atmosphere."
                ),
                related_lessons=["aerodynamics", "thermal-protection"],
                is_terminal=False,
            )
        )

    return found


def check_injections(
    t: float, dt: float, config: FailureConfig, already_fired: set
) -> List[FailureDetail]:
    """
    Fire any scripted failure whose time has arrived.

    An injection is a dict with at least ``mode_id`` and ``t``; optional keys are
    ``subsystem``, ``severity``, ``is_terminal``, ``probability``, and
    ``description``. Unknown keys are ignored so the mission format can grow
    without breaking older runs.

    Args:
        t: Current simulation time. Unit: s.
        dt: Timestep, so an injection lands in exactly one step. Unit: s.
        config: Failure configuration carrying the injection list.
        already_fired: Ids already fired.

    Returns:
        Newly triggered failures.
    """
    if not config.enabled or not config.injections:
        return []

    fired: List[FailureDetail] = []
    rng = SeededRandom(config.seed)

    for injection in config.injections:
        mode_id = str(injection.get("mode_id", "SCRIPTED_FAILURE"))
        if mode_id in already_fired:
            continue

        at = float(injection.get("t", 0.0))
        if not (t <= at < t + dt):
            continue

        probability = float(injection.get("probability", 1.0))
        if probability < 1.0 and rng.next() > probability:
            already_fired.add(mode_id)  # rolled and missed; do not re-roll
            continue

        subsystem = injection.get("subsystem", FailureSubsystem.AVIONICS.value)
        severity = injection.get("severity", EventSeverity.CRITICAL.value)

        fired.append(
            _detail(
                mode_id=mode_id,
                subsystem=FailureSubsystem(subsystem),
                failure_mode=str(injection.get("failure_mode", mode_id)),
                severity=EventSeverity(severity),
                t=at,
                stage_index=injection.get("stage_index"),
                trigger_condition="scripted injection",
                measured_value=at,
                threshold_value=at,
                unit="s",
                trigger_state={"t": at},
                contributing_factors=["Failure was scripted by the mission author"],
                consequence=str(
                    injection.get("consequence", "The affected subsystem stops working.")
                ),
                educational_explanation=str(
                    injection.get(
                        "educational_explanation",
                        "This failure was injected deliberately to demonstrate the "
                        "mode. It is not a prediction that this vehicle would fail.",
                    )
                ),
                recommended_fix=str(injection.get("recommended_fix", "Not applicable.")),
                related_lessons=list(injection.get("related_lessons", [])),
                is_terminal=bool(injection.get("is_terminal", False)),
            )
        )

    return fired


#: Which effect each known failure mode has on the vehicle.
_EFFECT_BY_MODE = {
    "INSUFFICIENT_THRUST": FailureEffects(terminal=True),
    "MAX_Q_EXCEEDED": FailureEffects(thrust_multiplier=0.0, terminal=True),
    "THERMAL_LIMIT": FailureEffects(),
    "EXCESSIVE_G_LOAD": FailureEffects(),
    "ENGINE_SHUTDOWN": FailureEffects(thrust_multiplier=0.0),
    "THRUST_LOSS": FailureEffects(thrust_multiplier=0.5),
    "PROPELLANT_LEAK": FailureEffects(mass_flow_multiplier=2.0),
    "GUIDANCE_FAILURE": FailureEffects(guidance_failed=True),
    "NAVIGATION_FAILURE": FailureEffects(guidance_failed=True),
    "CONTROL_FAILURE": FailureEffects(guidance_failed=True),
    "STAGE_SEPARATION_FAILURE": FailureEffects(staging_failed=True),
}


def combined_effects(active: List[FailureDetail]) -> FailureEffects:
    """
    Fold every active failure into a single set of effects.

    Multipliers compose multiplicatively (two half-thrust failures leave a
    quarter), booleans are sticky once set.
    """
    thrust = 1.0
    mass_flow = 1.0
    guidance_failed = False
    staging_failed = False
    terminal = False

    for failure in active:
        effect = _EFFECT_BY_MODE.get(failure.mode_id)
        if effect is None:
            # Unknown mode: severity alone decides whether it ends the flight.
            terminal = terminal or failure.is_terminal
            continue
        thrust *= effect.thrust_multiplier
        mass_flow *= effect.mass_flow_multiplier
        guidance_failed = guidance_failed or effect.guidance_failed
        staging_failed = staging_failed or effect.staging_failed
        terminal = terminal or effect.terminal or failure.is_terminal

    return FailureEffects(
        thrust_multiplier=thrust,
        mass_flow_multiplier=mass_flow,
        guidance_failed=guidance_failed,
        staging_failed=staging_failed,
        terminal=terminal,
    )


def failure_event_type(failure: FailureDetail) -> str:
    """The event ``type`` string used when a failure is emitted as an event."""
    return f"FAILURE_{failure.mode_id}"
