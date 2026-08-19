/**
 * Rocket builder analysis — turns a {@link RocketDesign} into engineering numbers.
 *
 * This module answers the questions the Build screen asks: how heavy is it,
 * where is its centre of mass, how much delta-v does it have, will it leave the
 * pad, and is it stable. It is pure: no rendering, no I/O, no simulation.
 *
 * ## Layout model
 *
 * The design stores components as offsets; this module resolves them into
 * absolute geometry. Two axes are in play and it is worth being explicit:
 *
 * - **axial position** — metres up from the vehicle's base (tail). This is how
 *   the design is authored, and how it is drawn in 3D.
 * - **station** — metres aft from the nose tip. This is the aerospace
 *   convention for mass and aero properties, and what `physics/stability.ts`
 *   consumes.
 *
 * They run in opposite directions: `station = totalLength − axialPosition`.
 *
 * Within a stage, a component's `offset_z` is the axial position of its **aft
 * end** relative to the stage's aft end. A stage's length is the highest point
 * any of its components reaches. Stages stack bottom-up, stage 0 at the base.
 *
 * Each component's own centre of mass is assumed to be at its geometric centre.
 *
 * ## Recognised configuration overrides
 *
 * | Key            | Applies to        | Meaning                                    |
 * |----------------|-------------------|--------------------------------------------|
 * | `mass_kg`      | adjustable payload | Payload mass, clamped to the def's range   |
 * | `fillFraction` | fuel/oxidizer tank | Propellant load, 0–1, default 1            |
 * | `throttle`     | engine             | Throttle setting, clamped to the def's min |
 *
 * Unrecognised keys are ignored, so the UI can stash its own annotations.
 *
 * @module core/builder
 */

import { G0 } from '../physics/constants.js';
import {
  analyzeStability,
  type MassElement,
  type NoseGeometry,
  type FinSetGeometry,
  type StabilityResult,
} from '../physics/stability.js';
import { deltaV, thrustToWeightRatio } from '../physics/thrust.js';
import type {
  RocketDesign,
  PlacedComponent,
  ComponentDef,
  ComponentCategory,
  EngineDef,
  FinDef,
  NoseConeDef,
} from './component-types.js';
import type { ComponentRegistry } from './component-registry.js';

// ============================================================
// Tunable modelling constants
// ============================================================

/**
 * Drag coefficient attributed to skin friction and base drag on the body,
 * added to the nose and fin contributions.
 *
 * A representative value for a slender launch vehicle at subsonic speed. It is
 * a single number rather than a Reynolds-number correlation because this is an
 * educational model; the transonic rise is applied separately by
 * `physics/drag.ts`.
 */
export const BODY_DRAG_COEFFICIENT = 0.05;

/**
 * Drag coefficient used when a design has no nose cone at all — a flat face is
 * far draggier than any cone, and showing that is the point.
 */
export const BLUFF_BODY_DRAG_COEFFICIENT = 0.8;

// ============================================================
// Resolved component
// ============================================================

/** A placed component with its definition resolved and overrides applied. */
export interface ResolvedComponent {
  readonly instanceId: string;
  readonly defId: string;
  readonly name: string;
  readonly category: ComponentCategory;
  readonly stageIndex: number;
  readonly def: ComponentDef;

  /** Structural mass, after any payload mass override. Unit: kg. */
  readonly dryMass_kg: number;
  /** Propellant carried by this component (tanks only). Unit: kg. */
  readonly propellantMass_kg: number;
  /** Dry mass plus propellant. Unit: kg. */
  readonly totalMass_kg: number;

  /** Throttle setting for engines, 1 for everything else. Dimensionless. */
  readonly throttle: number;

  /** Axial position of the component's aft end, up from the vehicle base. Unit: m. */
  readonly axialPosition_m: number;
  /** Axial position of the component's centre of mass, up from the base. Unit: m. */
  readonly axialCenter_m: number;
  /** Station of the component's centre of mass, aft from the nose tip. Unit: m. */
  readonly station_m: number;

  /** Radial offset from the vehicle axis. Unit: m. */
  readonly radialOffset_x: number;
  readonly radialOffset_y: number;

  readonly length_m: number;
  readonly diameter_m: number;
  readonly cost: number;
}

