import { describe, it, expect } from 'vitest';
import {
  orbitalElements,
  classifyOrbit,
  sampleOrbitPath,
} from '../../src/physics/orbital.js';
import { vec3, magnitude } from '../../src/physics/vec3.js';
import { MU_EARTH, R_EARTH, DEG_TO_RAD } from '../../src/physics/constants.js';

/** State vector of a circular equatorial orbit at the given altitude. */
function circularState(altitude_m: number) {
  const r = R_EARTH + altitude_m;
  return {
    position: vec3(r, 0, 0),
    velocity: vec3(0, Math.sqrt(MU_EARTH / r), 0),
  };
}

describe('orbitalElements — circular orbit', () => {
  const { position, velocity } = circularState(400_000);
  const el = orbitalElements(position, velocity);

  it('has near-zero eccentricity', () => {
    expect(el.eccentricity).toBeLessThan(1e-9);
    expect(el.shape).toBe('circular');
  });

  it('has a semi-major axis equal to the orbital radius', () => {
    expect(el.semiMajorAxis_m).toBeCloseTo(R_EARTH + 400_000, 3);
  });

  it('has equal apsides at the orbital altitude', () => {
    expect(el.periapsisAltitude_m).toBeCloseTo(400_000, 3);
    expect(el.apoapsisAltitude_m).toBeCloseTo(400_000, 3);
  });

  it('has a period close to the well-known 92-minute LEO value', () => {
    expect(el.period_s / 60).toBeGreaterThan(90);
    expect(el.period_s / 60).toBeLessThan(94);
  });

  it('is flagged as a stable orbit', () => {
    expect(el.isStableOrbit).toBe(true);
  });

  it('is equatorial in this frame', () => {
    expect(el.inclination_rad).toBeCloseTo(0, 9);
  });
});

describe('orbitalElements — elliptical orbit', () => {
  it('recovers apsides from a known transfer orbit', () => {
    // Periapsis burn at 200 km for an apoapsis at 35 786 km (GTO-like).
    const rp = R_EARTH + 200_000;
    const ra = R_EARTH + 35_786_000;
    const a = (rp + ra) / 2;
    // Vis-viva at periapsis: v = √(μ(2/r − 1/a))
    const vp = Math.sqrt(MU_EARTH * (2 / rp - 1 / a));

    const el = orbitalElements(vec3(rp, 0, 0), vec3(0, vp, 0));

    expect(el.periapsisRadius_m).toBeCloseTo(rp, 0);
    expect(el.apoapsisRadius_m).toBeCloseTo(ra, 0);
    expect(el.semiMajorAxis_m).toBeCloseTo(a, 0);
    expect(el.shape).toBe('elliptical');
    expect(el.eccentricity).toBeGreaterThan(0);
    expect(el.eccentricity).toBeLessThan(1);
  });

  it('reports true anomaly 0 at periapsis', () => {
    const rp = R_EARTH + 200_000;
    const a = rp * 2;
    const vp = Math.sqrt(MU_EARTH * (2 / rp - 1 / a));
    const el = orbitalElements(vec3(rp, 0, 0), vec3(0, vp, 0));
    expect(el.trueAnomaly_rad).toBeCloseTo(0, 6);
  });

  it('reports true anomaly π at apoapsis', () => {
    const rp = R_EARTH + 200_000;
    const a = rp * 2;
    const ra = 2 * a - rp;
    const va = Math.sqrt(MU_EARTH * (2 / ra - 1 / a));
    // At apoapsis the position is opposite the periapsis direction.
    const el = orbitalElements(vec3(-ra, 0, 0), vec3(0, -va, 0));
    expect(el.trueAnomaly_rad).toBeCloseTo(Math.PI, 5);
  });
});

describe('orbitalElements — suborbital trajectory', () => {
  it('is a closed ellipse whose periapsis is underground', () => {
    // 100 km altitude, moving horizontally far too slowly to stay up.
    const r = R_EARTH + 100_000;
    const el = orbitalElements(vec3(r, 0, 0), vec3(0, 2000, 0));

    expect(el.shape).toBe('elliptical');
    expect(el.periapsisAltitude_m).toBeLessThan(0);
    expect(el.isStableOrbit).toBe(false);
  });
});

