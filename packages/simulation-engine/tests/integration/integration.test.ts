import { describe, it, expect } from 'vitest';
import {
  toDesignDTO,
  toSimulationRunDTO,
  checkSchemaCompatibility,
  SCHEMA_VERSION,
  GENERATOR,
} from '../../src/integration/dto.js';
import {
  serializeRkt,
  parseRkt,
  findMissingComponents,
  RKT_VERSION,
  RKT_MAX_BYTES,
} from '../../src/integration/rkt.js';
import {
  buildMissionReport,
  formatReportAsText,
  REPORT_VERSION,
} from '../../src/integration/ai-export.js';
import { analyzeRocket } from '../../src/core/builder.js';
import { validateRocket } from '../../src/core/validation.js';
import { toVehicle } from '../../src/core/vehicle.js';
import { createSimConfig } from '../../src/sim/config.js';
import { runSimulation } from '../../src/sim/runner.js';
import { SUBORBITAL_PROFILE } from '../../src/sim/mission-state.js';
import { VERTICAL_GUIDANCE } from '../../src/sim/guidance.js';
import {
  DEFAULT_LAUNCH_SITE,
  DEFAULT_ENVIRONMENT,
  type MissionConfig,
} from '../../src/core/types.js';
import {
  stockRegistry,
  recoverableSoundingRocket,
  orbitalLauncher,
} from '../core/reference-designs.js';

const registry = stockRegistry();

const mission: MissionConfig = {
  name: 'Integration Test Flight',
  objective: 'Reach 30 km and return',
  target: { type: 'suborbital', targetAltitude_km: 30, inclination_deg: 13.7 },
  launchSite: DEFAULT_LAUNCH_SITE,
  environment: DEFAULT_ENVIRONMENT,
};

const design = recoverableSoundingRocket(registry);
const analysis = analyzeRocket(design, registry);
const config = createSimConfig(toVehicle(design, registry), mission, {
  profile: SUBORBITAL_PROFILE,
  guidance: VERTICAL_GUIDANCE,
});
const result = runSimulation(config);

describe('RocketDesignDTO', () => {
  const dto = toDesignDTO(design, analysis);

  it('stamps the generator and schema version', () => {
    expect(dto.generator.schemaVersion).toBe(SCHEMA_VERSION);
    expect(dto.generator.engine).toBe(GENERATOR.engine);
  });

  it('lists every component id the design needs, deduplicated and sorted', () => {
    const expected = [...new Set(design.components.map(c => c.defId))].sort();
    expect(dto.requiredComponentIds).toEqual(expected);
  });

  it('denormalises the headline figures so a list view needs no recomputation', () => {
    expect(dto.summary.totalMass_kg).toBeCloseTo(analysis.totalWetMass_kg, 6);
    expect(dto.summary.totalDeltaV_ms).toBeCloseTo(analysis.totalDeltaV_ms, 6);
    expect(dto.summary.stageCount).toBe(design.stages.length);
    expect(dto.summary.componentCount).toBe(design.components.length);
  });

  it('reports the worse of the wet and dry stability margins', () => {
    expect(dto.summary.stabilityMargin_cal).toBeCloseTo(
      Math.min(
        analysis.stabilityWet.stabilityMargin_cal,
        analysis.stabilityDry.stabilityMargin_cal,
      ),
      6,
    );
  });

  it('carries validation issues alongside the design', () => {
    const validation = validateRocket(design, registry);
    const withIssues = toDesignDTO(design, analysis, validation.issues);
    expect(withIssues.validationIssues).toHaveLength(validation.issues.length);
  });

  it('is JSON-safe', () => {
    expect(JSON.parse(JSON.stringify(dto))).toEqual(dto);
  });
});

