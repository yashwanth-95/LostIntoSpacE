/**
 * Simulation events — the structured record of what happened during a flight.
 *
 * Events are the engine's primary output alongside telemetry, and they serve
 * three consumers:
 *
 * 1. **P1** renders them as a mission timeline.
 * 2. **P2** stores them as rows against a simulation run.
 * 3. **P4** grounds its explanations in them, which is why every failure event
 *    carries a full {@link FailureDetail} rather than only a message string.
 *    An explanation layer that has to infer *why* from prose will invent physics.
 *
 * All event objects are plain data: no methods, no cycles, safe to serialize.
 *
 * @module sim/events
 */

/** Event severity, ordered by impact. */
export type EventSeverity = 'info' | 'warning' | 'critical' | 'fatal';

/**
 * Known event types.
 *
 * A string union rather than an enum, so events serialize as readable strings
 * and new types can be added without renumbering anything.
 */
export type SimEventType =
  // Flight milestones
  | 'ignition'
  | 'liftoff'
  | 'tower_clear'
  | 'supersonic'
  | 'max_q'
  | 'meco'
  | 'staging'
  | 'stage_ignition'
  | 'apogee'
  | 'orbit_insertion'
  | 'payload_deployment'
  | 'entry_interface'
  | 'parachute_deploy'
  | 'landing'
  | 'impact'
  | 'mission_complete'
  // Run control
  | 'target_reached'
  | 'timeout'
  // Failures
  | 'failure'
  | 'failure_twr'
  | 'failure_max_q'
  | 'failure_structural'
  | 'failure_instability'
  | 'failure_trajectory'
  | 'failure_fuel'
  | 'failure_engine'
  | 'failure_tank'
  | 'failure_guidance'
  | 'failure_control'
  | 'failure_separation'
  | 'failure_communication'
  | 'failure_power'
  | 'failure_thermal';

/** A significant moment during flight. */
export interface SimEvent {
  /** Time of occurrence. Unit: s. */
  readonly t: number;
  /** Event classification. */
  readonly type: SimEventType;
  /** Severity. */
  readonly severity: EventSeverity;
  /** Human-readable description. */
  readonly description: string;
  /**
   * Structured data specific to this event — altitude, speed, pressure, stage
   * index, and so on. Machine-readable so P4 can quote exact figures.
   */
  readonly data: Readonly<Record<string, number | string | boolean>>;
  /** Full failure record, present only on failure events. */
  readonly failure?: FailureDetail;
}

/** Which subsystem a failure originated in. */
export type FailureSubsystem =
  | 'propulsion'
  | 'structure'
  | 'aerodynamics'
  | 'trajectory'
  | 'thermal'
  | 'avionics'
  | 'power'
  | 'communication'
  | 'recovery';

/**
 * The complete record of one failure.
 *
 * This is what feeds the "why did it fail?" explanation. Every field is filled
 * from simulation state, never from a template — `triggerState` in particular is
 * a snapshot of the actual numbers at the moment the rule fired.
 */
export interface FailureDetail {
  /**
   * Identifier for this particular failure *occurrence*.
   *
   * For a detected failure this is the mode id. For a scripted one it is the
   * injection's own id, so a lesson can trace which of its scripted faults
   * fired. Use {@link FailureDetail.modeId} to look up behaviour — the two are
   * not interchangeable.
   */
  readonly id: string;
  /**
   * Which failure mode this is, for looking up effects and event types.
   *
   * Kept separate from `id` because an injection's id names the script entry,
   * not the physics. Conflating them means a scripted failure looks up nothing
   * and silently has no effect on the flight.
   */
  readonly modeId: string;
  /** Subsystem that failed. */
  readonly subsystem: FailureSubsystem;
  /** Classification of the failure mode. */
  readonly failureMode: string;
  /** Severity. */
  readonly severity: EventSeverity;
  /** Time of failure. Unit: s. */
  readonly t: number;
  /** Stage involved, or null if the failure is vehicle-wide. */
  readonly stageIndex: number | null;
  /** The condition that fired, written out. */
  readonly triggerCondition: string;
  /** The measured value that crossed the threshold. */
  readonly measuredValue: number;
  /** The threshold it crossed. */
  readonly thresholdValue: number;
  /** Unit of both values, for display. */
  readonly unit: string;
  /** Snapshot of relevant state at the moment of failure. */
  readonly triggerState: Readonly<Record<string, number>>;
  /** Contributing factors, for the explanation. */
  readonly contributingFactors: readonly string[];
  /** What this does to the mission. */
  readonly consequence: string;
  /** Plain-language explanation of the underlying physics. */
  readonly educationalExplanation: string;
  /** A design change that would prevent it. */
  readonly recommendedFix: string;
  /** Slugs of related lessons in the learning system. */
  readonly relatedLessons: readonly string[];
  /**
   * Whether this failure ends the flight. Non-terminal failures degrade the
   * vehicle and the simulation carries on, which is often the more interesting
   * case to watch.
   */
  readonly isTerminal: boolean;
}

