"""Weather for a launch site, in the form the simulation consumes.

Two responsibilities, and it is worth keeping them separate in your head:

1. Fetch and normalise an observation (delegated to `data.environment`).
2. Reduce that observation to the handful of SI fields the physics reads, so
   that what the user sees on the launch page and what the trajectory is flown
   against are the same numbers.

The second is the one that matters. The brief was explicit that weather must not
be a decorative card, and the way to guarantee that is to make the panel and the
simulation read from a single derived object rather than from two paths that
could drift.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, Dict, List

from src.catalog import service as catalog_service
from src.core.engines import ensure_engine_paths


@lru_cache(maxsize=1)
def _weather_service() -> Any:
    """One service per process, so its cache is actually shared."""
    ensure_engine_paths()
    from data.environment import WeatherService

    return WeatherService()


def _assess(observation: Any) -> Any:
    ensure_engine_paths()
    from data.environment import assess_launch_conditions

    return assess_launch_conditions(observation)


def _standard_density_at(elevation_m: float) -> float:
    """Standard-atmosphere density at a site's elevation. Unit: kg/m³.

    The comparison baseline for "is today's air thicker or thinner than usual",
    which is only meaningful against the site's own elevation — Baikonur at 90 m
    is always slightly thinner than sea level, and that is not weather.
    """
    temperature = 288.15 - 0.0065 * elevation_m
    pressure = 101_325.0 * (temperature / 288.15) ** 5.25588
    return pressure / (287.058 * temperature)


def _simulation_environment(observation: Any) -> Dict[str, Any]:
    """The observation, reduced to what `EnvironmentConfig` accepts.

    Exactly these fields are sent to the simulation. Nothing on the launch page
    is shown that is not either in here or explicitly labelled as context.
    """
    return {
        "temperature_K": round(observation.temperature_K, 3),
        "pressure_Pa": round(observation.pressure_Pa, 1),
        "wind_speed_ms": round(observation.wind.speed_ms, 3),
        "wind_direction_deg": round(observation.wind.direction_deg, 1),
        "relative_humidity": round(observation.relative_humidity, 4),
        # 0 tells the wind model to estimate the jet from the surface wind.
        "jet_wind_speed_ms": round(observation.jet_wind_speed_ms or 0.0, 2),
        "source": observation.provider,
        "observed_at": observation.observed_at.isoformat(),
    }


async def site_weather(site_id: str, *, refresh: bool = False) -> Dict[str, Any]:
    """Conditions at one launch site, with the verdict and the simulation inputs."""
    site = catalog_service.get_launch_site(site_id)
    service = _weather_service()

    observation = await service.observation(
        site_id=site.id,
        latitude_deg=site.latitude_deg,
        longitude_deg=site.longitude_deg,
        elevation_m=site.elevation_m,
        force_refresh=refresh,
    )

    standard_density = _standard_density_at(site.elevation_m)
    delta_pct = (
        (observation.air_density_kgm3 - standard_density) / standard_density * 100.0
        if standard_density > 0
        else 0.0
    )

    # The observation is returned as the model, not as a dumped dict. FastAPI
    # serialises it directly — and `temperature_C` is a computed field, which
    # serialises but is not accepted as *input*, so round-tripping it through a
    # dict made the response fail its own validation.
    return {
        "site": site,
        "observation": observation,
        "suitability": _assess(observation),
        "simulation_environment": _simulation_environment(observation),
        "density_vs_standard_pct": round(delta_pct, 2),
    }


async def all_site_weather() -> List[Dict[str, Any]]:
    """Conditions at every site, for the launch-site picker.

    Sequential rather than concurrent on purpose: ten parallel requests to a
    free weather API is how an installation gets rate-limited, and the
    ten-minute cache means this is a cold path at most once per interval.
    """
    results = []
    for site in catalog_service.list_launch_sites():
        try:
            results.append(await site_weather(site.id))
        except Exception:  # noqa: BLE001 - one bad site must not blank the picker
            continue
    return results


def provider_name() -> str:
    return _weather_service().provider_name


def wind_profile_preview(surface_speed_ms: float, direction_deg: float, latitude_deg: float) -> List[Dict[str, float]]:
    """The wind profile a given surface observation implies, sampled by altitude.

    Exposed so the launch page and the wind-shear lesson can show *why* a calm
    morning at the pad is not the same as calm conditions at max-Q. Uses the
    same model the force calculation uses, not a second approximation of it.
    """
    ensure_engine_paths()
    from simulation.models.wind import WindProfile, wind_at_altitude

    profile = WindProfile(
        surface_speed_ms=surface_speed_ms,
        surface_direction_deg=direction_deg,
        latitude_deg=latitude_deg,
    )

    samples = []
    for altitude_m in (0, 10, 100, 500, 1_000, 2_000, 5_000, 8_000, 11_000, 14_000, 18_000, 22_000, 25_000):
        state = wind_at_altitude(float(altitude_m), profile)
        samples.append(
            {
                "altitude_m": float(altitude_m),
                "speed_ms": round(state.speed_ms, 2),
                "direction_deg": round(state.direction_deg, 1),
            }
        )
    return samples
