"""Fetching launch-day weather.

Two providers, chosen by what the environment has configured:

* **Open-Meteo** — the default. No API key, no registration, and it publishes
  the fields this platform needs including 250 hPa wind, which is the level the
  jet stream lives at. Free for non-commercial use.
* **OpenWeather** — used when ``OPENWEATHER_API_KEY`` is set, for installations
  that already have a subscription.

Both normalise into :class:`WeatherObservation` before anything downstream sees
them, so the rest of the platform never learns which one answered.

When neither can be reached, :meth:`WeatherService.observation` falls back to a
**climatological standard day** for the site, clearly marked ``is_live=False``
with a stated reason. Silently substituting invented weather and letting the
interface present it as live would be worse than useless — the whole point of
the feature is that the conditions are real.
"""

from __future__ import annotations

import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx

from .models import WeatherObservation, WindObservation

logger = logging.getLogger("data.environment")

__all__ = ["WeatherService", "WeatherUnavailable", "assess_launch_conditions"]

#: Specific gas constant for dry air. Unit: J/(kg·K).
R_DRY_AIR = 287.058

#: Specific gas constant for water vapour. Unit: J/(kg·K).
R_WATER_VAPOUR = 461.495

#: Ratio of specific heats for air.
GAMMA_AIR = 1.4

#: Specific gas constant used for the speed of sound. Unit: J/(kg·K).
R_AIR = 287.05

#: How long an observation stays fresh. Weather APIs update every 15 minutes at
#: best, so polling faster only burns quota. Unit: seconds.
CACHE_TTL_S = 600.0


class WeatherUnavailable(RuntimeError):
    """No provider could supply an observation."""


def saturation_vapour_pressure_Pa(temperature_K: float) -> float:
    """Saturation vapour pressure over liquid water, by Tetens. Unit: Pa."""
    celsius = temperature_K - 273.15
    if celsius <= -35.0:
        return 0.0
    return 610.78 * math.exp(17.27 * celsius / (celsius + 237.3))


def air_density(pressure_Pa: float, temperature_K: float, relative_humidity: float) -> float:
    """
    Density of moist air. Unit: kg/m³.

    Water vapour is lighter than the air it displaces, so humid air is less
    dense — the opposite of most people's intuition, and worth a percent of
    drag on a tropical morning.
    """
    humidity = min(max(relative_humidity, 0.0), 1.0)
    vapour = min(humidity * saturation_vapour_pressure_Pa(temperature_K), pressure_Pa)
    dry = pressure_Pa - vapour
    return dry / (R_DRY_AIR * temperature_K) + vapour / (R_WATER_VAPOUR * temperature_K)


def speed_of_sound(temperature_K: float) -> float:
    """Speed of sound in air. Unit: m/s."""
    return math.sqrt(GAMMA_AIR * R_AIR * temperature_K)


def dew_point_K(temperature_K: float, relative_humidity: float) -> Optional[float]:
    """Dew point from temperature and relative humidity, by Magnus. Unit: K."""
    if relative_humidity <= 0.0:
        return None
    celsius = temperature_K - 273.15
    a, b = 17.27, 237.7
    gamma = (a * celsius) / (b + celsius) + math.log(max(relative_humidity, 1e-6))
    return (b * gamma) / (a - gamma) + 273.15


