/**
 * The parts bin must be internally consistent.
 *
 * The registry already refuses duplicate ids at load, which is how the
 * `fin_m_grid` collision between the core and extended catalogues was caught.
 * These tests go further and check the properties that make a component
 * *usable* rather than merely loadable — a motor whose published impulse
 * disagrees with its own thrust curve loads fine and teaches something false.
 */

import { describe, expect, it } from 'vitest';

import { STOCK_COMPONENTS, createStockRegistry } from '../../src/core/catalog.js';
import { EXTENDED_COMPONENTS } from '../../src/core/catalog-extended.js';
import { COMPONENT_CATEGORIES } from '../../src/core/component-types.js';
import type {
  ComponentCategory,
  EngineDef,
  FinDef,
  NoseConeDef,
} from '../../src/core/component-types.js';
import { finArea, finOutline, noseRadiusAt } from '../../src/geometry/profiles.js';

describe('catalogue integrity', () => {
  it('has no duplicate ids', () => {
    const ids = STOCK_COMPONENTS.map((c) => c.id);
    const duplicates = ids.filter((id, i) => ids.indexOf(id) !== i);
    expect(duplicates).toEqual([]);
  });

  it('loads into a registry', () => {
    const registry = createStockRegistry();
    expect(registry.size).toBe(STOCK_COMPONENTS.length);
  });

  it('is large enough that component choice is a real decision', () => {
    // A parts bin with one of everything makes the builder a form, not a
    // design tool.
    expect(STOCK_COMPONENTS.length).toBeGreaterThanOrEqual(70);
    expect(EXTENDED_COMPONENTS.length).toBeGreaterThanOrEqual(45);
  });

  it('every component declares a known category', () => {
    for (const component of STOCK_COMPONENTS) {
      expect(COMPONENT_CATEGORIES).toContain(component.category);
    }
  });

  it('every component has positive dimensions and non-negative mass', () => {
    for (const component of STOCK_COMPONENTS) {
      expect(component.length_m, component.id).toBeGreaterThan(0);
      expect(component.outerDiameter_m, component.id).toBeGreaterThan(0);
      expect(component.mass_kg, component.id).toBeGreaterThanOrEqual(0);
    }
  });

  it('every component explains itself', () => {
    // A picker full of names with no descriptions is a picker nobody can use.
    for (const component of STOCK_COMPONENTS) {
      expect(component.name.length, component.id).toBeGreaterThan(3);
      expect(component.description.length, component.id).toBeGreaterThan(40);
    }
  });

  it('covers the categories a complete vehicle needs', () => {
    const present = new Set<ComponentCategory>(STOCK_COMPONENTS.map((c) => c.category));
    const required: ComponentCategory[] = [
      'nose_cone', 'body', 'coupler', 'engine', 'motor_mount', 'fuel_tank',
      'oxidizer_tank', 'fin', 'bulkhead', 'centering_ring', 'avionics',
      'sensor', 'battery', 'payload', 'decoupler', 'parachute', 'fairing',
      'interstage',
    ];
    for (const category of required) {
      expect(present.has(category), `missing category: ${category}`).toBe(true);
    }
  });
});

describe('nose cones', () => {
  const noseCones = STOCK_COMPONENTS.filter(
    (c): c is NoseConeDef => c.category === 'nose_cone',
  );

  it('offers several distinct profiles', () => {
    const shapes = new Set(noseCones.map((n) => n.shape));
    expect(shapes.size).toBeGreaterThanOrEqual(6);
  });

  it('every profile generates a usable curve at its own dimensions', () => {
    for (const cone of noseCones) {
      const radius = cone.outerDiameter_m / 2;
      for (const t of [0, 0.25, 0.5, 0.75, 1]) {
        const r = noseRadiusAt(cone.shape, t, radius, cone.length_m, cone.shapeParameter);
        expect(Number.isFinite(r), `${cone.id} at t=${t}`).toBe(true);
        expect(r).toBeGreaterThanOrEqual(-1e-9);
        expect(r).toBeLessThanOrEqual(radius + 1e-6);
      }
    }
  });

  it('fineness ratio matches the declared length and diameter', () => {
    for (const cone of noseCones) {
      const implied = cone.length_m / cone.outerDiameter_m;
      expect(implied, cone.id).toBeCloseTo(cone.finenessRatio, 1);
    }
  });
});

