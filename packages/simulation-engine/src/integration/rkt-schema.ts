/**
 * The `.rkt` project schema.
 *
 * `.rkt` is LostIntoSpacE's native project format: a complete, portable,
 * versioned description of a rocket project. Opening one reconstructs the
 * vehicle exactly as it was saved — not approximately, not the parts of it the
 * UI happens to read, but the design, the mission, the environment, the
 * simulation configuration and whatever results have been generated from them.
 *
 * ## Design data and generated results are separated
 *
 * The single most important structural decision here. `design`, `mission`,
 * `environment` and `simulation` are **authored**: a human chose them. `results`
 * is **generated**: the engine produced it from the other four.
 *
 * Keeping them apart means the file can answer a question a flat document
 * cannot: *are these results still true?* Every results block records the hash
 * of the inputs that produced it. Change a fin and the hash no longer matches,
 * the results are marked stale, and the interface can say so instead of showing
 * a user telemetry from a rocket they no longer have.
 *
 * ## Versioning
 *
 * `formatVersion` is the document envelope; `schemaVersion` is the shape of the
 * content inside it. Old files migrate forward through an explicit chain of
 * steps, each of which states what it changes. A file too old or too new to
 * handle produces a clear compatibility error and is never silently reshaped
 * into something that loads but means something different.
 *
 * ## Untrusted input
 *
 * A `.rkt` file arrives from somebody's disk or from another user. Nothing in
 * one is ever evaluated; no field is used to build a path, a URL or a query;
 * strings are length-capped, numbers are range-checked against physical
 * plausibility, nesting depth is bounded, and unknown keys are dropped rather
 * than carried through. See `rkt.ts` for the parser that enforces all of it.
 *
 * @module integration/rkt-schema
 */

import type { RocketDesign } from '../core/component-types.js';
import type { MissionConfig } from '../core/types.js';

// ============================================================
// Versions
// ============================================================

/** Document envelope version this build writes. */
export const RKT_FORMAT_VERSION = '2.0';

/** Content schema version this build writes. */
export const RKT_SCHEMA_VERSION = 2;

/** Oldest schema version this build can migrate from. */
export const RKT_MIN_SCHEMA_VERSION = 1;

/** Largest file this parser will consider. Unit: bytes. */
export const RKT_MAX_BYTES = 16 * 1024 * 1024;

/** Longest string accepted in any text field. */
export const RKT_MAX_STRING = 8_000;

/** Deepest nesting accepted, to bound the cost of walking a hostile document. */
export const RKT_MAX_DEPTH = 32;

/** Most components a single project may declare. */
export const RKT_MAX_COMPONENTS = 2_000;

/** Most telemetry samples a stored result may carry. */
export const RKT_MAX_TELEMETRY = 200_000;

// ============================================================
// Metadata
// ============================================================

export interface RktMetadata {
  /** Document envelope version, e.g. "2.0". */
  readonly formatVersion: string;
  /** Content schema version. */
  readonly schemaVersion: number;
  /** Stable identifier for this project across saves. */
  readonly projectId: string;
  readonly name: string;
  readonly description: string;
  readonly author: string;
  /** ISO-8601. */
  readonly createdAt: string;
  /** ISO-8601. */
  readonly updatedAt: string;
  /** What wrote this file, for diagnosing a format problem later. */
  readonly generator: string;
  /** Free tags for the user's own organisation. */
  readonly tags: readonly string[];
}

// ============================================================
// Vehicle
// ============================================================

/**
 * A stage, described explicitly.
 *
 * The simulation reconstructs staging from this rather than inferring it, so
 * separation and ignition conditions are things a project states rather than
 * things an engine guesses.
 */
