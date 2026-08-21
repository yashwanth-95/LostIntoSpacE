"""Turning what the user is currently doing into evidence the assistant can cite.

The complaint this module exists to answer is specific: asked "why is my rocket
unstable?", a general assistant returns a paragraph about centres of pressure.
Correct, and useless — the user has a *particular* rocket with a *particular*
static margin, and what they need is the number and what to change.

So the client sends a `WorkbenchContext` describing its current state, and this
module renders it into :class:`ContextItem` records — the same shape the
retrieval pipeline produces — which are passed to the assistant as
`extra_context`. The answer is then assembled from the user's own measurements
alongside retrieved knowledge, and both are cited.

## Trust

Everything here is *data*, never instruction. Free-text fields — a mission name,
a vehicle name, an objective — are user-authored and pass through
``sanitize_context_text``; a name that tries to reassign the model's role is
quarantined rather than fenced, because there is no legitimate reading of it.
Numeric fields are bounded by the request schema before they arrive.

## Freshness

These items describe the user's design and their simulation output, not the
world. They are marked ``may_present_as_live=False`` so nothing here can be
reported as a live scientific reading — a simulated apogee is not a measurement
of anything, and the assistant must not imply otherwise.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from contracts._time import utc_now
from contracts.ai import ContextItem
from contracts.provenance import FreshnessClass, SourceReference, SourceType

from ..safety.sanitize import sanitize_context_text
from .render import PROJECT_SOURCE, SIMULATION_SOURCE

__all__ = ["render_workbench_context", "WORKBENCH_SOURCE", "WEATHER_SOURCE"]

#: Provenance for the design the user is editing right now.
WORKBENCH_SOURCE = PROJECT_SOURCE

#: Provenance for a live weather observation used as a launch condition.
#:
#: `AGENCY_PUBLIC_API` rather than a science archive: a forecast service is a
#: real observation of the world, but it is not an archival measurement and must
#: not outrank one in conflict resolution.
WEATHER_SOURCE = SourceReference(
    source_name="launch_site_weather",
    source_type=SourceType.AGENCY_PUBLIC_API,
    attribution="Open-Meteo / OpenWeather, via the launch site environment service",
)


def _clean(text: Any, location: str) -> Optional[str]:
    """Sanitize a user-authored string, or drop it if it is hostile."""
    if not isinstance(text, str) or not text.strip():
        return None
    result = sanitize_context_text(text, location=location)
    if result.should_quarantine:
        return None
    return result.text


def _item(
    ref: str,
    canonical_id: str,
    title: str,
    lines: List[str],
    source: SourceReference,
    *,
    live: bool = False,
) -> Optional[ContextItem]:
    """One context item from already-formatted lines.

    Lines are built from bounded numeric fields and pre-sanitized strings, so
    they are not re-sanitized here — doing so would mangle the units and the
    comparisons in ``measured 0.94, threshold 1.00``.

    `live` is false for everything except a genuine weather observation. The
    user's design and their simulation output describe a model, not the world,
    and the safety layer relies on that distinction to stop a simulated apogee
    being reported as a measurement of anything.
    """
    body = "\n".join(line for line in lines if line)
    if not body.strip():
        return None
    return ContextItem(
        ref=ref,
        canonical_id=canonical_id,
        title=title,
        content=body,
        source=source,
        source_type=source.source_type,
        timestamp=None,
        retrieved_at=utc_now(),
        freshness_class=FreshnessClass.NEAR_REAL_TIME if live else FreshnessClass.STATIC,
        relevance=1.0,
        may_present_as_live=live,
    )


def _number(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if abs(number) >= 1e6:
        return "{0:.3g}".format(number)
    if abs(number) >= 1000:
        return "{0:,.0f}".format(number)
    return "{0:.{1}f}".format(number, digits)


def render_workbench_context(
    context: Dict[str, Any], start_index: int = 1
) -> List[ContextItem]:
    """
    Render the client's current state into citable context items.

    Args:
        context: The `context` object from an `/ai/ask` request. Every key is
            optional — the user may be anywhere in the product, and an absent
            section simply produces no item.
        start_index: First citation number to assign. Refs are rendered as
            ``S1``, ``S2``, … to match what the retrieval pipeline produces, so
            the citation validator sees one consistent namespace.

    Returns:
        Context items, in the order the assistant should prefer them: the
        vehicle first, then the mission, the conditions, the flight, and the
        evaluation. A question about a failure is nearly always answered from
        the last two, but the first two are what make the answer specific.
    """
    if not isinstance(context, dict):
        return []

    items: List[ContextItem] = []
    ref = start_index

    for build in (
        _vehicle_item,
        _mission_item,
        _weather_item,
        _simulation_item,
        _evaluation_item,
        _location_item,
    ):
        item = build(context, "S{0}".format(ref))
        if item is not None:
            items.append(item)
            ref += 1

    return items


def _vehicle_item(context: Dict[str, Any], ref: str) -> Optional[ContextItem]:
    rocket = context.get("rocket")
    if not isinstance(rocket, dict):
        return None

    name = _clean(rocket.get("name"), "rocket.name") or "the current design"
    margin_wet = rocket.get("stability_margin_wet_cal")
    margin_dry = rocket.get("stability_margin_dry_cal")
    twr = rocket.get("liftoff_twr")

    lines = [
        "Name: {0}".format(name),
        "Stages: {0}".format(rocket.get("stage_count", "unknown")),
        "Components: {0}".format(rocket.get("component_count", "unknown")),
        "Launch mass: {0} kg".format(_number(rocket.get("total_wet_mass_kg"), 1)),
        "Dry mass: {0} kg".format(_number(rocket.get("total_dry_mass_kg"), 1)),
        "Payload mass: {0} kg".format(_number(rocket.get("payload_mass_kg"), 1)),
        "Length: {0} m, diameter {1} m".format(
            _number(rocket.get("length_m"), 2), _number(rocket.get("diameter_m"), 3)
        ),
        "Ideal delta-v: {0} m/s".format(_number(rocket.get("total_delta_v_ms"), 0)),
        "Liftoff thrust-to-weight: {0}".format(_number(twr)),
        "Static margin, full: {0} calibers".format(_number(margin_wet)),
        "Static margin, empty: {0} calibers".format(_number(margin_dry)),
        "Centre of gravity (full): {0} m from the nose".format(_number(rocket.get("cg_wet_m"))),
        "Centre of pressure: {0} m from the nose".format(_number(rocket.get("cp_m"))),
    ]

    # The interpretation, stated as a fact about this design rather than left
    # for the model to infer. These are the two thresholds every beginner
    # design fails, and getting them wrong in an answer is worse than useless.
    if isinstance(twr, (int, float)):
        if twr < 1.0:
            lines.append(
                "NOTE: thrust-to-weight is below 1.0, so this vehicle cannot lift its own "
                "weight and will not leave the pad."
            )
        elif twr < 1.2:
            lines.append(
                "NOTE: thrust-to-weight is above 1.0 but below the usual 1.2-1.5 band, so "
                "the ascent will be slow and gravity losses large."
            )
    if isinstance(margin_wet, (int, float)):
        if margin_wet < 0:
            lines.append(
                "NOTE: centre of pressure is AHEAD of centre of gravity, so the vehicle is "
                "statically unstable and will tumble."
            )
        elif margin_wet < 1.0:
            lines.append(
                "NOTE: static margin is below 1 caliber, which is marginally stable — a gust "
                "will upset it and recovery will be slow."
            )
        elif margin_wet > 2.5:
            lines.append(
                "NOTE: static margin is above 2.5 calibers, which is over-stable — the vehicle "
                "will weathercock hard into any crosswind."
            )

    errors = rocket.get("validation_errors") or []
    warnings = rocket.get("validation_warnings") or []
    for label, entries in (("Validation error", errors), ("Validation warning", warnings)):
        for entry in entries[:6]:
            cleaned = _clean(entry, "rocket.validation")
            if cleaned:
                lines.append("{0}: {1}".format(label, cleaned))

    return _item(ref, "workbench:vehicle", "Current rocket design", lines, WORKBENCH_SOURCE)


def _mission_item(context: Dict[str, Any], ref: str) -> Optional[ContextItem]:
    mission = context.get("mission")
    if not isinstance(mission, dict):
        return None

    lines = [
        "Name: {0}".format(_clean(mission.get("name"), "mission.name") or "unnamed"),
        "Objective: {0}".format(_clean(mission.get("objective"), "mission.objective") or "unstated"),
        "Profile: {0}".format(mission.get("mission_type", "unknown")),
        "Target altitude: {0} km".format(_number(mission.get("target_altitude_km"), 0)),
        "Launch site: {0}".format(_clean(mission.get("launch_site"), "mission.site") or "unknown"),
        "Guidance program: {0}".format(mission.get("guidance_mode", "unknown")),
    ]
    return _item(ref, "workbench:mission", "Current mission configuration", lines, WORKBENCH_SOURCE)


def _weather_item(context: Dict[str, Any], ref: str) -> Optional[ContextItem]:
    weather = context.get("weather")
    if not isinstance(weather, dict):
        return None

    is_live = bool(weather.get("is_live"))
    lines = [
        "Site: {0}".format(_clean(weather.get("site"), "weather.site") or "unknown"),
        "Temperature: {0} °C".format(_number(weather.get("temperature_C"), 1)),
        "Pressure: {0} hPa".format(_number(weather.get("pressure_hPa"), 1)),
        "Wind: {0} m/s from {1}°".format(
            _number(weather.get("wind_speed_ms"), 1),
            _number(weather.get("wind_direction_deg"), 0),
        ),
        "Air density: {0} kg/m³".format(_number(weather.get("air_density_kgm3"), 4)),
        "Launch commit verdict: {0}".format(weather.get("suitability", "unknown")),
        "Observation is live: {0}".format("yes" if is_live else "no"),
    ]
    return _item(
        ref,
        "workbench:weather",
        "Launch site conditions",
        lines,
        WEATHER_SOURCE if is_live else WORKBENCH_SOURCE,
        # A real observation of a real place, unlike everything else here.
        live=is_live,
    )


def _simulation_item(context: Dict[str, Any], ref: str) -> Optional[ContextItem]:
    simulation = context.get("simulation")
    if not isinstance(simulation, dict):
        return None

    lines = [
        "Outcome: {0} ({1})".format(
            simulation.get("outcome", "unknown"),
            "succeeded" if simulation.get("success") else "did not succeed",
        ),
        "Final mission state: {0}".format(simulation.get("final_state", "unknown")),
        "Termination reason: {0}".format(
            _clean(simulation.get("termination_reason"), "sim.termination") or "unstated"
        ),
        "Flight time: {0} s".format(_number(simulation.get("flight_time_s"), 1)),
        "Maximum altitude: {0} m".format(_number(simulation.get("max_altitude_m"), 0)),
        "Maximum speed: {0} m/s".format(_number(simulation.get("max_speed_ms"), 0)),
        "Peak acceleration: {0} g".format(_number(simulation.get("max_acceleration_g"), 2)),
        "Maximum dynamic pressure: {0} Pa".format(
            _number(simulation.get("max_dynamic_pressure_Pa"), 0)
        ),
        "Peak q-alpha: {0} Pa·deg".format(_number(simulation.get("max_q_alpha_Padeg"), 0)),
        "Maximum lateral deviation: {0} m".format(
            _number(simulation.get("max_lateral_deviation_m"), 0)
        ),
        "Ideal delta-v: {0} m/s".format(_number(simulation.get("delta_v_ideal_ms"), 0)),
        "Realised delta-v: {0} m/s".format(_number(simulation.get("delta_v_achieved_ms"), 0)),
        "Gravity loss: {0} m/s".format(_number(simulation.get("gravity_loss_ms"), 0)),
        "Drag loss: {0} m/s".format(_number(simulation.get("drag_loss_ms"), 0)),
    ]

    failures = simulation.get("failures") or []
    if failures:
        lines.append("")
        lines.append("Failures recorded, with the measurement that triggered each:")
        for failure in failures[:8]:
            if not isinstance(failure, dict):
                continue
            lines.append(
                "  - T+{0} s, {1} ({2}, {3}): measured {4} {6}, threshold {5} {6}. "
                "Recommended fix: {7}".format(
                    _number(failure.get("t"), 1),
                    _clean(failure.get("failure_mode"), "sim.failure") or "unnamed failure",
                    failure.get("subsystem", "unknown subsystem"),
                    failure.get("severity", "unknown severity"),
                    _number(failure.get("measured_value"), 2),
                    _number(failure.get("threshold_value"), 2),
                    failure.get("unit", ""),
                    _clean(failure.get("recommended_fix"), "sim.fix") or "not stated",
                )
            )
    else:
        lines.append("")
        lines.append("No failures were recorded during this flight.")

    return _item(ref, "workbench:simulation", "Most recent flight result", lines, SIMULATION_SOURCE)


def _evaluation_item(context: Dict[str, Any], ref: str) -> Optional[ContextItem]:
    evaluation = context.get("evaluation")
    if not isinstance(evaluation, dict):
        return None

    lines = [
        "Overall score: {0}/100".format(evaluation.get("overall_score", "unknown")),
    ]

    categories = evaluation.get("categories") or []
    if categories:
        lines.append("Category scores:")
        for category in categories[:12]:
            if not isinstance(category, dict):
                continue
            lines.append(
                "  - {0}: {1}/100".format(
                    _clean(category.get("label"), "eval.label") or category.get("id", "?"),
                    category.get("score", "?"),
                )
            )

    weaknesses = evaluation.get("weaknesses") or []
    if weaknesses:
        lines.append("")
        lines.append("What cost the most points:")
        for weakness in weaknesses[:6]:
            cleaned = _clean(weakness, "eval.weakness")
            if cleaned:
                lines.append("  - {0}".format(cleaned))

    return _item(ref, "workbench:evaluation", "Mission evaluation", lines, SIMULATION_SOURCE)


def _location_item(context: Dict[str, Any], ref: str) -> Optional[ContextItem]:
    """Where in the product the user is, so an ambiguous question can be resolved.

    "Why is this too small?" means different things on the builder and on an
    object page. This item is deliberately thin — it disambiguates, it does not
    answer.
    """
    page = _clean(context.get("page"), "context.page")
    subject_keys = ("object_id", "topic_slug", "experiment_id", "mission_id")
    subjects = [
        (key, _clean(context.get(key), "context." + key))
        for key in subject_keys
        if context.get(key)
    ]

    if not page and not subjects:
        return None

    lines: List[str] = []
    if page:
        lines.append("Current page: {0}".format(page))
    for key, value in subjects:
        if value:
            lines.append("Viewing {0}: {1}".format(key.replace("_", " "), value))

    return _item(ref, "workbench:location", "Current location in the app", lines, WORKBENCH_SOURCE)
