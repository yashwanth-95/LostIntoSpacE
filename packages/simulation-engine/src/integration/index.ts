/**
 * Integration layer — the boundary between P3 and the rest of the team.
 *
 * Nothing here touches a database, an HTTP client, or a filesystem. It produces
 * and consumes plain JSON-safe values, and the transport is somebody else's
 * concern:
 *
 * | Consumer | Uses                                          |
 * |----------|-----------------------------------------------|
 * | **P2**   | `RocketDesignDTO`, `SimulationRunDTO` to store |
 * | **P4**   | `MissionReport` to ground explanations         |
 * | **P1**   | `serializeRkt` / `parseRkt` for save and load  |
 *
 * @module integration
 */

export * from './dto.js';
export * from './ai-export.js';
export * from './rkt.js';
