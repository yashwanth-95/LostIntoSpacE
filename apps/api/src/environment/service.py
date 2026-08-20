"""Live launch-site conditions.

Wraps the weather providers in ``data/environment`` and adds the piece the
simulation actually consumes: an ``EnvironmentConfig`` built from the
observation, so a user can fetch real weather for Kennedy and fly through it
without any value being retyped in between.

That translation is the whole point of this module. A weather panel that shows
18 m/s of wind next to a simulation that flies in still air is a decoration,
and this product was told not to build one.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from src.catalog.service import launch_site
from src.core.engines import EngineUnavailableError, get_environment
from src.core.exceptions import AppError

logger = logging.getLogger("api.environment")

__all__ = ["observation_for_site", "environment_config_for_site", "weather_service"]


def _unavailable(exc: Exception) -> AppError:
    return AppError(503, "ENVIRONMENT_UNAVAILABLE", "Launch-site weather is not available")


@lru_cache(maxsize=1)
def _environment() -> Any:
    try:
        return get_environment()
    except EngineUnavailableError as exc:
        raise _unavailable(exc) from exc


@lru_cache(maxsize=1)
def weather_service() -> Any:
    """One service per process, so its cache and its HTTP client are shared."""
    return _environment().WeatherService()


async def observation_for_site(site_id: str, *, force_refresh: bool = False) -> dict[str, Any]:
    """
    Current conditions at a launch site, with the go/no-go assessment.

    Never raises for a provider outage: the service falls back to a clearly
    labelled standard day, and `is_live` says which happened. A simulator that
    cannot run because a weather API is down would be a worse product than one
    that runs on a stated standard day.
    """
    site = launch_site(site_id)
    environment = _environment()
    service = weather_service()

    observation = await service.observation(
        site_id=site["id"],
        latitude_deg=site["latitude_deg"],
        longitude_deg=site["longitude_deg"],
        elevation_m=site["elevation_m"],
        force_refresh=force_refresh,
    )
    suitability = environment.assess_launch_conditions(observation)

    return {
        "site": {
            "id": site["id"],
            "name": site["name"],
            "short_name": site["short_name"],
            "country": site["country"],
            "operator": site["operator"],
            "latitude_deg": site["latitude_deg"],
            "longitude_deg": site["longitude_deg"],
            "elevation_m": site["elevation_m"],
        },
        "observation": observation.model_dump(mode="json"),
        "suitability": suitability.model_dump(mode="json"),
        "simulation_environment": _to_environment_config(observation),
    }


def _to_environment_config(observation: Any) -> dict[str, Any]:
    """
    The observation, in the shape the simulation's ``EnvironmentConfig`` takes.

    This is the one place the two vocabularies meet. Weather providers speak
    Celsius and hPa; the physics speaks kelvin and pascals, and the conversion
    already happened at the provider boundary — so all that remains is renaming
    fields and being explicit about which ones the engine reads.
    """
    return {
        "temperature_K": round(observation.temperature_K, 3),
        "pressure_Pa": round(observation.pressure_Pa, 1),
        "wind_speed_ms": round(observation.wind.speed_ms, 2),
        "wind_direction_deg": round(observation.wind.direction_deg, 1),
        "relative_humidity": round(observation.relative_humidity, 3),
        # None means "estimate it from the surface wind"; a measured 250 hPa
        # value is far better than the estimate when the provider has one.
        "jet_wind_speed_ms": (
            round(observation.jet_wind_speed_ms, 2)
            if observation.jet_wind_speed_ms is not None
            else 0.0
        ),
        "source": observation.provider,
        "observed_at": observation.observed_at.isoformat(),
    }


async def environment_config_for_site(site_id: str) -> dict[str, Any]:
    """Just the simulation input, for a client that only wants to fly."""
    payload = await observation_for_site(site_id)
    return payload["simulation_environment"]
