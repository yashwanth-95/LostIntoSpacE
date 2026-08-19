from __future__ import annotations

from typing import Any

from simulation.contracts import SimConfig, SimResult


def build_renderer_frame(result: SimResult, config: SimConfig) -> dict[str, Any]:
    latest = result.telemetry[-1] if result.telemetry else None

    return {
        "mission_state": result.final_state.value,
        "altitude_m": latest.altitude_m if latest else 0.0,
        "velocity_ms": latest.speed_ms if latest else 0.0,
        "acceleration_ms2": latest.acceleration_ms2 if latest else 0.0,
        "thrust_N": latest.thrust_N if latest else 0.0,
        "pitch_rad": latest.pitch_rad if latest else 0.0,
        "yaw_rad": latest.yaw_rad if latest else 0.0,
        "telemetry_points": len(result.telemetry),
        "event_count": len(result.events),
        "vehicle_name": config.vehicle.name,
        "target_altitude_km": config.mission.target.target_altitude_km,
        "flight_time_s": result.flight_time_s,
        "status": "running" if not result.success else "complete",
    }
