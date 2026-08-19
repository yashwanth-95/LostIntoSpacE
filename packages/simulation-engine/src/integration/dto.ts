/**
 * Data transfer objects — the wire format between P3 and the rest of the team.
 *
 * The engine's internal types are shaped for computation. These are shaped for
 * *transport*: flat, versioned, JSON-safe, and stable across engine refactors.
 * P2 stores them, P4 reads them, P1 round-trips them. None of those consumers
 * should ever have to import a type whose shape is driven by the needs of an
 * RK4 inner loop.
 *
 * ## Versioning
 *
 * Every payload carries `schemaVersion`. The rule is:
 *
 * - **Adding an optional field** — no version bump. Old readers ignore it.
 * - **Removing or retyping a field** — major bump, and both readers must be
 *   updated before the writer ships.
 *
 * {@link SCHEMA_VERSION} is the version this build writes.
 *
 * ## What is deliberately *not* here
 *
 * Database ids, user ids, project ids, and timestamps of record. Those belong
 * to P2 and this package has no business inventing them. A DTO describes a
 * rocket or a flight; where it is filed is somebody else's problem.
 *
 * @module integration/dto
 */

import type { RocketDesign } from '../core/component-types.js';
import type { RocketAnalysis } from '../core/builder.js';
import type { ValidationIssue } from '../core/validation.js';
import type { SimConfig } from '../sim/config.js';
import type { SimResult } from '../sim/runner.js';
import type { SimEvent, FailureDetail, SimSummary } from '../sim/events.js';
import type { TelemetryPoint } from '../sim/telemetry.js';
import { decimateTelemetry } from '../sim/telemetry.js';

/** Schema version this build reads and writes. */
export const SCHEMA_VERSION = '1.0.0';

/** Identifies the engine build that produced a payload. */
export interface GeneratorInfo {
  /** Package name. */
  readonly engine: string;
  /** Package version. */
  readonly version: string;
  /** DTO schema version. */
  readonly schemaVersion: string;
}

/** The generator block this build stamps onto every payload. */
export const GENERATOR: GeneratorInfo = Object.freeze({
  engine: '@lostintospace/simulation-engine',
  version: '0.1.0',
  schemaVersion: SCHEMA_VERSION,
});

// ============================================================
// Rocket design
// ============================================================

/** A saved rocket design, plus the numbers derived from it. */
export interface RocketDesignDTO {
  readonly generator: GeneratorInfo;
  /** The design itself. Already JSON-safe. */
  readonly design: RocketDesign;
  /**
   * Ids of the component definitions the design references.
   *
   * Recorded so a design loaded on a machine with a different catalogue can be
   * told *which* parts are missing, rather than silently rendering wrong.
   */
  readonly requiredComponentIds: readonly string[];
  /** Headline figures, denormalised so a list view needs no recomputation. */
  readonly summary: DesignSummaryDTO;
  /** Validation issues at the time of saving. */
  readonly validationIssues: readonly ValidationIssue[];
}

/** Headline design figures, for list and card views. */
export interface DesignSummaryDTO {
  readonly name: string;
  readonly stageCount: number;
  readonly componentCount: number;
  readonly totalMass_kg: number;
  readonly dryMass_kg: number;
  readonly propellantMass_kg: number;
  readonly payloadMass_kg: number;
  readonly length_m: number;
  readonly diameter_m: number;
  readonly totalDeltaV_ms: number;
  readonly liftoffTWR: number;
  readonly stabilityMargin_cal: number;
  readonly cost: number;
}

/**
 * Build the transport payload for a design.
 *
 * @param design - The design to serialize.
 * @param analysis - Its analysis, so the summary needs no second pass.
 * @param validationIssues - Issues found at save time.
 * @returns The payload.
 */
export function toDesignDTO(
  design: RocketDesign,
  analysis: RocketAnalysis,
  validationIssues: readonly ValidationIssue[] = [],
): RocketDesignDTO {
  return {
    generator: GENERATOR,
    design,
    requiredComponentIds: [...new Set(design.components.map(c => c.defId))].sort(),
    summary: {
      name: design.name,
      stageCount: design.stages.length,
      componentCount: design.components.length,
      totalMass_kg: analysis.totalWetMass_kg,
      dryMass_kg: analysis.totalDryMass_kg,
      propellantMass_kg: analysis.totalPropellantMass_kg,
      payloadMass_kg: analysis.payloadMass_kg,
      length_m: analysis.totalLength_m,
      diameter_m: analysis.maxDiameter_m,
      totalDeltaV_ms: analysis.totalDeltaV_ms,
      liftoffTWR: analysis.liftoffTWR,
      // The worse of the two cases, which is the one that matters for flight.
      stabilityMargin_cal: Math.min(
        analysis.stabilityWet.stabilityMargin_cal,
        analysis.stabilityDry.stabilityMargin_cal,
      ),
      cost: analysis.totalCost,
    },
    validationIssues: [...validationIssues],
  };
}

// ============================================================
// Simulation run
// ============================================================