describe('fins', () => {
  const fins = STOCK_COMPONENTS.filter((c): c is FinDef => c.category === 'fin');

  it('offers several distinct planforms', () => {
    const shapes = new Set(fins.map((f) => f.shape ?? 'trapezoidal'));
    expect(shapes.size).toBeGreaterThanOrEqual(5);
  });

  it('every fin set encloses a positive area and has a sensible count', () => {
    for (const fin of fins) {
      const area = finArea(
        finOutline(
          fin.shape ?? 'trapezoidal',
          fin.rootChord_m,
          fin.tipChord_m,
          fin.span_m,
          fin.sweepAngle_rad,
        ),
      );
      expect(area, fin.id).toBeGreaterThan(0);
      // Barrowman is derived for 3 or 4 fins; more is unusual enough to be a
      // mistake in a stock part.
      expect(fin.finCount, fin.id).toBeGreaterThanOrEqual(3);
      expect(fin.finCount, fin.id).toBeLessThanOrEqual(6);
      expect(fin.tipChord_m, fin.id).toBeLessThanOrEqual(fin.rootChord_m + 1e-9);
    }
  });
});

describe('motors', () => {
  const engines = STOCK_COMPONENTS.filter((c): c is EngineDef => c.category === 'engine');
  const withCurves = engines.filter((e) => (e.thrustCurve?.length ?? 0) > 0);

  it('some motors carry a real thrust curve', () => {
    expect(withCurves.length).toBeGreaterThanOrEqual(5);
  });

  it('a published total impulse equals the integral of its own curve', () => {
    // The single most important consistency property in the catalogue: a motor
    // that advertises an impulse its curve does not produce teaches a number
    // the simulation will then contradict.
    for (const motor of withCurves) {
      const curve = motor.thrustCurve ?? [];
      let impulse = 0;
      for (let i = 1; i < curve.length; i += 1) {
        const a = curve[i - 1];
        const b = curve[i];
        if (!a || !b) continue;
        impulse += ((a.thrust_N + b.thrust_N) / 2) * (b.t - a.t);
      }
      expect(motor.totalImpulse_Ns, motor.id).toBeDefined();
      expect(impulse, motor.id).toBeCloseTo(motor.totalImpulse_Ns ?? 0, 0);
    }
  });

  it('a curve starts and ends at zero thrust', () => {
    for (const motor of withCurves) {
      const curve = motor.thrustCurve ?? [];
      expect(curve[0]?.thrust_N, motor.id).toBe(0);
      expect(curve[curve.length - 1]?.thrust_N, motor.id).toBe(0);
    }
  });

  it('a curve is ordered in time and spans the declared burn', () => {
    for (const motor of withCurves) {
      const curve = motor.thrustCurve ?? [];
      for (let i = 1; i < curve.length; i += 1) {
        expect(curve[i]!.t, motor.id).toBeGreaterThan(curve[i - 1]!.t);
      }
      expect(curve[curve.length - 1]!.t, motor.id).toBeCloseTo(motor.burnTime_s ?? 0, 3);
    }
  });

  it('peak thrust is at least the average, and never below it', () => {
    for (const motor of withCurves) {
      const peak = Math.max(...(motor.thrustCurve ?? []).map((p) => p.thrust_N));
      expect(peak, motor.id).toBeGreaterThanOrEqual((motor.averageThrust_N ?? 0) - 1);
      expect(motor.maxThrust_N, motor.id).toBeGreaterThanOrEqual(motor.averageThrust_N ?? 0);
    }
  });

  it('a solid motor cannot be shut down or throttled', () => {
    // The defining operational fact about a solid: once lit, it burns out.
    for (const motor of engines) {
      if (motor.propellantType !== 'solid') continue;
      expect(motor.canShutdown ?? false, motor.id).toBe(false);
      expect(motor.throttleable ?? false, motor.id).toBe(false);
      expect(motor.maxIgnitions, motor.id).toBe(1);
    }
  });

  it('every motor carries propellant it can actually expel', () => {
    for (const motor of engines) {
      if (motor.propellantType !== 'solid') continue;
      expect(motor.integralPropellant_kg, motor.id).toBeGreaterThan(0);
      // Isp and propellant mass together imply an impulse. It should be in the
      // same league as the published one — within a factor of two, which is a
      // loose enough bound to allow for rounding but tight enough to catch a
      // decimal-place error.
      const implied = motor.integralPropellant_kg * motor.isp_seaLevel_s * 9.80665;
      const published = motor.totalImpulse_Ns ?? implied;
      expect(published / implied, motor.id).toBeGreaterThan(0.5);
      expect(published / implied, motor.id).toBeLessThan(2.0);
    }
  });
});