export interface RktStage {
  readonly stageId: string;
  /** Firing order. 0 fires first. */
  readonly order: number;
  /** Instance ids of the components belonging to this stage. */
  readonly componentIds: readonly string[];
  /** Instance ids of the motors in this stage, in ignition order. */
  readonly motorIds: readonly string[];
  /** Seconds after the previous stage's burnout before this one lights. */
  readonly ignitionDelay_s: number;
  /** What has to be true before this stage separates. */
  readonly separationCondition: RktStageCondition;
  /** What has to be true before it ignites. */
  readonly ignitionCondition: RktStageCondition;
  /** Structural mass. Unit: kg */
  readonly dryMass_kg: number;
  /** Propellant at ignition. Unit: kg */
  readonly propellantMass_kg: number;
}

/**
 * A staging trigger.
 *
 * Deliberately a small closed vocabulary rather than an expression: a project
 * file must never contain something the engine has to *evaluate*.
 */
export interface RktStageCondition {
  readonly kind: 'burnout' | 'altitude' | 'time' | 'velocity' | 'manual' | 'immediate';
  /** Threshold in whatever unit `kind` implies. Ignored for burnout/manual. */
  readonly value: number;
  readonly unit: string;
}

/** A component instance, with a stable identity. */
export interface RktComponent {
  readonly id: string;
  /** Component category — the discriminant the engine dispatches on. */
  readonly type: string;
  /** Catalogue definition this instance was created from. */
  readonly defId: string;
  readonly name: string;
  /** Parent instance, for assemblies. `null` for a top-level part. */
  readonly parentId: string | null;
  readonly stageId: string;
  /** Position relative to the stage origin. Unit: m */
  readonly position: { readonly x: number; readonly y: number; readonly z: number };
  /** Orientation. Unit: rad */
  readonly orientation: { readonly pitch: number; readonly yaw: number; readonly roll: number };
  /** Overall dimensions. Unit: m */
  readonly dimensions: { readonly length: number; readonly diameter: number };
  /** Unit: kg */
  readonly mass_kg: number;
  readonly material: string;
  /**
   * Type-specific parameters — fin sweep, nose shape parameter, payload mass
   * override. Numbers, strings and booleans only, never nested structures, so
   * a hostile file cannot smuggle a deep graph through this field.
   */
  readonly parameters: Readonly<Record<string, number | string | boolean>>;
}

export interface RktVehicle {
  readonly name: string;
  readonly description: string;
  /** Overall dimensions of the assembled vehicle. Unit: m */
  readonly dimensions: {
    readonly length_m: number;
    readonly maxDiameter_m: number;
    readonly referenceArea_m2: number;
  };
  readonly mass: {
    readonly dry_kg: number;
    readonly propellant_kg: number;
    readonly payload_kg: number;
    readonly launch_kg: number;
  };
  /** Materials present in the build, for the bill of materials. */
  readonly materials: readonly string[];
  readonly stages: readonly RktStage[];
  readonly components: readonly RktComponent[];
  readonly payload: {
    readonly mass_kg: number;
    readonly type: string;
    readonly dimensions: { readonly length_m: number; readonly diameter_m: number };
    readonly description: string;
  };
  readonly recovery: {
    readonly enabled: boolean;
    readonly componentIds: readonly string[];
    readonly drogueDeployAltitude_m: number;
    readonly mainDeployAltitude_m: number;
    readonly maxDeploySpeed_ms: number;
  };
}

// ============================================================
// Propulsion, aerodynamics, avionics
// ============================================================

export interface RktMotor {
  readonly componentId: string;
  readonly defId: string;
  readonly designation: string;
  readonly propellantType: string;
  readonly thrustVacuum_N: number;
  readonly thrustSeaLevel_N: number;
  readonly ispVacuum_s: number;
  readonly ispSeaLevel_s: number;
  readonly burnTime_s: number;
  readonly totalImpulse_Ns: number;
  readonly propellantMass_kg: number;
  readonly dryMass_kg: number;
  /** Index into `thrustProfiles`, or -1 when the motor has no measured curve. */
  readonly thrustProfileIndex: number;
}

export interface RktThrustProfile {
  readonly id: string;
  readonly motorDefId: string;
  /** Sample times. Unit: s */
  readonly times_s: readonly number[];
  /** Thrust at each sample. Unit: N */
  readonly thrust_N: readonly number[];
}

