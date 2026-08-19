/**
 * Thrust and mass-flow model.
 *
 * F_thrust = Isp × g₀ × ṁ
 * ṁ = m_propellant / t_burn
 *
 * Assumptions:
 *   - Constant mass flow rate while burning — no throttling in v1
 *   - Instantaneous ignition and cutoff (no start/shutdown transient)
 *   - Thrust acts along the commanded attitude vector; the nozzle is treated as
 *     perfectly aligned (gimbal deflection is not modelled in 3-DOF)
 *   - Altitude compensation is the ideal-nozzle relation F(p) = F_vac − p·Aₑ,
 *     which ignores flow separation in over-expanded nozzles near sea level
 *
 * @module physics/thrust
 */

import { G0, P0_SEA_LEVEL } from './constants.js';
import { gravityAtAltitude } from './gravity.js';
import type { Vec3 } from './vec3.js';
import { vec3, scale, VEC3_ZERO } from './vec3.js';

/**
 * Compute mass flow rate for a stage.
 *
 * @param propellantMass_kg - Total propellant mass in the stage. Unit: kg.
 * @param burnTime_s - Total burn time. Unit: s. Must be > 0.
 * @returns Mass flow rate. Unit: kg/s.
 */
export function massFlowRate(propellantMass_kg: number, burnTime_s: number): number {
  if (burnTime_s <= 0) {
    throw new RangeError(`burnTime_s must be > 0, got ${burnTime_s}`);
  }
  return propellantMass_kg / burnTime_s;
}

/**
 * Compute thrust from specific impulse and mass flow rate.
 *
 * F = Isp × g₀ × ṁ
 *
 * @param isp_s - Specific impulse. Unit: s.
 * @param mdot_kgs - Mass flow rate. Unit: kg/s.
 * @returns Thrust magnitude. Unit: N.
 */
export function thrustFromIsp(isp_s: number, mdot_kgs: number): number {
  return isp_s * G0 * mdot_kgs;
}

/**
 * Compute thrust force vector for a stage, along +Z (local vertical).
 *
 * Kept for the simple vertical-launch case and for tests. Flight code should
 * use {@link thrustVector}, which takes an explicit direction from the
 * guidance model.
 *
 * @param isp_s - Specific impulse. Unit: s.
 * @param propellantMass_kg - Total propellant mass. Unit: kg.
 * @param burnTime_s - Total burn time. Unit: s.
 * @param isActive - Whether the stage is currently burning.
 * @returns Thrust force vector. Unit: N.
 */
export function thrustForce(
  isp_s: number,
  propellantMass_kg: number,
  burnTime_s: number,
  isActive: boolean,
): Vec3 {
  if (!isActive) return VEC3_ZERO;

  const mdot = massFlowRate(propellantMass_kg, burnTime_s);
  const F = thrustFromIsp(isp_s, mdot);

  return vec3(0, 0, F);
}

/**
 * Compute a thrust force vector along an arbitrary direction.
 *
 * @param thrustMagnitude_N - Thrust magnitude. Unit: N.
 * @param direction - Unit vector along which thrust acts. Must be normalised;
 *   the caller owns normalisation so this stays allocation-free on the hot path.
 * @returns Thrust force vector. Unit: N.
 */
export function thrustVector(thrustMagnitude_N: number, direction: Vec3): Vec3 {
  if (thrustMagnitude_N === 0) return VEC3_ZERO;
  return scale(direction, thrustMagnitude_N);
}

/**
 * Nozzle exit area implied by a pair of sea-level and vacuum thrust ratings.
 *
 * From F_vac = F_sl + P₀·Aₑ:
 *   Aₑ = (F_vac − F_sl) / P₀
 *
 * @param vacuumThrust_N - Vacuum thrust rating. Unit: N.
 * @param seaLevelThrust_N - Sea-level thrust rating. Unit: N.
 * @returns Effective nozzle exit area. Unit: m². Zero if the ratings are equal
 *   (a vacuum-only engine specified with a single figure).
 */
export function impliedExitArea(vacuumThrust_N: number, seaLevelThrust_N: number): number {
  return Math.max(0, (vacuumThrust_N - seaLevelThrust_N) / P0_SEA_LEVEL);
}

