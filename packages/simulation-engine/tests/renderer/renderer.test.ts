/**
 * Renderer tests.
 *
 * Three.js builds and manipulates its scene graph entirely on the CPU; only the
 * final draw needs WebGL. So everything short of `WebGLRenderer` is testable in
 * Node, and that covers the parts most likely to be wrong: unit conversion,
 * axis handedness, geometry placement, and buffer bookkeeping.
 *
 * `createSceneManager` is not tested here — it constructs a `WebGLRenderer`,
 * which needs a real canvas and a GPU context.
 */

import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import {
  SCENE_SCALES,
  toUnits,
  toMetres,
  toSceneVector,
  selectScale,
  earthRadiusInUnits,
} from '../../src/renderer/scale.js';
import {
  buildRocketMesh,
  separateStage,
  orientRocket,
} from '../../src/renderer/rocket-mesh.js';
import {
  createTrajectoryLine,
  createOrbitPath,
  createStaticPath,
  createAltitudeRings,
  disposeObject,
} from '../../src/renderer/trajectory.js';
import {
  createPlanet,
  createGroundPlane,
  createStarfield,
  createLighting,
  EARTH_APPEARANCE,
  MOON_APPEARANCE,
} from '../../src/renderer/planet.js';
import {
  createExhaustPlume,
  createEventMarker,
  markerColourForSeverity,
} from '../../src/renderer/effects.js';
import { createCameraRig } from '../../src/renderer/camera-rig.js';
import { layoutDesign } from '../../src/core/builder.js';
import { orbitalElements } from '../../src/physics/orbital.js';
import { vec3, magnitude } from '../../src/physics/vec3.js';
import { R_EARTH, MU_EARTH, P0_SEA_LEVEL } from '../../src/physics/constants.js';
import {
  stockRegistry,
  soundingRocket,
  orbitalLauncher,
} from '../core/reference-designs.js';

const registry = stockRegistry();
const scale = SCENE_SCALES.launch;

describe('scale conversion', () => {
  it('round-trips a length', () => {
    for (const band of Object.values(SCENE_SCALES)) {
      expect(toMetres(toUnits(12_345, band), band)).toBeCloseTo(12_345, 6);
    }
  });

  it('gives each band a bigger metres-per-unit than the last', () => {
    expect(SCENE_SCALES.vehicle.metresPerUnit).toBeLessThan(SCENE_SCALES.launch.metresPerUnit);
    expect(SCENE_SCALES.launch.metresPerUnit).toBeLessThan(SCENE_SCALES.orbital.metresPerUnit);
    expect(SCENE_SCALES.orbital.metresPerUnit).toBeLessThan(SCENE_SCALES.system.metresPerUnit);
  });

  it('keeps every band within a workable depth-buffer range', () => {
    // A far/near ratio beyond ~1e7 is where 32-bit depth starts z-fighting,
    // and distant geometry begins flickering through nearer geometry.
    for (const band of Object.values(SCENE_SCALES)) {
      expect(band.cameraFar / band.cameraNear, band.band).toBeLessThanOrEqual(1e7);
    }
  });

  it('converts Z-up ENU into Y-up scene coordinates', () => {
    // (east, north, up) → (east, up, −north)
    const [x, y, z] = toSceneVector(vec3(100, 200, 300), SCENE_SCALES.vehicle);
    expect(x).toBe(100);
    expect(y).toBe(300);
    expect(z).toBe(-200);
  });

  it('preserves vector length through the axis swap', () => {
    const v = vec3(300, -400, 1_200);
    const [x, y, z] = toSceneVector(v, SCENE_SCALES.vehicle);
    expect(Math.hypot(x, y, z)).toBeCloseTo(magnitude(v), 6);
  });

  it('picks a band that suits the extent', () => {
    expect(selectScale(50).band).toBe('vehicle');
    expect(selectScale(200_000).band).toBe('launch');
    expect(selectScale(500_000_000).band).toBe('orbital');
    expect(selectScale(1e12).band).toBe('system');
  });

  it('expresses the Earth radius consistently in each band', () => {
    for (const band of Object.values(SCENE_SCALES)) {
      expect(toMetres(earthRadiusInUnits(band), band)).toBeCloseTo(R_EARTH, 3);
    }
  });
});

