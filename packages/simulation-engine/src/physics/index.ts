/**
 * Physics layer — pure mathematical models with zero external dependencies.
 *
 * This layer can run in Node, browser, or Web Worker.
 * It must NEVER import Three.js, React, or browser APIs.
 *
 * @module physics
 */

export * from './constants.js';
export * from './vec3.js';
export * from './frames.js';
export * from './gravity.js';
export * from './atmosphere.js';
export * from './drag.js';
export * from './thrust.js';
export * from './stability.js';
export * from './orbital.js';
export * from './integrator.js';
