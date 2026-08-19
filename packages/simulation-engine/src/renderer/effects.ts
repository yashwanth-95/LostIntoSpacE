/**
 * Engine effects.
 *
 * Deliberately restrained. The brief is explicit that scientific clarity beats
 * spectacle, and an exhaust plume that dwarfs the vehicle actively misleads —
 * students read plume size as thrust. So the plume here is **scaled to the
 * physics**: its length tracks thrust, and its width tracks ambient pressure,
 * which is why a real plume is narrow at sea level and blooms in vacuum.
 *
 * There is no particle system. A cone with an additive material reads correctly,
 * costs one draw call, and cannot drop frames on a laptop.
 *
 * @module renderer/effects
 */

import * as THREE from 'three';
import { P0_SEA_LEVEL } from '../physics/constants.js';
import type { SceneScale } from './scale.js';
import { toUnits } from './scale.js';

/** Options for {@link createExhaustPlume}. */
export interface ExhaustPlumeOptions {
  /** Scale band to build in. */
  readonly scale: SceneScale;
  /** Nozzle exit diameter. Unit: m. */
  readonly nozzleDiameter_m: number;
  /** Plume length at full thrust and sea-level pressure. Unit: m. */
  readonly baseLength_m: number;
  /** Core colour. */
  readonly colour?: number;
}

/** A thrust-driven exhaust plume. */
export interface ExhaustPlume {
  /** The root object. Parent it to the engine's position on the vehicle. */
  readonly root: THREE.Group;
  /**
   * Update the plume for the current flight condition.
   *
   * @param thrustFraction - Thrust as a fraction of the engine's rating, 0–1.
   * @param ambientPressure_Pa - Ambient static pressure. Unit: Pa.
   */
  readonly update: (thrustFraction: number, ambientPressure_Pa: number) => void;
  /** Release the geometries and materials. */
  readonly dispose: () => void;
}

/** How much wider a plume gets in vacuum than at sea level. */
const VACUUM_BLOOM_FACTOR = 2.6;

/**
 * Create an exhaust plume whose shape follows the physics.
 *
 * @param options - Scale, nozzle geometry, and colour.
 * @returns The plume and its update handle.
 */
export function createExhaustPlume(options: ExhaustPlumeOptions): ExhaustPlume {
  const root = new THREE.Group();
  root.name = 'exhaust-plume';

  const radius = toUnits(options.nozzleDiameter_m / 2, options.scale);
  const length = toUnits(options.baseLength_m, options.scale);

  // Two nested cones: a bright core and a cooler, wider shroud. Cheap, and it
  // reads as an exhaust plume far better than a single cone does.
  const coreGeometry = new THREE.ConeGeometry(radius * 0.7, length, 16, 1, true);
  const coreMaterial = new THREE.MeshBasicMaterial({
    color: options.colour ?? 0xffd9a0,
    transparent: true,
    opacity: 0.9,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const core = new THREE.Mesh(coreGeometry, coreMaterial);
  // Cones are built point-up around the origin; the plume points *down* from
  // the nozzle, so it is flipped and pushed below its parent.
  core.rotation.x = Math.PI;
  core.position.y = -length / 2;
  root.add(core);

  const shroudGeometry = new THREE.ConeGeometry(radius * 1.35, length * 1.3, 16, 1, true);
  const shroudMaterial = new THREE.MeshBasicMaterial({
    color: 0xff8a3d,
    transparent: true,
    opacity: 0.28,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const shroud = new THREE.Mesh(shroudGeometry, shroudMaterial);
  shroud.rotation.x = Math.PI;
  shroud.position.y = -length * 0.65;
  root.add(shroud);

  root.visible = false;

  return {
    root,

    update: (thrustFraction: number, ambientPressure_Pa: number): void => {
      const thrust = Math.min(1, Math.max(0, thrustFraction));

      if (thrust <= 0.001) {
        root.visible = false;
        return;
      }
      root.visible = true;

      // Length follows thrust directly — the most legible mapping available.
      const lengthScale = 0.35 + 0.65 * thrust;

      // Width follows ambient pressure. In vacuum the exhaust has nothing
      // holding it in and spreads; at sea level the atmosphere confines it to a
      // narrow column. Getting this backwards is a common visualisation error.
      const pressureRatio = Math.min(
        1,
        Math.max(0, ambientPressure_Pa / P0_SEA_LEVEL),
      );
      const widthScale = 1 + (VACUUM_BLOOM_FACTOR - 1) * (1 - pressureRatio);

      core.scale.set(widthScale, lengthScale, widthScale);
      core.position.y = (-length / 2) * lengthScale;

      shroud.scale.set(widthScale, lengthScale, widthScale);
      shroud.position.y = -length * 0.65 * lengthScale;

      coreMaterial.opacity = 0.55 + 0.35 * thrust;
      shroudMaterial.opacity = 0.14 + 0.18 * thrust;
    },

    dispose: (): void => {
      coreGeometry.dispose();
      coreMaterial.dispose();
      shroudGeometry.dispose();
      shroudMaterial.dispose();
    },
  };
}

/**
 * Create a marker that flags a moment on the trajectory.
 *
 * Used for max-Q, staging, apogee, and failures. A small sprite that always
 * faces the camera, so it stays readable from any angle.
 *
 * @param colour - Marker colour. Convention: blue for milestones, amber for
 *   warnings, red for failures.
 * @param size - Marker size in scene units.
 * @returns The sprite. Release it with `disposeObject`.
 */
export function createEventMarker(colour = 0x4f9de8, size = 0.02): THREE.Sprite {
  const material = new THREE.SpriteMaterial({
    color: colour,
    transparent: true,
    opacity: 0.9,
    depthWrite: false,
  });

  const sprite = new THREE.Sprite(material);
  sprite.scale.set(size, size, 1);
  sprite.name = 'event-marker';
  return sprite;
}

/**
 * Colour convention for event markers, keyed on severity.
 *
 * @param severity - The event's severity.
 * @returns The colour to draw it in.
 */
export function markerColourForSeverity(
  severity: 'info' | 'warning' | 'critical' | 'fatal',
): number {
  switch (severity) {
    case 'info':
      return 0x4f9de8;
    case 'warning':
      return 0xd9a441;
    case 'critical':
      return 0xe0703c;
    case 'fatal':
      return 0xd6453f;
  }
}
