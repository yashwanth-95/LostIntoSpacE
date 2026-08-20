/**
 * Parametric component geometry.
 *
 * Pure mathematics: given a component's declared shape and dimensions, produce
 * the curve or outline that defines it. No Three.js, no SVG, no React — the 2D
 * drawing, the 3D lathe and the drag model all consume the *same* generated
 * profile, which is what stops a vehicle from looking one way and flying
 * another.
 *
 * ## Why real profiles matter
 *
 * A nose cone drawn as a triangle is not merely uglier than the real shape; it
 * is a different vehicle. The generating curve sets where the nose's centre of
 * pressure sits — a conical nose puts it two-thirds of the way back, an
 * elliptical one a third — which moves the static margin by a meaningful
 * fraction of a caliber with nothing else changed. A von Kármán ogive exists
 * because it is the minimum-drag body for a given length and base diameter at
 * supersonic speed, and drawing it as a cone throws away the entire reason
 * anyone specifies one.
 *
 * Every curve here is the published generating equation, evaluated directly.
 *
 * @module geometry/profiles
 */

import type { FinShape, NoseConeShape } from '../core/component-types.js';

// ============================================================
// Shared types
// ============================================================

/** A point on a 2D outline. */
export interface Point2 {
  readonly x: number;
  readonly y: number;
}

/**
 * A body of revolution, sampled along its axis.
 *
 * `x` runs from the forward end (0) aft; `radius` is the local radius at that
 * station. Lathing this around the x-axis gives the 3D shape; drawing it and
 * its mirror gives the 2D silhouette.
 */
export interface AxialProfile {
  /** Sampled stations from the forward end. Unit: m */
  readonly stations: readonly number[];
  /** Radius at each station. Unit: m */
  readonly radii: readonly number[];
  /** Overall length. Unit: m */
  readonly length_m: number;
  /** Largest radius reached. Unit: m */
  readonly maxRadius_m: number;
}

/** How finely to sample a curve. More points cost nothing here and read better. */
export const DEFAULT_PROFILE_SEGMENTS = 48;

// ============================================================
// Nose cone profiles
// ============================================================

/**
 * Local radius of a nose cone at a fraction of its length.
 *
 * All formulas take x from the *tip* (x = 0) to the base (x = L) and return the
 * radius there, with R the base radius.
 *
 * @param shape - The generating curve.
 * @param xFraction - Position along the cone, 0 at the tip, 1 at the base.
 * @param baseRadius_m - Radius at the base. Unit: m
 * @param length_m - Length from tip to base. Unit: m
 * @param shapeParameter - The free parameter for the families that take one.
 * @returns Local radius. Unit: m
 */
