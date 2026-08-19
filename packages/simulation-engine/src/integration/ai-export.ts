/**
 * Machine-readable mission report, for P4's explanation layer.
 *
 * ## The design constraint
 *
 * A language model asked "why did this rocket fail?" will produce a fluent
 * answer whether or not it has the facts. The only defence is to give it the
 * facts in a form it cannot misread — named quantities with units, thresholds
 * next to the values that crossed them, and an explicit statement of what the
 * engine *did not* model.
 *
 * So this module emits no prose about causes. It emits measurements. Every
 * number here came out of the simulation; nothing is inferred, and the
 * `modelLimitations` block states plainly what the engine cannot tell you, so
 * an explanation built on this report can be honest about its own limits.
 *
 * @module integration/ai-export
 */

import { G0 } from '../physics/constants.js';
import type { SimConfig } from '../sim/config.js';
import type { SimResult } from '../sim/runner.js';
import type { FailureDetail } from '../sim/events.js';
import type { RocketAnalysis } from '../core/builder.js';
import type { ValidationIssue } from '../core/validation.js';

/** A quantity with its unit and a short description, ready to be quoted. */
export interface ReportedQuantity {
  /** Machine-readable key. */
  readonly key: string;
  /** Human-readable label. */
  readonly label: string;
  /** The value. */
  readonly value: number;
  /** SI unit symbol, or a dimensionless marker. */
  readonly unit: string;
  /** What it means, in one line. */
  readonly description: string;
}

/** One moment in the flight, with the state around it. */
export interface ReportedMoment {
  readonly t_s: number;
  readonly type: string;
  readonly severity: string;
  readonly description: string;
  readonly altitude_m: number;
  readonly speed_ms: number;
}

/** What the engine does not model, stated explicitly. */
export interface ModelLimitations {
  /** One line per thing the engine leaves out. */
  readonly notModelled: readonly string[];
  /** One line per simplification that could change a conclusion. */
  readonly simplifications: readonly string[];
  /** The blanket caveat, for quoting verbatim. */
  readonly caveat: string;
}

/** The complete report handed to the explanation layer. */
export interface MissionReport {
  /** Schema version of this report shape. */
  readonly reportVersion: string;

  /** What was flown, and where. */
  readonly mission: {
    readonly name: string;
    readonly objective: string;
    readonly targetAltitude_km: number;
    readonly missionType: string;
    readonly launchSite: string;
    readonly guidanceMode: string;
  };

  /** What the vehicle was, before it flew. */
  readonly vehicle: {
    readonly name: string;
    readonly stageCount: number;
    readonly launchMass_kg: number;
    readonly dryMass_kg: number;
    readonly propellantMass_kg: number;
    readonly payloadMass_kg: number;
    readonly idealDeltaV_ms: number;
    readonly liftoffTWR: number;
    readonly stabilityMargin_cal: number;
  };

  /** How it went. */
  readonly outcome: {
    readonly result: 'success' | 'partial' | 'failure';
    readonly succeeded: boolean;
    readonly finalMissionState: string;
    readonly terminationReason: string;
    readonly flightTime_s: number;
  };

  /** The headline measurements. */
  readonly measurements: readonly ReportedQuantity[];

  /**
   * Where the delta-v went.
   *
   * The single most useful block for explaining an underperforming flight: the
   * gap between ideal and achieved is entirely accounted for here.
   */
  readonly deltaVBudget: {
    readonly ideal_ms: number;
    readonly achieved_ms: number;
    readonly gravityLoss_ms: number;
    readonly dragLoss_ms: number;
    readonly unaccounted_ms: number;
    readonly explanation: string;
  };

  /** The flight timeline. */
  readonly timeline: readonly ReportedMoment[];

  /** Every failure, with its full record. */
  readonly failures: readonly FailureDetail[];

  /** Design problems flagged before flight. */
  readonly preflightWarnings: readonly ValidationIssue[];

  /** What the engine cannot tell you. */
  readonly modelLimitations: ModelLimitations;
}

