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
  RKT_SCHEMA_VERSION,
  buildRktProject,
  computeInputsHash,
  areResultsStale,
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

describe('.rkt v2 — round trip', () => {
  function project() {
    return buildRktProject({
      design,
      mission,
      registry,
      metadata: { author: 'Test Author' },
      now: '2026-01-01T00:00:00.000Z',
    });
  }

  it('round-trips a project', () => {
    const parsed = parseRkt(serializeRkt(project()));

    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;

    expect(parsed.project.metadata.schemaVersion).toBe(RKT_SCHEMA_VERSION);
    expect(parsed.project.metadata.author).toBe('Test Author');
    expect(parsed.project.design.name).toBe(design.name);
    expect(parsed.project.design.components).toHaveLength(design.components.length);
    expect(parsed.project.missionConfig.launchSite.latitude_deg).toBeCloseTo(
      mission.launchSite.latitude_deg,
      6,
    );
  });

  it('derives the engineering view rather than asking the user to maintain it', () => {
    const built = project();
    expect(built.vehicle.stages).toHaveLength(design.stages.length);
    expect(built.vehicle.components).toHaveLength(design.components.length);
    expect(built.vehicle.mass.launch_kg).toBeCloseTo(analysis.totalWetMass_kg, 6);
    expect(built.aerodynamics.stabilityParameters.staticMarginWet_cal).toBeCloseTo(
      analysis.stabilityWet.stabilityMargin_cal,
      6,
    );
    expect(built.propulsion.motors.length).toBeGreaterThan(0);
  });

  it('preserves configuration overrides through the round trip', () => {
    const parsed = parseRkt(serializeRkt(project()));
    if (!parsed.ok) throw new Error('parse failed');

    const original = design.components.find(c => Object.keys(c.configOverrides).length > 0)!;
    const restored = parsed.project.design.components.find(
      c => c.instanceId === original.instanceId,
    )!;
    expect(restored.configOverrides).toEqual(original.configOverrides);
  });

  it('produces a design the builder can still analyse', () => {
    const parsed = parseRkt(serializeRkt(project()));
    if (!parsed.ok) throw new Error('parse failed');

    const restored = analyzeRocket(parsed.project.design, registry);
    expect(restored.totalWetMass_kg).toBeCloseTo(analysis.totalWetMass_kg, 6);
    expect(restored.totalDeltaV_ms).toBeCloseTo(analysis.totalDeltaV_ms, 6);
  });
});

describe('.rkt v2 — results and staleness', () => {
  function withResults() {
    const base = buildRktProject({ design, mission, registry, now: '2026-01-01T00:00:00.000Z' });
    const results = {
      ...base.results,
      hasResults: true,
      ranAt: '2026-01-01T00:05:00.000Z',
      engineVersion: '0.2.0',
      outcome: 'success',
      inputsHash: computeInputsHash(base),
      telemetry: { channels: ['t', 'altitude_m'], rows: [[0, 0], [1, 12.4]] },
    };
    return { ...base, results };
  }

  it('results produced from the current inputs are not stale', () => {
    expect(areResultsStale(withResults())).toBe(false);
  });

  it('editing the vehicle makes stored results stale', () => {
    // The property the whole design-versus-results split exists for.
    const stale = withResults();
    const edited = {
      ...stale,
      design: { ...stale.design, name: stale.design.name, components: stale.design.components.slice(1) },
    };
    expect(areResultsStale(edited)).toBe(true);
  });

  it('hashing does not depend on key order', () => {
    const built = withResults();
    const reordered = {
      ...built,
      // Same content, different insertion order.
      environment: {
        simulationConditions: built.environment.simulationConditions,
        gravity: built.environment.gravity,
        weather: built.environment.weather,
        atmosphere: built.environment.atmosphere,
      },
    };
    expect(computeInputsHash(reordered)).toBe(computeInputsHash(built));
  });

  it('renaming a project does not invalidate its results', () => {
    const built = withResults();
    const renamed = {
      ...built,
      metadata: { ...built.metadata, name: 'A completely different name' },
    };
    expect(areResultsStale(renamed)).toBe(false);
  });

  it('warns when a reopened project carries stale results', () => {
    const built = withResults();
    const tampered = JSON.parse(serializeRkt(built));
    tampered.results.inputsHash = 'hnotthehash';
    const parsed = parseRkt(JSON.stringify(tampered));

    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.warnings.some(w => /stale/i.test(w.message))).toBe(true);
  });

  it('round-trips telemetry as columns rather than as objects', () => {
    const parsed = parseRkt(serializeRkt(withResults()));
    if (!parsed.ok) throw new Error('parse failed');
    expect(parsed.project.results.telemetry.channels).toEqual(['t', 'altitude_m']);
    expect(parsed.project.results.telemetry.rows[1]).toEqual([1, 12.4]);
  });

  it('rejects telemetry whose rows do not match its channels', () => {
    const built = JSON.parse(serializeRkt(withResults()));
    built.results.telemetry.rows = [[0, 0, 0]];
    const parsed = parseRkt(JSON.stringify(built));
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors.some(e => /channels/i.test(e.message))).toBe(true);
  });
});

