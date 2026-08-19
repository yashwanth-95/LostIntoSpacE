/**
 * Immutable 3D vector type and pure-function operations.
 *
 * All operations return new objects — no mutation.
 * This is a plain data type, not a class, so it serializes cleanly to JSON
 * and can cross Web Worker boundaries without special handling.
 *
 * @module physics/vec3
 */

/** A 3D vector. All fields in SI units (meters, m/s, m/s², N, etc.) */
export interface Vec3 {
  readonly x: number;
  readonly y: number;
  readonly z: number;
}

/** Create a Vec3. Defaults to origin. */
export function vec3(x = 0, y = 0, z = 0): Vec3 {
  return { x, y, z };
}

/** The zero vector. */
export const VEC3_ZERO: Vec3 = vec3(0, 0, 0);

/** Vector addition: a + b */
export function add(a: Vec3, b: Vec3): Vec3 {
  return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z };
}

/** Vector subtraction: a - b */
export function sub(a: Vec3, b: Vec3): Vec3 {
  return { x: a.x - b.x, y: a.y - b.y, z: a.z - b.z };
}

/** Scalar multiplication: s * v */
export function scale(v: Vec3, s: number): Vec3 {
  return { x: v.x * s, y: v.y * s, z: v.z * s };
}

/** Dot product: a · b */
export function dot(a: Vec3, b: Vec3): number {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

/** Cross product: a × b */
export function cross(a: Vec3, b: Vec3): Vec3 {
  return {
    x: a.y * b.z - a.z * b.y,
    y: a.z * b.x - a.x * b.z,
    z: a.x * b.y - a.y * b.x,
  };
}

/** Squared magnitude: |v|² (avoids sqrt when only comparison is needed) */
export function magnitudeSq(v: Vec3): number {
  return v.x * v.x + v.y * v.y + v.z * v.z;
}

/** Magnitude: |v| */
export function magnitude(v: Vec3): number {
  return Math.sqrt(magnitudeSq(v));
}

/** Unit vector in the direction of v. Returns VEC3_ZERO if v is zero-length. */
export function normalize(v: Vec3): Vec3 {
  const mag = magnitude(v);
  if (mag === 0) return VEC3_ZERO;
  return scale(v, 1 / mag);
}

/** Negate: -v */
export function negate(v: Vec3): Vec3 {
  return { x: -v.x, y: -v.y, z: -v.z };
}

/** Linear interpolation between a and b: a + t*(b-a) */
export function lerp(a: Vec3, b: Vec3, t: number): Vec3 {
  return {
    x: a.x + t * (b.x - a.x),
    y: a.y + t * (b.y - a.y),
    z: a.z + t * (b.z - a.z),
  };
}

/** Distance between two points */
export function distance(a: Vec3, b: Vec3): number {
  return magnitude(sub(b, a));
}
