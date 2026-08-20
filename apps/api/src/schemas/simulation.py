"""Request and response schemas for the simulation endpoints.

The request body is a **structured configuration only**. There is no expression
field, no formula string, and no code path that evaluates client-supplied text
— the client picks numbers and enumerated options, and nothing else. This is a
deliberate security boundary (see docs/integration/REPOSITORY_AUDIT.md U-4): a
simulation service that accepted arbitrary expressions would be remote code
execution wearing a physics costume.

The other boundary is cost. A simulation is the most expensive thing this API
does, and it is reachable without a token so that guests can use the platform.
The limits below are what stop an unauthenticated caller from asking for a
year of flight at a microsecond timestep.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Server-side limits.
#
# These are caps on what a *client* may request, not statements about what the
# engine can do. A trusted internal caller constructing a SimConfig directly is
# not bound by them.
# ---------------------------------------------------------------------------

#: Longest flight a request may ask for. Unit: s. Comfortably covers an orbital
#: insertion (~550 s) and a high ballistic arc, without allowing a multi-day run.
MAX_TIME_S = 7_200.0

#: Smallest integration timestep a request may ask for. Unit: s. Below this the
#: step count explodes without meaningfully improving an educational result.
MIN_TIMESTEP_S = 0.001

#: Hard ceiling on integration steps, whatever the timestep works out to.
MAX_STEPS = 2_000_000

#: Most telemetry samples a response will carry. A 2-hour flight sampled every
#: 0.1 s would be 72,000 points and a multi-megabyte JSON body; the engine
#: samples at the requested interval and the response is decimated to fit.
MAX_TELEMETRY_POINTS = 5_000

#: Most stages a vehicle may declare.
MAX_STAGES = 10

#: Most scripted failure injections a mission may carry.
MAX_INJECTIONS = 20


class SimulationRunRequest(BaseModel):
    """A request to fly one mission.

    ``config`` is validated against the engine's own ``SimConfig`` contract
    inside the service; it is typed loosely here so the API layer does not
    have to re-declare the simulation team's schema and drift from it.
    """

    config: dict[str, Any] = Field(description="A simulation.contracts.SimConfig object")

    @field_validator("config")
    @classmethod
    def _enforce_limits(cls, config: dict[str, Any]) -> dict[str, Any]:
        settings = config.get("settings") or {}
        if not isinstance(settings, dict):
            raise ValueError("settings must be an object")

        max_time = settings.get("max_time_s")
        if max_time is not None and float(max_time) > MAX_TIME_S:
            raise ValueError(f"max_time_s may not exceed {MAX_TIME_S:g} s")

        for field in ("dt_powered_s", "dt_coast_s"):
            dt = settings.get(field)
            if dt is not None and float(dt) < MIN_TIMESTEP_S:
                raise ValueError(f"{field} may not be smaller than {MIN_TIMESTEP_S:g} s")

        steps = settings.get("max_steps")
        if steps is not None and int(steps) > MAX_STEPS:
            raise ValueError(f"max_steps may not exceed {MAX_STEPS:,}")

        vehicle = config.get("vehicle") or {}
        stages = vehicle.get("stages") if isinstance(vehicle, dict) else None
        if isinstance(stages, list) and len(stages) > MAX_STAGES:
            raise ValueError(f"a vehicle may not have more than {MAX_STAGES} stages")

        failures = config.get("failures") or {}
        injections = failures.get("injections") if isinstance(failures, dict) else None
        if isinstance(injections, list) and len(injections) > MAX_INJECTIONS:
            raise ValueError(f"a mission may not have more than {MAX_INJECTIONS} injections")

        return config

    @model_validator(mode="after")
    def _require_a_vehicle(self) -> "SimulationRunRequest":
        if not self.config.get("vehicle"):
            raise ValueError("config.vehicle is required")
        if not self.config.get("mission"):
            raise ValueError("config.mission is required")
        return self


class SimulationLimits(BaseModel):
    """The caps above, published so a client can validate before submitting."""

    max_time_s: float = MAX_TIME_S
    min_timestep_s: float = MIN_TIMESTEP_S
    max_steps: int = MAX_STEPS
    max_telemetry_points: int = MAX_TELEMETRY_POINTS
    max_stages: int = MAX_STAGES
    max_injections: int = MAX_INJECTIONS


class SimulationMeta(BaseModel):
    """How the run was produced — provenance for the numbers in ``data``."""

    engine: str = Field(description="Which engine produced this result")
    engine_version: str
    #: Wall-clock time the run took, not simulated time. Unit: s.
    compute_time_s: float
    #: Telemetry samples the engine produced, before any decimation.
    telemetry_points_generated: int
    #: Telemetry samples actually returned.
    telemetry_points_returned: int
    #: True when the series was decimated to fit MAX_TELEMETRY_POINTS.
    telemetry_decimated: bool
    #: Reminder that travels with every result. The brief is explicit that
    #: approximate output must never be presented as flight-certified.
    fidelity_notice: str = (
        "Educational simulation. Transparent, documented approximations - "
        "see docs/simulation/ASSUMPTIONS.md. Not flight-certified engineering."
    )


class EngineAvailability(BaseModel):
    """One engine's importability, for GET /health/engines."""

    available: bool
    reason: str | None = None


class EngineStatusReport(BaseModel):
    """All three engines, named explicitly rather than as a free-form map.

    A ``dict[str, EngineAvailability]`` would generate an OpenAPI schema with
    ``additionalProperties`` and no named fields, which a generated client sees
    as an untyped bag. Naming them keeps the contract legible — and the set of
    engines is fixed, so there is nothing dynamic to express.
    """

    simulation: EngineAvailability
    search: EngineAvailability
    ai: EngineAvailability
