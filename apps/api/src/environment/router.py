"""Environment routes: live weather for a launch site."""

from typing import Optional

from fastapi import APIRouter, Query

from src.core.envelope import success_envelope
from src.environment import service
from src.schemas.common import ErrorResponse

router = APIRouter()


@router.get("/weather", summary="Conditions at every launch site")
async def all_weather() -> dict:
    return success_envelope(await service.all_site_weather())


@router.get(
    "/weather/{site_id}",
    responses={404: {"model": ErrorResponse, "description": "No such launch site"}},
    summary="Conditions at one launch site",
)
async def site_weather(
    site_id: str,
    refresh: bool = Query(False, description="Bypass the ten-minute cache"),
) -> dict:
    """Current conditions, the launch commit verdict, and the simulation inputs.

    Never fails because a weather provider is unreachable: it falls back to a
    standard day with `is_live` false and a stated reason. A simulator that
    cannot run because an external API is down would be a worse product than one
    that runs on clearly-labelled default conditions.
    """
    return success_envelope(await service.site_weather(site_id, refresh=refresh))


@router.get(
    "/simulation-config/{site_id}",
    responses={404: {"model": ErrorResponse, "description": "No such launch site"}},
    summary="Just the simulation inputs for a site",
)
async def simulation_config(site_id: str) -> dict:
    """The measured conditions, reduced to the fields `EnvironmentConfig` accepts.

    The same object the launch page renders from, with nothing added and nothing
    retyped — so what the user reads and what the trajectory is flown against
    cannot drift apart.
    """
    weather = await service.site_weather(site_id)
    return success_envelope(weather["simulation_environment"])


@router.get("/wind-profile", summary="The wind profile a surface observation implies")
async def wind_profile(
    surface_speed_ms: float = Query(..., ge=0, le=80),
    direction_deg: float = Query(270.0, ge=0, le=360),
    latitude_deg: float = Query(28.6, ge=-90, le=90),
) -> dict:
    """Wind by altitude, from the same model the force calculation uses.

    The point it exists to make: a calm morning at the pad says very little
    about the wind at 11 km, which is roughly where max-Q happens.
    """
    return success_envelope(
        {
            "samples": service.wind_profile_preview(surface_speed_ms, direction_deg, latitude_deg),
            "note": (
                "Power-law surface layer to 2 km, a jet bump near the tropopause, still above "
                "25 km, with Ekman veer. An approximation: a real launch commit uses a balloon "
                "sounding taken hours before the window."
            ),
        }
    )


@router.get("/provider", summary="Which weather provider is configured")
async def provider() -> dict:
    return success_envelope({"provider": service.provider_name()})
