/**
 * Scene scaling.
 *
 * Rockets are metres tall and orbits are megametres across. Feeding raw SI
 * metres into a WebGL scene puts the camera's near and far planes six orders of
 * magnitude apart, and 32-bit depth buffers cannot resolve that — the result is
 * z-fighting so severe that a rocket disappears into the planet behind it.
 *
 * The fix is to render in **scene units** rather than metres, with a different
 * scale per view:
 *
 * | View       | Scale                  | Covers                        |
 * |------------|------------------------|-------------------------------|
 * | `vehicle`  | 1 unit = 1 m           | A rocket on the pad           |
 * | `launch`   | 1 unit = 100 m         | Ascent to a few hundred km    |
 * | `orbital`  | 1 unit = 100 km        | Orbits around a planet        |
 * | `system`   | 1 unit = 100 000 km    | Planetary distances           |
 *
 * Every renderer module takes a {@link SceneScale} and converts at the boundary,
 * so no module invents its own factor and the simulation never sees a scene unit.
 *
 * Each band's near and far planes are chosen to keep their ratio at or below
 * 10⁷. Beyond that a 32-bit depth buffer cannot separate surfaces reliably, and
 * distant geometry starts to flicker through nearer geometry.
 *
 * @module renderer/scale
 */

import { R_EARTH } from '../physics/constants.js';
import type { Vec3 } from '../physics/vec3.js';

/** The scale bands the renderer supports. */
export type ScaleBand = 'vehicle' | 'launch' | 'orbital' | 'system';

/** A metres-to-scene-units conversion. */
export interface SceneScale {
  /** Which band this is. */
  readonly band: ScaleBand;
  /** Metres represented by one scene unit. Unit: m/unit. */
  readonly metresPerUnit: number;
  /** Suggested camera near plane, in scene units. */
  readonly cameraNear: number;
  /** Suggested camera far plane, in scene units. */
  readonly cameraFar: number;
}

/** The predefined scale bands. */
export const SCENE_SCALES: Readonly<Record<ScaleBand, SceneScale>> = Object.freeze({
  vehicle: { band: 'vehicle', metresPerUnit: 1, cameraNear: 0.1, cameraFar: 10_000 },
  launch: { band: 'launch', metresPerUnit: 100, cameraNear: 0.1, cameraFar: 200_000 },
  orbital: { band: 'orbital', metresPerUnit: 100_000, cameraNear: 0.01, cameraFar: 100_000 },
  system: { band: 'system', metresPerUnit: 100_000_000, cameraNear: 0.01, cameraFar: 100_000 },
});

/** Earth's radius expressed in each band's scene units. */
export function earthRadiusInUnits(scale: SceneScale): number {
  return R_EARTH / scale.metresPerUnit;
}

/**
 * Convert a length from metres to scene units.
 *
 * @param metres - Length in metres.
 * @param scale - Scale band to convert into.
 * @returns The length in scene units.
 */
export function toUnits(metres: number, scale: SceneScale): number {
  return metres / scale.metresPerUnit;
}

/**
 * Convert a length from scene units back to metres.
 *
 * @param units - Length in scene units.
 * @param scale - Scale band it is expressed in.
 * @returns The length in metres.
 */
export function toMetres(units: number, scale: SceneScale): number {
  return units * scale.metresPerUnit;
}

/**
 * Convert a simulation position vector into scene coordinates.
 *
 * Also swaps the axis convention: the simulation uses **Z-up** ENU, while
 * Three.js and most 3D content pipelines use **Y-up**. The mapping is
 * `(east, north, up) → (east, up, −north)`, which is a right-handed rotation
 * that leaves east alone and sends "up" to +Y.
 *
 * @param v - Position or direction in the simulation's ENU frame. Unit: m.
 * @param scale - Scale band to convert into.
 * @returns `[x, y, z]` in scene units, Y-up.
 */
export function toSceneVector(
  v: Vec3,
  scale: SceneScale,
): [x: number, y: number, z: number] {
  const k = 1 / scale.metresPerUnit;
  return [v.x * k, v.z * k, -v.y * k];
}

/**
 * Pick the scale band that suits a given extent.
 *
 * @param extent_m - The largest distance the view has to show. Unit: m.
 * @returns The tightest band that still fits it comfortably.
 */
export function selectScale(extent_m: number): SceneScale {
  if (extent_m <= 500) return SCENE_SCALES.vehicle;
  if (extent_m <= 2_000_000) return SCENE_SCALES.launch;
  if (extent_m <= 2_000_000_000) return SCENE_SCALES.orbital;
  return SCENE_SCALES.system;
}
