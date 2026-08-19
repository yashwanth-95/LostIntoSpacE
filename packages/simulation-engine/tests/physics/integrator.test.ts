import { describe, it, expect } from 'vitest';
import {
  rk4Step,
  eulerStep,
  velocityVerletStep,
  getIntegrator,
  type KinematicState,
  type AccelerationFn,
} from '../../src/physics/integrator.js';
import { vec3, magnitude, sub } from '../../src/physics/vec3.js';
import { MU_EARTH, R_EARTH } from '../../src/physics/constants.js';

/** Constant downward acceleration — free fall. */
const freeFall: AccelerationFn = () => vec3(0, 0, -9.80665);

/** Central inverse-square gravity, for orbit tests. */
const centralGravity: AccelerationFn = (_t, p) => {
  const r = magnitude(p);
  const k = -MU_EARTH / (r * r * r);
  return vec3(p.x * k, p.y * k, p.z * k);
};

/** 1-D harmonic oscillator with ω = 1: a = −x. */
const harmonic: AccelerationFn = (_t, p) => vec3(-p.x, 0, 0);

describe('rk4Step — analytic free fall', () => {
  it('reproduces z = z₀ + v₀t − ½gt² exactly', () => {
    // Constant acceleration is a cubic in the state, so RK4 is exact for it.
    let state: KinematicState = { position: vec3(0, 0, 100), velocity: vec3(0, 0, 50) };
    const dt = 0.1;
    const steps = 100;

    for (let i = 0; i < steps; i++) {
      state = rk4Step(state, i * dt, dt, freeFall);
    }

    const t = steps * dt;
    const expectedZ = 100 + 50 * t - 0.5 * 9.80665 * t * t;
    const expectedVz = 50 - 9.80665 * t;

    expect(state.position.z).toBeCloseTo(expectedZ, 8);
    expect(state.velocity.z).toBeCloseTo(expectedVz, 8);
  });

  it('leaves the horizontal components untouched under vertical acceleration', () => {
    const state = rk4Step(
      { position: vec3(10, 20, 0), velocity: vec3(3, 4, 0) },
      0,
      1,
      freeFall,
    );
    expect(state.position.x).toBeCloseTo(13, 10);
    expect(state.position.y).toBeCloseTo(24, 10);
    expect(state.velocity.x).toBe(3);
    expect(state.velocity.y).toBe(4);
  });
});

describe('rk4Step — harmonic oscillator', () => {
  it('tracks x = cos(t) over a full period', () => {
    let state: KinematicState = { position: vec3(1, 0, 0), velocity: vec3(0, 0, 0) };
    // Divide the period exactly, so the final step lands on t = 2π and the
    // residual is integrator error rather than a truncated step count.
    const steps = 628;
    const dt = (2 * Math.PI) / steps;

    for (let i = 0; i < steps; i++) {
      state = rk4Step(state, i * dt, dt, harmonic);
    }

    // After one period the oscillator must return to its start.
    expect(state.position.x).toBeCloseTo(1, 8);
    expect(state.velocity.x).toBeCloseTo(0, 8);
  });
});

describe('rk4Step — circular orbit', () => {
  const radius = R_EARTH + 400_000;
  const speed = Math.sqrt(MU_EARTH / radius);
  const period = 2 * Math.PI * Math.sqrt(radius ** 3 / MU_EARTH);

  it('closes a full revolution to within a metre', () => {
    const start: KinematicState = {
      position: vec3(radius, 0, 0),
      velocity: vec3(0, speed, 0),
    };
    let state = start;
    // Divide the period exactly so the last step lands on the starting point.
    const steps = 5554;
    const dt = period / steps;

    for (let i = 0; i < steps; i++) {
      state = rk4Step(state, i * dt, dt, centralGravity);
    }

    // Position error after a full 92-minute revolution at a ~1 s step.
    expect(magnitude(sub(state.position, start.position))).toBeLessThan(1.0);
  });

  it('conserves orbital radius', () => {
    let state: KinematicState = {
      position: vec3(radius, 0, 0),
      velocity: vec3(0, speed, 0),
    };
    const dt = 1.0;

    for (let i = 0; i < 2000; i++) {
      state = rk4Step(state, i * dt, dt, centralGravity);
      expect(magnitude(state.position)).toBeCloseTo(radius, 0);
    }
  });
});

describe('eulerStep', () => {
  it('advances by the simple first-order formula', () => {
    const state = eulerStep(
      { position: vec3(0, 0, 0), velocity: vec3(1, 0, 0) },
      0,
      2,
      freeFall,
    );
    expect(state.position.x).toBe(2);
    expect(state.velocity.z).toBeCloseTo(-2 * 9.80665, 10);
  });

  it('gains orbital energy where RK4 does not — the teaching contrast', () => {
    const radius = R_EARTH + 400_000;
    const speed = Math.sqrt(MU_EARTH / radius);
    const start: KinematicState = {
      position: vec3(radius, 0, 0),
      velocity: vec3(0, speed, 0),
    };

    let euler = start;
    let rk4 = start;
    const dt = 10;
    for (let i = 0; i < 500; i++) {
      euler = eulerStep(euler, i * dt, dt, centralGravity);
      rk4 = rk4Step(rk4, i * dt, dt, centralGravity);
    }

    const eulerDrift = Math.abs(magnitude(euler.position) - radius);
    const rk4Drift = Math.abs(magnitude(rk4.position) - radius);
    expect(eulerDrift).toBeGreaterThan(rk4Drift * 100);
  });
});

describe('velocityVerletStep', () => {
  it('is exact for constant acceleration', () => {
    const state = velocityVerletStep(
      { position: vec3(0, 0, 100), velocity: vec3(0, 0, 0) },
      0,
      1,
      freeFall,
    );
    expect(state.position.z).toBeCloseTo(100 - 0.5 * 9.80665, 10);
    expect(state.velocity.z).toBeCloseTo(-9.80665, 10);
  });

  it('holds orbital radius better than Euler at the same step size', () => {
    const radius = R_EARTH + 400_000;
    const speed = Math.sqrt(MU_EARTH / radius);
    const start: KinematicState = {
      position: vec3(radius, 0, 0),
      velocity: vec3(0, speed, 0),
    };

    let verlet = start;
    let euler = start;
    const dt = 10;
    for (let i = 0; i < 500; i++) {
      verlet = velocityVerletStep(verlet, i * dt, dt, centralGravity);
      euler = eulerStep(euler, i * dt, dt, centralGravity);
    }

    expect(Math.abs(magnitude(verlet.position) - radius)).toBeLessThan(
      Math.abs(magnitude(euler.position) - radius),
    );
  });
});

describe('getIntegrator', () => {
  it('resolves every method name', () => {
    expect(getIntegrator('rk4')).toBe(rk4Step);
    expect(getIntegrator('euler')).toBe(eulerStep);
    expect(getIntegrator('velocity_verlet')).toBe(velocityVerletStep);
  });
});

describe('integrator determinism', () => {
  it('produces identical results for identical inputs', () => {
    const run = () => {
      let state: KinematicState = { position: vec3(1, 2, 3), velocity: vec3(4, 5, 6) };
      for (let i = 0; i < 200; i++) {
        state = rk4Step(state, i * 0.05, 0.05, centralGravity);
      }
      return state;
    };
    expect(run()).toEqual(run());
  });
});
