/**
 * Assembling a `.rkt` project from a design.
 *
 * The builder works on a {@link RocketDesign} — an editor's document, shaped
 * for editing. A `.rkt` file additionally carries the *engineering* view of
 * that design: the stage table with its separation conditions, the motor list
 * with its thrust profiles, the fin geometry, the stability parameters. Those
 * are all derivable from the design plus the catalogue, and deriving them here
 * rather than asking the user to maintain them is what stops a project file
 * from disagreeing with itself.
 *
 * Everything derived is recomputed on save. A project file therefore always
 * describes the vehicle it actually contains, even if it was hand-edited in
 * between.
 *
 * @module integration/rkt-project
 */

import { analyzeRocket, type RocketAnalysis } from '../core/builder.js';
import type { ComponentRegistry } from '../core/component-registry.js';
import type {
  EngineDef,
  FinDef,
  NoseConeDef,
  RocketDesign,
} from '../core/component-types.js';
import type { MissionConfig } from '../core/types.js';
import {
  RKT_FORMAT_VERSION,
  RKT_SCHEMA_VERSION,
  type RktAerodynamics,
  type RktComponent,
  type RktEnvironment,
  type RktMetadata,
  type RktMission,
  type RktMotor,
  type RktProject,
  type RktPropulsion,
  type RktResults,
  type RktSimulation,
  type RktStage,
  type RktThrustProfile,
  type RktVehicle,
} from './rkt-schema.js';

/** What this build stamps into the files it writes. */
export const RKT_GENERATOR = '@lostintospace/simulation-engine 0.2.0';

export interface BuildRktProjectInput {
  readonly design: RocketDesign;
  readonly mission: MissionConfig;
  /** Needed to resolve component definitions and derive the engineering view. */
  readonly registry: ComponentRegistry;
  readonly metadata?: Partial<RktMetadata>;
  readonly environment?: Partial<RktEnvironment>;
  readonly simulation?: Partial<RktSimulation>;
  /** Results from a completed run, if there are any. */
  readonly results?: RktResults;
  /** Fixed timestamp, so a test can produce a byte-identical file. */
  readonly now?: string;
}

/**
 * Build a complete project document from a design and a mission.
 *
 * @returns A project ready to serialise, with every derived block recomputed.
 */
export function buildRktProject(input: BuildRktProjectInput): RktProject {
  const { design, mission, registry } = input;
  const analysis = analyzeRocket(design, registry);
  const now = input.now ?? new Date().toISOString();

  const metadata: RktMetadata = {
    formatVersion: RKT_FORMAT_VERSION,
    schemaVersion: RKT_SCHEMA_VERSION,
    projectId: input.metadata?.projectId ?? design.id,
    name: input.metadata?.name ?? design.name,
    description: input.metadata?.description ?? design.description,
    author: input.metadata?.author ?? '',
    createdAt: input.metadata?.createdAt ?? design.createdAt ?? now,
    updatedAt: now,
    generator: input.metadata?.generator ?? RKT_GENERATOR,
    tags: input.metadata?.tags ?? [],
  };

  const project: RktProject = {
    metadata,
    vehicle: deriveVehicle(design, registry, analysis),
    propulsion: derivePropulsion(design, registry),
    aerodynamics: deriveAerodynamics(design, registry, analysis),
    avionics: deriveAvionics(design, registry),
    mission: deriveMission(mission),
    environment: mergeEnvironment(input.environment, mission),
    simulation: mergeSimulation(input.simulation),
    results: input.results ?? emptyResults(),
    assets: {
      componentReferences: [...new Set(design.components.map((c) => c.defId))].sort(),
      images: [],
      customAssets: [],
    },
    design,
    missionConfig: mission,
  };

  return project;
}

// ============================================================
// Derivations
// ============================================================