describe('SimulationRunDTO', () => {
  const dto = toSimulationRunDTO(result, config);

  it('records everything needed to reproduce the run', () => {
    expect(dto.reproduction.seed).toBe(config.failures.seed);
    expect(dto.reproduction.integrator).toBe(config.settings.integrator);
    expect(dto.reproduction.dt_powered_s).toBe(config.settings.dt_powered_s);
    expect(dto.reproduction.profileId).toBe(config.profile.id);
    expect(dto.reproduction.guidanceMode).toBe(config.guidance.mode);
  });

  it('links the run back to the design that flew it', () => {
    expect(dto.designId).toBe(config.vehicle.designId);
    expect(dto.missionName).toBe(mission.name);
  });

  it('carries the outcome and the summary intact', () => {
    expect(dto.outcome).toBe(result.outcome);
    expect(dto.success).toBe(result.success);
    expect(dto.summary).toEqual(result.summary);
  });

  it('thins telemetry to the requested cap', () => {
    const small = toSimulationRunDTO(result, config, { maxTelemetryPoints: 20 });
    expect(small.telemetry.length).toBeLessThanOrEqual(20);
  });

  it('records how many samples there were before thinning', () => {
    const small = toSimulationRunDTO(result, config, { maxTelemetryPoints: 20 });
    expect(small.telemetryFullResolutionCount).toBe(result.telemetry.length);
  });

  it('keeps the apogee through thinning', () => {
    const small = toSimulationRunDTO(result, config, { maxTelemetryPoints: 20 });
    const keptPeak = Math.max(...small.telemetry.map(p => p.altitude_m));
    const truePeak = Math.max(...result.telemetry.map(p => p.altitude_m));
    expect(keptPeak).toBe(truePeak);
  });

  it('keeps every event, since events are what a timeline is made of', () => {
    expect(dto.events).toHaveLength(result.events.length);
  });

  it('is JSON-safe', () => {
    expect(JSON.parse(JSON.stringify(dto))).toEqual(dto);
  });
});

describe('checkSchemaCompatibility', () => {
  it('accepts a payload this build wrote', () => {
    expect(checkSchemaCompatibility(toDesignDTO(design, analysis)).compatible).toBe(true);
  });

  it('accepts a differing minor version', () => {
    const major = SCHEMA_VERSION.split('.')[0];
    expect(
      checkSchemaCompatibility({
        generator: { schemaVersion: `${major}.99.0` },
      }).compatible,
    ).toBe(true);
  });

  it('rejects a differing major version, with a reason', () => {
    const check = checkSchemaCompatibility({ generator: { schemaVersion: '99.0.0' } });
    expect(check.compatible).toBe(false);
    expect(check.reason).toMatch(/major/i);
  });

  it('rejects a payload with no version at all', () => {
    expect(checkSchemaCompatibility({}).compatible).toBe(false);
  });
});

describe('.rkt serialization', () => {
  it('round-trips a project', () => {
    const json = serializeRkt(design, mission, { author: 'Test Author' });
    const parsed = parseRkt(json);

    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;

    expect(parsed.file.rkt_version).toBe(RKT_VERSION);
    expect(parsed.file.project.author).toBe('Test Author');
    expect(parsed.file.design.name).toBe(design.name);
    expect(parsed.file.design.components).toHaveLength(design.components.length);
    expect(parsed.file.mission.launchSite.latitude_deg).toBeCloseTo(
      mission.launchSite.latitude_deg,
      6,
    );
  });

  it('preserves configuration overrides through the round trip', () => {
    const json = serializeRkt(design, mission);
    const parsed = parseRkt(json);
    if (!parsed.ok) throw new Error('parse failed');

    const original = design.components.find(
      c => Object.keys(c.configOverrides).length > 0,
    )!;
    const restored = parsed.file.design.components.find(
      c => c.instanceId === original.instanceId,
    )!;
    expect(restored.configOverrides).toEqual(original.configOverrides);
  });

  it('produces a design the builder can still analyse', () => {
    const json = serializeRkt(design, mission);
    const parsed = parseRkt(json);
    if (!parsed.ok) throw new Error('parse failed');

    const restored = analyzeRocket(parsed.file.design, registry);
    expect(restored.totalWetMass_kg).toBeCloseTo(analysis.totalWetMass_kg, 6);
    expect(restored.totalDeltaV_ms).toBeCloseTo(analysis.totalDeltaV_ms, 6);
  });
});

