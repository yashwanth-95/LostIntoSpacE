/**
 * @lostintospace/simulation-engine
 *
 * Physics simulation engine for LostIntoSpacE.
 *
 * Architecture (strict dependency order):
 *   physics  →  core  →  sim  →  renderer  →  adapters
 *
 * Each layer only depends on layers to its left.
 * physics, core, and sim have ZERO browser/UI dependencies.
 *
 * @packageDocumentation
 */

// Layer 1: Physics (pure math, zero deps)
export * from './physics/index.js';

// Layer 1.5: Core domain model (depends on physics)
export * from './core/index.js';

// Layer 2: Simulation engine (depends on physics, core)
export * from './sim/index.js';

// Layer 3 & 4 are imported via subpath exports:
//   import { ... } from '@lostintospace/simulation-engine/renderer'
//   import { ... } from '@lostintospace/simulation-engine/adapters'
// They are NOT re-exported here to avoid pulling in Three.js/React
// for consumers who only need physics/sim.
