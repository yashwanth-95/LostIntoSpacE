/**
 * Simulation event types — structured events emitted during simulation.
 *
 * Events are the primary mechanism for:
 * 1. The failure engine to communicate what went wrong
 * 2. The telemetry system to mark significant moments
 * 3. The AI explanation layer (P4) to ground its responses
 *
 * All events are plain objects with no methods, safe for serialization.
 *
 * @module sim/events
 */

/** Event severity levels, ordered by impact. */
export type EventSeverity = 'info' | 'warning' | 'critical' | 'fatal';

/**
 * Known simulation event types.
 *
 * Using a string union (not an enum) so events serialize as readable strings
 * and are extensible without version-breaking changes.
 */
export type SimEventType =
  | 'ignition'
  | 'liftoff'
  | 'max_q'
  | 'meco'          // Main engine cutoff
  | 'staging'
  | 'apogee'
  | 'supersonic'
  | 'impact'
  | 'target_reached'
  | 'timeout'
  // Failure events
  | 'failure_twr'           // Thrust-to-weight ratio < 1
  | 'failure_max_q'         // Dynamic pressure exceeded limit
  | 'failure_structural'    // Acceleration exceeded g-limit
  | 'failure_instability'   // CP ahead of CG
  | 'failure_trajectory'    // Trajectory divergence
  | 'failure_fuel';         // Unexpected fuel exhaustion

/**
 * A simulation event — a significant moment during flight.
 */
export interface SimEvent {
  /** Time of occurrence. Unit: s */
  readonly t: number;
  /** Event classification. */
  readonly type: SimEventType;
  /** Severity level. */
  readonly severity: EventSeverity;
  /** Human-readable description. */
  readonly description: string;
  /** Event-specific structured data (altitude, velocity, pressure, etc.) */
  readonly data: Readonly<Record<string, unknown>>;
}

/** The subsystem where a failure originated. */
export type FailureSubsystem =
  | 'propulsion'
  | 'structure'
  | 'aerodynamics'
  | 'trajectory'
  | 'thermal';

/**
 * Detailed failure information, attached to failure-type SimEvents.
 *
 * This is the data that feeds the "Why Did It Fail?" explanation pipeline.
 */
export interface FailureDetail {
  /** Which subsystem failed. */
  readonly subsystem: FailureSubsystem;
  /** Classification of the failure mode. */
  readonly failureMode: string;
  /** The condition that triggered this failure. */
  readonly triggerCondition: string;
  /** Snapshot of relevant state values at failure time. */
  readonly triggerState: Readonly<Record<string, number>>;
  /** Contributing factors (for educational explanation). */
  readonly contributingFactors: readonly string[];
  /** What happens to the mission as a result. */
  readonly consequence: string;
  /** Plain-language educational explanation. */
  readonly educationalExplanation: string;
  /** Suggested design change to fix this failure. */
  readonly recommendedFix: string;
  /** Slugs of related lessons in the learning system. */
  readonly relatedLessons: readonly string[];
}

/** Outcome of a completed simulation. */
export type SimOutcome = 'success' | 'partial' | 'failure';

/**
 * Summary statistics for a completed simulation run.
 */
export interface SimSummary {
  /** Peak altitude reached. Unit: m */
  readonly maxAltitude_m: number;
  /** Peak speed. Unit: m/s */
  readonly maxSpeed_ms: number;
  /** Peak acceleration. Unit: g (multiples of G0) */
  readonly maxAcceleration_g: number;
  /** Peak dynamic pressure. Unit: Pa */
  readonly maxDynamicPressure_Pa: number;
  /** Peak Mach number. Dimensionless. */
  readonly maxMach: number;
  /** Total flight time. Unit: s */
  readonly flightTime_s: number;
  /** Time of apogee. Unit: s */
  readonly apogeeTime_s: number;
  /** Impact velocity (null if no impact). Unit: m/s */
  readonly impactSpeed_ms: number | null;
  /** Number of successful stage separations. */
  readonly stagesSeparated: number;
}

/**
 * A single telemetry sample — a snapshot of simulation state at one time.
 */
export interface TelemetryPoint {
  /** Time. Unit: s */
  readonly t: number;
  /** Altitude above launch site. Unit: m */
  readonly altitude_m: number;
  /** Speed magnitude. Unit: m/s */
  readonly speed_ms: number;
  /** Acceleration magnitude. Unit: m/s² */
  readonly acceleration_ms2: number;
  /** Current mass. Unit: kg */
  readonly mass_kg: number;
  /** Current thrust. Unit: N */
  readonly thrust_N: number;
  /** Current drag force. Unit: N */
  readonly drag_N: number;
  /** Dynamic pressure (q). Unit: Pa */
  readonly dynamicPressure_Pa: number;
  /** Mach number. Dimensionless. */
  readonly mach: number;
  /** Active stage index. */
  readonly stage: number;
  /** Current mission phase. */
  readonly phase: string;
  /** Downrange distance. Unit: m */
  readonly downrange_m: number;
}

/**
 * The complete result of a simulation run.
 *
 * This is the output of `runSimulation()` and the primary data
 * consumed by the renderer, analysis engine, and AI explanation pipeline.
 */
export interface SimResult {
  /** Whether the mission objective was achieved. */
  readonly success: boolean;
  /** Overall outcome classification. */
  readonly outcome: SimOutcome;
  /** Aggregate statistics. */
  readonly summary: SimSummary;
  /** Sampled telemetry timeline. */
  readonly telemetry: readonly TelemetryPoint[];
  /** All events that occurred during the simulation. */
  readonly events: readonly SimEvent[];
  /** Detailed failure information (empty if no failures). */
  readonly failures: readonly FailureDetail[];
  /** Error messages (empty if simulation ran without errors). */
  readonly errors: readonly string[];
  /** Total integration steps computed. */
  readonly totalSteps: number;
  /** Wall-clock duration of the simulation computation. Unit: s */
  readonly wallTime_s: number;
}
