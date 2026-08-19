/**
 * Guidance — the attitude program that decides where thrust points.
 *
 * The engine is 3-DOF: it integrates translation only, and attitude is
 * *commanded*, not derived from moments. Nothing here models a control loop,
 * gimbal actuators, or rotational inertia. What it does model is the shape of a
 * real ascent, which is what determines whether a vehicle reaches orbit or
 * comes straight back down.
 *
 * ## Why a rocket does not fly straight up
 *
 * A vehicle that thrusts vertically for its whole burn arrives at apogee with
 * no horizontal velocity and falls back. Orbit is almost entirely a *sideways*
 * problem: at 200 km you need about 7.8 km/s horizontally and essentially no
 * vertical speed. So a launch vehicle pitches over early and spends most of its
 * burn accelerating downrange.
 *
 * Two programs are offered:
 *
 * - **`pitch_program`** — pitch is a scheduled function of altitude. Fully
 *   deterministic and easy to reason about, which makes it the default.
 * - **`gravity_turn`** — after an initial pitchover kick, thrust simply follows
 *   the velocity vector and gravity does the steering. This is what real
 *   vehicles fly, and it costs nothing in steering losses because thrust and
 *   velocity stay aligned.
 *
 * @module sim/guidance
 */

import { DEG_TO_RAD } from '../physics/constants.js';
import type { Vec3 } from '../physics/vec3.js';
import { magnitude, normalize, vec3 } from '../physics/vec3.js';
import { directionFromPitchAzimuth } from '../physics/frames.js';

/** Which attitude program to fly. */
export type GuidanceMode = 'vertical' | 'pitch_program' | 'gravity_turn';

/** Configuration for the attitude program. */
export interface GuidanceConfig {
  /** Program to fly. */
  readonly mode: GuidanceMode;
  /**
   * Compass bearing to launch along, clockwise from North. Unit: degrees.
   *
   * 90° is due east, which is what an orbital launch normally wants: it is the
   * direction Earth's rotation already carries the vehicle. (The engine does not
   * model that rotational bonus — see `physics/frames.ts` — but the convention
   * is kept so inclinations come out right.)
   */
  readonly launchAzimuth_deg: number;
  /** Altitude at which the pitchover begins. Unit: m. */
  readonly pitchoverAltitude_m: number;
  /** Altitude by which the program reaches its final pitch. Unit: m. */
  readonly pitchProgramEndAltitude_m: number;
  /** Pitch held at and beyond the end of the program. Unit: degrees. */
  readonly finalPitch_deg: number;
  /**
   * Size of the initial pitchover, for `gravity_turn`. Unit: degrees.
   *
   * A gravity turn needs a real nudge to start: thrust held exactly along a
   * vertical velocity vector produces no turning at all, and a one- or
   * two-degree kick leaves the vehicle climbing almost straight up while
   * gravity bends it far too slowly to reach orbit. Real vehicles pitch over by
   * about ten degrees, held across several seconds of climb, and let gravity
   * take it from there.
   */
  readonly gravityTurnKick_deg: number;

  /**
   * How far above the pitchover altitude the kick is ramped in, as a multiple
   * of `pitchoverAltitude_m`. Dimensionless, > 1.
   *
   * Ramping rather than stepping keeps the commanded attitude continuous, which
   * matters because the vehicle's velocity vector follows it.
   */
  readonly gravityTurnKickBand: number;
  /**
   * Speed below which the gravity turn does not follow velocity. Unit: m/s.
   *
   * At low speed the velocity direction is noisy and following it would swing
   * the vehicle around. Below this threshold the scheduled pitch is used.
   */
  readonly gravityTurnMinSpeed_ms: number;

  /**
   * Whether to shut the engines down on reaching the mission's target orbit.
   *
   * Real vehicles do exactly this: second-stage cutoff is commanded when the
   * guidance computer sees the target orbit achieved, not when the tanks run
   * dry. Without it an over-performing vehicle burns its whole propellant load
   * and ends up in a wildly elliptical orbit instead of the circular one the
   * mission asked for — and the leftover propellant is what a real mission
   * would have kept as margin.
   */
  readonly cutoffOnTargetOrbit: boolean;
}

