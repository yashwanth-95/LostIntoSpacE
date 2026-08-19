/**
 * Telemetry — the sampled time series a flight produces.
 *
 * A {@link TelemetryPoint} is a flat record of primitives. That shape is
 * deliberate and worth defending: it maps one-to-one onto a database row for
 * P2, charts directly for P1, and can be handed to P4 as a table without any
 * traversal logic. Nested objects here would cost all three of those.
 *
 * ## Sampling
 *
 * The integrator runs at 0.05 s but nobody needs 20 samples per second for ten
 * minutes of flight. The sampler emits on a fixed interval, and *always* emits
 * on a step where an event fired, so the timeline never loses the moment
 * something happened between grid points.
 *
 * @module sim/telemetry
 */

import { G0 } from '../physics/constants.js';
import type { Vec3 } from '../physics/vec3.js';
import type { OrbitalElements } from '../physics/orbital.js';
import type { MissionState } from './mission-state.js';
import type { FlightPhase, StageStatus } from './state.js';

/**
 * One telemetry sample.
 *
 * Every field is a number, string, or boolean — no nesting — so this maps
 * directly onto a table row or a chart series.
 */
export interface TelemetryPoint {
  /** Time since ignition. Unit: s. */
  readonly t: number;

  // --- Position and motion ---
  /** Altitude above mean sea level. Unit: m. */
  readonly altitude_m: number;
  /** Great-circle distance from the launch site. Unit: m. */
  readonly downrange_m: number;
  /** ENU east component of position. Unit: m. */
  readonly position_x_m: number;
  /** ENU north component of position. Unit: m. */
  readonly position_y_m: number;
  /** ENU up component of position. Unit: m. */
  readonly position_z_m: number;
  /** Speed magnitude. Unit: m/s. */
  readonly speed_ms: number;
  /** Rate of climb. Unit: m/s. */
  readonly verticalSpeed_ms: number;
  /** Horizontal speed component. Unit: m/s. */
  readonly horizontalSpeed_ms: number;
  /** Net acceleration magnitude. Unit: m/s². */
  readonly acceleration_ms2: number;
  /**
   * Load factor felt on board, in multiples of standard gravity.
   *
   * This is the *non-gravitational* acceleration — thrust and drag — which is
   * what an accelerometer or a crew member actually experiences. A vehicle in
   * free fall reads 0 g here even though it is accelerating at 9.8 m/s².
   */
  readonly gLoad_g: number;

  // --- Mass and propulsion ---
  /** Current total mass. Unit: kg. */
  readonly mass_kg: number;
  /** Propellant remaining in the active stage. Unit: kg. */
  readonly fuelRemaining_kg: number;
  /** Fraction of the active stage's propellant remaining, 0–1. */
  readonly fuelFraction: number;
  /** Current total thrust. Unit: N. */
  readonly thrust_N: number;
  /** Current propellant flow. Unit: kg/s. */
  readonly massFlow_kgs: number;
  /** Thrust-to-weight ratio right now. Dimensionless. */
  readonly twr: number;

  // --- Atmosphere and aerodynamics ---
  /** Drag force magnitude. Unit: N. */
  readonly drag_N: number;
  /** Dynamic pressure. Unit: Pa. */
  readonly dynamicPressure_Pa: number;
  /** Mach number. Dimensionless. */
  readonly mach: number;
  /** Ambient air density. Unit: kg/m³. */
  readonly airDensity_kgm3: number;
  /** Ambient static pressure. Unit: Pa. */
  readonly ambientPressure_Pa: number;

  // --- Attitude ---
  /** Commanded pitch above the local horizontal. Unit: rad. */
  readonly pitch_rad: number;
  /** Commanded compass heading. Unit: rad. */
  readonly yaw_rad: number;
  /** Angle between the thrust axis and the velocity vector. Unit: rad. */
  readonly angleOfAttack_rad: number;

  // --- Orbital state ---
  /** Semi-major axis, or 0 while it is meaningless. Unit: m. */
  readonly semiMajorAxis_m: number;
  /** Eccentricity. Dimensionless. */
  readonly eccentricity: number;
  /** Periapsis altitude. Unit: m. */
  readonly periapsisAltitude_m: number;
  /** Apoapsis altitude, or 0 for an open trajectory. Unit: m. */
  readonly apoapsisAltitude_m: number;
  /** Inclination relative to the equator. Unit: rad. */
  readonly inclination_rad: number;
  /** Whether the current state describes a closed orbit clear of the surface. */
  readonly inOrbit: boolean;

