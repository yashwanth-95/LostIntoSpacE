/**
 * Orbital state approximation — classical elements from a position/velocity pair.
 *
 * This is the standard two-body ("Keplerian") solution. Given r⃗ and v⃗ at one
 * instant it produces the conic section the vehicle would follow if thrust,
 * drag, and every perturbation stopped right now. It is what "orbital
 * parameters" in the telemetry stream mean.
 *
 * Assumptions:
 *   - Two-body point-mass gravity: no J2, no drag, no third bodies, no thrust
 *   - Instantaneous ("osculating") elements — during powered flight or inside
 *     the atmosphere these change every step and should be read as *"the orbit
 *     you would coast into from here"*, not as a prediction
 *   - Angles are referenced to the frame the caller supplies. Pass ECI-aligned
 *     vectors (see `physics/frames.ts`) or inclination and RAAN are meaningless.
 *
 * Reference: Vallado, *Fundamentals of Astrodynamics and Applications*, §2.5
 *
 * @module physics/orbital
 */

import { MU_EARTH, R_EARTH } from './constants.js';
import type { Vec3 } from './vec3.js';
import { vec3, cross, dot, sub, scale, magnitude } from './vec3.js';

/** Classification of the conic section a state vector describes. */
export type OrbitShape = 'circular' | 'elliptical' | 'parabolic' | 'hyperbolic';

/** Classical orbital elements plus the derived quantities a UI wants. */
export interface OrbitalElements {
  /** Semi-major axis. Negative for hyperbolic orbits. Unit: m. */
  readonly semiMajorAxis_m: number;
  /** Eccentricity. Dimensionless. 0 = circular, <1 = elliptical, >=1 = escape. */
  readonly eccentricity: number;
  /** Inclination from the frame's reference plane. Unit: rad, [0, π]. */
  readonly inclination_rad: number;
  /** Right ascension of the ascending node. Unit: rad, [0, 2π). 0 if equatorial. */
  readonly raan_rad: number;
  /** Argument of periapsis. Unit: rad, [0, 2π). 0 if circular. */
  readonly argumentOfPeriapsis_rad: number;
  /** True anomaly — angular position from periapsis. Unit: rad, [0, 2π). */
  readonly trueAnomaly_rad: number;

  /** Periapsis radius from the body centre. Unit: m. */
  readonly periapsisRadius_m: number;
  /** Apoapsis radius from the body centre. Infinity for escape orbits. Unit: m. */
  readonly apoapsisRadius_m: number;
  /** Periapsis altitude above the body surface. Negative means it intersects. Unit: m. */
  readonly periapsisAltitude_m: number;
  /** Apoapsis altitude above the body surface. Infinity for escape orbits. Unit: m. */
  readonly apoapsisAltitude_m: number;

  /** Orbital period. Infinity for parabolic/hyperbolic orbits. Unit: s. */
  readonly period_s: number;
  /** Specific orbital energy (ε = v²/2 − μ/r). Unit: J/kg. */
  readonly specificEnergy_Jkg: number;
  /** Specific angular momentum magnitude. Unit: m²/s. */
  readonly specificAngularMomentum_m2s: number;

  /** Conic section classification. */
  readonly shape: OrbitShape;
  /**
   * Whether this is a closed orbit that clears the body's surface — i.e. the
   * vehicle would complete a revolution rather than re-entering. This is the
   * flag the mission state machine uses to declare orbit insertion.
   */
  readonly isStableOrbit: boolean;
}

/** Tolerance below which eccentricity is treated as zero (circular). */
const CIRCULAR_TOLERANCE = 1e-8;
/** Tolerance below which the node vector is treated as zero (equatorial). */
const EQUATORIAL_TOLERANCE = 1e-8;

/** Wrap an angle into [0, 2π). */
function wrapTwoPi(angle_rad: number): number {
  const twoPi = 2 * Math.PI;
  const wrapped = angle_rad % twoPi;
  return wrapped < 0 ? wrapped + twoPi : wrapped;
}

