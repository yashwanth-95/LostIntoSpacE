# Simulation Engine — Migration Plan

> **Owner**: Person 3 (Simulation / Physics / 3D)
> **Created**: 2026-08-19
> **Status**: Phase 0 Complete — Awaiting Approval

---

## 0. Phase 0 — Existing-code audit

### A. Existing Person 3 files

- `packages/simulation-engine/src/physics/` — pure physics models: constants, vectors, gravity, atmosphere, drag, thrust, stability, orbital mechanics and integrators.
- `packages/simulation-engine/src/core/` — rocket design, components, validation, vehicle conversion, builder logic and catalog definitions.
- `packages/simulation-engine/src/sim/` — mission state machine, guidance, forces, telemetry, failure modeling, determinism and flight loop.
- `packages/simulation-engine/src/renderer/` — Three.js scene manager, rocket mesh, trajectory, planet, camera and effects.
- `packages/simulation-engine/src/adapters/` — React hooks and R3F mounts for UI integration.
- `packages/simulation-engine/src/integration/` — cross-team DTO and export contracts.
- `simulation/` — Python experiment package with constants, physics models, telemetry contracts and tests.
- `simulation/contracts/` — Pydantic-based canonical schema layer for Python TypeScript exchange.
- `docs/simulation/` — migration and simulation documentation.

### B. Existing functionality

The current Person 3 work is already substantial and should be treated as the baseline to preserve:

- deterministic rocket design and validation flows
- physics models for gravity, atmosphere, drag, thrust, stability and orbital state
- a full simulation runner with mission-state sequencing, guidance and failure detection
- telemetry generation and sampling for UI and AI consumption
- a Three.js renderer with procedural rocket/planet/trajectory visualization
- a React adapter layer that integrates simulation controls into the frontend
- test coverage for physics, core domain logic, renderer and simulation determinism

### C. Current TypeScript architecture

The TypeScript engine is organized in strict layers, with low coupling and no browser dependencies in the core physics/simulation layers:

```
physics → core → sim → integration → renderer → adapters
```

This architecture is already sound and should be preserved. The main value is that the simulation logic can be translated to Python without dragging in browser-only rendering concerns.

### D. Existing simulation logic

The runner in `packages/simulation-engine/src/sim/runner.ts` already implements a flight loop that:

- sequences mission phases and stage behavior
- computes guidance and forces
- integrates acceleration with RK4
- updates mass and propellant consumption
- detects and records failures
- emits telemetry and mission events
- handles termination conditions

This is the clearest candidate for incremental Python migration because it is already deterministic and well-tested.

### E. Existing rendering logic

The rendering layer in `packages/simulation-engine/src/renderer/` is intentionally browser-only and should remain TypeScript/Three.js for real-time visualization. It includes:

- scene setup and camera rigging
- rocket mesh construction
- trajectory and orbit rendering
- planet and environment objects
- exhaust/visual effects
- imperative scene sync from simulation state

This should be preserved as the visual layer, not ported to Python.

### F. Existing dependencies

The existing engine depends on:

- TypeScript and Vitest for the TS simulation package
- Three.js for rendering
- React + React Three Fiber only in the adapter boundary
- Python scientific stack in the experimental `simulation/` package: NumPy and Pydantic

The repository already follows the recommended rule: no physics logic in browser components, no rendering dependencies in the pure simulation layers.

### G. What should remain TypeScript

- all Three.js rendering and scene graph code
- React hooks and frontend-facing adapters
- engine builder UX and visualization concerns
- any user interaction, camera manipulation and viewport behavior
- mission presentation and telemetry rendering in the browser

### H. What should move to Python

- gravity, atmosphere, drag and thrust models
- numerical integration logic and force accumulation
- orbital propagation and delta-v calculations
- mission state transitions and deterministic flight loop
- telemetry generation and failure events as serialized machine-readable outputs
- python-native validation of mission configs before execution

These should move incrementally, but only after shared contracts are defined and validated against the existing TS outputs.

### I. What should become shared contracts

The current Python contracts in `simulation/contracts/__init__.py` should become the canonical integration boundary for:

- vehicle / stage / mission config
- telemetry frame
- mission state
- simulation event
- failure event
- aggregate simulation result

The TypeScript package already has structurally similar definitions, so the migration should align them instead of creating a second incompatible schema.

### J. Risks

- accidentally mixing rendering and physics logic in the same file
- duplicating simulation rules in both TypeScript and Python and allowing drift
- over-porting before contract stability is reached
- using more dependencies than necessary instead of sticking to the MVP educational model
- losing deterministic behavior during migration if Python and TypeScript differ in time stepping or assumptions
- exposing Python execution or arbitrary code through the frontend

### K. Migration sequence

