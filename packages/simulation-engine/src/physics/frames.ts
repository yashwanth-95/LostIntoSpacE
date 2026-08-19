/**
 * Coordinate frame conversions.
 *
 * The engine integrates trajectories in a **Launch-Centred ENU frame**:
 *
 *   origin  — the launch site
 *   +X      — East
 *   +Y      — North
 *   +Z      — Up (the local vertical at the launch site)
 *
 * The axes are *fixed at t = 0* and do not follow the vehicle, so the frame is
 * inertial under the engine's non-rotating-Earth assumption. That makes it a
 * valid frame for Newtonian integration all the way to orbit — "up" stops being
 * the direction of gravity once the vehicle travels downrange, which is exactly
 * why the force model uses a central field rather than a constant −Z.
 *
 * Two derived frames matter:
 *
 * - **Earth-centred ENU** — the same axes, with the origin moved to the centre
 *   of the Earth. This is what the gravity model needs.
 * - **ECI-aligned** — Earth-centred with +Z through the North pole and +X
 *   through the prime meridian at t = 0. Orbital elements are only meaningful
 *   here: inclination measured in the ENU frame would be relative to the launch
 *   site's horizon, not the equator.
 *
 * Assumptions:
 *   - Spherical Earth of radius R_EARTH (no WGS-84 ellipsoid flattening, so
 *     geodetic and geocentric latitude are treated as equal)
 *   - Non-rotating Earth: the ECI-aligned frame coincides with ECEF at t = 0 and
 *     the engine never advances Earth rotation. A real eastward equatorial
 *     launch gains ~465 m/s that this engine does not model.
 *
 * @module physics/frames
 */

import { R_EARTH, DEG_TO_RAD } from './constants.js';
import type { Vec3 } from './vec3.js';
import { vec3, add, scale, magnitude } from './vec3.js';

/** A launch site on a spherical Earth. */
export interface SiteLocation {
  /** Geodetic latitude. Unit: degrees, [-90, 90]. */
  readonly latitude_deg: number;
  /** Longitude. Unit: degrees, [-180, 180]. */
  readonly longitude_deg: number;
  /** Site elevation above mean sea level. Unit: m. */
  readonly altitude_m: number;
}

/** The three ENU basis vectors of a site, expressed in ECI-aligned axes. */
export interface EnuBasis {
  readonly east: Vec3;
  readonly north: Vec3;
  readonly up: Vec3;
  /** The site's own position vector from Earth's centre, in ECI-aligned axes. Unit: m. */
  readonly origin: Vec3;
}

/**
 * Build the ENU basis of a site in ECI-aligned axes.
 *
 * @param site - Launch site location.
 * @returns The east/north/up unit vectors and the site's position vector.
 */
export function enuBasis(site: SiteLocation): EnuBasis {
  const lat = site.latitude_deg * DEG_TO_RAD;
  const lon = site.longitude_deg * DEG_TO_RAD;

  const sinLat = Math.sin(lat);
  const cosLat = Math.cos(lat);
  const sinLon = Math.sin(lon);
  const cosLon = Math.cos(lon);

  const up = vec3(cosLat * cosLon, cosLat * sinLon, sinLat);

  return {
    east: vec3(-sinLon, cosLon, 0),
    north: vec3(-sinLat * cosLon, -sinLat * sinLon, cosLat),
    up,
    origin: scale(up, R_EARTH + site.altitude_m),
  };
}

/**
 * Convert a position in the launch-centred ENU frame to an Earth-centred
 * position in the *same* ENU axes.
 *
 * This is a pure translation along +Z by the site's geocentric radius, and it is
 * all the gravity model needs: a central field is rotationally symmetric, so it
 * does not care how the axes are oriented.
 *
 * @param enuPosition - Position relative to the launch site. Unit: m.
 * @param siteAltitude_m - Site elevation above sea level. Unit: m.
 * @returns Position from Earth's centre, in ENU axes. Unit: m.
 */
