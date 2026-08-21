/**
 * Stability model — centre of gravity, Barrowman centre of pressure, and the
 * static stability margin.
 *
 * ## Station convention
 *
 * Every longitudinal position in this module is a **station**: distance from the
 * nose tip, measured **aft-positive**, in metres. This is the aerospace
 * convention and it is used consistently for CG, CP, and fin placement.
 *
 * It is *not* the same axis as the simulation's ENU `z` (which points up from
 * the launch pad, so it runs the other way and starts at the tail). The
 * conversion happens once, in `core/vehicle.ts`. Mixing the two is the single
 * easiest way to compute a meaningless stability margin.
 *
 * ## Method
 *
 * CG is the mass-weighted mean station of every mass element.
 *
 * CP uses the Barrowman equations: each lifting surface contributes a normal
 * force coefficient slope CNα and a station, and the CP is the CNα-weighted
 * mean station. For a constant-diameter body only the nose and the fins
 * contribute — a cylindrical body section produces no normal force at zero
 * angle of attack.
 *
 * ## Assumptions
 *
 *   - Small angle of attack (< ~10°)
 *   - Subsonic flow; Barrowman CP moves aft supersonically and this is not modelled
 *   - Axially symmetric vehicle, constant body diameter (no transitions modelled)
 *   - Rigid vehicle, no aeroelastic effects
 *   - Static margin only: this predicts whether disturbances are corrected, not
 *     how fast the vehicle oscillates (that needs moments of inertia and 6-DOF)
 *
 * Source: James Barrowman, "The Practical Calculation of the Aerodynamic
 *         Characteristics of Slender Finned Vehicles" (NASA TN, 1967)
 *
 * @module physics/stability
 */

/** A point mass at a longitudinal station, for CG computation. */
export interface MassElement {
  /** Identifier, for attributing contributions back to a component. */
  readonly id: string;
  /** Mass of this element. Unit: kg. */
  readonly mass_kg: number;
  /** Station of this element's own centre of mass, from nose tip, aft-positive. Unit: m. */
  readonly station_m: number;
}

/**
 * Nose profiles the Barrowman nose term recognises.
 *
 * Kept structurally identical to `NoseConeShape` in `core/component-types`, but
 * declared here rather than imported: `physics/` is a self-contained numerical
 * layer with no dependency on the component domain model, and the parity test
 * asserts the two lists stay in step.
 */
export type NoseProfile =
  | 'conical'
  | 'ogive'
  | 'tangent_ogive'
  | 'secant_ogive'
  | 'von_karman'
  | 'haack'
  | 'elliptical'
  | 'parabolic'
  | 'power_series'
  | 'blunt'
  | 'custom';

/** Nose cone geometry for the Barrowman nose term. */
export interface NoseGeometry {
  /** Profile shape — determines where the nose CP sits. */
  readonly shape: NoseProfile;
  /** Nose length. Unit: m. */
  readonly length_m: number;
  /** Diameter at the nose base (= body diameter). Unit: m. */
  readonly baseDiameter_m: number;
}

/** Trapezoidal fin set geometry for the Barrowman fin term. */
export interface FinSetGeometry {
  /** Number of fins in the set. Barrowman is valid for 3 or 4. */
  readonly count: number;
  /** Root chord (attached to the body). Unit: m. */
  readonly rootChord_m: number;
  /** Tip chord. Unit: m. */
  readonly tipChord_m: number;
  /** Semi-span, measured from the body surface outward. Unit: m. */
  readonly span_m: number;
  /** Axial distance from root leading edge to tip leading edge. Unit: m. */
  readonly sweepLength_m: number;
  /** Station of the fin root leading edge, from nose tip. Unit: m. */
  readonly stationLeadingEdge_m: number;
  /** Body radius where the fins attach. Unit: m. */
  readonly bodyRadius_m: number;
}

/** How a static margin is interpreted for a student. */
export type StabilityClassification = 'unstable' | 'marginal' | 'stable' | 'overstable';