/**
 * A completed flight, as stored and served.
 *
 * Telemetry is decimated before it goes on the wire — see
 * {@link toSimulationRunDTO}.
 */
export interface SimulationRunDTO {
  readonly generator: GeneratorInfo;
  /** Design this flight was flown with. */
  readonly designId: string;
  /** Mission name. */
  readonly missionName: string;
  /** Everything needed to reproduce the run exactly. */
  readonly reproduction: ReproductionDTO;
  /** Outcome. */
  readonly outcome: 'success' | 'partial' | 'failure';
  /** Whether the mission objective was met. */
  readonly success: boolean;
  /** Final mission state. */
  readonly finalMissionState: string;
  /** Why the run ended. */
  readonly terminationReason: string;
  /** Aggregate statistics. */
  readonly summary: SimSummary;
  /** Sampled telemetry. */
  readonly telemetry: readonly TelemetryPoint[];
  /** Number of telemetry samples the engine actually produced, before thinning. */
  readonly telemetryFullResolutionCount: number;
  /** Every event. */
  readonly events: readonly SimEvent[];
  /** Every failure. */
  readonly failures: readonly FailureDetail[];
  /** Integration steps taken. */
  readonly totalSteps: number;
}

/**
 * The minimum needed to reproduce a run byte-for-byte.
 *
 * Storing this instead of only the telemetry means a run can always be replayed
 * — at higher resolution, with a different sampling rate, or after an engine
 * upgrade to see what changed. The engine's determinism guarantee is what makes
 * this worth storing.
 */
export interface ReproductionDTO {
  /** Engine version that produced the original run. */
  readonly engineVersion: string;
  /** Failure RNG seed. */
  readonly seed: number;
  /** Integrator used. */
  readonly integrator: string;
  /** Powered-flight timestep. Unit: s. */
  readonly dt_powered_s: number;
  /** Coast timestep. Unit: s. */
  readonly dt_coast_s: number;
  /** Mission profile id. */
  readonly profileId: string;
  /** Guidance mode. */
  readonly guidanceMode: string;
  /** Launch azimuth. Unit: degrees. */
  readonly launchAzimuth_deg: number;
}

/** Options for {@link toSimulationRunDTO}. */
export interface SimulationRunDTOOptions {
  /**
   * Cap on telemetry samples in the payload.
   *
   * A 500-second orbital ascent at 1 Hz is 500 samples, which is fine. A
   * 3000-second mission at 10 Hz is 30 000 rows, which is not — it is slow to
   * store, slow to send, and far more than any chart can draw. The decimation
   * keeps the extremes rather than sampling evenly, so apogee and max-Q survive.
   */
  readonly maxTelemetryPoints?: number;
}

/**
 * Build the transport payload for a completed run.
 *
 * @param result - The result from `runSimulation` or `Simulation.getResult`.
 * @param config - The config it was run with.
 * @param options - Telemetry thinning.
 * @returns The payload.
 */
export function toSimulationRunDTO(
  result: SimResult,
  config: SimConfig,
  options: SimulationRunDTOOptions = {},
): SimulationRunDTO {
  const maxPoints = options.maxTelemetryPoints ?? 2_000;

  return {
    generator: GENERATOR,
    designId: config.vehicle.designId,
    missionName: config.mission.name,
    reproduction: {
      engineVersion: GENERATOR.version,
      seed: config.failures.seed,
      integrator: config.settings.integrator,
      dt_powered_s: config.settings.dt_powered_s,
      dt_coast_s: config.settings.dt_coast_s,
      profileId: config.profile.id,
      guidanceMode: config.guidance.mode,
      launchAzimuth_deg: config.guidance.launchAzimuth_deg,
    },
    outcome: result.outcome,
    success: result.success,
    finalMissionState: result.finalState,
    terminationReason: result.terminationReason,
    summary: result.summary,
    telemetry: decimateTelemetry(result.telemetry, maxPoints),
    telemetryFullResolutionCount: result.telemetry.length,
    events: result.events,
    failures: result.failures,
    totalSteps: result.totalSteps,
  };
}

// ============================================================
// Validation
// ============================================================

/**
 * Check that a payload came from a schema this build understands.
 *
 * Only the major version is compared. A minor or patch difference means fields
 * were added, which old readers safely ignore.
 *
 * @param payload - Anything with a `generator` block.
 * @returns Whether this build can read it, and why not if it cannot.
 */
export function checkSchemaCompatibility(payload: {
  generator?: Partial<GeneratorInfo>;
}): { compatible: boolean; reason?: string } {
  const version = payload.generator?.schemaVersion;
  if (!version) {
    return { compatible: false, reason: 'Payload has no schema version' };
  }

  const theirMajor = version.split('.')[0];
  const ourMajor = SCHEMA_VERSION.split('.')[0];

  if (theirMajor !== ourMajor) {
    return {
      compatible: false,
      reason:
        `Payload uses schema ${version}, this engine reads ${SCHEMA_VERSION}. ` +
        'Major versions differ, so field shapes are not guaranteed to match.',
    };
  }

  return { compatible: true };
}