describe('.rkt v2 — versioning and migration', () => {
  it('migrates a version 1 file forward', () => {
    // The shape v1 wrote: flat, with rkt_version at the top level.
    const v1 = JSON.stringify({
      rkt_version: '1.0',
      generator: '@lostintospace/simulation-engine 0.1.0',
      created_at: '2025-06-01T00:00:00.000Z',
      updated_at: '2025-06-01T00:00:00.000Z',
      project: { name: 'Legacy Rocket', description: 'from v1', author: 'Someone' },
      mission,
      design,
      simulation_settings: {},
      educational_metadata: { difficulty: 'beginner', concepts_covered: [], related_lessons: [] },
    });

    const parsed = parseRkt(v1);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;

    expect(parsed.project.metadata.schemaVersion).toBe(RKT_SCHEMA_VERSION);
    expect(parsed.project.metadata.name).toBe('Legacy Rocket');
    expect(parsed.project.metadata.author).toBe('Someone');
    expect(parsed.project.design.components).toHaveLength(design.components.length);
    // The user is told their file was upgraded rather than it happening silently.
    expect(parsed.warnings.some(w => w.path === 'metadata.schemaVersion')).toBe(true);
  });

  it('a migrated v1 file claims no results, because it had none', () => {
    const v1 = JSON.stringify({
      rkt_version: '1.0',
      project: { name: 'Legacy', description: '', author: '' },
      mission,
      design,
    });
    const parsed = parseRkt(v1);
    if (!parsed.ok) throw new Error('parse failed');
    expect(parsed.project.results.hasResults).toBe(false);
  });

  it('refuses a file from a newer build rather than dropping what it cannot read', () => {
    const built = JSON.parse(serializeRkt(buildRktProject({ design, mission, registry })));
    built.metadata.schemaVersion = 99;
    const parsed = parseRkt(JSON.stringify(built));

    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors[0]!.path).toBe('metadata.schemaVersion');
    expect(parsed.errors[0]!.message).toMatch(/newer version/i);
  });

  it('refuses a schema version older than the migration chain reaches', () => {
    const built = JSON.parse(serializeRkt(buildRktProject({ design, mission, registry })));
    built.metadata.schemaVersion = 0;
    const parsed = parseRkt(JSON.stringify(built));
    expect(parsed.ok).toBe(false);
  });
});

