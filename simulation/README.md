<![CDATA[# Simulation Engine — `simulation/`

## Owner: P3 (Simulation / Scientific Models)

## Purpose
Physics-based rocket flight simulation using 3-DOF translational dynamics with RK4 integration. Educational fidelity — not flight-certified.

## Dependencies
- `scientific/` — atmosphere model, constants, unit conversions
- `numpy` — numerical arrays
- `scipy` — integration utilities (optional)

## Prohibited Dependencies
- NO frontend imports
- NO database imports
- NO API framework imports
- This module must be usable as a standalone Python library

## Key Interface

```python
# simulation/engine/runner.py
def run_simulation(config: SimConfig) -> SimResult:
    """Run a complete simulation. Pure function — no side effects."""
    ...

# simulation/engine/config.py
@dataclass
class SimConfig:
    vehicle: VehicleConfig
    mission: MissionConfig
    environment: EnvironmentConfig
    settings: SimSettings

# simulation/engine/result.py
@dataclass
class SimResult:
    success: bool
    outcome: str            # "success" | "partial" | "failure"
    summary: dict           # max_alt, max_v, max_q, flight_time
    telemetry: list[TelemetryPoint]
    events: list[SimEvent]
    errors: list[str]
```

## Testing
- Every physics model has unit tests with known reference values
- Integration tests compare full trajectories against analytical solutions
- Run: `pytest simulation/tests/`
]]>
