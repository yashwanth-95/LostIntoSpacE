import { describe, it, expect } from 'vitest';
import {
  validateRocket,
  DEFAULT_THRESHOLDS,
  type ValidationCode,
} from '../../src/core/validation.js';
import {
  createRocket,
  addStage,
  addComponent,
  configureComponent,
} from '../../src/core/rocket-design.js';
import { toVehicle, currentMass, hasRemainingStages } from '../../src/core/vehicle.js';
import { STOCK_COMPONENTS, createStockRegistry } from '../../src/core/catalog.js';
import { validateComponentDef } from '../../src/core/component-registry.js';
import {
  stockRegistry,
  soundingRocket,
  liquidSoundingRocket,
  orbitalLauncher,
  underpoweredRocket,
  finlessRocket,
  FIXED_TIMESTAMP,
} from './reference-designs.js';

const registry = stockRegistry();

/** Codes present in a validation result. */
function codes(design: Parameters<typeof validateRocket>[0]): ValidationCode[] {
  return validateRocket(design, registry).issues.map(i => i.code);
}

describe('stock catalogue', () => {
  it('passes the registry validation rules for every entry', () => {
    for (const def of STOCK_COMPONENTS) {
      expect(validateComponentDef(def), def.id).toEqual([]);
    }
  });

  it('has unique ids', () => {
    const ids = STOCK_COMPONENTS.map(c => c.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('gives every component a description and a cost', () => {
    for (const def of STOCK_COMPONENTS) {
      expect(def.description.length, def.id).toBeGreaterThan(20);
      expect(def.cost, def.id).toBeGreaterThan(0);
    }
  });

  it('gives every component positive dimensions and non-negative mass', () => {
    for (const def of STOCK_COMPONENTS) {
      expect(def.length_m, def.id).toBeGreaterThan(0);
      expect(def.outerDiameter_m, def.id).toBeGreaterThan(0);
      expect(def.mass_kg, def.id).toBeGreaterThanOrEqual(0);
    }
  });

  it('gives every engine a vacuum rating above its sea-level rating', () => {
    for (const def of STOCK_COMPONENTS) {
      if (def.category !== 'engine') continue;
      expect(def.thrust_N, def.id).toBeGreaterThan(def.thrustSeaLevel_N);
      expect(def.isp_vacuum_s, def.id).toBeGreaterThan(def.isp_seaLevel_s);
    }
  });

  it('gives every engine a specific impulse in a physically real range', () => {
    for (const def of STOCK_COMPONENTS) {
      if (def.category !== 'engine') continue;
      // Cold gas sits near 60 s; the best chemical engines reach about 460 s.
      expect(def.isp_vacuum_s, def.id).toBeGreaterThan(50);
      expect(def.isp_vacuum_s, def.id).toBeLessThan(500);
    }
  });

  it('only gives integral propellant to solid motors', () => {
    for (const def of STOCK_COMPONENTS) {
      if (def.category !== 'engine') continue;
      if (def.propellantType === 'solid') {
        expect(def.integralPropellant_kg, def.id).toBeGreaterThan(0);
      } else {
        expect(def.integralPropellant_kg, def.id).toBe(0);
      }
    }
  });

  it('gives every tank a capacity consistent with its volume and density', () => {
    for (const def of STOCK_COMPONENTS) {
      if (def.category === 'fuel_tank') {
        expect(def.capacity_kg, def.id).toBeCloseTo(def.volume_m3 * def.fuelDensity_kgm3, -3);
      } else if (def.category === 'oxidizer_tank') {
        expect(def.capacity_kg, def.id).toBeCloseTo(
          def.volume_m3 * def.oxidizerDensity_kgm3,
          -3,
        );
      }
    }
  });

  it('gives every fin set a tip chord no larger than its root chord', () => {
    for (const def of STOCK_COMPONENTS) {
      if (def.category !== 'fin') continue;
      expect(def.tipChord_m, def.id).toBeLessThanOrEqual(def.rootChord_m);
      expect(def.finCount, def.id).toBeGreaterThanOrEqual(3);
    }
  });

  it('returns an independent registry each time', () => {
    const a = createStockRegistry();
    const b = createStockRegistry();
    a.unregister('nose_s_ogive');

    expect(a.has('nose_s_ogive')).toBe(false);
    expect(b.has('nose_s_ogive')).toBe(true);
  });
});

describe('validateRocket — healthy designs', () => {
  it('finds no errors in the reference sounding rockets', () => {
    for (const design of [soundingRocket(registry), liquidSoundingRocket(registry)]) {
      const result = validateRocket(design, registry);
      expect(result.valid, result.errors.map(e => e.message).join('; ')).toBe(true);
      expect(result.canSimulate).toBe(true);
    }
  });

  it('finds no errors in the reference orbital launcher', () => {
    const result = validateRocket(orbitalLauncher(registry), registry);
    expect(result.valid, result.errors.map(e => e.message).join('; ')).toBe(true);
  });

  it('returns the analysis it used, so callers need not recompute it', () => {
    const result = validateRocket(orbitalLauncher(registry), registry);
    expect(result.analysis.totalWetMass_kg).toBeGreaterThan(0);
  });

  it('sorts issues into severity buckets that add up', () => {
    const result = validateRocket(finlessRocket(registry), registry);
    expect(result.errors.length + result.warnings.length + result.infos.length).toBe(
      result.issues.length,
    );
  });
});

describe('validateRocket — propulsion rules', () => {
  it('rejects a rocket with no engine', () => {
    let design = createRocket('Glider', '', { id: 'g', timestamp: FIXED_TIMESTAMP });
    design = addStage(design, 'only', 0);
    design = addComponent(design, registry, 'body_s_short', 0, { z: 0 });
    design = addComponent(design, registry, 'nose_s_ogive', 0, { z: 1 });

    const result = validateRocket(design, registry);
    expect(result.valid).toBe(false);
    expect(result.errors.map(e => e.code)).toContain('NO_ENGINE');
  });

  it('rejects a liquid engine with no tanks', () => {
    let design = createRocket('Dry', '', { id: 'd', timestamp: FIXED_TIMESTAMP });
    design = addStage(design, 'only', 0);
    design = addComponent(design, registry, 'engine_s_liquid', 0, { z: 0 });
    design = addComponent(design, registry, 'nose_s_ogive', 0, { z: 1.1 });

    expect(codes(design)).toContain('ENGINE_WITHOUT_PROPELLANT');
  });

  it('accepts a solid motor with no tanks, since its grain is cast in', () => {
    let design = createRocket('Solid', '', { id: 's', timestamp: FIXED_TIMESTAMP });
    design = addStage(design, 'only', 0);
    design = addComponent(design, registry, 'engine_s_solid', 0, { z: 0 });
    design = addComponent(design, registry, 'nose_s_ogive', 0, { z: 2.5 });

    expect(codes(design)).not.toContain('ENGINE_WITHOUT_PROPELLANT');
  });

  it('warns about tanks with no engine to feed', () => {
    let design = createRocket('Ballast', '', { id: 'b', timestamp: FIXED_TIMESTAMP });
    design = addStage(design, 'lower', 0);
    design = addComponent(design, registry, 'engine_s_liquid', 0, { z: 0 });
    design = addComponent(design, registry, 'tank_s_ox', 0, { z: 1.1 });
    design = addComponent(design, registry, 'tank_s_fuel', 0, { z: 3.6 });
    design = addStage(design, 'upper', 1);
    design = addComponent(design, registry, 'tank_s_fuel', 1, { z: 0 });

    expect(codes(design)).toContain('PROPELLANT_WITHOUT_ENGINE');
  });

  it('rejects a vehicle that cannot lift its own weight', () => {
    const result = validateRocket(underpoweredRocket(registry), registry);
    expect(result.valid).toBe(false);

    const issue = result.errors.find(e => e.code === 'INSUFFICIENT_LIFTOFF_TWR')!;
    expect(issue.actual).toBeLessThan(1);
    expect(issue.expected).toBe(DEFAULT_THRESHOLDS.minLiftoffTWR);
    expect(issue.unit).toBe('ratio');
    expect(issue.explanation).toMatch(/thrust must exceed weight/i);
  });

  it('warns about a marginal but survivable thrust-to-weight', () => {
    let design = soundingRocket(registry);
    const payloadId = design.components.find(c => c.defId === 'payload_instrument')!
      .instanceId;
    // Heavy enough to drag the ratio into the marginal band without killing it.
    design = configureComponent(design, payloadId, { mass_kg: 150 });

    const marginal = validateRocket(design, registry, {
      thresholds: { recommendedLiftoffTWR: 20 },
    });
    expect(marginal.warnings.map(w => w.code)).toContain('MARGINAL_LIFTOFF_TWR');
  });

  it('warns about an excessive thrust-to-weight', () => {
    const result = validateRocket(soundingRocket(registry), registry, {
      thresholds: { maxLiftoffTWR: 1.1 },
    });
    expect(result.warnings.map(w => w.code)).toContain('EXCESSIVE_LIFTOFF_TWR');
  });

  it('warns about a burn too short for guidance to act', () => {
    const result = validateRocket(soundingRocket(registry), registry, {
      thresholds: { minBurnTime_s: 1_000 },
    });
    expect(result.warnings.map(w => w.code)).toContain('SHORT_BURN_TIME');
  });
});

describe('validateRocket — aerodynamic rules', () => {
  it('warns about a missing nose cone', () => {
    let design = createRocket('Blunt', '', { id: 'b', timestamp: FIXED_TIMESTAMP });
    design = addStage(design, 'only', 0);
    design = addComponent(design, registry, 'engine_s_solid', 0, { z: 0 });
    design = addComponent(design, registry, 'body_s_short', 0, { z: 2.5 });

    expect(codes(design)).toContain('NO_NOSE_CONE');
  });

  it('warns that a finless rocket will tumble', () => {
    const result = validateRocket(finlessRocket(registry), registry);
    const issue = result.issues.find(i => i.code === 'STATICALLY_UNSTABLE')!;

    expect(issue).toBeDefined();
    expect(issue.severity).toBe('warning');
    expect(issue.actual).toBeLessThan(0.5);
    expect(issue.explanation).toMatch(/tumble/i);
  });

  it('downgrades static instability to information when the vehicle can steer', () => {
    // Every real launch vehicle is statically unstable and flies on thrust
    // vector control, so warning about it would teach the wrong lesson.
    const result = validateRocket(orbitalLauncher(registry), registry);
    const issue = result.issues.find(i => i.code === 'STATICALLY_UNSTABLE')!;

    expect(issue.severity).toBe('info');
    expect(issue.explanation).toMatch(/gimball/i);
    expect(issue.recommendation).toMatch(/no change needed/i);
  });

  it('flags an over-stable vehicle as information, not a problem', () => {
    const result = validateRocket(soundingRocket(registry), registry, {
      thresholds: { maxStabilityMargin_cal: 0.1 },
    });
    const issue = result.infos.find(i => i.code === 'OVERSTABLE')!;
    expect(issue).toBeDefined();
    expect(issue.explanation).toMatch(/weathercock/i);
  });

  it('judges stability on the worse of the wet and dry cases', () => {
    // Propellant sits at the tail, so a vehicle usually gets less stable, not
    // more, as it drains. Checking only the fuelled case would miss that.
    const result = validateRocket(soundingRocket(registry), registry);
    const issue = result.issues.find(
      i => i.code === 'STATICALLY_UNSTABLE' || i.code === 'MARGINAL_STABILITY',
    );
    if (issue) {
      const worst = Math.min(
        result.analysis.stabilityWet.stabilityMargin_cal,
        result.analysis.stabilityDry.stabilityMargin_cal,
      );
      expect(issue.actual).toBeCloseTo(worst, 6);
    }
  });
});

describe('validateRocket — systems and mission fit', () => {
  it('warns about a rocket with no avionics', () => {
    expect(codes(finlessRocket(registry))).toContain('NO_AVIONICS');
  });

  it('notes a rocket with no payload', () => {
    const result = validateRocket(finlessRocket(registry), registry);
    const issue = result.infos.find(i => i.code === 'NO_PAYLOAD')!;
    expect(issue).toBeDefined();
    expect(issue.severity).toBe('info');
  });

  it('warns about a missing recovery system only when the mission needs one', () => {
    const without = validateRocket(soundingRocket(registry), registry);
    expect(without.issues.map(i => i.code)).not.toContain('NO_RECOVERY');

    const withRequirement = validateRocket(soundingRocket(registry), registry, {
      requiresRecovery: true,
    });
    expect(withRequirement.warnings.map(w => w.code)).toContain('NO_RECOVERY');
  });

  it('warns when the vehicle lacks the delta-v the mission needs', () => {
    const result = validateRocket(soundingRocket(registry), registry, {
      requiredDeltaV_ms: 9_400,
    });
    const issue = result.warnings.find(w => w.code === 'INSUFFICIENT_DELTA_V')!;

    expect(issue).toBeDefined();
    expect(issue.actual).toBeLessThan(9_400);
    expect(issue.expected).toBe(9_400);
    expect(issue.explanation).toMatch(/rocket equation/i);
  });

  it('stays quiet when the vehicle has the delta-v it needs', () => {
    const result = validateRocket(orbitalLauncher(registry), registry, {
      requiredDeltaV_ms: 9_400,
    });
    expect(result.issues.map(i => i.code)).not.toContain('INSUFFICIENT_DELTA_V');
  });
});

describe('validateRocket — issue quality', () => {
  it('gives every issue the fields the UI and the AI layer need', () => {
    const result = validateRocket(underpoweredRocket(registry), registry, {
      requiredDeltaV_ms: 9_400,
      requiresRecovery: true,
    });

    expect(result.issues.length).toBeGreaterThan(0);
    for (const issue of result.issues) {
      expect(issue.code, 'code').toBeTruthy();
      expect(issue.message.length, issue.code).toBeGreaterThan(10);
      expect(issue.explanation.length, issue.code).toBeGreaterThan(40);
      expect(issue.recommendation.length, issue.code).toBeGreaterThan(10);
      expect(['error', 'warning', 'info']).toContain(issue.severity);
    }
  });

  it('pairs a measured value with its threshold and unit wherever it has one', () => {
    const result = validateRocket(underpoweredRocket(registry), registry);
    for (const issue of result.issues) {
      if (issue.actual !== undefined) {
        expect(issue.unit, issue.code).toBeTruthy();
      }
    }
  });

  it('handles an entirely empty design without throwing', () => {
    const empty = createRocket('nothing', '', { id: 'n', timestamp: FIXED_TIMESTAMP });
    const result = validateRocket(empty, registry);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });
});

describe('toVehicle', () => {
  const vehicle = toVehicle(orbitalLauncher(registry), registry);

  it('carries one entry per design stage', () => {
    expect(vehicle.stages).toHaveLength(2);
    expect(vehicle.stages.map(s => s.stageNumber)).toEqual([0, 1]);
  });

  it('keeps the design id, so a run can be traced back', () => {
    expect(vehicle.designId).toBe('ref-orbital');
  });

  it('takes its structural limits from the weakest component', () => {
    // A stack is only as strong as the first thing that gives way.
    expect(vehicle.maxDynamicPressure_Pa).toBeGreaterThan(0);
    expect(Number.isFinite(vehicle.maxDynamicPressure_Pa)).toBe(true);
    expect(vehicle.maxAxialLoad_N).toBeGreaterThan(0);
  });

  it('reads separation timing from the stage decoupler', () => {
    // The orbital launcher's first stage carries an M-class separation ring.
    expect(vehicle.stages[0]!.separationDelay_s).toBeCloseTo(0.4, 6);
  });

  it('serializes cleanly for a Web Worker', () => {
    expect(() => structuredClone(vehicle)).not.toThrow();
    expect(JSON.parse(JSON.stringify(vehicle))).toEqual(vehicle);
  });
});

describe('currentMass', () => {
  const vehicle = toVehicle(orbitalLauncher(registry), registry);

  it('equals the launch mass with every stage attached and full', () => {
    expect(currentMass(vehicle, 0, vehicle.stages[0]!.propellantMass_kg)).toBeCloseTo(
      vehicle.launchMass_kg,
      6,
    );
  });

  it('drops as the active stage burns', () => {
    const full = currentMass(vehicle, 0, vehicle.stages[0]!.propellantMass_kg);
    const half = currentMass(vehicle, 0, vehicle.stages[0]!.propellantMass_kg / 2);
    expect(half).toBeLessThan(full);
  });

  it('drops again when a stage separates', () => {
    const beforeStaging = currentMass(vehicle, 0, 0);
    const afterStaging = currentMass(vehicle, 1, vehicle.stages[1]!.propellantMass_kg);
    expect(afterStaging).toBeLessThan(beforeStaging);
    expect(beforeStaging - afterStaging).toBeCloseTo(vehicle.stages[0]!.dryMass_kg, 6);
  });

  it('treats negative propellant as empty', () => {
    expect(currentMass(vehicle, 0, -100)).toBe(currentMass(vehicle, 0, 0));
  });

  it('is zero once every stage has gone', () => {
    expect(currentMass(vehicle, vehicle.stages.length, 0)).toBe(0);
  });
});

describe('hasRemainingStages', () => {
  const vehicle = toVehicle(orbitalLauncher(registry), registry);

  it('sees the upper stage from the bottom', () => {
    expect(hasRemainingStages(vehicle, 1)).toBe(true);
  });

  it('sees nothing past the top', () => {
    expect(hasRemainingStages(vehicle, 2)).toBe(false);
  });
});
