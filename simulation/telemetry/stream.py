from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simulation.contracts import SimConfig, SimResult


@dataclass(frozen=True)
class LiveTelemetrySample:
    t_s: float
    altitude_m: float
    velocity_ms: float
    acceleration_ms2: float
    temperature_c: float
    wind_speed_ms: float
    stage: int
    mission_state: str


@dataclass(frozen=True)
class LiveTelemetryFrame:
    live: bool = True
    launch_datetime_utc: str = ""
    weather_summary: str = "clear"
    temperature_c: float = 15.0
    wind_speed_ms: float = 0.0
    humidity_pct: float = 50.0
    pressure_pa: float = 101_325.0
    samples: list[LiveTelemetrySample] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def build_live_telemetry_frame(
    result: SimResult,
    config: SimConfig,
    *,
    launch_datetime_utc: str = "2026-08-19T12:00:00Z",
) -> LiveTelemetryFrame:
    environment = config.mission.environment
    temp_c = environment.temperature_K - 273.15
    weather_summary = "clear" if environment.wind_speed_ms < 10 else "windy"

    samples = [
        LiveTelemetrySample(
            t_s=point.t,
            altitude_m=point.altitude_m,
            velocity_ms=point.speed_ms,
            acceleration_ms2=point.acceleration_ms2,
            temperature_c=temp_c,
            wind_speed_ms=environment.wind_speed_ms,
            stage=point.stage,
            mission_state=point.mission_state.value,
        )
        for point in result.telemetry
    ]

    return LiveTelemetryFrame(
        live=True,
        launch_datetime_utc=launch_datetime_utc,
        weather_summary=weather_summary,
        temperature_c=temp_c,
        wind_speed_ms=environment.wind_speed_ms,
        humidity_pct=50.0,
        pressure_pa=environment.pressure_Pa,
        samples=samples,
        metadata={
            "vehicle_name": config.vehicle.name,
            "mission_name": config.mission.name,
            "target_altitude_km": config.mission.target.target_altitude_km,
            "launch_site": config.mission.launch_site.name,
        },
    )