/** Absolute geometry of a whole design. */
export interface DesignLayout {
  /** Every component with resolved masses and absolute positions. */
  readonly components: readonly ResolvedComponent[];
  /** Overall vehicle length, nose tip to tail. Unit: m. */
  readonly totalLength_m: number;
  /** Largest outer diameter anywhere on the vehicle. Unit: m. */
  readonly maxDiameter_m: number;
  /** Axial position of each stage's aft end, up from the vehicle base. Unit: m. */
  readonly stageBasePositions_m: readonly number[];
  /** Length of each stage. Unit: m. */
  readonly stageLengths_m: readonly number[];
  /** Instance ids in the design that could not be resolved against the registry. */
  readonly unresolvedInstanceIds: readonly string[];
}

/** Clamp a value into an inclusive range. */
function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * Effective dry mass of a component after applying overrides.
 *
 * Only adjustable payloads respond to a `mass_kg` override, and the value is
 * clamped to the range the definition allows.
 */
function resolveDryMass(def: ComponentDef, placed: PlacedComponent): number {
  if (def.category === 'payload' && def.massAdjustable) {
    const override = placed.configOverrides['mass_kg'];
    if (typeof override === 'number' && Number.isFinite(override)) {
      return clamp(override, def.minMass_kg, def.maxMass_kg);
    }
  }
  return def.mass_kg;
}

/**
 * Propellant carried by a component after applying the fill fraction.
 *
 * Tanks carry what they are filled with. Solid motors carry propellant cast
 * into the casing, and that grain cannot be part-loaded — a solid motor is
 * manufactured full, so `fillFraction` does not apply to it. Liquid engines
 * carry nothing and consume what the tanks in their stage hold.
 */
function resolvePropellantMass(def: ComponentDef, placed: PlacedComponent): number {
  if (def.category === 'engine') {
    return def.integralPropellant_kg;
  }
  if (def.category !== 'fuel_tank' && def.category !== 'oxidizer_tank') {
    return 0;
  }
  const fill = placed.configOverrides['fillFraction'];
  const fraction =
    typeof fill === 'number' && Number.isFinite(fill) ? clamp(fill, 0, 1) : 1;
  return def.capacity_kg * fraction;
}

/** Effective throttle for a component. Non-engines are always 1. */
function resolveThrottle(def: ComponentDef, placed: PlacedComponent): number {
  if (def.category !== 'engine') return 1;
  const throttle = placed.configOverrides['throttle'];
  if (typeof throttle === 'number' && Number.isFinite(throttle)) {
    return clamp(throttle, def.minThrottle, 1);
  }
  return 1;
}

/**
 * Resolve a design's components into absolute geometry and effective masses.
 *
 * Components whose definition is missing from the registry are skipped and
 * reported in `unresolvedInstanceIds` rather than throwing — a half-loaded
 * design should still render and still tell the user what is wrong.
 *
 * @param design - Design to lay out.
 * @param registry - Registry resolving component definitions.
 * @returns Absolute geometry, in both the axial and station conventions.
 */
export function layoutDesign(
  design: RocketDesign,
  registry: ComponentRegistry,
): DesignLayout {
  const unresolvedInstanceIds: string[] = [];

  // Pair each placed component with its definition, dropping unknown ones.
  const resolvable: { placed: PlacedComponent; def: ComponentDef }[] = [];
  for (const placed of design.components) {
    const def = registry.get(placed.defId);
    if (!def) {
      unresolvedInstanceIds.push(placed.instanceId);
      continue;
    }
    resolvable.push({ placed, def });
  }

  // Stage length is however far its tallest component reaches.
  const stageCount = design.stages.length;
  const stageLengths_m: number[] = new Array<number>(stageCount).fill(0);
  for (const { placed, def } of resolvable) {
    if (placed.stageIndex < 0 || placed.stageIndex >= stageCount) continue;
    const top = placed.offset_z + def.length_m;
    if (top > stageLengths_m[placed.stageIndex]!) {
      stageLengths_m[placed.stageIndex] = top;
    }
  }

  // Stages stack bottom-up: stage 0 sits at the base.
  const stageBasePositions_m: number[] = new Array<number>(stageCount).fill(0);
  let running = 0;
  for (let i = 0; i < stageCount; i++) {
    stageBasePositions_m[i] = running;
    running += stageLengths_m[i]!;
  }
  const totalLength_m = running;

  let maxDiameter_m = 0;
  const components: ResolvedComponent[] = [];

  for (const { placed, def } of resolvable) {
    const stageBase = stageBasePositions_m[placed.stageIndex] ?? 0;
    const axialPosition_m = stageBase + placed.offset_z;
    const axialCenter_m = axialPosition_m + def.length_m / 2;

    const dryMass_kg = resolveDryMass(def, placed);
    const propellantMass_kg = resolvePropellantMass(def, placed);

    if (def.outerDiameter_m > maxDiameter_m) maxDiameter_m = def.outerDiameter_m;

    components.push({
      instanceId: placed.instanceId,
      defId: placed.defId,
      name: def.name,
      category: def.category,
      stageIndex: placed.stageIndex,
      def,
      dryMass_kg,
      propellantMass_kg,
      totalMass_kg: dryMass_kg + propellantMass_kg,
      throttle: resolveThrottle(def, placed),
      axialPosition_m,
      axialCenter_m,
      // Station runs the other way: aft from the nose tip.
      station_m: totalLength_m - axialCenter_m,
      radialOffset_x: placed.offset_x,
      radialOffset_y: placed.offset_y,
      length_m: def.length_m,
      diameter_m: def.outerDiameter_m,
      cost: def.cost,
    });
  }

  return {
    components,
    totalLength_m,
    maxDiameter_m,
    stageBasePositions_m,
    stageLengths_m,
    unresolvedInstanceIds,
  };
}

