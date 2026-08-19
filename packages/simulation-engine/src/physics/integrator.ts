/**
 * Numerical integrators for second-order translational dynamics.
 *
 * The state being advanced is (position, velocity); acceleration is supplied by
 * a caller-provided function. Nothing here knows about rockets — that keeps the
 * integrator unit-testable against analytic solutions (free fall, harmonic
 * oscillator, circular orbit) with no vehicle model in the way.
 *
 * ## Why mass is not part of the state
 *
 * Propellant flow is constant while an engine burns, so mass is *exactly*
 * linear in time: m(t) = m₀ − ṁ·(t − t₀). Folding it into the RK4 state vector
 * would add error rather than remove it. The acceleration function evaluates
 * mass analytically at each substep time instead. This is operator splitting,
 * and here the split is exact.
 *
 * @module physics/integrator
 */

import type { Vec3 } from './vec3.js';
import { add, scale } from './vec3.js';

/** Position and velocity at one instant. */
export interface KinematicState {
  readonly position: Vec3;
  readonly velocity: Vec3;
}

/**
 * Acceleration as a function of time and kinematic state.
 *
 * Must be pure: the integrator calls it four times per step at different
 * substep times, and a function with side effects will corrupt the result.
 *
 * @param t - Absolute time at which to evaluate. Unit: s.
 * @param position - Position at that substep. Unit: m.
 * @param velocity - Velocity at that substep. Unit: m/s.
 * @returns Acceleration. Unit: m/s².
 */
export type AccelerationFn = (t: number, position: Vec3, velocity: Vec3) => Vec3;

/** Available integration methods. */
export type IntegratorMethod = 'rk4' | 'euler' | 'velocity_verlet';

/**
 * Advance one step with classical fourth-order Runge-Kutta.
 *
 * Local truncation error is O(dt⁵), global error O(dt⁴). This is the engine's
 * default: at the standard 0.05 s powered-flight step it tracks an analytic
 * circular orbit to better than a metre per revolution, which is far below the
 * fidelity of the force models feeding it.
 *
 * @param state - Current position and velocity.
 * @param t - Current time. Unit: s.
 * @param dt - Timestep. Unit: s. Must be > 0.
 * @param accel - Acceleration function.
 * @returns The state at t + dt.
 */
export function rk4Step(
  state: KinematicState,
  t: number,
  dt: number,
  accel: AccelerationFn,
): KinematicState {
  const { position: p0, velocity: v0 } = state;
  const half = dt / 2;

  // k1
  const a1 = accel(t, p0, v0);

  // k2 — midpoint using k1
  const p2 = add(p0, scale(v0, half));
  const v2 = add(v0, scale(a1, half));
  const a2 = accel(t + half, p2, v2);

  // k3 — midpoint using k2
  const p3 = add(p0, scale(v2, half));
  const v3 = add(v0, scale(a2, half));
  const a3 = accel(t + half, p3, v3);

  // k4 — endpoint using k3
  const p4 = add(p0, scale(v3, dt));
  const v4 = add(v0, scale(a3, dt));
  const a4 = accel(t + dt, p4, v4);

  // Weighted average: (k1 + 2k2 + 2k3 + k4) / 6
  const dPosition = scale(
    add(add(v0, scale(add(v2, v3), 2)), v4),
    dt / 6,
  );
  const dVelocity = scale(
    add(add(a1, scale(add(a2, a3), 2)), a4),
    dt / 6,
  );

  return {
    position: add(p0, dPosition),
    velocity: add(v0, dVelocity),
  };
}

/**
 * Advance one step with explicit (forward) Euler.
 *
 * First-order and unconditionally energy-gaining for orbital motion, so it is
 * unsuitable for flight. It exists as a teaching contrast: running the same
 * mission under `euler` and `rk4` and watching the trajectories diverge is a
 * good demonstration of why integrator choice matters.
 *
 * @param state - Current position and velocity.
 * @param t - Current time. Unit: s.
 * @param dt - Timestep. Unit: s.
 * @param accel - Acceleration function.
 * @returns The state at t + dt.
 */
export function eulerStep(
  state: KinematicState,
  t: number,
  dt: number,
  accel: AccelerationFn,
): KinematicState {
  const a = accel(t, state.position, state.velocity);
  return {
    position: add(state.position, scale(state.velocity, dt)),
    velocity: add(state.velocity, scale(a, dt)),
  };
}

/**
 * Advance one step with velocity Verlet.
 *
 * Second-order and symplectic, so it conserves orbital energy over long coasts
 * far better than its order suggests. Costs two acceleration evaluations per
 * step against RK4's four, which makes it the better choice for long orbital
 * propagation where RK4's accuracy is wasted on a coarse force model.
 *
 * @param state - Current position and velocity.
 * @param t - Current time. Unit: s.
 * @param dt - Timestep. Unit: s.
 * @param accel - Acceleration function.
 * @returns The state at t + dt.
 */
export function velocityVerletStep(
  state: KinematicState,
  t: number,
  dt: number,
  accel: AccelerationFn,
): KinematicState {
  const a0 = accel(t, state.position, state.velocity);

  const position = add(
    add(state.position, scale(state.velocity, dt)),
    scale(a0, 0.5 * dt * dt),
  );

  // Velocity at t+dt needs a(t+dt), which needs v(t+dt). Use the drift estimate
  // to evaluate it — exact for velocity-independent forces, first-order
  // otherwise (drag).
  const vPredicted = add(state.velocity, scale(a0, dt));
  const a1 = accel(t + dt, position, vPredicted);

  return {
    position,
    velocity: add(state.velocity, scale(add(a0, a1), 0.5 * dt)),
  };
}

/**
 * Resolve an integrator method name to its step function.
 *
 * @param method - Integrator to use.
 * @returns The corresponding step function.
 */
export function getIntegrator(
  method: IntegratorMethod,
): (state: KinematicState, t: number, dt: number, accel: AccelerationFn) => KinematicState {
  switch (method) {
    case 'rk4':
      return rk4Step;
    case 'euler':
      return eulerStep;
    case 'velocity_verlet':
      return velocityVerletStep;
  }
}
