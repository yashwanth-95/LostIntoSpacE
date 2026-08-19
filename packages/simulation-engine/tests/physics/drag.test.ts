import { describe, it, expect } from 'vitest';
import { dragForce, dragForceMagnitude } from '../../src/physics/drag.js';
import { vec3, magnitude, VEC3_ZERO } from '../../src/physics/vec3.js';

describe('dragForce', () => {
  it('is zero when velocity is zero', () => {
    const f = dragForce(VEC3_ZERO, 1.225, 0.5, 0.07);
    expect(f).toEqual(VEC3_ZERO);
  });

  it('is zero when density is zero (vacuum)', () => {
    const f = dragForce(vec3(0, 0, 100), 0, 0.5, 0.07);
    expect(f).toEqual(VEC3_ZERO);
  });

  it('opposes velocity direction', () => {
    // Moving upward (+Z)
    const f = dragForce(vec3(0, 0, 300), 1.225, 0.5, 0.07);
    expect(f.z).toBeLessThan(0); // drag is downward
    expect(f.x).toBeCloseTo(0, 10);
    expect(f.y).toBeCloseTo(0, 10);
  });

  it('opposes velocity in arbitrary direction', () => {
    const vel = vec3(100, 200, 300);
    const f = dragForce(vel, 1.0, 0.5, 0.1);
    // Dot product of drag and velocity should be negative (opposing)
    const dotProduct = f.x * vel.x + f.y * vel.y + f.z * vel.z;
    expect(dotProduct).toBeLessThan(0);
  });

  it('magnitude matches analytical formula', () => {
    const vel = vec3(0, 0, 300);
    const rho = 1.225;
    const cd = 0.5;
    const area = 0.07;
    const f = dragForce(vel, rho, cd, area);
    const expectedMag = 0.5 * rho * 300 * 300 * cd * area;
    expect(magnitude(f)).toBeCloseTo(expectedMag, 4);
  });

  it('scales with velocity squared', () => {
    const rho = 1.0;
    const cd = 0.5;
    const area = 0.1;
    const f1 = magnitude(dragForce(vec3(0, 0, 100), rho, cd, area));
    const f2 = magnitude(dragForce(vec3(0, 0, 200), rho, cd, area));
    // f2 / f1 should be (200/100)² = 4
    expect(f2 / f1).toBeCloseTo(4, 4);
  });
});

describe('dragForceMagnitude', () => {
  it('matches vector version magnitude', () => {
    const speed = 250;
    const rho = 0.8;
    const cd = 0.45;
    const area = 0.05;
    const scalar = dragForceMagnitude(speed, rho, cd, area);
    const vector = magnitude(dragForce(vec3(0, 0, speed), rho, cd, area));
    expect(scalar).toBeCloseTo(vector, 6);
  });
});
