/**
 * Design → Vehicle conversion.
 *
 * This is the boundary between the builder and the simulation. Everything the
 * simulation knows about a rocket comes through here, and nothing else in
 * `sim/` imports a component type.
 *
 * The conversion is lossy on purpose. A stage of fifteen components becomes
 * eight numbers. That is what makes the flight loop fast enough to run at
 * 0.05 s steps without allocating, and what makes a {@link Vehicle} small
 * enough to `postMessage` into a Web Worker.
 *
 * @module core/vehicle
 */

import type { RocketDesign } from './component-types.js';
import type { ComponentRegistry } from './component-registry.js';
import type { Stage, Vehicle } from './types.js';
import { analyzeRocket, type RocketAnalysis } from './builder.js';

/**
 * Fallback structural limit for a design that declares none.
 *
 * Deliberately generous: a missing limit should not manufacture a failure that
 * the user never designed in.
 */
const UNLIMITED_LOAD_N = Number.POSITIVE_INFINITY;

/**
 * Convert a rocket design into the flat {@link Vehicle} the simulation runs.
 *
 * @param design - Design to convert.
 * @param registry - Registry resolving component definitions.
 * @param separationDelay_s - Delay between a stage's cutoff and its separation.
 *   Unit: s. Applied uniformly; per-stage decoupler timing is read from the
 *   design where a decoupler is present.
 * @returns A simulation-ready vehicle.
 */
export function toVehicle(
  design: RocketDesign,
  registry: ComponentRegistry,
  separationDelay_s = 0.5,
): Vehicle {
  return vehicleFromAnalysis(analyzeRocket(design, registry), design, separationDelay_s);
}

/**
 * Convert an already-computed analysis into a {@link Vehicle}.
 *
 * Use this when the caller has run {@link analyzeRocket} for the builder UI and
 * does not want to pay for it twice.
 *
 * @param analysis - Analysis of the design.
 * @param design - The design the analysis came from, for stage metadata.
 * @param separationDelay_s - Delay between cutoff and separation. Unit: s.
 * @returns A simulation-ready vehicle.
 */
export function vehicleFromAnalysis(
  analysis: RocketAnalysis,
  design: RocketDesign,
  separationDelay_s = 0.5,
): Vehicle {
  const stages: Stage[] = analysis.stages.map(stage => {
    const designStage = design.stages[stage.index];

    // A decoupler in the stage sets its own separation timing.
    const decoupler = analysis.layout.components.find(
      c => c.stageIndex === stage.index && c.category === 'decoupler',
    );
    const stageSeparationDelay =
      decoupler && decoupler.def.category === 'decoupler'
        ? decoupler.def.separationTime_s
        : separationDelay_s;

    return {
      stageNumber: stage.index,
      name: stage.name,
      dryMass_kg: stage.dryMass_kg,
      propellantMass_kg: stage.propellantMass_kg,
      thrustVacuum_N: stage.thrustVacuum_N,
      thrustSeaLevel_N: stage.thrustSeaLevel_N,
      ispVacuum_s: stage.isp_vacuum_s,
      ispSeaLevel_s: stage.isp_seaLevel_s,
      massFlowRate_kgs: stage.massFlowRate_kgs,
      burnTime_s: stage.burnTime_s,
      ignitionDelay_s: designStage?.ignitionDelay_s ?? 0,
      separationDelay_s: stageSeparationDelay,
      canFire: stage.canFire,
    };
  });

  // The weakest link sets the vehicle's structural limits. A stack is only as
  // strong as the component that gives way first.
  let maxAxialLoad_N = UNLIMITED_LOAD_N;
  let maxDynamicPressure_Pa = UNLIMITED_LOAD_N;
  for (const c of analysis.layout.components) {
    const structural = c.def.structural;
    if (!structural) continue;
    if (structural.maxAxialLoad_N > 0 && structural.maxAxialLoad_N < maxAxialLoad_N) {
      maxAxialLoad_N = structural.maxAxialLoad_N;
    }
    if (
      structural.maxDynamicPressure_Pa > 0 &&
      structural.maxDynamicPressure_Pa < maxDynamicPressure_Pa
    ) {
      maxDynamicPressure_Pa = structural.maxDynamicPressure_Pa;
    }
  }

  return {
    name: analysis.designName,
    designId: analysis.designId,
    stages,
    payloadMass_kg: analysis.payloadMass_kg,
    launchMass_kg: analysis.totalWetMass_kg,
    length_m: analysis.totalLength_m,
    diameter_m: analysis.maxDiameter_m,
    referenceArea_m2: analysis.referenceArea_m2,
    dragCoefficient: analysis.dragCoefficient,
    stabilityMarginWet_cal: analysis.stabilityWet.stabilityMargin_cal,
    stabilityMarginDry_cal: analysis.stabilityDry.stabilityMargin_cal,
    maxAxialLoad_N,
    maxDynamicPressure_Pa,
  };
}

/**
 * Total mass of a vehicle from a given stage upward, with that stage's tanks
 * holding `propellantRemaining_kg`.
 *
 * This is the mass the flight loop actually accelerates: stages below
 * `activeStage` have already been jettisoned.
 *
 * @param vehicle - Vehicle being flown.
 * @param activeStage - Index of the stage currently attached at the bottom.
 * @param propellantRemaining_kg - Propellant left in the active stage. Unit: kg.
 * @returns Current total mass. Unit: kg. Zero once every stage is gone.
 */
export function currentMass(
  vehicle: Vehicle,
  activeStage: number,
  propellantRemaining_kg: number,
): number {
  let total = 0;
  for (let i = activeStage; i < vehicle.stages.length; i++) {
    const stage = vehicle.stages[i]!;
    total += stage.dryMass_kg;
    // Only the active stage has drained; stages above it are still full.
    total += i === activeStage ? Math.max(0, propellantRemaining_kg) : stage.propellantMass_kg;
  }
  return total;
}

/**
 * Whether any stage from `fromStage` upward is still capable of firing.
 *
 * @param vehicle - Vehicle to inspect.
 * @param fromStage - Lowest stage index to consider.
 * @returns True when at least one usable stage remains.
 */
export function hasRemainingStages(vehicle: Vehicle, fromStage: number): boolean {
  for (let i = fromStage; i < vehicle.stages.length; i++) {
    if (vehicle.stages[i]!.canFire) return true;
  }
  return false;
}
