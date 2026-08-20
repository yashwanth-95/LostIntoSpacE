"""Simulation routes.

Public: running a simulation needs no token. Guest mode is a product
requirement — someone should be able to land on the site, build a rocket, and
fly it without creating an account. Saving the result is what requires one.

Nothing here is a write to the database, so there is no ownership check to
make. The cost controls that would otherwise be enforced by authentication
live in `schemas.simulation` (request limits) and `simulation.service`
(wall-clock timeout) instead.
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from src.core.engines import EngineUnavailableError, get_simulation
from src.core.envelope import success_envelope
from src.schemas.common import ErrorResponse, SuccessResponse
from src.schemas.simulation import SimulationLimits, SimulationMeta, SimulationRunRequest
from src.simulation.service import run_simulation

router = APIRouter()


def _result_envelope_model() -> Any:
    """The response model for a completed run.

    The engine's own ``SimResult`` is used directly rather than being mirrored
    into a second Pydantic model here. It is already a Pydantic contract, and
    duplicating it would create exactly the drift the repository audit flagged
    (four places defining overlapping shapes). Publishing the real one means
    the OpenAPI schema describes the actual simulation contract, and the
    frontend's TypeScript types can be generated from it.

    Falls back to an untyped envelope when the engine is not installed, so the
    app still starts and ``/health/engines`` can report why.
    """
    try:
        sim = get_simulation()
    except EngineUnavailableError:  # pragma: no cover - depends on the install
        return None

    class SimulationRunResponse(BaseModel):
        """`{"status": "success", "data": <SimResult>, "meta": {...}}`."""

        status: str = "success"
        data: sim.SimResult  # type: ignore[name-defined]
        meta: SimulationMeta

    return SimulationRunResponse


_RUN_RESPONSE_MODEL = _result_envelope_model()

_RUN_RESPONSES: dict = {
    400: {"model": ErrorResponse, "description": "The configuration is not valid"},
    503: {"model": ErrorResponse, "description": "The simulation engine is unavailable"},
    504: {"model": ErrorResponse, "description": "The run exceeded the time limit"},
}


@router.post(
    "/run",
    response_model=_RUN_RESPONSE_MODEL,
    responses=_RUN_RESPONSES,
    tags=["simulation"],
)
async def run(payload: SimulationRunRequest) -> dict:
    """Fly one mission and return its telemetry, events, failures, and summary.

    The response is a complete flight, not a stream. Live telemetry playback is
    the client's job: it already has every sample, timestamped, and replays them
    against its own clock. That keeps the simulation deterministic and
    reproducible, and avoids one request per rendered frame.
    """
    outcome = await run_simulation(payload.config)
    return success_envelope(outcome["result"], meta=outcome["meta"])


@router.get("/limits", response_model=SuccessResponse[SimulationLimits], tags=["simulation"])
async def limits() -> dict:
    """The server-side caps a run request must satisfy.

    Published so a client can validate a configuration before submitting it,
    rather than discovering the limits through 400s.
    """
    return success_envelope(SimulationLimits().model_dump(mode="json"))