/** Numerically safe arc cosine — clamps the argument into [-1, 1]. */
function safeAcos(x: number): number {
  return Math.acos(Math.min(1, Math.max(-1, x)));
}

/**
 * Compute classical orbital elements from an instantaneous state vector.
 *
 * @param position - Position from the body centre. Unit: m. Must be non-zero.
 * @param velocity - Velocity in the same frame. Unit: m/s.
 * @param mu_m3s2 - Gravitational parameter of the central body. Unit: m³/s².
 *   Defaults to Earth.
 * @param bodyRadius_m - Body radius, used for the altitude fields. Unit: m.
 *   Defaults to Earth.
 * @returns The osculating orbital elements.
 * @throws RangeError if the position vector is degenerate.
 */
export function orbitalElements(
  position: Vec3,
  velocity: Vec3,
  mu_m3s2: number = MU_EARTH,
  bodyRadius_m: number = R_EARTH,
): OrbitalElements {
  const r = magnitude(position);
  if (r < 1e-6) {
    throw new RangeError('position must be a non-zero vector from the body centre');
  }
  const v = magnitude(velocity);

  // Specific angular momentum h⃗ = r⃗ × v⃗
  const hVec = cross(position, velocity);
  const h = magnitude(hVec);

  // Node vector n⃗ = ẑ × h⃗ — points at the ascending node
  const nVec = vec3(-hVec.y, hVec.x, 0);
  const n = magnitude(nVec);

  // Eccentricity vector e⃗ = ((v² − μ/r)·r⃗ − (r⃗·v⃗)·v⃗) / μ
  const rDotV = dot(position, velocity);
  const eVec = scale(
    sub(scale(position, v * v - mu_m3s2 / r), scale(velocity, rDotV)),
    1 / mu_m3s2,
  );
  const eccentricity = magnitude(eVec);

  // Specific orbital energy and semi-major axis
  const specificEnergy_Jkg = (v * v) / 2 - mu_m3s2 / r;
  const isParabolic = Math.abs(specificEnergy_Jkg) < 1e-9;
  const semiMajorAxis_m = isParabolic ? Infinity : -mu_m3s2 / (2 * specificEnergy_Jkg);

  // Inclination from the reference plane
  const inclination_rad = h > 0 ? safeAcos(hVec.z / h) : 0;

  // RAAN — undefined for an equatorial orbit, reported as 0 by convention
  let raan_rad = 0;
  if (n > EQUATORIAL_TOLERANCE) {
    raan_rad = safeAcos(nVec.x / n);
    if (nVec.y < 0) raan_rad = 2 * Math.PI - raan_rad;
  }

  // Argument of periapsis — undefined for a circular orbit, reported as 0
  let argumentOfPeriapsis_rad = 0;
  if (n > EQUATORIAL_TOLERANCE && eccentricity > CIRCULAR_TOLERANCE) {
    argumentOfPeriapsis_rad = safeAcos(dot(nVec, eVec) / (n * eccentricity));
    if (eVec.z < 0) argumentOfPeriapsis_rad = 2 * Math.PI - argumentOfPeriapsis_rad;
  } else if (eccentricity > CIRCULAR_TOLERANCE) {
    // Equatorial but eccentric: fall back to the longitude of periapsis.
    argumentOfPeriapsis_rad = wrapTwoPi(Math.atan2(eVec.y, eVec.x));
  }

  // True anomaly — for a circular orbit, measure from the ascending node instead
  let trueAnomaly_rad: number;
  if (eccentricity > CIRCULAR_TOLERANCE) {
    trueAnomaly_rad = safeAcos(dot(eVec, position) / (eccentricity * r));
    if (rDotV < 0) trueAnomaly_rad = 2 * Math.PI - trueAnomaly_rad;
  } else if (n > EQUATORIAL_TOLERANCE) {
    trueAnomaly_rad = safeAcos(dot(nVec, position) / (n * r));
    if (position.z < 0) trueAnomaly_rad = 2 * Math.PI - trueAnomaly_rad;
  } else {
    trueAnomaly_rad = wrapTwoPi(Math.atan2(position.y, position.x));
  }

  // Apsides. For open orbits only the periapsis exists.
  const isClosed = eccentricity < 1 && Number.isFinite(semiMajorAxis_m);
  const periapsisRadius_m = isClosed
    ? semiMajorAxis_m * (1 - eccentricity)
    : (h * h) / (mu_m3s2 * (1 + eccentricity));
  const apoapsisRadius_m = isClosed ? semiMajorAxis_m * (1 + eccentricity) : Infinity;

  const period_s = isClosed
    ? 2 * Math.PI * Math.sqrt(Math.pow(semiMajorAxis_m, 3) / mu_m3s2)
    : Infinity;

  return {
    semiMajorAxis_m,
    eccentricity,
    inclination_rad,
    raan_rad,
    argumentOfPeriapsis_rad,
    trueAnomaly_rad,
    periapsisRadius_m,
    apoapsisRadius_m,
    periapsisAltitude_m: periapsisRadius_m - bodyRadius_m,
    apoapsisAltitude_m: apoapsisRadius_m - bodyRadius_m,
    period_s,
    specificEnergy_Jkg,
    specificAngularMomentum_m2s: h,
    shape: classifyOrbit(eccentricity),
    // A "stable orbit" must be closed and clear the surface. We do not add an
    // atmospheric-decay margin here — that is a mission-profile decision, made
    // in sim/mission-state.ts.
    isStableOrbit: isClosed && periapsisRadius_m > bodyRadius_m,
  };
}

