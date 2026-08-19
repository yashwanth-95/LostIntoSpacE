# Simulation Architecture

## Purpose

This domain is responsible for rocket engineering, scientific simulation, telemetry, mission progression, and 3D visualization. The architecture is intentionally hybrid: Python owns the scientific simulation logic, while TypeScript owns rendering and UI-facing visualization.

## Core rule

- Python calculates the physics and mission behavior.
- TypeScript renders the scene and drives the UI.
- The renderer consumes serialized simulation state; it does not calculate flight physics.

## Responsibility split

### Python responsibilities

- rocket and stage domain models
- gravity, atmosphere, drag, thrust and mass models
- numerical integration and orbital calculations
- mission state transitions and failure logic
- telemetry generation and event emission
- deterministic simulation results for API and AI consumers

### TypeScript responsibilities

- Three.js / React Three Fiber rendering
- camera control and viewport layout
- rocket meshes, planets, atmosphere and trajectory visualization
- interactive builder UI and stage composition
- telemetry plotting and dashboard display
- real-time animation after receiving simulation output

## Layered architecture

```text
Python simulation
  ├── domain
  │   ├── rocket
  │   ├── stage
  │   ├── mission
  │   ├── environment
  │   └── vehicle
  ├── physics
  │   ├── gravity
  │   ├── atmosphere
  │   ├── drag
  │   ├── thrust
  │   ├── mass
  │   ├── orbital
  │   └── integration
  ├── propulsion
  │   ├── engine config
  │   ├── mass flow
  │   └── burn state
  ├── telemetry
  │   ├── telemetry frame
  │   ├── event stream
  │   └── summary metrics
  ├── failures
  │   ├── rules
  │   ├── events
  │   └── metadata
  └── api adapters

TypeScript visualization
  ├── renderer
  │   ├── rocket mesh
  │   ├── planet renderer
  │   ├── trajectory renderer
  │   ├── camera rig
  │   └── effects
  ├── adapters
  │   ├── simulation hook
  │   ├── builder hook
  │   └── viewer component
  └── UI
      ├── controls
      ├── charts
      └── mission dashboard
```

## Domain model

The domain model describes the vehicle and mission in a way that both Python and TypeScript can understand.

### Rocket / vehicle model

- rocket name and identifier
- stage list and stage order
- payload and structure mass
- engine and propellant definitions
- aerodynamic reference areas and coefficients
- launch and mission metadata

### Mission model

- mission type and target
- launch site and environment
- simulation settings
- mission state history
- telemetry and event stream
- outcome summary

## Physics model

The initial simulator is intentionally educational and explicit about assumptions.

### Primary model

- Newtonian translational dynamics
- gravity as inverse-square central field
- simplified atmosphere model
- drag approximation using density and velocity
- propulsion as constant Isp and mass flow during burn
- stage mass reduction during active burn
- basic orbital insertion and ascent guidance

### Numerical method

The current TypeScript implementation favors deterministic RK4 stepping. The Python version should mirror that behavior for consistency and testability. For an educational MVP, the selection should prioritize:

- predictable behavior
- stability
- explainability
- repeatability

## Time model

The model distinguishes:

- real time: wall-clock time of the UI and browser
- simulation time: numerical time used by the flight engine
- mission elapsed time: mission clock from preparation through completion

The engine must not use frontend wall-clock time as the physics clock.

## Coordinate system model

The engine should support at least:

- local launch coordinates
- Earth-centered coordinates
- future orbital and solar-system coordinate frames

The initial implementation should keep units explicit and avoid mixing metric/kinematic conventions.

## Telemetry contract

Telemetry is emitted as structured, serializable data with explicit field names and units. It should be designed for both UI display and AI processing.

Examples:

- altitude
- velocity
- acceleration
- mass
- propellant mass
- thrust
- drag
- position vector
- velocity vector
- mission state
- stage index
- engine status

## Mission state machine

The mission state machine should be configurable and data-driven. The initial set supports states such as:

- PREPARATION
- COUNTDOWN
- IGNITION
- LIFTOFF
- ASCENT
- MAX_Q
- ENGINE_CUTOFF
- STAGE_SEPARATION
- ORBIT_INSERTION
- ORBIT
- FAILURE
- COMPLETE

Not every mission must use every state.

## Failure model

The failure system is educational and should remain structured, not claimed to reproduce real accident investigation. It should explicitly capture:

- subsystem
- failure type
- severity
- cause
- telemetry snapshot
- event description

## Integration points

### Python → TypeScript

The Python engine delivers:

- initial config and mission setup
- telemetry samples
- mission event stream
- summary metrics
- failure events
- final mission state

### TypeScript → Python

The frontend sends:

- selected rocket configuration
- mission parameters
- start, pause, resume, reset commands
- simulation speed selection
- optional failure triggers or presets

## Recommended migration boundaries

1. Preserve current TypeScript engine as working baseline.
2. Freeze shared schema contracts before porting logic.
3. Port the pure physics and state machine into Python incrementally.
4. Keep all Three.js rendering in TypeScript.
5. Use the Python output only as the source of truth for simulation state.
6. Remove only obsolete duplicate logic after both implementations are validated to match.

## Conclusion

This architecture is intentionally layered and conservative. It preserves the current high-value work while enabling a Python-native scientific engine that can be connected to a TypeScript visualization layer without creating a second backend or a second frontend.
