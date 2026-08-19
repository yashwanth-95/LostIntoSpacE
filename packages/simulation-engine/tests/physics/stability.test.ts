import { describe, it, expect } from 'vitest';
import {
  centerOfGravity,
  totalMass,
  noseConeCP,
  finSetBarrowman,
  analyzeStability,
  classifyStability,
  type MassElement,
  type NoseGeometry,
  type FinSetGeometry,
} from '../../src/physics/stability.js';

const mass = (id: string, mass_kg: number, station_m: number): MassElement => ({
  id,
  mass_kg,
  station_m,
});

const OGIVE_NOSE: NoseGeometry = {
  shape: 'ogive',
  length_m: 0.5,
  baseDiameter_m: 0.3,
};

/** A conventional 4-fin set near the tail of a 3 m vehicle. */
const TAIL_FINS: FinSetGeometry = {
  count: 4,
  rootChord_m: 0.3,
  tipChord_m: 0.15,
  span_m: 0.15,
  sweepLength_m: 0.1,
  stationLeadingEdge_m: 2.6,
  bodyRadius_m: 0.15,
};

describe('centerOfGravity', () => {
  it('returns 0 for an empty list', () => {
    expect(centerOfGravity([])).toBe(0);
  });

  it('returns the station of a single element', () => {
    expect(centerOfGravity([mass('a', 10, 5)])).toBeCloseTo(5, 10);
  });

  it('computes the mass-weighted mean station', () => {
    // (10·2 + 30·6) / 40 = 5
    expect(centerOfGravity([mass('a', 10, 2), mass('b', 30, 6)])).toBeCloseTo(5, 10);
  });

  it('returns 0 rather than NaN for massless elements', () => {
    expect(centerOfGravity([mass('a', 0, 2), mass('b', 0, 6)])).toBe(0);
  });

  it('is unaffected by the order of elements', () => {
    const a = [mass('a', 10, 2), mass('b', 30, 6), mass('c', 5, 1)];
    const b = [a[2]!, a[0]!, a[1]!];
    expect(centerOfGravity(a)).toBeCloseTo(centerOfGravity(b), 12);
  });
});

describe('totalMass', () => {
  it('sums element masses', () => {
    expect(totalMass([mass('a', 10, 2), mass('b', 30, 6)])).toBe(40);
  });

  it('returns 0 for an empty list', () => {
    expect(totalMass([])).toBe(0);
  });
});

describe('noseConeCP', () => {
  it('places a conical nose CP at 0.666 L', () => {
    expect(noseConeCP({ shape: 'conical', length_m: 1.0, baseDiameter_m: 0.3 }))
      .toBeCloseTo(0.666, 6);
  });

  it('places an ogive nose CP ahead of a conical one of the same length', () => {
    const cone = noseConeCP({ shape: 'conical', length_m: 1.0, baseDiameter_m: 0.3 });
    const ogive = noseConeCP({ shape: 'ogive', length_m: 1.0, baseDiameter_m: 0.3 });
    expect(ogive).toBeLessThan(cone);
    expect(ogive).toBeCloseTo(0.466, 6);
  });

  it('scales linearly with nose length', () => {
    const short = noseConeCP({ shape: 'haack', length_m: 0.5, baseDiameter_m: 0.3 });
    const long = noseConeCP({ shape: 'haack', length_m: 1.0, baseDiameter_m: 0.3 });
    expect(long).toBeCloseTo(2 * short, 10);
  });
});