/** Stability analysis result. */
export interface StabilityResult {
  /** Centre of gravity station from the nose tip, aft-positive. Unit: m. */
  readonly cg_m: number;
  /** Centre of pressure station from the nose tip, aft-positive. Unit: m. */
  readonly cp_m: number;
  /** Static margin (CP − CG) / d_ref. Unit: calibers (dimensionless). */
  readonly stabilityMargin_cal: number;
  /** Whether the vehicle is statically stable (margin >= 1 caliber). */
  readonly isStable: boolean;
  /** Educational classification of the margin. */
  readonly classification: StabilityClassification;
  /** Reference diameter used to convert the margin to calibers. Unit: m. */
  readonly referenceDiameter_m: number;
  /** Total normal force coefficient slope, per radian. Dimensionless. */
  readonly totalCNalpha: number;
  /** Total vehicle mass used for the CG. Unit: kg. */
  readonly totalMass_kg: number;
}

/**
 * Fraction of the nose length at which a nose cone's centre of pressure sits.
 *
 * These are the standard Barrowman results, and they are the reason nose
 * profile is a design decision rather than styling: a conical nose puts its CP
 * two-thirds of the way back, an elliptical one puts it a third of the way
 * back, and swapping between them moves the vehicle's static margin by a
 * meaningful fraction of a caliber with no other change.
 *
 * The ogive family shares 0.466 because tangent and secant ogives differ in
 * generating radius rather than in where the resulting pressure distribution
 * centres; the secant value drifts with the radius ratio and 0.466 is the
 * usual working figure. The Haack family sits near mid-length, and von Kármán
 * — which is the C = 0 member of that family — is treated as its own entry
 * because it is the one people actually specify.
 *
 * Source: Barrowman (1967), NASA TN. Subsonic, small angle of attack.
 */
const NOSE_CP_FRACTION: Readonly<Record<NoseProfile, number>> = {
  conical: 0.666,
  ogive: 0.466,
  tangent_ogive: 0.466,
  secant_ogive: 0.466,
  von_karman: 0.5,
  haack: 0.437,
  elliptical: 0.333,
  parabolic: 0.5,
  power_series: 0.5,
  // A blunted nose behaves close to an ellipsoid for CP purposes.
  blunt: 0.4,
  // A user-defined profile the engine cannot analyse. Mid-length is the least
  // wrong assumption, and validation warns that the margin is an estimate.
  custom: 0.5,
};

/**
 * Normal force coefficient slope of a nose cone, referenced to the body
 * cross-sectional area. Barrowman gives CNα = 2 for any nose shape.
 */
const NOSE_CN_ALPHA = 2;

/**
 * Compute centre of gravity from a set of mass elements.
 *
 * CG = Σ(mᵢ · xᵢ) / Σ(mᵢ)
 *
 * @param elements - Mass elements with stations from the nose tip.
 * @returns CG station from the nose tip, aft-positive. Unit: m.
 *   Returns 0 for an empty or massless set.
 */
export function centerOfGravity(elements: readonly MassElement[]): number {
  let totalMass = 0;
  let momentSum = 0;

  for (const el of elements) {
    totalMass += el.mass_kg;
    momentSum += el.mass_kg * el.station_m;
  }

  if (totalMass <= 0) return 0;
  return momentSum / totalMass;
}

/**
 * Total mass of a set of mass elements.
 *
 * @param elements - Mass elements.
 * @returns Total mass. Unit: kg.
 */
export function totalMass(elements: readonly MassElement[]): number {
  let total = 0;
  for (const el of elements) total += el.mass_kg;
  return total;
}

/**
 * Centre of pressure of a nose cone, from the nose tip.
 *
 * @param nose - Nose geometry.
 * @returns CP station. Unit: m.
 */
export function noseConeCP(nose: NoseGeometry): number {
  return NOSE_CP_FRACTION[nose.shape] * nose.length_m;
}

/**
 * Barrowman normal force coefficient slope and centre of pressure for a
 * trapezoidal fin set.
 *
 * CNα = K_fb · (4N (s/d)²) / (1 + √(1 + (2·L_m / (Cr + Ct))²))
 *
 * where K_fb = 1 + R/(s + R) is the fin–body interference factor and L_m is the
 * length of the fin mid-chord line.
 *
 * @param fins - Fin set geometry.
 * @param referenceDiameter_m - Body reference diameter. Unit: m.
 * @returns CNα (per radian) and CP station from the nose tip. Unit: m.
 */
