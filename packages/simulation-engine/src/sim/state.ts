/**
 * Simulation state — the data that evolves during a flight.
 *
 * Everything here is a plain object with no methods and no cycles, so it
 * serializes cleanly for Web Worker transfer, telemetry emission, and JSON
 * persistence. A `SimulationState` can be `structuredClone`d or `JSON.stringify`d
 * as-is.
 *
 * ## Coordinate frame
 *
 * Position and velocity are in the **launch-centred ENU frame** described in
 * `physics/frames.ts`: origin at the launch site, +X east, +Y north, +Z up,
 * axes fixed at t = 0. Altitude is *not* the `z` component — it is the distance
 * above the spherical surface, which differs once the vehicle goes downrange.
 *
 * @module sim/state
 */

import type { Vec3 } from '../physics/vec3.js';
import type { OrbitalElements } from '../physics/orbital.js';
import type { MissionState } from './mission-state.js';
import type { SimEvent } from './events.js';
import type { TelemetryPoint } from './telemetry.js';

/**
 * Coarse flight phase, independent of the mission state machine.
 *
 * Where {@link MissionState} tracks *what the mission is doing*, this tracks
 * *what the physics is doing*. The force model switches on this; the UI reads
 * the mission state.
 */
export type FlightPhase =
  | 'prelaunch'
  | 'powered'
  | 'coast'
  | 'descent'
  | 'terminated';

/** What a stage is doing right now. */
export type StageStatus =
  /** Attached, not yet lit. */
  | 'stowed'
  /** Ignition commanded, waiting out the ignition delay. */
  | 'igniting'
  /** Burning. */
  | 'burning'
  /** Burn finished or commanded off, still attached. */
  | 'shutdown'
  /** Jettisoned. */
  | 'separated'
  /**
   * Failed. The Python engine sets this when a failure disables a stage, and it
   * appears in telemetry, so the union has to be able to name it — a state one
   * engine can emit and the other cannot represent is a silent type lie.
   */
  | 'failed'
  /** Failed; will not fire again. */
  | 'failed';

/** Per-stage state. */
export interface StageState {
  /** Stage index, 0 = bottom. */
  readonly index: number;
  /** Current status. */
  readonly status: StageStatus;
  /** Propellant left in this stage. Unit: kg. */
  readonly propellantRemaining_kg: number;
  /** Time ignition was commanded, or null if not yet. Unit: s. */
  readonly ignitionTime_s: number | null;
  /** Time the engines cut off, or null. Unit: s. */
  readonly cutoffTime_s: number | null;
  /** Time the stage separated, or null. Unit: s. */
  readonly separationTime_s: number | null;
  /** Fraction of the stage's initial propellant still on board, 0–1. */
  readonly propellantFraction: number;
}

/** Commanded attitude. In 3-DOF this is scripted, not integrated. */
export interface Attitude {
  /** Elevation above the local horizontal. π/2 is straight up. Unit: rad. */
  readonly pitch_rad: number;
  /** Compass bearing, clockwise from North. Unit: rad. */
  readonly yaw_rad: number;
  /** Roll about the longitudinal axis. Not modelled in 3-DOF; always 0. Unit: rad. */
  readonly roll_rad: number;
}

/** The physical state of the vehicle. */
export interface VehicleState {
  /** Position in the launch-centred ENU frame. Unit: m. */
  readonly position: Vec3;
  /** Velocity in the same frame. Unit: m/s. */
  readonly velocity: Vec3;
  /** Net acceleration, gravity included. Unit: m/s². */
  readonly acceleration: Vec3;
  /** Commanded attitude. */
  readonly attitude: Attitude;

  /** Total current mass. Unit: kg. */
  readonly mass_kg: number;
  /** Altitude above mean sea level. Unit: m. */
  readonly altitude_m: number;
  /** Speed magnitude. Unit: m/s. */
  readonly speed_ms: number;
  /** Great-circle distance from the launch site. Unit: m. */
  readonly downrange_m: number;
  /** Rate of climb — the radial component of velocity. Unit: m/s. */
  readonly verticalSpeed_ms: number;

  /** Index of the stage currently at the bottom of the stack. */
  readonly activeStage: number;
  /** State of every stage. */
  readonly stages: readonly StageState[];

  /** Coarse flight phase. */
  readonly phase: FlightPhase;
}

/** Whether the simulation is running, and why it stopped if it has. */
export type SimStatus = 'ready' | 'running' | 'paused' | 'complete' | 'failed';

/**
 * The complete simulation state at one instant.
 *
 * This is the object the renderer reads every frame and the object a Web Worker
 * posts back. It is deliberately flat enough to diff cheaply.
 */
export interface SimulationState {
  /** Time since ignition was commanded. Negative during countdown. Unit: s. */
  readonly time_s: number;
  /** Integration steps taken so far. */
  readonly stepCount: number;
  /** Current mission state. */
  readonly missionState: MissionState;
  /** Physical state of the vehicle. */
  readonly vehicle: VehicleState;
  /** The most recent telemetry sample. */
  readonly telemetry: TelemetryPoint;
  /** Every event emitted so far, oldest first. */
  readonly events: readonly SimEvent[];
  /** Run status. */
  readonly status: SimStatus;
  /**
   * Osculating orbital elements, or null while the vehicle is on the pad and a
   * two-body solution would be meaningless.
   */
  readonly orbit: OrbitalElements | null;
  /** Why the run ended, or null while it is still going. */
  readonly terminationReason: string | null;
}

/**
 * Create the stage states for a vehicle at t = 0, all stowed and full.
 *
 * @param propellantByStage - Initial propellant load of each stage. Unit: kg.
 * @returns Freshly initialised stage states.
 */
export function initialStageStates(
  propellantByStage: readonly number[],
): StageState[] {
  return propellantByStage.map((propellant, index) => ({
    index,
    status: 'stowed' as const,
    propellantRemaining_kg: propellant,
    ignitionTime_s: null,
    cutoffTime_s: null,
    separationTime_s: null,
    propellantFraction: propellant > 0 ? 1 : 0,
  }));
}

/**
 * Replace one stage's state, returning a new array.
 *
 * @param stages - Current stage states.
 * @param index - Stage to update.
 * @param patch - Fields to change.
 * @returns A new array with that stage updated. An index that matches nothing
 *   passes through unchanged rather than throwing — the runner never produces
 *   one, and crashing mid-flight would be worse than a no-op.
 */
export function updateStage(
  stages: readonly StageState[],
  index: number,
  patch: Partial<StageState>,
): StageState[] {
  return stages.map(s => (s.index === index ? { ...s, ...patch } : s));
}
