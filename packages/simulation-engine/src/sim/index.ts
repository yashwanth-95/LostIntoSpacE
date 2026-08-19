/**
 * Simulation engine — state machine, integrator, telemetry, events, failures.
 *
 * Depends on `physics/` and `core/` only. It must never import Three.js, React,
 * or a browser API, which is what lets it run in Node and in a Web Worker.
 *
 * @module sim
 */

export * from './state.js';
export * from './config.js';
export * from './events.js';
export * from './mission-state.js';
export * from './telemetry.js';
export * from './guidance.js';
export * from './failures.js';
export * from './forces.js';
export * from './runner.js';
