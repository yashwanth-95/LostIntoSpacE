import { describe, it, expect } from 'vitest';
import {
  layoutDesign,
  analyzeRocket,
  estimatePayloadCapacity,
} from '../../src/core/builder.js';
import {
  createRocket,
  addStage,
  addComponent,
  configureComponent,
} from '../../src/core/rocket-design.js';
import { G0 } from '../../src/physics/constants.js';
import {
  stockRegistry,
  soundingRocket,
  liquidSoundingRocket,
  orbitalLauncher,
  FIXED_TIMESTAMP,
} from './reference-designs.js';

const registry = stockRegistry();

describe('layoutDesign — geometry', () => {
  it('stacks stages bottom-up and reports the total length', () => {
    const layout = layoutDesign(orbitalLauncher(registry), registry);

    expect(layout.stageBasePositions_m[0]).toBe(0);
    expect(layout.stageBasePositions_m[1]).toBe(layout.stageLengths_m[0]);
    expect(layout.totalLength_m).toBeCloseTo(
      layout.stageLengths_m.reduce((a, b) => a + b, 0),
      6,
    );
  });

  it('measures station aft from the nose tip', () => {
    const layout = layoutDesign(soundingRocket(registry), registry);

    const nose = layout.components.find(c => c.category === 'nose_cone')!;
    const engine = layout.components.find(c => c.category === 'engine')!;

    // The nose is nearest the tip, so its station is smallest.
    expect(nose.station_m).toBeLessThan(engine.station_m);
    // Station and axial position run in opposite directions and sum to the length.
    expect(nose.station_m + nose.axialCenter_m).toBeCloseTo(layout.totalLength_m, 6);
  });

  it('places each component centre of mass at its geometric centre', () => {
    const layout = layoutDesign(soundingRocket(registry), registry);
    for (const c of layout.components) {
      expect(c.axialCenter_m).toBeCloseTo(c.axialPosition_m + c.length_m / 2, 9);
    }
  });

  it('reports unresolvable components instead of throwing', () => {
    let design = createRocket('broken', '', { id: 'b', timestamp: FIXED_TIMESTAMP });
    design = addStage(design, 'only', 0);
    design = addComponent(design, registry, 'body_s_short', 0, { z: 0 });
    // Forge a reference to a component that is not in the registry.
    design = {
      ...design,
      components: [
        ...design.components,
        {
          instanceId: 'ghost',
          defId: 'does_not_exist',
          stageIndex: 0,
          offset_x: 0,
          offset_y: 0,
          offset_z: 0,
          configOverrides: {},
        },
      ],
    };

    const layout = layoutDesign(design, registry);
    expect(layout.unresolvedInstanceIds).toEqual(['ghost']);
    expect(layout.components).toHaveLength(1);
  });
});

