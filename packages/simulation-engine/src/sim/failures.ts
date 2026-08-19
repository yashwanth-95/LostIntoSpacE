/**
 * Failure system.
 *
 * Two ways a flight can go wrong here, and they are deliberately different
 * things:
 *
 * 1. **Detected failures** — the vehicle broke *because of its design*. Dynamic
 *    pressure exceeded what the airframe could take; the g-load exceeded its
 *    structural limit; it never had the thrust to leave the pad. These are the
 *    valuable ones, because the student can go back and fix the cause.
 * 2. **Injected failures** — the instructor or the lesson scripted a fault at a
 *    given moment. An engine shuts down at T+40. A stage fails to separate.
 *    These teach what a failure *looks like* in telemetry.
 *
 * ## On honesty
 *
 * These are simplified models of failure modes, not reconstructions of real
 * accidents. A simulated tank rupture here is one threshold comparison; the
 * real thing is a coupled structural, thermal, and fluid problem. Every
 * {@link FailureDetail} says what triggered it and what the threshold was, so
 * the reasoning is always inspectable rather than mysterious. Nothing in this
 * engine should ever be presented as an explanation of an actual accident.
 *
 * ## Determinism
 *
 * Probabilistic injection uses a seeded PRNG carried in the config. The same
 * seed always produces the same flight. There is no `Math.random()` anywhere in
 * this module.
 *
 * @module sim/failures
 */

import { G0 } from '../physics/constants.js';
import type { Vehicle } from '../core/types.js';
import type { FailureDetail, FailureSubsystem, SimEventType } from './events.js';

// ============================================================
// Failure modes
// ============================================================

/** The failure modes the engine can produce. */
export type FailureModeId =
  | 'engine_shutdown'
  | 'tank_failure'
  | 'guidance_failure'
  | 'control_failure'
  | 'separation_failure'
  | 'communication_failure'
  | 'power_failure'
  | 'thermal_problem'
  | 'structural_problem'
  | 'insufficient_thrust'
  | 'aerodynamic_breakup'
  | 'excessive_g_load'
  | 'propellant_depletion';

/** How a failure changes the vehicle's behaviour from that moment on. */
export interface FailureEffects {
  /** All engines stop and cannot restart. */
  readonly killThrust: boolean;
  /** Remaining propellant in the active stage is lost. */
  readonly dumpPropellant: boolean;
  /** Attitude commands stop updating; the last one is held. */
  readonly freezeGuidance: boolean;
  /** Stage separation will not occur. */
  readonly blockSeparation: boolean;
  /** Telemetry is marked stale; the flight is otherwise unaffected. */
  readonly loseTelemetry: boolean;
  /** The vehicle is destroyed and the run ends. */
  readonly destroyVehicle: boolean;
}

/** No effect — the baseline every failure mode overrides. */
const NO_EFFECTS: FailureEffects = {
  killThrust: false,
  dumpPropellant: false,
  freezeGuidance: false,
  blockSeparation: false,
  loseTelemetry: false,
  destroyVehicle: false,
};

/** Static description of a failure mode. */
interface FailureModeSpec {
  readonly subsystem: FailureSubsystem;
  readonly name: string;
  readonly eventType: SimEventType;
  readonly effects: FailureEffects;
  readonly consequence: string;
  readonly educationalExplanation: string;
  readonly recommendedFix: string;
  readonly relatedLessons: readonly string[];
}

/**
 * What each failure mode means and does.
 *
 * The explanations are written to be read by a student mid-flight, and are the
 * text P4 grounds its answers in.
 */
