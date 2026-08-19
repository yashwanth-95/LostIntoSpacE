/**
 * Trajectory and orbit path rendering.
 *
 * Two different things get drawn here and they are worth separating:
 *
 * - **Trajectory** — where the vehicle *has been*, built from telemetry. It
 *   grows as the flight proceeds.
 * - **Orbit path** — where the vehicle *would go* if it coasted from here,
 *   built from the osculating elements. It is a prediction, and it changes
 *   every time the engines fire.
 *
 * Drawing them in the same colour would be misleading, so they default to
 * different ones.
 *
 * ## Why the buffer is preallocated
 *
 * A growing trail could rebuild its geometry each frame, but that allocates and
 * uploads a new buffer every time. Instead the line owns a fixed-capacity
 * buffer and only its draw range advances — one small `needsUpdate` per frame
 * and no allocation at all. That is what keeps a 10 000-point ascent trail from
 * costing anything measurable.
 *
 * @module renderer/trajectory
 */

import * as THREE from 'three';
import type { Vec3 } from '../physics/vec3.js';
import type { OrbitalElements } from '../physics/orbital.js';
import { sampleOrbitPath } from '../physics/orbital.js';
import type { TelemetryPoint } from '../sim/telemetry.js';
import type { SceneScale } from './scale.js';
import { toSceneVector, toUnits } from './scale.js';

/** Default colour for the flown trajectory. */
const TRAJECTORY_COLOUR = 0x4f9de8;
/** Default colour for the predicted orbit, deliberately distinct. */
const ORBIT_COLOUR = 0x8a7fd4;

/** Options for {@link createTrajectoryLine}. */
export interface TrajectoryLineOptions {
  /** Scale band to draw in. */
  readonly scale: SceneScale;
  /** Maximum points the trail can hold. */
  readonly capacity?: number;
  /** Line colour. */
  readonly colour?: number;
  /** Line opacity, 0–1. */
  readonly opacity?: number;
}

/** A growable polyline for the flown trajectory. */
export interface TrajectoryLine {
  /** The renderable object. Add this to a scene. */
  readonly object: THREE.Line;
  /** Append one point, in simulation ENU metres. Returns false when full. */
  readonly push: (position: Vec3) => boolean;
  /** Replace the whole trail from a telemetry series. */
  readonly setFromTelemetry: (points: readonly TelemetryPoint[]) => void;
  /** Empty the trail. */
  readonly clear: () => void;
  /** How many points are currently drawn. */
  readonly count: () => number;
  /** Release the geometry and material. */
  readonly dispose: () => void;
}

/**
 * Create a preallocated trajectory line.
 *
 * @param options - Scale, capacity, and appearance.
 * @returns The line and the handles to grow it.
 */
export function createTrajectoryLine(
  options: TrajectoryLineOptions,
): TrajectoryLine {
  const capacity = options.capacity ?? 20_000;
  const positions = new Float32Array(capacity * 3);

  const geometry = new THREE.BufferGeometry();
  const attribute = new THREE.BufferAttribute(positions, 3);
  attribute.setUsage(THREE.DynamicDrawUsage);
  geometry.setAttribute('position', attribute);
  geometry.setDrawRange(0, 0);

  const material = new THREE.LineBasicMaterial({
    color: options.colour ?? TRAJECTORY_COLOUR,
    transparent: (options.opacity ?? 1) < 1,
    opacity: options.opacity ?? 1,
  });

  const object = new THREE.Line(geometry, material);
  object.name = 'trajectory';
  // The trail is often far larger than the camera frustum test expects, and
  // recomputing its bounding sphere every frame is not worth the cost.
  object.frustumCulled = false;

  let count = 0;

  const writePoint = (index: number, position: Vec3): void => {
    const [x, y, z] = toSceneVector(position, options.scale);
    positions[index * 3] = x;
    positions[index * 3 + 1] = y;
    positions[index * 3 + 2] = z;
  };

  return {
    object,

    push: (position: Vec3): boolean => {
      if (count >= capacity) return false;
      writePoint(count, position);
      count++;
      geometry.setDrawRange(0, count);
      attribute.needsUpdate = true;
      return true;
    },

    setFromTelemetry: (points: readonly TelemetryPoint[]): void => {
      const n = Math.min(points.length, capacity);
      for (let i = 0; i < n; i++) {
        const p = points[i]!;
        writePoint(i, { x: p.position_x_m, y: p.position_y_m, z: p.position_z_m });
      }
      count = n;
      geometry.setDrawRange(0, count);
      attribute.needsUpdate = true;
      geometry.computeBoundingSphere();
    },

    clear: (): void => {
      count = 0;
      geometry.setDrawRange(0, 0);
      attribute.needsUpdate = true;
    },

    count: () => count,

    dispose: (): void => {
      geometry.dispose();
      material.dispose();
    },
  };
}

/** Options for {@link createOrbitPath}. */
export interface OrbitPathOptions {
  /** Scale band to draw in. */
  readonly scale: SceneScale;
  /** Points around the ellipse. More is smoother. */
  readonly segments?: number;
  /** Line colour. */
  readonly colour?: number;
  /** Line opacity, 0–1. */
  readonly opacity?: number;
}