// ============================================================
// Stage analysis
// ============================================================

/** Engineering summary of one stage. */
export interface StageAnalysis {
  readonly index: number;
  readonly name: string;

  /** Structural mass of this stage alone. Unit: kg. */
  readonly dryMass_kg: number;
  /** Propellant loaded in this stage. Unit: kg. */
  readonly propellantMass_kg: number;
  /** Dry + propellant for this stage alone. Unit: kg. */
  readonly wetMass_kg: number;

  /**
   * Mass this stage must accelerate at its ignition: itself plus every stage
   * above it. Lower stages have already separated by then. Unit: kg.
   */
  readonly ignitionStackMass_kg: number;
  /** The same stack at burnout, with this stage's propellant spent. Unit: kg. */
  readonly burnoutStackMass_kg: number;

  /** Number of engines in this stage. */
  readonly engineCount: number;
  /** Combined vacuum thrust at the configured throttle. Unit: N. */
  readonly thrustVacuum_N: number;
  /** Combined sea-level thrust at the configured throttle. Unit: N. */
  readonly thrustSeaLevel_N: number;
  /** Mass-flow-weighted vacuum specific impulse. Unit: s. */
  readonly isp_vacuum_s: number;
  /** Mass-flow-weighted sea-level specific impulse. Unit: s. */
  readonly isp_seaLevel_s: number;
  /** Combined propellant mass flow. Unit: kg/s. */
  readonly massFlowRate_kgs: number;
  /** How long the propellant lasts at that flow. Unit: s. 0 if it cannot burn. */
  readonly burnTime_s: number;

  /** Ideal delta-v from the rocket equation, excluding losses. Unit: m/s. */
  readonly deltaV_ms: number;
  /** Thrust-to-weight at ignition using sea-level thrust. Dimensionless. */
  readonly twrSeaLevel: number;
  /** Thrust-to-weight at ignition using vacuum thrust. Dimensionless. */
  readonly twrVacuum: number;

  /** Whether this stage has engines and propellant and can actually fire. */
  readonly canFire: boolean;
}

/** Aggregate the engine properties of a set of components. */
function summarizeEngines(components: readonly ResolvedComponent[]): {
  engineCount: number;
  thrustVacuum_N: number;
  thrustSeaLevel_N: number;
  massFlowRate_kgs: number;
  isp_vacuum_s: number;
  isp_seaLevel_s: number;
} {
  let engineCount = 0;
  let thrustVacuum_N = 0;
  let thrustSeaLevel_N = 0;
  let massFlowRate_kgs = 0;

  for (const c of components) {
    if (c.category !== 'engine') continue;
    const def = c.def as EngineDef;
    engineCount++;

    const vac = def.thrust_N * c.throttle;
    thrustVacuum_N += vac;
    thrustSeaLevel_N += def.thrustSeaLevel_N * c.throttle;

    // Mass flow is set by the vacuum rating: ṁ = F_vac / (Isp_vac · g₀).
    // It is a property of the turbopump/injector, not of ambient pressure.
    if (def.isp_vacuum_s > 0) {
      massFlowRate_kgs += vac / (def.isp_vacuum_s * G0);
    }
  }

  // Effective Isp of the cluster is the flow-weighted value, which falls
  // straight out of dividing total thrust by total flow.
  const isp_vacuum_s = massFlowRate_kgs > 0 ? thrustVacuum_N / (massFlowRate_kgs * G0) : 0;
  const isp_seaLevel_s =
    massFlowRate_kgs > 0 ? thrustSeaLevel_N / (massFlowRate_kgs * G0) : 0;

  return {
    engineCount,
    thrustVacuum_N,
    thrustSeaLevel_N,
    massFlowRate_kgs,
    isp_vacuum_s,
    isp_seaLevel_s,
  };
}

