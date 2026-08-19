/**
 * Camera rig — framing and following.
 *
 * Deliberately not a general-purpose orbit controller. `OrbitControls` from
 * three's examples already does that well, and P1 can attach it to the camera
 * this module returns. What is here instead is the mission-specific behaviour:
 * following a vehicle that climbs six orders of magnitude, and framing a rocket
 * whose size the user just changed.
 *
 * @module renderer/camera-rig
 */

import * as THREE from 'three';
import type { SceneScale } from './scale.js';

/** How the camera behaves. */
export type CameraMode =
  /** Fixed at the launch site, turning to keep the vehicle in view. */
  | 'ground'
  /** Following at a fixed offset, as if flying alongside. */
  | 'chase'
  /** Locked to the vehicle, looking along its velocity vector. */
  | 'onboard'
  /** Framing the whole trajectory. */
  | 'overview'
  /** Framing a static vehicle, for the builder. */
  | 'inspect';

/** Options for {@link createCameraRig}. */
export interface CameraRigOptions {
  /** Scale band, which sets the near and far planes. */
  readonly scale: SceneScale;
  /** Viewport aspect ratio. */
  readonly aspect: number;
  /** Vertical field of view. Unit: degrees. */
  readonly fov?: number;
  /** Starting mode. */
  readonly mode?: CameraMode;
}

/** A camera plus the logic that aims it. */
export interface CameraRig {
  /** The camera. Hand this to the renderer, and to OrbitControls if wanted. */
  readonly camera: THREE.PerspectiveCamera;
  /** Current mode. */
  readonly getMode: () => CameraMode;
  /** Switch mode. */
  readonly setMode: (mode: CameraMode) => void;
  /**
   * Update for this frame.
   *
   * @param target - What to look at, in scene coordinates.
   * @param velocity - Vehicle velocity in scene coordinates, for the modes that
   *   orient along the direction of travel.
   * @param dt - Frame time, for smoothing. Unit: s.
   */
  readonly update: (
    target: THREE.Vector3,
    velocity: THREE.Vector3,
    dt: number,
  ) => void;
  /** Frame an object so it fills the view. */
  readonly frameObject: (object: THREE.Object3D, padding?: number) => void;
  /** Frame a bounding sphere. */
  readonly frameSphere: (centre: THREE.Vector3, radius: number, padding?: number) => void;
  /** Update the projection after a viewport resize. */
  readonly setAspect: (aspect: number) => void;
  /** Distance the chase and ground cameras hold. Scene units. */
  readonly setFollowDistance: (distance: number) => void;
}

/**
 * Smoothing factor for a first-order lag, made frame-rate independent.
 *
 * A naive `lerp(current, target, 0.1)` moves 10 % per *frame*, so the camera
 * behaves differently at 30 fps and 144 fps. This converts a time constant into
 * the right per-frame factor.
 *
 * @param timeConstant_s - Time to close ~63 % of the gap. Unit: s.
 * @param dt - Frame time. Unit: s.
 * @returns The interpolation factor to use this frame.
 */
function smoothingFactor(timeConstant_s: number, dt: number): number {
  if (timeConstant_s <= 0) return 1;
  return 1 - Math.exp(-dt / timeConstant_s);
}

/**
 * Create a camera rig.
 *
 * @param options - Scale, aspect, and starting mode.
 * @returns The camera and its controls.
 */
export function createCameraRig(options: CameraRigOptions): CameraRig {
  const camera = new THREE.PerspectiveCamera(
    options.fov ?? 50,
    options.aspect,
    options.scale.cameraNear,
    options.scale.cameraFar,
  );

  let mode: CameraMode = options.mode ?? 'chase';
  let followDistance = 40;

  // Where the ground camera sits: at the pad, slightly back and to one side.
  const groundPosition = new THREE.Vector3(followDistance, followDistance * 0.15, followDistance);

  const smoothedTarget = new THREE.Vector3();
  let hasTarget = false;

  const desiredPosition = new THREE.Vector3();
  const offset = new THREE.Vector3();

  return {
    camera,

    getMode: () => mode,

    setMode: (next: CameraMode): void => {
      mode = next;
    },

    setAspect: (aspect: number): void => {
      camera.aspect = aspect;
      camera.updateProjectionMatrix();
    },

    setFollowDistance: (distance: number): void => {
      followDistance = Math.max(1e-6, distance);
    },

    update: (target: THREE.Vector3, velocity: THREE.Vector3, dt: number): void => {
      // Smooth the look-at point so a jittering vehicle does not shake the view.
      if (!hasTarget) {
        smoothedTarget.copy(target);
        hasTarget = true;
      } else {
        smoothedTarget.lerp(target, smoothingFactor(0.12, dt));
      }

      switch (mode) {
        case 'ground': {
          // Fixed position, tracking the vehicle.
          camera.position.copy(groundPosition);
          camera.lookAt(smoothedTarget);
          break;
        }

        case 'chase': {
          // Behind and above, along the reverse of the velocity vector. Falls
          // back to a fixed offset while the vehicle is still on the pad.
          if (velocity.lengthSq() > 1e-8) {
            offset.copy(velocity).normalize().multiplyScalar(-followDistance);
            offset.y += followDistance * 0.35;
          } else {
            offset.set(followDistance * 0.7, followDistance * 0.35, followDistance * 0.7);
          }
          desiredPosition.copy(target).add(offset);
          camera.position.lerp(desiredPosition, smoothingFactor(0.25, dt));
          camera.lookAt(smoothedTarget);
          break;
        }

        case 'onboard': {
          // At the vehicle, looking where it is going.
          camera.position.copy(target);
          if (velocity.lengthSq() > 1e-8) {
            offset.copy(velocity).normalize().multiplyScalar(followDistance);
            camera.lookAt(target.clone().add(offset));
          }
          break;
        }

        case 'overview':
        case 'inspect':
          // Framing modes are driven by frameObject/frameSphere and by whatever
          // orbit controls the host has attached, not per frame from here.
          break;
      }
    },

    frameObject: (object: THREE.Object3D, padding = 1.4): void => {
      const box = new THREE.Box3().setFromObject(object);
      if (box.isEmpty()) return;

      const sphere = new THREE.Sphere();
      box.getBoundingSphere(sphere);

      const fovRadians = (camera.fov * Math.PI) / 180;
      const distance = (sphere.radius * padding) / Math.sin(fovRadians / 2);

      const direction = new THREE.Vector3(0.6, 0.35, 1).normalize();
      camera.position.copy(sphere.center).add(direction.multiplyScalar(distance));
      camera.lookAt(sphere.center);
      smoothedTarget.copy(sphere.center);
      hasTarget = true;
    },

    frameSphere: (centre: THREE.Vector3, radius: number, padding = 1.4): void => {
      const fovRadians = (camera.fov * Math.PI) / 180;
      const distance = (radius * padding) / Math.sin(fovRadians / 2);

      const direction = new THREE.Vector3(0.6, 0.35, 1).normalize();
      camera.position.copy(centre).add(direction.multiplyScalar(distance));
      camera.lookAt(centre);
      smoothedTarget.copy(centre);
      hasTarget = true;
    },
  };
}