export function finSetBarrowman(
  fins: FinSetGeometry,
  referenceDiameter_m: number,
): { cnAlpha: number; cp_m: number } {
  const { count, rootChord_m: cr, tipChord_m: ct, span_m: s } = fins;

  // Degenerate fin sets contribute nothing rather than producing NaN.
  if (count <= 0 || s <= 0 || cr + ct <= 0 || referenceDiameter_m <= 0) {
    return { cnAlpha: 0, cp_m: fins.stationLeadingEdge_m };
  }

  // Mid-chord line length: the hypotenuse of the semi-span and the axial
  // offset between the root and tip mid-chord points.
  const midChordOffset = fins.sweepLength_m + ct / 2 - cr / 2;
  const midChordLength = Math.hypot(s, midChordOffset);

  // Fin–body interference: the body carries some of the fins' lift.
  const kfb = 1 + fins.bodyRadius_m / (s + fins.bodyRadius_m);

  const spanRatio = s / referenceDiameter_m;
  const denominator =
    1 + Math.sqrt(1 + Math.pow((2 * midChordLength) / (cr + ct), 2));
  const cnAlpha = (kfb * (4 * count * spanRatio * spanRatio)) / denominator;

  // Barrowman fin CP, relative to the fin root leading edge.
  const sweepTerm = (fins.sweepLength_m * (cr + 2 * ct)) / (3 * (cr + ct));
  const chordTerm = (1 / 6) * (cr + ct - (cr * ct) / (cr + ct));
  const cp_m = fins.stationLeadingEdge_m + sweepTerm + chordTerm;

  return { cnAlpha, cp_m };
}

/**
 * Compute the overall static stability of a vehicle.
 *
 * @param massElements - All mass elements, with stations from the nose tip.
 * @param nose - Nose cone geometry.
 * @param fins - Fin sets, if any. A finless vehicle is almost always unstable,
 *   which the result will show.
 * @param referenceDiameter_m - Body diameter used to express the margin in
 *   calibers. Defaults to the nose base diameter.
 * @returns Full stability analysis.
 */
export function analyzeStability(
  massElements: readonly MassElement[],
  nose: NoseGeometry,
  fins: readonly FinSetGeometry[] = [],
  referenceDiameter_m: number = nose.baseDiameter_m,
): StabilityResult {
  const cg_m = centerOfGravity(massElements);
  const dRef = referenceDiameter_m > 0 ? referenceDiameter_m : 1;

  // Barrowman superposition: CP is the CNα-weighted mean of each surface's CP.
  let cnAlphaSum = NOSE_CN_ALPHA;
  let momentSum = NOSE_CN_ALPHA * noseConeCP(nose);

  for (const finSet of fins) {
    const { cnAlpha, cp_m } = finSetBarrowman(finSet, dRef);
    cnAlphaSum += cnAlpha;
    momentSum += cnAlpha * cp_m;
  }

  const cp_m = cnAlphaSum > 0 ? momentSum / cnAlphaSum : noseConeCP(nose);
  const stabilityMargin_cal = (cp_m - cg_m) / dRef;

  return {
    cg_m,
    cp_m,
    stabilityMargin_cal,
    isStable: stabilityMargin_cal >= 1.0,
    classification: classifyStability(stabilityMargin_cal),
    referenceDiameter_m: dRef,
    totalCNalpha: cnAlphaSum,
    totalMass_kg: totalMass(massElements),
  };
}

/**
 * Classify a static margin for educational display.
 *
 * - `< 0.5 cal` — **unstable**: the CP is at or ahead of the CG, so any
 *   disturbance grows and the vehicle tumbles.
 * - `0.5 – 1.0 cal` — **marginal**: nominally corrective but with little authority.
 * - `1.0 – 2.0 cal` — **stable**: the conventional design target.
 * - `> 2.0 cal` — **overstable**: strongly self-correcting, but it weathercocks
 *   into crosswinds and loses altitude to the resulting steering.
 *
 * @param margin_cal - Static margin. Unit: calibers.
 * @returns Classification.
 */
export function classifyStability(margin_cal: number): StabilityClassification {
  if (margin_cal < 0.5) return 'unstable';
  if (margin_cal < 1.0) return 'marginal';
  if (margin_cal <= 2.0) return 'stable';
  return 'overstable';
}
