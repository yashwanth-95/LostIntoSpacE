/**
 * Stock component catalogue.
 *
 * A ready-made parts bin so the builder is usable the moment it loads, and so
 * every team member has the same components to test against.
 *
 * Two size classes are provided, and they are deliberately *not* mixable in a
 * sensible design — the point is that a student picks a class and stays in it:
 *
 * - **S-class**, 0.5 m diameter — sounding rockets. A single S-class stage
 *   reaches roughly 30–80 km, high enough to see max-Q and apogee clearly
 *   without the flight taking ten minutes.
 * - **M-class**, 2.0 m diameter — small orbital launchers. Two M-class stages
 *   with a modest payload have enough delta-v to reach low Earth orbit.
 *
 * ## Where the numbers come from
 *
 * Masses, thrusts, and specific impulses are *representative* of real hardware
 * in each class, rounded to memorable figures. An S-class engine's 280 s
 * sea-level Isp is typical of a kerosene/LOX gas-generator cycle; the M-class
 * vacuum engine's 340 s is typical of a hydrogen upper stage. They are teaching
 * values, not any specific vehicle's spec sheet, and nothing here should be
 * quoted as the performance of a real engine.
 *
 * @module core/catalog
 */

import type {
  ComponentDef,
  BodyDef,
  NoseConeDef,
  EngineDef,
  FuelTankDef,
  OxidizerTankDef,
  AvionicsDef,
  GuidanceDef,
  FinDef,
  PayloadDef,
  DecouplerDef,
  ParachuteDef,
  HeatShieldDef,
  LandingLegDef,
  StructuralProperties,
  ThermalProperties,
  FailureMode,
} from './component-types.js';
import { ComponentRegistry } from './component-registry.js';
import { EXTENDED_COMPONENTS } from './catalog-extended.js';

// ============================================================
// Shared property presets
// ============================================================

// Dynamic-pressure limits carry design margin over what a well-flown vehicle
// actually sees. A sounding rocket peaks near 100–170 kPa on the way up and can
// see more again on a ballistic re-entry, so a solid motor casing and its
// airframe are built for it. Propellant tanks are not: a thin-walled pressure
// vessel is the weakest structure on any liquid vehicle, which is why it gets
// its own, lower limit below.
const AIRFRAME_STRUCTURAL: StructuralProperties = {
  maxAxialLoad_N: 400_000,
  maxLateralLoad_N: 80_000,
  maxDynamicPressure_Pa: 250_000,
};

/** Thin-walled propellant tanks — the weakest structure on a liquid vehicle. */
const TANK_STRUCTURAL: StructuralProperties = {
  maxAxialLoad_N: 300_000,
  maxLateralLoad_N: 50_000,
  maxDynamicPressure_Pa: 150_000,
};

/** Large-vehicle tanks: stronger in absolute terms, still the weakest link. */
const HEAVY_TANK_STRUCTURAL: StructuralProperties = {
  maxAxialLoad_N: 6_000_000,
  maxLateralLoad_N: 900_000,
  maxDynamicPressure_Pa: 90_000,
};

const HEAVY_STRUCTURAL: StructuralProperties = {
  maxAxialLoad_N: 8_000_000,
  maxLateralLoad_N: 1_500_000,
  maxDynamicPressure_Pa: 65_000,
};

const AMBIENT_THERMAL: ThermalProperties = {
  maxTemperature_K: 500,
  thermalMass_JperK: 20_000,
  emissivity: 0.6,
};

const ENGINE_THERMAL: ThermalProperties = {
  maxTemperature_K: 3_600,
  thermalMass_JperK: 90_000,
  emissivity: 0.85,
};

const ENGINE_FAILURE_MODES: readonly FailureMode[] = [
  {
    id: 'combustion_instability',
    name: 'Combustion instability',
    condition: 'Chamber pressure oscillates beyond the injector’s damping capacity',
    severity: 'fatal',
    monitoredParameter: 'chamberPressureOscillation',
    threshold: 0.15,
    thresholdUnit: 'fraction',
  },
  {
    id: 'turbopump_overspeed',
    name: 'Turbopump overspeed',
    condition: 'Pump spins beyond its rated speed and the impeller fails',
    severity: 'fatal',
    monitoredParameter: 'throttle',
    threshold: 1.1,
    thresholdUnit: 'fraction',
  },
];