describe('.rkt parsing — untrusted input', () => {
  it('rejects malformed JSON without throwing', () => {
    const parsed = parseRkt('{ not json at all');
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors[0]!.message).toMatch(/not valid json/i);
  });

  it('rejects a file above the size limit before parsing it', () => {
    const huge = 'x'.repeat(RKT_MAX_BYTES + 1);
    const parsed = parseRkt(huge);
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors[0]!.message).toMatch(/byte limit/i);
  });

  it('rejects an unsupported format version', () => {
    const json = serializeRkt(design, mission).replace('"1.0"', '"99.0"');
    const parsed = parseRkt(json);
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors.some(e => e.path === 'rkt_version')).toBe(true);
  });

  it('rejects a design with no stages', () => {
    const file = JSON.parse(serializeRkt(design, mission));
    file.design.stages = [];
    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(false);
  });

  it('rejects an out-of-range latitude', () => {
    const file = JSON.parse(serializeRkt(design, mission));
    file.mission.launchSite.latitude_deg = 500;
    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors.some(e => e.path.includes('latitude'))).toBe(true);
  });

  it('rejects a non-numeric mass where a number belongs', () => {
    const file = JSON.parse(serializeRkt(design, mission));
    file.design.components[0].offset_z = 'not a number';
    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(false);
  });

  it('discards a non-finite configuration override rather than admitting NaN', () => {
    const file = JSON.parse(serializeRkt(design, mission));
    file.design.components[0].configOverrides = { mass_kg: 'huge', fillFraction: 0.5 };
    const parsed = parseRkt(JSON.stringify(file));

    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    // The bad value is dropped; the good one survives.
    expect(parsed.file.design.components[0]!.configOverrides).toEqual({
      fillFraction: 0.5,
    });
  });

  it('caps an over-long string instead of carrying it through', () => {
    const file = JSON.parse(serializeRkt(design, mission));
    file.project.name = 'a'.repeat(10_000);
    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(false);
  });

  it('drops unknown top-level keys rather than passing them along', () => {
    const file = JSON.parse(serializeRkt(design, mission));
    file.__proto__inject = { evil: true };
    file.arbitrary_key = 'ignored';

    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(Object.keys(parsed.file)).not.toContain('arbitrary_key');
  });

  it('reports every problem at once, so the user fixes them together', () => {
    const file = JSON.parse(serializeRkt(design, mission));
    file.mission.launchSite.latitude_deg = 500;
    file.mission.launchSite.longitude_deg = 900;
    file.rkt_version = '0.1';

    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors.length).toBeGreaterThanOrEqual(3);
  });

  it('names the offending field by path', () => {
    const file = JSON.parse(serializeRkt(design, mission));
    file.mission.environment.temperature_K = 5_000;
    const parsed = parseRkt(JSON.stringify(file));

    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors[0]!.path).toBe('mission.environment.temperature_K');
  });
});

describe('findMissingComponents', () => {
  it('finds nothing missing against the full catalogue', () => {
    const parsed = parseRkt(serializeRkt(design, mission));
    if (!parsed.ok) throw new Error('parse failed');
    expect(findMissingComponents(parsed.file, registry.listIds())).toEqual([]);
  });

  it('names the parts a partial catalogue lacks', () => {
    const parsed = parseRkt(serializeRkt(design, mission));
    if (!parsed.ok) throw new Error('parse failed');

    // Loading against a catalogue missing a part would otherwise silently
    // produce a lighter, weaker rocket than the author designed.
    const partial = registry.listIds().filter(id => id !== 'engine_s_solid');
    expect(findMissingComponents(parsed.file, partial)).toEqual(['engine_s_solid']);
  });
});