describe('buildRocketMesh', () => {
  const layout = layoutDesign(orbitalLauncher(registry), registry);
  const mesh = buildRocketMesh(layout, { scale });

  it('creates one group per stage', () => {
    expect(mesh.stageGroups).toHaveLength(layout.stageLengths_m.length);
    expect(mesh.stageGroups.map(g => g.name)).toEqual(['stage-0', 'stage-1']);
  });

  it('parents every stage group to the root', () => {
    for (const group of mesh.stageGroups) {
      expect(group.parent).toBe(mesh.root);
    }
  });

  it('reports height and diameter in scene units', () => {
    expect(mesh.height).toBeCloseTo(toUnits(layout.totalLength_m, scale), 6);
    expect(mesh.maxDiameter).toBeCloseTo(toUnits(layout.maxDiameter_m, scale), 6);
  });

  it('places each component at its layout position', () => {
    for (const component of layout.components) {
      if (component.category === 'fin') continue;
      const mesh3d = mesh.componentMeshes.get(component.instanceId)!;
      expect(mesh3d, component.instanceId).toBeDefined();
      expect(mesh3d.position.y).toBeCloseTo(toUnits(component.axialCenter_m, scale), 6);
    }
  });

  it('puts every component into its own stage group', () => {
    for (const component of layout.components) {
      if (component.category === 'fin') continue;
      const mesh3d = mesh.componentMeshes.get(component.instanceId)!;
      expect(mesh3d.parent!.name).toBe(`stage-${component.stageIndex}`);
    }
  });

  it('tags each mesh with the ids needed for picking', () => {
    for (const [instanceId, mesh3d] of mesh.componentMeshes) {
      expect(mesh3d.userData['instanceId']).toBe(instanceId);
      expect(mesh3d.userData['defId']).toBeTruthy();
      expect(mesh3d.userData['category']).toBeTruthy();
    }
  });

  it('builds a fin set as several plates around the body', () => {
    const finless = buildRocketMesh(
      layoutDesign(soundingRocket(registry), registry),
      { scale },
    );
    const finGroup = finless.root
      .getObjectByName('stage-0')!
      .children.find(c => c.name.startsWith('fins-'));

    expect(finGroup).toBeDefined();
    expect(finGroup!.children.length).toBeGreaterThanOrEqual(3);
    finless.dispose();
  });

  it('spans the full vehicle height', () => {
    const box = new THREE.Box3().setFromObject(mesh.root);
    const height = box.max.y - box.min.y;
    // Within a component's length of the design height.
    expect(height).toBeGreaterThan(mesh.height * 0.8);
    expect(height).toBeLessThan(mesh.height * 1.2);
  });

  it('builds an empty but valid mesh for an empty design', () => {
    const empty = layoutDesign(
      { ...orbitalLauncher(registry), components: [] },
      registry,
    );
    const emptyMesh = buildRocketMesh(empty, { scale });
    expect(emptyMesh.componentMeshes.size).toBe(0);
    expect(emptyMesh.height).toBe(0);
    emptyMesh.dispose();
  });
});

