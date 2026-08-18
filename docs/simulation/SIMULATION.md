<![CDATA[# Simulation Engine Architecture

## Overview

The simulation engine models rocket flight using 3-DOF translational dynamics with analytical/educational-fidelity physics models. It is NOT a certified aerospace tool — it is an educational simulation that teaches real physics concepts.

## Model Fidelity Classification

| Model | Type | Fidelity Level |
|-------|------|---------------|
| Gravity | `g(h) = g₀(R/(R+h))²` | Analytical approximation |
| Atmosphere | US Standard Atmosphere 1976 | Educational simulation |
| Drag | `Fd = 0.5·ρ·v²·Cd·A` | Educational simulation |
| Thrust | `F = Isp·g₀·ṁ` (constant per stage) | Analytical approximation |
| Mass | Linear depletion during burn | Analytical approximation |
| Trajectory | RK4 integration, 3-DOF | Numerical simulation |
| Stability | Barrowman CP + CG calc | Analytical approximation |

**None of these models should be described as research-grade or flight-certified.**

## Simulation Loop

```python
def run_simulation(config: SimConfig) -> SimResult:
    state = initial_state(config)
    telemetry = []
    events = []

    while not terminated(state, config):
        # 1. Environment
        atm = atmosphere_model(state.altitude)

        # 2. Forces
        gravity = gravity_force(state)
        thrust  = thrust_force(state, config.vehicle)
        drag    = drag_force(state, atm, config.vehicle)
        net     = gravity + thrust + drag

        # 3. Acceleration
        state.acceleration = net / state.mass

        # 4. Integrate (RK4)
        state = rk4_step(state, dt, force_func)

        # 5. Mass update
        state.mass -= mass_flow_rate(state) * dt

        # 6. Event detection
        new_events = detect_events(state, prev_state, config)
        events.extend(new_events)

        # 7. Telemetry
        if should_sample(state.t):
            telemetry.append(snapshot(state))

    return SimResult(telemetry=telemetry, events=events, summary=analyze(telemetry, events))
```

## State Vector

```
t               float       Time since ignition (s)
position        [x, y, z]   Meters, ENU frame from launch site
velocity        [vx,vy,vz]  m/s
acceleration    [ax,ay,az]  m/s²
mass            float       Current total mass (kg)
attitude        [p, y, r]   Pitch/yaw/roll (radians) — simplified
stage           int         Current active stage index
phase           enum        PRELAUNCH | POWERED | COAST | DESCENT | TERMINATED
```

## Units Convention

| Quantity | Unit | Symbol |
|----------|------|--------|
| Length | meters | m |
| Mass | kilograms | kg |
| Time | seconds | s |
| Force | newtons | N |
| Velocity | meters/second | m/s |
| Angle | radians | rad |
| Temperature | kelvin | K |
| Pressure | pascals | Pa |

## Termination Conditions

1. Altitude ≤ 0 after launch (impact)
2. Simulation time exceeds max_time (timeout)
3. Critical failure event (structural, explosion)
4. Mission objective achieved (target orbit reached)
5. All stages exhausted + coast complete

## Numerical Integrator

- **Method**: Runge-Kutta 4th order (RK4)
- **Default timestep**: 0.05s during powered flight, 0.1s during coast
- **Adaptive**: Optional halving if acceleration changes rapidly

## Telemetry Sampling

- **Realtime stream**: Every 10 integration steps (~0.5s)
- **Stored data**: Every 1s for persistence, full resolution discarded
- **Events**: Sampled at detection time (not on grid)

## Event Types

| Event | Trigger | Severity |
|-------|---------|----------|
| `ignition` | t = 0, thrust > 0 | info |
| `liftoff` | velocity > 0 AND altitude > 0 | info |
| `max_q` | dynamic_pressure starts decreasing | info |
| `meco` | stage fuel exhausted | info |
| `staging` | stage separation triggered | info |
| `apogee` | vertical velocity crosses 0 (ascending→descending) | info |
| `supersonic` | Mach > 1.0 | info |
| `failure_*` | See Failure Engine | warning/critical/fatal |
| `impact` | altitude ≤ 0 | info or critical |

## Failure Detection Rules

| Rule | Condition | Type |
|------|-----------|------|
| Insufficient TWR | thrust/weight < 1.0 at ignition | fatal |
| Excessive Q | dynamic_pressure > threshold | critical |
| Structural overload | acceleration > g_limit | critical |
| Instability | CP ahead of CG (margin < 0) | warning→critical |
| Trajectory divergence | horizontal velocity >> expected | warning |
| Fuel exhaustion | unexpected early fuel depletion | critical |

## Directory Structure

```
simulation/
├── engine/
│   ├── __init__.py
│   ├── runner.py          # Main simulation loop
│   ├── config.py          # SimConfig dataclass
│   ├── state.py           # SimState dataclass
│   └── result.py          # SimResult dataclass
├── models/
│   ├── gravity/
│   │   └── inverse_square.py
│   ├── atmosphere/
│   │   └── us_standard_1976.py
│   ├── drag/
│   │   └── simple_drag.py
│   ├── thrust/
│   │   └── constant_thrust.py
│   └── trajectory/
│       └── equations_of_motion.py
├── integrator/
│   └── rk4.py
├── telemetry/
│   └── sampler.py
├── events/
│   ├── detector.py
│   └── types.py
├── analysis/
│   └── post_flight.py
├── validation/
│   └── preflight.py
└── tests/
    ├── test_gravity.py
    ├── test_atmosphere.py
    ├── test_drag.py
    ├── test_integration.py
    └── reference_cases.py
```
]]>
