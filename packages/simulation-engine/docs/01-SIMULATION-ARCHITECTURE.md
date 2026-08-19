# 1 — Simulation Architecture

## Layers

```
┌──────────────────────────────────────────────────────────────┐
│ adapters/     React hooks + the canvas-mounting component      │
│               imports: react, renderer, sim, core              │
├──────────────────────────────────────────────────────────────┤
│ renderer/     Three.js scene graph, meshes, camera             │
│               imports: three, sim, core, physics               │
├──────────────────────────────────────────────────────────────┤
│ integration/  DTOs, .rkt files, AI mission report              │
│               imports: sim, core, physics                      │
├──────────────────────────────────────────────────────────────┤
│ sim/          Flight loop, state machine, telemetry, failures  │
│               imports: core, physics                           │
├──────────────────────────────────────────────────────────────┤
│ core/         Components, designs, builder analysis, vehicle   │
│               imports: physics                                 │
├──────────────────────────────────────────────────────────────┤
│ physics/      Constants, vectors, frames, models, integrators  │
│               imports: nothing                                 │
└──────────────────────────────────────────────────────────────┘
```

Dependencies point **downward only**. `physics`, `core`, `sim`, and
`integration` import nothing outside the package — no Three.js, no React, no
DOM. That is what lets the engine run in Node, in a browser, and in a Web
Worker without modification.

The boundary is enforced two ways, so it cannot rot quietly:

- `tsconfig.headless.json` compiles those four layers with `lib: ["ES2022"]`
  and no DOM. Reaching for `window` or `document` fails the build.
- `tests/architecture.test.ts` reads every source file and fails on a
  disallowed import, a `Math.random()` in a deterministic layer, or a
  wall-clock read inside `sim/`.

## The separation the brief mandates

> Separate PHYSICS from SIMULATION STATE from RENDERING from UI.

| Concern | Where | Shape |
|---|---|---|
| **Physics** | `physics/` | Pure functions. No state, no time, no vehicle. |
| **Simulation state** | `sim/state.ts` | Plain data. No methods, no cycles, `structuredClone`-safe. |
| **Simulation behaviour** | `sim/runner.ts` | The only place state mutates. |
| **Rendering** | `renderer/` | Reads state, never writes it. Owns no simulation. |
| **UI** | `adapters/` | Binds React to the two above. Contains no physics. |

A concrete consequence: `physics/integrator.ts` knows how to advance a
position and velocity but has never heard of a rocket, which is why it can be
tested against free fall, a harmonic oscillator, and a closed circular orbit
rather than against a rocket that might itself be wrong.

## The flight loop

`Simulation.step()` advances the state from `t` to `t + dt` in nine phases:

```
1. Sequencing      ignite / cut off / separate stages whose time has come
2. Guidance        compute the commanded attitude
3. Forces          thrust, drag, gravity at the current state
4. Integrate       advance position and velocity (RK4 by default)
5. Mass            deplete propellant analytically
6. Failures        run detection rules and scripted injections
7. Mission state   advance the state machine, emit its events
8. Telemetry       sample if the interval elapsed or an event fired
9. Termination     check the stop conditions
```

### Timing convention

Phases 1–4 make decisions from the state at the **start** of the step, which is
the only state actually known. Everything **recorded** — event timestamps,
ignition and cutoff times, telemetry — is stamped at `t + dt`, because that is
the state the resulting telemetry row describes.

Without that split, a cutoff event lands one timestep before the telemetry row
showing the engine off, and the two records disagree. This package had exactly
that bug; `tests/sim/runner.test.ts` now asserts that every event has a
telemetry sample at the same instant.

## Mass integration

Propellant flow is constant while an engine burns, so mass is *exactly* linear
in time:

```
m(t) = m₀ − ṁ·(t − t₀)
```

Folding mass into the RK4 state vector would add error rather than remove it.
Instead the acceleration function evaluates mass analytically at each substep
time. This is operator splitting, and here the split is exact.

## Timestep

| Phase | Step | Why |
|---|---|---|
| Powered | 0.05 s | Mass, thrust, and dynamic pressure all change quickly. |
| Coast | 0.5 s | Nothing changes fast; a smooth conic does not need 20 Hz. |

A 500-second orbital ascent runs in roughly 10 500 steps and completes in about
150 ms — see `tests/sim/performance.test.ts` for the measured budgets.

## Determinism

A `SimConfig` fully determines a flight. There is no `Math.random()` and no
wall-clock read anywhere in `physics`, `core`, or `sim`:

- Failure injection uses a seeded `mulberry32` generator carried in the config.
- Fixed-step integration, so the step count is a pure function of the config.
- `createRocket()` takes an injectable id and timestamp; design operations are
  pure and do not stamp times (`touch()` does that, at save time).

`tests/sim/determinism.test.ts` asserts *byte-identical* telemetry across
independent runs, across `run()` versus repeated `step()`, and across
pause/resume cycles.

This is what lets P2 store a config instead of a result, lets P4 re-derive a
flight to explain it, and lets a lesson guarantee every student sees the same
failure.

## Extension points

| To add | Change | Nothing else moves |
|---|---|---|
| A new force (lift, wind) | `sim/forces.ts` | Runner, state, telemetry |
| A new integrator | `physics/integrator.ts` + `IntegratorMethod` | Force model |
| A new mission shape | A row in `MISSION_TRANSITIONS`, a `MissionProfile` | Runner |
| A new failure mode | An entry in `FAILURE_MODES` | Runner, events |
| A new component type | A member of the `ComponentDef` union | Simulation |
| 6-DOF dynamics | A new `ForceModel` behind the same interface | Runner |
