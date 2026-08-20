"""Top-level /api/v1 router.

Mount order matters where paths overlap: routers with literal segments that
could be mistaken for a path parameter (e.g. `/lessons/categories` vs
`/lessons/{identifier}`) declare the literal route first inside their own
module.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.router import router as conversations_router
from src.auth.router import router as auth_router
from src.core.config import get_settings
from src.core.database import get_db
from src.core.engines import engine_status
from src.core.envelope import success_envelope
from src.core.exceptions import AppError
from src.learning.router import lessons_router, progress_router
from src.missions.router import router as missions_router
from src.projects.router import router as projects_router
from src.schemas.common import (
    ErrorResponse,
    HealthStatus,
    ReadinessStatus,
    SuccessResponse,
)
from src.schemas.simulation import EngineStatusReport
from src.simulation.router import router as simulation_router
from src.space_data.router import router as space_objects_router
from src.users.router import router as users_router
from src.vehicles.router import component_router
from src.vehicles.router import router as vehicles_router

settings = get_settings()
api_router = APIRouter(prefix=settings.api_v1_prefix)

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(projects_router, prefix="/projects", tags=["projects"])
api_router.include_router(missions_router, prefix="/missions", tags=["missions"])
api_router.include_router(vehicles_router, prefix="/vehicles", tags=["vehicles"])
api_router.include_router(component_router, prefix="/components", tags=["vehicles"])
api_router.include_router(lessons_router, prefix="/lessons", tags=["learning"])
api_router.include_router(progress_router, prefix="/learning/progress", tags=["learning"])
api_router.include_router(space_objects_router, prefix="/space-objects", tags=["space-data"])
api_router.include_router(simulation_router, prefix="/simulations", tags=["simulation"])
api_router.include_router(conversations_router, prefix="/conversations", tags=["ai"])
# docs/api/API.md publishes the conversation endpoints under /ai as well.
# Mounting the same router twice keeps both documented paths working rather
# than forcing P1/P4 to pick one - no duplicated logic, just two prefixes.
api_router.include_router(conversations_router, prefix="/ai/conversations", tags=["ai"])


@api_router.get("/health", tags=["health"], response_model=SuccessResponse[HealthStatus])
async def health_check() -> dict:
    """Liveness only - deliberately does NOT touch the database.

    A health check that queries PostgreSQL turns a database blip into a
    "service down" signal and, during the demo, would fail before the seed
    data is loaded. Readiness (can I reach the DB?) is a separate concern; see
    /health/ready.
    """
    return success_envelope({"state": "ok", "service": "lostintospace-api", "version": "0.1.0"})


@api_router.get(
    "/health/engines",
    tags=["health"],
    response_model=SuccessResponse[EngineStatusReport],
)
async def engines_check() -> dict:
    """Which compute engines this process can actually reach.

    The simulation, search, and AI engines live in sibling trees rather than
    installed packages, so an incomplete install shows up as a missing feature
    at request time rather than at startup. This endpoint makes that visible
    before a user hits it. Always 200: it reports failures as data, because it
    is the endpoint you check when something is already wrong.
    """
    return success_envelope(engine_status())


@api_router.get(
    "/health/ready",
    tags=["health"],
    response_model=SuccessResponse[ReadinessStatus],
    responses={503: {"model": ErrorResponse, "description": "Database is not reachable"}},
)
async def readiness_check(session: AsyncSession = Depends(get_db)) -> dict:
    """Readiness: can the API actually reach PostgreSQL?

    Separate from /health on purpose - this is the one to check before a demo,
    and the one that legitimately fails when the database is down. Returns 503
    rather than 500 so the failure reads as "not ready yet" rather than "bug".
    """
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any driver error means "not ready"
        # The exception text can carry the connection string; never echo it.
        raise AppError(503, "DATABASE_UNAVAILABLE", "Database is not reachable") from exc
    return success_envelope({"state": "ready", "database": "reachable"})