1. Freeze and audit current TS simulation engine.
2. Separate rendering concerns from logic and keep the TS renderer intact.
3. Define shared simulation contracts.
4. Build Python simulation domain models using the same units and assumptions.
5. Port physics functions incrementally and compare against TS tests.
6. Port mission state, event and failure behavior.
7. Add FastAPI adapter boundaries without creating a second backend.
8. Connect TypeScript viewer to Python telemetry output.
9. Remove only redundant duplicate logic after validation.
10. Run the full regression set at each migration step.

This Phase 0 audit confirms that the existing work is already valuable and should be preserved. The migration strategy is incremental, not a destructive rewrite.

---

## 1. Phase 1 — Migration architecture

### 1.1 Target architecture

The target architecture remains hybrid and intentionally conservative:

```text
Frontend (Person 1)
    │
    │ HTTP / WebSocket / simulation client
    ▼
FastAPI backend (Person 2)
    │
    ├── project / auth / persistence
    └── simulation module / adapters
             │
             ▼
        Python simulation engine
             │
             ├── domain/
             ├── physics/
             ├── propulsion/
             ├── orbital/
             ├── mission/
             ├── telemetry/
             └── failures/

Frontend (Person 1)
    │
    ▼
TypeScript / Three.js renderer
    ├── Rocket renderer
    ├── Planet renderer
    ├── Trajectory renderer
    ├── Camera
    └── Telemetry visualization
```

### 1.2 Architectural rules

- No second backend is created.
- No second frontend is created.
- The TypeScript renderer remains the visualization boundary.
- The Python engine is the scientific truth source for mission behavior.
- The backend may expose Python simulation results via API routes or a service layer, but the simulation remains modular and importable.
- The renderer and UI do not calculate physics or mission logic.

### 1.3 Keep / refactor / migrate decisions

| Area | Decision | Why |
|------|----------|-----|
| `packages/simulation-engine/src/renderer/*` | Keep | It is already working Three.js rendering and should remain the browser visualization layer. |
| `packages/simulation-engine/src/adapters/*` | Keep | These are the frontend integration boundary for Person 1. |
| `packages/simulation-engine/src/physics/*` | Keep + migrate to Python | The physics layer is pure and ideal for a Python scientific implementation. |
| `packages/simulation-engine/src/core/*` | Keep + align with shared contracts | Builder logic is still valuable, but the sim-facing contracts must be canonical. |
| `packages/simulation-engine/src/sim/*` | Keep + migrate incrementally | This is the central flight loop and should become the Python reference model. |
| `simulation/contracts/*` | Extend and formalize | This is the correct place for the canonical schema boundary. |
| `simulation/` Python package | Grow incrementally | It should become the Python simulation engine without replacing the existing TS engine abruptly. |

### 1.4 Migration constraints

- Do not rename existing TypeScript files solely to make the Python port look cleaner.
- Do not delete working simulation or renderer files before equivalent Python behavior is verified.
- Use small, reviewable migration commits.
- Preserve stable interfaces for Person 1 and Person 2.
- Treat the current TS engine as a baseline, not as disposable prototype code.

---

## 2. Phase 2 — Shared simulation contracts

### 2.1 Contract objective

The contract layer is the bridge between the Python simulation and the TypeScript frontend. It ensures that the same conceptual objects are shared across the stack without ambiguity.

The canonical objects should be:

- `Vehicle`
- `Stage`
- `RocketDesign` or design summary
- `MissionConfig`
- `MissionState`
- `TelemetryFrame`
- `SimulationEvent`
- `FailureEvent`
- `SimulationState`
- `SimulationResult`

### 2.2 Canonical schema principles

- All values are SI units unless explicitly documented.
- Numeric values and time are explicit and serializable.
- Event objects must be machine-readable for AI and analytics.
- The frontend should consume simulation state, not Python classes.
- The Python engine should output JSON-friendly objects that TypeScript can render directly.

### 2.3 Contract mapping

| Python concept | TypeScript equivalent | Notes |
|----------------|----------------------|-------|
| `Vehicle` | `Vehicle` | Simulation-facing flattened rocket model |
| `Stage` | `Stage` | per-stage mass, thrust, burn metadata |
| `MissionConfig` | `MissionConfig` | launch site, target, environment |
| `MissionState` | `MissionState` | state machine status |
| `TelemetryFrame` | `TelemetryPoint` | serializable sample with numeric values |
| `SimulationEvent` | `SimEvent` | timeline and milestone events |
| `FailureEvent` | `FailureDetail` | structured cause, severity and metadata |
| `SimulationState` | `SimulationState` | snapshot of live simulation state |
| `SimulationResult` | `SimResult` | summary, telemetry and final outcome |

### 2.4 Shared schema shape