/**
 * Build an event. A small helper, but it keeps `severity: 'info'` from being
 * forgotten at the dozen call sites that emit milestones.
 *
 * @param t - Time. Unit: s.
 * @param type - Event type.
 * @param description - Human-readable description.
 * @param data - Structured payload.
 * @param severity - Severity. Defaults to `'info'`.
 * @returns The event.
 */
export function makeEvent(
  t: number,
  type: SimEventType,
  description: string,
  data: Readonly<Record<string, number | string | boolean>> = {},
  severity: EventSeverity = 'info',
): SimEvent {
  return { t, type, severity, description, data };
}

/**
 * Build a failure event with its detail attached.
 *
 * @param type - Failure event type.
 * @param detail - The failure record.
 * @returns The event.
 */
export function makeFailureEvent(
  type: SimEventType,
  detail: FailureDetail,
): SimEvent {
  return {
    t: detail.t,
    type,
    severity: detail.severity,
    description: `${detail.failureMode}: ${detail.consequence}`,
    data: {
      subsystem: detail.subsystem,
      failureMode: detail.failureMode,
      measuredValue: detail.measuredValue,
      thresholdValue: detail.thresholdValue,
      unit: detail.unit,
      isTerminal: detail.isTerminal,
      ...(detail.stageIndex !== null ? { stageIndex: detail.stageIndex } : {}),
    },
    failure: detail,
  };
}

/** Overall outcome of a completed run. */
export type SimOutcome = 'success' | 'partial' | 'failure';

/** Aggregate statistics for a completed run. */
export interface SimSummary {
  /** Peak altitude. Unit: m. */
  readonly maxAltitude_m: number;
  /** Peak speed. Unit: m/s. */
  readonly maxSpeed_ms: number;
  /** Peak acceleration, as a multiple of standard gravity. Unit: g. */
  readonly maxAcceleration_g: number;
  /** Peak dynamic pressure. Unit: Pa. */
  readonly maxDynamicPressure_Pa: number;
  /** Altitude at which dynamic pressure peaked. Unit: m. */
  readonly maxQAltitude_m: number;
  /** Peak Mach number. Dimensionless. */
  readonly maxMach: number;
  /** Total flight time. Unit: s. */
  readonly flightTime_s: number;
  /** Time of apogee. Unit: s. */
  readonly apogeeTime_s: number;
  /** Greatest downrange distance. Unit: m. */
  readonly maxDownrange_m: number;
  /** Impact speed, or null if the vehicle did not come down. Unit: m/s. */
  readonly impactSpeed_ms: number | null;
  /** Number of successful stage separations. */
  readonly stagesSeparated: number;
  /** Propellant consumed. Unit: kg. */
  readonly propellantUsed_kg: number;
  /**
   * Velocity actually gained, against the ideal delta-v the vehicle carried.
   * The gap is the gravity, drag, and steering losses. Unit: m/s.
   */
  readonly deltaVAchieved_ms: number;
  /** Ideal delta-v from the rocket equation. Unit: m/s. */
  readonly deltaVIdeal_ms: number;
  /** Velocity lost to gravity during the climb. Unit: m/s. */
  readonly gravityLoss_ms: number;
  /** Velocity lost to atmospheric drag. Unit: m/s. */
  readonly dragLoss_ms: number;
}