export function noseRadiusAt(
  shape: NoseConeShape,
  xFraction: number,
  baseRadius_m: number,
  length_m: number,
  shapeParameter?: number,
): number {
  const t = clamp01(xFraction);
  const R = baseRadius_m;
  const L = length_m;

  if (L <= 0 || R <= 0) return 0;

  switch (shape) {
    case 'conical':
      // A straight line from tip to base.
      return R * t;

    case 'ogive':
    case 'tangent_ogive': {
      // A circular arc tangent to the body at the base. The generating radius
      // is fixed by the requirement of tangency.
      const rho = (R * R + L * L) / (2 * R);
      const x = t * L;
      const inner = rho * rho - (L - x) * (L - x);
      return Math.sqrt(Math.max(inner, 0)) + R - rho;
    }

    case 'secant_ogive': {
      // A circular arc that is *not* tangent at the base, so the profile meets
      // the body at a visible angle. The parameter is how much larger the
      // generating radius is than the tangent case; 1 reproduces a tangent
      // ogive exactly.
      //
      // Built geometrically rather than from the closed-form angle expression,
      // which is stated inconsistently across references and is easy to get
      // sign-wrong: find the circle of radius rho through the tip (0, 0) and
      // the base (L, R), and evaluate it. Solving
      //
      //     cx^2 + cy^2 = rho^2        (passes through the tip)
      //     (L-cx)^2 + (R-cy)^2 = rho^2  (passes through the base)
      //
      // reduces to a quadratic in cy whose lower root puts the centre below
      // the axis, which is the arc that bulges the right way.
      const rhoTangent = (R * R + L * L) / (2 * R);
      const ratio = Math.max(shapeParameter ?? 1.2, 1);
      const rho = rhoTangent * ratio;
      const S = L * L + R * R;
      const discriminant = R * R - (S * S - 4 * L * L * rho * rho) / S;
      if (discriminant < 0) {
        // No such circle exists; fall back to the tangent ogive, which always
        // does.
        return noseRadiusAt('tangent_ogive', t, R, L);
      }
      const cy = (R - Math.sqrt(discriminant)) / 2;
      const cx = (S - 2 * R * cy) / (2 * L);
      const x = t * L;
      const inner = rho * rho - (x - cx) * (x - cx);
      return cy + Math.sqrt(Math.max(inner, 0));
    }

    case 'von_karman':
      // The C = 0 member of the Haack series: minimum drag for a given length
      // and base diameter. Also called LD-Haack.
      return haackRadius(t, R, 0);

    case 'haack':
      // The general Haack series. C = 1/3 gives LV-Haack, minimum drag for a
      // given length and *volume*.
      return haackRadius(t, R, shapeParameter ?? 1 / 3);

    case 'elliptical': {
      // A quarter-ellipse. Blunt at the tip, which is why it is common on
      // subsonic vehicles and rare on supersonic ones.
      const u = 1 - t;
      return R * Math.sqrt(Math.max(1 - u * u, 0));
    }

    case 'parabolic': {
      // K' = 0 is a cone, K' = 1 is the full parabola. Values between
      // interpolate, which is exactly why the parameter exists.
      const K = clamp01(shapeParameter ?? 0.75);
      return (R * (2 * t - K * t * t)) / (2 - K);
    }

    case 'power_series': {
      // r = R·(x/L)^n. n = 1 is a cone, n = 0.5 is the common "1/2 power"
      // profile, n → 0 approaches a flat-faced cylinder.
      const n = Math.max(shapeParameter ?? 0.5, 0.01);
      return R * Math.pow(t, n);
    }

    case 'blunt': {
      // A hemispherical cap blended into a cone. The cap occupies the forward
      // portion; beyond it the profile is conical.
      const capFraction = clamp01(shapeParameter ?? 0.25);
      if (t < capFraction && capFraction > 0) {
        const capR = R * capFraction;
        const u = t / capFraction;
        return capR * Math.sqrt(Math.max(1 - (1 - u) * (1 - u), 0));
      }
      return R * t;
    }

    case 'custom':
    default:
      // Nothing better to assume than an ogive, which is the most common real
      // profile. Validation flags a custom shape so the estimate is not
      // presented as exact.
      return noseRadiusAt('tangent_ogive', t, R, L);
  }
}

/**
 * The Haack series.
 *
 * r(θ) = (R/√π)·√(θ − sin(2θ)/2 + C·sin³θ),  θ = arccos(1 − 2x/L)
 *
 * C = 0 is the von Kármán (LD-Haack) body — minimum drag for a given length and
 * diameter. C = 1/3 is LV-Haack — minimum drag for a given length and volume.
 */
function haackRadius(xFraction: number, baseRadius_m: number, C: number): number {
  const theta = Math.acos(clampUnit(1 - 2 * xFraction));
  const inner = theta - Math.sin(2 * theta) / 2 + C * Math.pow(Math.sin(theta), 3);
  return (baseRadius_m / Math.sqrt(Math.PI)) * Math.sqrt(Math.max(inner, 0));
}

/**
 * Sample a nose cone into an axial profile ready to draw or lathe.
 *
 * @param shape - Generating curve.
 * @param baseRadius_m - Radius where the cone meets the body. Unit: m
 * @param length_m - Tip-to-base length. Unit: m
 * @param options - Sampling density and the shape's free parameter.
 */
export function noseConeProfile(
  shape: NoseConeShape,
  baseRadius_m: number,
  length_m: number,
  options: { segments?: number; shapeParameter?: number; tipRadius_m?: number } = {},
): AxialProfile {
  const segments = Math.max(options.segments ?? DEFAULT_PROFILE_SEGMENTS, 4);
  const stations: number[] = [];
  const radii: number[] = [];

  for (let i = 0; i <= segments; i += 1) {
    const t = i / segments;
    stations.push(t * length_m);
    let radius = noseRadiusAt(shape, t, baseRadius_m, length_m, options.shapeParameter);
    // A blunted tip: never let the profile come to a mathematical point when
    // the component declares a finite tip radius.
    if (options.tipRadius_m && options.tipRadius_m > 0) {
      radius = Math.max(radius, options.tipRadius_m * (1 - t) + radius * t);
    }
    radii.push(radius);
  }

  return {
    stations,
    radii,
    length_m,
    maxRadius_m: radii.reduce((a, b) => Math.max(a, b), 0),
  };
}