describe('separateStage', () => {
  it('reparents a stage into the scene, preserving its world position', () => {
    const layout = layoutDesign(orbitalLauncher(registry), registry);
    const mesh = buildRocketMesh(layout, { scale });
    const scene = new THREE.Scene();
    scene.add(mesh.root);
    mesh.root.position.set(10, 200, -30);

    const before = new THREE.Vector3();
    mesh.stageGroups[0]!.updateWorldMatrix(true, false);
    mesh.stageGroups[0]!.getWorldPosition(before);

    const detached = separateStage(mesh, 0, scene)!;
    expect(detached.parent).toBe(scene);

    const after = new THREE.Vector3();
    detached.getWorldPosition(after);
    expect(after.distanceTo(before)).toBeLessThan(1e-6);

    mesh.dispose();
  });

  it('returns null for a stage that has already gone', () => {
    const layout = layoutDesign(orbitalLauncher(registry), registry);
    const mesh = buildRocketMesh(layout, { scale });
    const scene = new THREE.Scene();
    scene.add(mesh.root);

    expect(separateStage(mesh, 0, scene)).not.toBeNull();
    expect(separateStage(mesh, 0, scene)).toBeNull();
    expect(separateStage(mesh, 99, scene)).toBeNull();

    mesh.dispose();
  });
});

describe('orientRocket', () => {
  it('points the vehicle along a direction', () => {
    const mesh = buildRocketMesh(layoutDesign(soundingRocket(registry), registry), { scale });

    orientRocket(mesh, new THREE.Vector3(1, 0, 0));
    const nose = new THREE.Vector3(0, 1, 0).applyQuaternion(mesh.root.quaternion);
    expect(nose.x).toBeCloseTo(1, 6);
    expect(nose.y).toBeCloseTo(0, 6);

    mesh.dispose();
  });

  it('leaves a vertical vehicle unrotated', () => {
    const mesh = buildRocketMesh(layoutDesign(soundingRocket(registry), registry), { scale });
    orientRocket(mesh, new THREE.Vector3(0, 1, 0));
    const nose = new THREE.Vector3(0, 1, 0).applyQuaternion(mesh.root.quaternion);
    expect(nose.y).toBeCloseTo(1, 9);
    mesh.dispose();
  });
});

describe('trajectory line', () => {
  it('starts empty', () => {
    const line = createTrajectoryLine({ scale });
    expect(line.count()).toBe(0);
    expect(line.object.geometry.drawRange.count).toBe(0);
    line.dispose();
  });

  it('grows as points are pushed', () => {
    const line = createTrajectoryLine({ scale, capacity: 10 });
    for (let i = 0; i < 5; i++) {
      expect(line.push(vec3(0, 0, i * 100))).toBe(true);
    }
    expect(line.count()).toBe(5);
    expect(line.object.geometry.drawRange.count).toBe(5);
    line.dispose();
  });

  it('refuses to grow past its capacity rather than reallocating', () => {
    const line = createTrajectoryLine({ scale, capacity: 3 });
    expect(line.push(vec3(0, 0, 0))).toBe(true);
    expect(line.push(vec3(0, 0, 1))).toBe(true);
    expect(line.push(vec3(0, 0, 2))).toBe(true);
    expect(line.push(vec3(0, 0, 3))).toBe(false);
    expect(line.count()).toBe(3);
    line.dispose();
  });

  it('writes points in scene coordinates', () => {
    const line = createTrajectoryLine({ scale: SCENE_SCALES.vehicle, capacity: 4 });
    line.push(vec3(10, 20, 30));

    const positions = line.object.geometry.getAttribute('position');
    expect(positions.getX(0)).toBeCloseTo(10, 5);
    expect(positions.getY(0)).toBeCloseTo(30, 5);
    expect(positions.getZ(0)).toBeCloseTo(-20, 5);
    line.dispose();
  });

  it('clears back to empty', () => {
    const line = createTrajectoryLine({ scale, capacity: 10 });
    line.push(vec3(0, 0, 1));
    line.clear();
    expect(line.count()).toBe(0);
    line.dispose();
  });

  it('rebuilds from a telemetry series', () => {
    const line = createTrajectoryLine({ scale, capacity: 100 });
    line.setFromTelemetry([
      { position_x_m: 0, position_y_m: 0, position_z_m: 0 },
      { position_x_m: 100, position_y_m: 0, position_z_m: 500 },
      // Only the position fields are read.
    ] as never);
    expect(line.count()).toBe(2);
    line.dispose();
  });

  it('is exempt from frustum culling, since its bounds change every frame', () => {
    const line = createTrajectoryLine({ scale });
    expect(line.object.frustumCulled).toBe(false);
    line.dispose();
  });
});

