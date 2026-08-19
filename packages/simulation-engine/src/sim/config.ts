/**
 * Simulation configuration — the immutable input to a simulation run.
 *
 * Constructed from a Vehicle + MissionConfig + user settings.
 * Once created, a SimConfig does not change during the simulation.
 *
 * @module sim/config
 */

import type { Vehicle, MissionConfig } from '../core/types.js';

/** Numerical integrator selection. */
export type IntegratorType = 'rk4';

/** Gravity model selection. */
export type GravityModel = 'inverse_square';

/** Atmosphere model selection. */
export type AtmosphereModel = 'us_standard_1976';

/**
 * Simulation solver settings.
 */
export interface SimSettings {
  /** Maximum simulation wall time. Unit: s */
  readonly maxTime_s: number;
  /** Timestep during powered flight. Unit: s */
  readonly dt_powered_s: number;
  /** Timestep during coast/descent. Unit: s */
  readonly dt_coast_s: number;
  /** Integrator to use. */
  readonly integrator: IntegratorType;
  /** Gravity model to use. */
  readonly gravityModel: GravityModel;
  /** Atmosphere model to use. */
  readonly atmosphereModel: AtmosphereModel;
  /** Interval between telemetry samples. Unit: s */
  readonly telemetrySampleInterval_s: number;
}

/** Default simulation settings. */
export const DEFAULT_SIM_SETTINGS: SimSettings = {
  maxTime_s: 600,
  dt_powered_s: 0.05,
  dt_coast_s: 0.1,
  integrator: 'rk4',
  gravityModel: 'inverse_square',
  atmosphereModel: 'us_standard_1976',
  telemetrySampleInterval_s: 1.0,
} as const;

/**
 * The complete, immutable simulation configuration.
 */
export interface SimConfig {
  readonly vehicle: Vehicle;
  readonly mission: MissionConfig;
  readonly settings: SimSettings;
}