A consistent payload shape should look like:

```json
{
  "time_s": 42.5,
  "mission_state": "ASCENT",
  "vehicle": {
    "mass_kg": 2450,
    "altitude_m": 1850,
    "velocity_ms": 148,
    "acceleration_ms2": 18.4,
    "stage": 1
  },
  "telemetry": {
    "altitude_m": 1850,
    "velocity_ms": 148,
    "thrust_N": 56000,
    "propellant_kg": 920
  },
  "events": [
    {
      "timestamp_s": 42.5,
      "type": "MAX_Q",
      "severity": "info",
      "description": "Maximum dynamic pressure reached"
    }
  ],
  "failure": null
}
```

This is the format that should feed the 3D scene, UI dashboards, and AI explanation layers.

### 2.5 Contract lifecycle

1. Freeze the current TS contracts as the baseline.
2. Add or align Python Pydantic schemas to those same concepts.
3. Validate that field names, units and types match.
4. Keep contract validation in the API boundary rather than the renderer.
5. Update the contract only when both sides agree and tests are green.

---

## 3. Existing Architecture

The TypeScript simulation engine in `packages/simulation-engine/` has a 6-layer architecture with one-directional dependencies, enforced by `tsconfig.headless.json` and `tests/architecture.test.ts`:

```
physics → core → sim → integration → renderer → adapters
```

- `physics/`, `core/`, `sim/`, `integration/` — zero browser dependencies, run in Node/Worker
- `renderer/` — Three.js only, no React
- `adapters/` — React + R3F, the only browser-specific layer

## 2. Existing Files

### Physics Layer (11 files, ~1,600 lines)

| File | Role |
|------|------|
| `constants.ts` | Physical constants (NIST, WGS-84, USSA-1976 sourced) |
| `vec3.ts` | Immutable 3D vector type + pure operations |
| `gravity.ts` | Inverse-square gravity (scalar + central vector) |
| `atmosphere.ts` | US Standard Atmosphere 1976 (7 layers + exponential) |
| `drag.ts` | Aerodynamic drag (Mach-corrected transonic rise) |
| `thrust.ts` | Thrust, Isp, mass flow, delta-v, TWR |
| `integrator.ts` | RK4 + Euler + Velocity Verlet (generic) |
| `orbital.ts` | Classical Keplerian elements + orbit path sampling |
| `frames.ts` | ENU, Earth-centred, ECI frame conversions |
| `stability.ts` | Barrowman CG/CP, fin sets, margin classification |
| `index.ts` | Re-exports |

### Core Domain Layer (9 files, ~1,800 lines)

| File | Role |
|------|------|
| `component-types.ts` | 13-category discriminated union component system |
| `types.ts` | Vehicle, Stage, LaunchSite, MissionConfig, etc. |
| `component-registry.ts` | Component lookup |
| `rocket-design.ts` | Rocket design operations |
| `builder.ts` | Construction/modification API |
| `validation.ts` | Design validation rules |
| `vehicle.ts` | Design → Vehicle conversion (sim-facing flat model) |
| `catalog.ts` | Predefined component catalog |
| `index.ts` | Re-exports |

### Simulation Layer (10 files, ~3,900 lines)

| File | Role |
|------|------|
| `runner.ts` | Full 9-phase flight loop (1,305 lines) |
| `failures.ts` | 13 failure modes, detected + injected, seeded PRNG |
| `mission-state.ts` | 19-state data-driven state machine, 3 profiles |
| `telemetry.ts` | 42-field flat telemetry, sampler, decimation |
| `guidance.ts` | Pitch program, gravity turn, vertical |
| `events.ts` | 25+ event types, FailureDetail |
| `forces.ts` | Force composition (thrust + drag + gravity) |
| `state.ts` | SimulationState, VehicleState, StageState |
| `config.ts` | SimConfig (deterministic flight spec) |
| `index.ts` | Re-exports |

### Renderer Layer (8 files)

| File | Role |
|------|------|
| `scene-manager.ts` | Imperative Three.js lifecycle |
| `rocket-mesh.ts` | Procedural rocket geometry |
| `trajectory.ts` | Trajectory line rendering |
| `planet.ts` | Planet rendering |
| `camera-rig.ts` | Camera controls |
| `effects.ts` | Visual effects (exhaust, etc.) |
| `scale.ts` | Multi-scale coordinate mapping |
| `index.ts` | Re-exports |

### Adapters Layer (4 files)

| File | Role |
|------|------|
| `useSimulation.ts` | React hook for simulation control |
| `useRocketBuilder.ts` | React hook for builder |
| `RocketViewer.tsx` | R3F canvas mount |
| `index.ts` | Re-exports |

### Integration Layer (4 files)

