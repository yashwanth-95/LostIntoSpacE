/**
 * Scene manager — the imperative renderer P1 mounts.
 *
 * This is the top of the renderer layer and the piece the React adapter drives.
 * It owns a Three.js scene, a camera rig, a rocket, a planet, and a trajectory,
 * and it exposes exactly two verbs: `syncState` to push new simulation data in,
 * and `render` to draw a frame.
 *
 * ## Why it is imperative
 *
 * The simulation ticks 20 times a second. Routing that through React state
 * would re-render the component tree 20 times a second for a change no DOM node
 * cares about. Instead the adapter calls `syncState` from inside
 * `requestAnimationFrame` and React never learns a frame happened. This is the
 * single decision that keeps the viewport smooth, and it is why the renderer
 * has no React dependency at all.
 *
 * ## Lifecycle
 *
 * ```
 * const manager = createSceneManager({ canvas, ... });
 * manager.setRocket(layout);
 * // per frame:
 * manager.syncState(simulation.getState());
 * manager.render(dt);
 * // on unmount:
 * manager.dispose();
 * ```
 *
 * `dispose` is not optional. Three.js holds GPU buffers that garbage collection
 * does not free.
 *
 * @module renderer/scene-manager
 */

import * as THREE from 'three';
import { R_EARTH } from '../physics/constants.js';
import type { DesignLayout } from '../core/builder.js';
import type { SimulationState } from '../sim/state.js';
import type { SceneScale, ScaleBand } from './scale.js';
import { SCENE_SCALES, toSceneVector, toUnits } from './scale.js';
import {
  buildRocketMesh,
  separateStage,
  orientRocket,
  type RocketMesh,
} from './rocket-mesh.js';
import {
  createTrajectoryLine,
  createOrbitPath,
  disposeObject,
  type TrajectoryLine,
  type OrbitPath,
} from './trajectory.js';
import {
  createPlanet,
  createGroundPlane,
  createStarfield,
  createLighting,
  EARTH_APPEARANCE,
  type Planet,
} from './planet.js';
import { createExhaustPlume, type ExhaustPlume } from './effects.js';
import { createCameraRig, type CameraRig, type CameraMode } from './camera-rig.js';

/** Options for {@link createSceneManager}. */
export interface SceneManagerOptions {
  /** Canvas to render into. */
  readonly canvas: HTMLCanvasElement;
  /** Scale band. Defaults to `'launch'`. */
  readonly scaleBand?: ScaleBand;
  /** Starting camera mode. */
  readonly cameraMode?: CameraMode;
  /** Whether to draw the planet. Off for a builder view. */
  readonly showPlanet?: boolean;
  /** Whether to draw a flat ground plane and grid. */
  readonly showGround?: boolean;
  /** Whether to draw stars. */
  readonly showStars?: boolean;
  /** Whether to draw the flown trajectory. */
  readonly showTrajectory?: boolean;
  /** Whether to draw the predicted orbit. */
  readonly showOrbitPath?: boolean;
  /** Background colour. */
  readonly backgroundColour?: number;
  /**
   * Device pixel ratio cap.
   *
   * Uncapped, a 3× display renders nine times the pixels for a difference
   * almost nobody can see, and it is the most common cause of a "slow" WebGL
   * view on a laptop.
   */
  readonly maxPixelRatio?: number;
}

/** The mounted renderer. */
export interface SceneManager {
  /** The Three.js scene, for callers that want to add their own objects. */
  readonly scene: THREE.Scene;
  /** The camera rig. Attach OrbitControls to `rig.camera` if wanted. */
  readonly rig: CameraRig;
  /** The WebGL renderer. */
  readonly renderer: THREE.WebGLRenderer;

  /** Build or rebuild the rocket from a design layout. */
  readonly setRocket: (layout: DesignLayout) => void;
  /** Push the latest simulation state in. Call once per frame. */
  readonly syncState: (state: SimulationState) => void;
  /** Draw a frame. @param dt - Time since the previous frame. Unit: s. */
  readonly render: (dt: number) => void;
  /** Resize the viewport. */
  readonly resize: (width: number, height: number) => void;
  /** Switch camera mode. */
  readonly setCameraMode: (mode: CameraMode) => void;
  /** Frame the whole rocket, for the builder view. */
  readonly frameRocket: () => void;
  /** Clear the trajectory, for a simulation reset. */
  readonly clearTrajectory: () => void;
  /** Release every GPU resource. Required on unmount. */
  readonly dispose: () => void;
}

/**
 * Create and mount a scene.
 *
 * @param options - Canvas and display options.
 * @returns The manager.
 */