  // --- Discrete state ---
  /** Index of the stage at the bottom of the stack. */
  readonly stage: number;
  /** Status of that stage. */
  readonly stageStatus: StageStatus;
  /** Whether any engine is producing thrust. */
  readonly engineOn: boolean;
  /** Mission state machine state. */
  readonly missionState: MissionState;
  /** Coarse flight phase. */
  readonly phase: FlightPhase;
}

/** A zeroed telemetry point, used before the first sample exists. */
export const EMPTY_TELEMETRY: TelemetryPoint = Object.freeze({
  t: 0,
  altitude_m: 0,
  downrange_m: 0,
  position_x_m: 0,
  position_y_m: 0,
  position_z_m: 0,
  speed_ms: 0,
  verticalSpeed_ms: 0,
  horizontalSpeed_ms: 0,
  acceleration_ms2: 0,
  gLoad_g: 0,
  mass_kg: 0,
  fuelRemaining_kg: 0,
  fuelFraction: 0,
  thrust_N: 0,
  massFlow_kgs: 0,
  twr: 0,
  drag_N: 0,
  dynamicPressure_Pa: 0,
  mach: 0,
  airDensity_kgm3: 0,
  ambientPressure_Pa: 0,
  pitch_rad: Math.PI / 2,
  yaw_rad: 0,
  angleOfAttack_rad: 0,
  semiMajorAxis_m: 0,
  eccentricity: 0,
  periapsisAltitude_m: 0,
  apoapsisAltitude_m: 0,
  inclination_rad: 0,
  inOrbit: false,
  stage: 0,
  stageStatus: 'stowed',
  engineOn: false,
  missionState: 'PREPARATION',
  phase: 'prelaunch',
});

/** Everything needed to build a telemetry point. */
export interface TelemetryInputs {
  readonly t: number;
  readonly position: Vec3;
  readonly velocity: Vec3;
  readonly acceleration: Vec3;
  readonly altitude_m: number;
  readonly downrange_m: number;
  readonly verticalSpeed_ms: number;
  readonly mass_kg: number;
  readonly fuelRemaining_kg: number;
  readonly fuelFraction: number;
  readonly thrust_N: number;
  readonly massFlow_kgs: number;
  readonly drag_N: number;
  readonly dynamicPressure_Pa: number;
  readonly mach: number;
  readonly airDensity_kgm3: number;
  readonly ambientPressure_Pa: number;
  readonly localGravity_ms2: number;
  readonly pitch_rad: number;
  readonly yaw_rad: number;
  readonly angleOfAttack_rad: number;
  readonly orbit: OrbitalElements | null;
  readonly stage: number;
  readonly stageStatus: StageStatus;
  readonly engineOn: boolean;
  readonly missionState: MissionState;
  readonly phase: FlightPhase;
}

/** Magnitude of a vector, inlined to avoid an import cycle on the hot path. */
function mag(v: Vec3): number {
  return Math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
}

/**
 * Assemble a telemetry point from simulation state.
 *
 * @param inputs - Everything measured this step.
 * @returns A complete, flat telemetry sample.
 */
export function buildTelemetryPoint(inputs: TelemetryInputs): TelemetryPoint {
  const speed_ms = mag(inputs.velocity);
  const horizontalSpeed_ms = Math.sqrt(
    Math.max(0, speed_ms * speed_ms - inputs.verticalSpeed_ms * inputs.verticalSpeed_ms),
  );

  // Load factor is what an accelerometer reads: the non-gravitational forces
  // only. Thrust and drag divided by mass, expressed in g.
  const specificForce_ms2 =
    inputs.mass_kg > 0 ? (inputs.thrust_N + inputs.drag_N) / inputs.mass_kg : 0;

  const weight_N = inputs.mass_kg * inputs.localGravity_ms2;

  return {
    t: inputs.t,
    altitude_m: inputs.altitude_m,
    downrange_m: inputs.downrange_m,
    position_x_m: inputs.position.x,
    position_y_m: inputs.position.y,
    position_z_m: inputs.position.z,
    speed_ms,
    verticalSpeed_ms: inputs.verticalSpeed_ms,
    horizontalSpeed_ms,
    acceleration_ms2: mag(inputs.acceleration),
    gLoad_g: specificForce_ms2 / G0,
    mass_kg: inputs.mass_kg,
    fuelRemaining_kg: inputs.fuelRemaining_kg,
    fuelFraction: inputs.fuelFraction,
    thrust_N: inputs.thrust_N,
    massFlow_kgs: inputs.massFlow_kgs,
    twr: weight_N > 0 ? inputs.thrust_N / weight_N : 0,
    drag_N: inputs.drag_N,
    dynamicPressure_Pa: inputs.dynamicPressure_Pa,
    mach: inputs.mach,
    airDensity_kgm3: inputs.airDensity_kgm3,
    ambientPressure_Pa: inputs.ambientPressure_Pa,
    pitch_rad: inputs.pitch_rad,
    yaw_rad: inputs.yaw_rad,
    angleOfAttack_rad: inputs.angleOfAttack_rad,
    semiMajorAxis_m: inputs.orbit && Number.isFinite(inputs.orbit.semiMajorAxis_m)
      ? inputs.orbit.semiMajorAxis_m
      : 0,
    eccentricity: inputs.orbit?.eccentricity ?? 0,
    periapsisAltitude_m: inputs.orbit?.periapsisAltitude_m ?? 0,
    apoapsisAltitude_m:
      inputs.orbit && Number.isFinite(inputs.orbit.apoapsisAltitude_m)
        ? inputs.orbit.apoapsisAltitude_m
        : 0,
    inclination_rad: inputs.orbit?.inclination_rad ?? 0,
    inOrbit: inputs.orbit?.isStableOrbit ?? false,
    stage: inputs.stage,
    stageStatus: inputs.stageStatus,
    engineOn: inputs.engineOn,
    missionState: inputs.missionState,
    phase: inputs.phase,
  };
}

