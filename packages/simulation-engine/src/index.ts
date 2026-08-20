/**
 * @lostintospace/simulation-engine
 *
 * Physics simulation engine for LostIntoSpacE.
 *
 * ## Architecture
 *
 * ```
 * physics  →  core  →  sim  →  renderer  →  adapters
 *                        ↘  integration
 * ```
 *
 * Each layer depends only on those to its left. `physics`, `core`, and `sim`
 * have zero browser or UI dependencies and run unchanged in Node, in a browser,
 * and in a Web Worker — a boundary `tsconfig.headless.json` enforces at build
 * time by compiling them without the DOM library.
 *
 * ## Entry points
 *
 * ```ts
 * // Physics, domain model, and simulation — no browser dependency
 * import { runSimulation, analyzeRocket } from '@lostintospace/simulation-engine';
 *
 * // 3D rendering (requires `three`)
 * import { createSceneManager } from '@lostintospace/simulation-engine/renderer';
 *
 * // React integration (requires `react`)
 * import { useSimulation, RocketViewer } from '@lostintospace/simulation-engine/adapters';
 *
 * // Serialization and cross-team payloads
 * import { toSimulationRunDTO, buildMissionReport } from '@lostintospace/simulation-engine/integration';
 * ```
 *
 * `renderer` and `adapters` are reachable only through their subpaths, so a
 * consumer that only needs physics never pulls Three.js or React into its
 * bundle.
 *
 * @packageDocumentation
 */

// Layer 1: Physics — pure math, zero dependencies
export * from './physics/index.js';

// Layer 2: Core domain model — depends on physics
export * from './core/index.js';

// Layer 3: Simulation engine — depends on physics and core
export * from './sim/index.js';

// Layer 4: Integration — serialization and cross-team payloads.
// Included here because it has no browser dependency either.
export * from './integration/index.js';

// Parametric geometry: the shapes the builder draws and the physics flies.
export * from './geometry/index.js';
