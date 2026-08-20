"""Running simulations.

The API owns none of the physics. This module validates the client's request
against the engine's own contract, runs it, and shapes the result for
transport. If you find yourself computing a trajectory here, it belongs in
``simulation/`` instead.

Blocking, on purpose
--------------------
``run_simulation`` is CPU-bound and synchronous. A reference orbital ascent
takes roughly 0.4 s of wall clock, which is short enough that awaiting it in a
thread beats the complexity of a job queue for the first prototype. It runs in
a worker thread (never inline on the event loop) so one long flight cannot
stall every other request on the process.

When runs grow past a few seconds — higher-fidelity models, longer missions —
this is the seam that should become a task queue. The endpoint contract does
not change when it does.
"""

from __future__ import annotations

import time
from typing import Any

import anyio

from src.core.engines import EngineUnavailableError, get_simulation
from src.core.exceptions import AppError, BadRequestError
from src.schemas.simulation import MAX_TELEMETRY_POINTS

#: Wall-clock ceiling for one run. A configuration that survives the request
#: limits but still grinds (a pathological vehicle in a dense atmosphere at a
#: 1 ms step) gets cut off rather than occupying a worker indefinitely.
RUN_TIMEOUT_S = 30.0

ENGINE_NAME = "lostintospace-python-simulation"
ENGINE_VERSION = "1.0.0"


def _decimate(points: list[Any], limit: int = MAX_TELEMETRY_POINTS) -> tuple[list[Any], bool]:
    """
    Thin a telemetry series to at most ``limit`` samples.

    Takes every nth sample and always keeps the last one, so the series still
    ends where the flight ended — dropping the final sample would make a
    mission look like it stopped early. Events are never decimated; they are
    the sparse, meaningful record.
    """
    total = len(points)
    if total <= limit:
        return points, False

    stride = (total + limit - 1) // limit
    kept = points[::stride]
    if kept and points and kept[-1] is not points[-1]:
        kept.append(points[-1])
    return kept, True


async def run_simulation(config_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and fly one mission.

    Args:
        config_payload: A raw ``SimConfig`` object from the client. Already
            checked against the request limits in ``schemas.simulation``.

    Returns:
        ``{"result": <SimResult as dict>, "meta": {...}}``.

    Raises:
        BadRequestError: If the configuration does not satisfy the engine's
            contract. The validation detail is returned, since it describes the
            caller's own payload and leaks nothing about the server.
        AppError: 503 if the engine is unavailable, 504 if the run times out.
    """
    try:
        engine = get_simulation()
    except EngineUnavailableError as exc:
        raise AppError(
            503,
            "SIMULATION_ENGINE_UNAVAILABLE",
            "The simulation engine is not available on this server",
        ) from exc

    try:
        config = engine.SimConfig.model_validate(config_payload)
    except Exception as exc:  # pydantic ValidationError, and anything it wraps
        raise BadRequestError(
            "Invalid simulation configuration",
            details=_validation_details(exc),
        ) from exc

    started = time.perf_counter()
    try:
        with anyio.fail_after(RUN_TIMEOUT_S):
            result = await anyio.to_thread.run_sync(engine.run_simulation, config)
    except TimeoutError as exc:
        raise AppError(
            504,
            "SIMULATION_TIMEOUT",
            f"The simulation exceeded the {RUN_TIMEOUT_S:g}s limit. "
            "Try a shorter mission or a coarser timestep.",
        ) from exc
    compute_time_s = time.perf_counter() - started

    # Evaluation runs on the *undecimated* result. Scoring against a thinned
    # series would miss the peaks - max-Q, peak g, peak q-alpha - which are
    # exactly the samples the structural criteria are measured against.
    evaluation = engine.evaluate_mission(result, config.vehicle, config.mission).to_dict()

    payload = result.model_dump(mode="json")
    generated = len(payload["telemetry"])
    payload["telemetry"], decimated = _decimate(payload["telemetry"])

    return {
        "result": payload,
        "evaluation": evaluation,
        "meta": {
            "engine": ENGINE_NAME,
            "engine_version": ENGINE_VERSION,
            "compute_time_s": round(compute_time_s, 4),
            "telemetry_points_generated": generated,
            "telemetry_points_returned": len(payload["telemetry"]),
            "telemetry_decimated": decimated,
            "evaluated": True,
        },
    }


def _validation_details(exc: Exception) -> list[Any]:
    """Turn a pydantic ValidationError into JSON-safe envelope details.

    Falls back to the string form for anything that is not a ValidationError,
    and never includes the input value — a config can be large, and echoing it
    back doubles the payload for no benefit.
    """
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return [str(exc)]
    return [
        {"field": ".".join(str(p) for p in err.get("loc", ())), "message": err.get("msg", "")}
        for err in errors()
    ][:20]