/** The report shape's own version. */
export const REPORT_VERSION = '1.0.0';

/** What this engine does not model, stated once and reused. */
const MODEL_LIMITATIONS: ModelLimitations = Object.freeze({
  notModelled: Object.freeze([
    'Earth rotation — a real eastward equatorial launch gains about 465 m/s that this engine does not provide.',
    'Wind and weather — the atmosphere is the standard atmosphere with no local conditions.',
    'Rotational dynamics — the vehicle has no moments of inertia, does not tumble, and cannot be steered by a control loop.',
    'Aerodynamic lift — the only aerodynamic force is drag, acting exactly opposite to velocity.',
    'Engine throttling in flight — thrust is fixed at the configured setting for the whole burn.',
    'Thermal state — temperatures are never integrated; the heating failure rule is a speed-and-altitude threshold, not a heat-transfer model.',
    'Structural dynamics — no bending, no vibration, no coupling between the vehicle and its propellant.',
    'Earth oblateness (J2), third-body gravity, and solar radiation pressure.',
  ]),
  simplifications: Object.freeze([
    'Drag uses one coefficient for the whole vehicle, scaled by a generic transonic curve rather than by measured aerodynamics.',
    'Stage separation is instantaneous once its delay elapses; no separation transient is modelled.',
    'Propellant is assumed to sit at each tank\'s geometric centre and never to slosh or shift as it drains.',
    'Attitude is scripted by the guidance program rather than achieved by a control system, so steering is always perfect.',
    'Orbital elements are osculating two-body values: they describe the orbit the vehicle would coast into from that instant, not a prediction.',
  ]),
  caveat:
    'This is an educational simulation. Its models are simplified approximations ' +
    'chosen to teach real physical relationships, not to reproduce the behaviour ' +
    'of any specific vehicle. Simulated failures show how a failure mode behaves ' +
    'in this model; they are not reconstructions of real accidents and must not ' +
    'be presented as explanations of one.',
});

/**
 * Build the mission report.
 *
 * @param result - The completed run.
 * @param config - The config it was run with.
 * @param analysis - The vehicle's pre-flight analysis.
 * @param preflightWarnings - Validation issues found before flight.
 * @returns A report containing only measured values and stated limitations.
 */