| File | Role |
|------|------|
| `dto.ts` | P2 persistence payloads |
| `ai-export.ts` | P4 mission reports |
| `rkt.ts` | .rkt file format |
| `index.ts` | Re-exports |

### Tests (22 files)

- 9 physics tests, 4 core tests, 6 sim tests, 1 renderer test, 1 integration test, 1 architecture test

## 3. Existing Functionality Summary

All features needed for the MVP simulation are implemented and tested:
- Complete physics models (gravity, atmosphere, drag, thrust, orbital, stability)
- Full flight loop with determinism guarantee
- Data-driven mission state machine
- Comprehensive failure system with educational explanations
- Telemetry generation and sampling
- 3D rendering (rocket, trajectory, planet, camera, effects)
- React integration hooks
- Cross-team DTOs (P2, P4)

## 4. Migration Table

| File | Action | Reason |
|------|--------|--------|
| `physics/*` | **KEEP + PORT to Python** | Pure math; Python gets same values |
| `core/types.ts` (Vehicle, Stage) | **KEEP + SHARED CONTRACT** | Becomes JSON Schema source |
| `core/component-types.ts` | **KEEP** | Builder is browser-facing |
| `core/builder.ts` | **KEEP** | Browser-facing construction |
| `core/validation.ts` | **KEEP + PORT subset** | Preflight validation in Python |
| `core/vehicle.ts` | **KEEP + PORT** | Vehicle conversion in Python |
| `core/catalog.ts` | **KEEP** | Browser-facing catalog |
| `sim/*` | **KEEP + PORT to Python** | Flight loop, state machine, etc. |
| `renderer/*` | **KEEP — NO PORT** | Three.js, browser only |
| `adapters/*` | **KEEP — NO PORT** | React, browser only |
| `integration/*` | **KEEP + EVOLVE** | Add Python Pydantic equivalents |

## 5. New Python Modules

```
simulation/
├── __init__.py
├── engine/
│   ├── __init__.py
│   ├── constants.py        ← from physics/constants.ts
│   ├── vec3.py             ← from physics/vec3.ts (or numpy)
│   ├── config.py           ← from sim/config.ts
│   ├── state.py            ← from sim/state.ts
│   ├── vehicle.py          ← from core/types.ts (Vehicle/Stage)
│   ├── forces.py           ← from sim/forces.ts
│   ├── guidance.py         ← from sim/guidance.ts
│   ├── mission_state.py    ← from sim/mission-state.ts
│   ├── failures.py         ← from sim/failures.ts
│   └── runner.py           ← from sim/runner.ts
├── models/
│   ├── gravity.py          ← from physics/gravity.ts
│   ├── atmosphere.py       ← from physics/atmosphere.ts
│   ├── drag.py             ← from physics/drag.ts
│   ├── thrust.py           ← from physics/thrust.ts
│   ├── orbital.py          ← from physics/orbital.ts
│   └── stability.py        ← from physics/stability.ts
├── integrator/
│   └── rk4.py              ← from physics/integrator.ts
├── telemetry/
│   └── sampler.py          ← from sim/telemetry.ts
├── events/
│   └── types.py            ← from sim/events.ts
└── tests/
    └── ...                  ← mirror TS test coverage
```

## 6. Integration Strategy

**Dual-mode architecture**: Browser TS + Server Python producing identical output shapes.

- **Browser mode** (existing): TS engine in browser/Worker. Zero server dependency.
- **Server mode** (new): Python engine via FastAPI. For batch sims, AI analysis, persistence.
- Both produce identical `SimulationState` / `TelemetryPoint` / `SimEvent`.
- Renderer and adapters consume either transparently.

## 7. Migration Stages

| Stage | Description | Depends On |
|-------|-------------|------------|
| 1 ✅ | Freeze & audit existing code | — |
| 2 | Shared simulation schemas (JSON Schema / Pydantic) | Stage 1 |
| 3 | Python simulation foundation (constants, models, vehicle) | Stage 2 |
| 4 | Port physics (integrators, forces, orbital); cross-validate | Stage 3 |
| 5 | Port flight loop (guidance, state machine, failures, runner) | Stage 4 |
| 6 | FastAPI integration (routes, coordinate with P2) | Stage 5 |
| 7 | TS↔Python connection (SimulationClient, mode switch) | Stage 6 |
| 8 | WebSocket streaming (future) | Stage 7 |
| 9 | TS physics deprecation (future, optional) | Stage 8 |
| 10 | Regression testing at every stage | Continuous |

## 8. Rules

- No existing file is deleted until its Python replacement is validated
- All existing vitest tests must pass at every stage
- Git history is preserved; small commits with clear messages
- No second backend; simulation is a module P2's FastAPI imports
- No second frontend; adapters layer is the P1 interface