/** A due-east ascent with a gentle pitchover — a reasonable orbital profile. */
/**
 * A due-east ascent that reaches low Earth orbit.
 *
 * The pitchover starts low and the program flattens to horizontal by 80 km,
 * which puts gravity losses near 1.4 km/s — in line with what real launch
 * vehicles pay.
 */
export const DEFAULT_GUIDANCE: GuidanceConfig = {
  mode: 'pitch_program',
  launchAzimuth_deg: 90,
  pitchoverAltitude_m: 200,
  pitchProgramEndAltitude_m: 80_000,
  finalPitch_deg: 0,
  gravityTurnKick_deg: 12,
  gravityTurnKickBand: 4,
  gravityTurnMinSpeed_ms: 80,
  cutoffOnTargetOrbit: true,
} as const;

/** Straight up, for sounding rockets and stability demonstrations. */
export const VERTICAL_GUIDANCE: GuidanceConfig = {
  ...DEFAULT_GUIDANCE,
  mode: 'vertical',
  cutoffOnTargetOrbit: false,
} as const;

/** A gravity turn, the profile real launch vehicles fly. */
export const GRAVITY_TURN_GUIDANCE: GuidanceConfig = {
  ...DEFAULT_GUIDANCE,
  mode: 'gravity_turn',
  pitchoverAltitude_m: 500,
} as const;

/** The attitude the guidance system is commanding. */
export interface GuidanceCommand {
  /** Elevation above the local horizontal. π/2 is straight up. Unit: rad. */
  readonly pitch_rad: number;
  /** Compass bearing, clockwise from North. Unit: rad. */
  readonly yaw_rad: number;
  /** Unit vector in the launch-centred ENU frame that thrust acts along. */
  readonly thrustDirection: Vec3;
}

/** What the guidance program is allowed to look at. */
export interface GuidanceInputs {
  /** Altitude above mean sea level. Unit: m. */
  readonly altitude_m: number;
  /** Velocity in the launch-centred ENU frame. Unit: m/s. */
  readonly velocity: Vec3;
  /** Local "up" direction — the radial unit vector at the vehicle's position. */
  readonly localUp: Vec3;
  /**
   * Whether guidance has failed. A failed guidance system holds its last
   * command rather than updating, which is what {@link frozenCommand} produces.
   */
  readonly guidanceFailed: boolean;
  /** The last command issued, held when guidance has failed. */
  readonly lastCommand: GuidanceCommand | null;
}

/**
 * Scheduled pitch as a function of altitude.
 *
 * Vertical below the pitchover altitude, then linear in altitude down to the
 * final pitch, then held. Linear-in-altitude rather than linear-in-time so the
 * program does not depend on how fast the vehicle happens to be climbing.
 *
 * @param altitude_m - Current altitude. Unit: m.
 * @param config - Guidance configuration.
 * @returns Commanded pitch. Unit: rad.
 */
export function scheduledPitch(altitude_m: number, config: GuidanceConfig): number {
  const vertical_rad = Math.PI / 2;
  const final_rad = config.finalPitch_deg * DEG_TO_RAD;

  if (altitude_m <= config.pitchoverAltitude_m) {
    return vertical_rad;
  }

  const span = config.pitchProgramEndAltitude_m - config.pitchoverAltitude_m;
  if (span <= 0) return final_rad;

  const fraction = Math.min(1, (altitude_m - config.pitchoverAltitude_m) / span);
  return vertical_rad + (final_rad - vertical_rad) * fraction;
}

/**
 * Compute the attitude command for the current state.
 *
 * @param inputs - Current flight state.
 * @param config - Guidance configuration.
 * @returns The commanded pitch, yaw, and thrust direction.
 */
