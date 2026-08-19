/**
 * Force model — everything that accelerates the vehicle.
 *
 * This is the glue between `physics/` (which knows equations) and `sim/` (which
 * knows the flight). It is kept separate from the runner for two reasons:
 * it is the piece most likely to be replaced by a higher-fidelity model, and
 * it is the piece that must be *pure* so RK4 can call it four times per step.
 *
 * ## Forces modelled
 *
 * | Force   | Model                                                    |
 * |---------|----------------------------------------------------------|
 * | Gravity | Central inverse-square field                              |
 * | Thrust  | Along the commanded attitude, pressure-compensated        |
 * | Drag    | ½ρv²·Cd·A, anti-parallel to velocity, Mach-corrected      |
 *
 * ## Not modelled
 *
 * Lift, wind, Earth rotation (so no Coriolis and no free eastward velocity),
 * J2 oblateness, third bodies, solar radiation pressure, and any rotational
 * dynamics. Each is documented where it would enter.
 *
 * @module sim/forces
 */

import { R_EARTH, MU_EARTH } from '../physics/constants.js';
import type { Vec3 } from '../physics/vec3.js';
import { vec3, add, scale, magnitude } from '../physics/vec3.js';
import { gravityAccelerationCentral } from '../physics/gravity.js';
import {
  atmosphere,
  machNumber,
  dynamicPressure,
  type AtmosphereState,
} from '../physics/atmosphere.js';
import { dragForce, effectiveDragCoefficient } from '../physics/drag.js';
import { thrustAtPressure } from '../physics/thrust.js';

/** Everything the force model needs about the current instant. */
export interface ForceInputs {
  /** Position in the launch-centred ENU frame. Unit: m. */
  readonly position: Vec3;
  /** Velocity in the same frame. Unit: m/s. */
  readonly velocity: Vec3;
  /** Current total mass. Unit: kg. Must be > 0. */
  readonly mass_kg: number;
  /** Unit vector along which thrust acts. */
  readonly thrustDirection: Vec3;
  /** Vacuum thrust of the burning stage, 0 if not burning. Unit: N. */
  readonly thrustVacuum_N: number;
  /** Sea-level thrust of the burning stage, 0 if not burning. Unit: N. */
  readonly thrustSeaLevel_N: number;
  /** Vehicle reference area. Unit: m². */
  readonly referenceArea_m2: number;
  /** Vehicle subsonic drag coefficient. Dimensionless. */
  readonly dragCoefficient: number;
  /** Distance from Earth's centre to the launch site. Unit: m. */
  readonly siteRadius_m: number;
  /** Whether to apply the transonic drag rise. */
  readonly useMachDragRise: boolean;
  /** Whether thrust varies with ambient pressure. */
  readonly useAltitudeCompensation: boolean;
}

/** The forces acting, broken out so telemetry can report each one. */
export interface ForceResult {
  /** Thrust force vector. Unit: N. */
  readonly thrust: Vec3;
  /** Drag force vector. Unit: N. */
  readonly drag: Vec3;
  /** Gravitational force vector. Unit: N. */
  readonly gravity: Vec3;
  /** Sum of the above. Unit: N. */
  readonly net: Vec3;
  /** Net acceleration. Unit: m/s². */
  readonly acceleration: Vec3;

  /** Thrust magnitude at the current ambient pressure. Unit: N. */
  readonly thrustMagnitude_N: number;
  /** Drag magnitude. Unit: N. */
  readonly dragMagnitude_N: number;
  /** Local gravitational acceleration. Unit: m/s². */
  readonly localGravity_ms2: number;

  /** Atmospheric conditions at the current altitude. */
  readonly atmosphere: AtmosphereState;
  /** Altitude above mean sea level. Unit: m. */
  readonly altitude_m: number;
  /** Mach number. Dimensionless. */
  readonly mach: number;
  /** Dynamic pressure. Unit: Pa. */
  readonly dynamicPressure_Pa: number;
  /** Drag coefficient actually used, after the Mach correction. Dimensionless. */
  readonly effectiveCd: number;
}

/**
 * Position measured from Earth's centre, in ENU axes.
 *
 * A pure translation along +Z. The central gravity field is rotationally
 * symmetric, so it does not care that the axes are the launch site's rather
 * than the equator's.
 */
function earthCentered(position: Vec3, siteRadius_m: number): Vec3 {
  return vec3(position.x, position.y, position.z + siteRadius_m);
}