export function enuToEarthCentered(enuPosition: Vec3, siteAltitude_m: number): Vec3 {
  return vec3(
    enuPosition.x,
    enuPosition.y,
    enuPosition.z + R_EARTH + siteAltitude_m,
  );
}

/**
 * Geometric altitude above the spherical surface, from a launch-centred ENU
 * position.
 *
 * Altitude is `|r⃗| − R`, not simply the ENU `z` component: a vehicle 500 km
 * downrange at `z = 0` is genuinely ~20 km above the curved surface.
 *
 * @param enuPosition - Position relative to the launch site. Unit: m.
 * @param siteAltitude_m - Site elevation above sea level. Unit: m.
 * @returns Altitude above mean sea level. Unit: m. May be negative below ground.
 */
export function altitudeFromEnu(enuPosition: Vec3, siteAltitude_m: number): number {
  return magnitude(enuToEarthCentered(enuPosition, siteAltitude_m)) - R_EARTH;
}

/**
 * Great-circle downrange distance from the launch site.
 *
 * Computed as the arc length `R · θ`, where θ is the central angle between the
 * site and the vehicle. This is the distance a ground observer would measure,
 * not the straight-line chord.
 *
 * @param enuPosition - Position relative to the launch site. Unit: m.
 * @param siteAltitude_m - Site elevation above sea level. Unit: m.
 * @returns Downrange distance along the surface. Unit: m.
 */
export function downrangeFromEnu(enuPosition: Vec3, siteAltitude_m: number): number {
  const siteRadius = R_EARTH + siteAltitude_m;
  const r = enuToEarthCentered(enuPosition, siteAltitude_m);
  const rMag = magnitude(r);
  if (rMag < 1e-6) return 0;

  // The site direction is +Z in ENU axes, so cos θ is just the normalised z.
  const cosTheta = Math.min(1, Math.max(-1, r.z / rMag));
  return siteRadius * Math.acos(cosTheta);
}

/**
 * Rotate a vector from launch-centred ENU axes into ECI-aligned axes.
 *
 * Use this for velocities and other free vectors; use {@link enuPositionToEci}
 * for positions, which also need the site translation.
 *
 * @param enuVector - Vector in ENU axes.
 * @param basis - The site's ENU basis (from {@link enuBasis}).
 * @returns The same vector expressed in ECI-aligned axes.
 */
export function enuVectorToEci(enuVector: Vec3, basis: EnuBasis): Vec3 {
  return add(
    add(scale(basis.east, enuVector.x), scale(basis.north, enuVector.y)),
    scale(basis.up, enuVector.z),
  );
}

/**
 * Convert a launch-centred ENU position into an Earth-centred, ECI-aligned
 * position.
 *
 * @param enuPosition - Position relative to the launch site. Unit: m.
 * @param basis - The site's ENU basis (from {@link enuBasis}).
 * @returns Position from Earth's centre in ECI-aligned axes. Unit: m.
 */
export function enuPositionToEci(enuPosition: Vec3, basis: EnuBasis): Vec3 {
  return add(basis.origin, enuVectorToEci(enuPosition, basis));
}

/**
 * Build a unit vector in the launch-centred ENU frame from a flight-path
 * elevation and a compass azimuth.
 *
 * @param pitch_rad - Elevation above the local horizontal. π/2 is straight up,
 *   0 is horizontal. Unit: rad.
 * @param azimuth_rad - Compass bearing, measured clockwise from North.
 *   0 is North, π/2 is East. Unit: rad.
 * @returns Unit direction vector in ENU axes.
 */
export function directionFromPitchAzimuth(pitch_rad: number, azimuth_rad: number): Vec3 {
  const horizontal = Math.cos(pitch_rad);
  return vec3(
    horizontal * Math.sin(azimuth_rad), // East
    horizontal * Math.cos(azimuth_rad), // North
    Math.sin(pitch_rad),                // Up
  );
}
