/**
 * Core domain types.
 *
 * Two representations of a rocket coexist in this package, deliberately:
 *
 * - **{@link RocketDesign}** (in `component-types.ts`) — what the *builder*
 *   edits. Components, offsets, connections, overrides. Rich, editable, and
 *   what gets saved.
 * - **{@link Vehicle}** (here) — what the *simulation* consumes. Flat per-stage
 *   numbers with everything already summed. Small, immutable, and cheap to ship
 *   into a Web Worker.
 *
 * `core/vehicle.ts` converts the first into the second. The simulation never
 * sees a component, and the builder never sees a mass flow rate.
 *
 * All values are SI units. See `physics/constants.ts` for reference values.
 *
 * @module core/types
 */

// Re-export the full builder-side domain model.
export type {
  ComponentCategory,
  ThermalProperties,
  StructuralProperties,
  VisualAssetRef,
  FailureMode,
  AttachmentPoint,
  BaseComponentDef,
  ComponentDef,
  BodyDef,
  NoseConeDef,
  EngineDef,
  FuelTankDef,
  OxidizerTankDef,
  AvionicsDef,
  GuidanceDef,
  FinDef,
  PayloadDef,
  DecouplerDef,
  HeatShieldDef,
  LandingLegDef,
  ParachuteDef,
  PropellantType,
  PlacedComponent,
  Connection,
  ConnectionType,
  DesignStage,
  RocketDesign,
  CelestialBody,
  MissionConfiguration,
  FailureDefinition,
} from './component-types.js';
export { COMPONENT_CATEGORIES } from './component-types.js';

// ============================================================
// Simulation-facing vehicle model
// ============================================================

/**
 * One stage as the simulation sees it: a lump of dry mass, a lump of
 * propellant, and an engine that converts the second into thrust.
 *
 * Produced by `core/vehicle.ts` from a whole stage's worth of components.
 */
export interface Stage {
  /** Stage index, 0 = bottom stage, which fires first. */
  readonly stageNumber: number;
  /** Display name. */
  readonly name: string;

  /** Structural mass, jettisoned at separation. Unit: kg. */
  readonly dryMass_kg: number;
  /** Propellant loaded at ignition. Unit: kg. */
  readonly propellantMass_kg: number;

  /** Combined vacuum thrust at the configured throttle. Unit: N. */
  readonly thrustVacuum_N: number;
  /** Combined sea-level thrust at the configured throttle. Unit: N. */
  readonly thrustSeaLevel_N: number;
  /** Flow-weighted vacuum specific impulse. Unit: s. */
  readonly ispVacuum_s: number;
  /** Flow-weighted sea-level specific impulse. Unit: s. */
  readonly ispSeaLevel_s: number;
  /** Combined propellant mass flow while burning. Unit: kg/s. */
  readonly massFlowRate_kgs: number;
  /** Time until the propellant runs out at that flow. Unit: s. */
  readonly burnTime_s: number;

  /** Delay after the stage below separates before this one ignites. Unit: s. */
  readonly ignitionDelay_s: number;
  /** Delay between this stage's cutoff and its separation. Unit: s. */
  readonly separationDelay_s: number;

  /** Whether this stage has engines and propellant and can actually fire. */
  readonly canFire: boolean;
}

/**
 * A rocket reduced to the numbers the flight simulation needs.
 *
 * Fully serializable: no functions, no cycles, safe to `structuredClone` across
 * a Web Worker boundary.
 */
export interface Vehicle {
  /** Display name. */
  readonly name: string;
  /** Id of the design this was built from, for tracing results back. */
  readonly designId: string;

  /** Stages, index 0 = bottom. */
  readonly stages: readonly Stage[];

  /** Payload mass carried to the destination. Unit: kg. */
  readonly payloadMass_kg: number;
  /** Mass on the pad, all stages and propellant included. Unit: kg. */
  readonly launchMass_kg: number;

  /** Nose tip to tail. Unit: m. */
  readonly length_m: number;
  /** Largest diameter. Unit: m. */
  readonly diameter_m: number;
  /** Aerodynamic reference area. Unit: m². */
  readonly referenceArea_m2: number;
  /** Subsonic drag coefficient of the assembled vehicle. Dimensionless. */
  readonly dragCoefficient: number;

  /** Static margin with full tanks. Unit: calibers. */
  readonly stabilityMarginWet_cal: number;
  /** Static margin with empty tanks. Unit: calibers. */
  readonly stabilityMarginDry_cal: number;

  /**
   * Peak axial load the weakest structural component can carry, taken from the
   * component definitions. The failure engine compares the vehicle's actual
   * axial load against it. Unit: N.
   */
  readonly maxAxialLoad_N: number;
  /** Lowest dynamic pressure limit among the components. Unit: Pa. */
  readonly maxDynamicPressure_Pa: number;
}

// ============================================================
// Launch site, environment, and mission
// ============================================================

export interface LaunchSite {
  readonly name: string;
  /** Geodetic latitude. Unit: degrees, [-90, 90]. */
  readonly latitude_deg: number;
  /** Longitude. Unit: degrees, [-180, 180]. */
  readonly longitude_deg: number;
  /** Elevation above mean sea level. Unit: m. */
  readonly altitude_m: number;
}

/**
 * Launch-day conditions.
 *
 * Temperature and pressure are carried for display and for future use; the
 * atmosphere model itself is the standard atmosphere and does not yet accept a
 * local override. Wind is not applied to the force model in v1.
 */
export interface EnvironmentConfig {
  /** Surface temperature. Unit: K. */
  readonly temperature_K: number;
  /** Surface pressure. Unit: Pa. */
  readonly pressure_Pa: number;
  /** Wind speed. Unit: m/s. */
  readonly windSpeed_ms: number;
  /** Wind direction, the compass bearing the wind blows *from*. Unit: degrees. */
  readonly windDirection_deg: number;
}

export type MissionType = 'suborbital' | 'leo' | 'meo' | 'geo' | 'escape';

export interface MissionTarget {
  readonly type: MissionType;
  /** Target altitude above the surface. Unit: km. */
  readonly targetAltitude_km: number;
  /** Target orbital inclination. Unit: degrees. */
  readonly inclination_deg?: number;
}

export interface MissionConfig {
  readonly name: string;
  readonly objective: string;
  readonly target: MissionTarget;
  readonly launchSite: LaunchSite;
  readonly environment: EnvironmentConfig;
}

/** Satish Dhawan Space Centre — the default launch site. */
export const DEFAULT_LAUNCH_SITE: LaunchSite = {
  name: 'Satish Dhawan Space Centre',
  latitude_deg: 13.7199,
  longitude_deg: 80.2304,
  altitude_m: 4,
} as const;

/** Standard-day conditions at sea level. */
export const DEFAULT_ENVIRONMENT: EnvironmentConfig = {
  temperature_K: 288.15,
  pressure_Pa: 101_325,
  windSpeed_ms: 0,
  windDirection_deg: 0,
} as const;
