/**
 * The rest of the parts bin.
 *
 * `catalog.ts` provides a minimal set — one or two of each category — which was
 * enough to prove the builder worked and not enough to design anything with.
 * This module adds the parts that make component choice a real decision:
 *
 * - **Nose cones in every profile**, so the effect of swapping a cone for a von
 *   Kármán on static margin and drag is something a user can go and try.
 * - **Fins in every planform**, for the same reason.
 * - **Solid motors with thrust curves**, because a solid motor is defined by
 *   its curve — startup transient, peak, tail-off — and a rectangle is not a
 *   motor.
 * - **Structure**: couplers, bulkheads, centering rings, motor mounts,
 *   interstages. Small parts with an outsized effect on where mass sits, which
 *   is exactly what stability depends on.
 * - **Avionics and power**: flight computers, individual sensors, batteries.
 * - **Recovery**: drogues and mains sized for each class, with real deployment
 *   speed limits.
 *
 * ## Where the numbers come from
 *
 * As in `catalog.ts`: representative of real hardware in each class, rounded to
 * memorable figures, and never to be quoted as any specific product's spec.
 * The motor thrust curves follow the shape of published certification data for
 * their impulse class — progressive, regressive or neutral burn — rather than
 * reproducing any one manufacturer's motor.
 *
 * @module core/catalog-extended
 */

import type {
  AvionicsDef,
  BatteryDef,
  BulkheadDef,
  CenteringRingDef,
  ComponentDef,
  CouplerDef,
  EngineDef,
  FairingDef,
  FinDef,
  InterstageDef,
  MotorMountDef,
  NoseConeDef,
  ParachuteDef,
  SensorDef,
  StructuralProperties,
  ThermalProperties,
  ThrustCurvePoint,
} from './component-types.js';

// ============================================================
// Shared presets
// ============================================================

const LIGHT_STRUCTURAL: StructuralProperties = {
  maxAxialLoad_N: 90_000,
  maxLateralLoad_N: 22_000,
  maxDynamicPressure_Pa: 260_000,
};

const AIRFRAME_STRUCTURAL: StructuralProperties = {
  maxAxialLoad_N: 400_000,
  maxLateralLoad_N: 110_000,
  maxDynamicPressure_Pa: 320_000,
};

const HEAVY_STRUCTURAL: StructuralProperties = {
  maxAxialLoad_N: 6_000_000,
  maxLateralLoad_N: 1_400_000,
  maxDynamicPressure_Pa: 420_000,
};

const AMBIENT_THERMAL: ThermalProperties = {
  maxTemperature_K: 420,
  thermalMass_JperK: 6_000,
  emissivity: 0.35,
};

const HOT_THERMAL: ThermalProperties = {
  maxTemperature_K: 1_150,
  thermalMass_JperK: 24_000,
  emissivity: 0.75,
};

const MOTOR_THERMAL: ThermalProperties = {
  maxTemperature_K: 3_400,
  thermalMass_JperK: 90_000,
  emissivity: 0.85,
};

/** Fill in the fields every definition shares. */
function base(partial: {
  id: string;
  name: string;
  description: string;
  mass_kg: number;
  outerDiameter_m: number;
  length_m: number;
  cost: number;
  structural?: StructuralProperties;
  thermal?: ThermalProperties;
  color?: string;
}) {
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
    failureModes: [],
    visual: {
      assetId: partial.id,
      fallbackProcedural: true,
      color: partial.color ?? '#c8ccd4',
    },
  };
}

/** In-line stacking attachment points. */
function stackPoints(length_m: number) {
  return [
    {
      id: 'top',
      accepts: [
        'nose_cone', 'fairing', 'body', 'coupler', 'interstage', 'decoupler',
        'payload', 'fuel_tank', 'oxidizer_tank', 'avionics', 'guidance',
        'sensor', 'battery', 'parachute', 'heat_shield', 'bulkhead',
      ] as const,
      offset_x: 0,
      offset_y: 0,
      offset_z: length_m,
    },
    {
      id: 'bottom',
      accepts: [
        'engine', 'motor_mount', 'body', 'coupler', 'interstage', 'decoupler',
        'fin', 'fuel_tank', 'oxidizer_tank', 'landing_leg', 'heat_shield',
        'centering_ring', 'bulkhead',
      ] as const,
      offset_x: 0,
      offset_y: 0,
      offset_z: 0,
    },
  ];
}

function mountPoint(length_m = 0) {
  return [
    {
      id: 'mount',
      accepts: ['body', 'fuel_tank', 'oxidizer_tank', 'coupler', 'interstage'] as const,
      offset_x: 0,
      offset_y: 0,
      offset_z: length_m,
    },
  ];
}

// ============================================================
// Thrust curves
// ============================================================

