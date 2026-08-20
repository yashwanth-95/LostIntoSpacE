"""Launch-site environment routes. Public — weather is not per-user data."""

from fastapi import APIRouter, Query

from src.core.envelope import success_envelope
from src.environment.service import environment_config_for_site, observation_for_site
from src.schemas.common import ErrorResponse, SuccessResponse

router = APIRouter()

_RESPONSES: dict = {
    404: {"model": ErrorResponse, "description": "No such launch site"},
    503: {"model": ErrorResponse, "description": "Weather is unavailable"},
}


@router.get(
    "/weather/{site_id}", response_model=SuccessResponse[dict], responses=_RESPONSES
)
async def weather(
    site_id: str,
    refresh: bool = Query(
        default=False,
        description="Bypass the ten-minute cache. Providers update no faster than that.",
    ),
) -> dict:
    """
    Current conditions at a launch site, the launch commit assessment, and the
    same values in the shape the simulation consumes.

    `observation.is_live` is false when no provider could be reached; in that
    case `fallback_reason` says so and the values are US Standard Atmosphere
    for the site's elevation in still air. They are never presented as measured.
    """
    return success_envelope(await observation_for_site(site_id, force_refresh=refresh))


@router.get(
    "/simulation-config/{site_id}", response_model=SuccessResponse[dict], responses=_RESPONSES
)
async def simulation_config(site_id: str) -> dict:
    """Just the `EnvironmentConfig` block, for a client about to fly."""
    return success_envelope(await environment_config_for_site(site_id))