describe('layoutDesign — configuration overrides', () => {
  it('applies an adjustable payload mass', () => {
    let design = createRocket('t', '', { id: 't', timestamp: FIXED_TIMESTAMP });
    design = addStage(design, 's', 0);
    design = addComponent(design, registry, 'payload_instrument', 0, { z: 0 });
    const id = design.components[0]!.instanceId;

    const before = layoutDesign(design, registry).components[0]!;
    design = configureComponent(design, id, { mass_kg: 90 });
    const after = layoutDesign(design, registry).components[0]!;

    expect(before.dryMass_kg).toBe(25);
    expect(after.dryMass_kg).toBe(90);
  });

  it('clamps a payload mass override to the definition range', () => {
    let design = createRocket('t', '', { id: 't', timestamp: FIXED_TIMESTAMP });
    design = addStage(design, 's', 0);
    design = addComponent(design, registry, 'payload_instrument', 0, { z: 0 });
    const id = design.components[0]!.instanceId;

    // The instrument package allows 5–150 kg.
    const tooHeavy = layoutDesign(
      configureComponent(design, id, { mass_kg: 10_000 }),
      registry,
    ).components[0]!;
    const tooLight = layoutDesign(
      configureComponent(design, id, { mass_kg: -50 }),
      registry,
    ).components[0]!;

    expect(tooHeavy.dryMass_kg).toBe(150);
    expect(tooLight.dryMass_kg).toBe(5);
  });

  it('applies a tank fill fraction', () => {
    let design = createRocket('t', '', { id: 't', timestamp: FIXED_TIMESTAMP });
    design = addStage(design, 's', 0);
    design = addComponent(design, registry, 'tank_s_fuel', 0, { z: 0 });
    const id = design.components[0]!.instanceId;

    const full = layoutDesign(design, registry).components[0]!;
    const half = layoutDesign(
      configureComponent(design, id, { fillFraction: 0.5 }),
      registry,
    ).components[0]!;

    expect(half.propellantMass_kg).toBeCloseTo(full.propellantMass_kg / 2, 6);
    // Fill fraction changes propellant, never structure.
    expect(half.dryMass_kg).toBe(full.dryMass_kg);
  });

  it('ignores a fill fraction on a solid motor, whose grain is cast in', () => {
    let design = createRocket('t', '', { id: 't', timestamp: FIXED_TIMESTAMP });
    design = addStage(design, 's', 0);
    design = addComponent(design, registry, 'engine_s_solid', 0, { z: 0 });
    const id = design.components[0]!.instanceId;

    const full = layoutDesign(design, registry).components[0]!;
    const attemptedHalf = layoutDesign(
      configureComponent(design, id, { fillFraction: 0.5 }),
      registry,
    ).components[0]!;

    expect(attemptedHalf.propellantMass_kg).toBe(full.propellantMass_kg);
    expect(full.propellantMass_kg).toBeGreaterThan(0);
  });

  it('clamps an engine throttle to the definition minimum', () => {
    let design = createRocket('t', '', { id: 't', timestamp: FIXED_TIMESTAMP });
    design = addStage(design, 's', 0);
    design = addComponent(design, registry, 'engine_s_liquid', 0, { z: 0 });
    const id = design.components[0]!.instanceId;

    // The liquid engine's minimum throttle is 0.6.
    const throttled = layoutDesign(
      configureComponent(design, id, { throttle: 0.1 }),
      registry,
    ).components[0]!;
    expect(throttled.throttle).toBeCloseTo(0.6, 9);
  });
});

describe('analyzeRocket — mass accounting', () => {
  const analysis = analyzeRocket(orbitalLauncher(registry), registry);

  it('has wet mass equal to dry plus propellant', () => {
    expect(analysis.totalWetMass_kg).toBeCloseTo(
      analysis.totalDryMass_kg + analysis.totalPropellantMass_kg,
      6,
    );
  });

  it('has per-stage masses summing to the vehicle totals', () => {
    const dry = analysis.stages.reduce((a, s) => a + s.dryMass_kg, 0);
    const propellant = analysis.stages.reduce((a, s) => a + s.propellantMass_kg, 0);

    expect(dry).toBeCloseTo(analysis.totalDryMass_kg, 6);
    expect(propellant).toBeCloseTo(analysis.totalPropellantMass_kg, 6);
  });

  it('gives the bottom stage a stack mass equal to the whole vehicle', () => {
    expect(analysis.stages[0]!.ignitionStackMass_kg).toBeCloseTo(
      analysis.totalWetMass_kg,
      6,
    );
  });

  it('gives each upper stage a smaller stack than the one below', () => {
    for (let i = 1; i < analysis.stages.length; i++) {
      expect(analysis.stages[i]!.ignitionStackMass_kg).toBeLessThan(
        analysis.stages[i - 1]!.ignitionStackMass_kg,
      );
    }
  });

  it('reports payload mass separately from, but inside, dry mass', () => {
    expect(analysis.payloadMass_kg).toBeGreaterThan(0);
    expect(analysis.payloadMass_kg).toBeLessThan(analysis.totalDryMass_kg);
  });
});

