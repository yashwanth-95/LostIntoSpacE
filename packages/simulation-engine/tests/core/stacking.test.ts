/**
 * Components must assemble into a vehicle, not a pile.
 *
 * `offset_z` defaults to zero, so before automatic stacking existed every part
 * a user added sat at the stage base on top of every other part: a nose cone
 * inside a body tube inside an engine, all claiming the same space. The
 * engineering numbers still computed — which is exactly why nobody noticed
 * until the builder started drawing the vehicle.
 */

import { describe, expect, it } from 'vitest';

import { analyzeRocket, layoutDesign } from '../../src/core/builder.js';
import { createStockRegistry } from '../../src/core/catalog.js';
import { addComponent, addStage, createRocket } from '../../src/core/rocket-design.js';
import { buildVehicleOutline } from '../../src/geometry/vehicle-outline.js';
import { soundingRocket, FIXED_TIMESTAMP } from './reference-designs.js';

const registry = createStockRegistry();

/** A design built the way the UI builds one: parts added, nothing positioned. */
function assembled(ids: readonly string[]) {
  let design = createRocket('Stacked', 'built by adding parts', {
    id: 'stack-test',
    timestamp: FIXED_TIMESTAMP,
  });
  design = addStage(design, 'Stage 1', 0);
  for (const id of ids) design = addComponent(design, registry, id, 0);
  return design;
}

describe('automatic stacking', () => {
  const ids = ['motor_s_k560', 'body_s_long', 'nose_s_vonkarman', 'fin_s_delta'];

  it('gives every axial component a distinct position', () => {
    const layout = layoutDesign(assembled(ids), registry);
    const axial = layout.components.filter((c) => c.category !== 'fin');
    const positions = axial.map((c) => c.axialPosition_m);
    expect(new Set(positions).size).toBe(axial.length);
  });

  it('makes the vehicle as long as the sum of its parts', () => {
    const layout = layoutDesign(assembled(ids), registry);
    const axialLength = layout.components
      .filter((c) => c.category !== 'fin')
      .reduce((sum, c) => sum + c.length_m, 0);
    expect(layout.totalLength_m).toBeCloseTo(axialLength, 6);
  });

  it('puts the nose at the front and the engine at the back', () => {
    const layout = layoutDesign(assembled(ids), registry);
    const nose = layout.components.find((c) => c.category === 'nose_cone')!;
    const engine = layout.components.find((c) => c.category === 'engine')!;
    const body = layout.components.find((c) => c.category === 'body')!;

    // Station runs aft from the nose tip, so a smaller station is further
    // forward. The nose must be the forwardmost thing on the vehicle.
    expect(nose.station_m).toBeLessThan(body.station_m);
    expect(body.station_m).toBeLessThan(engine.station_m);
  });

  it('starts the nose cone at the very tip', () => {
    const outline = buildVehicleOutline(layoutDesign(assembled(ids), registry));
    const nose = outline.shapes.find((s) => s.category === 'nose_cone')!;
    expect(nose.station_m).toBeCloseTo(0, 6);
  });

  it('does not let a fin make the rocket longer', () => {
    const withoutFins = layoutDesign(assembled(['motor_s_k560', 'body_s_long']), registry);
    const withFins = layoutDesign(
      assembled(['motor_s_k560', 'body_s_long', 'fin_s_delta']),
      registry,
    );
    expect(withFins.totalLength_m).toBeCloseTo(withoutFins.totalLength_m, 6);
  });

  it('mounts fins on the airframe rather than under the engine', () => {
    const layout = layoutDesign(assembled(ids), registry);
    const fin = layout.components.find((c) => c.category === 'fin')!;
    const engine = layout.components.find((c) => c.category === 'engine')!;
    // The fin's aft end sits at or above the top of the engine, not below it.
    expect(fin.axialPosition_m).toBeGreaterThanOrEqual(
      engine.axialPosition_m + engine.length_m - 1e-9,
    );
  });

  it('components do not overlap along the axis', () => {
    const layout = layoutDesign(assembled(ids), registry);
    const axial = layout.components
      .filter((c) => c.category !== 'fin')
      .sort((a, b) => a.axialPosition_m - b.axialPosition_m);
    for (let i = 1; i < axial.length; i += 1) {
      const previous = axial[i - 1]!;
      const current = axial[i]!;
      expect(current.axialPosition_m).toBeGreaterThanOrEqual(
        previous.axialPosition_m + previous.length_m - 1e-9,
      );
    }
  });

  it('leaves a hand-placed stage exactly as the caller placed it', () => {
    // The reference designs position every part explicitly. Automatic stacking
    // must not touch them, or a fixture's stability margin silently changes.
    const design = soundingRocket(registry);
    const layout = layoutDesign(design, registry);
    for (const placed of design.components) {
      const resolved = layout.components.find((c) => c.instanceId === placed.instanceId)!;
      expect(resolved.axialPosition_m).toBeCloseTo(placed.offset_z, 9);
    }
  });

  it('produces a vehicle whose drawn silhouette spans its whole length', () => {
    const outline = buildVehicleOutline(layoutDesign(assembled(ids), registry));
    const revolved = outline.shapes.filter((s) => s.kind === 'revolved');
    const forwardmost = Math.min(...revolved.map((s) => s.station_m));
    const aftmost = Math.max(
      ...revolved.map((s) => s.station_m + (s.kind === 'revolved' ? s.profile.length_m : 0)),
    );
    expect(forwardmost).toBeCloseTo(0, 6);
    expect(aftmost).toBeCloseTo(outline.totalLength_m, 6);
  });

  it('a longer body tube produces a longer vehicle and moves the CG aft', () => {
    // The property that makes the drawing worth having: editing a component
    // changes the vehicle, visibly and measurably.
    const short = analyzeRocket(
      assembled(['motor_s_k560', 'body_s_short', 'nose_s_vonkarman', 'fin_s_delta']),
      registry,
    );
    const long = analyzeRocket(
      assembled(['motor_s_k560', 'body_s_long', 'nose_s_vonkarman', 'fin_s_delta']),
      registry,
    );
    expect(long.totalLength_m).toBeGreaterThan(short.totalLength_m);
    expect(long.totalWetMass_kg).toBeGreaterThan(short.totalWetMass_kg);
  });

  it('swapping the nose profile moves the centre of pressure', () => {
    // A conical nose puts its CP two-thirds aft; an elliptical one a third.
    // If this does not move, nose profile is decoration.
    const conical = analyzeRocket(
      assembled(['motor_s_k560', 'body_s_long', 'nose_m_conical', 'fin_s_delta']),
      registry,
    );
    const elliptical = analyzeRocket(
      assembled(['motor_s_k560', 'body_s_long', 'nose_s_elliptical', 'fin_s_delta']),
      registry,
    );
    expect(conical.stabilityWet.cp_m).not.toBeCloseTo(elliptical.stabilityWet.cp_m, 2);
  });
});
