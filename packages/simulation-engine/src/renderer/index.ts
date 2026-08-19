/**
 * 3D renderer — Three.js visualisation of rockets, trajectories, and planets.
 *
 * Consumes simulation data read-only and draws it. Depends on `three` and on
 * the package's own `core/` and `sim/` types; it must **not** import React.
 * That boundary is what lets P1 use these builders inside any React Three Fiber
 * version, or none at all.
 *
 * Every builder returns a plain `THREE.Object3D`, so they drop into an existing
 * R3F scene through `<primitive object={...} />` just as easily as into the
 * imperative {@link createSceneManager}.
 *
 * @module renderer
 */

export * from './scale.js';
export * from './rocket-mesh.js';
export * from './trajectory.js';
export * from './planet.js';
export * from './effects.js';
export * from './camera-rig.js';
export * from './scene-manager.js';