class WeatherService:
    """Live weather for a launch site, cached and normalised."""

    def __init__(
        self,
        *,
        client: Optional[httpx.AsyncClient] = None,
        openweather_key: Optional[str] = None,
        timeout_s: float = 8.0,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._openweather_key = openweather_key or os.environ.get("OPENWEATHER_API_KEY") or None
        self._timeout_s = timeout_s
        self._cache: Dict[str, Tuple[float, WeatherObservation]] = {}

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_s)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def provider_name(self) -> str:
        """Which provider this service will try first."""
        return "openweather" if self._openweather_key else "open-meteo"

    async def observation(
        self,
        *,
        site_id: str,
        latitude_deg: float,
        longitude_deg: float,
        elevation_m: float,
        force_refresh: bool = False,
    ) -> WeatherObservation:
        """
        Current conditions at a site.

        Returns a live observation where one can be fetched, and a clearly
        marked standard-day fallback where none can. Never raises for a network
        problem: a launch simulation that cannot run because a weather API is
        down would be a worse product than one that runs on a stated standard
        day.
        """
        now = time.monotonic()
        cached = self._cache.get(site_id)
        if cached and not force_refresh and now - cached[0] < CACHE_TTL_S:
            return cached[1]

        for fetch in self._provider_chain():
            try:
                observation = await fetch(site_id, latitude_deg, longitude_deg, elevation_m)
            except Exception as exc:  # noqa: BLE001 - any provider failure falls through
                logger.warning("weather provider failed for %s: %s", site_id, exc)
                continue
            if observation is not None:
                self._cache[site_id] = (now, observation)
                return observation

        stale = self._cache.get(site_id)
        if stale is not None:
            # A ten-minute-old real observation beats an invented one.
            aged = stale[1].model_copy(
                update={
                    "is_live": False,
                    "fallback_reason": "Live providers unreachable; showing the last observation received.",
                }
            )
            return aged

        return self._standard_day(site_id, latitude_deg, longitude_deg, elevation_m)

    def _provider_chain(self):
        if self._openweather_key:
            return [self._fetch_openweather, self._fetch_open_meteo]
        return [self._fetch_open_meteo]

    # ── Open-Meteo ────────────────────────────────────────────────

    async def _fetch_open_meteo(
        self, site_id: str, latitude: float, longitude: float, elevation: float
    ) -> Optional[WeatherObservation]:
        client = await self._http()
        response = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "elevation": elevation,
                "current": ",".join(
                    [
                        "temperature_2m",
                        "relative_humidity_2m",
                        "surface_pressure",
                        "pressure_msl",
                        "wind_speed_10m",
                        "wind_direction_10m",
                        "wind_gusts_10m",
                        "precipitation",
                        "cloud_cover",
                    ]
                ),
                # 250 hPa is the jet-stream level. Having it means the wind
                # profile is anchored on a measurement rather than an estimate.
                "hourly": "wind_speed_250hPa",
                "forecast_days": 1,
                "wind_speed_unit": "ms",
                "timezone": "GMT",
            },
        )
        response.raise_for_status()
        payload: Dict[str, Any] = response.json()
        current = payload.get("current") or {}
        if "temperature_2m" not in current:
            return None

        temperature_K = float(current["temperature_2m"]) + 273.15
        humidity = float(current.get("relative_humidity_2m", 0.0)) / 100.0
        # Open-Meteo reports pressure in hPa.
        pressure_Pa = float(current.get("surface_pressure", 1013.25)) * 100.0
        msl_Pa = (
            float(current["pressure_msl"]) * 100.0 if current.get("pressure_msl") else None
        )

        jet_ms = None
        hourly = payload.get("hourly") or {}
        jet_series = hourly.get("wind_speed_250hPa") or []
        if jet_series:
            usable = [float(v) for v in jet_series[:6] if v is not None]
            if usable:
                jet_ms = max(usable)

        return WeatherObservation(
            site_id=site_id,
            latitude_deg=latitude,
            longitude_deg=longitude,
            elevation_m=elevation,
            observed_at=_parse_time(current.get("time")),
            temperature_K=temperature_K,
            dew_point_K=dew_point_K(temperature_K, humidity),
            pressure_Pa=pressure_Pa,
            sea_level_pressure_Pa=msl_Pa,
            relative_humidity=humidity,
            wind=WindObservation(
                speed_ms=float(current.get("wind_speed_10m", 0.0)),
                direction_deg=float(current.get("wind_direction_10m", 0.0)) % 360.0,
                gust_ms=(
                    float(current["wind_gusts_10m"])
                    if current.get("wind_gusts_10m") is not None
                    else None
                ),
            ),
            precipitation_mm_h=float(current.get("precipitation", 0.0)),
            cloud_cover=float(current.get("cloud_cover", 0.0)) / 100.0,
            air_density_kgm3=air_density(pressure_Pa, temperature_K, humidity),
            speed_of_sound_ms=speed_of_sound(temperature_K),
            jet_wind_speed_ms=jet_ms,
            provider="open-meteo",
            is_live=True,
            attribution="Weather data by Open-Meteo.com (CC BY 4.0)",
        )

    # ── OpenWeather ───────────────────────────────────────────────

    async def _fetch_openweather(
        self, site_id: str, latitude: float, longitude: float, elevation: float
    ) -> Optional[WeatherObservation]:
        if not self._openweather_key:
            return None
        client = await self._http()
        response = await client.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "lat": latitude,
                "lon": longitude,
                "appid": self._openweather_key,
                "units": "metric",
            },
        )
        response.raise_for_status()
        payload: Dict[str, Any] = response.json()
        main = payload.get("main") or {}
        wind = payload.get("wind") or {}
        if "temp" not in main:
            return None

        temperature_K = float(main["temp"]) + 273.15
        humidity = float(main.get("humidity", 0.0)) / 100.0
        # OpenWeather's `grnd_level` is the station pressure; `pressure` is
        # reduced to sea level. Using the wrong one puts a 90 m site under an
        # extra 10 hPa of air.
        pressure_hPa = main.get("grnd_level") or main.get("pressure") or 1013.25
        pressure_Pa = float(pressure_hPa) * 100.0

        return WeatherObservation(
            site_id=site_id,
            latitude_deg=latitude,
            longitude_deg=longitude,
            elevation_m=elevation,
            observed_at=datetime.fromtimestamp(
                int(payload.get("dt", time.time())), tz=timezone.utc
            ),
            temperature_K=temperature_K,
            dew_point_K=dew_point_K(temperature_K, humidity),
            pressure_Pa=pressure_Pa,
            sea_level_pressure_Pa=float(main.get("sea_level", main.get("pressure", 1013.25))) * 100.0,
            relative_humidity=humidity,
            wind=WindObservation(
                speed_ms=float(wind.get("speed", 0.0)),
                direction_deg=float(wind.get("deg", 0.0)) % 360.0,
                gust_ms=float(wind["gust"]) if wind.get("gust") is not None else None,
            ),
            precipitation_mm_h=float((payload.get("rain") or {}).get("1h", 0.0)),
            cloud_cover=float((payload.get("clouds") or {}).get("all", 0.0)) / 100.0,
            visibility_m=float(payload["visibility"]) if payload.get("visibility") else None,
            air_density_kgm3=air_density(pressure_Pa, temperature_K, humidity),
            speed_of_sound_ms=speed_of_sound(temperature_K),
            provider="openweather",
            is_live=True,
            attribution="Weather data by OpenWeather",
        )

    # ── Fallback ──────────────────────────────────────────────────

    def _standard_day(
        self, site_id: str, latitude: float, longitude: float, elevation: float
    ) -> WeatherObservation:
        """
        A standard day at this site's elevation, marked as not live.

        This is the US Standard Atmosphere evaluated at the pad, with still air.
        It is a defensible default and it is labelled as one; nothing in the
        interface may present it as an observation.
        """
        temperature_K = 288.15 - 0.0065 * elevation
        pressure_Pa = 101_325.0 * (temperature_K / 288.15) ** 5.25588

        return WeatherObservation(
            site_id=site_id,
            latitude_deg=latitude,
            longitude_deg=longitude,
            elevation_m=elevation,
            observed_at=datetime.now(timezone.utc),
            temperature_K=temperature_K,
            pressure_Pa=pressure_Pa,
            relative_humidity=0.0,
            wind=WindObservation(speed_ms=0.0, direction_deg=0.0),
            air_density_kgm3=air_density(pressure_Pa, temperature_K, 0.0),
            speed_of_sound_ms=speed_of_sound(temperature_K),
            provider="standard_day",
            is_live=False,
            fallback_reason=(
                "No weather provider could be reached. These are US Standard "
                "Atmosphere values for this site's elevation, in still air — "
                "not an observation."
            ),
            attribution="US Standard Atmosphere 1976",
        )