describe('orbitalElements — escape trajectory', () => {
  it('classifies a hyperbolic state and reports infinite apoapsis', () => {
    const r = R_EARTH + 400_000;
    const vEscape = Math.sqrt((2 * MU_EARTH) / r);
    const el = orbitalElements(vec3(r, 0, 0), vec3(0, vEscape * 1.2, 0));

    expect(el.eccentricity).toBeGreaterThan(1);
    expect(el.shape).toBe('hyperbolic');
    expect(el.apoapsisRadius_m).toBe(Infinity);
    expect(el.period_s).toBe(Infinity);
    expect(el.isStableOrbit).toBe(false);
    expect(el.specificEnergy_Jkg).toBeGreaterThan(0);
  });
});

describe('orbitalElements — inclination and node', () => {
  it('recovers a 51.6° inclination', () => {
    const r = R_EARTH + 400_000;
    const v = Math.sqrt(MU_EARTH / r);
    const inc = 51.6 * DEG_TO_RAD;
    const el = orbitalElements(
      vec3(r, 0, 0),
      vec3(0, v * Math.cos(inc), v * Math.sin(inc)),
    );
    expect(el.inclination_rad).toBeCloseTo(inc, 9);
  });

  it('recovers a polar orbit', () => {
    const r = R_EARTH + 400_000;
    const v = Math.sqrt(MU_EARTH / r);
    const el = orbitalElements(vec3(r, 0, 0), vec3(0, 0, v));
    expect(el.inclination_rad).toBeCloseTo(Math.PI / 2, 9);
  });

  it('recovers a retrograde orbit', () => {
    const r = R_EARTH + 400_000;
    const v = Math.sqrt(MU_EARTH / r);
    const el = orbitalElements(vec3(r, 0, 0), vec3(0, -v, 0));
    expect(el.inclination_rad).toBeCloseTo(Math.PI, 9);
  });
});

describe('orbitalElements — degenerate inputs', () => {
  it('throws on a zero position vector', () => {
    expect(() => orbitalElements(vec3(0, 0, 0), vec3(1, 0, 0))).toThrow(RangeError);
  });

  it('returns finite angles for a circular equatorial orbit', () => {
    const { position, velocity } = circularState(400_000);
    const el = orbitalElements(position, velocity);
    expect(Number.isFinite(el.raan_rad)).toBe(true);
    expect(Number.isFinite(el.argumentOfPeriapsis_rad)).toBe(true);
    expect(Number.isFinite(el.trueAnomaly_rad)).toBe(true);
  });
});

describe('classifyOrbit', () => {
  it('maps eccentricity to a conic section', () => {
    expect(classifyOrbit(0)).toBe('circular');
    expect(classifyOrbit(0.5)).toBe('elliptical');
    expect(classifyOrbit(1)).toBe('parabolic');
    expect(classifyOrbit(2)).toBe('hyperbolic');
  });
});

describe('sampleOrbitPath', () => {
  it('traces a circle of the right radius', () => {
    const { position, velocity } = circularState(400_000);
    const points = sampleOrbitPath(orbitalElements(position, velocity), 64);

    expect(points).toHaveLength(65);
    for (const p of points) {
      expect(magnitude(p)).toBeCloseTo(R_EARTH + 400_000, 0);
    }
  });

  it('closes the loop', () => {
    const { position, velocity } = circularState(400_000);
    const points = sampleOrbitPath(orbitalElements(position, velocity), 32);
    const first = points[0]!;
    const last = points[points.length - 1]!;
    expect(last.x).toBeCloseTo(first.x, 3);
    expect(last.y).toBeCloseTo(first.y, 3);
    expect(last.z).toBeCloseTo(first.z, 3);
  });

  it('spans periapsis to apoapsis for an ellipse', () => {
    const rp = R_EARTH + 200_000;
    const a = rp * 1.5;
    const vp = Math.sqrt(MU_EARTH * (2 / rp - 1 / a));
    const el = orbitalElements(vec3(rp, 0, 0), vec3(0, vp, 0));
    const points = sampleOrbitPath(el, 180);

    const radii = points.map(magnitude);
    expect(Math.min(...radii)).toBeCloseTo(el.periapsisRadius_m, 0);
    expect(Math.max(...radii)).toBeCloseTo(el.apoapsisRadius_m, 0);
  });

  it('returns nothing for an open orbit', () => {
    const r = R_EARTH + 400_000;
    const vEscape = Math.sqrt((2 * MU_EARTH) / r);
    const el = orbitalElements(vec3(r, 0, 0), vec3(0, vEscape * 1.2, 0));
    expect(sampleOrbitPath(el)).toEqual([]);
  });
});
