/**
 * A whole vehicle, as drawable geometry.
 *
 * Turns a {@link DesignLayout} into an ordered set of shapes with real
 * dimensions: a silhouette that can be drawn as an SVG side view, lathed into a
 * 3D mesh, or annotated with the centre of gravity and centre of pressure. One
 * assembly step, three consumers, so the 2D drawing, the 3D model and the
 * engineering annotations can never disagree about where anything is.
 *
 * ## Coordinates
 *
 * `station` runs aft from the nose tip, matching the convention the stability
 * model uses. Every shape reports the station of its forward end and its
 * length, so a component's position on screen and its position in the CG
 * calculation come from the same number.
 *
 * Radii are measured from the vehicle axis. Fins and other radial parts carry
 * their own outline in the fin plane plus the angular positions of each blade.
 *
 * @module geometry/vehicle-outline
 */

import type { DesignLayout, ResolvedComponent } from '../core/builder.js';
import type {
  BodyDef,
  ComponentCategory,
  EngineDef,
  FinDef,
  NoseConeDef,
  ParachuteDef,
} from '../core/component-types.js';
import {
  finOutline,
  noseConeProfile,
  nozzleProfile,
  transitionProfile,
  tubeProfile,
  type AxialProfile,
  type Point2,
} from './profiles.js';

// ============================================================
// Shapes
// ============================================================

/** How a shape should be drawn and shaded. */
export type SurfaceKind =
  | 'airframe'
  | 'nose'
  | 'nozzle'
  | 'tank'
  | 'fin'
  | 'structure'
  | 'payload'
  | 'recovery'
  | 'avionics'
  | 'separator';

/** A body of revolution positioned on the vehicle axis. */
export interface RevolvedShape {
  readonly kind: 'revolved';
  readonly instanceId: string;
  readonly name: string;
  readonly category: ComponentCategory;
  readonly surface: SurfaceKind;
  readonly stageIndex: number;
  /** Station of the forward end, aft from the nose tip. Unit: m */
  readonly station_m: number;
  /** The generated profile, forward end first. */
  readonly profile: AxialProfile;
  /** Radial offset for a strap-on booster. Unit: m */
  readonly offsetRadius_m: number;
  /** Angular position of a strap-on around the core. Unit: rad */
  readonly offsetAngle_rad: number;
  /** Mass this component contributes, for the annotated view. Unit: kg */
  readonly mass_kg: number;
}

/** A set of fins: one planform, repeated around the body. */
export interface FinSetShape {
  readonly kind: 'fin_set';
  readonly instanceId: string;
  readonly name: string;
  readonly category: ComponentCategory;
  readonly surface: SurfaceKind;
  readonly stageIndex: number;
  /** Station of the fin root leading edge. Unit: m */
  readonly station_m: number;
  /** The blade outline, in the fin's own plane. */
  readonly outline: readonly Point2[];
  /** Body radius the fins attach to. Unit: m */
  readonly bodyRadius_m: number;
  /** Angular position of each blade around the body. Unit: rad */
  readonly angles_rad: readonly number[];
  readonly thickness_m: number;
  readonly mass_kg: number;
  /** Grid fins draw a lattice inside their outline rather than a solid plate. */
  readonly isLattice: boolean;
}

export type VehicleShape = RevolvedShape | FinSetShape;

/** Everything needed to draw a vehicle and label it. */
export interface VehicleOutline {
  readonly shapes: readonly VehicleShape[];
  /** Nose tip to tail. Unit: m */
  readonly totalLength_m: number;
  /** Largest radius anywhere. Unit: m */
  readonly maxRadius_m: number;
  /** Station of each stage's forward end, aft from the nose tip. Unit: m */
  readonly stageStations_m: readonly number[];
  /** Instance ids the registry could not resolve. */
  readonly unresolvedInstanceIds: readonly string[];
}

// ============================================================
// Category → surface treatment
// ============================================================

const SURFACE_BY_CATEGORY: Readonly<Record<ComponentCategory, SurfaceKind>> = {
  body: 'airframe',
  nose_cone: 'nose',
  fairing: 'nose',
  coupler: 'structure',
  interstage: 'structure',
  engine: 'nozzle',
  motor_mount: 'structure',
  fuel_tank: 'tank',
  oxidizer_tank: 'tank',
  fin: 'fin',
  bulkhead: 'structure',
  centering_ring: 'structure',
  avionics: 'avionics',
  guidance: 'avionics',
  sensor: 'avionics',
  battery: 'avionics',
  payload: 'payload',
  decoupler: 'separator',
  parachute: 'recovery',
  heat_shield: 'recovery',
  landing_leg: 'recovery',
  custom: 'structure',
};

// ============================================================
// Assembly
// ============================================================