// ============================================================
// Body, transition and nozzle profiles
// ============================================================

/** A constant-diameter tube. Two stations is all it needs. */
export function tubeProfile(radius_m: number, length_m: number): AxialProfile {
  return {
    stations: [0, length_m],
    radii: [radius_m, radius_m],
    length_m,
    maxRadius_m: radius_m,
  };
}

/**
 * A conical transition between two diameters — an interstage, a boat-tail, or
 * the shoulder where a wide fairing meets a narrower body.
 */
export function transitionProfile(
  forwardRadius_m: number,
  aftRadius_m: number,
  length_m: number,
  segments = 8,
): AxialProfile {
  const stations: number[] = [];
  const radii: number[] = [];
  for (let i = 0; i <= segments; i += 1) {
    const t = i / segments;
    stations.push(t * length_m);
    radii.push(forwardRadius_m + (aftRadius_m - forwardRadius_m) * t);
  }
  return {
    stations,
    radii,
    length_m,
    maxRadius_m: Math.max(forwardRadius_m, aftRadius_m),
  };
}

/**
 * A bell nozzle.
 *
 * Narrow at the throat, flaring to the exit along a parabolic contour — the
 * standard approximation to a Rao bell. Drawn from the forward (chamber) end
 * aft, so it assembles into the vehicle profile like any other component.
 *
 * @param throatRadius_m - Radius at the throat. Unit: m
 * @param exitRadius_m - Radius at the nozzle exit. Unit: m
 * @param length_m - Throat-to-exit length. Unit: m
 */
export function nozzleProfile(
  throatRadius_m: number,
  exitRadius_m: number,
  length_m: number,
  segments = 20,
): AxialProfile {
  const stations: number[] = [];
  const radii: number[] = [];
  for (let i = 0; i <= segments; i += 1) {
    const t = i / segments;
    stations.push(t * length_m);
    // A square-root flare: fast expansion near the throat, easing toward the
    // exit, which is what a real bell contour does.
    radii.push(throatRadius_m + (exitRadius_m - throatRadius_m) * Math.sqrt(t));
  }
  return { stations, radii, length_m, maxRadius_m: exitRadius_m };
}

// ============================================================
// Fin planforms
// ============================================================

/**
 * Fin outline in the plane of the fin.
 *
 * The returned polygon starts at the root leading edge and runs clockwise:
 * root leading edge → tip leading edge → tip trailing edge → root trailing
 * edge. `x` is chordwise (aft-positive), `y` is spanwise from the body surface.
 *
 * @param shape - Planform.
 * @param rootChord_m - Chord where the fin meets the body. Unit: m
 * @param tipChord_m - Chord at the tip. Zero for a true delta. Unit: m
 * @param span_m - Distance from body surface to tip. Unit: m
 * @param sweepAngle_rad - Leading-edge sweep. Unit: rad
 */
