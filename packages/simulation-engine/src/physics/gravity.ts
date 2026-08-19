/**
 * Gravity model — spherical, inverse-square.
 *
 * Scalar form (altitude above a spherical Earth):
 *   g(h) = g₀ × (R / (R + h))²
 *
 * Vector form (central field, used by the trajectory integrator):
 *   a⃗ = −μ · r⃗ / |r⃗|³
 *
 * Assumptions:
 *   - Spherical, homogeneous Earth (no J2 oblateness, no mascons)
 *   - Non-rotating Earth (no Coriolis or centrifugal terms)
 *   - No lunar/solar third-body perturbations
 *   - Suitable for educational simulation, NOT ephemeris-grade orbit prediction
 *
 * Source: NIST CODATA 2018 for g₀; WGS-84 mean radius for R.
 * See constants.ts for why μ is derived as g₀·R² rather than taken from EGM96.
 *
 * @module physics/gravity
 */

import { G0, R_EARTH, MU_EARTH } from './constants.js';
import type { Vec3 } from './vec3.js';
import { vec3, magnitude, scale, VEC3_ZERO } from './vec3.js';

/**
 * Gravitational acceleration magnitude at a given altitude.
 *
 * @param altitude_m - Geometric altitude above sea level. Unit: m. Must be >= 0.
 * @returns Gravitational acceleration magnitude. Unit: m/s². Always positive.
 * @throws RangeError if altitude_m is negative. Callers inside the integrator
 *   must clamp first — a negative altitude there means the vehicle has hit the
 *   ground, which is an event to detect, not a value to extrapolate through.
 */
export function gravityAtAltitude(altitude_m: number): number {
  if (altitude_m < 0) {
    throw new RangeError(
      `altitude_m must be >= 0, got ${altitude_m}`
    );
  }
  const ratio = R_EARTH / (R_EARTH + altitude_m);
  return G0 * ratio * ratio;
}

/**
 * Gravitational force vector acting on a body at a given altitude, in a local
 * frame where +Z is "up" (away from Earth's centre).
 *
 * This is the flat-ground approximation. It is correct only while the vehicle
 * is close enough to the launch site that the local vertical has not rotated
 * appreciably. For trajectories that go downrange, use
 * {@link gravityAccelerationCentral}.
 *
 * @param mass_kg - Body mass. Unit: kg. Must be > 0.
 * @param altitude_m - Geometric altitude above sea level. Unit: m. Must be >= 0.
 * @returns Gravitational force vector (pointing downward). Unit: N.
 */
export function gravityForce(mass_kg: number, altitude_m: number): Vec3 {
  const g = gravityAtAltitude(altitude_m);
  return vec3(0, 0, -mass_kg * g);
}

/**
 * Weight of a body at a given altitude.
 *
 * @param mass_kg - Body mass. Unit: kg.
 * @param altitude_m - Geometric altitude above sea level. Unit: m.
 * @returns Weight magnitude. Unit: N.
 */
export function weight(mass_kg: number, altitude_m: number): number {
  return mass_kg * gravityAtAltitude(altitude_m);
}

/**
 * Gravitational acceleration vector in a central inverse-square field.
 *
 * a⃗ = −μ · r⃗ / |r⃗|³
 *
 * This is the form the trajectory integrator uses. It stays correct when the
 * vehicle travels far downrange or reaches orbit, where "down" is no longer the
 * launch site's −Z axis.
 *
 * @param positionFromCenter - Position measured from the centre of the
 *   attracting body. Unit: m.
 * @param mu_m3s2 - Standard gravitational parameter of the body. Unit: m³/s².
 *   Defaults to Earth.
 * @returns Acceleration vector pointing toward the body centre. Unit: m/s².
 *   Returns the zero vector at the exact centre (unphysical but non-singular).
 */
export function gravityAccelerationCentral(
  positionFromCenter: Vec3,
  mu_m3s2: number = MU_EARTH,
): Vec3 {
  const r = magnitude(positionFromCenter);
  if (r < 1e-6) return VEC3_ZERO;
  // −μ/r³ · r⃗
  return scale(positionFromCenter, -mu_m3s2 / (r * r * r));
}

/**
 * Circular orbital speed at a given radius from the body centre.
 *
 * v = √(μ / r)
 *
 * @param radius_m - Distance from the body centre. Unit: m. Must be > 0.
 * @param mu_m3s2 - Gravitational parameter. Unit: m³/s². Defaults to Earth.
 * @returns Circular orbital speed. Unit: m/s.
 */
export function circularOrbitSpeed(radius_m: number, mu_m3s2: number = MU_EARTH): number {
  if (radius_m <= 0) {
    throw new RangeError(`radius_m must be > 0, got ${radius_m}`);
  }
  return Math.sqrt(mu_m3s2 / radius_m);
}

/**
 * Escape speed at a given radius from the body centre.
 *
 * v_esc = √(2μ / r)
 *
 * @param radius_m - Distance from the body centre. Unit: m. Must be > 0.
 * @param mu_m3s2 - Gravitational parameter. Unit: m³/s². Defaults to Earth.
 * @returns Escape speed. Unit: m/s.
 */
export function escapeSpeed(radius_m: number, mu_m3s2: number = MU_EARTH): number {
  return Math.SQRT2 * circularOrbitSpeed(radius_m, mu_m3s2);
}
