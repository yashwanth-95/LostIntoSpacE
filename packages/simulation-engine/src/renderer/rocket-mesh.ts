/**
 * Procedural rocket geometry.
 *
 * Builds a `THREE.Object3D` from a {@link DesignLayout}, so a design is
 * viewable the moment it is assembled — no modelling, no asset pipeline, no
 * waiting for art. Components that declare a `visualAsset` can have a loaded
 * model swapped in later; until then `fallbackProcedural` gives every part a
 * shape derived from its real dimensions.
 *
 * That matters beyond convenience: the mesh is generated from the *same*
 * numbers the physics uses, so what the user sees is what the simulation flies.
 * A component cannot look long and behave short.
 *
 * ## Grouping
 *
 * The returned object has one child group per stage, named `stage-0`,
 * `stage-1`, … Stage separation is then just detaching a group, which is what
 * {@link separateStage} does.
 *
 * @module renderer/rocket-mesh
 */

import * as THREE from 'three';
import type { DesignLayout, ResolvedComponent } from '../core/builder.js';
import type { SceneScale } from './scale.js';
import { toUnits } from './scale.js';

/** How much of a component's length a nose cone tip occupies. */
const NOSE_TIP_RATIO = 1.0;

/** Radial segment count. Enough to read as round without wasting triangles. */
const RADIAL_SEGMENTS = 24;

/** Fallback colour for a component whose definition declares none. */
const DEFAULT_COLOUR = 0xc8ccd4;

/** Options for {@link buildRocketMesh}. */
export interface RocketMeshOptions {
  /** Scale band to build in. */
  readonly scale: SceneScale;
  /**
   * Draw each component in a distinct colour rather than the vehicle's own
   * palette. Useful in the builder, where telling parts apart matters more than
   * looking like a rocket.
   */
  readonly highlightComponents?: boolean;
  /** Render as wireframe, for inspecting geometry. */
  readonly wireframe?: boolean;
}

/** A built rocket, with the handles a renderer needs to animate it. */
export interface RocketMesh {
  /** The root object. Add this to a scene. */
  readonly root: THREE.Group;
  /** One group per stage, indexed by stage number. */
  readonly stageGroups: readonly THREE.Group[];
  /** Every component mesh, by instance id, for picking and highlighting. */
  readonly componentMeshes: ReadonlyMap<string, THREE.Mesh>;
  /** Overall height in scene units. */
  readonly height: number;
  /** Widest diameter in scene units. */
  readonly maxDiameter: number;
  /** Release every geometry and material this mesh owns. */
  readonly dispose: () => void;
}

/** Distinct colours for the component-highlighting mode. */
const HIGHLIGHT_PALETTE = [
  0x4f9de8, 0xe8894f, 0x5fc98a, 0xd45f9e, 0xc9b74f, 0x8a6fd4, 0x4fc9c0,
];

/** Build the geometry for one component from its category and dimensions. */
function buildComponentGeometry(
  component: ResolvedComponent,
  scale: SceneScale,
): THREE.BufferGeometry {
  const radius = toUnits(component.diameter_m / 2, scale);
  const length = toUnits(component.length_m, scale);

  switch (component.category) {
    case 'nose_cone': {
      // A cone is the honest shape for any of the profiles. The ogive/haack
      // curvature is a drag refinement the physics models but the silhouette
      // barely shows at these sizes.
      return new THREE.ConeGeometry(radius, length * NOSE_TIP_RATIO, RADIAL_SEGMENTS);
    }

    case 'engine': {
      // A nozzle: narrow at the throat, flaring to the exit.
      return new THREE.CylinderGeometry(
        radius * 0.45,
        radius,
        length,
        RADIAL_SEGMENTS,
        1,
        true,
      );
    }

    case 'fin': {
      // Fins are flat plates arranged radially — built separately in
      // buildFinSet, since one component means several meshes.
      return new THREE.BoxGeometry(0.01, length, radius);
    }

    case 'parachute':
    case 'heat_shield': {
      return new THREE.CylinderGeometry(radius, radius * 0.9, length, RADIAL_SEGMENTS);
    }

    case 'decoupler': {
      // Slightly proud of the body so the joint is visible.
      return new THREE.CylinderGeometry(radius * 1.04, radius * 1.04, length, RADIAL_SEGMENTS);
    }

    default:
      return new THREE.CylinderGeometry(radius, radius, length, RADIAL_SEGMENTS);
  }
}

/** Build a fin set as several plates arranged around the body. */
function buildFinSet(
  component: ResolvedComponent,
  material: THREE.Material,
  scale: SceneScale,
): THREE.Group {
  const group = new THREE.Group();
  group.name = `fins-${component.instanceId}`;

  const finCount =
    component.def.category === 'fin' ? component.def.finCount : 4;
  const span = toUnits(
    component.def.category === 'fin' ? component.def.span_m : component.diameter_m / 2,
    scale,
  );
  const rootChord = toUnits(
    component.def.category === 'fin' ? component.def.rootChord_m : component.length_m,
    scale,
  );
  const bodyRadius = toUnits(component.diameter_m / 2, scale);

  const geometry = new THREE.BoxGeometry(span, rootChord, span * 0.06);

  for (let i = 0; i < finCount; i++) {
    const angle = (i / finCount) * Math.PI * 2;
    const fin = new THREE.Mesh(geometry, material);
    // Push the plate out from the body surface by half its span.
    fin.position.set(
      Math.cos(angle) * (bodyRadius + span / 2),
      0,
      Math.sin(angle) * (bodyRadius + span / 2),
    );
    fin.rotation.y = -angle;
    group.add(fin);
  }

  return group;
}