function deriveVehicle(
  design: RocketDesign,
  registry: ComponentRegistry,
  analysis: RocketAnalysis,
): RktVehicle {
  const components: RktComponent[] = [];
  const materials = new Set<string>();

  for (const resolved of analysis.layout.components) {
    const def = resolved.def as { material?: string };
    if (def.material) materials.add(def.material);
    const placed = design.components.find((c) => c.instanceId === resolved.instanceId);
    components.push({
      id: resolved.instanceId,
      type: resolved.category,
      defId: resolved.defId,
      name: resolved.name,
      parentId: null,
      stageId: `stage-${resolved.stageIndex}`,
      position: {
        x: resolved.radialOffset_x,
        y: resolved.radialOffset_y,
        z: resolved.axialPosition_m,
      },
      orientation: { pitch: 0, yaw: 0, roll: 0 },
      dimensions: { length: resolved.length_m, diameter: resolved.diameter_m },
      mass_kg: resolved.totalMass_kg,
      material: def.material ?? 'unspecified',
      parameters: { ...(placed?.configOverrides ?? {}) },
    });
  }

  const stages: RktStage[] = design.stages.map((stage, index) => {
    const stageComponents = analysis.layout.components.filter((c) => c.stageIndex === index);
    const stageAnalysis = analysis.stages[index];
    return {
      stageId: `stage-${index}`,
      order: index,
      componentIds: stageComponents.map((c) => c.instanceId),
      motorIds: stageComponents.filter((c) => c.category === 'engine').map((c) => c.instanceId),
      ignitionDelay_s: stage.ignitionDelay_s,
      // Staging conditions are a closed vocabulary, never an expression: a
      // project file must not contain something the engine has to evaluate.
      separationCondition: { kind: 'burnout', value: 0, unit: '' },
      ignitionCondition:
        index === 0
          ? { kind: 'immediate', value: 0, unit: '' }
          : { kind: 'burnout', value: stage.ignitionDelay_s, unit: 's' },
      dryMass_kg: stageAnalysis?.dryMass_kg ?? 0,
      propellantMass_kg: stageAnalysis?.propellantMass_kg ?? 0,
    };
  });

  const payloadComponents = analysis.layout.components.filter((c) => c.category === 'payload');
  const recoveryComponents = analysis.layout.components.filter(
    (c) => c.category === 'parachute' || c.category === 'heat_shield',
  );
  const chutes = recoveryComponents
    .filter((c) => c.category === 'parachute')
    .map((c) => c.def as { parachuteType?: string; deployAltitude_m?: number; maxDeploySpeed_ms?: number });

  return {
    name: design.name,
    description: design.description,
    dimensions: {
      length_m: analysis.totalLength_m,
      maxDiameter_m: analysis.maxDiameter_m,
      referenceArea_m2: analysis.referenceArea_m2,
    },
    mass: {
      dry_kg: analysis.totalDryMass_kg,
      propellant_kg: analysis.totalPropellantMass_kg,
      payload_kg: analysis.payloadMass_kg,
      launch_kg: analysis.totalWetMass_kg,
    },
    materials: [...materials].sort(),
    stages,
    components,
    payload: {
      mass_kg: analysis.payloadMass_kg,
      type: payloadComponents[0]?.name ?? 'none',
      dimensions: {
        length_m: payloadComponents[0]?.length_m ?? 0,
        diameter_m: payloadComponents[0]?.diameter_m ?? 0,
      },
      description: payloadComponents.map((c) => c.name).join(', '),
    },
    recovery: {
      enabled: recoveryComponents.length > 0,
      componentIds: recoveryComponents.map((c) => c.instanceId),
      drogueDeployAltitude_m: Math.max(
        0,
        ...chutes.filter((c) => c.parachuteType === 'drogue').map((c) => c.deployAltitude_m ?? 0),
      ),
      mainDeployAltitude_m: Math.max(
        0,
        ...chutes.filter((c) => c.parachuteType !== 'drogue').map((c) => c.deployAltitude_m ?? 0),
      ),
      maxDeploySpeed_ms: Math.min(
        Number.POSITIVE_INFINITY,
        ...chutes.map((c) => c.maxDeploySpeed_ms ?? Number.POSITIVE_INFINITY),
      ) === Number.POSITIVE_INFINITY
        ? 0
        : Math.min(...chutes.map((c) => c.maxDeploySpeed_ms ?? 0)),
    },
  };
}