describe('.rkt v2 — untrusted input', () => {
  const good = () => serializeRkt(buildRktProject({ design, mission, registry }));

  it('rejects malformed JSON without throwing', () => {
    const parsed = parseRkt('{ not json at all');
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors[0]!.message).toMatch(/not a valid project file/i);
  });

  it('rejects a file above the size limit before parsing it', () => {
    const huge = 'x'.repeat(RKT_MAX_BYTES + 1);
    const parsed = parseRkt(huge);
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors[0]!.message).toMatch(/limit/i);
  });

  it('rejects a document nested past the depth limit', () => {
    // A deeply nested document must not be able to exhaust the stack during
    // validation.
    let nested: unknown = { end: true };
    for (let i = 0; i < 60; i += 1) nested = { nested };
    const file = JSON.parse(good());
    file.assets.customAssets = [nested];
    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors[0]!.message).toMatch(/nests/i);
  });

  it('rejects a non-object document', () => {
    expect(parseRkt('[1,2,3]').ok).toBe(false);
    expect(parseRkt('"just a string"').ok).toBe(false);
  });

  it('rejects an out-of-range latitude', () => {
    const file = JSON.parse(good());
    file.missionConfig.launchSite.latitude_deg = 500;
    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors.some(e => e.path.includes('latitude'))).toBe(true);
  });

  it('rejects a temperature that is not a temperature', () => {
    // 5,000 K at the pad is a Celsius/kelvin mix-up or a decimal slip, and
    // either way the flight it produces would be meaningless.
    const file = JSON.parse(good());
    file.missionConfig.environment.temperature_K = 5_000;
    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors.some(e => e.path === 'mission.environment.temperature_K')).toBe(true);
  });

  it('rejects a non-numeric offset where a number belongs', () => {
    const file = JSON.parse(good());
    file.design.components[0].offset_z = 'not a number';
    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(false);
  });

  it('rejects duplicate component identifiers', () => {
    const file = JSON.parse(good());
    file.design.components[1].instanceId = file.design.components[0].instanceId;
    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors.some(e => /share the identifier/i.test(e.message))).toBe(true);
  });

  it('rejects a component assigned to a stage that does not exist', () => {
    const file = JSON.parse(good());
    file.design.components[0].stageIndex = 47;
    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors.some(e => /stage 47/i.test(e.message))).toBe(true);
  });

  it('rejects a reference to a component that is not in the design', () => {
    const file = JSON.parse(good());
    file.design.connections = [
      {
        id: 'conn-1',
        fromInstanceId: file.design.components[0].instanceId,
        toInstanceId: 'BODY-02',
        fromAttachmentId: 'top',
        toAttachmentId: 'base',
        type: 'structural',
      },
    ];
    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors.some(e => e.message.includes('BODY-02'))).toBe(true);
  });

  it('discards a non-finite configuration override rather than admitting NaN', () => {
    const file = JSON.parse(good());
    file.design.components[0].configOverrides = { mass_kg: 'huge', fillFraction: 0.5 };
    const parsed = parseRkt(JSON.stringify(file));

    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.project.design.components[0]!.configOverrides).toEqual({ fillFraction: 0.5 });
    expect(parsed.warnings.some(w => /discarded/i.test(w.message))).toBe(true);
  });

  it('caps an over-long string instead of carrying it through', () => {
    const file = JSON.parse(good());
    file.metadata.name = 'a'.repeat(50_000);
    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.project.metadata.name.length).toBeLessThanOrEqual(8_000);
  });

  it('drops unknown top-level keys rather than passing them along', () => {
    const file = JSON.parse(good());
    file.arbitrary_key = 'ignored';
    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(Object.keys(parsed.project)).not.toContain('arbitrary_key');
  });

  it('refuses to load an image from an untrusted host', () => {
    const file = JSON.parse(good());
    file.assets.images = [
      { id: 'i1', url: 'https://attacker.example/tracker.png', credit: '', alt: '' },
    ];
    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.warnings.some(w => /not a trusted source/i.test(w.message))).toBe(true);
  });

  it('reports every problem at once, so the user fixes them together', () => {
    const file = JSON.parse(good());
    file.missionConfig.launchSite.latitude_deg = 500;
    file.missionConfig.launchSite.longitude_deg = 900;
    file.design.components[0].offset_z = 'not a number';

    const parsed = parseRkt(JSON.stringify(file));
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors.length).toBeGreaterThanOrEqual(3);
  });

  it('names the offending field by path', () => {
    const file = JSON.parse(good());
    file.missionConfig.environment.temperature_K = 5_000;
    const parsed = parseRkt(JSON.stringify(file));

    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors[0]!.path).toBe('mission.environment.temperature_K');
  });
});

describe('findMissingComponents', () => {
  const parsedProject = () => {
    const parsed = parseRkt(serializeRkt(buildRktProject({ design, mission, registry })));
    if (!parsed.ok) throw new Error('parse failed');
    return parsed.project;
  };

  it('finds nothing missing against the full catalogue', () => {
    expect(findMissingComponents(parsedProject(), registry.listIds())).toEqual([]);
  });

  it('names the parts a partial catalogue lacks', () => {
    // Loading against a catalogue missing a part would otherwise silently
    // produce a lighter, weaker rocket than the author designed.
    const partial = registry.listIds().filter(id => id !== 'engine_s_solid');
    expect(findMissingComponents(parsedProject(), partial)).toEqual(['engine_s_solid']);
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