describe('orbit path', () => {
  const circular = orbitalElements(
    vec3(R_EARTH + 400_000, 0, 0),
    vec3(0, Math.sqrt(MU_EARTH / (R_EARTH + 400_000)), 0),
  );

  it('is hidden until given elements', () => {
    const path = createOrbitPath({ scale: SCENE_SCALES.orbital });
    expect(path.object.visible).toBe(false);
    path.dispose();
  });

  it('draws a closed orbit', () => {
    const path = createOrbitPath({ scale: SCENE_SCALES.orbital, segments: 64 });
    path.update(circular);

    expect(path.object.visible).toBe(true);
    expect(path.object.geometry.drawRange.count).toBe(65);
    path.dispose();
  });

  it('draws the orbit at the right radius', () => {
    const band = SCENE_SCALES.orbital;
    const path = createOrbitPath({ scale: band, segments: 32 });
    path.update(circular);

    const positions = path.object.geometry.getAttribute('position');
    const radius = Math.hypot(positions.getX(0), positions.getY(0), positions.getZ(0));
    expect(toMetres(radius, band)).toBeCloseTo(R_EARTH + 400_000, -2);
    path.dispose();
  });

  it('hides again when the orbit becomes open', () => {
    const path = createOrbitPath({ scale: SCENE_SCALES.orbital });
    path.update(circular);
    expect(path.object.visible).toBe(true);

    const escape = orbitalElements(
      vec3(R_EARTH + 400_000, 0, 0),
      vec3(0, Math.sqrt((2 * MU_EARTH) / (R_EARTH + 400_000)) * 1.2, 0),
    );
    path.update(escape);
    expect(path.object.visible).toBe(false);
    path.dispose();
  });

  it('hides when given null', () => {
    const path = createOrbitPath({ scale: SCENE_SCALES.orbital });
    path.update(circular);
    path.update(null);
    expect(path.object.visible).toBe(false);
    path.dispose();
  });
});

describe('static geometry helpers', () => {
  it('builds a static path with one vertex per point', () => {
    const line = createStaticPath([vec3(0, 0, 0), vec3(1, 1, 1), vec3(2, 2, 2)], scale);
    expect(line.geometry.getAttribute('position').count).toBe(3);
    disposeObject(line);
  });

  it('builds one ring per requested altitude, tagged with it', () => {
    const rings = createAltitudeRings([10_000, 100_000], 50_000, scale);
    expect(rings.children).toHaveLength(2);
    expect(rings.children[0]!.userData['altitude_m']).toBe(10_000);
    disposeObject(rings);
  });

  it('places each ring at its altitude in scene units', () => {
    const rings = createAltitudeRings([100_000], 50_000, scale);
    const positions = (rings.children[0] as THREE.LineLoop).geometry.getAttribute('position');
    expect(positions.getY(0)).toBeCloseTo(toUnits(100_000, scale), 6);
    disposeObject(rings);
  });
});