export function computeGuidance(
  inputs: GuidanceInputs,
  config: GuidanceConfig,
): GuidanceCommand {
  // A failed guidance system stops updating and holds whatever it last had.
  if (inputs.guidanceFailed && inputs.lastCommand) {
    return inputs.lastCommand;
  }

  const yaw_rad = config.launchAzimuth_deg * DEG_TO_RAD;

  switch (config.mode) {
    case 'vertical':
      return command(Math.PI / 2, yaw_rad);

    case 'pitch_program':
      return command(scheduledPitch(inputs.altitude_m, config), yaw_rad);

    case 'gravity_turn': {
      const speed = magnitude(inputs.velocity);

      // Below the pitchover altitude, or too slow for the velocity vector to be
      // a trustworthy reference, fly the schedule instead.
      if (
        inputs.altitude_m <= config.pitchoverAltitude_m ||
        speed < config.gravityTurnMinSpeed_ms
      ) {
        return command(Math.PI / 2, yaw_rad);
      }

      // Ramp the pitchover in across the kick band. Stepping straight to the
      // final kick angle would put thrust well off the velocity vector and
      // waste it steering.
      const kickCeiling = config.pitchoverAltitude_m * config.gravityTurnKickBand;
      const kick_rad = config.gravityTurnKick_deg * DEG_TO_RAD;
      if (inputs.altitude_m < kickCeiling) {
        const band = kickCeiling - config.pitchoverAltitude_m;
        const fraction =
          band > 0 ? (inputs.altitude_m - config.pitchoverAltitude_m) / band : 1;
        return command(Math.PI / 2 - kick_rad * fraction, yaw_rad);
      }

      // Established: thrust along the velocity vector. Gravity bends the
      // velocity over, and thrust follows it — no steering losses.
      const direction = normalize(inputs.velocity);
      const sinPitch = Math.min(
        1,
        Math.max(-1, dotProduct(direction, inputs.localUp)),
      );
      return {
        pitch_rad: Math.asin(sinPitch),
        yaw_rad: Math.atan2(direction.x, direction.y),
        thrustDirection: direction,
      };
    }
  }
}

/** Build a command from pitch and yaw. */
function command(pitch_rad: number, yaw_rad: number): GuidanceCommand {
  return {
    pitch_rad,
    yaw_rad,
    thrustDirection: directionFromPitchAzimuth(pitch_rad, yaw_rad),
  };
}

/** Dot product, inlined to keep this module free of a vec3 import cycle. */
function dotProduct(a: Vec3, b: Vec3): number {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

/** The command a vehicle starts with: straight up, along the launch azimuth. */
export function initialCommand(config: GuidanceConfig): GuidanceCommand {
  return command(Math.PI / 2, config.launchAzimuth_deg * DEG_TO_RAD);
}

/**
 * Freeze a command, as a failed guidance system would.
 *
 * @param last - The last good command, if there was one.
 * @param config - Guidance configuration, for the fallback.
 * @returns The held command.
 */
export function frozenCommand(
  last: GuidanceCommand | null,
  config: GuidanceConfig,
): GuidanceCommand {
  return last ?? initialCommand(config);
}

/**
 * Angle between the thrust axis and the velocity vector.
 *
 * In a 3-DOF model this does not generate a side force, but it is the number
 * that explains steering losses: thrust spent at an angle to the direction of
 * travel does not add to speed. It is reported in telemetry for exactly that
 * reason.
 *
 * @param thrustDirection - Unit vector along the thrust axis.
 * @param velocity - Velocity vector. Unit: m/s.
 * @returns Angle between them. Unit: rad. Zero when the vehicle is stationary.
 */
export function angleOfAttack(thrustDirection: Vec3, velocity: Vec3): number {
  const speed = magnitude(velocity);
  if (speed < 1e-6) return 0;

  const cosAngle = dotProduct(thrustDirection, normalize(velocity));
  return Math.acos(Math.min(1, Math.max(-1, cosAngle)));
}

/**
 * The local vertical at a position in the launch-centred ENU frame.
 *
 * Straight up over the pad is +Z, but the local vertical tilts as the vehicle
 * travels downrange, and the guidance model has to follow it.
 *
 * @param position - Position in the ENU frame. Unit: m.
 * @param siteRadius_m - Distance from Earth's centre to the launch site. Unit: m.
 * @returns The radial unit vector at that position.
 */
export function localUpVector(position: Vec3, siteRadius_m: number): Vec3 {
  const earthCentered = vec3(position.x, position.y, position.z + siteRadius_m);
  return normalize(earthCentered);
}
