import { describe, it, expect } from 'vitest';
import {
  massFlowRate, thrustFromIsp, thrustForce,
  exhaustVelocity, deltaV, thrustToWeightRatio,
} from '../../src/physics/thrust.js';
import { G0 } from '../../src/physics/constants.js';
import { VEC3_ZERO } from '../../src/physics/vec3.js';

describe('massFlowRate', () => {
  it('computes propellant / burn time', () => {
    expect(massFlowRate(200, 40)).toBeCloseTo(5, 10);
  });

  it('throws on zero burn time', () => {
    expect(() => massFlowRate(200, 0)).toThrow(RangeError);
  });
});

describe('thrustFromIsp', () => {
  it('computes F = Isp × g₀ × ṁ', () => {
    expect(thrustFromIsp(250, 5)).toBeCloseTo(250 * G0 * 5, 6);
  });
});

describe('thrustForce', () => {
  it('returns zero when inactive', () => {
    expect(thrustForce(250, 200, 40, false)).toEqual(VEC3_ZERO);
  });

  it('points in +Z (upward in ENU)', () => {
    const f = thrustForce(250, 200, 40, true);
    expect(f.z).toBeGreaterThan(0);
    expect(f.x).toBe(0);
    expect(f.y).toBe(0);
  });

  it('magnitude equals Isp × g₀ × ṁ', () => {
    const expected = 250 * G0 * (200 / 40);
    expect(thrustForce(250, 200, 40, true).z).toBeCloseTo(expected, 4);
  });
});

describe('exhaustVelocity', () => {
  it('returns Isp × g₀', () => {
    expect(exhaustVelocity(300)).toBeCloseTo(300 * G0, 6);
  });
});

describe('deltaV', () => {
  it('computes Tsiolkovsky equation', () => {
    const expected = 300 * G0 * Math.log(1000 / 400);
    expect(deltaV(300, 1000, 400)).toBeCloseTo(expected, 6);
  });

  it('returns 0 when initial <= final', () => {
    expect(deltaV(300, 400, 400)).toBe(0);
  });

  it('throws when final mass is zero', () => {
    expect(() => deltaV(300, 1000, 0)).toThrow(RangeError);
  });
});

describe('thrustToWeightRatio', () => {
  it('> 1 for liftoff-capable vehicle', () => {
    const twr = thrustToWeightRatio(5000, 250, 0);
    expect(twr).toBeCloseTo(5000 / (250 * G0), 4);
    expect(twr).toBeGreaterThan(1);
  });

  it('< 1 for too-heavy vehicle', () => {
    expect(thrustToWeightRatio(1000, 250, 0)).toBeLessThan(1);
  });

  it('returns 0 for zero mass', () => {
    expect(thrustToWeightRatio(5000, 0, 0)).toBe(0);
  });
});
