"""
Mission evaluation.

Turns a finished flight into a scored report: nine categories, each with a
number out of a hundred, the measurements that produced it, and a sentence
saying what the number means.

## Why the scores are rules rather than a formula

Every score here is computed from a *stated criterion* with a threshold — "the
liftoff thrust-to-weight ratio should be between 1.2 and 1.5", "static margin
should sit between 1 and 2 calibers" — and the report carries the measured
value, the threshold, and the deduction alongside the score. A single opaque
number derived from a weighted formula would be worse than useless in a
teaching product: it would tell a learner they scored 61 without telling them
which of their decisions cost them the other 39.

Every criterion is therefore individually explicable, and the report shows its
working.

## What a score is not

It is not a judgement of whether the mission succeeded. A flight can fail and
still score well on propulsion, and a flight that reached orbit can score badly
on structure because it spent the whole ascent inside its own load limits by a
hair. Success is a separate, binary fact the simulation already reports;
these scores are about *how well the design was made*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from simulation.contracts import (
    EventSeverity,
    FailureDetail,
    MissionConfig,
    SimResult,
    TelemetryPoint,
    Vehicle,
)

__all__ = [
    "Criterion",
    "CategoryScore",
    "MissionEvaluation",
    "evaluate_mission",
    "CATEGORY_ORDER",
]

#: The categories, in report order — vehicle first, outcome last.
CATEGORY_ORDER = [
    "vehicle",
    "propulsion",
    "stability",
    "aerodynamics",
    "structural",
    "environment",
    "trajectory",
    "recovery",
    "mission",
]

CATEGORY_LABELS = {
    "vehicle": "Vehicle",
    "propulsion": "Propulsion",
    "stability": "Stability",
    "aerodynamics": "Aerodynamics",
    "structural": "Structural",
    "environment": "Environment",
    "trajectory": "Trajectory",
    "recovery": "Recovery",
    "mission": "Mission",
}


@dataclass(frozen=True)
class Criterion:
    """One rule, evaluated against one measurement.

    The report is built out of these rather than out of a formula, so every
    point deducted can be traced to a specific number crossing a specific
    threshold.
    """

    id: str
    label: str
    #: What was measured.
    measured: float
    unit: str
    #: The acceptable band. `None` on either side means unbounded.
    good_min: Optional[float]
    good_max: Optional[float]
    #: Points available for this criterion.
    weight: float
    #: Points earned, 0 to `weight`.
    earned: float
    #: What this measurement means, in a sentence.
    note: str
    #: What to change, when it fell short.
    recommendation: Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.earned >= self.weight * 0.999

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "measured": round(self.measured, 4),
            "unit": self.unit,
            "good_min": self.good_min,
            "good_max": self.good_max,
            "weight": self.weight,
            "earned": round(self.earned, 2),
            "passed": self.passed,
            "note": self.note,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class CategoryScore:
    """One scored category."""

    id: str
    label: str
    #: 0–100.
    score: float
    #: The criteria that produced it.
    criteria: List[Criterion] = field(default_factory=list)
    #: A one-line summary of the category's state.
    summary: str = ""
    #: True when no criterion in this category could be evaluated.
    not_applicable: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "score": round(self.score),
            "summary": self.summary,
            "not_applicable": self.not_applicable,
            "criteria": [c.to_dict() for c in self.criteria],
        }


@dataclass(frozen=True)
class MissionEvaluation:
    """The complete report."""

    overall_score: float
    categories: List[CategoryScore]
    #: What the design did well, in the order a reviewer would say it.
    strengths: List[str]
    #: What cost it the most points, worst first.
    weaknesses: List[str]
    #: Concrete changes, ordered by how much they would recover.
    recommendations: List[str]
    #: Stated limits of what this evaluation can see.
    limitations: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "overall_score": round(self.overall_score),
            "categories": [c.to_dict() for c in self.categories],
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "recommendations": self.recommendations,
            "limitations": self.limitations,
        }


# ──────────────────────────────────────────────────────────────
# Scoring helpers
# ──────────────────────────────────────────────────────────────


def _band_score(
    measured: float,
    good_min: Optional[float],
    good_max: Optional[float],
    weight: float,
    *,
    tolerance: float = 0.5,
) -> float:
    """
    Points earned for a value against an acceptable band.

    Full marks inside the band. Outside it, marks fall off linearly over a
    tolerance window expressed as a fraction of the band's width, reaching zero
    at the far edge of that window. A cliff at the threshold would make a
    design that is 1% out look identical to one that is 200% out, which teaches
    the wrong lesson: engineering margins are gradients, not switches.
    """
    if good_min is not None and good_max is not None:
        if good_min <= measured <= good_max:
            return weight
        width = max(good_max - good_min, 1e-9)
        distance = good_min - measured if measured < good_min else measured - good_max
        return max(0.0, weight * (1.0 - distance / (width * tolerance * 2)))

    if good_min is not None:
        if measured >= good_min:
            return weight
        span = max(abs(good_min) * tolerance, 1e-9)
        return max(0.0, weight * (1.0 - (good_min - measured) / span))

    if good_max is not None:
        if measured <= good_max:
            return weight
        span = max(abs(good_max) * tolerance, 1e-9)
        return max(0.0, weight * (1.0 - (measured - good_max) / span))

    return weight


def _criteria_score(criteria: Sequence[Criterion]) -> float:
    """Weighted score out of 100 from a set of criteria."""
    usable = [c for c in criteria if c.weight > 0]
    if not usable:
        return 0.0
    return 100.0 * sum(c.earned for c in usable) / sum(c.weight for c in usable)


def _category(
    cat_id: str,
    criteria: Sequence[Criterion],
    summary: str,
    score: Optional[float] = None,
) -> CategoryScore:
    """
    Roll criteria up into a category score out of 100.

    `score` overrides the weighted roll-up. It exists for the case the criteria
    cannot express: a subsystem that *failed outright*. A propulsion system that
    stopped working mid-flight did not score 78 on its criteria and then have an
    unrelated accident — the criteria measured a design that no longer applies,
    and the score has to say so.
    """
    usable = [c for c in criteria if c.weight > 0]
    if not usable:
        return CategoryScore(
            id=cat_id,
            label=CATEGORY_LABELS[cat_id],
            score=0.0,
            criteria=list(criteria),
            summary="Not applicable to this design.",
            not_applicable=True,
        )
    return CategoryScore(
        id=cat_id,
        label=CATEGORY_LABELS[cat_id],
        score=score if score is not None else _criteria_score(criteria),
        criteria=list(criteria),
        summary=summary,
    )


def _peak(telemetry: Sequence[TelemetryPoint], attribute: str) -> float:
    """Largest value of one channel across the flight."""
    return max((getattr(p, attribute, 0.0) or 0.0) for p in telemetry) if telemetry else 0.0


# ──────────────────────────────────────────────────────────────
# The evaluation
# ──────────────────────────────────────────────────────────────


def evaluate_mission(
    result: SimResult,
    vehicle: Vehicle,
    mission: MissionConfig,
) -> MissionEvaluation:
    """
    Score a finished flight.

    Args:
        result: The completed simulation.
        vehicle: The vehicle that flew, as the simulation saw it.
        mission: The mission it was flying.

    Returns:
        A scored report with the measurements behind every number.
    """
    telemetry = result.telemetry
    summary = result.summary
    failures = list(result.failures)

    categories = [
        _score_vehicle(vehicle, summary),
        _score_propulsion(vehicle, telemetry, summary, failures),
        _score_stability(vehicle, telemetry, failures),
        _score_aerodynamics(vehicle, telemetry, summary),
        _score_structural(vehicle, summary, failures),
        _score_environment(mission, summary, failures),
        _score_trajectory(mission, result, summary),
        _score_recovery(result, summary, failures),
        _score_mission(result, mission, summary),
    ]

    applicable = [c for c in categories if not c.not_applicable]
    overall = sum(c.score for c in applicable) / len(applicable) if applicable else 0.0

    strengths, weaknesses, recommendations = _narrate(categories)

    return MissionEvaluation(
        overall_score=overall,
        categories=categories,
        strengths=strengths,
        weaknesses=weaknesses,
        recommendations=recommendations,
        limitations=[
            "Scores measure how well the design was made, not whether the mission "
            "succeeded. Those are separate facts and the report gives both.",
            "The simulation models three degrees of freedom. Roll, yaw coupling and "
            "aeroelastic effects are not simulated, so a design that would flutter "
            "or spin will not be penalised for it here.",
            "Earth's rotation is not modelled, so an eastward launch does not "
            "collect the free velocity it would in reality.",
            "Structural scoring compares loads against declared limits. It does not "
            "analyse the structure itself.",
        ],
    )


def _score_vehicle(vehicle: Vehicle, summary) -> CategoryScore:
    """Mass fractions and proportions — the design before it flies."""
    criteria: List[Criterion] = []

    total_dry = sum(s.dry_mass_kg for s in vehicle.stages) + vehicle.payload_mass_kg
    total_propellant = sum(s.propellant_mass_kg for s in vehicle.stages)
    launch_mass = max(vehicle.launch_mass_kg, 1e-6)
    propellant_fraction = total_propellant / launch_mass

    criteria.append(
        Criterion(
            id="propellant_fraction",
            label="Propellant mass fraction",
            measured=propellant_fraction,
            unit="",
            good_min=0.70,
            good_max=0.95,
            weight=35,
            earned=_band_score(propellant_fraction, 0.70, 0.95, 35),
            note=(
                "Reaching orbit needs a mass ratio near 17, which means about 94% "
                "propellant. A vehicle carrying much less than 70% is mostly structure "
                "and will not go far."
            ),
            recommendation=(
                None
                if propellant_fraction >= 0.70
                else "Add propellant, or take mass out of the structure. The rocket "
                "equation is logarithmic, so structural mass costs more than "
                "propellant buys."
            ),
        )
    )

    fineness = vehicle.length_m / max(vehicle.diameter_m, 1e-6)
    criteria.append(
        Criterion(
            id="fineness_ratio",
            label="Fineness ratio",
            measured=fineness,
            unit="",
            good_min=8,
            good_max=25,
            weight=20,
            earned=_band_score(fineness, 8, 25, 20),
            note=(
                "Length over diameter. Below 8 the vehicle is a barrel and carries "
                "heavy drag for its volume; above 25 it becomes a bending problem."
            ),
            recommendation=(
                None
                if 8 <= fineness <= 25
                else "Adjust the ratio of body length to diameter toward the 8–25 band."
            ),
        )
    )

    payload_fraction = vehicle.payload_mass_kg / launch_mass
    criteria.append(
        Criterion(
            id="payload_fraction",
            label="Payload fraction",
            measured=payload_fraction,
            unit="",
            good_min=0.005,
            good_max=None,
            weight=25,
            earned=_band_score(payload_fraction, 0.005, None, 25),
            note=(
                "Payload as a share of launch mass. Real launchers manage 1–4% to low "
                "Earth orbit; a vehicle carrying nothing has no mission."
            ),
            recommendation=(
                None
                if payload_fraction >= 0.005
                else "Add payload. A vehicle with none is a test article, not a mission."
            ),
        )
    )

    stage_count = len(vehicle.stages)
    criteria.append(
        Criterion(
            id="staging_count",
            label="Number of stages",
            measured=float(stage_count),
            unit="",
            good_min=1,
            good_max=3,
            weight=20,
            earned=_band_score(float(stage_count), 1, 3, 20),
            note=(
                "One to three stages is where essentially every real vehicle lands. "
                "Beyond three, the mass of extra interstages and separation systems "
                "outweighs what staging returns."
            ),
            recommendation=(
                None
                if 1 <= stage_count <= 3
                else "Consolidate into two or three stages."
            ),
        )
    )

    score = _criteria_score(criteria)
    return _category(
        "vehicle",
        criteria,
        _summarise(
            score,
            good="Well-proportioned, with a sensible mass breakdown.",
            fair="Workable, though the mass breakdown leaves performance on the table.",
            poor="The proportions are working against this design before it leaves the pad.",
        ),
    )


def _score_propulsion(vehicle, telemetry, summary, failures) -> CategoryScore:
    """Thrust, impulse and how much of the Δv budget survived."""
    criteria: List[Criterion] = []

    total_thrust = sum(s.thrust_sea_level_N for s in vehicle.stages[:1]) or (
        vehicle.stages[0].thrust_sea_level_N if vehicle.stages else 0.0
    )
    weight_N = vehicle.launch_mass_kg * 9.80665
    twr = total_thrust / weight_N if weight_N > 0 else 0.0

    criteria.append(
        Criterion(
            id="liftoff_twr",
            label="Liftoff thrust-to-weight",
            measured=twr,
            unit="",
            good_min=1.2,
            good_max=1.8,
            weight=40,
            earned=_band_score(twr, 1.2, 1.8, 40),
            note=(
                "Below 1.0 the vehicle cannot lift itself. Between 1.0 and 1.2 it "
                "rises so slowly that gravity losses consume the budget. Above 1.8 it "
                "reaches high dynamic pressure while still deep in the atmosphere."
            ),
            recommendation=(
                None
                if 1.2 <= twr <= 1.8
                else (
                    "Add thrust or remove mass — this will not leave the pad."
                    if twr < 1.0
                    else "Raise thrust toward a liftoff ratio of 1.2–1.5."
                    if twr < 1.2
                    else "Reduce thrust or add mass; this is accelerating harder than "
                    "it needs to, and paying for it in drag and structural load."
                )
            ),
        )
    )

    ideal = summary.delta_v_ideal_ms
    achieved = summary.delta_v_achieved_ms
    efficiency = achieved / ideal if ideal > 0 else 0.0
    criteria.append(
        Criterion(
            id="delta_v_efficiency",
            label="Δv realised",
            measured=efficiency,
            unit="",
            good_min=0.55,
            good_max=None,
            weight=35,
            earned=_band_score(efficiency, 0.55, None, 35),
            note=(
                "Peak speed reached against the ideal Δv the propellant contained. "
                "Gravity and drag take 1.5–2 km/s of it on a launch to orbit; losing "
                "much more than half means the trajectory is fighting itself."
            ),
            recommendation=(
                None
                if efficiency >= 0.55
                else "Most of the propellant is going into gravity loss. Raise liftoff "
                "thrust-to-weight, or pitch over earlier so the velocity vector turns "
                "horizontal sooner."
            ),
        )
    )

    gravity_loss = summary.gravity_loss_ms
    criteria.append(
        Criterion(
            id="gravity_loss",
            label="Gravity loss",
            measured=gravity_loss,
            unit="m/s",
            good_min=None,
            good_max=2000,
            weight=25,
            earned=_band_score(gravity_loss, None, 2000, 25),
            note=(
                "Velocity spent holding the vehicle up rather than accelerating it "
                "downrange. A well-flown ascent keeps it near 1.2–1.5 km/s."
            ),
            recommendation=(
                None
                if gravity_loss <= 2000
                else "Spend less time going straight up: raise thrust-to-weight or "
                "start the pitchover lower."
            ),
        )
    )

    propulsion_failures = [f for f in failures if f.subsystem.value == "propulsion"]
    score = _criteria_score(criteria)
    if propulsion_failures:
        # A propulsion failure is not a deduction against a criterion; it is a
        # statement that the subsystem did not work.
        score *= 0.4

    return _category(
        "propulsion",
        criteria,
        _summarise(
            score,
            good="Thrust and impulse are well matched to the vehicle.",
            fair="The propulsion works, but the trajectory is wasting some of it.",
            poor="Propulsion is the limiting factor on this design.",
        ),
        score,
    )


def _score_stability(vehicle, telemetry, failures) -> CategoryScore:
    """Static margin, and how much the vehicle was actually disturbed."""
    criteria: List[Criterion] = []

    wet = vehicle.stability_margin_wet_cal
    dry = vehicle.stability_margin_dry_cal

    criteria.append(
        Criterion(
            id="static_margin_wet",
            label="Static margin, fuelled",
            measured=wet,
            unit="cal",
            good_min=1.0,
            good_max=2.0,
            weight=35,
            earned=_band_score(wet, 1.0, 2.0, 35),
            note=(
                "Centre of pressure behind centre of gravity, in body diameters. Below "
                "1 a gust upsets it; above 2 it weathercocks hard into any crosswind."
            ),
            recommendation=(
                None
                if 1.0 <= wet <= 2.0
                else (
                    "Increase fin area or move mass forward — the centre of pressure "
                    "is ahead of the centre of gravity and the vehicle will tumble."
                    if wet < 0
                    else "Increase fin area or add nose ballast to reach 1 caliber."
                    if wet < 1.0
                    else "Reduce fin area. This is over-stable and will turn into the "
                    "wind rather than flying where it was aimed."
                )
            ),
        )
    )

    criteria.append(
        Criterion(
            id="static_margin_dry",
            label="Static margin, empty",
            measured=dry,
            unit="cal",
            good_min=1.0,
            good_max=2.5,
            weight=30,
            earned=_band_score(dry, 1.0, 2.5, 30),
            note=(
                "Propellant burns off from ahead of the engine, so the centre of "
                "gravity moves aft and the margin shrinks through the flight. This is "
                "usually the harder case."
            ),
            recommendation=(
                None
                if dry >= 1.0
                else "The vehicle becomes unstable as it empties. Move dry mass "
                "forward, or increase fin area."
            ),
        )
    )

    max_aoa = max(
        (math.degrees(p.angle_of_attack_rad) for p in telemetry if p.engine_on), default=0.0
    )
    criteria.append(
        Criterion(
            id="angle_of_attack",
            label="Peak angle of attack, powered",
            measured=max_aoa,
            unit="°",
            good_min=None,
            good_max=12,
            weight=35,
            earned=_band_score(max_aoa, None, 12, 35),
            note=(
                "How far the vehicle flew off its own axis while under power. A "
                "well-flown ascent keeps this near zero — that is the whole point of a "
                "gravity turn."
            ),
            recommendation=(
                None
                if max_aoa <= 12
                else "Soften the pitch program, or wait for calmer wind. A large angle "
                "of attack at high dynamic pressure is a bending load."
            ),
        )
    )

    score = _criteria_score(criteria)
    if any(f.subsystem.value == "aerodynamics" for f in failures):
        score *= 0.5

    return _category(
        "stability",
        criteria,
        _summarise(
            score,
            good="The vehicle flew where it was pointed.",
            fair="Stable, but with less margin than is comfortable.",
            poor="This vehicle is not reliably controllable.",
        ),
        score,
    )


def _score_aerodynamics(vehicle, telemetry, summary) -> CategoryScore:
    """Drag, dynamic pressure and where max-Q landed."""
    criteria: List[Criterion] = []

    criteria.append(
        Criterion(
            id="drag_coefficient",
            label="Drag coefficient",
            measured=vehicle.drag_coefficient,
            unit="",
            good_min=None,
            good_max=0.55,
            weight=25,
            earned=_band_score(vehicle.drag_coefficient, None, 0.55, 25),
            note=(
                "Subsonic Cd for the assembled vehicle. A slender vehicle with a "
                "low-drag nose sits near 0.3; a blunt one with large fins climbs past 0.6."
            ),
            recommendation=(
                None
                if vehicle.drag_coefficient <= 0.55
                else "Choose a lower-drag nose profile, or reduce fin area."
            ),
        )
    )

    drag_loss = summary.drag_loss_ms
    criteria.append(
        Criterion(
            id="drag_loss",
            label="Drag loss",
            measured=drag_loss,
            unit="m/s",
            good_min=None,
            good_max=400,
            weight=35,
            earned=_band_score(drag_loss, None, 400, 35),
            note=(
                "Velocity lost to the atmosphere. Real launch vehicles pay 100–300 m/s; "
                "far more than that means too much frontal area, or too much speed too low."
            ),
            recommendation=(
                None
                if drag_loss <= 400
                else "Reduce frontal area, or lower the liftoff thrust-to-weight so "
                "the vehicle is slower through the dense air."
            ),
        )
    )

    max_q_altitude = summary.max_q_altitude_m
    criteria.append(
        Criterion(
            id="max_q_altitude",
            label="Max-Q altitude",
            measured=max_q_altitude,
            unit="m",
            good_min=8_000,
            good_max=16_000,
            weight=40,
            earned=_band_score(max_q_altitude, 8_000, 16_000, 40),
            note=(
                "Real launch vehicles peak between 8 and 16 km. Much lower means the "
                "vehicle is accelerating hard in dense air; much higher means it is "
                "climbing slowly and paying for it in gravity loss."
            ),
            recommendation=(
                None
                if 8_000 <= max_q_altitude <= 16_000
                else "Adjust the liftoff thrust-to-weight to move max-Q into the "
                "8–16 km band."
            ),
        )
    )

    score = _criteria_score(criteria)
    return _category(
        "aerodynamics",
        criteria,
        _summarise(
            score,
            good="Clean through the atmosphere.",
            fair="The atmosphere is costing more than it should.",
            poor="Aerodynamics are a major drag on this design, literally.",
        ),
    )


def _score_structural(vehicle, summary, failures) -> CategoryScore:
    """Loads carried against declared limits."""
    criteria: List[Criterion] = []

    max_q = summary.max_dynamic_pressure_Pa
    limit_q = vehicle.max_dynamic_pressure_Pa
    utilisation = max_q / limit_q if limit_q > 0 else 0.0
    criteria.append(
        Criterion(
            id="dynamic_pressure_margin",
            label="Dynamic pressure against limit",
            measured=utilisation,
            unit="",
            good_min=None,
            good_max=0.8,
            weight=40,
            earned=_band_score(utilisation, None, 0.8, 40),
            note=(
                f"Peak dynamic pressure was {max_q / 1000:.1f} kPa against a "
                f"{limit_q / 1000:.0f} kPa limit. Flying above 80% of a structural "
                "limit leaves nothing for a gust."
            ),
            recommendation=(
                None
                if utilisation <= 0.8
                else "Throttle back through max-Q, or reduce liftoff thrust-to-weight."
            ),
        )
    )

    max_g = summary.max_acceleration_g
    criteria.append(
        Criterion(
            id="peak_acceleration",
            label="Peak acceleration",
            measured=max_g,
            unit="g",
            good_min=None,
            good_max=6.0,
            weight=30,
            earned=_band_score(max_g, None, 6.0, 30),
            note=(
                "Acceleration climbs through a burn as propellant is consumed. Crewed "
                "vehicles limit it to about 3 g; uncrewed ones to whatever the payload "
                "will take."
            ),
            recommendation=(
                None
                if max_g <= 6.0
                else "Throttle down near the end of the burn, when the vehicle is "
                "lightest and acceleration is highest."
            ),
        )
    )

    q_alpha = summary.max_q_alpha_Padeg
    criteria.append(
        Criterion(
            id="q_alpha",
            label="Peak q·α",
            measured=q_alpha,
            unit="Pa·°",
            good_min=None,
            good_max=250_000,
            weight=30,
            earned=_band_score(q_alpha, None, 250_000, 30),
            note=(
                "Dynamic pressure times angle of attack: the lateral bending moment on "
                "a long thin tube. This is the number a launch is scrubbed for on a "
                "cloudless day."
            ),
            recommendation=(
                None
                if q_alpha <= 250_000
                else "Wait for lighter wind, or soften the pitch program so the vehicle "
                "flies closer to its own velocity vector."
            ),
        )
    )

    score = _criteria_score(criteria)
    if any(f.subsystem.value == "structure" for f in failures):
        # The airframe came apart. Whatever the margins said before that, they
        # were wrong.
        score = min(score, 20.0)

    return _category(
        "structural",
        criteria,
        _summarise(
            score,
            good="Comfortable margin against every load limit.",
            fair="Within limits, but without much room left.",
            poor="This vehicle flew outside what its structure could carry.",
        ),
        score,
    )


def _score_environment(mission, summary, failures) -> CategoryScore:
    """Whether the conditions were flyable, and whether they were used."""
    criteria: List[Criterion] = []
    environment = mission.environment

    wind = environment.wind_speed_ms
    criteria.append(
        Criterion(
            id="ground_wind",
            label="Ground wind at launch",
            measured=wind,
            unit="m/s",
            good_min=None,
            good_max=15.0,
            weight=35,
            earned=_band_score(wind, None, 15.0, 35),
            note=(
                "Wind at the pad pushes the vehicle sideways while it is slow and its "
                "control authority is weakest."
            ),
            recommendation=None if wind <= 15.0 else "Hold for lighter wind.",
        )
    )

    deviation = summary.max_lateral_deviation_m
    criteria.append(
        Criterion(
            id="lateral_deviation",
            label="Lateral deviation from track",
            measured=deviation,
            unit="m",
            good_min=None,
            good_max=5_000,
            weight=35,
            earned=_band_score(deviation, None, 5_000, 35),
            note=(
                "How far crosswind carried the vehicle off the plane it was aimed "
                "along. Real range safety corridors are narrower than most people expect."
            ),
            recommendation=(
                None
                if deviation <= 5_000
                else "Launch on a calmer day, or aim into the crosswind to compensate."
            ),
        )
    )

    # Using measured weather is itself worth marks: a flight run on a standard
    # day is a less meaningful result than one run on real conditions, and the
    # report should say so rather than quietly treating them as equivalent.
    used_live = environment.source not in ("standard_day", "")
    criteria.append(
        Criterion(
            id="live_conditions",
            label="Measured conditions used",
            measured=1.0 if used_live else 0.0,
            unit="",
            good_min=1.0,
            good_max=None,
            weight=30,
            earned=30.0 if used_live else 0.0,
            note=(
                f"Flown on observed conditions from {environment.source}."
                if used_live
                else "Flown on a standard day. The result is valid but idealised: real "
                "air is rarely 15 °C, 1013 hPa and still."
            ),
            recommendation=(
                None
                if used_live
                else "Pull the live weather for your launch site and fly it again — "
                "surface density alone varies by nearly 19% across real conditions."
            ),
        )
    )

    score = _criteria_score(criteria)
    return _category(
        "environment",
        criteria,
        _summarise(
            score,
            good="Flown in conditions that were genuinely flyable.",
            fair="The conditions were marginal.",
            poor="The environment, not the vehicle, decided this flight.",
        ),
    )


def _score_trajectory(mission, result, summary) -> CategoryScore:
    """Did it go where it was aimed."""
    criteria: List[Criterion] = []

    target_m = mission.target.target_altitude_km * 1000.0
    reached = summary.max_altitude_m
    ratio = reached / target_m if target_m > 0 else 0.0
    criteria.append(
        Criterion(
            id="altitude_vs_target",
            label="Apogee against target",
            measured=ratio,
            unit="",
            good_min=0.95,
            good_max=None,
            weight=45,
            earned=_band_score(ratio, 0.95, None, 45),
            note=(
                f"Reached {reached / 1000:.1f} km against a "
                f"{target_m / 1000:.0f} km target."
            ),
            recommendation=(
                None
                if ratio >= 0.95
                else "More Δv is needed: add propellant, improve specific impulse, or "
                "reduce payload."
            ),
        )
    )

    final = result.telemetry[-1] if result.telemetry else None
    periapsis = final.periapsis_altitude_m if final else 0.0
    is_orbital = mission.target.type.value in ("leo", "meo", "geo", "escape")

    if is_orbital:
        criteria.append(
            Criterion(
                id="periapsis",
                label="Final periapsis",
                measured=periapsis,
                unit="m",
                good_min=100_000,
                good_max=None,
                weight=55,
                earned=_band_score(periapsis, 100_000, None, 55),
                note=(
                    "Altitude alone never produces an orbit. Periapsis — the low point "
                    "of the resulting ellipse — has to be above the atmosphere, or the "
                    "trajectory intersects the planet."
                ),
                recommendation=(
                    None
                    if periapsis >= 100_000
                    else "The trajectory is ballistic, not orbital. More of the burn "
                    "needs to go into horizontal velocity: pitch over earlier."
                ),
            )
        )
    else:
        criteria.append(
            Criterion(
                id="downrange",
                label="Downrange distance",
                measured=summary.max_downrange_m,
                unit="m",
                good_min=None,
                good_max=400_000,
                weight=55,
                earned=_band_score(summary.max_downrange_m, None, 400_000, 55),
                note=(
                    "How far downrange a suborbital profile travelled. A vertical "
                    "sounding flight should land near where it started."
                ),
                recommendation=None,
            )
        )

    score = _criteria_score(criteria)
    return _category(
        "trajectory",
        criteria,
        _summarise(
            score,
            good="Flew the profile it was set.",
            fair="Close, but short of the target.",
            poor="The trajectory did not achieve what the mission asked of it.",
        ),
    )


def _score_recovery(result, summary, failures) -> CategoryScore:
    """Whether it came back, and whether that was survivable."""
    recovery_failures = [f for f in failures if f.subsystem.value == "recovery"]
    impact = summary.impact_speed_ms

    if impact is None:
        # The vehicle did not return to the surface — it is in orbit, escaped,
        # or was lost. Recovery is not applicable rather than zero, and the
        # difference matters: scoring a successful orbital insertion zero for
        # recovery would be nonsense.
        return CategoryScore(
            id="recovery",
            label="Recovery",
            score=0.0,
            criteria=[],
            summary="No recovery attempted — the vehicle did not return to the surface.",
            not_applicable=True,
        )

    criteria = [
        Criterion(
            id="impact_speed",
            label="Impact speed",
            measured=impact,
            unit="m/s",
            good_min=None,
            good_max=10.0,
            weight=70,
            earned=_band_score(impact, None, 10.0, 70, tolerance=2.0),
            note=(
                "Touchdown speed. Under about 10 m/s most hardware survives; a "
                "ballistic return at hundreds of metres per second does not."
            ),
            recommendation=(
                None
                if impact <= 10.0
                else "Fit a parachute, or a larger canopy. Terminal velocity falls with "
                "the square root of area, so halving the impact speed needs four times "
                "the chute."
            ),
        ),
        Criterion(
            id="recovery_failures",
            label="Recovery system failures",
            measured=float(len(recovery_failures)),
            unit="",
            good_min=None,
            good_max=0,
            weight=30,
            earned=30.0 if not recovery_failures else 0.0,
            note=(
                "A parachute deployed outside its rated speed does not save the "
                "vehicle; it tears off."
                if recovery_failures
                else "Recovery sequence completed without a failure."
            ),
            recommendation=(
                "Deploy the main chute lower, where the vehicle is slower and the "
                "opening shock is survivable."
                if recovery_failures
                else None
            ),
        ),
    ]

    score = _criteria_score(criteria)
    return _category(
        "recovery",
        criteria,
        _summarise(
            score,
            good="Came back in one piece.",
            fair="Recovered, but harder than it should have been.",
            poor="The vehicle did not survive its return.",
        ),
    )


def _score_mission(result, mission, summary) -> CategoryScore:
    """The outcome, and how cleanly it was reached."""
    criteria = [
        Criterion(
            id="outcome",
            label="Mission outcome",
            measured=1.0 if result.success else 0.0,
            unit="",
            good_min=1.0,
            good_max=None,
            weight=50,
            earned=50.0 if result.success else 0.0,
            note=f"Ended as {result.outcome.value}: {result.termination_reason}",
            recommendation=None if result.success else "See the failure analysis below.",
        ),
        Criterion(
            id="fatal_failures",
            label="Fatal failures",
            measured=float(
                sum(1 for f in result.failures if f.severity == EventSeverity.FATAL)
            ),
            unit="",
            good_min=None,
            good_max=0,
            weight=30,
            earned=(
                30.0
                if not any(f.severity == EventSeverity.FATAL for f in result.failures)
                else 0.0
            ),
            note="A fatal failure ends the mission at the moment it occurs.",
            recommendation=None,
        ),
        Criterion(
            id="warnings",
            label="Warnings raised",
            measured=float(
                sum(1 for f in result.failures if f.severity == EventSeverity.WARNING)
            ),
            unit="",
            good_min=None,
            good_max=2,
            weight=20,
            earned=_band_score(
                float(sum(1 for f in result.failures if f.severity == EventSeverity.WARNING)),
                None,
                2,
                20,
                tolerance=2.0,
            ),
            note=(
                "Warnings are conditions the vehicle survived. Several of them usually "
                "means the design is operating near several limits at once."
            ),
            recommendation=None,
        ),
    ]

    score = _criteria_score(criteria)
    return _category(
        "mission",
        criteria,
        _summarise(
            score,
            good="Mission accomplished, cleanly.",
            fair="The objective was met, with problems along the way.",
            poor="The mission was not accomplished.",
        ),
    )


# ──────────────────────────────────────────────────────────────
# Narration
# ──────────────────────────────────────────────────────────────


def _summarise(score: float, *, good: str, fair: str, poor: str) -> str:
    if score >= 80:
        return good
    if score >= 55:
        return fair
    return poor


def _narrate(categories: Sequence[CategoryScore]):
    """
    Turn the scored criteria into what a reviewer would actually say.

    Recommendations are ordered by how many points each failing criterion cost,
    so the first suggestion is the one that recovers the most — which is almost
    never the one a beginner would try first.
    """
    strengths: List[str] = []
    weaknesses: List[str] = []
    scored: List[tuple] = []

    for category in categories:
        if category.not_applicable:
            continue
        if category.score >= 85:
            strengths.append(f"{category.label}: {category.summary}")
        for criterion in category.criteria:
            deficit = criterion.weight - criterion.earned
            if deficit <= 0.01:
                continue
            scored.append((deficit, category, criterion))

    scored.sort(key=lambda item: item[0], reverse=True)

    for deficit, category, criterion in scored[:5]:
        weaknesses.append(
            "{0} — {1} is {2:.2f} {3}, against a target of {4}. Cost {5:.0f} points.".format(
                category.label,
                criterion.label,
                criterion.measured,
                criterion.unit or "",
                _describe_band(criterion),
                deficit,
            ).replace("  ", " ")
        )

    recommendations = []
    seen = set()
    for _, _, criterion in scored:
        if criterion.recommendation and criterion.recommendation not in seen:
            recommendations.append(criterion.recommendation)
            seen.add(criterion.recommendation)
        if len(recommendations) >= 5:
            break

    if not strengths:
        best = max(
            (c for c in categories if not c.not_applicable),
            key=lambda c: c.score,
            default=None,
        )
        if best:
            strengths.append(
                f"{best.label} is the strongest part of this design at "
                f"{best.score:.0f}/100."
            )

    return strengths, weaknesses, recommendations


def _describe_band(criterion: Criterion) -> str:
    if criterion.good_min is not None and criterion.good_max is not None:
        return f"{criterion.good_min:g}–{criterion.good_max:g}"
    if criterion.good_min is not None:
        return f"at least {criterion.good_min:g}"
    if criterion.good_max is not None:
        return f"no more than {criterion.good_max:g}"
    return "any value"
