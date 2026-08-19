/**
 * Aerodynamic drag model.
 *
 * F_drag = 0.5 × ρ × v² × Cd × A_ref
 * Direction: opposite to velocity vector.
 *
 * Assumptions:
 *   - Cd is a single number per stage, optionally scaled by a Mach factor
 *     ({@link machDragFactor}); there is no angle-of-attack dependence
 *   - No wind (velocity relative to ground = velocity relative to air)
 *   - No base drag, wave drag, or skin friction decomposition
 *   - No lift: the force is purely anti-parallel to velocity
 *   - Suitable for educational simulation
 *
 * @module physics/drag
 */

import type { Vec3 } from './vec3.js';
import { magnitude, scale, normalize, negate, VEC3_ZERO } from './vec3.js';

/**
 * Compute aerodynamic drag force vector.
 *
 * @param velocity - Vehicle velocity vector. Unit: m/s.
 * @param density_kgm3 - Air density at current altitude. Unit: kg/m³.
 * @param dragCoefficient - Aerodynamic drag coefficient (dimensionless). Must be >= 0.
 * @param referenceArea_m2 - Aerodynamic reference area. Unit: m². Must be > 0.
 * @returns Drag force vector (opposing velocity). Unit: N.
 */
export function dragForce(
  velocity: Vec3,
  density_kgm3: number,
  dragCoefficient: number,
  referenceArea_m2: number,
): Vec3 {
  const speed = magnitude(velocity);
  if (speed < 1e-10 || density_kgm3 <= 0) {
    return VEC3_ZERO;
  }

  // Drag magnitude: 0.5 * ρ * v² * Cd * A
  const dragMagnitude =
    0.5 * density_kgm3 * speed * speed * dragCoefficient * referenceArea_m2;

  // Direction: opposite to velocity
  const dragDirection = negate(normalize(velocity));

  return scale(dragDirection, dragMagnitude);
}

/**
 * Compute drag force magnitude (scalar).
 *
 * @param speed_ms - Speed magnitude. Unit: m/s.
 * @param density_kgm3 - Air density. Unit: kg/m³.
 * @param dragCoefficient - Cd (dimensionless).
 * @param referenceArea_m2 - Reference area. Unit: m².
 * @returns Drag force magnitude. Unit: N.
 */
export function dragForceMagnitude(
  speed_ms: number,
  density_kgm3: number,
  dragCoefficient: number,
  referenceArea_m2: number,
): number {
  return 0.5 * density_kgm3 * speed_ms * speed_ms * dragCoefficient * referenceArea_m2;
}

/**
 * Mach-dependent multiplier applied to the base (subsonic) drag coefficient.
 *
 * Real slender bodies show a sharp transonic drag rise: Cd roughly triples
 * between M 0.8 and M 1.2, then falls away again as the shock system stabilises.
 * Ignoring this makes the simulation understate max-Q and mislead students about
 * why vehicles throttle down through the transonic region.
 *
 * This is a **shape-agnostic educational curve**, not wind-tunnel data. It is
 * piecewise-linear in four regions:
 *
 * | Mach range | Behaviour                                  |
 * |------------|--------------------------------------------|
 * | 0 – 0.8    | 1.0 (incompressible)                       |
 * | 0.8 – 1.2  | rises linearly to the transonic peak (2.5×) |
 * | 1.2 – 5.0  | decays linearly toward the hypersonic floor |
 * | > 5.0      | 1.1 (hypersonic floor)                     |
 *
 * @param mach - Mach number (dimensionless). Negative values are treated as 0.
 * @returns Multiplier for the base drag coefficient. Dimensionless, >= 1.
 */
export function machDragFactor(mach: number): number {
  const m = Math.max(0, mach);

  const TRANSONIC_PEAK = 2.5;
  const HYPERSONIC_FLOOR = 1.1;

  if (m < 0.8) return 1.0;
  if (m < 1.2) {
    // Linear rise 1.0 → 2.5 across the transonic band
    return 1.0 + ((TRANSONIC_PEAK - 1.0) * (m - 0.8)) / 0.4;
  }
  if (m < 5.0) {
    // Linear decay 2.5 → 1.1 through the supersonic range
    return TRANSONIC_PEAK - ((TRANSONIC_PEAK - HYPERSONIC_FLOOR) * (m - 1.2)) / 3.8;
  }
  return HYPERSONIC_FLOOR;
}

/**
 * Effective drag coefficient at a given Mach number.
 *
 * @param baseDragCoefficient - Subsonic Cd of the vehicle. Dimensionless.
 * @param mach - Mach number. Dimensionless.
 * @returns Cd corrected for compressibility. Dimensionless.
 */
export function effectiveDragCoefficient(
  baseDragCoefficient: number,
  mach: number,
): number {
  return baseDragCoefficient * machDragFactor(mach);
}