/**
 * Build a renderable rocket from a resolved design layout.
 *
 * @param layout - Geometry from `core/builder.ts`.
 * @param options - Scale and display options.
 * @returns The mesh, its stage groups, and a disposer.
 */
export function buildRocketMesh(
  layout: DesignLayout,
  options: RocketMeshOptions,
): RocketMesh {
  const { scale } = options;
  const root = new THREE.Group();
  root.name = 'rocket';

  const geometries: THREE.BufferGeometry[] = [];
  const materials: THREE.Material[] = [];
  const componentMeshes = new Map<string, THREE.Mesh>();

  // One group per stage, so separation is a matter of detaching a group.
  const stageCount = layout.stageLengths_m.length;
  const stageGroups: THREE.Group[] = [];
  for (let i = 0; i < stageCount; i++) {
    const group = new THREE.Group();
    group.name = `stage-${i}`;
    stageGroups.push(group);
    root.add(group);
  }

  layout.components.forEach((component, index) => {
    const colour = options.highlightComponents
      ? HIGHLIGHT_PALETTE[index % HIGHLIGHT_PALETTE.length]!
      : parseColour(component.def.visual.color);

    const material = new THREE.MeshStandardMaterial({
      color: colour,
      metalness: 0.55,
      roughness: 0.45,
      ...(options.wireframe ? { wireframe: true } : {}),
    });
    materials.push(material);

    const target = stageGroups[component.stageIndex] ?? root;

    if (component.category === 'fin') {
      const finSet = buildFinSet(component, material, scale);
      // Fins sit at their own axial position; +Y is up in scene space.
      finSet.position.y = toUnits(component.axialCenter_m, scale);
      finSet.position.x = toUnits(component.radialOffset_x, scale);
      finSet.position.z = toUnits(component.radialOffset_y, scale);
      target.add(finSet);
      return;
    }

    const geometry = buildComponentGeometry(component, scale);
    geometries.push(geometry);

    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = component.instanceId;
    mesh.userData['instanceId'] = component.instanceId;
    mesh.userData['defId'] = component.defId;
    mesh.userData['category'] = component.category;

    // Cylinders and cones are built centred on the origin along +Y, which is
    // exactly the axial centre the layout gives us.
    mesh.position.set(
      toUnits(component.radialOffset_x, scale),
      toUnits(component.axialCenter_m, scale),
      toUnits(component.radialOffset_y, scale),
    );

    target.add(mesh);
    componentMeshes.set(component.instanceId, mesh);
  });

  return {
    root,
    stageGroups,
    componentMeshes,
    height: toUnits(layout.totalLength_m, scale),
    maxDiameter: toUnits(layout.maxDiameter_m, scale),
    dispose: () => {
      for (const g of geometries) g.dispose();
      for (const m of materials) m.dispose();
    },
  };
}

/** Parse a CSS hex colour into a Three.js colour value. */
function parseColour(colour: string | undefined): number {
  if (!colour) return DEFAULT_COLOUR;
  const parsed = Number.parseInt(colour.replace('#', ''), 16);
  return Number.isNaN(parsed) ? DEFAULT_COLOUR : parsed;
}

/**
 * Detach a stage group from the rocket so it can drift away on its own.
 *
 * The group is reparented to `scene` with its world transform preserved, which
 * is what makes a separation look like the stage falling behind rather than
 * teleporting.
 *
 * @param mesh - The rocket to separate a stage from.
 * @param stageIndex - Which stage leaves.
 * @param scene - Where the detached stage goes.
 * @returns The detached group, or null if that stage does not exist or has
 *   already gone.
 */
export function separateStage(
  mesh: RocketMesh,
  stageIndex: number,
  scene: THREE.Object3D,
): THREE.Group | null {
  const group = mesh.stageGroups[stageIndex];
  if (!group || group.parent !== mesh.root) return null;

  // Preserve the world transform across the reparent.
  group.updateWorldMatrix(true, false);
  const worldPosition = new THREE.Vector3();
  const worldQuaternion = new THREE.Quaternion();
  const worldScale = new THREE.Vector3();
  group.matrixWorld.decompose(worldPosition, worldQuaternion, worldScale);

  mesh.root.remove(group);
  scene.add(group);
  group.position.copy(worldPosition);
  group.quaternion.copy(worldQuaternion);
  group.scale.copy(worldScale);

  return group;
}

/**
 * Point a rocket along a direction.
 *
 * The mesh is built along +Y, so this rotates +Y onto the given vector.
 *
 * @param mesh - The rocket to orient.
 * @param direction - Unit vector in **scene** coordinates, Y-up.
 */
export function orientRocket(mesh: RocketMesh, direction: THREE.Vector3): void {
  const up = new THREE.Vector3(0, 1, 0);
  mesh.root.quaternion.setFromUnitVectors(up, direction.clone().normalize());
}