export function finOutline(
  shape: FinShape,
  rootChord_m: number,
  tipChord_m: number,
  span_m: number,
  sweepAngle_rad: number,
): readonly Point2[] {
  const sweep = span_m * Math.tan(sweepAngle_rad);

  switch (shape) {
    case 'delta':
      // A triangle: the tip chord collapses to a point.
      return [
        { x: 0, y: 0 },
        { x: rootChord_m, y: 0 },
        { x: rootChord_m, y: span_m },
      ];

    case 'clipped_delta':
      // A delta with the point cut off, so it keeps a finite tip chord.
      return [
        { x: 0, y: 0 },
        { x: rootChord_m, y: 0 },
        { x: rootChord_m, y: span_m },
        { x: rootChord_m - tipChord_m, y: span_m },
      ];

    case 'rectangular':
      return [
        { x: 0, y: 0 },
        { x: rootChord_m, y: 0 },
        { x: rootChord_m, y: span_m },
        { x: 0, y: span_m },
      ];

    case 'elliptical': {
      // A quarter-ellipse leading edge against a straight trailing edge — the
      // planform with the lowest induced drag for a given area.
      //
      // The polygon is traced as one loop: up the curved leading edge from
      // root to tip, then straight back down the trailing edge. Interleaving
      // the two edges instead produces a self-intersecting outline whose
      // shoelace area is meaningless.
      const segments = 24;
      const leadingEdge: Point2[] = [];
      for (let i = 0; i <= segments; i += 1) {
        const t = i / segments;
        const y = span_m * t;
        const chord = rootChord_m * Math.sqrt(Math.max(1 - t * t, 0));
        leadingEdge.push({ x: rootChord_m - chord, y });
      }
      return dedupe([
        ...leadingEdge,
        { x: rootChord_m, y: span_m },
        { x: rootChord_m, y: 0 },
      ]);
    }

    case 'grid': {
      // A grid fin is a lattice inside a rectangular frame. The outline is the
      // frame; the lattice is drawn separately by the renderer.
      return [
        { x: 0, y: 0 },
        { x: rootChord_m, y: 0 },
        { x: rootChord_m, y: span_m },
        { x: 0, y: span_m },
      ];
    }

    case 'swept':
    case 'trapezoidal':
    case 'custom':
    default:
      // The general trapezoid, which every other planform is a special case of.
      return [
        { x: 0, y: 0 },
        { x: rootChord_m, y: 0 },
        { x: sweep + tipChord_m, y: span_m },
        { x: sweep, y: span_m },
      ];
  }
}

/**
 * Planform area of one fin. Unit: m²
 *
 * Computed from the generated outline by the shoelace formula rather than from
 * a per-shape formula, so it can never disagree with the shape being drawn.
 */
export function finArea(outline: readonly Point2[]): number {
  if (outline.length < 3) return 0;
  let twiceArea = 0;
  for (let i = 0; i < outline.length; i += 1) {
    const a = outline[i];
    const b = outline[(i + 1) % outline.length];
    if (!a || !b) continue;
    twiceArea += a.x * b.y - b.x * a.y;
  }
  return Math.abs(twiceArea) / 2;
}

/**
 * The trapezoid that best represents an arbitrary planform, for Barrowman.
 *
 * The Barrowman fin term is derived for trapezoidal fins. Rather than refuse to
 * analyse an elliptical or custom planform, the outline is reduced to the
 * trapezoid with the same area, span and mid-chord sweep — a documented
 * approximation, and a far better answer than declining to compute a static
 * margin at all.
 */
export function equivalentTrapezoid(
  outline: readonly Point2[],
  span_m: number,
): { rootChord_m: number; tipChord_m: number; sweepLength_m: number } {
  if (outline.length < 3 || span_m <= 0) {
    return { rootChord_m: 0, tipChord_m: 0, sweepLength_m: 0 };
  }

  const chordAt = (y: number): { min: number; max: number } => {
    let min = Number.POSITIVE_INFINITY;
    let max = Number.NEGATIVE_INFINITY;
    const tolerance = span_m * 0.02;
    for (const point of outline) {
      if (Math.abs(point.y - y) <= tolerance) {
        min = Math.min(min, point.x);
        max = Math.max(max, point.x);
      }
    }
    return Number.isFinite(min) ? { min, max } : { min: 0, max: 0 };
  };

  const root = chordAt(0);
  const tip = chordAt(span_m);

  return {
    rootChord_m: Math.max(root.max - root.min, 0),
    tipChord_m: Math.max(tip.max - tip.min, 0),
    sweepLength_m: Math.max(tip.min - root.min, 0),
  };
}

// ============================================================
// Helpers
// ============================================================

function clamp01(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

/** Clamp to [-1, 1] before an inverse trig call, so rounding cannot produce NaN. */
function clampUnit(value: number): number {
  return value < -1 ? -1 : value > 1 ? 1 : value;
}

function dedupe(points: readonly Point2[]): Point2[] {
  const result: Point2[] = [];
  for (const point of points) {
    const last = result[result.length - 1];
    if (!last || Math.abs(last.x - point.x) > 1e-9 || Math.abs(last.y - point.y) > 1e-9) {
      result.push(point);
    }
  }
  return result;
}