// ============================================================
// Whole-rocket analysis
// ============================================================

/** Complete engineering analysis of a design. */
export interface RocketAnalysis {
  readonly designId: string;
  readonly designName: string;

  /** Resolved geometry, reusable by the renderer. */
  readonly layout: DesignLayout;
  /** Per-stage figures, index 0 = bottom stage. */
  readonly stages: readonly StageAnalysis[];

  /** Structural mass of the whole vehicle. Unit: kg. */
  readonly totalDryMass_kg: number;
  /** All propellant on board. Unit: kg. */
  readonly totalPropellantMass_kg: number;
  /** Mass on the pad. Unit: kg. */
  readonly totalWetMass_kg: number;
  /** Mass of payload components. Included in dry mass; broken out here. Unit: kg. */
  readonly payloadMass_kg: number;

  /** Nose tip to tail. Unit: m. */
  readonly totalLength_m: number;
  /** Largest diameter on the vehicle. Unit: m. */
  readonly maxDiameter_m: number;
  /** Aerodynamic reference area, from the maximum diameter. Unit: m². */
  readonly referenceArea_m2: number;
  /** Subsonic drag coefficient of the assembled vehicle. Dimensionless. */
  readonly dragCoefficient: number;

  /** Sum of the per-stage ideal delta-v. Unit: m/s. */
  readonly totalDeltaV_ms: number;
  /** Thrust-to-weight on the pad, sea-level thrust over launch mass. */
  readonly liftoffTWR: number;

  /** Centre of mass fully fuelled, as a station aft of the nose. Unit: m. */
  readonly centerOfMassWet_m: number;
  /** Centre of mass with all tanks empty, as a station. Unit: m. */
  readonly centerOfMassDry_m: number;
  /** Static stability fully fuelled. */
  readonly stabilityWet: StabilityResult;
  /** Static stability with empty tanks — usually the harder case. */
  readonly stabilityDry: StabilityResult;

  /** Propellant mass fraction, propellant / wet mass. Dimensionless. */
  readonly propellantMassFraction: number;
  /** Payload mass fraction, payload / wet mass. Dimensionless. */
  readonly payloadFraction: number;

  /** Total build cost in catalogue units. */
  readonly totalCost: number;
}

/**
 * Assemble the mass elements the stability model needs.
 *
 * @param components - Resolved components.
 * @param includePropellant - Whether tanks contribute their propellant.
 * @returns Mass elements keyed on station.
 */
function toMassElements(
  components: readonly ResolvedComponent[],
  includePropellant: boolean,
): MassElement[] {
  return components.map(c => ({
    id: c.instanceId,
    // Propellant is assumed to sit at the tank's geometric centre. Real tanks
    // see their propellant CoM move as they drain; modelling that needs tank
    // geometry we do not carry.
    mass_kg: includePropellant ? c.totalMass_kg : c.dryMass_kg,
    station_m: c.station_m,
  }));
}

/**
 * Derive the nose geometry the Barrowman model needs.
 *
 * A design without a nose cone gets a blunt stand-in of zero length, which
 * places the CP at the very tip and shows up as an unstable vehicle — the
 * physically honest answer.
 */
function extractNoseGeometry(
  components: readonly ResolvedComponent[],
  fallbackDiameter_m: number,
): NoseGeometry {
  // The forwardmost nose cone is the one that shapes the flow.
  let nose: ResolvedComponent | undefined;
  for (const c of components) {
    if (c.category !== 'nose_cone') continue;
    if (!nose || c.station_m < nose.station_m) nose = c;
  }

  if (!nose) {
    return { shape: 'conical', length_m: 0, baseDiameter_m: fallbackDiameter_m };
  }

  const def = nose.def as NoseConeDef;
  return {
    shape: def.shape,
    length_m: def.length_m,
    baseDiameter_m: def.outerDiameter_m,
  };
}