/**
 * Decides which steps become telemetry samples.
 *
 * Emits on a fixed interval, and unconditionally on any step where an event
 * fired so the record never misses a milestone that landed between grid points.
 */
export class TelemetrySampler {
  private readonly _points: TelemetryPoint[] = [];
  private _nextSampleTime_s: number;

  /**
   * @param interval_s - Seconds between routine samples. Unit: s. Must be > 0.
   * @param startTime_s - Time of the first sample. Unit: s.
   */
  constructor(
    private readonly interval_s: number,
    startTime_s = 0,
  ) {
    if (interval_s <= 0) {
      throw new RangeError(`interval_s must be > 0, got ${interval_s}`);
    }
    this._nextSampleTime_s = startTime_s;
  }

  /**
   * Offer a sample. It is kept if the interval has elapsed or if something
   * happened this step.
   *
   * @param point - The candidate sample.
   * @param forceEmit - Emit regardless of the interval, for event steps.
   * @returns True if the point was recorded.
   */
  offer(point: TelemetryPoint, forceEmit = false): boolean {
    if (!forceEmit && point.t < this._nextSampleTime_s) {
      return false;
    }
    this._points.push(point);
    // Advance to the next grid slot at or after this sample, so a forced emit
    // between slots does not shift the whole grid.
    while (this._nextSampleTime_s <= point.t) {
      this._nextSampleTime_s += this.interval_s;
    }
    return true;
  }

  /** Every sample recorded so far, oldest first. */
  get points(): readonly TelemetryPoint[] {
    return this._points;
  }

  /** How many samples have been recorded. */
  get length(): number {
    return this._points.length;
  }

  /** The most recent sample, or undefined if none yet. */
  get latest(): TelemetryPoint | undefined {
    return this._points[this._points.length - 1];
  }

  /** Discard everything and restart the sampling grid. */
  reset(startTime_s = 0): void {
    this._points.length = 0;
    this._nextSampleTime_s = startTime_s;
  }
}

/**
 * Reduce a telemetry series to at most `maxPoints`, keeping the extremes.
 *
 * Straight decimation would drop the apogee and the max-Q peak, which are
 * exactly the samples a chart must not lose. This walks the series in buckets
 * and keeps the first, last, highest, and fastest point of each.
 *
 * @param points - Full-resolution series.
 * @param maxPoints - Target maximum. Values below 4 are treated as 4.
 * @returns A reduced series in time order, with duplicates removed.
 */
export function decimateTelemetry(
  points: readonly TelemetryPoint[],
  maxPoints: number,
): TelemetryPoint[] {
  const target = Math.max(4, maxPoints);
  if (points.length <= target) return [...points];

  const bucketCount = Math.floor(target / 4);
  const bucketSize = Math.ceil(points.length / bucketCount);
  const kept = new Set<TelemetryPoint>();

  for (let start = 0; start < points.length; start += bucketSize) {
    const end = Math.min(points.length, start + bucketSize);
    let highest = points[start]!;
    let fastest = points[start]!;

    for (let i = start; i < end; i++) {
      const p = points[i]!;
      if (p.altitude_m > highest.altitude_m) highest = p;
      if (p.speed_ms > fastest.speed_ms) fastest = p;
    }

    kept.add(points[start]!);
    kept.add(points[end - 1]!);
    kept.add(highest);
    kept.add(fastest);
  }

  return [...kept].sort((a, b) => a.t - b.t);
}
