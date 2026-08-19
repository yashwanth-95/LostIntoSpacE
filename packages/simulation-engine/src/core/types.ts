/**
 * Core domain types for rocket vehicles, missions, and components.
 *
 * This file re-exports the comprehensive domain model from component-types
 * and provides backward-compatible aliases used by the simulation layer.
 *
 * All values are SI units. See physics/constants.ts for reference values.
 *
 * @module core/types
 */

import type { Vec3 } from '../physics/vec3.js';

// Re-export full domain model
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
// Backward-compatible types for simulation layer
// ============================================================

/**
 * Legacy component type alias.
 * Used by physics/stability.ts. Maps to categories that the sim cares about.
 */
export type ComponentType =
  | 'nose'
  | 'body'
  | 'fins'
  | 'engine'
  | 'payload'
  | 'recovery'
  | 'avionics';

/**
 * A placed component compatible with the simulation layer.
 * Used by physics/stability.ts for CG/CP calculations.
 */
export interface RocketComponent {
  readonly id: string;
  readonly type: ComponentType;
  readonly name: string;
  readonly mass_kg: number;
  readonly position: Vec3;
  readonly dimensions: Readonly<Record<string, number>>;
  readonly parentId?: string;
  readonly sortOrder: number;
}

/**
 * Simulation-compatible stage definition.
 * Aggregated from component definitions for sim input.
 */
export interface Stage {
  readonly stageNumber: number;
  readonly name: string;
  readonly dryMass_kg: number;
  readonly propellantMass_kg: number;
  readonly thrust_N: number;
  readonly isp_s: number;
  readonly burnTime_s: number;
  readonly dragCoefficient: number;
  readonly referenceArea_m2: number;
  readonly separationDelay_s: number;
}

/**
 * Simulation-compatible vehicle definition.
 * Created by converting a RocketDesign + registry into sim-ready data.
 */
export interface Vehicle {
  readonly name: string;
  readonly stages: readonly Stage[];
  readonly components: readonly RocketComponent[];
}

// ============================================================
// Launch & Mission (unchanged, used by sim/config)
// ============================================================

export interface LaunchSite {
  readonly name: string;
  readonly latitude_deg: number;
  readonly longitude_deg: number;
  readonly altitude_m: number;
}

export interface EnvironmentConfig {
  readonly temperature_K: number;
  readonly pressure_Pa: number;
  readonly windSpeed_ms: number;
  readonly windDirection_deg: number;
}

export type MissionType = 'suborbital' | 'leo' | 'meo' | 'geo' | 'escape';

export interface MissionTarget {
  readonly type: MissionType;
  readonly targetAltitude_km: number;
  readonly inclination_deg?: number;
}

export interface MissionConfig {
  readonly name: string;
  readonly objective: string;
  readonly target: MissionTarget;
  readonly launchSite: LaunchSite;
  readonly environment: EnvironmentConfig;
}
