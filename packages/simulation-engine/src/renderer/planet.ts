/**
 * Planetary bodies, the ground plane, and scene lighting.
 *
 * Procedural, like the rocket geometry: a sphere sized from the body's real
 * radius, shaded well enough to read as a planet without any texture assets.
 * A `map` can be assigned to the returned material later if P1 supplies one.
 *
 * @module renderer/planet
 */

import * as THREE from 'three';
import { R_EARTH } from '../physics/constants.js';
import type { SceneScale } from './scale.js';
import { toUnits } from './scale.js';

/** How a body should look. */
export interface PlanetAppearance {
  /** Surface colour. */
  readonly surfaceColour: number;
  /** Atmosphere glow colour. */
  readonly atmosphereColour: number;
  /** Whether to draw an atmosphere shell. */
  readonly hasAtmosphere: boolean;
  /** Atmosphere shell thickness. Unit: m. */
  readonly atmosphereThickness_m: number;
}

/** Earth's default appearance. */
export const EARTH_APPEARANCE: PlanetAppearance = {
  surfaceColour: 0x1f4f7a,
  atmosphereColour: 0x5fa8e0,
  hasAtmosphere: true,
  // Thin on purpose: the atmosphere is 100 km against a 6371 km radius, and
  // drawing it thicker is the single most common way space visualisations
  // mislead people about how little of it there is.
  atmosphereThickness_m: 100_000,
} as const;

/** The Moon's default appearance. */
export const MOON_APPEARANCE: PlanetAppearance = {
  surfaceColour: 0x8a8578,
  atmosphereColour: 0x000000,
  hasAtmosphere: false,
  atmosphereThickness_m: 0,
} as const;

/** Mars's default appearance. */
export const MARS_APPEARANCE: PlanetAppearance = {
  surfaceColour: 0xa8522f,
  atmosphereColour: 0xd4a07a,
  hasAtmosphere: true,
  atmosphereThickness_m: 60_000,
} as const;

/** Options for {@link createPlanet}. */
export interface PlanetOptions {
  /** Body radius. Unit: m. Defaults to Earth's. */
  readonly radius_m?: number;
  /** Scale band to build in. */
  readonly scale: SceneScale;
  /** Appearance. Defaults to Earth's. */
  readonly appearance?: PlanetAppearance;
  /**
   * Sphere subdivision. 64 reads as smooth at any sensible zoom; raise it only
   * if the planet fills the viewport.
   */
  readonly segments?: number;
}

/** A rendered planetary body. */
export interface Planet {
  /** The root object. Add this to a scene. */
  readonly root: THREE.Group;
  /** The surface mesh, so a texture can be assigned to its material later. */
  readonly surface: THREE.Mesh;
  /** The atmosphere shell, or null when the body has none. */
  readonly atmosphere: THREE.Mesh | null;
  /** Release the geometries and materials. */
  readonly dispose: () => void;
}

/**
 * Build a planetary body.
 *
 * The body is centred on its own origin, so the caller positions it — for a
 * launch-centred scene that means placing it one planet radius below the pad.
 *
 * @param options - Radius, scale, and appearance.
 * @returns The planet and a disposer.
 */