function derivePropulsion(design: RocketDesign, registry: ComponentRegistry): RktPropulsion {
  const motors: RktMotor[] = [];
  const thrustProfiles: RktThrustProfile[] = [];
  const mounts: RktPropulsion['mounts'] = [];

  for (const placed of design.components) {
    const def = registry.get(placed.defId);
    if (!def) continue;

    if (def.category === 'engine') {
      const engine = def as EngineDef;
      let profileIndex = -1;
      if (engine.thrustCurve && engine.thrustCurve.length > 1) {
        // Columnar, not an array of objects: a curve is two parallel number
        // arrays and repeating the keys per sample bloats the file for nothing.
        profileIndex = thrustProfiles.findIndex((p) => p.motorDefId === engine.id);
        if (profileIndex === -1) {
          thrustProfiles.push({
            id: `profile-${engine.id}`,
            motorDefId: engine.id,
            times_s: engine.thrustCurve.map((p) => p.t),
            thrust_N: engine.thrustCurve.map((p) => p.thrust_N),
          });
          profileIndex = thrustProfiles.length - 1;
        }
      }

      motors.push({
        componentId: placed.instanceId,
        defId: engine.id,
        designation: engine.designation ?? engine.name,
        propellantType: engine.propellantType,
        thrustVacuum_N: engine.thrust_N,
        thrustSeaLevel_N: engine.thrustSeaLevel_N,
        ispVacuum_s: engine.isp_vacuum_s,
        ispSeaLevel_s: engine.isp_seaLevel_s,
        burnTime_s: engine.burnTime_s ?? 0,
        totalImpulse_Ns: engine.totalImpulse_Ns ?? 0,
        propellantMass_kg: engine.integralPropellant_kg,
        dryMass_kg: engine.mass_kg,
        thrustProfileIndex: profileIndex,
      });
    }

    if (def.category === 'motor_mount') {
      const mount = def as { motorCount?: number; thrustCapacity_N?: number };
      mounts.push({
        componentId: placed.instanceId,
        motorCount: mount.motorCount ?? 1,
        thrustCapacity_N: mount.thrustCapacity_N ?? 0,
      });
    }
  }

  return { motors, mounts, thrustProfiles };
}

function deriveAerodynamics(
  design: RocketDesign,
  registry: ComponentRegistry,
  analysis: RocketAnalysis,
): RktAerodynamics {
  const fins: RktAerodynamics['fins'] = [];
  let noseCone: RktAerodynamics['noseCone'] = null;

  for (const resolved of analysis.layout.components) {
    const def = registry.get(resolved.defId);
    if (!def) continue;

    if (def.category === 'fin') {
      const fin = def as FinDef;
      fins.push({
        componentId: resolved.instanceId,
        shape: fin.shape ?? 'trapezoidal',
        count: fin.finCount,
        rootChord_m: fin.rootChord_m,
        tipChord_m: fin.tipChord_m,
        span_m: fin.span_m,
        sweepAngle_rad: fin.sweepAngle_rad,
        thickness_m: fin.thickness_m ?? 0,
        stationFromNose_m: resolved.station_m,
      });
    }

    if ((def.category === 'nose_cone' || def.category === 'fairing') && !noseCone) {
      const nose = def as NoseConeDef;
      noseCone = {
        componentId: resolved.instanceId,
        shape: nose.shape ?? 'tangent_ogive',
        length_m: nose.length_m,
        baseDiameter_m: nose.outerDiameter_m,
        shapeParameter: nose.shapeParameter ?? 0,
        finenessRatio: nose.finenessRatio,
      };
    }
  }

  return {
    fins,
    noseCone,
    dragParameters: {
      subsonicCd: analysis.dragCoefficient,
      referenceArea_m2: analysis.referenceArea_m2,
      useMachDragRise: true,
    },
    stabilityParameters: {
      cgWet_m: analysis.centerOfMassWet_m,
      cgDry_m: analysis.centerOfMassDry_m,
      cp_m: analysis.stabilityWet.cp_m,
      staticMarginWet_cal: analysis.stabilityWet.stabilityMargin_cal,
      staticMarginDry_cal: analysis.stabilityDry.stabilityMargin_cal,
      referenceDiameter_m: analysis.stabilityWet.referenceDiameter_m,
    },
  };
}

function deriveAvionics(
  design: RocketDesign,
  registry: ComponentRegistry,
): RktProject['avionics'] {
  let flightComputer: RktProject['avionics']['flightComputer'] = null;
  const sensors: RktProject['avionics']['sensors'] = [];

  for (const placed of design.components) {
    const def = registry.get(placed.defId);
    if (!def) continue;

    if (def.category === 'avionics') {
      const avionics = def as { hasFlightComputer?: boolean; name: string };
      if (avionics.hasFlightComputer && !flightComputer) {
        flightComputer = {
          componentId: placed.instanceId,
          name: avionics.name,
          redundancy: /triple/i.test(avionics.name) ? 3 : 1,
        };
      }
    }

    if (def.category === 'sensor') {
      const sensor = def as { sensorKind?: string; sampleRate_Hz?: number };
      sensors.push({
        componentId: placed.instanceId,
        kind: sensor.sensorKind ?? 'unknown',
        sampleRate_Hz: sensor.sampleRate_Hz ?? 0,
      });
    }
  }

  return {
    flightComputer,
    sensors,
    telemetry: {
      enabled: true,
      sampleInterval_s: 1,
      channels: [
        't', 'altitude_m', 'downrange_m', 'speed_ms', 'airspeed_ms', 'acceleration_ms2',
        'g_load_g', 'mass_kg', 'thrust_N', 'drag_N', 'dynamic_pressure_Pa', 'mach',
        'air_density_kgm3', 'pitch_rad', 'angle_of_attack_rad', 'q_alpha_Padeg',
        'lateral_deviation_m', 'wind_speed_ms',
      ],
    },
  };
}