/**
 * Build the drawable outline of a design.
 *
 * @param layout - Resolved geometry from the builder.
 * @returns Shapes in draw order, forward to aft.
 */
export function buildVehicleOutline(layout: DesignLayout): VehicleOutline {
  const shapes: VehicleShape[] = [];
  const total = layout.totalLength_m;

  for (const component of layout.components) {
    // The builder measures axial position *up from the base*; drawing and
    // stability both work *aft from the nose tip*. Convert once, here.
    const station = total - (component.axialPosition_m + component.length_m);
    const shape = shapeFor(component, station, layout);
    if (shape) shapes.push(shape);
  }

  shapes.sort((a, b) => a.station_m - b.station_m);

  const stageStations = layout.stageBasePositions_m.map(
    (base, index) => total - (base + (layout.stageLengths_m[index] ?? 0)),
  );

  return {
    shapes,
    totalLength_m: total,
    maxRadius_m: layout.maxDiameter_m / 2,
    stageStations_m: stageStations,
    unresolvedInstanceIds: layout.unresolvedInstanceIds,
  };
}

function shapeFor(
  component: ResolvedComponent,
  station_m: number,
  layout: DesignLayout,
): VehicleShape | null {
  const surface = SURFACE_BY_CATEGORY[component.category] ?? 'structure';
  const radius = component.diameter_m / 2;
  const offsetRadius = Math.hypot(component.radialOffset_x, component.radialOffset_y);
  const offsetAngle = Math.atan2(component.radialOffset_y, component.radialOffset_x);

  const base = {
    instanceId: component.instanceId,
    name: component.name,
    category: component.category,
    surface,
    stageIndex: component.stageIndex,
    station_m,
    offsetRadius_m: offsetRadius,
    offsetAngle_rad: offsetAngle,
    mass_kg: component.totalMass_kg,
  } as const;

  switch (component.category) {
    case 'nose_cone':
    case 'fairing': {
      const def = component.def as NoseConeDef;
      return {
        ...base,
        kind: 'revolved',
        profile: noseConeProfile(def.shape ?? 'tangent_ogive', radius, component.length_m, {
          shapeParameter: def.shapeParameter,
          tipRadius_m: def.tipRadius_m,
        }),
      };
    }

    case 'fin': {
      const def = component.def as FinDef;
      const shape = def.shape ?? 'trapezoidal';
      const outline = finOutline(
        shape,
        def.rootChord_m,
        def.tipChord_m,
        def.span_m,
        def.sweepAngle_rad,
      );
      const count = Math.max(def.finCount, 1);
      const angles = Array.from({ length: count }, (_, i) => (i * 2 * Math.PI) / count);
      // Fins sit at the aft end of whatever they are mounted on, offset
      // forward by however far the definition sets them from the rear.
      const finStation =
        station_m + component.length_m - def.rootChord_m - (def.positionFromRear_m ?? 0);
      return {
        ...base,
        kind: 'fin_set',
        station_m: Math.max(finStation, 0),
        outline,
        bodyRadius_m: radius,
        angles_rad: angles,
        thickness_m: def.thickness_m ?? Math.max(radius * 0.02, 0.002),
        isLattice: shape === 'grid',
      };
    }

    case 'engine': {
      const def = component.def as EngineDef;
      // A real nozzle: narrow at the throat, flaring to the exit area the
      // definition declares. The exit area is a physical quantity the thrust
      // model already uses, so the drawn bell is the one being flown.
      const exitRadius =
        def.nozzleExitArea_m2 > 0
          ? Math.sqrt(def.nozzleExitArea_m2 / Math.PI)
          : radius * 0.9;
      const throatRadius = Math.max(
        exitRadius / Math.sqrt(Math.max(def.expansionRatio, 1.2)),
        exitRadius * 0.12,
      );
      // The chamber sits ahead of the bell and is drawn as a short tube.
      const bellLength = component.length_m * 0.62;
      const chamberLength = component.length_m - bellLength;
      const chamber = tubeProfile(Math.min(throatRadius * 2.2, radius), chamberLength);
      const bell = nozzleProfile(throatRadius, Math.min(exitRadius, radius), bellLength);
      return {
        ...base,
        kind: 'revolved',
        profile: concatProfiles(chamber, bell),
      };
    }

    case 'interstage': {
      // An interstage is usually a transition between two diameters.
      const def = component.def as { forwardDiameter_m?: number; aftDiameter_m?: number };
      const forward = (def.forwardDiameter_m ?? component.diameter_m) / 2;
      const aft = (def.aftDiameter_m ?? component.diameter_m) / 2;
      return {
        ...base,
        kind: 'revolved',
        profile:
          Math.abs(forward - aft) < 1e-6
            ? tubeProfile(forward, component.length_m)
            : transitionProfile(forward, aft, component.length_m),
      };
    }

    case 'parachute': {
      const def = component.def as ParachuteDef;
      // Stowed, a parachute is a packed cylinder inside the airframe. Its
      // deployed canopy is drawn only during descent, by the flight view.
      return {
        ...base,
        kind: 'revolved',
        profile: tubeProfile(Math.min(radius * 0.92, radius), component.length_m),
        // Carried so the flight view can inflate the right canopy.
        ...({ canopyDiameter_m: def.canopyDiameter_m } as Record<string, number>),
      } as RevolvedShape;
    }

    case 'centering_ring':
    case 'bulkhead': {
      // Internal structure. Drawn as a thin disc in the cutaway view; invisible
      // in the exterior view but present in the mass breakdown either way.
      return {
        ...base,
        kind: 'revolved',
        profile: tubeProfile(radius, Math.max(component.length_m, 0.004)),
      };
    }

    case 'body':
    default: {
      const def = component.def as Partial<BodyDef>;
      // A body tube whose inner diameter differs from a neighbour's would be a
      // transition; without that information it is a straight tube.
      void def;
      void layout;
      return {
        ...base,
        kind: 'revolved',
        profile: tubeProfile(radius, component.length_m),
      };
    }
  }
}

