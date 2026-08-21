"""Environment routes: live weather for a launch site.

Response models are resolved at import from `data.environment`, so the OpenAPI
schema carries the real observation and suitability shapes rather than an
untyped object — the frontend builds against that schema, and "returns a dict"
is not a contract.
"""

from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.core.engines import ensure_engine_paths
from src.core.envelope import success_envelope
from src.environment import service
from src.schemas.common import ErrorResponse, SuccessResponse

router = APIRouter()


def _environment_models() -> dict:
    """Envelope models for the weather responses, or `{}` if unavailable."""
    try:
        ensure_engine_paths()
        from data.catalog.models import LaunchSiteRecord
        from data.environment.models import LaunchSuitability, WeatherObservation
    except ImportError:  # pragma: no cover - depends on the install
        return {}

    class SimulationEnvironment(BaseModel):
        """Exactly the fields the simulation's `EnvironmentConfig` accepts."""

        temperature_K: float
        pressure_Pa: float
        wind_speed_ms: float
        wind_direction_deg: float
        relative_humidity: float
        jet_wind_speed_ms: float
        source: str
        observed_at: Optional[str] = None

    class SiteWeather(BaseModel):
        """Conditions, the launch verdict, and the simulation inputs together.

        One object rather than three endpoints, so what the launch page shows
        and what the trajectory is flown against cannot come from different
        reads and drift apart.
        """

        site: LaunchSiteRecord
        observation: WeatherObservation
        suitability: LaunchSuitability
        simulation_environment: SimulationEnvironment
        #: Today's density against a standard day at this elevation, per cent.
        density_vs_standard_pct: float

    class WindSample(BaseModel):
        altitude_m: float
        speed_ms: float
        direction_deg: float

    class WindProfile(BaseModel):
        samples: List[WindSample]
        note: str

    class ProviderInfo(BaseModel):
        provider: str

    return {
        "weather": SuccessResponse[SiteWeather],
        "all_weather": SuccessResponse[List[SiteWeather]],
        "sim_config": SuccessResponse[SimulationEnvironment],
        "wind_profile": SuccessResponse[WindProfile],
        "provider": SuccessResponse[ProviderInfo],
    }


_MODELS = _environment_models()


@router.get("/weather", summary="Conditions at every launch site", response_model=_MODELS.get("all_weather"))
async def all_weather() -> dict:
    return success_envelope(await service.all_site_weather())


@router.get(
    "/weather/{site_id}",
    response_model=_MODELS.get("weather"),
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
    response_model=_MODELS.get("sim_config"),
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


@router.get("/wind-profile", summary="The wind profile a surface observation implies", response_model=_MODELS.get("wind_profile"))
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


@router.get("/provider", summary="Which weather provider is configured", response_model=_MODELS.get("provider"))
async def provider() -> dict:
    return success_envelope({"provider": service.provider_name()})