export function buildMissionReport(
  result: SimResult,
  config: SimConfig,
  analysis: RocketAnalysis,
  preflightWarnings: readonly ValidationIssue[] = [],
): MissionReport {
  const s = result.summary;

  // The gap the loss terms do not explain. It is normally small, and when it is
  // not, that itself is worth surfacing rather than hiding.
  const accountedFor = s.deltaVAchieved_ms + s.gravityLoss_ms + s.dragLoss_ms;
  const unaccounted = s.deltaVIdeal_ms - accountedFor;

  return {
    reportVersion: REPORT_VERSION,

    mission: {
      name: config.mission.name,
      objective: config.mission.objective,
      targetAltitude_km: config.mission.target.targetAltitude_km,
      missionType: config.mission.target.type,
      launchSite: config.mission.launchSite.name,
      guidanceMode: config.guidance.mode,
    },

    vehicle: {
      name: config.vehicle.name,
      stageCount: config.vehicle.stages.length,
      launchMass_kg: config.vehicle.launchMass_kg,
      dryMass_kg: analysis.totalDryMass_kg,
      propellantMass_kg: analysis.totalPropellantMass_kg,
      payloadMass_kg: analysis.payloadMass_kg,
      idealDeltaV_ms: analysis.totalDeltaV_ms,
      liftoffTWR: analysis.liftoffTWR,
      stabilityMargin_cal: Math.min(
        analysis.stabilityWet.stabilityMargin_cal,
        analysis.stabilityDry.stabilityMargin_cal,
      ),
    },

    outcome: {
      result: result.outcome,
      succeeded: result.success,
      finalMissionState: result.finalState,
      terminationReason: result.terminationReason,
      flightTime_s: result.flightTime_s,
    },

    measurements: [
      quantity('maxAltitude', 'Maximum altitude', s.maxAltitude_m, 'm',
        'Highest point above mean sea level the vehicle reached.'),
      quantity('apogeeTime', 'Time of apogee', s.apogeeTime_s, 's',
        'When the vehicle stopped climbing.'),
      quantity('maxSpeed', 'Maximum speed', s.maxSpeed_ms, 'm/s',
        'Greatest speed relative to the launch-centred inertial frame.'),
      quantity('maxMach', 'Maximum Mach number', s.maxMach, 'dimensionless',
        'Peak ratio of speed to the local speed of sound.'),
      quantity('maxDynamicPressure', 'Maximum dynamic pressure', s.maxDynamicPressure_Pa, 'Pa',
        'Peak aerodynamic load, q = ½·ρ·v². This is the max-Q moment.'),
      quantity('maxQAltitude', 'Altitude at max-Q', s.maxQAltitude_m, 'm',
        'Where the aerodynamic load peaked.'),
      quantity('maxAcceleration', 'Maximum load factor', s.maxAcceleration_g, 'g',
        'Peak non-gravitational acceleration, as an accelerometer would read it.'),
      quantity('maxDownrange', 'Maximum downrange', s.maxDownrange_m, 'm',
        'Greatest great-circle distance from the launch site.'),
      quantity('propellantUsed', 'Propellant consumed', s.propellantUsed_kg, 'kg',
        'Total propellant burnt across all stages.'),
      quantity('stagesSeparated', 'Stages separated', s.stagesSeparated, 'count',
        'Number of successful stage separations.'),
      ...(s.impactSpeed_ms !== null
        ? [quantity('impactSpeed', 'Impact speed', s.impactSpeed_ms, 'm/s',
            'Speed at which the vehicle reached the surface.')]
        : []),
    ],

    deltaVBudget: {
      ideal_ms: s.deltaVIdeal_ms,
      achieved_ms: s.deltaVAchieved_ms,
      gravityLoss_ms: s.gravityLoss_ms,
      dragLoss_ms: s.dragLoss_ms,
      unaccounted_ms: unaccounted,
      explanation:
        'Ideal delta-v is what the rocket equation promises for the propellant ' +
        'actually burnt. Achieved is the speed the vehicle reached. The ' +
        'difference is loss: gravity loss is the velocity spent holding the ' +
        'vehicle up against its own weight during the climb, and drag loss is ' +
        'the velocity spent pushing air aside. Any remainder is steering loss ' +
        'plus the fact that some of the achieved velocity was traded for ' +
        'altitude rather than kept as speed.',
    },

    timeline: result.events.map(event => ({
      t_s: event.t,
      type: event.type,
      severity: event.severity,
      description: event.description,
      altitude_m: typeof event.data['altitude_m'] === 'number' ? event.data['altitude_m'] : 0,
      speed_ms: typeof event.data['speed_ms'] === 'number' ? event.data['speed_ms'] : 0,
    })),

    failures: result.failures,
    preflightWarnings: [...preflightWarnings],
    modelLimitations: MODEL_LIMITATIONS,
  };
}

/** Assemble a reported quantity. */
function quantity(
  key: string,
  label: string,
  value: number,
  unit: string,
  description: string,
): ReportedQuantity {
  return { key, label, value, unit, description };
}

/**
 * Render the report as compact text, for prompting.
 *
 * Roughly 60 lines rather than the several hundred kilobytes the JSON would be
 * with telemetry attached — and it is the *facts* an explanation needs, not the
 * time series.
 *
 * @param report - The report to render.
 * @returns Plain text, one fact per line.
 */