/**
 * Thrust at an arbitrary ambient pressure, interpolating between the engine's
 * sea-level and vacuum ratings.
 *
 * F(p) = F_vac − p · Aₑ
 *
 * @param vacuumThrust_N - Vacuum thrust rating. Unit: N.
 * @param seaLevelThrust_N - Sea-level thrust rating. Unit: N.
 * @param ambientPressure_Pa - Ambient static pressure. Unit: Pa.
 * @returns Thrust at the given ambient pressure. Unit: N. Never negative.
 */
export function thrustAtPressure(
  vacuumThrust_N: number,
  seaLevelThrust_N: number,
  ambientPressure_Pa: number,
): number {
  const exitArea = impliedExitArea(vacuumThrust_N, seaLevelThrust_N);
  return Math.max(0, vacuumThrust_N - ambientPressure_Pa * exitArea);
}

/**
 * Specific impulse at an arbitrary ambient pressure.
 *
 * Isp scales with thrust at constant mass flow, so this is the thrust ratio
 * applied to the vacuum Isp.
 *
 * @param vacuumIsp_s - Vacuum specific impulse. Unit: s.
 * @param seaLevelIsp_s - Sea-level specific impulse. Unit: s.
 * @param ambientPressure_Pa - Ambient static pressure. Unit: Pa.
 * @returns Specific impulse at the given pressure. Unit: s.
 */
export function ispAtPressure(
  vacuumIsp_s: number,
  seaLevelIsp_s: number,
  ambientPressure_Pa: number,
): number {
  if (vacuumIsp_s <= seaLevelIsp_s) return vacuumIsp_s;
  const fraction = Math.min(1, Math.max(0, ambientPressure_Pa / P0_SEA_LEVEL));
  return vacuumIsp_s - (vacuumIsp_s - seaLevelIsp_s) * fraction;
}

/**
 * Compute exhaust velocity from specific impulse.
 *
 * v_e = Isp × g₀
 *
 * @param isp_s - Specific impulse. Unit: s.
 * @returns Effective exhaust velocity. Unit: m/s.
 */
export function exhaustVelocity(isp_s: number): number {
  return isp_s * G0;
}

/**
 * Compute delta-v for a single stage (Tsiolkovsky rocket equation).
 *
 * Δv = v_e × ln(m_initial / m_final)
 *
 * This is the *ideal* delta-v: it excludes gravity losses, drag losses, and
 * steering losses, which together typically consume 1.5–2.0 km/s on an Earth
 * ascent to orbit. Compare the value reported here with the velocity the
 * simulation actually achieves to see those losses.
 *
 * @param isp_s - Specific impulse. Unit: s.
 * @param initialMass_kg - Total mass before burn. Unit: kg.
 * @param finalMass_kg - Total mass after burn (dry mass). Unit: kg. Must be > 0.
 * @returns Delta-v. Unit: m/s.
 */
export function deltaV(
  isp_s: number,
  initialMass_kg: number,
  finalMass_kg: number,
): number {
  if (finalMass_kg <= 0) {
    throw new RangeError(`finalMass_kg must be > 0, got ${finalMass_kg}`);
  }
  if (initialMass_kg <= finalMass_kg) {
    return 0;
  }
  const ve = exhaustVelocity(isp_s);
  return ve * Math.log(initialMass_kg / finalMass_kg);
}

/**
 * Compute thrust-to-weight ratio at a given altitude.
 *
 * Weight uses the *local* gravitational acceleration, so TWR rises with
 * altitude even at constant thrust. At sea level this reduces to F / (m·g₀).
 *
 * @param thrust_N - Thrust force. Unit: N.
 * @param mass_kg - Vehicle mass. Unit: kg.
 * @param altitude_m - Geometric altitude. Unit: m. Negative values are clamped
 *   to sea level.
 * @returns TWR (dimensionless). Must exceed 1 for a vertical liftoff.
 */
export function thrustToWeightRatio(
  thrust_N: number,
  mass_kg: number,
  altitude_m: number,
): number {
  if (mass_kg <= 0) return 0;
  const g = gravityAtAltitude(Math.max(0, altitude_m));
  return thrust_N / (mass_kg * g);
}
