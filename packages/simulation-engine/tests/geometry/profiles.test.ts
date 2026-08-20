/**
 * Nose profiles and fin planforms must be the real generating curves.
 *
 * These tests check the properties that make a profile *that* profile — a
 * tangent ogive meets the body tangentially, von Kármán is the C = 0 Haack
 * body, a delta has no tip chord — because an approximation that merely looks
 * roughly right is exactly how a cone ends up standing in for every nose.
 */

import { describe, expect, it } from 'vitest';

import {
  DEFAULT_PROFILE_SEGMENTS,
  equivalentTrapezoid,
  finArea,
  finOutline,
  noseConeProfile,
  noseRadiusAt,
  nozzleProfile,
  transitionProfile,
  tubeProfile,
} from '../../src/geometry/profiles.js';
import type { NoseConeShape } from '../../src/core/component-types.js';

const ALL_SHAPES: NoseConeShape[] = [
  'conical',
  'ogive',
  'tangent_ogive',
  'secant_ogive',
  'von_karman',
  'haack',
  'elliptical',
  'parabolic',
  'power_series',
  'blunt',
  'custom',
];

const R = 0.75; // base radius, m
const L = 3.0; // nose length, m

describe('nose cone profiles', () => {
  it.each(ALL_SHAPES)('%s starts at zero radius and ends at the base radius', (shape) => {
    expect(noseRadiusAt(shape, 0, R, L)).toBeCloseTo(0, 6);
    expect(noseRadiusAt(shape, 1, R, L)).toBeCloseTo(R, 3);
  });

  it.each(ALL_SHAPES)('%s never exceeds the base radius or goes negative', (shape) => {
    for (let i = 0; i <= 100; i += 1) {
      const radius = noseRadiusAt(shape, i / 100, R, L);
      expect(radius).toBeGreaterThanOrEqual(-1e-9);
      expect(radius).toBeLessThanOrEqual(R + 1e-6);
      expect(Number.isFinite(radius)).toBe(true);
    }
  });

  it.each(ALL_SHAPES)('%s increases monotonically from tip to base', (shape) => {
    let previous = -1;
    for (let i = 0; i <= 60; i += 1) {
      const radius = noseRadiusAt(shape, i / 60, R, L);
      expect(radius).toBeGreaterThanOrEqual(previous - 1e-9);
      previous = radius;
    }
  });

  it('a conical profile is exactly linear', () => {
    expect(noseRadiusAt('conical', 0.5, R, L)).toBeCloseTo(R / 2, 9);
    expect(noseRadiusAt('conical', 0.25, R, L)).toBeCloseTo(R / 4, 9);
  });

  it('a tangent ogive meets the body tangentially', () => {
    // Tangency means the profile's slope goes to zero at the base: the cone
    // blends into the tube with no visible corner. This is the defining
    // property, and the property a triangle does not have.
    const h = 1e-4;
    const slopeAtBase = (noseRadiusAt('tangent_ogive', 1, R, L) -
      noseRadiusAt('tangent_ogive', 1 - h, R, L)) / (h * L);
    expect(Math.abs(slopeAtBase)).toBeLessThan(0.02);

    // A cone, by contrast, meets it at a definite angle.
    const coneSlope = (noseRadiusAt('conical', 1, R, L) -
      noseRadiusAt('conical', 1 - h, R, L)) / (h * L);
    expect(coneSlope).toBeCloseTo(R / L, 3);
  });

  it('von Kármán is the C = 0 member of the Haack series', () => {
    for (const t of [0.2, 0.4, 0.6, 0.8]) {
      const vonKarman = noseRadiusAt('von_karman', t, R, L);
      const haackC0 = noseRadiusAt('haack', t, R, L, 0);
      expect(vonKarman).toBeCloseTo(haackC0, 9);
    }
  });

  it('a parabolic profile with K = 0 degenerates to a cone', () => {
    for (const t of [0.25, 0.5, 0.75]) {
      expect(noseRadiusAt('parabolic', t, R, L, 0)).toBeCloseTo(
        noseRadiusAt('conical', t, R, L),
        9,
      );
    }
  });

  it('a power series with n = 1 degenerates to a cone', () => {
    for (const t of [0.3, 0.6, 0.9]) {
      expect(noseRadiusAt('power_series', t, R, L, 1)).toBeCloseTo(
        noseRadiusAt('conical', t, R, L),
        9,
      );
    }
  });

  it('an elliptical nose is blunter than a cone everywhere', () => {
    // The whole reason to choose one: it carries more volume forward.
    for (const t of [0.1, 0.3, 0.5, 0.7, 0.9]) {
      expect(noseRadiusAt('elliptical', t, R, L)).toBeGreaterThan(
        noseRadiusAt('conical', t, R, L),
      );
    }
  });

  it('profiles differ enough from each other to be worth choosing between', () => {
    // If every shape produced nearly the same curve, the parameter would be
    // decoration. At mid-length they should be visibly distinct.
    const midpoints = ALL_SHAPES.map((shape) => noseRadiusAt(shape, 0.5, R, L));
    const spread = Math.max(...midpoints) - Math.min(...midpoints);
    expect(spread).toBeGreaterThan(0.15 * R);
  });

  it('samples a profile ready to lathe', () => {
    const profile = noseConeProfile('von_karman', R, L);
    expect(profile.stations).toHaveLength(DEFAULT_PROFILE_SEGMENTS + 1);
    expect(profile.radii).toHaveLength(DEFAULT_PROFILE_SEGMENTS + 1);
    expect(profile.length_m).toBe(L);
    expect(profile.maxRadius_m).toBeCloseTo(R, 3);
    expect(profile.stations[0]).toBe(0);
    expect(profile.stations[profile.stations.length - 1]).toBeCloseTo(L, 9);
  });

  it('degenerate dimensions produce a flat profile rather than NaN', () => {
    expect(noseRadiusAt('von_karman', 0.5, 0, L)).toBe(0);
    expect(noseRadiusAt('von_karman', 0.5, R, 0)).toBe(0);
    const profile = noseConeProfile('haack', 0, 0);
    expect(profile.radii.every((r) => Number.isFinite(r))).toBe(true);
  });
});