export const FAILURE_MODES: Readonly<Record<FailureModeId, FailureModeSpec>> =
  Object.freeze({
    engine_shutdown: {
      subsystem: 'propulsion',
      name: 'Engine shutdown',
      eventType: 'failure_engine',
      effects: { ...NO_EFFECTS, killThrust: true },
      consequence: 'Thrust stopped; the vehicle coasts from here on whatever velocity it had.',
      educationalExplanation:
        'An engine that stops early leaves the rest of its propellant unused. ' +
        'Because delta-v depends on the ratio of start mass to end mass, and ' +
        'the unburnt propellant is still aboard as dead weight, the loss is ' +
        'worse than the missing burn time alone suggests.',
      recommendedFix:
        'Carry engine-out capability: several engines per stage, sized so the ' +
        'remaining ones can still complete the burn.',
      relatedLessons: ['propulsion-basics', 'engine-out-capability'],
    },

    tank_failure: {
      subsystem: 'structure',
      name: 'Propellant tank failure',
      eventType: 'failure_tank',
      effects: { ...NO_EFFECTS, killThrust: true, dumpPropellant: true },
      consequence: 'The tank lost its contents; the engines starved and stopped.',
      educationalExplanation:
        'Propellant tanks are thin-walled pressure vessels, and they are also ' +
        'the vehicle\'s main structure. They carry internal pressure, the ' +
        'compressive load of everything stacked above, and aerodynamic ' +
        'bending all at once. Exceeding any one of those limits can open the tank.',
      recommendedFix:
        'Fly a shallower ascent to reduce dynamic pressure, or use a tank with ' +
        'a higher pressure rating.',
      relatedLessons: ['structural-loads', 'max-q'],
    },

    guidance_failure: {
      subsystem: 'avionics',
      name: 'Guidance failure',
      eventType: 'failure_guidance',
      effects: { ...NO_EFFECTS, freezeGuidance: true },
      consequence:
        'Attitude commands stopped updating; the vehicle holds its last ' +
        'commanded attitude for the rest of the flight.',
      educationalExplanation:
        'Guidance decides where to point. With it frozen the engines keep ' +
        'burning, but along whatever direction happened to be commanded last. ' +
        'A vehicle stuck at a steep pitch wastes its remaining propellant ' +
        'climbing instead of building the horizontal speed an orbit needs.',
      recommendedFix:
        'Add a redundant guidance unit, and a flight computer that can fall ' +
        'back to a stored attitude schedule.',
      relatedLessons: ['guidance-navigation-control'],
    },

    control_failure: {
      subsystem: 'avionics',
      name: 'Control failure',
      eventType: 'failure_control',
      effects: { ...NO_EFFECTS, freezeGuidance: true },
      consequence: 'The vehicle can no longer steer and holds its last attitude.',
      educationalExplanation:
        'Guidance decides where to point; control makes it happen, through ' +
        'engine gimbals or aerodynamic surfaces. Losing control on a ' +
        'statically unstable vehicle is not recoverable — nothing is left to ' +
        'correct the disturbances that instability keeps amplifying.',
      recommendedFix:
        'Design in positive static stability so the airframe self-corrects, or ' +
        'carry redundant actuators.',
      relatedLessons: ['stability-and-control', 'thrust-vector-control'],
    },

    separation_failure: {
      subsystem: 'structure',
      name: 'Stage separation failure',
      eventType: 'failure_separation',
      effects: { ...NO_EFFECTS, blockSeparation: true, killThrust: true },
      consequence:
        'The spent stage stayed attached; the next stage cannot ignite behind it.',
      educationalExplanation:
        'A spent stage is pure dead weight — its propellant is gone but its ' +
        'structure is not. Carrying it into the next burn can easily double the ' +
        'mass that burn has to accelerate, which the rocket equation punishes ' +
        'severely.',
      recommendedFix:
        'Use redundant separation initiators, and verify the separation ' +
        'sequence timing against the burn profile.',
      relatedLessons: ['staging', 'rocket-equation'],
    },

    communication_failure: {
      subsystem: 'communication',
      name: 'Communication failure',
      eventType: 'failure_communication',
      effects: { ...NO_EFFECTS, loseTelemetry: true },
      consequence:
        'Telemetry downlink lost. The vehicle flies on exactly as before, but ' +
        'the ground can no longer see what it is doing.',
      educationalExplanation:
        'Losing the downlink changes nothing about the physics — it changes ' +
        'what anyone can know about it. This is why real vehicles record ' +
        'on board as well as transmitting: a flight nobody could observe is ' +
        'a flight nobody can learn from.',
      recommendedFix: 'Add a redundant transmitter and an onboard recorder.',
      relatedLessons: ['telemetry-systems'],
    },

    power_failure: {
      subsystem: 'power',
      name: 'Electrical power failure',
      eventType: 'failure_power',
      effects: { ...NO_EFFECTS, freezeGuidance: true, loseTelemetry: true },
      consequence: 'Avionics lost power; guidance and telemetry both stopped.',
      educationalExplanation:
        'Power is the single dependency every other system shares. When it ' +
        'goes, guidance, control, telemetry, and the staging sequencer all go ' +
        'with it, which is why a power fault cascades faster than almost any ' +
        'other single failure.',
      recommendedFix:
        'Carry redundant batteries on independent buses, so no single failure ' +
        'takes all of the avionics.',
      relatedLessons: ['spacecraft-power-systems'],
    },

    thermal_problem: {
      subsystem: 'thermal',
      name: 'Thermal limit exceeded',
      eventType: 'failure_thermal',
      effects: { ...NO_EFFECTS, destroyVehicle: true },
      consequence: 'Structure exceeded its temperature limit and failed.',
      educationalExplanation:
        'Aerodynamic heating rises roughly with the cube of speed, so a vehicle ' +
        'moving twice as fast heats about eight times as hard. That is why ' +
        'ascent profiles keep the vehicle slow while the air is thick, and why ' +
        'entry vehicles need dedicated heat shields.',
      recommendedFix:
        'Add thermal protection, or shape the trajectory to spend less time ' +
        'fast and low.',
      relatedLessons: ['aerodynamic-heating', 'thermal-protection'],
    },

    structural_problem: {
      subsystem: 'structure',
      name: 'Structural failure',
      eventType: 'failure_structural',
      effects: { ...NO_EFFECTS, destroyVehicle: true },
      consequence: 'The airframe exceeded its load limit and broke up.',
      educationalExplanation:
        'A launch vehicle is a thin metal tube carrying an enormous ' +
        'compressive load. Peak acceleration is a good proxy for that load, ' +
        'because the mass of everything above a given point pushes down on it ' +
        'in proportion to how hard the vehicle is accelerating.',
      recommendedFix:
        'Throttle back at peak acceleration, or use a stronger airframe.',
      relatedLessons: ['structural-loads', 'max-acceleration'],
    },

    insufficient_thrust: {
      subsystem: 'propulsion',
      name: 'Insufficient thrust for liftoff',
      eventType: 'failure_twr',
      effects: { ...NO_EFFECTS, killThrust: true },
      consequence: 'The vehicle never left the pad.',
      educationalExplanation:
        'Thrust has to exceed weight before a vehicle can accelerate upward. ' +
        'Below a thrust-to-weight ratio of 1.0 the engines simply burn until ' +
        'the propellant is gone, with the vehicle still sitting where it started.',
      recommendedFix:
        'Add engines, choose a higher-thrust engine, or cut launch mass.',
      relatedLessons: ['thrust-to-weight', 'propulsion-basics'],
    },

    aerodynamic_breakup: {
      subsystem: 'aerodynamics',
      name: 'Aerodynamic breakup',
      eventType: 'failure_max_q',
      effects: { ...NO_EFFECTS, destroyVehicle: true },
      consequence: 'Dynamic pressure exceeded the airframe limit and the vehicle broke apart.',
      educationalExplanation:
        'Dynamic pressure, q = ½ρv², is the aerodynamic load on the airframe. ' +
        'It peaks partway up: speed is still rising while air density is ' +
        'already falling, and their product turns over. That peak is called ' +
        'max-Q, and it is the moment the vehicle is most likely to be torn apart.',
      recommendedFix:
        'Throttle down through the transonic region, or fly a shallower ' +
        'profile so speed builds after the air has thinned.',
      relatedLessons: ['max-q', 'atmospheric-drag'],
    },

    excessive_g_load: {
      subsystem: 'structure',
      name: 'Excessive acceleration',
      eventType: 'failure_structural',
      effects: { ...NO_EFFECTS, destroyVehicle: true },
      consequence: 'Acceleration exceeded the design limit and the structure failed.',
      educationalExplanation:
        'Acceleration climbs through a burn even at constant thrust, because ' +
        'the vehicle keeps getting lighter as propellant leaves. The highest ' +
        'g-load of a stage is almost always in its final seconds, right before ' +
        'cutoff.',
      recommendedFix:
        'Throttle down late in the burn, which is exactly why real vehicles do it.',
      relatedLessons: ['acceleration-limits', 'throttling'],
    },

    propellant_depletion: {
      subsystem: 'propulsion',
      name: 'Premature propellant depletion',
      eventType: 'failure_fuel',
      effects: { ...NO_EFFECTS, killThrust: true },
      consequence: 'Propellant ran out before the mission objective was reached.',
      educationalExplanation:
        'Running dry early means the delta-v budget was short. That is usually ' +
        'either too little propellant or too much dry mass — and because the ' +
        'rocket equation is logarithmic, shaving dry mass buys far more than ' +
        'adding the equivalent propellant.',
      recommendedFix: 'Add propellant, cut dry mass, or add a stage.',
      relatedLessons: ['rocket-equation', 'mass-fractions'],
    },
  });

