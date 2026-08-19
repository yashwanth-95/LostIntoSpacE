/**
 * Simulation engine — state machine, integrator, telemetry, events.
 *
 * This layer depends on physics/ and core/.
 * It must NEVER import Three.js, React, or browser APIs.
 * It can run in a Web Worker.
 *
 * @module sim
 */

export * from './state.js';
export * from './config.js';
export * from './events.js';

// Future exports (uncomment as implemented):
// export * from './runner.js';
// export * from './integrator.js';
// export * from './failures.js';
// export * from './telemetry.js';
// export * from './result.js';
