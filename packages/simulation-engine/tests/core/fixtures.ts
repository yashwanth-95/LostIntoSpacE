/**
 * Test fixtures — factory functions for creating valid component definitions.
 * Used across core/ tests.
 */

import type {
  BodyDef, NoseConeDef, EngineDef, FuelTankDef,
  FinDef, PayloadDef, DecouplerDef, AvionicsDef,
  ThermalProperties, StructuralProperties, VisualAssetRef,
} from '../../src/core/component-types.js';

const DEFAULT_THERMAL: ThermalProperties = {
  maxTemperature_K: 2000,
  thermalMass_JperK: 500,
  emissivity: 0.8,
};

const DEFAULT_STRUCTURAL: StructuralProperties = {
  maxAxialLoad_N: 100_000,
  maxLateralLoad_N: 20_000,
  maxDynamicPressure_Pa: 50_000,
};

const DEFAULT_VISUAL: VisualAssetRef = {
  assetId: 'default',
  fallbackProcedural: true,
  color: '#888888',
};

export function makeBody(overrides: Partial<BodyDef> & { id: string }): BodyDef {
  return {
    name: 'Body Tube',
    description: 'Standard body tube',
    category: 'body',
    mass_kg: 20,
    outerDiameter_m: 0.3,
    length_m: 1.0,
    innerDiameter_m: 0.28,
    wallThickness_m: 0.01,
    material: 'aluminum',
    structural: DEFAULT_STRUCTURAL,
    thermal: DEFAULT_THERMAL,
    failureModes: [],
    attachmentPoints: [
      { id: 'top', accepts: ['nose_cone', 'body', 'decoupler', 'payload'], offset_x: 0, offset_y: 0, offset_z: 1.0 },
      { id: 'bottom', accepts: ['engine', 'body', 'decoupler', 'fin'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
    visual: DEFAULT_VISUAL,
    cost: 100,
    ...overrides,
  };
}

export function makeNoseCone(overrides: Partial<NoseConeDef> & { id: string }): NoseConeDef {
  return {
    name: 'Ogive Nose',
    description: 'Standard ogive nose cone',
    category: 'nose_cone',
    mass_kg: 5,
    outerDiameter_m: 0.3,
    length_m: 0.5,
    shape: 'ogive',
    finenessRatio: 1.67,
    dragCoefficient: 0.3,
    structural: DEFAULT_STRUCTURAL,
    thermal: DEFAULT_THERMAL,
    failureModes: [],
    attachmentPoints: [
      { id: 'base', accepts: ['body'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
    visual: DEFAULT_VISUAL,
    cost: 50,
    ...overrides,
  };
}

export function makeEngine(overrides: Partial<EngineDef> & { id: string }): EngineDef {
  return {
    name: 'Standard Engine',
    description: 'Liquid bipropellant engine',
    category: 'engine',
    mass_kg: 30,
    outerDiameter_m: 0.25,
    length_m: 0.6,
    thrust_N: 50_000,
    thrustSeaLevel_N: 45_000,
    isp_vacuum_s: 310,
    isp_seaLevel_s: 280,
    propellantType: 'liquid_bipropellant',
    nozzleExitArea_m2: 0.04,
    expansionRatio: 15,
    maxIgnitions: 1,
    minThrottle: 1.0,
    gimballed: false,
    maxGimbalAngle_rad: 0,
    structural: DEFAULT_STRUCTURAL,
    thermal: { ...DEFAULT_THERMAL, maxTemperature_K: 3500 },
    failureModes: [],
    attachmentPoints: [
      { id: 'mount', accepts: ['body', 'fuel_tank'], offset_x: 0, offset_y: 0, offset_z: 0.6 },
    ],
    visual: DEFAULT_VISUAL,
    cost: 500,
    ...overrides,
  };
}

export function makeFuelTank(overrides: Partial<FuelTankDef> & { id: string }): FuelTankDef {
  return {
    name: 'Fuel Tank',
    description: 'Standard fuel tank',
    category: 'fuel_tank',
    mass_kg: 15,
    outerDiameter_m: 0.3,
    length_m: 0.8,
    capacity_kg: 200,
    fuelType: 'RP-1',
    fuelDensity_kgm3: 810,
    volume_m3: 0.247,
    pressurization_Pa: 300_000,
    structural: DEFAULT_STRUCTURAL,
    thermal: DEFAULT_THERMAL,
    failureModes: [],
    attachmentPoints: [
      { id: 'top', accepts: ['body', 'oxidizer_tank'], offset_x: 0, offset_y: 0, offset_z: 0.8 },
      { id: 'bottom', accepts: ['engine', 'body'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
    visual: DEFAULT_VISUAL,
    cost: 200,
    ...overrides,
  };
}

export function makeFin(overrides: Partial<FinDef> & { id: string }): FinDef {
  return {
    name: 'Fin Set',
    description: 'Trapezoidal fin set',
    category: 'fin',
    mass_kg: 3,
    outerDiameter_m: 0.3,
    length_m: 0.2,
    finCount: 4,
    rootChord_m: 0.2,
    tipChord_m: 0.1,
    span_m: 0.15,
    sweepAngle_rad: 0.52,
    airfoil: 'symmetric',
    dragCoefficient: 0.01,
    structural: DEFAULT_STRUCTURAL,
    thermal: DEFAULT_THERMAL,
    failureModes: [],
    attachmentPoints: [
      { id: 'mount', accepts: ['body'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
    visual: DEFAULT_VISUAL,
    cost: 80,
    ...overrides,
  };
}

export function makePayload(overrides: Partial<PayloadDef> & { id: string }): PayloadDef {
  return {
    name: 'Payload',
    description: 'Generic payload',
    category: 'payload',
    mass_kg: 50,
    outerDiameter_m: 0.25,
    length_m: 0.4,
    massAdjustable: true,
    minMass_kg: 10,
    maxMass_kg: 200,
    payloadType: 'satellite',
    structural: DEFAULT_STRUCTURAL,
    thermal: DEFAULT_THERMAL,
    failureModes: [],
    attachmentPoints: [
      { id: 'base', accepts: ['body', 'decoupler'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
    visual: DEFAULT_VISUAL,
    cost: 1000,
    ...overrides,
  };
}

export function makeDecoupler(overrides: Partial<DecouplerDef> & { id: string }): DecouplerDef {
  return {
    name: 'Stage Separator',
    description: 'Pyrotechnic stage separator',
    category: 'decoupler',
    mass_kg: 2,
    outerDiameter_m: 0.3,
    length_m: 0.05,
    separationForce_N: 5000,
    separationTime_s: 0.1,
    isStageSeparator: true,
    structural: DEFAULT_STRUCTURAL,
    thermal: DEFAULT_THERMAL,
    failureModes: [],
    attachmentPoints: [
      { id: 'top', accepts: ['body', 'fuel_tank', 'payload'], offset_x: 0, offset_y: 0, offset_z: 0.05 },
      { id: 'bottom', accepts: ['body', 'fuel_tank'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
    visual: DEFAULT_VISUAL,
    cost: 150,
    ...overrides,
  };
}

export function makeAvionics(overrides: Partial<AvionicsDef> & { id: string }): AvionicsDef {
  return {
    name: 'Flight Computer',
    description: 'Basic flight computer',
    category: 'avionics',
    mass_kg: 2,
    outerDiameter_m: 0.15,
    length_m: 0.1,
    powerConsumption_W: 50,
    hasFlightComputer: true,
    hasTelemetry: true,
    structural: DEFAULT_STRUCTURAL,
    thermal: DEFAULT_THERMAL,
    failureModes: [],
    attachmentPoints: [],
    visual: DEFAULT_VISUAL,
    cost: 300,
    ...overrides,
  };
}