/** Derive fin set geometry, converting each fin's axial placement to a station. */
function extractFinGeometry(
  components: readonly ResolvedComponent[],
  totalLength_m: number,
): FinSetGeometry[] {
  const fins: FinSetGeometry[] = [];

  for (const c of components) {
    if (c.category !== 'fin') continue;
    const def = c.def as FinDef;

    // The fin's leading edge is its forwardmost point, so it sits at the
    // component's *top* in axial terms — the smallest station.
    const stationLeadingEdge_m =
      totalLength_m - (c.axialPosition_m + def.rootChord_m);

    fins.push({
      count: def.finCount,
      rootChord_m: def.rootChord_m,
      tipChord_m: def.tipChord_m,
      span_m: def.span_m,
      // Convert the sweep angle into the axial offset Barrowman expects.
      sweepLength_m: def.span_m * Math.tan(def.sweepAngle_rad),
      stationLeadingEdge_m,
      bodyRadius_m: def.outerDiameter_m / 2,
    });
  }

  return fins;
}

/**
 * Subsonic drag coefficient of the assembled vehicle.
 *
 * Cd = Cd_nose + Σ (Cd_fin × fin count) + Cd_body
 *
 * A crude superposition, and deliberately so: it gives students a Cd that
 * responds to their design choices — a sharper nose and fewer fins lower it —
 * without pretending to be CFD.
 */
function computeDragCoefficient(components: readonly ResolvedComponent[]): number {
  let noseCd: number | null = null;
  let finCd = 0;

  for (const c of components) {
    if (c.category === 'nose_cone') {
      const cd = (c.def as NoseConeDef).dragCoefficient;
      // Keep the draggiest nose if somebody stacked several.
      if (noseCd === null || cd > noseCd) noseCd = cd;
    } else if (c.category === 'fin') {
      const def = c.def as FinDef;
      finCd += def.dragCoefficient * def.finCount;
    }
  }

  return (noseCd ?? BLUFF_BODY_DRAG_COEFFICIENT) + finCd + BODY_DRAG_COEFFICIENT;
}

/**
 * Run the full engineering analysis of a design.
 *
 * Every number here is derived, cached in the returned object, and safe to
 * render. Nothing is mutated and nothing is memoised across calls — the caller
 * decides when to recompute.
 *
 * @param design - Design to analyse.
 * @param registry - Registry resolving component definitions.
 * @returns The complete analysis.
 */