/** A closed ellipse showing the orbit a state vector implies. */
export interface OrbitPath {
  /** The renderable object. Add this to a scene. */
  readonly object: THREE.LineLoop;
  /**
   * Redraw for a new set of elements. Passing null, or elements describing an
   * open trajectory, hides the path — there is no closed curve to show.
   */
  readonly update: (elements: OrbitalElements | null) => void;
  /** Release the geometry and material. */
  readonly dispose: () => void;
}

/**
 * Create an orbit path that can be re-pointed at new elements.
 *
 * The path is drawn in the **Earth-centred** frame the elements were computed
 * in, so the caller must position its parent object at the planet's centre.
 *
 * @param options - Scale, resolution, and appearance.
 * @returns The path and its update handle.
 */
export function createOrbitPath(options: OrbitPathOptions): OrbitPath {
  const segments = options.segments ?? 180;
  // sampleOrbitPath returns segments + 1 points; the LineLoop closes the last
  // back to the first itself, so the buffer is sized for the samples it gives.
  const positions = new Float32Array((segments + 1) * 3);

  const geometry = new THREE.BufferGeometry();
  const attribute = new THREE.BufferAttribute(positions, 3);
  attribute.setUsage(THREE.DynamicDrawUsage);
  geometry.setAttribute('position', attribute);
  geometry.setDrawRange(0, 0);

  const material = new THREE.LineBasicMaterial({
    color: options.colour ?? ORBIT_COLOUR,
    transparent: true,
    opacity: options.opacity ?? 0.6,
  });

  const object = new THREE.LineLoop(geometry, material);
  object.name = 'orbit-path';
  object.frustumCulled = false;
  object.visible = false;

  return {
    object,

    update: (elements: OrbitalElements | null): void => {
      if (!elements) {
        object.visible = false;
        geometry.setDrawRange(0, 0);
        return;
      }

      const points = sampleOrbitPath(elements, segments);
      if (points.length === 0) {
        // Hyperbolic or parabolic: no closed path exists to draw.
        object.visible = false;
        geometry.setDrawRange(0, 0);
        return;
      }

      const n = Math.min(points.length, segments + 1);
      for (let i = 0; i < n; i++) {
        const p = points[i]!;
        const [x, y, z] = toSceneVector(p, options.scale);
        positions[i * 3] = x;
        positions[i * 3 + 1] = y;
        positions[i * 3 + 2] = z;
      }

      geometry.setDrawRange(0, n);
      attribute.needsUpdate = true;
      geometry.computeBoundingSphere();
      object.visible = true;
    },

    dispose: (): void => {
      geometry.dispose();
      material.dispose();
    },
  };
}

/**
 * Build a static line through a list of positions.
 *
 * For paths that will not change — a planned trajectory, a ground track, a
 * comparison run loaded from the backend.
 *
 * @param points - Positions in simulation ENU metres.
 * @param scale - Scale band to draw in.
 * @param colour - Line colour.
 * @returns The line. Dispose its geometry and material when done with it.
 */
export function createStaticPath(
  points: readonly Vec3[],
  scale: SceneScale,
  colour = TRAJECTORY_COLOUR,
): THREE.Line {
  const positions = new Float32Array(points.length * 3);
  points.forEach((p, i) => {
    const [x, y, z] = toSceneVector(p, scale);
    positions[i * 3] = x;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = z;
  });

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

  return new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: colour }));
}

/**
 * Build an altitude reference grid: concentric rings at fixed altitudes.
 *
 * A trajectory alone gives no sense of scale. Rings at 10 km, 100 km, and the
 * Kármán line turn "it went up a lot" into a readable measurement.
 *
 * @param altitudes_m - Altitudes to draw rings at. Unit: m.
 * @param radius_m - Radius of each ring. Unit: m.
 * @param scale - Scale band to draw in.
 * @param colour - Ring colour.
 * @returns A group of rings. Dispose via {@link disposeObject}.
 */
export function createAltitudeRings(
  altitudes_m: readonly number[],
  radius_m: number,
  scale: SceneScale,
  colour = 0x3a4454,
): THREE.Group {
  const group = new THREE.Group();
  group.name = 'altitude-rings';

  const material = new THREE.LineBasicMaterial({
    color: colour,
    transparent: true,
    opacity: 0.35,
  });

  for (const altitude of altitudes_m) {
    const radius = toUnits(radius_m, scale);
    const segments = 96;
    const positions = new Float32Array(segments * 3);

    for (let i = 0; i < segments; i++) {
      const angle = (i / segments) * Math.PI * 2;
      positions[i * 3] = Math.cos(angle) * radius;
      positions[i * 3 + 1] = toUnits(altitude, scale);
      positions[i * 3 + 2] = Math.sin(angle) * radius;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const ring = new THREE.LineLoop(geometry, material);
    ring.name = `altitude-ring-${altitude}`;
    ring.userData['altitude_m'] = altitude;
    group.add(ring);
  }

  return group;
}

/**
 * Recursively dispose every geometry and material under an object.
 *
 * Three.js does not free GPU resources on garbage collection, so anything the
 * renderer creates has to be released explicitly or the buffers leak for the
 * lifetime of the page.
 *
 * @param object - Root of the subtree to release.
 */
export function disposeObject(object: THREE.Object3D): void {
  object.traverse(child => {
    const mesh = child as Partial<THREE.Mesh>;
    if (mesh.geometry) mesh.geometry.dispose();
    if (mesh.material) {
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const material of materials) material.dispose();
    }
  });
}