describe('planet', () => {
  it('builds a surface sized from the body radius', () => {
    const planet = createPlanet({ scale: SCENE_SCALES.orbital });
    const box = new THREE.Box3().setFromObject(planet.surface);
    const radius = (box.max.x - box.min.x) / 2;
    expect(toMetres(radius, SCENE_SCALES.orbital)).toBeCloseTo(R_EARTH, -4);
    planet.dispose();
  });

  it('adds an atmosphere shell for a body that has one', () => {
    const earth = createPlanet({ scale: SCENE_SCALES.orbital, appearance: EARTH_APPEARANCE });
    expect(earth.atmosphere).not.toBeNull();
    earth.dispose();
  });

  it('omits the atmosphere for an airless body', () => {
    const moon = createPlanet({
      scale: SCENE_SCALES.orbital,
      radius_m: 1_737_000,
      appearance: MOON_APPEARANCE,
    });
    expect(moon.atmosphere).toBeNull();
    moon.dispose();
  });

  it('keeps the atmosphere shell thin, as it really is', () => {
    // 100 km against a 6371 km radius is under 2 %. Drawing it thicker is the
    // most common way space visualisations mislead.
    const earth = createPlanet({ scale: SCENE_SCALES.orbital, appearance: EARTH_APPEARANCE });
    const surfaceBox = new THREE.Box3().setFromObject(earth.surface);
    const atmosphereBox = new THREE.Box3().setFromObject(earth.atmosphere!);

    const ratio = (atmosphereBox.max.x - atmosphereBox.min.x) /
      (surfaceBox.max.x - surfaceBox.min.x);
    expect(ratio).toBeLessThan(1.03);
    earth.dispose();
  });

  it('builds a ground plane with a grid', () => {
    const ground = createGroundPlane(1_000, SCENE_SCALES.vehicle);
    expect(ground.getObjectByName('ground-plane')).toBeDefined();
    expect(ground.getObjectByName('ground-grid')).toBeDefined();
    disposeObject(ground);
  });

  it('builds a starfield with the requested star count', () => {
    const stars = createStarfield(500, 1_000);
    expect(stars.geometry.getAttribute('position').count).toBe(500);
    disposeObject(stars);
  });

  it('places every star on the sphere', () => {
    const radius = 1_000;
    const stars = createStarfield(200, radius);
    const positions = stars.geometry.getAttribute('position');
    for (let i = 0; i < positions.count; i++) {
      expect(
        Math.hypot(positions.getX(i), positions.getY(i), positions.getZ(i)),
      ).toBeCloseTo(radius, 3);
    }
    disposeObject(stars);
  });

  it('builds the same starfield for the same seed', () => {
    const a = createStarfield(100, 1_000, 7);
    const b = createStarfield(100, 1_000, 7);
    const pa = a.geometry.getAttribute('position');
    const pb = b.geometry.getAttribute('position');
    for (let i = 0; i < pa.count; i++) {
      expect(pb.getX(i)).toBe(pa.getX(i));
    }
    disposeObject(a);
    disposeObject(b);
  });

  it('builds a sun and a fill light', () => {
    const lighting = createLighting();
    expect(lighting.getObjectByName('sun')).toBeDefined();
    expect(lighting.getObjectByName('ambient')).toBeDefined();
    expect(lighting.getObjectByName('fill')).toBeDefined();
  });
});

describe('exhaust plume', () => {
  it('is hidden until the engine lights', () => {
    const plume = createExhaustPlume({ scale, nozzleDiameter_m: 1, baseLength_m: 5 });
    expect(plume.root.visible).toBe(false);

    plume.update(0, P0_SEA_LEVEL);
    expect(plume.root.visible).toBe(false);
    plume.dispose();
  });

  it('appears and grows with thrust', () => {
    const plume = createExhaustPlume({ scale, nozzleDiameter_m: 1, baseLength_m: 5 });

    plume.update(0.3, P0_SEA_LEVEL);
    expect(plume.root.visible).toBe(true);
    const small = (plume.root.children[0] as THREE.Mesh).scale.y;

    plume.update(1.0, P0_SEA_LEVEL);
    const large = (plume.root.children[0] as THREE.Mesh).scale.y;

    expect(large).toBeGreaterThan(small);
    plume.dispose();
  });

  it('blooms wider in vacuum than at sea level', () => {
    // With nothing to confine it the exhaust spreads. Getting this backwards is
    // a common visualisation error.
    const plume = createExhaustPlume({ scale, nozzleDiameter_m: 1, baseLength_m: 5 });

    plume.update(1, P0_SEA_LEVEL);
    const atSeaLevel = (plume.root.children[0] as THREE.Mesh).scale.x;

    plume.update(1, 0);
    const inVacuum = (plume.root.children[0] as THREE.Mesh).scale.x;

    expect(inVacuum).toBeGreaterThan(atSeaLevel);
    plume.dispose();
  });

  it('clamps a thrust fraction outside 0–1', () => {
    const plume = createExhaustPlume({ scale, nozzleDiameter_m: 1, baseLength_m: 5 });
    expect(() => plume.update(5, P0_SEA_LEVEL)).not.toThrow();
    expect(() => plume.update(-1, P0_SEA_LEVEL)).not.toThrow();
    plume.dispose();
  });
});