describe('body and nozzle profiles', () => {
  it('a tube has constant radius', () => {
    const profile = tubeProfile(0.5, 4);
    expect(profile.radii).toEqual([0.5, 0.5]);
    expect(profile.length_m).toBe(4);
  });

  it('a transition interpolates between two diameters', () => {
    const profile = transitionProfile(0.3, 0.9, 1.2, 6);
    expect(profile.radii[0]).toBeCloseTo(0.3, 9);
    expect(profile.radii[profile.radii.length - 1]).toBeCloseTo(0.9, 9);
    expect(profile.maxRadius_m).toBeCloseTo(0.9, 9);
    // Monotonic, so a boat-tail never bulges.
    for (let i = 1; i < profile.radii.length; i += 1) {
      expect(profile.radii[i]).toBeGreaterThanOrEqual(profile.radii[i - 1]);
    }
  });

  it('a nozzle flares from throat to exit', () => {
    const profile = nozzleProfile(0.1, 0.6, 1.0);
    expect(profile.radii[0]).toBeCloseTo(0.1, 9);
    expect(profile.radii[profile.radii.length - 1]).toBeCloseTo(0.6, 9);
    // The bell expands fastest near the throat, which is what makes it a bell
    // rather than a cone.
    const midpoint = profile.radii[Math.floor(profile.radii.length / 2)];
    expect(midpoint).toBeGreaterThan((0.1 + 0.6) / 2);
  });
});

describe('fin planforms', () => {
  const rootChord = 0.6;
  const tipChord = 0.25;
  const span = 0.4;
  const sweep = Math.PI / 6; // 30°

  it('a delta has no tip chord', () => {
    const outline = finOutline('delta', rootChord, tipChord, span, sweep);
    expect(outline).toHaveLength(3);
    const tipPoints = outline.filter((p) => Math.abs(p.y - span) < 1e-9);
    expect(tipPoints).toHaveLength(1);
  });

  it('a clipped delta keeps a finite tip chord', () => {
    const outline = finOutline('clipped_delta', rootChord, tipChord, span, sweep);
    const tipPoints = outline.filter((p) => Math.abs(p.y - span) < 1e-9);
    expect(tipPoints).toHaveLength(2);
    const chord = Math.abs(tipPoints[0].x - tipPoints[1].x);
    expect(chord).toBeCloseTo(tipChord, 9);
  });

  it('a rectangular fin has equal root and tip chords and no sweep', () => {
    const outline = finOutline('rectangular', rootChord, tipChord, span, sweep);
    const root = outline.filter((p) => Math.abs(p.y) < 1e-9);
    const tip = outline.filter((p) => Math.abs(p.y - span) < 1e-9);
    expect(Math.abs(root[1].x - root[0].x)).toBeCloseTo(rootChord, 9);
    expect(Math.abs(tip[0].x - tip[1].x)).toBeCloseTo(rootChord, 9);
  });

  it('a swept trapezoid places its tip aft by span·tan(sweep)', () => {
    const outline = finOutline('trapezoidal', rootChord, tipChord, span, sweep);
    const tipLeadingEdge = outline.find((p) => Math.abs(p.y - span) < 1e-9 && p.x < 1);
    expect(outline.some((p) => Math.abs(p.x - span * Math.tan(sweep)) < 1e-9)).toBe(true);
    expect(tipLeadingEdge).toBeDefined();
  });

  it.each(['trapezoidal', 'delta', 'clipped_delta', 'rectangular', 'elliptical', 'swept', 'grid'] as const)(
    '%s encloses a positive area',
    (shape) => {
      const area = finArea(finOutline(shape, rootChord, tipChord, span, sweep));
      expect(area).toBeGreaterThan(0);
      // Never larger than the bounding rectangle it is drawn inside.
      expect(area).toBeLessThanOrEqual(rootChord * span * 1.001);
    },
  );

  it('an elliptical fin has less area than the rectangle it fits inside', () => {
    const elliptical = finArea(finOutline('elliptical', rootChord, tipChord, span, 0));
    const rectangular = finArea(finOutline('rectangular', rootChord, tipChord, span, 0));
    expect(elliptical).toBeLessThan(rectangular);
    expect(elliptical).toBeGreaterThan(rectangular * 0.5);
  });

  it('reduces an arbitrary planform to a trapezoid Barrowman can use', () => {
    const outline = finOutline('trapezoidal', rootChord, tipChord, span, sweep);
    const equivalent = equivalentTrapezoid(outline, span);
    expect(equivalent.rootChord_m).toBeCloseTo(rootChord, 6);
    expect(equivalent.tipChord_m).toBeCloseTo(tipChord, 6);
    expect(equivalent.sweepLength_m).toBeCloseTo(span * Math.tan(sweep), 6);
  });

  it('handles a degenerate fin without producing NaN', () => {
    const equivalent = equivalentTrapezoid([], 0);
    expect(equivalent.rootChord_m).toBe(0);
    expect(finArea([])).toBe(0);
    expect(finArea([{ x: 0, y: 0 }, { x: 1, y: 0 }])).toBe(0);
  });
});