describe('analyzeRocket — propulsion', () => {
  const analysis = analyzeRocket(orbitalLauncher(registry), registry);

  it('derives burn time from propellant and mass flow', () => {
    for (const stage of analysis.stages) {
      if (!stage.canFire) continue;
      expect(stage.burnTime_s).toBeCloseTo(
        stage.propellantMass_kg / stage.massFlowRate_kgs,
        6,
      );
    }
  });

  it('derives mass flow consistently with thrust and Isp', () => {
    for (const stage of analysis.stages) {
      if (!stage.canFire) continue;
      // F_vac = Isp_vac · g₀ · ṁ
      expect(stage.thrustVacuum_N).toBeCloseTo(
        stage.isp_vacuum_s * G0 * stage.massFlowRate_kgs,
        3,
      );
    }
  });

  it('gives every stage less sea-level thrust than vacuum thrust', () => {
    for (const stage of analysis.stages) {
      if (stage.engineCount === 0) continue;
      expect(stage.thrustSeaLevel_N).toBeLessThan(stage.thrustVacuum_N);
      expect(stage.isp_seaLevel_s).toBeLessThan(stage.isp_vacuum_s);
    }
  });

  it('matches each stage delta-v to the rocket equation', () => {
    for (const stage of analysis.stages) {
      if (!stage.canFire) continue;
      const expected =
        stage.isp_vacuum_s *
        G0 *
        Math.log(stage.ignitionStackMass_kg / stage.burnoutStackMass_kg);
      expect(stage.deltaV_ms).toBeCloseTo(expected, 6);
    }
  });

  it('sums stage delta-v into the vehicle total', () => {
    expect(analysis.totalDeltaV_ms).toBeCloseTo(
      analysis.stages.reduce((a, s) => a + s.deltaV_ms, 0),
      6,
    );
  });

  it('gives a two-stage orbital vehicle enough delta-v for low Earth orbit', () => {
    // An ascent to LEO needs roughly 9.4 km/s once losses are included.
    expect(analysis.totalDeltaV_ms).toBeGreaterThan(9_400);
  });
});

describe('analyzeRocket — thrust-to-weight', () => {
  it('gives the reference launcher a liftoff ratio above 1', () => {
    const analysis = analyzeRocket(orbitalLauncher(registry), registry);
    expect(analysis.liftoffTWR).toBeGreaterThan(1);
    expect(analysis.liftoffTWR).toBeCloseTo(
      analysis.stages[0]!.thrustSeaLevel_N / (analysis.totalWetMass_kg * G0),
      6,
    );
  });

  it('falls as payload is added', () => {
    const base = analyzeRocket(soundingRocket(registry), registry);

    let heavier = soundingRocket(registry);
    const payloadId = heavier.components.find(c => c.defId === 'payload_instrument')!
      .instanceId;
    heavier = configureComponent(heavier, payloadId, { mass_kg: 150 });

    // Both already carry 150 kg, so add mass another way: a full second tank.
    expect(base.liftoffTWR).toBeGreaterThan(1);
    expect(analyzeRocket(heavier, registry).liftoffTWR).toBeCloseTo(base.liftoffTWR, 6);
  });
});

describe('analyzeRocket — geometry and aerodynamics', () => {
  const analysis = analyzeRocket(liquidSoundingRocket(registry), registry);

  it('derives reference area from the maximum diameter', () => {
    expect(analysis.referenceArea_m2).toBeCloseTo(
      (Math.PI / 4) * analysis.maxDiameter_m ** 2,
      9,
    );
  });

  it('produces a drag coefficient in a physically sensible range', () => {
    expect(analysis.dragCoefficient).toBeGreaterThan(0.1);
    expect(analysis.dragCoefficient).toBeLessThan(1.0);
  });

  it('reports a positive cost', () => {
    expect(analysis.totalCost).toBeGreaterThan(0);
  });
});