def _parse_time(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            text = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────────────────────
# Launch commit criteria
# ──────────────────────────────────────────────────────────────

from .models import LaunchConstraint, LaunchSuitability  # noqa: E402

#: Ground wind limit for a typical medium launch vehicle. Unit: m/s.
#:
#: Real limits are vehicle-specific and are quoted as a peak wind at a
#: reference height — Falcon 9's ground wind constraint sits in the low
#: 20 m/s range, Atlas V's around 17 m/s at 49 m. 15 m/s sustained is a
#: reasonable general figure and is stated as a simplification.
GROUND_WIND_LIMIT_MS = 15.0
GROUND_WIND_CAUTION_MS = 10.0

#: Gust limit. A vehicle can survive its sustained-wind limit; a gust to the
#: same speed on top of it is a different load case. Unit: m/s.
GUST_LIMIT_MS = 20.0

#: Precipitation limit. Rain at ascent speed erodes thermal protection and,
#: more importantly, means the cloud layers that carry a lightning risk.
#: Unit: mm/h.
PRECIPITATION_LIMIT_MM_H = 2.0

#: Temperature limits. Below freezing, ice forms on cryogenic tanks and can
#: shed into the vehicle; the low limit is the lesson of STS-51-L, where an
#: O-ring seal failed at 2 °C. Unit: K.
TEMPERATURE_MIN_K = 275.15
TEMPERATURE_MAX_K = 311.15

#: Visibility floor for a launch that must be optically tracked. Unit: m.
VISIBILITY_LIMIT_M = 4_000.0


def assess_launch_conditions(
    observation: WeatherObservation,
    *,
    wind_limit_ms: float = GROUND_WIND_LIMIT_MS,
    gust_limit_ms: float = GUST_LIMIT_MS,
) -> LaunchSuitability:
    """
    Evaluate an observation against launch commit criteria.

    Modelled on how a real launch weather officer works: each criterion is
    checked independently, any single violation is a no-go, and the reason is
    always given as a measured value against a stated limit rather than as a
    verdict on its own.

    These are simplified, general limits, not any specific vehicle's. A real
    review also covers lightning, anvil and debris cloud rules, cumulus
    standoff, triboelectrification and upper-level shear — none of which a
    surface observation can answer.

    Args:
        observation: The current conditions.
        wind_limit_ms: Sustained ground wind limit for this vehicle.
        gust_limit_ms: Gust limit for this vehicle.

    Returns:
        The overall verdict and every criterion that produced it.
    """
    constraints = []

    wind = observation.wind.speed_ms
    constraints.append(
        LaunchConstraint(
            id="ground_wind",
            label="Ground wind",
            status=(
                "no-go" if wind > wind_limit_ms
                else "caution" if wind > GROUND_WIND_CAUTION_MS
                else "go"
            ),
            measured=round(wind, 1),
            limit=wind_limit_ms,
            unit="m/s",
            explanation=(
                "Wind at the pad pushes the vehicle sideways while it is slow "
                "and its control authority is at its weakest, in the seconds "
                "just after it clears the tower."
            ),
        )
    )

    gust = observation.wind.gust_ms
    if gust is not None:
        constraints.append(
            LaunchConstraint(
                id="wind_gust",
                label="Peak gust",
                status="no-go" if gust > gust_limit_ms else "caution" if gust > wind_limit_ms else "go",
                measured=round(gust, 1),
                limit=gust_limit_ms,
                unit="m/s",
                explanation=(
                    "A gust is a step change in load, not a steady one. The "
                    "airframe sees it as a shock, and the guidance sees it as a "
                    "disturbance it did not command."
                ),
            )
        )

    constraints.append(
        LaunchConstraint(
            id="precipitation",
            label="Precipitation",
            status=(
                "no-go" if observation.precipitation_mm_h > PRECIPITATION_LIMIT_MM_H
                else "caution" if observation.precipitation_mm_h > 0.1
                else "go"
            ),
            measured=round(observation.precipitation_mm_h, 2),
            limit=PRECIPITATION_LIMIT_MM_H,
            unit="mm/h",
            explanation=(
                "Rain at several hundred metres a second erodes thermal "
                "protection, and rain means the cloud structure that carries a "
                "triggered-lightning risk."
            ),
        )
    )

    temperature = observation.temperature_K
    too_cold = temperature < TEMPERATURE_MIN_K
    too_hot = temperature > TEMPERATURE_MAX_K
    temperature_status = (
        "no-go"
        if too_cold or too_hot
        else "caution"
        if temperature < TEMPERATURE_MIN_K + 3 or temperature > TEMPERATURE_MAX_K - 3
        else "go"
    )
    # Report the limit the reading is actually near, so "35 °C exceeds the
    # 2 °C limit" cannot happen.
    temperature_limit_K = (
        TEMPERATURE_MIN_K
        if too_cold or temperature < (TEMPERATURE_MIN_K + TEMPERATURE_MAX_K) / 2
        else TEMPERATURE_MAX_K
    )
    constraints.append(
        LaunchConstraint(
            id="temperature",
            label="Air temperature",
            status=temperature_status,
            measured=round(temperature - 273.15, 1),
            limit=round(temperature_limit_K - 273.15, 1),
            unit="°C",
            explanation=(
                "Cold stiffens elastomeric seals and lets ice form on cryogenic "
                "tanks — Challenger was lost at 2 °C, to an O-ring that could no "
                "longer seal. Heat is the milder constraint: it is usually "
                "handled by conditioning the vehicle on the pad rather than by "
                "waiting."
            ),
        )
    )

    if observation.visibility_m is not None:
        constraints.append(
            LaunchConstraint(
                id="visibility",
                label="Visibility",
                status="caution" if observation.visibility_m < VISIBILITY_LIMIT_M else "go",
                measured=round(observation.visibility_m),
                limit=VISIBILITY_LIMIT_M,
                unit="m",
                explanation=(
                    "Optical tracking is part of range safety. Losing sight of "
                    "the vehicle does not endanger it, but it removes one way of "
                    "knowing where it is."
                ),
            )
        )

    violations = [c.id for c in constraints if c.status == "no-go"]
    cautions = [c.id for c in constraints if c.status == "caution"]

    if violations:
        status = "no-go"
        summary = "Hold. " + "; ".join(
            "{0} {1} {2} is outside the {3} {2} limit".format(
                c.label, c.measured, c.unit, c.limit
            )
            for c in constraints
            if c.status == "no-go"
        ) + "."
    elif cautions:
        status = "caution"
        summary = (
            "Within limits, but close to them: "
            + ", ".join(c.label.lower() for c in constraints if c.status == "caution")
            + ". Expect a noisier ascent."
        )
    else:
        status = "go"
        summary = "All evaluated criteria are within limits."

    return LaunchSuitability(
        status=status, summary=summary, constraints=constraints, violations=violations
    )