export function createSceneManager(options: SceneManagerOptions): SceneManager {
  const scale: SceneScale = SCENE_SCALES[options.scaleBand ?? 'launch'];

  const renderer = new THREE.WebGLRenderer({
    canvas: options.canvas,
    antialias: true,
    // The scene is drawn fresh every frame, so preserving it costs memory
    // bandwidth for nothing.
    preserveDrawingBuffer: false,
  });
  renderer.setPixelRatio(
    Math.min(
      options.maxPixelRatio ?? 2,
      typeof globalThis.devicePixelRatio === 'number' ? globalThis.devicePixelRatio : 1,
    ),
  );

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(options.backgroundColour ?? 0x05070c);

  const rig = createCameraRig({
    scale,
    aspect: options.canvas.width / Math.max(1, options.canvas.height),
    ...(options.cameraMode ? { mode: options.cameraMode } : {}),
  });

  // --- Static scenery -----------------------------------------------------
  const lighting = createLighting();
  scene.add(lighting);

  let starfield: THREE.Points | null = null;
  if (options.showStars ?? true) {
    starfield = createStarfield(3_000, scale.cameraFar * 0.9);
    scene.add(starfield);
  }

  let planet: Planet | null = null;
  if (options.showPlanet ?? true) {
    planet = createPlanet({ scale, appearance: EARTH_APPEARANCE });
    // The scene origin is the launch pad, so the planet centre sits one radius
    // below it. Everything the simulation reports is relative to that origin.
    planet.root.position.y = -toUnits(R_EARTH, scale);
    scene.add(planet.root);
  }

  let ground: THREE.Group | null = null;
  if (options.showGround ?? true) {
    ground = createGroundPlane(scale.metresPerUnit * 400, scale);
    scene.add(ground);
  }

  // --- Dynamic objects ----------------------------------------------------
  let trajectory: TrajectoryLine | null = null;
  if (options.showTrajectory ?? true) {
    trajectory = createTrajectoryLine({ scale });
    scene.add(trajectory.object);
  }

  let orbitPath: OrbitPath | null = null;
  if (options.showOrbitPath ?? true) {
    orbitPath = createOrbitPath({ scale });
    // Orbit elements are Earth-centred, so the path shares the planet's origin.
    orbitPath.object.position.y = -toUnits(R_EARTH, scale);
    scene.add(orbitPath.object);
  }

  let rocket: RocketMesh | null = null;
  let plume: ExhaustPlume | null = null;
  const separatedStages = new Set<number>();

  // Scratch vectors, reused each frame so the render loop allocates nothing.
  const scratchPosition = new THREE.Vector3();
  const scratchVelocity = new THREE.Vector3();
  const scratchDirection = new THREE.Vector3();

  let lastTrajectoryTime = -Infinity;

  const disposeRocket = (): void => {
    if (!rocket) return;
    // Stages already detached live directly under the scene.
    for (const group of rocket.stageGroups) {
      group.removeFromParent();
      disposeObject(group);
    }
    rocket.root.removeFromParent();
    rocket.dispose();
    rocket = null;
    plume?.dispose();
    plume = null;
    separatedStages.clear();
  };

  return {
    scene,
    rig,
    renderer,

    setRocket: (layout: DesignLayout): void => {
      disposeRocket();

      rocket = buildRocketMesh(layout, { scale });
      scene.add(rocket.root);

      // One plume at the base of the stack, sized from the widest engine.
      const engine = layout.components.find(c => c.category === 'engine');
      if (engine) {
        plume = createExhaustPlume({
          scale,
          nozzleDiameter_m: engine.diameter_m,
          baseLength_m: engine.length_m * 3.5,
        });
        rocket.root.add(plume.root);
      }
    },

    syncState: (state: SimulationState): void => {
      if (!rocket) return;

      const [x, y, z] = toSceneVector(state.vehicle.position, scale);
      rocket.root.position.set(x, y, z);

      // Point the vehicle along its commanded attitude. The mesh is built along
      // +Y, and scene space is Y-up, so the ENU thrust direction converts the
      // same way any other vector does.
      const { pitch_rad, yaw_rad } = state.vehicle.attitude;
      const horizontal = Math.cos(pitch_rad);
      scratchDirection.set(
        horizontal * Math.sin(yaw_rad),
        Math.sin(pitch_rad),
        -horizontal * Math.cos(yaw_rad),
      );
      orientRocket(rocket, scratchDirection);

      // Stage separation: detach any group whose stage has gone.
      for (const stageState of state.vehicle.stages) {
        if (stageState.status === 'separated' && !separatedStages.has(stageState.index)) {
          separatedStages.add(stageState.index);
          separateStage(rocket, stageState.index, scene);
        }
      }

      // Exhaust plume, driven by the actual thrust and ambient pressure.
      if (plume) {
        const t = state.telemetry;
        // Normalised against the vehicle's own weight on the pad, so the plume
        // is a sensible size for any size of rocket.
        const reference_N = Math.max(1, t.mass_kg * 9.80665 * 2);
        plume.update(t.thrust_N / reference_N, t.ambientPressure_Pa);
      }

      // Trajectory: one point per telemetry sample, not per frame.
      if (trajectory && state.telemetry.t > lastTrajectoryTime) {
        lastTrajectoryTime = state.telemetry.t;
        trajectory.push(state.vehicle.position);
      }

      orbitPath?.update(state.orbit);

      // Feed the camera the vehicle's position and velocity in scene space.
      scratchPosition.set(x, y, z);
      const [vx, vy, vz] = toSceneVector(state.vehicle.velocity, scale);
      scratchVelocity.set(vx, vy, vz);
    },

    render: (dt: number): void => {
      rig.update(scratchPosition, scratchVelocity, dt);
      renderer.render(scene, rig.camera);
    },

    resize: (width: number, height: number): void => {
      renderer.setSize(width, height, false);
      rig.setAspect(width / Math.max(1, height));
    },

    setCameraMode: (mode: CameraMode): void => {
      rig.setMode(mode);
    },

    frameRocket: (): void => {
      if (rocket) rig.frameObject(rocket.root);
    },

    clearTrajectory: (): void => {
      trajectory?.clear();
      lastTrajectoryTime = -Infinity;
      // Bring any detached stages back under the rocket for a fresh run.
      if (rocket) {
        for (const index of separatedStages) {
          const group = rocket.stageGroups[index];
          if (group) {
            group.removeFromParent();
            group.position.set(0, 0, 0);
            group.quaternion.identity();
            rocket.root.add(group);
          }
        }
        separatedStages.clear();
      }
    },

    dispose: (): void => {
      disposeRocket();
      trajectory?.dispose();
      orbitPath?.dispose();
      planet?.dispose();
      if (ground) disposeObject(ground);
      if (starfield) disposeObject(starfield);
      renderer.dispose();
    },
  };
}