describe('finSetBarrowman', () => {
  it('places the fin CP within the fin planform', () => {
    const { cp_m } = finSetBarrowman(TAIL_FINS, 0.3);
    expect(cp_m).toBeGreaterThan(TAIL_FINS.stationLeadingEdge_m);
    expect(cp_m).toBeLessThan(
      TAIL_FINS.stationLeadingEdge_m + TAIL_FINS.sweepLength_m + TAIL_FINS.rootChord_m,
    );
  });

  it('produces a positive normal force slope for a real fin set', () => {
    expect(finSetBarrowman(TAIL_FINS, 0.3).cnAlpha).toBeGreaterThan(0);
  });

  it('gives more lift with more fins', () => {
    const three = finSetBarrowman({ ...TAIL_FINS, count: 3 }, 0.3).cnAlpha;
    const four = finSetBarrowman({ ...TAIL_FINS, count: 4 }, 0.3).cnAlpha;
    expect(four).toBeGreaterThan(three);
  });

  it('gives more lift with a larger span', () => {
    const small = finSetBarrowman({ ...TAIL_FINS, span_m: 0.1 }, 0.3).cnAlpha;
    const large = finSetBarrowman({ ...TAIL_FINS, span_m: 0.25 }, 0.3).cnAlpha;
    expect(large).toBeGreaterThan(small);
  });

  it('contributes nothing for a degenerate fin set instead of returning NaN', () => {
    const { cnAlpha, cp_m } = finSetBarrowman({ ...TAIL_FINS, span_m: 0 }, 0.3);
    expect(cnAlpha).toBe(0);
    expect(Number.isFinite(cp_m)).toBe(true);
  });
});

describe('analyzeStability', () => {
  it('reports a finless vehicle as unstable', () => {
    // Nose CP sits at 0.233 m; the CG of any realistic vehicle is far aft of it.
    const elements = [mass('nose', 5, 0.25), mass('body', 20, 1.5), mass('engine', 30, 2.8)];
    const result = analyzeStability(elements, OGIVE_NOSE, []);

    expect(result.cp_m).toBeCloseTo(0.233, 3);
    expect(result.stabilityMargin_cal).toBeLessThan(0);
    expect(result.isStable).toBe(false);
    expect(result.classification).toBe('unstable');
  });

  it('reports a finned vehicle with a forward CG as stable', () => {
    // Heavy payload and nose forward, light tail — CG well ahead of the fin CP.
    const elements = [
      mass('payload', 80, 0.6),
      mass('nose', 10, 0.25),
      mass('body', 20, 1.5),
      mass('engine', 15, 2.8),
    ];
    const result = analyzeStability(elements, OGIVE_NOSE, [TAIL_FINS]);

    expect(result.cp_m).toBeGreaterThan(result.cg_m);
    expect(result.stabilityMargin_cal).toBeGreaterThan(1);
    expect(result.isStable).toBe(true);
    expect(result.classification).toMatch(/stable|overstable/);
  });

  it('moves the CP aft when fins are added', () => {
    const elements = [mass('body', 50, 1.5)];
    const finless = analyzeStability(elements, OGIVE_NOSE, []);
    const finned = analyzeStability(elements, OGIVE_NOSE, [TAIL_FINS]);

    expect(finned.cp_m).toBeGreaterThan(finless.cp_m);
    expect(finned.stabilityMargin_cal).toBeGreaterThan(finless.stabilityMargin_cal);
  });

  it('expresses the margin in calibers of the reference diameter', () => {
    const elements = [mass('body', 50, 1.0)];
    const result = analyzeStability(elements, OGIVE_NOSE, [TAIL_FINS]);
    expect(result.stabilityMargin_cal).toBeCloseTo(
      (result.cp_m - result.cg_m) / result.referenceDiameter_m,
      10,
    );
    expect(result.referenceDiameter_m).toBe(OGIVE_NOSE.baseDiameter_m);
  });

  it('never divides by a zero reference diameter', () => {
    const nose: NoseGeometry = { ...OGIVE_NOSE, baseDiameter_m: 0 };
    const result = analyzeStability([mass('body', 50, 1.0)], nose, []);
    expect(Number.isFinite(result.stabilityMargin_cal)).toBe(true);
    expect(result.referenceDiameter_m).toBe(1);
  });

  it('reports the total mass it used', () => {
    const elements = [mass('a', 10, 1), mass('b', 25, 2)];
    expect(analyzeStability(elements, OGIVE_NOSE, []).totalMass_kg).toBe(35);
  });
});

describe('classifyStability', () => {
  it('classifies each band', () => {
    expect(classifyStability(-0.5)).toBe('unstable');
    expect(classifyStability(0.2)).toBe('unstable');
    expect(classifyStability(0.7)).toBe('marginal');
    expect(classifyStability(1.5)).toBe('stable');
    expect(classifyStability(2.0)).toBe('stable');
    expect(classifyStability(3.0)).toBe('overstable');
  });
});