export function analyzeRocket(
  design: RocketDesign,
  registry: ComponentRegistry,
): RocketAnalysis {
  const layout = layoutDesign(design, registry);
  const { components, totalLength_m, maxDiameter_m } = layout;

  // --- Per-stage mass roll-up -------------------------------------------
  const stageCount = design.stages.length;
  const stageComponents: ResolvedComponent[][] = Array.from(
    { length: stageCount },
    () => [],
  );
  for (const c of components) {
    if (c.stageIndex >= 0 && c.stageIndex < stageCount) {
      stageComponents[c.stageIndex]!.push(c);
    }
  }

  const stageDryMass: number[] = [];
  const stagePropellant: number[] = [];
  for (let i = 0; i < stageCount; i++) {
    let dry = 0;
    let prop = 0;
    for (const c of stageComponents[i]!) {
      dry += c.dryMass_kg;
      prop += c.propellantMass_kg;
    }
    stageDryMass.push(dry);
    stagePropellant.push(prop);
  }

  // Stack mass at each stage's ignition: itself plus everything above it.
  // Accumulated from the top down so it stays O(n).
  const ignitionStackMass: number[] = new Array<number>(stageCount).fill(0);
  let above = 0;
  for (let i = stageCount - 1; i >= 0; i--) {
    const wet = stageDryMass[i]! + stagePropellant[i]!;
    ignitionStackMass[i] = wet + above;
    above = ignitionStackMass[i]!;
  }

  // --- Per-stage performance --------------------------------------------
  const stages: StageAnalysis[] = [];
  let totalDeltaV_ms = 0;

  for (let i = 0; i < stageCount; i++) {
    const engines = summarizeEngines(stageComponents[i]!);
    const propellantMass_kg = stagePropellant[i]!;
    const dryMass_kg = stageDryMass[i]!;
    const stackMass = ignitionStackMass[i]!;
    const burnoutStackMass = stackMass - propellantMass_kg;

    const burnTime_s =
      engines.massFlowRate_kgs > 0 ? propellantMass_kg / engines.massFlowRate_kgs : 0;

    const canFire =
      engines.engineCount > 0 && propellantMass_kg > 0 && engines.massFlowRate_kgs > 0;

    // The rocket equation needs a positive final mass; a stage with no
    // structure left after burnout would give an infinite delta-v.
    const stageDeltaV =
      canFire && burnoutStackMass > 0
        ? deltaV(engines.isp_vacuum_s, stackMass, burnoutStackMass)
        : 0;
    totalDeltaV_ms += stageDeltaV;

    stages.push({
      index: i,
      name: design.stages[i]?.name ?? `Stage ${i}`,
      dryMass_kg,
      propellantMass_kg,
      wetMass_kg: dryMass_kg + propellantMass_kg,
      ignitionStackMass_kg: stackMass,
      burnoutStackMass_kg: burnoutStackMass,
      engineCount: engines.engineCount,
      thrustVacuum_N: engines.thrustVacuum_N,
      thrustSeaLevel_N: engines.thrustSeaLevel_N,
      isp_vacuum_s: engines.isp_vacuum_s,
      isp_seaLevel_s: engines.isp_seaLevel_s,
      massFlowRate_kgs: engines.massFlowRate_kgs,
      burnTime_s,
      deltaV_ms: stageDeltaV,
      twrSeaLevel: thrustToWeightRatio(engines.thrustSeaLevel_N, stackMass, 0),
      twrVacuum: thrustToWeightRatio(engines.thrustVacuum_N, stackMass, 0),
      canFire,
    });
  }

  // --- Whole-vehicle totals ---------------------------------------------
  let totalDryMass_kg = 0;
  let totalPropellantMass_kg = 0;
  let payloadMass_kg = 0;
  let totalCost = 0;

  for (const c of components) {
    totalDryMass_kg += c.dryMass_kg;
    totalPropellantMass_kg += c.propellantMass_kg;
    totalCost += c.cost;
    if (c.category === 'payload') payloadMass_kg += c.dryMass_kg;
  }
  const totalWetMass_kg = totalDryMass_kg + totalPropellantMass_kg;

  // --- Aerodynamics and stability ---------------------------------------
  const referenceArea_m2 = (Math.PI / 4) * maxDiameter_m * maxDiameter_m;
  const nose = extractNoseGeometry(components, maxDiameter_m);
  const finSets = extractFinGeometry(components, totalLength_m);
  const referenceDiameter_m = maxDiameter_m > 0 ? maxDiameter_m : 1;

  const stabilityWet = analyzeStability(
    toMassElements(components, true),
    nose,
    finSets,
    referenceDiameter_m,
  );
  const stabilityDry = analyzeStability(
    toMassElements(components, false),
    nose,
    finSets,
    referenceDiameter_m,
  );

  const firstStage = stages[0];

  return {
    designId: design.id,
    designName: design.name,
    layout,
    stages,
    totalDryMass_kg,
    totalPropellantMass_kg,
    totalWetMass_kg,
    payloadMass_kg,
    totalLength_m,
    maxDiameter_m,
    referenceArea_m2,
    dragCoefficient: computeDragCoefficient(components),
    totalDeltaV_ms,
    liftoffTWR: firstStage
      ? thrustToWeightRatio(firstStage.thrustSeaLevel_N, totalWetMass_kg, 0)
      : 0,
    centerOfMassWet_m: stabilityWet.cg_m,
    centerOfMassDry_m: stabilityDry.cg_m,
    stabilityWet,
    stabilityDry,
    propellantMassFraction:
      totalWetMass_kg > 0 ? totalPropellantMass_kg / totalWetMass_kg : 0,
    payloadFraction: totalWetMass_kg > 0 ? payloadMass_kg / totalWetMass_kg : 0,
    totalCost,
  };
}

// ============================================================
// Payload capacity
// ============================================================