// ============================================================
// Configuration
// ============================================================

/** When a scripted failure fires. */
export type FailureTrigger =
  /** At a given mission time. */
  | { readonly type: 'time'; readonly t_s: number }
  /** The first time the vehicle passes an altitude while climbing. */
  | { readonly type: 'altitude'; readonly altitude_m: number }
  /** When a given stage ignites. */
  | { readonly type: 'stage_ignition'; readonly stageIndex: number }
  /** When a given stage is due to separate. */
  | { readonly type: 'stage_separation'; readonly stageIndex: number }
  /**
   * Randomly, at the given hazard rate, evaluated each step.
   *
   * Uses the seeded PRNG, so a given seed always produces the same outcome.
   */
  | { readonly type: 'probability'; readonly perSecond: number };

/** A scripted failure. */
export interface FailureInjection {
  /** Identifier, so the event can be traced back to the script. */
  readonly id: string;
  /** Which failure to cause. */
  readonly mode: FailureModeId;
  /** When to cause it. */
  readonly trigger: FailureTrigger;
  /** Stage the failure applies to, or null for vehicle-wide. */
  readonly stageIndex?: number;
}

/** Thresholds the automatic detection rules compare against. */
export interface FailureThresholds {
  /** Load factor above which the structure fails. Unit: g. */
  readonly maxGLoad_g: number;
  /**
   * Dynamic pressure above which the airframe fails. Unit: Pa.
   *
   * When null, the vehicle's own weakest-component limit is used instead.
   */
  readonly maxDynamicPressure_Pa: number | null;
  /** Minimum liftoff thrust-to-weight before the pad-abort rule fires. */
  readonly minLiftoffTWR: number;
  /**
   * Speed above which aerodynamic heating is treated as destructive while
   * still inside the atmosphere. Unit: m/s.
   */
  readonly maxAtmosphericSpeed_ms: number;
  /** Altitude below which the heating rule applies. Unit: m. */
  readonly heatingAltitudeCeiling_m: number;
}

