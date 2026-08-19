# P3 Engine — Design Decisions

Decisions taken before implementation. Each entry states the choice, the
alternative rejected, and why. This file is the "why"; the other docs in this
folder are the "what".

---

## D1 — Language: TypeScript, not Python

`docs/architecture/ARCHITECTURE.md` (written during initial repo setup) sketches
the simulation engine as a Python library imported by P2's FastAPI process.
The P3 brief specifies Three.js / React Three Fiber / TypeScript / Web Workers,
and the started work is a TypeScript package.

**Decision:** the engine is TypeScript and runs *in the browser* (optionally in a
Web Worker). It is not imported by the Python backend.

**Consequence for P2:** the backend never calls the engine. It persists and
serves the engine's *serialized artifacts* (`RocketDesignDTO`,
`SimulationRunDTO`) as opaque-but-validated JSON. `src/integration/` defines
those payloads and their versioning. This is documented as an open item in
`06-INTEGRATION-API.md` so P2 can confirm.

---

## D2 — Four layers, one-directional dependencies

```
physics → core → sim → renderer → adapters
```

`physics`, `core`, and `sim` import **nothing** outside the package — no Three.js,
no React, no DOM. That is what makes the engine testable in Node, runnable in a
Web Worker, and reusable by P2/P4 without a browser.

`renderer` is Three.js only, no React. `adapters` is the only React layer.
A lint-style test (`tests/architecture.test.ts`) enforces this by scanning
imports, so the boundary cannot rot silently.

---

## D3 — Renderer is imperative Three.js; React only mounts it

Rejected: building the scene from R3F JSX (`<mesh>`, `<line>`…).

Reasons:
1. The simulation loop must not tick React state every frame (§14 of the brief).
   An imperative `SceneManager` reads the latest `SimulationState` inside
   `requestAnimationFrame` and touches zero React internals.
2. It makes the renderer unit-testable in Node — a scene graph can be built and
   asserted on without a WebGL context.
3. It removes `@react-three/fiber` from P3's type surface, so P1 keeps full
   freedom over which R3F version the app uses.

P1 can still use the engine inside an existing R3F canvas: every builder returns
a plain `THREE.Object3D`, droppable via `<primitive object={...} />`.

---

## D4 — Determinism is a hard requirement

No `Math.random()` and no `Date.now()` anywhere in `physics`/`core`/`sim`.

- Failure injection uses a seeded PRNG (`mulberry32`) with the seed carried in
  `SimConfig`. Same seed + same config ⇒ byte-identical telemetry.
- `createRocket()` takes an injectable id factory and clock, defaulting to
  deterministic counters, so designs are reproducible in tests and diffable.
- Fixed-step RK4 (no adaptive stepping) so step count is a pure function of config.

`tests/sim/determinism.test.ts` asserts two independent runs produce identical
output.

---

## D5 — Station convention for mass/aero properties

The pre-existing `physics/stability.ts` mixed two conventions: `centerOfGravity`
summed ENU `z` (up-positive, measured from the base) while `noseConeCP` returned
a distance aft of the nose tip. The resulting stability margin was meaningless.

**Decision:** all longitudinal mass/aero properties use a single **station**
axis: `x = 0` at the nose tip, increasing **aft**. Conversion from the design's
bottom-up layout happens once, in `core/vehicle.ts`. The ENU `z` frame is used
only for trajectory state.

---

## D6 — Mass is integrated analytically, not by RK4

Propellant flow is constant during a burn, so `m(t) = m₀ − ṁ·(t − t₀)` is exact.
RK4 integrates only position and velocity, evaluating mass analytically at each
substep. This is operator splitting and is *more* accurate here than folding mass
into the state vector, as well as cheaper.

---

## D7 — 3-DOF with a scripted attitude

Full 6-DOF (rotational dynamics, moments, gimbal control loops) is out of scope
for v1 per §8 of the brief. Attitude is *scripted* by a pitch program
(`sim/guidance.ts`); thrust is applied along the commanded attitude. Stability
margin is computed and reported as an **educational indicator** and can trigger a
failure, but it does not feed back into rotational motion.

The force model is behind a `ForceModel` interface so a 6-DOF model can be added
later without touching the runner.

---

## D8 — Simulation state machine is data, not code branches

Mission states (§9) are declared as a transition table with guard predicates.
A mission profile selects which states participate. Adding `TRANSFER` or
`SURFACE` to a mission means adding a row, not editing the runner.