export interface RktPropulsion {
  readonly motors: readonly RktMotor[];
  readonly mounts: readonly {
    readonly componentId: string;
    readonly motorCount: number;
    readonly thrustCapacity_N: number;
  }[];
  readonly thrustProfiles: readonly RktThrustProfile[];
}

export interface RktAerodynamics {
  readonly fins: readonly {
    readonly componentId: string;
    readonly shape: string;
    readonly count: number;
    readonly rootChord_m: number;
    readonly tipChord_m: number;
    readonly span_m: number;
    readonly sweepAngle_rad: number;
    readonly thickness_m: number;
    readonly stationFromNose_m: number;
  }[];
  readonly noseCone: {
    readonly componentId: string;
    readonly shape: string;
    readonly length_m: number;
    readonly baseDiameter_m: number;
    readonly shapeParameter: number;
    readonly finenessRatio: number;
  } | null;
  readonly dragParameters: {
    readonly subsonicCd: number;
    readonly referenceArea_m2: number;
    readonly useMachDragRise: boolean;
  };
  readonly stabilityParameters: {
    readonly cgWet_m: number;
    readonly cgDry_m: number;
    readonly cp_m: number;
    readonly staticMarginWet_cal: number;
    readonly staticMarginDry_cal: number;
    readonly referenceDiameter_m: number;
  };
}

export interface RktAvionics {
  readonly flightComputer: {
    readonly componentId: string;
    readonly name: string;
    readonly redundancy: number;
  } | null;
  readonly sensors: readonly {
    readonly componentId: string;
    readonly kind: string;
    readonly sampleRate_Hz: number;
  }[];
  readonly telemetry: {
    readonly enabled: boolean;
    readonly sampleInterval_s: number;
    readonly channels: readonly string[];
  };
}

// ============================================================
// Mission, environment, simulation
// ============================================================

export interface RktMission {
  readonly name: string;
  readonly objective: string;
  readonly launchSite: {
    readonly id: string;
    readonly name: string;
    readonly latitude_deg: number;
    readonly longitude_deg: number;
    readonly elevation_m: number;
  };
  readonly target: {
    readonly type: string;
    readonly altitude_km: number;
    readonly inclination_deg: number | null;
    readonly bodyId: string;
  };
  readonly trajectory: {
    readonly guidanceMode: string;
    readonly pitchoverAltitude_m: number;
    readonly pitchProgramEndAltitude_m: number;
    readonly finalPitch_deg: number;
  };
  readonly orientation: {
    readonly launchAzimuth_deg: number;
    readonly launchElevation_deg: number;
    readonly rollOrientation_deg: number;
  };
  readonly constraints: {
    readonly maxG: number;
    readonly maxDynamicPressure_Pa: number;
    readonly maxQAlpha_Padeg: number;
    readonly maxGroundWind_ms: number;
  };
}

export interface RktEnvironment {
  readonly atmosphere: {
    readonly model: string;
    readonly surfaceTemperature_K: number;
    readonly surfacePressure_Pa: number;
    readonly relativeHumidity: number;
  };
  readonly weather: {
    /** Where the observation came from. `"standard_day"` means none was used. */
    readonly source: string;
    /** ISO-8601, or null when no live observation was taken. */
    readonly observedAt: string | null;
    readonly windSpeed_ms: number;
    readonly windDirection_deg: number;
    readonly windGust_ms: number;
    readonly jetWindSpeed_ms: number;
    readonly cloudCover: number;
    readonly precipitation_mmh: number;
  };
  readonly gravity: {
    readonly model: string;
    readonly bodyId: string;
    readonly mu_m3s2: number;
    readonly surfaceRadius_m: number;
  };
  readonly simulationConditions: {
    readonly includeWind: boolean;
    readonly includeWeather: boolean;
    readonly includeEarthRotation: boolean;
  };
}

export interface RktSimulation {
  readonly engine: string;
  readonly engineVersion: string;
  readonly solver: string;
  readonly timestep: {
    readonly powered_s: number;
    readonly coast_s: number;
    readonly maxSteps: number;
  };
  readonly configuration: {
    readonly maxTime_s: number;
    readonly telemetrySampleInterval_s: number;
    readonly countdown_s: number;
    readonly useAltitudeCompensation: boolean;
    readonly failureDetection: boolean;
    readonly failureSeed: number;
  };
}