/** Result of a payload capacity search. */
export interface PayloadCapacityResult {
  /** Largest payload that still meets both constraints. Unit: kg. */
  readonly maxPayload_kg: number;
  /** Delta-v the vehicle achieves carrying that payload. Unit: m/s. */
  readonly deltaVAtMax_ms: number;
  /** Liftoff thrust-to-weight carrying that payload. Dimensionless. */
  readonly twrAtMax: number;
  /** Which constraint stopped the search. */
  readonly limitingFactor: 'delta_v' | 'thrust_to_weight' | 'search_bound' | 'none';
}

/**
 * Ideal delta-v of a stack when an extra payload mass rides on top.
 *
 * Adds `payload_kg` to every stage's stack mass and re-runs the rocket
 * equation. Structure and propellant are unchanged — this asks "what if we
 * bolted more payload on", not "what if we redesigned".
 */
function deltaVWithPayload(
  stages: readonly StageAnalysis[],
  payload_kg: number,
): number {
  let total = 0;
  for (const stage of stages) {
    if (!stage.canFire) continue;
    const initial = stage.ignitionStackMass_kg + payload_kg;
    const final = stage.burnoutStackMass_kg + payload_kg;
    if (final <= 0) continue;
    total += deltaV(stage.isp_vacuum_s, initial, final);
  }
  return total;
}

/**
 * Find the largest payload a design can carry while still meeting a delta-v
 * target and a minimum liftoff thrust-to-weight.
 *
 * Both constraints weaken monotonically as payload grows — more mass means less
 * delta-v and less TWR — so a bisection search converges reliably.
 *
 * The payload is treated as mass *added on top of* the design's existing
 * contents. If the design already carries a payload component, the number
 * returned is the additional capacity beyond it.
 *
 * @param analysis - Analysis of the design, from {@link analyzeRocket}.
 * @param targetDeltaV_ms - Delta-v the mission needs. Unit: m/s. A low-Earth
 *   orbit ascent needs roughly 9 400 m/s once losses are included.
 * @param minTWR - Minimum acceptable liftoff thrust-to-weight. Defaults to 1.2,
 *   the conventional floor for a vertical launch with margin.
 * @param searchBound_kg - Upper bound for the search. Unit: kg.
 * @returns The capacity and which constraint bound it.
 */
export function estimatePayloadCapacity(
  analysis: RocketAnalysis,
  targetDeltaV_ms: number,
  minTWR = 1.2,
  searchBound_kg = 1_000_000,
): PayloadCapacityResult {
  const firstStage = analysis.stages[0];
  const liftoffThrust_N = firstStage?.thrustSeaLevel_N ?? 0;

  const meets = (payload_kg: number): boolean => {
    const dv = deltaVWithPayload(analysis.stages, payload_kg);
    if (dv < targetDeltaV_ms) return false;
    const twr = thrustToWeightRatio(
      liftoffThrust_N,
      analysis.totalWetMass_kg + payload_kg,
      0,
    );
    return twr >= minTWR;
  };

  const describe = (payload_kg: number): PayloadCapacityResult => {
    const deltaVAtMax_ms = deltaVWithPayload(analysis.stages, payload_kg);
    const twrAtMax = thrustToWeightRatio(
      liftoffThrust_N,
      analysis.totalWetMass_kg + payload_kg,
      0,
    );
    let limitingFactor: PayloadCapacityResult['limitingFactor'] = 'none';
    if (payload_kg >= searchBound_kg) {
      limitingFactor = 'search_bound';
    } else if (deltaVAtMax_ms - targetDeltaV_ms < twrAtMax - minTWR) {
      // Whichever constraint has less slack is the one that bound the search.
      limitingFactor = 'delta_v';
    } else {
      limitingFactor = 'thrust_to_weight';
    }
    return { maxPayload_kg: payload_kg, deltaVAtMax_ms, twrAtMax, limitingFactor };
  };

  // The vehicle cannot even meet the target empty — capacity is zero.
  if (!meets(0)) {
    return { ...describe(0), maxPayload_kg: 0 };
  }
  // The vehicle meets the target at the search bound — report the bound.
  if (meets(searchBound_kg)) {
    return describe(searchBound_kg);
  }

  // Bisect: `low` always satisfies, `high` never does.
  let low = 0;
  let high = searchBound_kg;
  // 60 iterations halves a 1e6 kg range to well below floating-point relevance;
  // 40 is already sub-milligram and keeps this comfortably fast.
  for (let i = 0; i < 40; i++) {
    const mid = (low + high) / 2;
    if (meets(mid)) {
      low = mid;
    } else {
      high = mid;
    }
  }

  return describe(low);
}