const TANK_FAILURE_MODES: readonly FailureMode[] = [
  {
    id: 'tank_rupture',
    name: 'Tank rupture',
    condition: 'Internal pressure or aerodynamic load exceeds the wall strength',
    severity: 'fatal',
    monitoredParameter: 'dynamicPressure_Pa',
    threshold: 150_000,
    thresholdUnit: 'Pa',
  },
];

const STRUCTURE_FAILURE_MODES: readonly FailureMode[] = [
  {
    id: 'buckling',
    name: 'Structural buckling',
    condition: 'Axial compression exceeds the airframe’s critical load',
    severity: 'fatal',
    monitoredParameter: 'axialLoad_N',
    threshold: 400_000,
    thresholdUnit: 'N',
  },
];

/** Fill in the fields every definition shares, so the entries below stay readable. */
function base(
  partial: Pick<ComponentDef, 'id' | 'name' | 'description' | 'mass_kg' | 'outerDiameter_m' | 'length_m' | 'cost'> & {
    structural?: StructuralProperties;
    thermal?: ThermalProperties;
    failureModes?: readonly FailureMode[];
    color?: string;
  },
) {
  return {
    id: partial.id,
    name: partial.name,
    description: partial.description,
    mass_kg: partial.mass_kg,
    outerDiameter_m: partial.outerDiameter_m,
    length_m: partial.length_m,
    cost: partial.cost,
    structural: partial.structural ?? AIRFRAME_STRUCTURAL,
    thermal: partial.thermal ?? AMBIENT_THERMAL,
    failureModes: partial.failureModes ?? [],
    visual: {
      assetId: partial.id,
      fallbackProcedural: true,
      color: partial.color ?? '#c8ccd4',
    },
  };
}

/** Attachment points for a component that stacks in line, like a tube. */
function stackPoints(length_m: number) {
  return [
    {
      id: 'top',
      accepts: [
        'nose_cone', 'body', 'decoupler', 'payload', 'fuel_tank',
        'oxidizer_tank', 'avionics', 'guidance', 'parachute', 'heat_shield',
      ] as const,
      offset_x: 0,
      offset_y: 0,
      offset_z: length_m,
    },
    {
      id: 'bottom',
      accepts: [
        'engine', 'body', 'decoupler', 'fin', 'fuel_tank',
        'oxidizer_tank', 'landing_leg', 'heat_shield',
      ] as const,
      offset_x: 0,
      offset_y: 0,
      offset_z: 0,
    },
  ];
}

// ============================================================
// Nose cones
// ============================================================