/** Join two profiles end to end into one. */
function concatProfiles(first: AxialProfile, second: AxialProfile): AxialProfile {
  const stations = [...first.stations];
  const radii = [...first.radii];
  for (let i = 0; i < second.stations.length; i += 1) {
    // Skip the duplicated joint sample.
    if (i === 0 && stations.length > 0) continue;
    const station = second.stations[i];
    const radius = second.radii[i];
    if (station === undefined || radius === undefined) continue;
    stations.push(first.length_m + station);
    radii.push(radius);
  }
  return {
    stations,
    radii,
    length_m: first.length_m + second.length_m,
    maxRadius_m: Math.max(first.maxRadius_m, second.maxRadius_m),
  };
}

// ============================================================
// Silhouette
// ============================================================

/**
 * The vehicle's outer silhouette, as a single closed polygon.
 *
 * Takes the maximum radius present at each station across every revolved
 * shape, so a wider fairing over a narrower body reads correctly and internal
 * structure never pokes through the skin. This is what the 2D side view draws,
 * and what the drag reference area is checked against.
 *
 * @param outline - The assembled vehicle.
 * @param samples - How many stations to evaluate.
 * @returns Upper edge points, forward to aft. Mirror for the lower edge.
 */
export function vehicleSilhouette(
  outline: VehicleOutline,
  samples = 200,
): readonly Point2[] {
  const points: Point2[] = [];
  const revolved = outline.shapes.filter(
    (s): s is RevolvedShape => s.kind === 'revolved' && s.offsetRadius_m === 0,
  );

  for (let i = 0; i <= samples; i += 1) {
    const station = (i / samples) * outline.totalLength_m;
    let radius = 0;
    for (const shape of revolved) {
      if (station < shape.station_m || station > shape.station_m + shape.profile.length_m) {
        continue;
      }
      radius = Math.max(radius, radiusAt(shape.profile, station - shape.station_m));
    }
    points.push({ x: station, y: radius });
  }
  return points;
}

/** Radius of a profile at a local station, by linear interpolation. */
export function radiusAt(profile: AxialProfile, localStation_m: number): number {
  const { stations, radii } = profile;
  const count = Math.min(stations.length, radii.length);
  if (count === 0) return 0;

  const first = stations[0] ?? 0;
  const last = stations[count - 1] ?? 0;
  if (localStation_m <= first) return radii[0] ?? 0;
  if (localStation_m >= last) return radii[count - 1] ?? 0;

  for (let i = 1; i < count; i += 1) {
    const stationHere = stations[i];
    const stationBefore = stations[i - 1];
    if (stationHere === undefined || stationBefore === undefined) continue;
    if (localStation_m <= stationHere) {
      const span = stationHere - stationBefore;
      const t = span > 0 ? (localStation_m - stationBefore) / span : 0;
      const radiusBefore = radii[i - 1] ?? 0;
      const radiusHere = radii[i] ?? radiusBefore;
      return radiusBefore + (radiusHere - radiusBefore) * t;
    }
  }
  return radii[count - 1] ?? 0;
}

/**
 * Frontal area of the silhouette. Unit: m²
 *
 * The drag reference area, taken from the drawn shape rather than declared
 * separately — so a user who widens the fairing sees drag rise without anyone
 * having to remember to update a second number.
 */
export function frontalArea(outline: VehicleOutline): number {
  let maxRadius = 0;
  for (const shape of outline.shapes) {
    if (shape.kind !== 'revolved') continue;
    maxRadius = Math.max(maxRadius, shape.profile.maxRadius_m + shape.offsetRadius_m);
  }
  return Math.PI * maxRadius * maxRadius;
}