/**
 * Build a solid-motor thrust curve.
 *
 * Solid motors do not produce constant thrust. The grain's burning surface area
 * changes as it is consumed, and the shape of that change is a design choice:
 *
 * - **progressive** — surface area grows as the grain burns outward, so thrust
 *   rises through the burn. A star-shaped core inverted, or a simple end-burner
 *   bored out.
 * - **regressive** — surface area shrinks, so thrust falls away. The most
 *   common shape for hobby motors: a hard initial kick, then a decay.
 * - **neutral** — a grain geometry chosen so area stays roughly constant, for a
 *   flat curve. Harder to make and what a launch vehicle booster wants.
 *
 * Every curve starts at zero, rises through a short ignition transient, follows
 * its profile, and tails off. Total impulse is the integral, and the caller
 * gets it back so the definition cannot claim an impulse its own curve does not
 * produce.
 */
function solidThrustCurve(
  peakThrust_N: number,
  burnTime_s: number,
  profile: 'progressive' | 'regressive' | 'neutral',
  samples = 24,
): { curve: ThrustCurvePoint[]; totalImpulse_Ns: number; averageThrust_N: number } {
  const curve: ThrustCurvePoint[] = [];
  const ignitionFraction = 0.06;
  const tailFraction = 0.12;

  for (let i = 0; i <= samples; i += 1) {
    const t = (i / samples) * burnTime_s;
    const phase = t / burnTime_s;
    let level: number;

    if (phase < ignitionFraction) {
      // Ignition transient: chamber pressure building.
      level = phase / ignitionFraction;
    } else if (phase > 1 - tailFraction) {
      // Tail-off as the last of the grain is consumed.
      level = (1 - phase) / tailFraction;
    } else {
      const burn = (phase - ignitionFraction) / (1 - ignitionFraction - tailFraction);
      level =
        profile === 'progressive'
          ? 0.62 + 0.38 * burn
          : profile === 'regressive'
            ? 1.0 - 0.42 * burn
            : 0.94 + 0.06 * Math.sin(burn * Math.PI);
    }

    curve.push({ t: round(t, 4), thrust_N: round(peakThrust_N * Math.max(level, 0), 1) });
  }

  // Trapezoidal integration of the curve that will actually be flown, so the
  // published total impulse and the curve can never disagree.
  let impulse = 0;
  for (let i = 1; i < curve.length; i += 1) {
    const a = curve[i - 1];
    const b = curve[i];
    if (!a || !b) continue;
    impulse += ((a.thrust_N + b.thrust_N) / 2) * (b.t - a.t);
  }

  return {
    curve,
    totalImpulse_Ns: round(impulse, 1),
    averageThrust_N: round(impulse / burnTime_s, 1),
  };
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

// ============================================================
// Nose cones — one of every profile
// ============================================================

function noseCone(
  id: string,
  name: string,
  shape: NoseConeDef['shape'],
  diameter_m: number,
  finenessRatio: number,
  mass_kg: number,
  dragCoefficient: number,
  description: string,
  extra: Partial<NoseConeDef> = {},
): NoseConeDef {
  const length_m = round(diameter_m * finenessRatio, 3);
  return {
    ...base({
      id,
      name,
      description,
      mass_kg,
      outerDiameter_m: diameter_m,
      length_m,
      cost: Math.round(mass_kg * 120),
      thermal: HOT_THERMAL,
      color: '#d6d2c8',
    }),
    category: 'nose_cone',
    shape,
    finenessRatio,
    dragCoefficient,
    wallThickness_m: round(diameter_m * 0.006, 4),
    material: 'Aluminium alloy',
    attachmentPoints: [
      { id: 'base', accepts: ['body', 'payload', 'coupler'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
    ...extra,
  };
}

const EXTENDED_NOSE_CONES: readonly NoseConeDef[] = [
  noseCone(
    'nose_s_vonkarman', 'S-class von Kármán', 'von_karman', 0.5, 4.0, 3.4, 0.28,
    'The minimum-drag profile for a given length and base diameter at supersonic ' +
    'speed. If the vehicle is going past Mach 1, this is the shape to beat.',
    { shapeParameter: 0 },
  ),
  noseCone(
    'nose_s_tangent', 'S-class Tangent Ogive', 'tangent_ogive', 0.5, 3.5, 3.1, 0.31,
    'A circular arc that meets the body with no corner. The most common profile ' +
    'on real vehicles, and easy to make on a lathe.',
  ),
  noseCone(
    'nose_s_secant', 'S-class Secant Ogive', 'secant_ogive', 0.5, 3.5, 3.2, 0.33,
    'An ogive that meets the body at a visible angle, trading a small drag penalty ' +
    'for more internal volume forward.',
    { shapeParameter: 1.35 },
  ),
  noseCone(
    'nose_s_elliptical', 'S-class Elliptical', 'elliptical', 0.5, 2.5, 2.6, 0.42,
    'Blunt, with a lot of volume carried forward. Good subsonic drag and a CP ' +
    'a third of the way back, which pulls the static margin down noticeably.',
  ),
  noseCone(
    'nose_s_parabolic', 'S-class Parabolic', 'parabolic', 0.5, 3.0, 2.9, 0.34,
    'Between a cone and an ellipse. The K parameter sets where on that spectrum ' +
    'it sits; 0.75 is the usual compromise.',
    { shapeParameter: 0.75 },
  ),
  noseCone(
    'nose_s_power', 'S-class Power Series', 'power_series', 0.5, 3.0, 2.8, 0.36,
    'r = R·(x/L)^n. At n = 0.5 the profile is blunt at the tip and flat toward the ' +
    'base — the "half-power" shape.',
    { shapeParameter: 0.5 },
  ),
  noseCone(
    'nose_s_blunt', 'S-class Blunted Cone', 'blunt', 0.5, 2.2, 3.8, 0.48,
    'A cone with a hemispherical cap. Blunt costs drag and buys survivable heating ' +
    'at high Mach — the reason re-entry vehicles are not sharp.',
    { shapeParameter: 0.3, tipRadius_m: 0.03 },
  ),
  noseCone(
    'nose_m_vonkarman', 'M-class von Kármán Fairing', 'von_karman', 2.0, 3.0, 285, 0.26,
    'A minimum-drag payload fairing. On most launch vehicles this is the widest ' +
    'part of the stack, so its diameter drives the whole drag budget.',
    { shapeParameter: 0, isSeparable: true },
  ),
  noseCone(
    'nose_m_tangent', 'M-class Tangent Ogive Fairing', 'tangent_ogive', 2.0, 2.6, 265, 0.29,
    'A conventional ogive fairing. Slightly more drag than von Kármán, slightly ' +
    'more usable volume.',
    { isSeparable: true },
  ),
  noseCone(
    'nose_m_conical', 'M-class Conical Fairing', 'conical', 2.0, 2.4, 240, 0.38,
    'The simplest profile to manufacture, and the worst aerodynamically. Its CP ' +
    'sits two-thirds aft, which is the most stabilising of any nose.',
  ),
];

// ============================================================
// Fins — one of every planform
// ============================================================

function finSet(
  id: string,
  name: string,
  shape: FinDef['shape'],
  diameter_m: number,
  finCount: number,
  rootChord_m: number,
  tipChord_m: number,
  span_m: number,
  sweepDeg: number,
  mass_kg: number,
  dragCoefficient: number,
  description: string,
): FinDef {
  return {
    ...base({
      id,
      name,
      description,
      mass_kg,
      outerDiameter_m: diameter_m,
      length_m: rootChord_m,
      cost: Math.round(mass_kg * 240),
      structural: LIGHT_STRUCTURAL,
      color: '#9aa0a8',
    }),
    category: 'fin',
    shape,
    finCount,
    rootChord_m,
    tipChord_m,
    span_m,
    sweepAngle_rad: (sweepDeg * Math.PI) / 180,
    thickness_m: round(diameter_m * 0.012, 4),
    airfoil: 'symmetric',
    dragCoefficient,
    positionFromRear_m: 0,
    material: 'Carbon composite',
    attachmentPoints: [
      {
        id: 'mount',
        accepts: ['body', 'fuel_tank', 'oxidizer_tank'] as const,
        offset_x: 0,
        offset_y: 0,
        offset_z: 0,
      },
    ],
  };
}

const EXTENDED_FINS: readonly FinDef[] = [
  finSet('fin_s_trapezoid', 'S-class Trapezoidal (3)', 'trapezoidal', 0.5, 3,
    0.34, 0.17, 0.22, 25, 1.5, 0.010,
    'The general-purpose planform. Swept enough to keep the tips out of the shock ' +
    'and tapered enough to keep the tip mass down.'),
  finSet('fin_s_delta', 'S-class Delta (3)', 'delta', 0.5, 3,
    0.40, 0.0, 0.24, 40, 1.7, 0.011,
    'No tip chord at all. Puts the fin CP well aft, which is the most stabilising ' +
    'planform for a given area — at the cost of a fragile tip.'),
  finSet('fin_s_clipped', 'S-class Clipped Delta (4)', 'clipped_delta', 0.5, 4,
    0.36, 0.10, 0.22, 35, 2.1, 0.013,
    'A delta with the point cut off, which recovers most of the stability and ' +
    'loses the vulnerable tip. Four fins for redundancy.'),
  finSet('fin_s_elliptical', 'S-class Elliptical (3)', 'elliptical', 0.5, 3,
    0.32, 0.0, 0.22, 0, 1.4, 0.008,
    'The lowest induced drag for a given area. Harder to make, and the reason ' +
    'the Spitfire looked the way it did.'),
  finSet('fin_s_swept', 'S-class Highly Swept (3)', 'swept', 0.5, 3,
    0.30, 0.12, 0.26, 55, 1.6, 0.009,
    'A steep leading-edge sweep keeps the fin behind the shock cone at high Mach, ' +
    'delaying the transonic drag rise.'),
  finSet('fin_s_rect', 'S-class Rectangular (4)', 'rectangular', 0.5, 4,
    0.28, 0.28, 0.20, 0, 2.0, 0.014,
    'The simplest fin to cut. More drag than anything tapered, and the tip mass ' +
    'sits at the worst possible radius for roll inertia.'),
  finSet('fin_m_trapezoid', 'M-class Trapezoidal (4)', 'trapezoidal', 2.0, 4,
    1.60, 0.80, 1.10, 30, 210, 0.012,
    'Large aerodynamic surfaces for an orbital first stage. Adds real drag, and ' +
    'buys stability through the part of the flight where it is scarcest.'),
  finSet('fin_m_gridfin', 'M-class Grid Fins (4)', 'grid', 2.0, 4,
    1.20, 1.20, 0.95, 0, 190, 0.028,
    'A lattice rather than a plate. Far more control authority per unit span at ' +
    'high Mach, and considerably more drag — which is why they fold flat during ' +
    'ascent and only deploy for the descent.'),
];

// ============================================================
// Solid motors, with curves
// ============================================================

/**
 * Build a solid motor from its curve.
 *
 * Propellant mass is *derived*, not declared: total impulse, specific impulse
 * and propellant mass are related by I = m·Isp·g₀, so any two of them fix the
 * third. Declaring all three by hand is how a motor ends up advertising an
 * impulse its own propellant load cannot produce — which is exactly what the
 * catalogue integrity test caught here, at a factor of 2.09.
 *
 * Deriving it means the curve is the single source of truth. Change the peak
 * thrust or the burn time and the propellant load follows automatically.
 */
function solidMotor(
  id: string,
  name: string,
  designation: string,
  motorClass: EngineDef['motorClass'],
  diameter_m: number,
  length_m: number,
  casingMass_kg: number,
  peakThrust_N: number,
  burnTime_s: number,
  isp_s: number,
  profile: 'progressive' | 'regressive' | 'neutral',
  description: string,
): EngineDef {
  const { curve, totalImpulse_Ns, averageThrust_N } = solidThrustCurve(
    peakThrust_N,
    burnTime_s,
    profile,
  );
  const propellantMass_kg = round(totalImpulse_Ns / (isp_s * 9.80665), 4);
  const exitArea = Math.PI * (diameter_m * 0.34) ** 2;
  return {
    ...base({
      id,
      name,
      description,
      mass_kg: casingMass_kg,
      outerDiameter_m: diameter_m,
      length_m,
      cost: Math.round((casingMass_kg + propellantMass_kg) * 320),
      thermal: MOTOR_THERMAL,
      structural: AIRFRAME_STRUCTURAL,
      color: '#8d8378',
    }),
    category: 'engine',
    integralPropellant_kg: propellantMass_kg,
    thrust_N: round(averageThrust_N * 1.12, 0),
    thrustSeaLevel_N: averageThrust_N,
    isp_vacuum_s: round(isp_s * 1.1, 1),
    isp_seaLevel_s: isp_s,
    propellantType: 'solid',
    nozzleExitArea_m2: round(exitArea, 5),
    expansionRatio: 8,
    maxIgnitions: 1,
    minThrottle: 1,
    gimballed: false,
    maxGimbalAngle_rad: 0,
    thrustCurve: curve,
    burnTime_s,
    totalImpulse_Ns,
    averageThrust_N,
    maxThrust_N: peakThrust_N,
    motorClass,
    designation,
    // A solid motor cannot be shut down. Once the grain is lit it burns to
    // completion, which is the single most important operational fact about it.
    canShutdown: false,
    throttleable: false,
    attachmentPoints: [
      {
        id: 'mount',
        accepts: ['body', 'motor_mount', 'coupler', 'decoupler'] as const,
        offset_x: 0,
        offset_y: 0,
        offset_z: length_m,
      },
    ],
  };
}

const SOLID_MOTORS: readonly EngineDef[] = [
  solidMotor('motor_s_h128', 'H128 Composite Motor', 'H128', 'H', 0.29, 0.30, 0.09,
    155, 2.2, 195, 'regressive',
    'A single-use composite motor. Regressive burn: a hard initial kick that ' +
    'decays, which is what most hobby motors do.'),
  solidMotor('motor_s_j350', 'J350 Composite Motor', 'J350', 'J', 0.38, 0.45, 0.22,
    420, 2.8, 210, 'regressive',
    'Roughly twice the total impulse of an H. The J is where a certification ' +
    'requirement usually starts to apply.'),
  solidMotor('motor_s_k560', 'K560 Composite Motor', 'K560', 'K', 0.54, 0.62, 0.55,
    690, 3.6, 218, 'neutral',
    'A neutral-burn grain: thrust stays close to flat through the burn, which ' +
    'makes the acceleration profile far easier to reason about.'),
  solidMotor('motor_s_m1500', 'M1500 High-Power Motor', 'M1500', 'M', 0.75, 1.05, 2.4,
    1_950, 5.0, 224, 'progressive',
    'A progressive grain: thrust rises through the burn as the burning surface ' +
    'grows. Gentle off the pad, hard by the end.'),
  solidMotor('motor_m_booster', 'M-class Strap-on Booster', 'SRB-2', 'orbital', 1.6, 14.0,
    5_800, 1_420_000, 62, 245, 'neutral',
    'A large segmented solid booster. Enormous thrust, no throttle, and no way ' +
    'to shut it down once lit — which is why crewed vehicles that use them need ' +
    'an escape system that can outrun one.'),
];

// ============================================================
// Structure
// ============================================================

const COUPLERS: readonly CouplerDef[] = [
  {
    ...base({
      id: 'coupler_s', name: 'S-class Coupler',
      description:
        'Joins two body tubes end to end. It slips inside both, so its outer ' +
        'diameter is the inner diameter of the tubes it links.',
      mass_kg: 0.35, outerDiameter_m: 0.485, length_m: 0.20, cost: 180,
      structural: LIGHT_STRUCTURAL, color: '#7f8a94',
    }),
    category: 'coupler',
    insertionDepth_m: 0.09,
    wallThickness_m: 0.003,
    material: 'Phenolic',
    loadBearing: true,
    attachmentPoints: stackPoints(0.20),
  },
  {
    ...base({
      id: 'coupler_m', name: 'M-class Coupler',
      description: 'A load-bearing joint between two orbital-class tube sections.',
      mass_kg: 46, outerDiameter_m: 1.96, length_m: 0.55, cost: 22_000,
      structural: HEAVY_STRUCTURAL, color: '#7f8a94',
    }),
    category: 'coupler',
    insertionDepth_m: 0.24,
    wallThickness_m: 0.012,
    material: 'Aluminium-lithium',
    loadBearing: true,
    attachmentPoints: stackPoints(0.55),
  },
];

const INTERSTAGES: readonly InterstageDef[] = [
  {
    ...base({
      id: 'interstage_m', name: 'M-class Interstage',
      description:
        'Carries load between two stages until separation. Vented, so an upper ' +
        'stage can light before it separates.',
      mass_kg: 340, outerDiameter_m: 2.0, length_m: 2.4, cost: 120_000,
      structural: HEAVY_STRUCTURAL, thermal: HOT_THERMAL, color: '#6f767f',
    }),
    category: 'interstage',
    forwardDiameter_m: 2.0,
    aftDiameter_m: 2.0,
    wallThickness_m: 0.014,
    material: 'Aluminium-lithium',
    ventedForHotStaging: true,
    attachmentPoints: stackPoints(2.4),
  },
  {
    ...base({
      id: 'interstage_m_taper', name: 'M-class Tapered Interstage',
      description:
        'A transition between a 2.0 m core and a narrower upper stage. Every ' +
        'diameter change is drag, so a taper is only worth it when the stages ' +
        'genuinely differ.',
      mass_kg: 300, outerDiameter_m: 2.0, length_m: 1.8, cost: 105_000,
      structural: HEAVY_STRUCTURAL, thermal: HOT_THERMAL, color: '#6f767f',
    }),
    category: 'interstage',
    forwardDiameter_m: 1.4,
    aftDiameter_m: 2.0,
    wallThickness_m: 0.012,
    material: 'Aluminium-lithium',
    ventedForHotStaging: false,
    attachmentPoints: stackPoints(1.8),
  },
];

const BULKHEADS: readonly BulkheadDef[] = [
  {
    ...base({
      id: 'bulkhead_s', name: 'S-class Bulkhead',
      description:
        'A disc closing off a tube section and carrying load across it. Also what ' +
        'a recovery harness anchors to.',
      mass_kg: 0.12, outerDiameter_m: 0.485, length_m: 0.008, cost: 60,
      structural: LIGHT_STRUCTURAL, color: '#5f6873',
    }),
    category: 'bulkhead',
    thickness_m: 0.008,
    material: 'Plywood laminate',
    pressureSealing: false,
    loadCapacity_N: 12_000,
    boreDiameter_m: 0,
    attachmentPoints: mountPoint(0.008),
  },
  {
    ...base({
      id: 'bulkhead_m', name: 'M-class Pressure Bulkhead',
      description:
        'A sealing dome between two propellant volumes. A common bulkhead saves ' +
        'the length and mass of two separate tank domes.',
      mass_kg: 180, outerDiameter_m: 1.96, length_m: 0.35, cost: 95_000,
      structural: HEAVY_STRUCTURAL, color: '#5f6873',
    }),
    category: 'bulkhead',
    thickness_m: 0.010,
    material: 'Aluminium-lithium',
    pressureSealing: true,
    loadCapacity_N: 1_800_000,
    boreDiameter_m: 0.12,
    attachmentPoints: mountPoint(0.35),
  },
];

const CENTERING_RINGS: readonly CenteringRingDef[] = [
  {
    ...base({
      id: 'ring_s_29', name: 'S-class Centering Ring (29 mm)',
      description:
        'Holds a 29 mm motor mount concentric inside a 0.5 m airframe. Small, ' +
        'and it decides where the motor thrust enters the structure.',
      mass_kg: 0.05, outerDiameter_m: 0.485, length_m: 0.006, cost: 25,
      structural: LIGHT_STRUCTURAL, color: '#5f6873',
    }),
    category: 'centering_ring',
    outerFitDiameter_m: 0.485,
    innerFitDiameter_m: 0.029,
    thickness_m: 0.006,
    material: 'Plywood laminate',
    attachmentPoints: mountPoint(0.006),
  },
  {
    ...base({
      id: 'ring_s_54', name: 'S-class Centering Ring (54 mm)',
      description: 'For a 54 mm motor mount inside a 0.5 m airframe.',
      mass_kg: 0.06, outerDiameter_m: 0.485, length_m: 0.006, cost: 28,
      structural: LIGHT_STRUCTURAL, color: '#5f6873',
    }),
    category: 'centering_ring',
    outerFitDiameter_m: 0.485,
    innerFitDiameter_m: 0.054,
    thickness_m: 0.006,
    material: 'Plywood laminate',
    attachmentPoints: mountPoint(0.006),
  },
];

const MOTOR_MOUNTS: readonly MotorMountDef[] = [
  {
    ...base({
      id: 'mount_s_single', name: 'S-class Motor Mount',
      description:
        'The tube a motor sits in, transferring its thrust into the airframe. ' +
        'Includes a retainer, so the motor cannot be ejected out the back at ' +
        'ignition.',
      mass_kg: 0.28, outerDiameter_m: 0.075, length_m: 0.55, cost: 240,
      structural: AIRFRAME_STRUCTURAL, thermal: HOT_THERMAL, color: '#6c7079',
    }),
    category: 'motor_mount',
    motorDiameter_m: 0.054,
    motorLength_m: 0.50,
    motorCount: 1,
    thrustCapacity_N: 3_500,
    hasRetainer: true,
    material: 'Phenolic with aluminium retainer',
    attachmentPoints: mountPoint(0.55),
  },
  {
    ...base({
      id: 'mount_m_cluster', name: 'M-class Engine Cluster Mount',
      description:
        'A thrust structure holding four engines and spreading their load into ' +
        'the tank skirt. Clustering buys redundancy: one engine out need not end ' +
        'the mission.',
      mass_kg: 720, outerDiameter_m: 2.0, length_m: 1.1, cost: 380_000,
      structural: HEAVY_STRUCTURAL, thermal: HOT_THERMAL, color: '#6c7079',
    }),
    category: 'motor_mount',
    motorDiameter_m: 0.85,
    motorLength_m: 2.4,
    motorCount: 4,
    thrustCapacity_N: 4_200_000,
    hasRetainer: true,
    material: 'Titanium truss',
    attachmentPoints: mountPoint(1.1),
  },
];

// ============================================================
// Avionics, sensors and power
// ============================================================

const EXTENDED_AVIONICS: readonly AvionicsDef[] = [
  {
    ...base({
      id: 'fc_s_basic', name: 'S-class Flight Computer',
      description:
        'Barometric apogee detection and recovery deployment, plus a telemetry ' +
        'downlink. The minimum a recoverable vehicle needs.',
      mass_kg: 0.09, outerDiameter_m: 0.05, length_m: 0.09, cost: 900,
      structural: LIGHT_STRUCTURAL, color: '#4d7d63',
    }),
    category: 'avionics',
    powerConsumption_W: 1.2,
    hasFlightComputer: true,
    hasTelemetry: true,
    attachmentPoints: mountPoint(0.09),
  },
  {
    ...base({
      id: 'fc_m_redundant', name: 'M-class Triple-Redundant Flight Computer',
      description:
        'Three computers voting on every command. A single computer that fails ' +
        'ends the mission; three that disagree can outvote the faulty one.',
      mass_kg: 34, outerDiameter_m: 0.55, length_m: 0.42, cost: 480_000,
      structural: AIRFRAME_STRUCTURAL, color: '#4d7d63',
    }),
    category: 'avionics',
    powerConsumption_W: 210,
    hasFlightComputer: true,
    hasTelemetry: true,
    attachmentPoints: mountPoint(0.42),
  },
];

function sensor(
  id: string,
  name: string,
  kind: SensorDef['sensorKind'],
  mass_kg: number,
  sampleRate_Hz: number,
  range: number,
  rangeUnit: string,
  accuracy: number,
  power_W: number,
  cost: number,
  description: string,
): SensorDef {
  return {
    ...base({
      id, name, description, mass_kg,
      outerDiameter_m: 0.04, length_m: 0.03, cost,
      structural: LIGHT_STRUCTURAL, color: '#5b7f96',
    }),
    category: 'sensor',
    sensorKind: kind,
    sampleRate_Hz,
    range,
    rangeUnit,
    accuracy,
    powerConsumption_W: power_W,
    attachmentPoints: mountPoint(0.03),
  };
}

const SENSORS: readonly SensorDef[] = [
  sensor('sensor_accel', 'Three-Axis Accelerometer', 'accelerometer', 0.012, 1000, 200, 'g', 0.05, 0.15, 220,
    'Measures the acceleration the vehicle actually experiences. High sample rates ' +
    'matter here: staging and ignition transients happen in milliseconds.'),
  sensor('sensor_gyro', 'Rate Gyroscope', 'gyroscope', 0.014, 1000, 2000, '°/s', 0.5, 0.2, 280,
    'Angular rate about all three axes. Integrating it gives attitude, and the ' +
    'integration drifts, which is why it is paired with something absolute.'),
  sensor('sensor_baro', 'Barometric Altimeter', 'barometer', 0.008, 50, 110_000, 'Pa', 10, 0.05, 90,
    'Altitude from static pressure. Cheap and accurate low down; useless above ' +
    'about 30 km where there is not enough air to measure.'),
  sensor('sensor_gps', 'GNSS Receiver', 'gps', 0.035, 10, 50_000, 'm', 2.5, 0.8, 640,
    'Absolute position, which is what stops inertial drift accumulating. Most ' +
    'civilian receivers stop working above 18 km or 515 m/s under export rules.'),
  sensor('sensor_mag', 'Magnetometer', 'magnetometer', 0.006, 100, 800, 'µT', 0.5, 0.04, 110,
    'Measures the local magnetic field for absolute heading. Easily upset by ' +
    'current flowing anywhere nearby.'),
  sensor('sensor_thermo', 'Type-K Thermocouple', 'thermocouple', 0.004, 20, 1600, 'K', 2, 0.02, 45,
    'Surface or chamber temperature. The channel that tells you a thermal ' +
    'protection system is being consumed faster than planned.'),
  sensor('sensor_pressure', 'Chamber Pressure Transducer', 'pressure_transducer', 0.05, 500, 25e6, 'Pa', 5000, 0.3, 850,
    'Combustion chamber pressure. The first place an engine problem shows up, ' +
    'usually well before thrust visibly changes.'),
  sensor('sensor_strain', 'Structural Strain Gauge', 'strain_gauge', 0.003, 200, 5000, 'µε', 5, 0.02, 130,
    'Local structural strain. Turns "the airframe felt a load" into a number you ' +
    'can compare against what it was designed for.'),
  sensor('sensor_camera', 'Onboard Camera', 'camera', 0.11, 60, 4096, 'px', 1, 2.4, 380,
    'Not instrumentation, exactly — but staging, fairing separation and parachute ' +
    'deployment are all far easier to diagnose when you can see them.'),
];

const BATTERIES: readonly BatteryDef[] = [
  {
    ...base({
      id: 'battery_s_lipo', name: 'S-class LiPo Pack',
      description:
        'A small lithium-polymer pack for avionics and recovery charges. Loses ' +
        'capacity fast in the cold, which matters at altitude.',
      mass_kg: 0.055, outerDiameter_m: 0.04, length_m: 0.07, cost: 60,
      structural: LIGHT_STRUCTURAL, color: '#8a6a3f',
    }),
    category: 'battery',
    capacity_Wh: 4.2,
    voltage_V: 11.1,
    maxCurrent_A: 12,
    chemistry: 'lipo',
    minOperatingTemperature_K: 258,
    attachmentPoints: mountPoint(0.07),
  },
  {
    ...base({
      id: 'battery_m_silverzinc', name: 'M-class Silver-Zinc Battery',
      description:
        'High energy density and a very high discharge rate, at the price of a ' +
        'short shelf life. The chemistry launch vehicles have used for decades.',
      mass_kg: 68, outerDiameter_m: 0.45, length_m: 0.55, cost: 140_000,
      structural: AIRFRAME_STRUCTURAL, color: '#8a6a3f',
    }),
    category: 'battery',
    capacity_Wh: 2_800,
    voltage_V: 28,
    maxCurrent_A: 220,
    chemistry: 'silver_zinc',
    minOperatingTemperature_K: 253,
    attachmentPoints: mountPoint(0.55),
  },
];

// ============================================================
// Recovery
// ============================================================

function parachute(
  id: string,
  name: string,
  type: ParachuteDef['parachuteType'],
  canopyDiameter_m: number,
  diameter_m: number,
  length_m: number,
  mass_kg: number,
  deployAltitude_m: number,
  maxDeploySpeed_ms: number,
  cost: number,
  description: string,
): ParachuteDef {
  return {
    ...base({
      id, name, description, mass_kg,
      outerDiameter_m: diameter_m, length_m, cost,
      structural: LIGHT_STRUCTURAL, color: '#b0603f',
    }),
    category: 'parachute',
    canopyDiameter_m,
    deployedDragCoefficient: type === 'drogue' ? 1.1 : 1.5,
    deployAltitude_m,
    minDeploySpeed_ms: 0,
    maxDeploySpeed_ms,
    parachuteType: type,
    attachmentPoints: mountPoint(length_m),
  };
}

const EXTENDED_PARACHUTES: readonly ParachuteDef[] = [
  parachute('chute_s_drogue', 'S-class Drogue', 'drogue', 0.6, 0.44, 0.12, 0.18, 100_000, 180, 140,
    'Deployed at apogee. Its job is stability, not deceleration: it keeps the ' +
    'vehicle from tumbling while letting it fall fast through thin air, where a ' +
    'main would drift for kilometres.'),
  parachute('chute_s_main', 'S-class Main', 'main', 2.4, 0.46, 0.22, 0.62, 400, 45, 380,
    'Deployed low, around 400 m. Opening it high means a long drifting descent ' +
    'and a much larger opening shock in denser air at higher speed.'),
  parachute('chute_s_main_large', 'S-class Oversized Main', 'main', 3.6, 0.47, 0.30, 1.05, 350, 38, 620,
    'A larger canopy for a heavier vehicle. Terminal velocity falls with the ' +
    'square root of area, so halving the impact speed needs four times the chute.'),
  parachute('chute_m_drogue', 'M-class Drogue Cluster', 'drogue', 8.4, 1.4, 0.9, 96, 8_000, 160, 42_000,
    'Two drogues stabilising a capsule-class descent from high altitude.'),
  parachute('chute_m_main', 'M-class Main Cluster', 'main', 34.0, 1.6, 1.4, 380, 3_000, 60, 210_000,
    'Three reefed mains, opening in stages so the shock load is spread rather ' +
    'than arriving all at once. Apollo used exactly this arrangement.'),
];

// ============================================================
// Fairings
// ============================================================

const FAIRINGS: readonly FairingDef[] = [
  {
    ...base({
      id: 'fairing_m_standard', name: 'M-class Payload Fairing',
      description:
        'Two halves protecting the payload through the atmosphere, jettisoned ' +
        'once heating drops. After that it is pure dead mass, so it goes as ' +
        'early as the payload can survive.',
      mass_kg: 420, outerDiameter_m: 2.4, length_m: 6.0, cost: 480_000,
      structural: AIRFRAME_STRUCTURAL, thermal: HOT_THERMAL, color: '#e0dcd2',
    }),
    category: 'fairing',
    usableDiameter_m: 2.15,
    usableLength_m: 4.4,
    segments: 2,
    jettisonAltitude_m: 110_000,
    shape: 'von_karman',
    material: 'Carbon composite with acoustic blankets',
    attachmentPoints: [
      { id: 'base', accepts: ['body', 'payload', 'coupler', 'interstage'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
  {
    ...base({
      id: 'fairing_m_wide', name: 'M-class Extended Fairing',
      description:
        'A wider fairing for a bulky payload. Frontal area goes as the square of ' +
        'diameter, so this is the single most expensive aerodynamic decision ' +
        'available in the builder.',
      mass_kg: 610, outerDiameter_m: 3.2, length_m: 7.5, cost: 720_000,
      structural: AIRFRAME_STRUCTURAL, thermal: HOT_THERMAL, color: '#e0dcd2',
    }),
    category: 'fairing',
    usableDiameter_m: 2.9,
    usableLength_m: 5.6,
    segments: 2,
    jettisonAltitude_m: 115_000,
    shape: 'tangent_ogive',
    material: 'Carbon composite',
    attachmentPoints: [
      { id: 'base', accepts: ['body', 'payload', 'coupler', 'interstage'], offset_x: 0, offset_y: 0, offset_z: 0 },
    ],
  },
];

// ============================================================
// Public
// ============================================================

/** Everything this module adds to the stock parts bin. */
export const EXTENDED_COMPONENTS: readonly ComponentDef[] = Object.freeze([
  ...EXTENDED_NOSE_CONES,
  ...FAIRINGS,
  ...COUPLERS,
  ...INTERSTAGES,
  ...SOLID_MOTORS,
  ...MOTOR_MOUNTS,
  ...EXTENDED_FINS,
  ...BULKHEADS,
  ...CENTERING_RINGS,
  ...EXTENDED_AVIONICS,
  ...SENSORS,
  ...BATTERIES,
  ...EXTENDED_PARACHUTES,
]);

export { solidThrustCurve };