/**
 * Compute every force acting on the vehicle right now.
 *
 * Pure — RK4 calls this at four substeps per timestep, and any state carried
 * between calls would corrupt the integration.
 *
 * @param inputs - The current instant.
 * @returns Each force, the net acceleration, and the atmospheric quantities
 *   telemetry needs.
 */
export function computeForces(inputs: ForceInputs): ForceResult {
  const r = earthCentered(inputs.position, inputs.siteRadius_m);
  const radius = magnitude(r);
  const altitude_m = radius - R_EARTH;

  // Below the surface only happens inside an RK4 substep that overshoots the
  // ground. Clamping keeps the atmosphere model in range; the impact itself is
  // detected by the runner, not here.
  const atm = atmosphere(Math.max(0, altitude_m));

  const speed = magnitude(inputs.velocity);
  const mach = machNumber(speed, atm);
  const q = dynamicPressure(speed, atm.density_kgm3);

  // --- Gravity ------------------------------------------------------------
  const gravityAccel = gravityAccelerationCentral(r, MU_EARTH);
  const localGravity_ms2 = magnitude(gravityAccel);
  const gravity = scale(gravityAccel, inputs.mass_kg);

  // --- Thrust -------------------------------------------------------------
  // Ambient pressure pushes back on the nozzle exit, so thrust rises with
  // altitude. Without compensation the vacuum rating is used throughout.
  const thrustMagnitude_N =
    inputs.thrustVacuum_N <= 0
      ? 0
      : inputs.useAltitudeCompensation
        ? thrustAtPressure(
            inputs.thrustVacuum_N,
            inputs.thrustSeaLevel_N,
            atm.pressure_Pa,
          )
        : inputs.thrustVacuum_N;
  const thrust = scale(inputs.thrustDirection, thrustMagnitude_N);

  // --- Drag ---------------------------------------------------------------
  const effectiveCd = inputs.useMachDragRise
    ? effectiveDragCoefficient(inputs.dragCoefficient, mach)
    : inputs.dragCoefficient;
  const drag = dragForce(
    inputs.velocity,
    atm.density_kgm3,
    effectiveCd,
    inputs.referenceArea_m2,
  );

  // --- Sum ----------------------------------------------------------------
  const net = add(add(thrust, drag), gravity);
  const acceleration =
    inputs.mass_kg > 0 ? scale(net, 1 / inputs.mass_kg) : vec3(0, 0, 0);

  return {
    thrust,
    drag,
    gravity,
    net,
    acceleration,
    thrustMagnitude_N,
    dragMagnitude_N: magnitude(drag),
    localGravity_ms2,
    atmosphere: atm,
    altitude_m,
    mach,
    dynamicPressure_Pa: q,
    effectiveCd,
  };
}

/**
 * Just the acceleration, for the integrator's inner loop.
 *
 * `computeForces` allocates a dozen objects per call, which at four calls per
 * step and 20 steps per second adds up. This returns only what RK4 needs.
 *
 * @param inputs - The current instant.
 * @returns Net acceleration. Unit: m/s².
 */
export function computeAcceleration(inputs: ForceInputs): Vec3 {
  const r = earthCentered(inputs.position, inputs.siteRadius_m);
  const altitude_m = magnitude(r) - R_EARTH;
  const atm = atmosphere(Math.max(0, altitude_m));

  const gravityAccel = gravityAccelerationCentral(r, MU_EARTH);

  if (inputs.mass_kg <= 0) return gravityAccel;

  const thrustMagnitude_N =
    inputs.thrustVacuum_N <= 0
      ? 0
      : inputs.useAltitudeCompensation
        ? thrustAtPressure(
            inputs.thrustVacuum_N,
            inputs.thrustSeaLevel_N,
            atm.pressure_Pa,
          )
        : inputs.thrustVacuum_N;

  const effectiveCd = inputs.useMachDragRise
    ? effectiveDragCoefficient(
        inputs.dragCoefficient,
        machNumber(magnitude(inputs.velocity), atm),
      )
    : inputs.dragCoefficient;

  const drag = dragForce(
    inputs.velocity,
    atm.density_kgm3,
    effectiveCd,
    inputs.referenceArea_m2,
  );

  const thrustAndDrag = add(
    scale(inputs.thrustDirection, thrustMagnitude_N),
    drag,
  );

  // a = (T + D)/m + g. Gravity is already an acceleration, so it is not divided.
  return add(scale(thrustAndDrag, 1 / inputs.mass_kg), gravityAccel);
}