// ============================================================
// Results — generated, never authored
// ============================================================

/**
 * A stored simulation result.
 *
 * `inputsHash` is what makes staleness detectable: it is computed over the
 * design, mission, environment and simulation blocks that produced this run.
 * When the project is re-opened the hash is recomputed; if it differs, the
 * result is from a vehicle that no longer exists and must be marked stale
 * rather than displayed as current.
 */
export interface RktResults {
  readonly hasResults: boolean;
  /** ISO-8601 of when the run completed. */
  readonly ranAt: string | null;
  /** Engine build that produced it, so an old result stays attributable. */
  readonly engineVersion: string;
  /** Hash of the inputs. Compare against a freshly computed one. */
  readonly inputsHash: string;
  readonly outcome: string;
  readonly telemetry: {
    /** Channel names, in column order. */
    readonly channels: readonly string[];
    /**
     * Samples as rows of numbers, one row per sample, matching `channels`.
     *
     * Columnar rather than an array of objects: a 20,000-sample flight with 30
     * channels is 600,000 numbers, and repeating every key alongside every one
     * of them roughly quadruples the file for no benefit.
     */
    readonly rows: readonly (readonly number[])[];
  };
  readonly trajectory: {
    readonly maxAltitude_m: number;
    readonly maxSpeed_ms: number;
    readonly maxAcceleration_g: number;
    readonly maxDynamicPressure_Pa: number;
    readonly maxQAlpha_Padeg: number;
    readonly apogeeTime_s: number;
    readonly flightTime_s: number;
    readonly downrange_m: number;
    readonly finalPeriapsis_m: number;
    readonly finalApoapsis_m: number;
  };
  readonly evaluation: {
    readonly overallScore: number;
    readonly categories: readonly {
      readonly id: string;
      readonly label: string;
      readonly score: number;
      readonly note: string;
    }[];
  } | null;
  readonly failures: readonly {
    readonly id: string;
    readonly modeId: string;
    readonly subsystem: string;
    readonly severity: string;
    readonly t_s: number;
    readonly measured: number;
    readonly threshold: number;
    readonly unit: string;
    readonly cause: string;
    readonly recommendation: string;
  }[];
}

// ============================================================
// Assets
// ============================================================

export interface RktAssets {
  /** Catalogue component ids this project depends on. */
  readonly componentReferences: readonly string[];
  /**
   * Images referenced by the project.
   *
   * URLs only, never file paths, and only from hosts the application already
   * trusts. A `.rkt` file must not be able to make the application fetch an
   * arbitrary address.
   */
  readonly images: readonly {
    readonly id: string;
    readonly url: string;
    readonly credit: string;
    readonly alt: string;
  }[];
  /** User-supplied notes and attachments. Data only; never executable. */
  readonly customAssets: readonly {
    readonly id: string;
    readonly kind: string;
    readonly label: string;
    readonly value: string;
  }[];
}

// ============================================================
// The document
// ============================================================

/** A complete `.rkt` project. */
export interface RktProject {
  readonly metadata: RktMetadata;
  readonly vehicle: RktVehicle;
  readonly propulsion: RktPropulsion;
  readonly aerodynamics: RktAerodynamics;
  readonly avionics: RktAvionics;
  readonly mission: RktMission;
  readonly environment: RktEnvironment;
  readonly simulation: RktSimulation;
  readonly results: RktResults;
  readonly assets: RktAssets;
  /**
   * The builder's own design document, carried verbatim.
   *
   * The structured blocks above are the portable, engine-facing description —
   * what a simulator, an exporter or another tool reads. This is the editor's
   * working state, kept so that reopening a project restores the exact editing
   * session rather than a reconstruction of it.
   */
  readonly design: RocketDesign;
  /** The mission configuration in the engine's own shape. */
  readonly missionConfig: MissionConfig;
}