describe('event markers', () => {
  it('builds a sprite at the requested size', () => {
    const marker = createEventMarker(0xff0000, 0.5);
    expect(marker.scale.x).toBe(0.5);
    disposeObject(marker);
  });

  it('gives each severity its own colour', () => {
    const colours = (['info', 'warning', 'critical', 'fatal'] as const).map(
      markerColourForSeverity,
    );
    expect(new Set(colours).size).toBe(4);
  });
});

describe('camera rig', () => {
  it('takes its near and far planes from the scale band', () => {
    const rig = createCameraRig({ scale: SCENE_SCALES.orbital, aspect: 16 / 9 });
    expect(rig.camera.near).toBe(SCENE_SCALES.orbital.cameraNear);
    expect(rig.camera.far).toBe(SCENE_SCALES.orbital.cameraFar);
  });

  it('switches mode', () => {
    const rig = createCameraRig({ scale, aspect: 1 });
    rig.setMode('onboard');
    expect(rig.getMode()).toBe('onboard');
  });

  it('updates the projection on resize', () => {
    const rig = createCameraRig({ scale, aspect: 1 });
    rig.setAspect(2);
    expect(rig.camera.aspect).toBe(2);
  });

  it('frames an object so it fits in view', () => {
    const rig = createCameraRig({ scale: SCENE_SCALES.vehicle, aspect: 1 });
    const mesh = buildRocketMesh(
      layoutDesign(soundingRocket(registry), registry),
      { scale: SCENE_SCALES.vehicle },
    );

    rig.frameObject(mesh.root);
    const box = new THREE.Box3().setFromObject(mesh.root);
    const centre = box.getCenter(new THREE.Vector3());

    // The camera must stand off far enough to see the whole vehicle.
    expect(rig.camera.position.distanceTo(centre)).toBeGreaterThan(mesh.height / 2);
    mesh.dispose();
  });

  it('tolerates framing an empty object', () => {
    const rig = createCameraRig({ scale, aspect: 1 });
    expect(() => rig.frameObject(new THREE.Group())).not.toThrow();
  });

  it('holds a fixed position in ground mode', () => {
    const rig = createCameraRig({ scale, aspect: 1, mode: 'ground' });
    rig.update(new THREE.Vector3(0, 100, 0), new THREE.Vector3(0, 50, 0), 0.016);
    const first = rig.camera.position.clone();

    rig.update(new THREE.Vector3(0, 500, 0), new THREE.Vector3(0, 80, 0), 0.016);
    expect(rig.camera.position.distanceTo(first)).toBeLessThan(1e-9);
  });

  it('follows the target in chase mode', () => {
    const rig = createCameraRig({ scale, aspect: 1, mode: 'chase' });
    rig.update(new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 1, 0), 0.016);
    const start = rig.camera.position.clone();

    for (let i = 0; i < 60; i++) {
      rig.update(new THREE.Vector3(0, 1_000, 0), new THREE.Vector3(0, 100, 0), 0.016);
    }
    expect(rig.camera.position.y).toBeGreaterThan(start.y);
  });

  it('sits at the vehicle in onboard mode', () => {
    const rig = createCameraRig({ scale, aspect: 1, mode: 'onboard' });
    const target = new THREE.Vector3(10, 200, -30);
    rig.update(target, new THREE.Vector3(0, 100, 0), 0.016);
    expect(rig.camera.position.distanceTo(target)).toBeLessThan(1e-9);
  });
});