export function createPlanet(options: PlanetOptions): Planet {
  const radius_m = options.radius_m ?? R_EARTH;
  const appearance = options.appearance ?? EARTH_APPEARANCE;
  const segments = options.segments ?? 64;
  const radius = toUnits(radius_m, options.scale);

  const root = new THREE.Group();
  root.name = 'planet';

  const surfaceGeometry = new THREE.SphereGeometry(radius, segments, segments / 2);
  const surfaceMaterial = new THREE.MeshStandardMaterial({
    color: appearance.surfaceColour,
    roughness: 0.95,
    metalness: 0.0,
  });
  const surface = new THREE.Mesh(surfaceGeometry, surfaceMaterial);
  surface.name = 'planet-surface';
  root.add(surface);

  let atmosphere: THREE.Mesh | null = null;
  let atmosphereGeometry: THREE.SphereGeometry | null = null;
  let atmosphereMaterial: THREE.Material | null = null;

  if (appearance.hasAtmosphere && appearance.atmosphereThickness_m > 0) {
    atmosphereGeometry = new THREE.SphereGeometry(
      toUnits(radius_m + appearance.atmosphereThickness_m, options.scale),
      segments,
      segments / 2,
    );
    // Back-face rendering plus additive blending gives a limb glow that reads
    // as atmosphere from outside without hiding anything inside it.
    atmosphereMaterial = new THREE.MeshBasicMaterial({
      color: appearance.atmosphereColour,
      transparent: true,
      opacity: 0.16,
      side: THREE.BackSide,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    atmosphere = new THREE.Mesh(atmosphereGeometry, atmosphereMaterial);
    atmosphere.name = 'planet-atmosphere';
    root.add(atmosphere);
  }

  return {
    root,
    surface,
    atmosphere,
    dispose: () => {
      surfaceGeometry.dispose();
      surfaceMaterial.dispose();
      atmosphereGeometry?.dispose();
      atmosphereMaterial?.dispose();
    },
  };
}

/**
 * Build a flat ground plane with a reference grid, for launch-site views.
 *
 * At vehicle and launch scale the planet's curvature is invisible, so a plane
 * is both cheaper and easier to read than a sphere. The grid gives the eye
 * something to judge height and speed against.
 *
 * @param extent_m - Half-width of the plane. Unit: m.
 * @param scale - Scale band to build in.
 * @param divisions - Grid divisions across the full width.
 * @returns The ground group. Release it with `disposeObject`.
 */
export function createGroundPlane(
  extent_m: number,
  scale: SceneScale,
  divisions = 40,
): THREE.Group {
  const group = new THREE.Group();
  group.name = 'ground';

  const size = toUnits(extent_m * 2, scale);

  const planeGeometry = new THREE.PlaneGeometry(size, size);
  const planeMaterial = new THREE.MeshStandardMaterial({
    color: 0x1a2029,
    roughness: 1,
    metalness: 0,
  });
  const plane = new THREE.Mesh(planeGeometry, planeMaterial);
  plane.rotation.x = -Math.PI / 2;
  // Just below the grid, so the grid lines are never z-fought by the plane.
  plane.position.y = -size * 1e-4;
  plane.name = 'ground-plane';
  group.add(plane);

  const grid = new THREE.GridHelper(size, divisions, 0x3a4454, 0x262d38);
  grid.name = 'ground-grid';
  group.add(grid);

  return group;
}

/**
 * Build a starfield as a single points cloud.
 *
 * One draw call for the whole sky. The stars sit on a sphere far outside the
 * scene and never move, so this costs essentially nothing per frame.
 *
 * @param count - Number of stars.
 * @param radius - Sphere radius in **scene units**, not metres. Put it just
 *   inside the camera's far plane.
 * @param seed - Seed for the star positions, so a scene looks the same every
 *   time it is built.
 * @returns The starfield. Release it with `disposeObject`.
 */
export function createStarfield(count = 3_000, radius = 9_000, seed = 42): THREE.Points {
  const positions = new Float32Array(count * 3);

  // Deterministic placement: a scene that rebuilds should not reshuffle the sky.
  let state = seed >>> 0;
  const random = (): number => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };

  for (let i = 0; i < count; i++) {
    // Uniform on a sphere: latitude from acos of a uniform, not from a uniform
    // angle, or the stars bunch at the poles.
    const theta = random() * Math.PI * 2;
    const phi = Math.acos(2 * random() - 1);
    positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = radius * Math.cos(phi);
    positions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

  const points = new THREE.Points(
    geometry,
    new THREE.PointsMaterial({ color: 0xffffff, size: radius * 0.0012, sizeAttenuation: false }),
  );
  points.name = 'starfield';
  points.frustumCulled = false;
  return points;
}

/**
 * Build the scene lighting: one sun, plus fill so the shadowed side is readable.
 *
 * A physically accurate space scene has one light source and pitch-black
 * shadows. That is dramatic and useless for reading a rocket, so a low ambient
 * term is added deliberately. Clarity beats realism here.
 *
 * @param sunDirection - Direction the sunlight comes *from*, in scene space.
 * @returns A group holding the lights.
 */
export function createLighting(
  sunDirection = new THREE.Vector3(1, 0.6, 0.4),
): THREE.Group {
  const group = new THREE.Group();
  group.name = 'lighting';

  const sun = new THREE.DirectionalLight(0xfff4e6, 2.4);
  sun.position.copy(sunDirection.clone().normalize().multiplyScalar(100));
  sun.name = 'sun';
  group.add(sun);

  const ambient = new THREE.AmbientLight(0x404a5a, 1.1);
  ambient.name = 'ambient';
  group.add(ambient);

  // A dim fill from below stops the underside of the vehicle going to pure
  // black, which is where the engines are and therefore where the user looks.
  const fill = new THREE.DirectionalLight(0x2a3a4a, 0.5);
  fill.position.set(-1, -0.5, -0.5);
  fill.name = 'fill';
  group.add(fill);

  return group;
}
