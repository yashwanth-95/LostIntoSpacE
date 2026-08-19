import { describe, it, expect } from 'vitest';
import { gravityAtAltitude, gravityForce, weight } from '../../src/physics/gravity.js';
import { G0, R_EARTH } from '../../src/physics/constants.js';

describe('gravityAtAltitude', () => {
  it('returns standard gravity at sea level', () => {
    expect(gravityAtAltitude(0)).toBeCloseTo(G0, 6);
  });

  it('decreases with altitude', () => {
    const g0 = gravityAtAltitude(0);
    const g10k = gravityAtAltitude(10_000);
    const g100k = gravityAtAltitude(100_000);
    expect(g10k).toBeLessThan(g0);
    expect(g100k).toBeLessThan(g10k);
  });

  it('matches known value at ISS altitude (~400 km)', () => {
    // At 400 km, g ≈ 8.69 m/s² (well-known reference value)
    const g400 = gravityAtAltitude(400_000);
    expect(g400).toBeCloseTo(8.69, 1);
  });

  it('matches known value at 10 km', () => {
    // At 10 km, g ≈ 9.776 m/s²
    const g10 = gravityAtAltitude(10_000);
    expect(g10).toBeCloseTo(9.776, 2);
  });

  it('matches analytical formula exactly', () => {
    const h = 50_000; // 50 km
    const expected = G0 * Math.pow(R_EARTH / (R_EARTH + h), 2);
    expect(gravityAtAltitude(h)).toBeCloseTo(expected, 10);
  });

  it('throws on negative altitude', () => {
    expect(() => gravityAtAltitude(-1)).toThrow(RangeError);
  });
});

describe('gravityForce', () => {
  it('points in -Z direction (downward in ENU)', () => {
    const f = gravityForce(100, 0);
    expect(f.x).toBe(0);
    expect(f.y).toBe(0);
    expect(f.z).toBeLessThan(0);
  });

  it('magnitude equals mass × g at sea level', () => {
    const mass = 250; // kg
    const f = gravityForce(mass, 0);
    expect(Math.abs(f.z)).toBeCloseTo(mass * G0, 4);
  });

  it('force decreases with altitude', () => {
    const mass = 100;
    const f0 = Math.abs(gravityForce(mass, 0).z);
    const f100k = Math.abs(gravityForce(mass, 100_000).z);
    expect(f100k).toBeLessThan(f0);
  });
});

describe('weight', () => {
  it('equals mass × g at sea level', () => {
    expect(weight(1, 0)).toBeCloseTo(G0, 6);
  });

  it('equals mass × g at altitude', () => {
    const mass = 500;
    const alt = 20_000;
    expect(weight(mass, alt)).toBeCloseTo(mass * gravityAtAltitude(alt), 6);
  });
});