/**
 * Classify a conic section from its eccentricity.
 *
 * @param eccentricity - Orbital eccentricity. Dimensionless.
 * @returns The conic section type.
 */
export function classifyOrbit(eccentricity: number): OrbitShape {
  if (eccentricity < CIRCULAR_TOLERANCE) return 'circular';
  if (eccentricity < 1 - 1e-9) return 'elliptical';
  if (eccentricity < 1 + 1e-9) return 'parabolic';
  return 'hyperbolic';
}

/**
 * Sample a closed orbit into a list of position vectors, for drawing the orbit
 * path in 3D.
 *
 * Points are generated in the same frame as the elements were computed in, by
 * evaluating the conic equation r(ν) = p / (1 + e·cos ν) and rotating from the
 * perifocal frame through ω, i, and Ω.
 *
 * @param elements - Orbital elements to sample.
 * @param segments - Number of points to generate. More is smoother.
 * @returns Positions around one full revolution. Empty for open orbits, which
 *   have no closed path to draw.
 */
export function sampleOrbitPath(
  elements: OrbitalElements,
  segments = 128,
): Vec3[] {
  if (elements.eccentricity >= 1 || !Number.isFinite(elements.semiMajorAxis_m)) {
    return [];
  }

  const { eccentricity: e, semiMajorAxis_m: a } = elements;
  const semiLatusRectum = a * (1 - e * e);

  const cosW = Math.cos(elements.argumentOfPeriapsis_rad);
  const sinW = Math.sin(elements.argumentOfPeriapsis_rad);
  const cosI = Math.cos(elements.inclination_rad);
  const sinI = Math.sin(elements.inclination_rad);
  const cosO = Math.cos(elements.raan_rad);
  const sinO = Math.sin(elements.raan_rad);

  const points: Vec3[] = [];
  for (let i = 0; i <= segments; i++) {
    const nu = (2 * Math.PI * i) / segments;
    const r = semiLatusRectum / (1 + e * Math.cos(nu));

    // Perifocal coordinates
    const xp = r * Math.cos(nu);
    const yp = r * Math.sin(nu);

    // Rotate perifocal → reference frame: Rz(-Ω) · Rx(-i) · Rz(-ω)
    points.push(
      vec3(
        xp * (cosO * cosW - sinO * sinW * cosI) - yp * (cosO * sinW + sinO * cosW * cosI),
        xp * (sinO * cosW + cosO * sinW * cosI) - yp * (sinO * sinW - cosO * cosW * cosI),
        xp * (sinW * sinI) + yp * (cosW * sinI),
      ),
    );
  }
  return points;
}