export function formatReportAsText(report: MissionReport): string {
  const lines: string[] = [];

  lines.push(`MISSION: ${report.mission.name} — ${report.mission.objective}`);
  lines.push(
    `Target: ${report.mission.targetAltitude_km} km ${report.mission.missionType}, ` +
      `launched from ${report.mission.launchSite}, guidance "${report.mission.guidanceMode}".`,
  );
  lines.push('');

  lines.push('VEHICLE');
  lines.push(`  ${report.vehicle.name}, ${report.vehicle.stageCount} stage(s)`);
  lines.push(`  Launch mass ${round(report.vehicle.launchMass_kg)} kg ` +
    `(dry ${round(report.vehicle.dryMass_kg)} kg, propellant ${round(report.vehicle.propellantMass_kg)} kg, ` +
    `payload ${round(report.vehicle.payloadMass_kg)} kg)`);
  lines.push(`  Ideal delta-v ${round(report.vehicle.idealDeltaV_ms)} m/s`);
  lines.push(`  Liftoff thrust-to-weight ${report.vehicle.liftoffTWR.toFixed(2)}`);
  lines.push(`  Static margin ${report.vehicle.stabilityMargin_cal.toFixed(2)} calibers`);
  lines.push('');

  lines.push('OUTCOME');
  lines.push(`  ${report.outcome.result.toUpperCase()} — ${report.outcome.terminationReason}`);
  lines.push(`  Final mission state: ${report.outcome.finalMissionState}`);
  lines.push(`  Flight time ${round(report.outcome.flightTime_s)} s`);
  lines.push('');

  lines.push('MEASUREMENTS');
  for (const m of report.measurements) {
    lines.push(`  ${m.label}: ${formatValue(m.value)} ${m.unit}`);
  }
  lines.push('');

  lines.push('DELTA-V BUDGET (m/s)');
  lines.push(`  Ideal from rocket equation: ${round(report.deltaVBudget.ideal_ms)}`);
  lines.push(`  Achieved as speed:          ${round(report.deltaVBudget.achieved_ms)}`);
  lines.push(`  Lost to gravity:            ${round(report.deltaVBudget.gravityLoss_ms)}`);
  lines.push(`  Lost to drag:               ${round(report.deltaVBudget.dragLoss_ms)}`);
  lines.push(`  Unaccounted:                ${round(report.deltaVBudget.unaccounted_ms)}`);
  lines.push('');

  if (report.preflightWarnings.length > 0) {
    lines.push('PRE-FLIGHT WARNINGS');
    for (const issue of report.preflightWarnings) {
      lines.push(`  [${issue.severity}] ${issue.code}: ${issue.message}`);
    }
    lines.push('');
  }

  lines.push('TIMELINE');
  for (const moment of report.timeline) {
    lines.push(
      `  T+${moment.t_s.toFixed(1).padStart(7)}s  ${moment.type.padEnd(22)} ` +
        `alt ${round(moment.altitude_m).padStart(9)} m  ${moment.description}`,
    );
  }
  lines.push('');

  if (report.failures.length > 0) {
    lines.push('FAILURES');
    for (const f of report.failures) {
      lines.push(`  ${f.failureMode} (${f.subsystem}) at T+${f.t.toFixed(1)}s`);
      lines.push(`    Trigger: ${f.triggerCondition}`);
      lines.push(`    Measured ${formatValue(f.measuredValue)} ${f.unit} against a limit of ${formatValue(f.thresholdValue)} ${f.unit}`);
      lines.push(`    Consequence: ${f.consequence}`);
      lines.push(`    Suggested fix: ${f.recommendedFix}`);
    }
    lines.push('');
  }

  lines.push('MODEL LIMITATIONS — do not attribute behaviour to anything below');
  for (const item of report.modelLimitations.notModelled) {
    lines.push(`  - ${item}`);
  }
  lines.push('');
  lines.push(report.modelLimitations.caveat);

  return lines.join('\n');
}

/** Round to a whole number and stringify. */
function round(value: number): string {
  return Math.round(value).toString();
}

/** Format a value with a sensible number of significant figures. */
function formatValue(value: number): string {
  if (!Number.isFinite(value)) return 'n/a';
  if (Math.abs(value) >= 1000) return Math.round(value).toString();
  if (Math.abs(value) >= 1) return value.toFixed(2);
  return value.toFixed(4);
}

/**
 * The g constant, re-exported so a consumer converting the report's `g` values
 * into m/s² uses the same number the engine did.
 */
export const REPORT_G0 = G0;