/**
 * Default thresholds — generous enough that a sane design never trips them.
 *
 * The 15 g structural limit suits an uncrewed vehicle; a crewed one would be
 * held nearer 4 g, which is a limit set by the people aboard rather than by the
 * airframe. Lower `maxGLoad_g` to model that.
 */
export const DEFAULT_FAILURE_THRESHOLDS: FailureThresholds = {
  maxGLoad_g: 15,
  maxDynamicPressure_Pa: null,
  minLiftoffTWR: 1.0,
  maxAtmosphericSpeed_ms: 3_000,
  heatingAltitudeCeiling_m: 60_000,
} as const;

/** Failure detection and injection settings. */
export interface FailureConfig {
  /** Master switch. When false, nothing in this module fires. */
  readonly enabled: boolean;
  /** Whether the automatic design-driven rules run. */
  readonly detectionEnabled: boolean;
  /** Seed for probabilistic injection. Same seed, same flight. */
  readonly seed: number;
  /** Scripted failures. */
  readonly injections: readonly FailureInjection[];
  /** Thresholds for the detection rules. */
  readonly thresholds: FailureThresholds;
}

/** Detection on, no scripted failures — the default. */
export const DEFAULT_FAILURE_CONFIG: FailureConfig = {
  enabled: true,
  detectionEnabled: true,
  seed: 1,
  injections: [],
  thresholds: DEFAULT_FAILURE_THRESHOLDS,
} as const;

