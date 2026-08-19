import { describe, it, expect } from 'vitest';
import { vec3, add, sub, scale, dot, cross, magnitude, magnitudeSq, normalize, negate, lerp, distance, VEC3_ZERO } from '../../src/physics/vec3.js';

describe('vec3', () => {
  it('creates a vector with given components', () => {
    const v = vec3(1, 2, 3);
    expect(v).toEqual({ x: 1, y: 2, z: 3 });
  });

  it('defaults to origin', () => {
    expect(vec3()).toEqual({ x: 0, y: 0, z: 0 });
  });
});

describe('add', () => {
  it('adds two vectors', () => {
    expect(add(vec3(1, 2, 3), vec3(4, 5, 6))).toEqual({ x: 5, y: 7, z: 9 });
  });

  it('identity with zero vector', () => {
    const v = vec3(3, 4, 5);
    expect(add(v, VEC3_ZERO)).toEqual(v);
  });
});

describe('sub', () => {
  it('subtracts two vectors', () => {
    expect(sub(vec3(5, 7, 9), vec3(1, 2, 3))).toEqual({ x: 4, y: 5, z: 6 });
  });
});

describe('scale', () => {
  it('scales a vector', () => {
    expect(scale(vec3(1, 2, 3), 2)).toEqual({ x: 2, y: 4, z: 6 });
  });

  it('scales by zero', () => {
    expect(scale(vec3(1, 2, 3), 0)).toEqual(VEC3_ZERO);
  });
});

describe('dot', () => {
  it('computes dot product', () => {
    expect(dot(vec3(1, 2, 3), vec3(4, 5, 6))).toBe(32);
  });

  it('perpendicular vectors have zero dot product', () => {
    expect(dot(vec3(1, 0, 0), vec3(0, 1, 0))).toBe(0);
  });
});

describe('cross', () => {
  it('x × y = z', () => {
    expect(cross(vec3(1, 0, 0), vec3(0, 1, 0))).toEqual(vec3(0, 0, 1));
  });

  it('y × x = -z', () => {
    expect(cross(vec3(0, 1, 0), vec3(1, 0, 0))).toEqual(vec3(0, 0, -1));
  });
});

describe('magnitude', () => {
  it('computes length of unit vectors', () => {
    expect(magnitude(vec3(1, 0, 0))).toBe(1);
  });

  it('computes 3-4-5 triangle hypotenuse', () => {
    expect(magnitude(vec3(3, 4, 0))).toBe(5);
  });

  it('zero vector has zero magnitude', () => {
    expect(magnitude(VEC3_ZERO)).toBe(0);
  });
});

describe('magnitudeSq', () => {
  it('returns squared magnitude', () => {
    expect(magnitudeSq(vec3(3, 4, 0))).toBe(25);
  });
});

describe('normalize', () => {
  it('produces unit vector', () => {
    const n = normalize(vec3(3, 4, 0));
    expect(magnitude(n)).toBeCloseTo(1, 10);
  });

  it('preserves direction', () => {
    const n = normalize(vec3(0, 0, 5));
    expect(n).toEqual(vec3(0, 0, 1));
  });

  it('returns zero for zero vector', () => {
    expect(normalize(VEC3_ZERO)).toEqual(VEC3_ZERO);
  });
});

describe('negate', () => {
  it('negates all components', () => {
    expect(negate(vec3(1, -2, 3))).toEqual(vec3(-1, 2, -3));
  });
});

describe('lerp', () => {
  it('returns a at t=0', () => {
    expect(lerp(vec3(1, 2, 3), vec3(4, 5, 6), 0)).toEqual(vec3(1, 2, 3));
  });

  it('returns b at t=1', () => {
    expect(lerp(vec3(1, 2, 3), vec3(4, 5, 6), 1)).toEqual(vec3(4, 5, 6));
  });

  it('returns midpoint at t=0.5', () => {
    expect(lerp(vec3(0, 0, 0), vec3(10, 10, 10), 0.5)).toEqual(vec3(5, 5, 5));
  });
});

describe('distance', () => {
  it('returns 0 for same point', () => {
    const v = vec3(1, 2, 3);
    expect(distance(v, v)).toBe(0);
  });

  it('computes correct distance', () => {
    expect(distance(vec3(0, 0, 0), vec3(3, 4, 0))).toBe(5);
  });
});