const NOSE_CONES: readonly NoseConeDef[] = [
  {
    ...base({
      id: 'nose_s_ogive',
      name: 'S-class Ogive Nose',
      description:
        'A tangent-ogive nose for the 0.5 m airframe. The ogive profile has ' +
        'lower drag than a cone of the same length and puts its centre of ' +
        'pressure further forward.',
      mass_kg: 8,
      outerDiameter_m: 0.5,
      length_m: 1.2,
      cost: 400,
      color: '#e8eaee',
    }),
    category: 'nose_cone',
    shape: 'ogive',
    finenessRatio: 2.4,
    dragCoefficient: 0.15,
    attachmentPoints: [
      { id: 'base', accepts: ['body', 'payload'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
  {
    ...base({
      id: 'nose_s_conical',
      name: 'S-class Conical Nose',
      description:
        'A simple straight cone. Easier to build than an ogive and noticeably ' +
        'draggier — a good A/B comparison for a first lesson on nose shape.',
      mass_kg: 6,
      outerDiameter_m: 0.5,
      length_m: 1.0,
      cost: 250,
      color: '#e8eaee',
    }),
    category: 'nose_cone',
    shape: 'conical',
    finenessRatio: 2.0,
    dragCoefficient: 0.25,
    attachmentPoints: [
      { id: 'base', accepts: ['body', 'payload'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
  {
    ...base({
      id: 'nose_m_fairing',
      name: 'M-class Payload Fairing',
      description:
        'A von Kármán (Haack series) fairing for the 2.0 m airframe. The Haack ' +
        'profile is the minimum-drag shape for a given length and base diameter.',
      mass_kg: 320,
      outerDiameter_m: 2.0,
      length_m: 4.5,
      cost: 12_000,
      structural: HEAVY_STRUCTURAL,
      color: '#f2f4f7',
    }),
    category: 'nose_cone',
    shape: 'haack',
    finenessRatio: 2.25,
    dragCoefficient: 0.12,
    attachmentPoints: [
      { id: 'base', accepts: ['body', 'payload', 'decoupler'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
];

// ============================================================
// Body tubes
// ============================================================

const BODIES: readonly BodyDef[] = [
  {
    ...base({
      id: 'body_s_short',
      name: 'S-class Body Tube (1 m)',
      description: 'A one-metre aluminium airframe section for the 0.5 m class.',
      mass_kg: 12,
      outerDiameter_m: 0.5,
      length_m: 1.0,
      cost: 300,
      failureModes: STRUCTURE_FAILURE_MODES,
    }),
    category: 'body',
    innerDiameter_m: 0.48,
    wallThickness_m: 0.01,
    material: 'aluminium 6061',
    attachmentPoints: stackPoints(1.0),
  },
  {
    ...base({
      id: 'body_s_long',
      name: 'S-class Body Tube (3 m)',
      description: 'A three-metre aluminium airframe section for the 0.5 m class.',
      mass_kg: 34,
      outerDiameter_m: 0.5,
      length_m: 3.0,
      cost: 800,
      failureModes: STRUCTURE_FAILURE_MODES,
    }),
    category: 'body',
    innerDiameter_m: 0.48,
    wallThickness_m: 0.01,
    material: 'aluminium 6061',
    attachmentPoints: stackPoints(3.0),
  },
  {
    ...base({
      id: 'body_m_interstage',
      name: 'M-class Interstage',
      description:
        'A load-bearing structure between two M-class stages. It carries the ' +
        'full compressive load of everything above it during first-stage burn.',
      mass_kg: 240,
      outerDiameter_m: 2.0,
      length_m: 2.0,
      cost: 6_000,
      structural: HEAVY_STRUCTURAL,
      failureModes: STRUCTURE_FAILURE_MODES,
    }),
    category: 'body',
    innerDiameter_m: 1.95,
    wallThickness_m: 0.025,
    material: 'aluminium-lithium 2195',
    attachmentPoints: stackPoints(2.0),
  },
];

// ============================================================
// Engines
// ============================================================

const ENGINES: readonly EngineDef[] = [
  {
    ...base({
      id: 'engine_s_solid',
      name: 'S-class Solid Motor',
      description:
        'A solid motor: high thrust, cheap, and impossible to throttle or ' +
        'shut down once lit. Its propellant is cast into the casing, so it ' +
        'needs no separate tanks.',
      mass_kg: 90,
      outerDiameter_m: 0.5,
      length_m: 2.5,
      cost: 2_000,
      thermal: ENGINE_THERMAL,
      failureModes: ENGINE_FAILURE_MODES,
      color: '#8b8f98',
    }),
    category: 'engine',
    // Casing mass above is the *empty* motor; the grain is carried here.
    // 600 kg of grain in a 90 kg casing is a propellant fraction of 0.87,
    // typical for a solid motor of this size. At ~1750 kg/m³ that grain needs
    // roughly 1.75 m of the 2.5 m casing, the rest being dome and nozzle.
    integralPropellant_kg: 600,
    // Thrust is chosen so the motor burns for ~48 s rather than ~34 s. A solid
    // motor cannot throttle, so its acceleration climbs all the way to burnout
    // as propellant leaves; a shorter, harder burn on the same grain would put
    // the vehicle past 15 g in its final seconds.
    thrust_N: 30_000,
    thrustSeaLevel_N: 27_000,
    isp_vacuum_s: 245,
    isp_seaLevel_s: 220,
    propellantType: 'solid',
    nozzleExitArea_m2: 0.04,
    expansionRatio: 8,
    maxIgnitions: 1,
    minThrottle: 1.0,
    gimballed: false,
    maxGimbalAngle_rad: 0,
    attachmentPoints: [
      { id: 'mount', accepts: ['body', 'fuel_tank', 'decoupler'], offset_x: 0, offset_y: 0, offset_z: 2.5 },
    ],
  },
  {
    ...base({
      id: 'engine_s_liquid',
      name: 'S-class Liquid Engine',
      description:
        'A pressure-fed kerosene/LOX engine for the 0.5 m class. Throttleable ' +
        'and restartable, and it needs both a fuel tank and an oxidizer tank.',
      mass_kg: 55,
      outerDiameter_m: 0.45,
      length_m: 1.1,
      cost: 6_000,
      thermal: ENGINE_THERMAL,
      failureModes: ENGINE_FAILURE_MODES,
      color: '#6f747d',
    }),
    category: 'engine',
    integralPropellant_kg: 0,
    thrust_N: 30_000,
    thrustSeaLevel_N: 26_000,
    isp_vacuum_s: 305,
    isp_seaLevel_s: 265,
    propellantType: 'liquid_bipropellant',
    nozzleExitArea_m2: 0.04,
    expansionRatio: 16,
    maxIgnitions: 3,
    minThrottle: 0.6,
    gimballed: true,
    maxGimbalAngle_rad: 0.087,
    attachmentPoints: [
      { id: 'mount', accepts: ['body', 'fuel_tank', 'oxidizer_tank', 'decoupler'], offset_x: 0, offset_y: 0, offset_z: 1.1 },
    ],
  },
  {
    ...base({
      id: 'engine_m_booster',
      name: 'M-class Booster Engine',
      description:
        'A gas-generator kerosene/LOX engine sized for a first stage. High ' +
        'sea-level thrust at the cost of specific impulse — the right trade ' +
        'while the vehicle is still deep in the atmosphere.',
      mass_kg: 4_500,
      outerDiameter_m: 1.8,
      length_m: 3.0,
      cost: 220_000,
      structural: HEAVY_STRUCTURAL,
      thermal: ENGINE_THERMAL,
      failureModes: ENGINE_FAILURE_MODES,
      color: '#5b6069',
    }),
    category: 'engine',
    integralPropellant_kg: 0,
    thrust_N: 2_400_000,
    thrustSeaLevel_N: 2_100_000,
    isp_vacuum_s: 311,
    isp_seaLevel_s: 275,
    propellantType: 'liquid_bipropellant',
    nozzleExitArea_m2: 2.9,
    expansionRatio: 18,
    maxIgnitions: 2,
    minThrottle: 0.55,
    gimballed: true,
    maxGimbalAngle_rad: 0.087,
    attachmentPoints: [
      { id: 'mount', accepts: ['body', 'fuel_tank', 'oxidizer_tank', 'decoupler'], offset_x: 0, offset_y: 0, offset_z: 3.0 },
    ],
  },
  {
    ...base({
      id: 'engine_m_vacuum',
      name: 'M-class Vacuum Engine',
      description:
        'A hydrogen/LOX upper-stage engine with a large expansion ratio. Its ' +
        'oversized nozzle would separate flow at sea level, so it is only ' +
        'useful once the vehicle is out of the thick atmosphere.',
      mass_kg: 900,
      outerDiameter_m: 1.9,
      length_m: 3.4,
      cost: 300_000,
      structural: HEAVY_STRUCTURAL,
      thermal: ENGINE_THERMAL,
      failureModes: ENGINE_FAILURE_MODES,
      color: '#4d525b',
    }),
    category: 'engine',
    integralPropellant_kg: 0,
    thrust_N: 180_000,
    thrustSeaLevel_N: 110_000,
    isp_vacuum_s: 440,
    isp_seaLevel_s: 270,
    propellantType: 'liquid_bipropellant',
    nozzleExitArea_m2: 2.4,
    expansionRatio: 84,
    maxIgnitions: 5,
    minThrottle: 0.4,
    gimballed: true,
    maxGimbalAngle_rad: 0.07,
    attachmentPoints: [
      { id: 'mount', accepts: ['body', 'fuel_tank', 'oxidizer_tank', 'decoupler'], offset_x: 0, offset_y: 0, offset_z: 3.4 },
    ],
  },
];

// ============================================================
// Tanks
// ============================================================

const FUEL_TANKS: readonly FuelTankDef[] = [
  {
    ...base({
      id: 'tank_s_fuel',
      name: 'S-class Fuel Tank',
      description: 'A 2 m kerosene tank for the 0.5 m airframe.',
      mass_kg: 18,
      outerDiameter_m: 0.5,
      length_m: 2.0,
      cost: 900,
      structural: TANK_STRUCTURAL,
      failureModes: TANK_FAILURE_MODES,
      color: '#b7bcc4',
    }),
    category: 'fuel_tank',
    capacity_kg: 260,
    fuelType: 'RP-1',
    fuelDensity_kgm3: 810,
    volume_m3: 0.321,
    pressurization_Pa: 350_000,
    attachmentPoints: stackPoints(2.0),
  },
  {
    ...base({
      id: 'tank_m_fuel',
      name: 'M-class Fuel Tank',
      description: 'A 12 m kerosene tank for the 2.0 m airframe.',
      mass_kg: 2_400,
      outerDiameter_m: 2.0,
      length_m: 12.0,
      cost: 45_000,
      structural: HEAVY_TANK_STRUCTURAL,
      failureModes: TANK_FAILURE_MODES,
      color: '#b7bcc4',
    }),
    category: 'fuel_tank',
    capacity_kg: 29_000,
    fuelType: 'RP-1',
    fuelDensity_kgm3: 810,
    volume_m3: 35.8,
    pressurization_Pa: 300_000,
    attachmentPoints: stackPoints(12.0),
  },
  {
    ...base({
      id: 'tank_m_upper_fuel',
      name: 'M-class Upper Fuel Tank',
      description:
        'A 5 m kerosene tank sized for an upper stage. Upper stages carry far ' +
        'less propellant than boosters — every kilogram up there had to be ' +
        'lifted by the stage below.',
      mass_kg: 500,
      outerDiameter_m: 2.0,
      length_m: 5.0,
      cost: 20_000,
      structural: HEAVY_TANK_STRUCTURAL,
      failureModes: TANK_FAILURE_MODES,
      color: '#b7bcc4',
    }),
    category: 'fuel_tank',
    capacity_kg: 5_000,
    fuelType: 'RP-1',
    fuelDensity_kgm3: 810,
    volume_m3: 6.2,
    pressurization_Pa: 300_000,
    attachmentPoints: stackPoints(5.0),
  },
];

const OXIDIZER_TANKS: readonly OxidizerTankDef[] = [
  {
    ...base({
      id: 'tank_s_ox',
      name: 'S-class Oxidizer Tank',
      description:
        'A 2.5 m liquid-oxygen tank. Bipropellant engines burn far more ' +
        'oxidizer than fuel by mass, so this tank is the larger of the pair.',
      mass_kg: 24,
      outerDiameter_m: 0.5,
      length_m: 2.5,
      cost: 1_100,
      structural: TANK_STRUCTURAL,
      failureModes: TANK_FAILURE_MODES,
      color: '#a9b6c6',
    }),
    category: 'oxidizer_tank',
    capacity_kg: 600,
    oxidizerType: 'LOX',
    oxidizerDensity_kgm3: 1_141,
    volume_m3: 0.526,
    pressurization_Pa: 350_000,
    attachmentPoints: stackPoints(2.5),
  },
  {
    ...base({
      id: 'tank_m_ox',
      name: 'M-class Oxidizer Tank',
      description: 'A 16 m liquid-oxygen tank for the 2.0 m airframe.',
      mass_kg: 3_600,
      outerDiameter_m: 2.0,
      length_m: 16.0,
      cost: 58_000,
      structural: HEAVY_TANK_STRUCTURAL,
      failureModes: TANK_FAILURE_MODES,
      color: '#a9b6c6',
    }),
    category: 'oxidizer_tank',
    capacity_kg: 67_000,
    oxidizerType: 'LOX',
    oxidizerDensity_kgm3: 1_141,
    volume_m3: 58.7,
    pressurization_Pa: 300_000,
    attachmentPoints: stackPoints(16.0),
  },
  {
    ...base({
      id: 'tank_m_upper_ox',
      name: 'M-class Upper Oxidizer Tank',
      description: 'A 7 m liquid-oxygen tank sized for an upper stage.',
      mass_kg: 750,
      outerDiameter_m: 2.0,
      length_m: 7.0,
      cost: 26_000,
      structural: HEAVY_TANK_STRUCTURAL,
      failureModes: TANK_FAILURE_MODES,
      color: '#a9b6c6',
    }),
    category: 'oxidizer_tank',
    capacity_kg: 12_000,
    oxidizerType: 'LOX',
    oxidizerDensity_kgm3: 1_141,
    volume_m3: 10.5,
    pressurization_Pa: 300_000,
    attachmentPoints: stackPoints(7.0),
  },
];

// ============================================================
// Aerodynamic surfaces
// ============================================================

const FINS: readonly FinDef[] = [
  {
    ...base({
      id: 'fin_s_standard',
      name: 'S-class Fin Set (4)',
      description:
        'Four swept trapezoidal fins. Fins move the centre of pressure aft, ' +
        'which is what makes an unguided rocket fly straight.',
      mass_kg: 6,
      outerDiameter_m: 0.5,
      length_m: 0.6,
      cost: 500,
      color: '#8b8f98',
    }),
    category: 'fin',
    finCount: 4,
    rootChord_m: 0.6,
    tipChord_m: 0.25,
    span_m: 0.35,
    sweepAngle_rad: 0.61,
    airfoil: 'symmetric',
    dragCoefficient: 0.012,
    attachmentPoints: [
      { id: 'mount', accepts: ['body', 'fuel_tank', 'oxidizer_tank'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
  {
    ...base({
      id: 'fin_s_large',
      name: 'S-class Large Fin Set (4)',
      description:
        'Oversized fins for maximum stability. They add drag and can make the ' +
        'rocket weathercock into crosswinds — stability has a price.',
      mass_kg: 11,
      outerDiameter_m: 0.5,
      length_m: 0.9,
      cost: 750,
      color: '#8b8f98',
    }),
    category: 'fin',
    finCount: 4,
    rootChord_m: 0.9,
    tipChord_m: 0.4,
    span_m: 0.6,
    sweepAngle_rad: 0.61,
    airfoil: 'symmetric',
    dragCoefficient: 0.022,
    attachmentPoints: [
      { id: 'mount', accepts: ['body', 'fuel_tank', 'oxidizer_tank'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
  {
    ...base({
      id: 'fin_m_grid',
      name: 'M-class Grid Fins (4)',
      description:
        'Lattice control surfaces for the 2.0 m class. They stow flat against ' +
        'the body and work well at supersonic speed, at the cost of high drag.',
      mass_kg: 180,
      outerDiameter_m: 2.0,
      length_m: 1.2,
      cost: 30_000,
      structural: HEAVY_STRUCTURAL,
      color: '#71767f',
    }),
    category: 'fin',
    finCount: 4,
    rootChord_m: 1.2,
    tipChord_m: 1.2,
    span_m: 1.0,
    sweepAngle_rad: 0,
    airfoil: 'flat',
    dragCoefficient: 0.03,
    attachmentPoints: [
      { id: 'mount', accepts: ['body', 'fuel_tank', 'oxidizer_tank'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
];

// ============================================================
// Payloads and systems
// ============================================================

const PAYLOADS: readonly PayloadDef[] = [
  {
    ...base({
      id: 'payload_instrument',
      name: 'Instrument Package',
      description:
        'A small science package for a sounding rocket. Its mass is adjustable ' +
        'so you can watch apogee fall as you load it up.',
      mass_kg: 25,
      outerDiameter_m: 0.45,
      length_m: 0.6,
      cost: 8_000,
      color: '#d4a843',
    }),
    category: 'payload',
    massAdjustable: true,
    minMass_kg: 5,
    maxMass_kg: 150,
    payloadType: 'probe',
    attachmentPoints: [
      { id: 'base', accepts: ['body', 'decoupler'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
  {
    ...base({
      id: 'payload_smallsat',
      name: 'Small Satellite',
      description: 'A 2.0 m-class satellite bus with adjustable mass.',
      mass_kg: 1_200,
      outerDiameter_m: 1.8,
      length_m: 2.2,
      cost: 400_000,
      color: '#d4a843',
    }),
    category: 'payload',
    massAdjustable: true,
    minMass_kg: 100,
    maxMass_kg: 8_000,
    payloadType: 'satellite',
    attachmentPoints: [
      { id: 'base', accepts: ['body', 'decoupler'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
];

const DECOUPLERS: readonly DecouplerDef[] = [
  {
    ...base({
      id: 'decoupler_s',
      name: 'S-class Separator',
      description:
        'A pyrotechnic separation ring. It defines where one stage ends and ' +
        'the next begins, and pushes them apart when it fires.',
      mass_kg: 3,
      outerDiameter_m: 0.5,
      length_m: 0.1,
      cost: 600,
      color: '#c2691f',
      failureModes: [
        {
          id: 'separation_failure',
          name: 'Separation failure',
          condition: 'The pyrotechnic charge fails to sever the joint',
          severity: 'fatal',
          monitoredParameter: 'separationCommanded',
          threshold: 1,
          thresholdUnit: 'boolean',
        },
      ],
    }),
    category: 'decoupler',
    separationForce_N: 6_000,
    separationTime_s: 0.2,
    isStageSeparator: true,
    attachmentPoints: [
      { id: 'top', accepts: ['body', 'fuel_tank', 'oxidizer_tank', 'payload'], offset_x: 0, offset_y: 0, offset_z: 0.1 },
      { id: 'bottom', accepts: ['body', 'fuel_tank', 'oxidizer_tank', 'engine'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
  {
    ...base({
      id: 'decoupler_m',
      name: 'M-class Separation Ring',
      description: 'A frangible-joint separation ring for the 2.0 m airframe.',
      mass_kg: 140,
      outerDiameter_m: 2.0,
      length_m: 0.3,
      cost: 18_000,
      structural: HEAVY_STRUCTURAL,
      color: '#c2691f',
      failureModes: [
        {
          id: 'separation_failure',
          name: 'Separation failure',
          condition: 'The frangible joint fails to fracture cleanly',
          severity: 'fatal',
          monitoredParameter: 'separationCommanded',
          threshold: 1,
          thresholdUnit: 'boolean',
        },
      ],
    }),
    category: 'decoupler',
    separationForce_N: 90_000,
    separationTime_s: 0.4,
    isStageSeparator: true,
    attachmentPoints: [
      { id: 'top', accepts: ['body', 'fuel_tank', 'oxidizer_tank', 'payload'], offset_x: 0, offset_y: 0, offset_z: 0.3 },
      { id: 'bottom', accepts: ['body', 'fuel_tank', 'oxidizer_tank', 'engine'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
];

const AVIONICS: readonly AvionicsDef[] = [
  {
    ...base({
      id: 'avionics_basic',
      name: 'Flight Computer',
      description:
        'Sequences the flight: ignition, staging, and payload deployment. ' +
        'Without one, nothing on board decides when events happen.',
      mass_kg: 4,
      outerDiameter_m: 0.4,
      length_m: 0.3,
      cost: 5_000,
      color: '#3f7a4f',
    }),
    category: 'avionics',
    powerConsumption_W: 45,
    hasFlightComputer: true,
    hasTelemetry: true,
    attachmentPoints: [
      { id: 'base', accepts: ['body', 'payload'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
];

const GUIDANCE: readonly GuidanceDef[] = [
  {
    ...base({
      id: 'guidance_inertial',
      name: 'Inertial Guidance Unit',
      description:
        'Accelerometers and gyroscopes that track attitude with no outside ' +
        'reference. Accurate over a launch, and it drifts slowly over hours.',
      mass_kg: 9,
      outerDiameter_m: 0.4,
      length_m: 0.35,
      cost: 40_000,
      color: '#3f6a7a',
    }),
    category: 'guidance',
    powerConsumption_W: 120,
    guidanceType: 'inertial',
    accuracy_rad: 0.0017,
    attachmentPoints: [
      { id: 'base', accepts: ['body', 'payload'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
];

// ============================================================
// Recovery and thermal protection
// ============================================================

const PARACHUTES: readonly ParachuteDef[] = [
  {
    ...base({
      id: 'parachute_s_main',
      name: 'S-class Main Parachute',
      description:
        'A main canopy for recovering the 0.5 m airframe. Deploying it above ' +
        'its rated speed will tear it.',
      mass_kg: 7,
      outerDiameter_m: 0.45,
      length_m: 0.5,
      cost: 1_500,
      color: '#c94f4f',
    }),
    category: 'parachute',
    canopyDiameter_m: 6.0,
    deployedDragCoefficient: 1.4,
    deployAltitude_m: 800,
    minDeploySpeed_ms: 5,
    maxDeploySpeed_ms: 90,
    parachuteType: 'main',
    attachmentPoints: [
      { id: 'base', accepts: ['body', 'payload'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
];

const HEAT_SHIELDS: readonly HeatShieldDef[] = [
  {
    ...base({
      id: 'heatshield_s',
      name: 'S-class Heat Shield',
      description:
        'An ablative shield for atmospheric entry. It protects by burning ' +
        'away, carrying heat off with the material it loses.',
      mass_kg: 45,
      outerDiameter_m: 0.55,
      length_m: 0.25,
      cost: 20_000,
      thermal: { maxTemperature_K: 3_000, thermalMass_JperK: 400_000, emissivity: 0.9 },
      color: '#4a3b33',
    }),
    category: 'heat_shield',
    ablatorThickness_m: 0.04,
    maxHeatFlux_Wm2: 4_500_000,
    shieldDiameter_m: 0.55,
    attachmentPoints: [
      { id: 'mount', accepts: ['body', 'payload'], offset_x: 0, offset_y: 0, offset_z: 0.25 },
    ],
  },
];

const LANDING_LEGS: readonly LandingLegDef[] = [
  {
    ...base({
      id: 'legs_m',
      name: 'M-class Landing Legs (4)',
      description:
        'Deployable legs for a propulsive landing. They set the maximum touchdown ' +
        'speed the vehicle can survive.',
      mass_kg: 1_100,
      outerDiameter_m: 2.0,
      length_m: 2.5,
      cost: 90_000,
      structural: HEAVY_STRUCTURAL,
      color: '#71767f',
    }),
    category: 'landing_leg',
    legCount: 4,
    deployedLength_m: 4.5,
    maxLandingVelocity_ms: 6,
    autoDeployAltitude_m: 400,
    attachmentPoints: [
      { id: 'mount', accepts: ['body', 'fuel_tank', 'oxidizer_tank'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
];

// ============================================================
// Public catalogue
// ============================================================

/**
 * Every stock component definition, in catalogue order.
 *
 * The core set defined above provides one or two of each category — enough to
 * build something that flies. `catalog-extended.ts` adds the rest: every nose
 * profile and fin planform so the aerodynamic choice is real, solid motors with
 * thrust curves, and the structural, avionics and recovery parts a complete
 * vehicle actually has.
 */
export const STOCK_COMPONENTS: readonly ComponentDef[] = Object.freeze([
  ...NOSE_CONES,
  ...BODIES,
  ...ENGINES,
  ...FUEL_TANKS,
  ...OXIDIZER_TANKS,
  ...FINS,
  ...PAYLOADS,
  ...DECOUPLERS,
  ...AVIONICS,
  ...GUIDANCE,
  ...PARACHUTES,
  ...HEAT_SHIELDS,
  ...LANDING_LEGS,
  ...EXTENDED_COMPONENTS,
]);

/**
 * Build a registry pre-loaded with the stock catalogue.
 *
 * Each call returns a fresh registry, so callers can add their own components
 * without one consumer's additions leaking into another's.
 *
 * @returns A registry containing every stock component.
 */
export function createStockRegistry(): ComponentRegistry {
  const registry = new ComponentRegistry();
  registry.registerAll(STOCK_COMPONENTS);
  return registry;
}