// ============================================================
// Seeded PRNG
// ============================================================

/**
 * Mulberry32 — a small, fast, well-distributed 32-bit PRNG.
 *
 * Chosen over `Math.random()` because the engine's determinism guarantee
 * requires a reproducible stream, and over a cryptographic generator because
 * nothing here needs unpredictability, only repeatability.
 */
export class SeededRandom {
  private _state: number;

  /** @param seed - Any 32-bit integer. The same seed gives the same sequence. */
  constructor(seed: number) {
    this._state = seed >>> 0;
  }

  /** Next value in [0, 1). */
  next(): number {
    this._state = (this._state + 0x6d2b79f5) >>> 0;
    let t = this._state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  /**
   * Whether an event of the given per-second hazard rate occurs in `dt`.
   *
   * Uses the exponential survival function, so the outcome does not depend on
   * the timestep: halving `dt` halves the per-call probability.
   *
   * @param ratePerSecond - Hazard rate. Unit: 1/s.
   * @param dt_s - Interval length. Unit: s.
   * @returns True if the event fires in this interval.
   */
  occursIn(ratePerSecond: number, dt_s: number): boolean {
    if (ratePerSecond <= 0 || dt_s <= 0) return false;
    return this.next() < 1 - Math.exp(-ratePerSecond * dt_s);
  }
}

// ============================================================
// Detection
// ============================================================

/** State the failure engine inspects each step. */
export interface FailureCheckInputs {
  readonly t: number;
  readonly dt_s: number;
  readonly altitude_m: number;
  readonly speed_ms: number;
  readonly verticalSpeed_ms: number;
  readonly gLoad_g: number;
  readonly dynamicPressure_Pa: number;
  readonly thrust_N: number;
  readonly mass_kg: number;
  readonly activeStage: number;
  readonly isBurning: boolean;
  /** Whether the vehicle has left the pad yet. */
  readonly hasLiftedOff: boolean;
  /** How long the vehicle has been burning without leaving the pad. Unit: s. */
  readonly burnTimeOnPad_s: number;
}

/** Build a failure record from a mode and the measurements that triggered it. */
function buildDetail(
  mode: FailureModeId,
  inputs: FailureCheckInputs,
  triggerCondition: string,
  measuredValue: number,
  thresholdValue: number,
  unit: string,
  contributingFactors: readonly string[],
  stageIndex: number | null,
): FailureDetail {
  const spec = FAILURE_MODES[mode];
  return {
    id: mode,
    modeId: mode,
    subsystem: spec.subsystem,
    failureMode: spec.name,
    severity: spec.effects.destroyVehicle ? 'fatal' : 'critical',
    t: inputs.t,
    stageIndex,
    triggerCondition,
    measuredValue,
    thresholdValue,
    unit,
    triggerState: {
      t: inputs.t,
      altitude_m: inputs.altitude_m,
      speed_ms: inputs.speed_ms,
      verticalSpeed_ms: inputs.verticalSpeed_ms,
      mass_kg: inputs.mass_kg,
      thrust_N: inputs.thrust_N,
      gLoad_g: inputs.gLoad_g,
      dynamicPressure_Pa: inputs.dynamicPressure_Pa,
      activeStage: inputs.activeStage,
    },
    contributingFactors,
    consequence: spec.consequence,
    educationalExplanation: spec.educationalExplanation,
    recommendedFix: spec.recommendedFix,
    relatedLessons: spec.relatedLessons,
    isTerminal: spec.effects.destroyVehicle || spec.effects.killThrust,
  };
}

/**
 * Run the automatic detection rules for one step.
 *
 * @param inputs - Measurements for this step.
 * @param vehicle - Vehicle being flown, for its structural limits.
 * @param config - Failure configuration.
 * @returns Every failure detected this step. Usually empty.
 */
export function detectFailures(
  inputs: FailureCheckInputs,
  vehicle: Vehicle,
  config: FailureConfig,
): FailureDetail[] {
  if (!config.enabled || !config.detectionEnabled) return [];

  const detected: FailureDetail[] = [];
  const { thresholds } = config;

  // --- Never left the pad -------------------------------------------------
  // Only meaningful once the engines have been burning for a moment: thrust
  // takes a finite time to build and the vehicle is briefly held by its own
  // weight even on a healthy launch.
  if (
    !inputs.hasLiftedOff &&
    inputs.isBurning &&
    inputs.burnTimeOnPad_s > 2.0 &&
    inputs.mass_kg > 0
  ) {
    const twr = inputs.thrust_N / (inputs.mass_kg * G0);
    if (twr < thresholds.minLiftoffTWR) {
      detected.push(
        buildDetail(
          'insufficient_thrust',
          inputs,
          `Thrust-to-weight ${twr.toFixed(2)} stayed below ${thresholds.minLiftoffTWR} for over 2 s of burn`,
          twr,
          thresholds.minLiftoffTWR,
          'ratio',
          [
            `Launch mass ${Math.round(inputs.mass_kg)} kg`,
            `Available thrust ${Math.round(inputs.thrust_N / 1000)} kN`,
            `Weight ${Math.round((inputs.mass_kg * G0) / 1000)} kN`,
          ],
          inputs.activeStage,
        ),
      );
    }
  }

  // --- Aerodynamic breakup ------------------------------------------------
  const qLimit = thresholds.maxDynamicPressure_Pa ?? vehicle.maxDynamicPressure_Pa;
  if (Number.isFinite(qLimit) && inputs.dynamicPressure_Pa > qLimit) {
    detected.push(
      buildDetail(
        'aerodynamic_breakup',
        inputs,
        `Dynamic pressure ${Math.round(inputs.dynamicPressure_Pa)} Pa exceeded the airframe limit of ${Math.round(qLimit)} Pa`,
        inputs.dynamicPressure_Pa,
        qLimit,
        'Pa',
        [
          `Speed ${Math.round(inputs.speed_ms)} m/s at ${Math.round(inputs.altitude_m)} m`,
          'Dynamic pressure grows with the square of speed and with air density',
        ],
        null,
      ),
    );
  }

  // --- Excessive acceleration --------------------------------------------
  if (Math.abs(inputs.gLoad_g) > thresholds.maxGLoad_g) {
    detected.push(
      buildDetail(
        'excessive_g_load',
        inputs,
        `Load factor ${inputs.gLoad_g.toFixed(1)} g exceeded the ${thresholds.maxGLoad_g} g limit`,
        Math.abs(inputs.gLoad_g),
        thresholds.maxGLoad_g,
        'g',
        [
          `Thrust ${Math.round(inputs.thrust_N / 1000)} kN acting on ${Math.round(inputs.mass_kg)} kg`,
          'Acceleration rises through a burn as propellant mass leaves',
        ],
        inputs.activeStage,
      ),
    );
  }

  // --- Aerodynamic heating ------------------------------------------------
  if (
    inputs.altitude_m < thresholds.heatingAltitudeCeiling_m &&
    inputs.speed_ms > thresholds.maxAtmosphericSpeed_ms
  ) {
    detected.push(
      buildDetail(
        'thermal_problem',
        inputs,
        `Speed ${Math.round(inputs.speed_ms)} m/s below ${Math.round(thresholds.heatingAltitudeCeiling_m)} m exceeded the heating limit of ${thresholds.maxAtmosphericSpeed_ms} m/s`,
        inputs.speed_ms,
        thresholds.maxAtmosphericSpeed_ms,
        'm/s',
        [
          `Altitude ${Math.round(inputs.altitude_m)} m, where the air is still dense`,
          'Heating rate rises roughly with the cube of speed',
        ],
        null,
      ),
    );
  }

  return detected;
}

// ============================================================
// Injection
// ============================================================

/** State the injection scheduler inspects. */
export interface InjectionCheckInputs extends FailureCheckInputs {
  /** Stages that ignited this step. */
  readonly stagesIgnitedThisStep: readonly number[];
  /** Stages due to separate this step. */
  readonly stagesSeparatingThisStep: readonly number[];
  /** Peak altitude reached so far, for edge-triggering altitude injections. Unit: m. */
  readonly maxAltitudeSoFar_m: number;
}

/**
 * Decide which scripted failures fire this step.
 *
 * Each injection fires at most once; `alreadyFired` carries that across steps
 * and is mutated by this function as failures trigger.
 *
 * @param inputs - Measurements and stage events for this step.
 * @param config - Failure configuration.
 * @param rng - The run's seeded generator.
 * @param alreadyFired - Ids that have already fired. Updated in place.
 * @returns Failure records for the injections that fired.
 */
export function checkInjections(
  inputs: InjectionCheckInputs,
  config: FailureConfig,
  rng: SeededRandom,
  alreadyFired: Set<string>,
): FailureDetail[] {
  if (!config.enabled) return [];

  const fired: FailureDetail[] = [];

  for (const injection of config.injections) {
    if (alreadyFired.has(injection.id)) continue;
    if (!triggerFires(injection.trigger, inputs, rng)) continue;

    alreadyFired.add(injection.id);

    const spec = FAILURE_MODES[injection.mode];
    fired.push({
      id: injection.id,
      modeId: injection.mode,
      subsystem: spec.subsystem,
      failureMode: spec.name,
      severity: spec.effects.destroyVehicle ? 'fatal' : 'critical',
      t: inputs.t,
      stageIndex: injection.stageIndex ?? null,
      triggerCondition: describeTrigger(injection.trigger),
      measuredValue: triggerMeasurement(injection.trigger, inputs),
      thresholdValue: triggerThreshold(injection.trigger),
      unit: triggerUnit(injection.trigger),
      triggerState: {
        t: inputs.t,
        altitude_m: inputs.altitude_m,
        speed_ms: inputs.speed_ms,
        verticalSpeed_ms: inputs.verticalSpeed_ms,
        mass_kg: inputs.mass_kg,
        thrust_N: inputs.thrust_N,
        gLoad_g: inputs.gLoad_g,
        dynamicPressure_Pa: inputs.dynamicPressure_Pa,
        activeStage: inputs.activeStage,
      },
      contributingFactors: [
        'This failure was scripted into the simulation, not caused by the design',
      ],
      consequence: spec.consequence,
      educationalExplanation: spec.educationalExplanation,
      recommendedFix: spec.recommendedFix,
      relatedLessons: spec.relatedLessons,
      isTerminal: spec.effects.destroyVehicle || spec.effects.killThrust,
    });
  }

  return fired;
}

/** Whether a trigger condition is met this step. */
function triggerFires(
  trigger: FailureTrigger,
  inputs: InjectionCheckInputs,
  rng: SeededRandom,
): boolean {
  switch (trigger.type) {
    case 'time':
      return inputs.t >= trigger.t_s;
    case 'altitude':
      // Edge-triggered on the way up, so a descending vehicle passing back
      // through the same altitude does not re-arm it.
      return (
        inputs.maxAltitudeSoFar_m >= trigger.altitude_m && inputs.verticalSpeed_ms > 0
      );
    case 'stage_ignition':
      return inputs.stagesIgnitedThisStep.includes(trigger.stageIndex);
    case 'stage_separation':
      return inputs.stagesSeparatingThisStep.includes(trigger.stageIndex);
    case 'probability':
      return rng.occursIn(trigger.perSecond, inputs.dt_s);
  }
}

/** Human-readable description of a trigger. */
function describeTrigger(trigger: FailureTrigger): string {
  switch (trigger.type) {
    case 'time':
      return `Scripted to occur at T+${trigger.t_s} s`;
    case 'altitude':
      return `Scripted to occur on passing ${trigger.altitude_m} m while climbing`;
    case 'stage_ignition':
      return `Scripted to occur when stage ${trigger.stageIndex} ignites`;
    case 'stage_separation':
      return `Scripted to occur when stage ${trigger.stageIndex} separates`;
    case 'probability':
      return `Scripted with a hazard rate of ${trigger.perSecond} per second`;
  }
}

/** The measured quantity a trigger keyed on. */
function triggerMeasurement(
  trigger: FailureTrigger,
  inputs: InjectionCheckInputs,
): number {
  switch (trigger.type) {
    case 'time':
      return inputs.t;
    case 'altitude':
      return inputs.altitude_m;
    case 'stage_ignition':
    case 'stage_separation':
      return inputs.activeStage;
    case 'probability':
      return trigger.perSecond;
  }
}

/** The threshold a trigger keyed on. */
function triggerThreshold(trigger: FailureTrigger): number {
  switch (trigger.type) {
    case 'time':
      return trigger.t_s;
    case 'altitude':
      return trigger.altitude_m;
    case 'stage_ignition':
    case 'stage_separation':
      return trigger.stageIndex;
    case 'probability':
      return trigger.perSecond;
  }
}

/** Unit of a trigger's measurement. */
function triggerUnit(trigger: FailureTrigger): string {
  switch (trigger.type) {
    case 'time':
      return 's';
    case 'altitude':
      return 'm';
    case 'stage_ignition':
    case 'stage_separation':
      return 'stage';
    case 'probability':
      return '1/s';
  }
}

/**
 * Combine the effects of every failure active so far.
 *
 * Effects accumulate: a vehicle that has lost guidance *and* had an engine shut
 * down suffers both.
 *
 * @param failures - Failures that have occurred.
 * @returns The union of their effects.
 */
export function combinedEffects(failures: readonly FailureDetail[]): FailureEffects {
  let combined = NO_EFFECTS;

  for (const failure of failures) {
    const spec = FAILURE_MODES[failure.modeId as FailureModeId];
    if (!spec) continue;
    combined = {
      killThrust: combined.killThrust || spec.effects.killThrust,
      dumpPropellant: combined.dumpPropellant || spec.effects.dumpPropellant,
      freezeGuidance: combined.freezeGuidance || spec.effects.freezeGuidance,
      blockSeparation: combined.blockSeparation || spec.effects.blockSeparation,
      loseTelemetry: combined.loseTelemetry || spec.effects.loseTelemetry,
      destroyVehicle: combined.destroyVehicle || spec.effects.destroyVehicle,
    };
  }

  return combined;
}

/**
 * The event type to emit for a failure.
 *
 * @param failure - The failure record.
 * @returns Its event type, or the generic `'failure'` for an unknown mode.
 */
export function failureEventType(failure: FailureDetail): SimEventType {
  return FAILURE_MODES[failure.modeId as FailureModeId]?.eventType ?? 'failure';
}
