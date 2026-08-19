/**
 * Simulation state — the mutable data that evolves during each timestep.
 *
 * This is a plain object (not a class) to ensure clean serialization
 * for Web Worker transfer, telemetry emission, and JSON persistence.
 *
 * Coordinate frame: East-North-Up (ENU) with origin at launch site.
 *
 * @module sim/state
 */

import type { Vec3 } from '../physics/vec3.js';

/** Phases of a rocket mission. */
export type MissionPhase =
  | 'prelaunch'
  | 'powered'
  | 'coast'
  | 'descent'
  | 'terminated';

/**
 * The complete simulation state at a single point in time.
 *
 * Every field uses SI units. See physics/constants.ts.
 */
export interface SimState {
  /** Simulation time since ignition. Unit: s */
  readonly t: number;
  /** Position in ENU frame from launch site. Unit: m */
  readonly position: Vec3;
  /** Velocity in ENU frame. Unit: m/s */
  readonly velocity: Vec3;
  /** Net acceleration. Unit: m/s² */
  readonly acceleration: Vec3;
  /** Current total mass (vehicle + remaining propellant). Unit: kg */
  readonly mass_kg: number;
  /** Attitude angles [pitch, yaw, roll]. Unit: rad */
  readonly attitude: Vec3;
  /** Index of the currently active stage (0-based). */
  readonly activeStage: number;
  /** Current mission phase. */
  readonly phase: MissionPhase;
  /** Integration step counter. */
  readonly stepCount: number;
}