describe('MissionReport', () => {
  const validation = validateRocket(design, registry);
  const report = buildMissionReport(result, config, analysis, validation.issues);

  it('carries its own version', () => {
    expect(report.reportVersion).toBe(REPORT_VERSION);
  });

  it('describes the mission and the vehicle', () => {
    expect(report.mission.name).toBe(mission.name);
    expect(report.vehicle.launchMass_kg).toBeCloseTo(analysis.totalWetMass_kg, 6);
    expect(report.vehicle.stageCount).toBe(1);
  });

  it('gives every measurement a unit and a description', () => {
    expect(report.measurements.length).toBeGreaterThan(5);
    for (const m of report.measurements) {
      expect(m.unit, m.key).toBeTruthy();
      expect(m.description.length, m.key).toBeGreaterThan(20);
      expect(Number.isFinite(m.value), m.key).toBe(true);
    }
  });

  it('accounts for the delta-v budget', () => {
    const budget = report.deltaVBudget;
    expect(budget.ideal_ms).toBeGreaterThan(0);
    // The loss terms plus what was achieved must reconstruct the ideal figure.
    expect(
      budget.achieved_ms + budget.gravityLoss_ms + budget.dragLoss_ms + budget.unaccounted_ms,
    ).toBeCloseTo(budget.ideal_ms, 6);
  });

  it('carries the timeline with state at each moment', () => {
    expect(report.timeline.length).toBe(result.events.length);
    for (const moment of report.timeline) {
      expect(Number.isFinite(moment.t_s)).toBe(true);
      expect(moment.type).toBeTruthy();
    }
  });

  it('states plainly what the engine does not model', () => {
    // A model that does not say what it leaves out invites an explanation layer
    // to attribute behaviour to physics that was never simulated.
    expect(report.modelLimitations.notModelled.length).toBeGreaterThan(5);
    expect(report.modelLimitations.simplifications.length).toBeGreaterThan(3);
    expect(report.modelLimitations.caveat).toMatch(/educational/i);
    expect(report.modelLimitations.caveat).toMatch(/not.*reconstruction/i);
  });

  it('names Earth rotation among the things it does not model', () => {
    expect(report.modelLimitations.notModelled.join(' ')).toMatch(/rotation/i);
  });

  it('carries the pre-flight warnings the design already had', () => {
    expect(report.preflightWarnings).toHaveLength(validation.issues.length);
  });

  it('is JSON-safe', () => {
    expect(JSON.parse(JSON.stringify(report))).toEqual(report);
  });
});

describe('formatReportAsText', () => {
  const report = buildMissionReport(result, config, analysis);
  const text = formatReportAsText(report);

  it('includes the mission, vehicle, and outcome', () => {
    expect(text).toContain(mission.name);
    expect(text).toContain('VEHICLE');
    expect(text).toContain('OUTCOME');
    expect(text).toContain('MEASUREMENTS');
    expect(text).toContain('DELTA-V BUDGET');
    expect(text).toContain('TIMELINE');
  });

  it('always ends with the model limitations', () => {
    expect(text).toContain('MODEL LIMITATIONS');
    expect(text.trimEnd().endsWith(report.modelLimitations.caveat)).toBe(true);
  });

  it('stays small enough to prompt with', () => {
    // The JSON with telemetry runs to hundreds of kilobytes; this is the facts.
    expect(text.length).toBeLessThan(20_000);
  });

  it('includes the failure detail when a flight fails', () => {
    const failing = createSimConfig(toVehicle(orbitalLauncher(registry), registry), mission, {
      profile: SUBORBITAL_PROFILE,
      guidance: VERTICAL_GUIDANCE,
      settings: { maxTime_s: 400 },
      failures: {
        ...config.failures,
        injections: [
          { id: 'scripted-shutdown', mode: 'engine_shutdown', trigger: { type: 'time', t_s: 20 } },
        ],
      },
    });
    const failedRun = runSimulation(failing);
    const failedText = formatReportAsText(
      buildMissionReport(failedRun, failing, analyzeRocket(orbitalLauncher(registry), registry)),
    );

    expect(failedText).toContain('FAILURES');
    expect(failedText).toContain('Suggested fix');
  });
});