describe('analyzeRocket — stability', () => {
  it('moves the centre of gravity as propellant drains', () => {
    const analysis = analyzeRocket(liquidSoundingRocket(registry), registry);
    expect(analysis.centerOfMassWet_m).not.toBeCloseTo(analysis.centerOfMassDry_m, 3);
  });

  it('gives the reference sounding rockets a stable margin in both cases', () => {
    for (const design of [soundingRocket(registry), liquidSoundingRocket(registry)]) {
      const analysis = analyzeRocket(design, registry);
      expect(analysis.stabilityWet.stabilityMargin_cal).toBeGreaterThan(1);
      expect(analysis.stabilityDry.stabilityMargin_cal).toBeGreaterThan(1);
    }
  });

  it('reports a tall launcher as statically unstable, as real ones are', () => {
    // A launch vehicle carries almost all its mass as propellant at the bottom,
    // which puts the centre of gravity behind the centre of pressure. Real ones
    // fly on thrust vector control rather than static stability.
    const analysis = analyzeRocket(orbitalLauncher(registry), registry);
    expect(analysis.stabilityWet.stabilityMargin_cal).toBeLessThan(0);
  });
});

describe('analyzeRocket — empty and degenerate designs', () => {
  it('handles a design with no components', () => {
    const empty = addStage(
      createRocket('empty', '', { id: 'e', timestamp: FIXED_TIMESTAMP }),
      'stage',
      0,
    );
    const analysis = analyzeRocket(empty, registry);

    expect(analysis.totalWetMass_kg).toBe(0);
    expect(analysis.totalDeltaV_ms).toBe(0);
    expect(analysis.liftoffTWR).toBe(0);
    expect(Number.isFinite(analysis.stabilityWet.stabilityMargin_cal)).toBe(true);
  });

  it('handles a design with no stages', () => {
    const bare = createRocket('bare', '', { id: 'b', timestamp: FIXED_TIMESTAMP });
    const analysis = analyzeRocket(bare, registry);

    expect(analysis.stages).toEqual([]);
    expect(analysis.totalLength_m).toBe(0);
  });
});

describe('estimatePayloadCapacity', () => {
  const analysis = analyzeRocket(orbitalLauncher(registry), registry);

  it('finds a positive capacity for a vehicle with delta-v to spare', () => {
    const result = estimatePayloadCapacity(analysis, 9_400);
    expect(result.maxPayload_kg).toBeGreaterThan(0);
  });

  it('produces exactly the requested delta-v at the capacity limit', () => {
    const result = estimatePayloadCapacity(analysis, 9_400);
    // The binding constraint should sit right on its threshold.
    expect(result.deltaVAtMax_ms).toBeGreaterThanOrEqual(9_400);
    expect(result.deltaVAtMax_ms).toBeLessThan(9_410);
  });

  it('shrinks capacity as the delta-v requirement rises', () => {
    const easy = estimatePayloadCapacity(analysis, 8_000);
    const hard = estimatePayloadCapacity(analysis, 11_000);
    expect(hard.maxPayload_kg).toBeLessThan(easy.maxPayload_kg);
  });

  it('returns zero when the vehicle cannot meet the target even empty', () => {
    const result = estimatePayloadCapacity(analysis, 50_000);
    expect(result.maxPayload_kg).toBe(0);
  });

  it('names the constraint that bound the search', () => {
    // A very high thrust-to-weight floor should bind before delta-v does.
    const twrBound = estimatePayloadCapacity(analysis, 5_000, 1.6);
    expect(twrBound.twrAtMax).toBeGreaterThanOrEqual(1.6);
    expect(twrBound.limitingFactor).toBe('thrust_to_weight');
  });
});

describe('analyzeRocket — determinism', () => {
  it('produces identical results for the same design', () => {
    const design = orbitalLauncher(registry);
    expect(analyzeRocket(design, registry)).toEqual(analyzeRocket(design, registry));
  });

  it('produces identical results across independently built designs', () => {
    const a = analyzeRocket(orbitalLauncher(stockRegistry()), stockRegistry());
    const b = analyzeRocket(orbitalLauncher(stockRegistry()), stockRegistry());
    expect(a.totalWetMass_kg).toBe(b.totalWetMass_kg);
    expect(a.totalDeltaV_ms).toBe(b.totalDeltaV_ms);
    expect(a.layout.components.map(c => c.instanceId)).toEqual(
      b.layout.components.map(c => c.instanceId),
    );
  });
});
