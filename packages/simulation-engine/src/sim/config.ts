/**
 * Simulation configuration — the immutable input to a run.
 *
 * A `SimConfig` fully determines a simulation. Two runs with equal configs
 * produce byte-identical telemetry, which is the property the whole engine is
 * built around: it is what lets P2 store a config instead of a result, lets P4
 * re-derive a flight to explain it, and lets tests assert on exact numbers.
 *
 * @module sim/config
 */

import type { Vehicle, MissionConfig } from '../core/types.js';
import type { IntegratorMethod } from '../physics/integrator.js';
import type { MissionProfile } from './mission-state.js';
import { SUBORBITAL_PROFILE } from './mission-state.js';
import type { FailureConfig } from './failures.js';
import { DEFAULT_FAILURE_CONFIG } from './failures.js';
import type { GuidanceConfig } from './guidance.js';
import { DEFAULT_GUIDANCE } from './guidance.js';

/** Gravity model selection. Only one model exists today. */
export type GravityModel = 'inverse_square';

/** Atmosphere model selection. Only one model exists today. */
export type AtmosphereModel = 'us_standard_1976';

/** Numerical and sampling settings. */
export interface SimSettings {
  /** Hard stop on simulated flight time. Unit: s. */
  readonly maxTime_s: number;
  /** Timestep while any engine is burning. Unit: s. */
  readonly dt_powered_s: number;
  /**
   * Timestep while coasting. Unit: s.
   *
   * Larger than the powered step because nothing changes quickly during a
   * coast — no mass flow, and usually no atmosphere. Running a 400 km apogee
   * coast at the powered step would waste tens of thousands of evaluations on
   * a smooth conic.
   */
  readonly dt_coast_s: number;
  /** Integrator. */
  readonly integrator: IntegratorMethod;
  /** Gravity model. */
  readonly gravityModel: GravityModel;
  /** Atmosphere model. */
  readonly atmosphereModel: AtmosphereModel;
  /** Seconds between routine telemetry samples. Unit: s. */
  readonly telemetrySampleInterval_s: number;
  /** Countdown length before ignition. Unit: s. */
  readonly countdown_s: number;
  /** Whether the vehicle's Cd is scaled by the transonic drag rise. */
  readonly useMachDragRise: boolean;
  /** Whether thrust and Isp vary with ambient pressure. */
  readonly useAltitudeCompensation: boolean;
  /**
   * Hard cap on integration steps.
   *
   * A backstop against a configuration that would otherwise spin — a coast step
   * of zero, say. Reaching it terminates the run with an explicit reason rather
   * than hanging the browser tab.
   */
  readonly maxSteps: number;
}

/** Default settings: the values every reference run in the docs uses. */
export const DEFAULT_SIM_SETTINGS: SimSettings = {
  maxTime_s: 1_200,
  dt_powered_s: 0.05,
  dt_coast_s: 0.5,
  integrator: 'rk4',
  gravityModel: 'inverse_square',
  atmosphereModel: 'us_standard_1976',
  telemetrySampleInterval_s: 1.0,
  countdown_s: 3.0,
  useMachDragRise: true,
  useAltitudeCompensation: true,
  maxSteps: 2_000_000,
} as const;

/** When a run should stop. */
export interface TerminationConfig {
  /** Stop when the vehicle reaches the surface. */
  readonly onImpact: boolean;
  /** Stop when a closed orbit clear of the atmosphere is achieved. */
  readonly onStableOrbit: boolean;
  /** Stop when the mission's target altitude is first reached. */
  readonly onTargetAltitude: boolean;
  /** Stop on the first terminal failure. */
  readonly onFatalFailure: boolean;
  /** Stop once the state machine reaches a terminal state. */
  readonly onMissionComplete: boolean;
}

/** Default termination rules. */
export const DEFAULT_TERMINATION: TerminationConfig = {
  onImpact: true,
  onStableOrbit: false,
  onTargetAltitude: false,
  onFatalFailure: true,
  onMissionComplete: true,
} as const;

/** The complete, immutable input to a simulation run. */
export interface SimConfig {
  /** The vehicle to fly. */
  readonly vehicle: Vehicle;
  /** Mission objective, launch site, and environment. */
  readonly mission: MissionConfig;
  /** Which mission states participate. */
  readonly profile: MissionProfile;
  /** Numerical and sampling settings. */
  readonly settings: SimSettings;
  /** Attitude program. */
  readonly guidance: GuidanceConfig;
  /** Failure detection and injection. */
  readonly failures: FailureConfig;
  /** Termination rules. */
  readonly termination: TerminationConfig;
}

/** Overrides accepted by {@link createSimConfig}. */
export interface SimConfigOverrides {
  readonly profile?: MissionProfile;
  readonly settings?: Partial<SimSettings>;
  readonly guidance?: Partial<GuidanceConfig>;
  readonly failures?: Partial<FailureConfig>;
  readonly termination?: Partial<TerminationConfig>;
}

/**
 * Build a complete config from a vehicle, a mission, and optional overrides.
 *
 * Every field the simulation reads gets a value here, so the runner never has to
 * cope with a partially specified config.
 *
 * @param vehicle - Vehicle to fly.
 * @param mission - Mission objective and launch conditions.
 * @param overrides - Anything to change from the defaults.
 * @returns A fully populated config.
 */
export function createSimConfig(
  vehicle: Vehicle,
  mission: MissionConfig,
  overrides: SimConfigOverrides = {},
): SimConfig {
  return {
    vehicle,
    mission,
    profile: overrides.profile ?? SUBORBITAL_PROFILE,
    settings: { ...DEFAULT_SIM_SETTINGS, ...overrides.settings },
    guidance: { ...DEFAULT_GUIDANCE, ...overrides.guidance },
    failures: { ...DEFAULT_FAILURE_CONFIG, ...overrides.failures },
    termination: { ...DEFAULT_TERMINATION, ...overrides.termination },
  };
}
