"""Scoring a flight against engineering criteria.

Nine categories, each scored out of 100 from criteria whose measurements come
from the *undecimated* telemetry — the run's true peaks, not the thinned series
sent to the browser. A max-Q that falls between two returned samples must still
be scored.

## How a criterion scores

Each criterion declares an acceptable band and a weight. Inside the band it
earns full marks. Outside it, marks fall off smoothly with how far outside it
sits, rather than dropping to zero at the boundary — because a static margin of
0.98 calibers is very nearly fine and 0.1 calibers is not, and a step function
would score them identically.

## What is deliberately not scored

Categories the flight never exercised. A vehicle with no recovery system is not
marked down for failing to deploy a parachute; that category is returned as
`not_applicable` with the reason. Scoring absent hardware as zero would push
every simple design's overall score down for no engineering reason.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

from .evaluation_models import (
    EvaluationCategory,
    EvaluationCriterion,
    MissionEvaluation,
)

__all__ = ["evaluate_mission"]

#: How far outside its band a value must go before a criterion scores zero,
#: as a multiple of the bound it violated. 1.5 means a static margin of 0.42
#: against a 1.0 minimum keeps 61% of its marks — clearly penalised, but not
#: scored identically to a margin of zero.
#:
#: Scaled against the *bound*, never against the band width. Scaling by width
#: made a wide band forgiving in a way that had nothing to do with the physics:
#: stability's 1.0–2.5 caliber band is 1.5 wide, so a margin of 0.42 scored 74%
#: purely because the acceptable range happened to be broad.
_FALLOFF = 1.5


def _score_band(
    measured: float,
    good_min: Optional[float],
    good_max: Optional[float],
    weight: float,
) -> tuple:
    """Points earned, and whether the criterion passed.

    Returns `(earned, passed)`.
    """
    if good_min is not None and good_max is not None:
        if good_min <= measured <= good_max:
            return weight, True
        below = measured < good_min
        bound = good_min if below else good_max
        distance = (good_min - measured) if below else (measured - good_max)
        scale = max(abs(bound), 1e-9)
        fraction = max(0.0, 1.0 - distance / (scale * _FALLOFF))
        return weight * fraction, False

    if good_min is not None:
        if measured >= good_min:
            return weight, True
        scale = max(abs(good_min), 1e-9)
        fraction = max(0.0, 1.0 - (good_min - measured) / (scale * _FALLOFF))
        return weight * fraction, False

    if good_max is not None:
        if measured <= good_max:
            return weight, True
        scale = max(abs(good_max), 1e-9)
        fraction = max(0.0, 1.0 - (measured - good_max) / (scale * _FALLOFF))
        return weight * fraction, False

    return weight, True


def _criterion(
    id: str,
    label: str,
    measured: float,
    *,
    unit: str = "",
    good_min: Optional[float] = None,
    good_max: Optional[float] = None,
    weight: float = 25.0,
    note: str = "",
    recommendation: Optional[str] = None,
) -> EvaluationCriterion:
    earned, passed = _score_band(measured, good_min, good_max, weight)
    return EvaluationCriterion(
        id=id,
        label=label,
        measured=float(measured),
        unit=unit,
        good_min=good_min,
        good_max=good_max,
        weight=weight,
        earned=round(earned, 2),
        passed=passed,
        note=note,
        recommendation=None if passed else recommendation,
    )


def _category(
    id: str,
    label: str,
    criteria: Sequence[EvaluationCriterion],
    summary_pass: str,
    summary_fail: str,
) -> EvaluationCategory:
    total_weight = sum(c.weight for c in criteria) or 1.0
    earned = sum(c.earned for c in criteria)
    score = int(round(100 * earned / total_weight))
    failures = [c for c in criteria if not c.passed]
    return EvaluationCategory(
        id=id,
        label=label,
        score=max(0, min(100, score)),
        summary=summary_pass if not failures else summary_fail,
        criteria=list(criteria),
    )


def _not_applicable(id: str, label: str, reason: str) -> EvaluationCategory:
    return EvaluationCategory(
        id=id, label=label, score=0, summary=reason, not_applicable=True, criteria=[]
    )


def evaluate_mission(
    result: Any,
    vehicle: Any,
    mission: Any,
    *,
    telemetry: Optional[Sequence[Any]] = None,
) -> MissionEvaluation:
    """
    Score a completed flight.

    Args:
        result: The `SimResult` the engine produced.
        vehicle: The `Vehicle` that was flown.
        mission: The `MissionConfig` it was flown under.
        telemetry: The undecimated telemetry. Defaults to `result.telemetry`;
            the API passes the full series so the peaks the structural criteria
            are measured against are not lost to decimation.

    Returns:
        Nine scored categories, the strengths and weaknesses behind them, and an
        ordered list of what to change, most recovery first.
    """
    samples = list(telemetry if telemetry is not None else result.telemetry)
    summary = result.summary
    environment = mission.environment

    categories: List[EvaluationCategory] = [
        _vehicle(vehicle, summary),
        _stability(vehicle),
        _propulsion(vehicle, summary),
        _aerodynamics(summary, samples),
        _structural(vehicle, summary, result),
        _environment(environment, summary),
        _trajectory(mission, summary, samples),
        _mission_outcome(result, summary),
        _recovery(vehicle, result),
    ]

    scored = [c for c in categories if not c.not_applicable]
    overall = int(round(sum(c.score for c in scored) / max(len(scored), 1)))

    strengths = [
        "{0}: {1}/100.".format(c.label, c.score) for c in scored if c.score >= 85
    ]
    weaknesses = []
    recommendations = []

    # Order what to fix by how many points it would recover, so the first
    # suggestion is the one that changes the most.
    losses = []
    for category in scored:
        for criterion in category.criteria:
            if criterion.passed:
                continue
            lost = criterion.weight - criterion.earned
            if lost < 1.0:
                continue
            losses.append((lost, category, criterion))

    losses.sort(key=lambda item: item[0], reverse=True)

    for lost, category, criterion in losses[:8]:
        weaknesses.append(
            "{0} — {1} measured {2}, against {3}. Cost {4:.0f} points.".format(
                category.label,
                criterion.label.lower(),
                _format_measure(criterion.measured, criterion.unit),
                _describe_band(criterion),
                lost,
            )
        )
        if criterion.recommendation:
            recommendations.append(criterion.recommendation)

    # Failures the simulation itself detected come first: they ended the flight.
    for failure in result.failures:
        recommendations.insert(0, failure.recommended_fix)

    if not recommendations:
        recommendations.append(
            "Nothing is clearly wrong with this design. Try raising the target orbit, "
            "adding payload, or flying it in worse weather to find where it breaks."
        )

    return MissionEvaluation(
        overall_score=max(0, min(100, overall)),
        categories=categories,
        strengths=strengths,
        weaknesses=weaknesses,
        recommendations=_dedupe(recommendations)[:6],
        limitations=[
            "The flight is a three-degree-of-freedom point-mass simulation. It does not model "
            "the vehicle's rotational dynamics, so a design that would be uncontrollable in "
            "pitch can still fly here.",
            "Aerodynamics use a single drag coefficient with a Mach correction. There is no "
            "lift, no base drag model and no fin interference.",
            "The wind profile is built from one surface observation. A real launch commit uses "
            "a balloon sounding taken hours before the window.",
            "Earth's rotation is not added to the initial velocity, so an eastward launch does "
            "not receive the free velocity it would in reality.",
            "Structural limits are compared against a single rated value rather than against a "
            "load path, so where a vehicle would break is not modelled — only that it would.",
        ],
    )


# ── Categories ────────────────────────────────────────────────


def _vehicle(vehicle: Any, summary: Any) -> EvaluationCategory:
    dry = sum(stage.dry_mass_kg for stage in vehicle.stages)
    propellant = sum(stage.propellant_mass_kg for stage in vehicle.stages)
    wet = dry + propellant + vehicle.payload_mass_kg
    propellant_fraction = propellant / wet if wet > 0 else 0.0
    payload_fraction = vehicle.payload_mass_kg / wet if wet > 0 else 0.0
    fineness = vehicle.length_m / vehicle.diameter_m if vehicle.diameter_m > 0 else 0.0

    return _category(
        "vehicle",
        "Vehicle",
        [
            _criterion(
                "propellant_fraction",
                "Propellant mass fraction",
                propellant_fraction,
                unit="",
                good_min=0.70,
                good_max=0.95,
                weight=40,
                note="Launch vehicles run around 0.85–0.90. Below 0.7 the structure is carrying its own weight rather than the payload's.",
                recommendation="Increase propellant relative to structure, or reduce dry mass. Below a 0.7 propellant fraction the rocket equation gives very little back.",
            ),
            _criterion(
                "payload_fraction",
                "Payload mass fraction",
                payload_fraction,
                unit="",
                good_min=0.005,
                good_max=0.06,
                weight=25,
                note="Real launchers deliver 1–4% of launch mass to orbit.",
                recommendation="Add payload. A vehicle carrying nothing is a demonstration rather than a mission.",
            ),
            _criterion(
                "fineness_ratio",
                "Fineness ratio",
                fineness,
                unit="",
                good_min=8.0,
                good_max=25.0,
                weight=20,
                note="Length over diameter. Slender vehicles have less frontal area for the same volume.",
                recommendation="A stubby vehicle pays for its frontal area in drag; an extremely slender one becomes hard to keep stiff. Aim for 10–20.",
            ),
            _criterion(
                "stage_count",
                "Stage count",
                float(len(vehicle.stages)),
                unit="",
                good_min=1,
                good_max=3,
                weight=15,
                note="Two or three stages is where almost every real launch vehicle lands.",
                recommendation="Beyond three stages the mass of interstages and separation systems outweighs what staging returns.",
            ),
        ],
        "Mass distribution and proportions are in the range real vehicles occupy.",
        "The vehicle's proportions are outside the range that flies well.",
    )


def _stability(vehicle: Any) -> EvaluationCategory:
    return _category(
        "stability",
        "Stability",
        [
            _criterion(
                "margin_wet",
                "Static margin, full",
                vehicle.stability_margin_wet_cal,
                unit="cal",
                good_min=1.0,
                good_max=2.5,
                weight=55,
                note="Calibers of separation between centre of pressure and centre of gravity, at liftoff.",
                recommendation="Below 1 caliber a gust is amplified rather than corrected. Increase fin area, or move mass forward.",
            ),
            _criterion(
                "margin_dry",
                "Static margin, empty",
                vehicle.stability_margin_dry_cal,
                unit="cal",
                good_min=0.8,
                good_max=3.5,
                weight=45,
                note="Propellant burns off from ahead of the engine, so the centre of gravity moves aft and the margin shrinks through the flight.",
                recommendation="This design is stable full and marginal empty. Check the margin at burnout, not just on the pad.",
            ),
        ],
        "Statically stable throughout the burn.",
        "Static margin is outside the 1–2 caliber band somewhere in the flight.",
    )


def _propulsion(vehicle: Any, summary: Any) -> EvaluationCategory:
    first = vehicle.stages[0] if vehicle.stages else None
    if first is None:
        return _not_applicable("propulsion", "Propulsion", "This vehicle has no stages.")

    launch_mass = vehicle.launch_mass_kg or 1.0
    twr = first.thrust_sea_level_N / (launch_mass * 9.80665)
    isp = first.isp_vacuum_s
    total_impulse = sum(s.thrust_vacuum_N * s.burn_time_s for s in vehicle.stages)
    dv_efficiency = (
        summary.delta_v_achieved_ms / summary.delta_v_ideal_ms
        if summary.delta_v_ideal_ms > 0
        else 0.0
    )

    return _category(
        "propulsion",
        "Propulsion",
        [
            _criterion(
                "liftoff_twr",
                "Liftoff thrust-to-weight",
                twr,
                unit="",
                good_min=1.2,
                good_max=2.0,
                weight=40,
                note="Below 1.0 nothing happens. Above about 2 the vehicle gets fast while still deep in dense air.",
                recommendation=(
                    "Below 1.2 the vehicle spends most of its propellant fighting gravity. "
                    "Above 2.0 it reaches high dynamic pressure too low down. Aim for 1.2–1.5."
                ),
            ),
            _criterion(
                "specific_impulse",
                "First-stage specific impulse",
                isp,
                unit="s",
                good_min=240,
                good_max=470,
                weight=25,
                note="Solids reach 250–280 s, kerolox 300–350, hydrolox up to 450.",
                recommendation="An Isp outside 240–470 s is outside what chemical propulsion achieves. Check the engine selection.",
            ),
            _criterion(
                "delta_v_efficiency",
                "Δv realised",
                dv_efficiency,
                unit="",
                good_min=0.55,
                good_max=1.0,
                weight=35,
                note="Peak speed as a fraction of the ideal Δv the propellant contained.",
                recommendation=(
                    "Most of the propellant's energy went into gravity and drag rather than into speed. "
                    "A higher thrust-to-weight or an earlier pitchover both reduce gravity loss."
                ),
            ),
        ],
        "Propulsion is sized and performing in the range real vehicles do.",
        "Propulsion is outside the band that produces an efficient ascent.",
    )


def _aerodynamics(summary: Any, samples: Sequence[Any]) -> EvaluationCategory:
    max_q = summary.max_dynamic_pressure_Pa
    drag_loss = summary.drag_loss_ms
    max_alpha = summary.max_angle_of_attack_deg
    q_alpha = summary.max_q_alpha_Padeg

    return _category(
        "aerodynamics",
        "Aerodynamics",
        [
            _criterion(
                "max_q",
                "Maximum dynamic pressure",
                max_q / 1000.0,
                unit="kPa",
                good_max=45.0,
                weight=30,
                note="Typical launch vehicles peak at 30–40 kPa. It is what the airframe is sized against.",
                recommendation="Reduce liftoff thrust-to-weight, or throttle through max-Q, so the vehicle is higher before it is fast.",
            ),
            _criterion(
                "drag_loss",
                "Drag loss",
                drag_loss,
                unit="m/s",
                good_max=400.0,
                weight=30,
                note="Real launches lose 100–300 m/s to drag. More than that means too much frontal area, or too long in dense air.",
                recommendation="Reduce diameter or drag coefficient, or climb faster through the lower atmosphere.",
            ),
            _criterion(
                "angle_of_attack",
                "Peak angle of attack",
                max_alpha,
                unit="°",
                good_max=12.0,
                weight=20,
                note="Measured during powered atmospheric ascent only. A rocket has almost no tolerance for side loading.",
                recommendation="Pitch over more gently, or fly a gravity turn so the vehicle follows its velocity vector instead of fighting it.",
            ),
            _criterion(
                "q_alpha",
                "Peak q·α",
                q_alpha,
                unit="Pa·deg",
                good_max=250_000.0,
                weight=20,
                note="Dynamic pressure times angle of attack — the lateral bending load. The Shuttle's limit was around 240,000 Pa·deg.",
                recommendation="Either the wind or the pitch program is putting the vehicle sideways to the airflow while dynamic pressure is high. Fly in calmer conditions or pitch more gently.",
            ),
        ],
        "Aerodynamic loads stayed inside the range an airframe is normally built for.",
        "Aerodynamic loads exceeded what a conventional airframe is sized to carry.",
    )


def _structural(vehicle: Any, summary: Any, result: Any) -> EvaluationCategory:
    peak_g = summary.max_acceleration_g
    q_margin = (
        vehicle.max_dynamic_pressure_Pa / max(summary.max_dynamic_pressure_Pa, 1.0)
    )
    structural_failures = sum(
        1 for f in result.failures if f.subsystem.value in ("structure", "aerodynamics")
    )

    return _category(
        "structural",
        "Structural",
        [
            _criterion(
                "peak_g",
                "Peak acceleration",
                peak_g,
                unit="g",
                good_max=8.0,
                weight=40,
                note="Uncrewed vehicles are typically limited by structure and payload to under 8 g. Crewed ones to about 3.",
                recommendation="Throttle down near the end of the burn. Acceleration climbs as propellant burns off, so the peak is at cutoff.",
            ),
            _criterion(
                "q_margin",
                "Margin against rated max-Q",
                q_margin,
                unit="×",
                good_min=1.25,
                weight=35,
                note="How much headroom the airframe had over the dynamic pressure it actually saw.",
                recommendation="The flight came close to the airframe's rated limit. Either strengthen it or fly a profile that does not reach that dynamic pressure.",
            ),
            _criterion(
                "structural_failures",
                "Structural failures",
                float(structural_failures),
                unit="",
                good_max=0.0,
                weight=25,
                note="Any structural or aerodynamic failure the simulation detected.",
                recommendation="The airframe failed. Read the failure record for the measured value and the threshold it crossed.",
            ),
        ],
        "The structure carried every load the flight imposed, with margin.",
        "The structure was loaded beyond what it is rated for.",
    )


def _environment(environment: Any, summary: Any) -> EvaluationCategory:
    wind = environment.wind_speed_ms
    density_ratio = 1.0
    # Standard-day sea-level density, for the comparison.
    if environment.temperature_K > 0:
        density = environment.pressure_Pa / (287.058 * environment.temperature_K)
        density_ratio = density / 1.225

    return _category(
        "environment",
        "Environment",
        [
            _criterion(
                "surface_wind",
                "Surface wind",
                wind,
                unit="m/s",
                good_max=15.0,
                weight=35,
                note="Ground wind limits for medium launch vehicles sit around 15 m/s sustained.",
                recommendation="This is above the ground wind limit for a typical vehicle. Wait for a calmer window, or accept the lateral deviation.",
            ),
            _criterion(
                "lateral_deviation",
                "Lateral deviation from track",
                summary.max_lateral_deviation_m / 1000.0,
                unit="km",
                good_max=5.0,
                weight=35,
                note="How far crosswind carried the vehicle off the plane it was aimed along.",
                recommendation="Wind pushed the vehicle well off its intended ground track. A launch azimuth correction or calmer conditions would both help.",
            ),
            _criterion(
                "air_density",
                "Air density against standard",
                density_ratio,
                unit="×",
                good_min=0.90,
                good_max=1.10,
                weight=30,
                note="Denser air means proportionally more drag. This is context, not a fault of the design.",
                recommendation="Conditions were well away from a standard day. The trajectory reflects that; it is not a design problem.",
            ),
        ],
        "Conditions were within the range a launch would normally be committed in.",
        "Conditions were outside normal launch commit criteria.",
    )


def _trajectory(mission: Any, summary: Any, samples: Sequence[Any]) -> EvaluationCategory:
    target_m = mission.target.target_altitude_km * 1000.0
    reached = summary.max_altitude_m / target_m if target_m > 0 else 0.0

    final = samples[-1] if samples else None
    periapsis_km = (final.periapsis_altitude_m / 1000.0) if final else -1.0
    eccentricity = final.eccentricity if final else 1.0

    is_orbital = mission.target.type.value != "suborbital"

    criteria = [
        _criterion(
            "target_altitude",
            "Target altitude reached",
            reached,
            unit="×",
            good_min=0.95,
            good_max=1.35,
            weight=40,
            note="Apogee as a fraction of the mission's target altitude.",
            recommendation="The vehicle did not reach its target. Either add Δv or lower the target.",
        ),
        _criterion(
            "gravity_loss",
            "Gravity loss",
            summary.gravity_loss_ms,
            unit="m/s",
            good_max=1800.0,
            weight=30,
            note="Real ascents lose 1,200–1,500 m/s to gravity. More means too long spent climbing vertically.",
            recommendation="Pitch over earlier so the thrust vector goes into horizontal velocity sooner.",
        ),
    ]

    if is_orbital:
        criteria.append(
            _criterion(
                "periapsis",
                "Periapsis altitude",
                periapsis_km,
                unit="km",
                good_min=120.0,
                weight=30,
                note="The low point of the orbit must clear the atmosphere, or the trajectory intersects Earth.",
                recommendation=(
                    "Apogee was reached but periapsis is still inside the atmosphere, so this is a "
                    "ballistic arc rather than an orbit. More of the burn needs to go into horizontal velocity."
                ),
            )
        )
    else:
        criteria.append(
            _criterion(
                "eccentricity",
                "Trajectory shape",
                eccentricity,
                unit="",
                good_max=1.0,
                weight=30,
                note="A suborbital profile is expected to be a closed ballistic arc.",
            )
        )

    return _category(
        "trajectory",
        "Trajectory",
        criteria,
        "The flight followed a profile appropriate to its target.",
        "The trajectory did not put the vehicle where the mission needed it.",
    )


def _mission_outcome(result: Any, summary: Any) -> EvaluationCategory:
    fatal = sum(1 for f in result.failures if f.is_terminal)
    warnings = sum(1 for f in result.failures if not f.is_terminal)

    return _category(
        "mission",
        "Mission",
        [
            _criterion(
                "outcome",
                "Objective achieved",
                1.0 if result.success else 0.0,
                unit="",
                good_min=1.0,
                weight=50,
                note="Whether the mission met its stated objective.",
                recommendation="The mission did not succeed. The failure analysis names the specific reason.",
            ),
            _criterion(
                "terminal_failures",
                "Terminal failures",
                float(fatal),
                unit="",
                good_max=0.0,
                weight=30,
                note="Failures that ended the flight.",
                recommendation="Address the terminal failure first; nothing downstream of it was exercised.",
            ),
            _criterion(
                "warnings",
                "Warnings raised",
                float(warnings),
                unit="",
                good_max=2.0,
                weight=20,
                note="Non-terminal anomalies. A flight with none is either well-designed or under-tested.",
                recommendation="Several systems ran outside their nominal bands. They did not end the flight, but they narrow the margin available for a worse day.",
            ),
        ],
        "The mission met its objective without a terminal failure.",
        "The mission did not complete as configured.",
    )


def _recovery(vehicle: Any, result: Any) -> EvaluationCategory:
    recovery_failures = [f for f in result.failures if f.subsystem.value == "recovery"]

    # Nothing in the simulation contract exposes a recovery system, so the only
    # honest signal is whether recovery events occurred. Scoring a vehicle with
    # no parachute as zero here would penalise every orbital design for not
    # carrying hardware it has no use for.
    recovery_events = [
        event for event in result.events if "chute" in event.type or "recovery" in event.type
    ]

    if not recovery_events and not recovery_failures:
        return _not_applicable(
            "recovery",
            "Recovery",
            "No recovery system was exercised on this flight. Nothing to score.",
        )

    return _category(
        "recovery",
        "Recovery",
        [
            _criterion(
                "deployments",
                "Recovery events",
                float(len(recovery_events)),
                unit="",
                good_min=1.0,
                weight=50,
                note="Deployment events the flight recorded.",
                recommendation="Recovery hardware was carried but never deployed. Check the deployment conditions.",
            ),
            _criterion(
                "recovery_failures",
                "Recovery failures",
                float(len(recovery_failures)),
                unit="",
                good_max=0.0,
                weight=50,
                note="Failures in the recovery subsystem.",
                recommendation="The recovery system failed. A canopy deployed above its rated speed tears rather than decelerates.",
            ),
        ],
        "Recovery worked as configured.",
        "The recovery sequence did not complete.",
    )


# ── Helpers ───────────────────────────────────────────────────


def _format_measure(value: float, unit: str) -> str:
    if abs(value) >= 1e6:
        text = "{0:.2e}".format(value)
    elif abs(value) >= 1000:
        text = "{0:,.0f}".format(value)
    elif abs(value) >= 10:
        text = "{0:.1f}".format(value)
    else:
        text = "{0:.2f}".format(value)
    return "{0} {1}".format(text, unit).strip()


def _describe_band(criterion: EvaluationCriterion) -> str:
    if criterion.good_min is not None and criterion.good_max is not None:
        return "a target of {0}–{1} {2}".format(
            criterion.good_min, criterion.good_max, criterion.unit
        ).strip()
    if criterion.good_min is not None:
        return "a minimum of {0} {1}".format(criterion.good_min, criterion.unit).strip()
    if criterion.good_max is not None:
        return "a maximum of {0} {1}".format(criterion.good_max, criterion.unit).strip()
    return "no limit"


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