function deriveMission(mission: MissionConfig): RktMission {
  return {
    name: mission.name,
    objective: mission.objective ?? '',
    launchSite: {
      id: '',
      name: mission.launchSite?.name ?? '',
      latitude_deg: mission.launchSite?.latitude_deg ?? 0,
      longitude_deg: mission.launchSite?.longitude_deg ?? 0,
      elevation_m: mission.launchSite?.altitude_m ?? 0,
    },
    target: {
      type: mission.target?.type ?? 'suborbital',
      altitude_km: mission.target?.targetAltitude_km ?? 0,
      inclination_deg: mission.target?.inclination_deg ?? null,
      bodyId: 'earth',
    },
    trajectory: {
      guidanceMode: 'pitch_program',
      pitchoverAltitude_m: 200,
      pitchProgramEndAltitude_m: 80_000,
      finalPitch_deg: 0,
    },
    orientation: { launchAzimuth_deg: 90, launchElevation_deg: 90, rollOrientation_deg: 0 },
    constraints: {
      maxG: 15,
      maxDynamicPressure_Pa: 1e6,
      maxQAlpha_Padeg: 250_000,
      maxGroundWind_ms: 15,
    },
  };
}

function mergeEnvironment(
  partial: Partial<RktEnvironment> | undefined,
  mission: MissionConfig,
): RktEnvironment {
  const environment = mission.environment;
  return {
    atmosphere: {
      model: 'us_standard_1976',
      surfaceTemperature_K: environment?.temperature_K ?? 288.15,
      surfacePressure_Pa: environment?.pressure_Pa ?? 101_325,
      relativeHumidity: 0,
      ...partial?.atmosphere,
    },
    weather: {
      source: 'standard_day',
      observedAt: null,
      windSpeed_ms: environment?.windSpeed_ms ?? 0,
      windDirection_deg: 0,
      windGust_ms: 0,
      jetWindSpeed_ms: 0,
      cloudCover: 0,
      precipitation_mmh: 0,
      ...partial?.weather,
    },
    gravity: {
      model: 'inverse_square',
      bodyId: 'earth',
      mu_m3s2: 3.986004418e14,
      surfaceRadius_m: 6_371_000,
      ...partial?.gravity,
    },
    simulationConditions: {
      includeWind: true,
      includeWeather: true,
      includeEarthRotation: false,
      ...partial?.simulationConditions,
    },
  };
}

function mergeSimulation(partial: Partial<RktSimulation> | undefined): RktSimulation {
  return {
    engine: 'lostintospace-python',
    engineVersion: '0.2.0',
    solver: 'rk4',
    ...partial,
    timestep: { powered_s: 0.05, coast_s: 0.5, maxSteps: 2_000_000, ...partial?.timestep },
    configuration: {
      maxTime_s: 2000,
      telemetrySampleInterval_s: 1,
      countdown_s: 3,
      useAltitudeCompensation: true,
      failureDetection: true,
      failureSeed: 1,
      ...partial?.configuration,
    },
  };
}

function emptyResults(): RktResults {
  return {
    hasResults: false,
    ranAt: null,
    engineVersion: '',
    inputsHash: '',
    outcome: 'not_run',
    telemetry: { channels: [], rows: [] },
    trajectory: {
      maxAltitude_m: 0,
      maxSpeed_ms: 0,
      maxAcceleration_g: 0,
      maxDynamicPressure_Pa: 0,
      maxQAlpha_Padeg: 0,
      apogeeTime_s: 0,
      flightTime_s: 0,
      downrange_m: 0,
      finalPeriapsis_m: 0,
      finalApoapsis_m: 0,
    },
    evaluation: null,
    failures: [],
  };
}
