/**
 * Mission state machine.
 *
 * The machine is **data**, not control flow. States and their outgoing
 * transitions are declared in a table; the runner just evaluates guards. Adding
 * a new mission shape — a lunar transfer, a propulsive landing — means adding
 * rows, not editing the flight loop.
 *
 * A {@link MissionProfile} selects which states a given mission participates in.
 * A suborbital hop never enters `ORBIT`; a satellite launch never enters
 * `LANDING`. Transitions into a state the profile excludes are skipped, and the
 * machine falls through to the next candidate.
 *
 * ## Transient states
 *
 * `MAX_Q`, `STAGE_SEPARATION`, `ORBIT_INSERTION`, and `PAYLOAD_DEPLOYMENT` are
 * *moments*, not phases. They are marked transient: the machine enters them,
 * emits their event, and leaves again within the same step. That keeps them
 * visible in the event timeline and in the UI without pretending the vehicle
 * spends time in them.
 *
 * @module sim/mission-state
 */

import type { SimEventType } from './events.js';

// ============================================================
// States
// ============================================================

/**
 * Every mission state the engine knows.
 *
 * Not every mission uses every state — see {@link MissionProfile}.
 */
export type MissionState =
  | 'PREPARATION'
  | 'COUNTDOWN'
  | 'IGNITION'
  | 'LIFTOFF'
  | 'ASCENT'
  | 'MAX_Q'
  | 'ENGINE_CUTOFF'
  | 'STAGE_SEPARATION'
  | 'ORBIT_INSERTION'
  | 'ORBIT'
  | 'MANEUVER'
  | 'PAYLOAD_DEPLOYMENT'
  | 'TRANSFER'
  | 'ENTRY'
  | 'DESCENT'
  | 'LANDING'
  | 'SURFACE'
  | 'FAILURE'
  | 'COMPLETE';

/** Every state, in roughly chronological order. */
export const MISSION_STATES: readonly MissionState[] = Object.freeze([
  'PREPARATION',
  'COUNTDOWN',
  'IGNITION',
  'LIFTOFF',
  'ASCENT',
  'MAX_Q',
  'ENGINE_CUTOFF',
  'STAGE_SEPARATION',
  'ORBIT_INSERTION',
  'ORBIT',
  'MANEUVER',
  'PAYLOAD_DEPLOYMENT',
  'TRANSFER',
  'ENTRY',
  'DESCENT',
  'LANDING',
  'SURFACE',
  'FAILURE',
  'COMPLETE',
]);

/**
 * States the machine passes straight through.
 *
 * On entering one, the runner emits its event and immediately re-evaluates
 * transitions, so no simulation time is spent inside.
 *
 * `ENGINE_CUTOFF` is deliberately *not* here. The vehicle genuinely spends
 * time between shutdown and separation — that coast is when the stage is
 * pushed clear — so treating it as a moment would make the machine bounce in
 * and out of it on every step of that interval.
 */
export const TRANSIENT_STATES: ReadonlySet<MissionState> = new Set<MissionState>([
  'IGNITION',
  'MAX_Q',
  'STAGE_SEPARATION',
  'ORBIT_INSERTION',
  'PAYLOAD_DEPLOYMENT',
]);

/** States from which no transition is possible. */
export const TERMINAL_STATES: ReadonlySet<MissionState> = new Set<MissionState>([
  'FAILURE',
  'COMPLETE',
]);

// ============================================================
// Transition context
// ============================================================

/**
 * Everything a transition guard is allowed to look at.
 *
 * Guards must be **pure and side-effect free** — the machine may evaluate the
 * same guard several times within one step while resolving transient states.
 */
export interface TransitionContext {
  /** Simulation time. Negative during countdown. Unit: s. */
  readonly time_s: number;
  /** Altitude above mean sea level. Unit: m. */
  readonly altitude_m: number;
  /** Speed magnitude. Unit: m/s. */
  readonly speed_ms: number;
  /** Rate of climb. Unit: m/s. */
  readonly verticalSpeed_ms: number;
  /** Dynamic pressure now. Unit: Pa. */
  readonly dynamicPressure_Pa: number;
  /** Dynamic pressure on the previous step, for detecting the max-Q peak. Unit: Pa. */
  readonly previousDynamicPressure_Pa: number;
  /**
   * Whether the max-Q peak has already been recorded.
   *
   * Dynamic pressure keeps falling for the rest of the ascent, so without this
   * the peak-detection guard would stay true and re-fire on every step.
   */
  readonly maxQPassed: boolean;
  /** Total thrust now. Unit: N. */
  readonly thrust_N: number;
  /** Whether any stage is currently burning. */
  readonly isBurning: boolean;
  /** Index of the stage at the bottom of the stack. */
  readonly activeStage: number;
  /** Whether the active stage has finished its burn. */
  readonly activeStageSpent: boolean;
  /**
   * Whether a stage physically separated on this step.
   *
   * Edge-triggered, not level-triggered: the runner sets it only on the step
   * where separation actually happens, so the machine passes through
   * `STAGE_SEPARATION` exactly once per stage.
   */
  readonly separationDue: boolean;
  /** Whether any stage above the active one can still fire. */
  readonly hasRemainingStages: boolean;
  /** Whether the current state vector describes a closed orbit clear of the surface. */
  readonly isInStableOrbit: boolean;
  /** Whether the mission's target altitude has been reached. */
  readonly targetAltitudeReached: boolean;
  /** Whether the payload has been released. */
  readonly payloadDeployed: boolean;
  /** Whether a fatal failure has occurred. */
  readonly hasFatalFailure: boolean;
  /** Whether the vehicle has touched the surface. */
  readonly hasImpacted: boolean;
  /** Whether the vehicle is descending through the atmosphere from above it. */
  readonly isReentering: boolean;
  /** Whether the mission's objectives are all satisfied. */
  readonly objectivesComplete: boolean;
  /** How long the machine has been in the current state. Unit: s. */
  readonly timeInState_s: number;
}

// ============================================================
// Transition table
// ============================================================

/** One edge in the state machine. */
export interface MissionTransition {
  /** State this edge leaves. */
  readonly from: MissionState;
  /** State this edge enters. */
  readonly to: MissionState;
  /** Condition under which the edge is taken. Must be pure. */
  readonly guard: (ctx: TransitionContext) => boolean;
  /** Event emitted when the edge is taken, if any. */
  readonly event?: SimEventType;
  /** Human-readable description of the edge, used in event descriptions. */
  readonly description: string;
}

/**
 * The transition table.
 *
 * Order matters: for a given `from` state the first edge whose guard passes and
 * whose `to` state the profile permits is the one taken. Failure edges are
 * listed first so a fatal failure always wins.
 */
export const MISSION_TRANSITIONS: readonly MissionTransition[] = Object.freeze([
  // --- Failure can interrupt anything ------------------------------------
  ...MISSION_STATES.filter(s => !TERMINAL_STATES.has(s)).map(from => ({
    from,
    to: 'FAILURE' as MissionState,
    guard: (ctx: TransitionContext) => ctx.hasFatalFailure,
    event: 'failure' as SimEventType,
    description: 'A fatal failure ended the mission',
  })),

  // --- Pre-flight ---------------------------------------------------------
  {
    from: 'PREPARATION',
    to: 'COUNTDOWN',
    guard: () => true,
    description: 'Vehicle configured, countdown started',
  },
  {
    from: 'COUNTDOWN',
    to: 'IGNITION',
    guard: ctx => ctx.time_s >= 0,
    event: 'ignition',
    description: 'Countdown reached zero, engines commanded to start',
  },
  {
    from: 'IGNITION',
    to: 'LIFTOFF',
    guard: ctx => ctx.verticalSpeed_ms > 0.1 && ctx.altitude_m > 0,
    event: 'liftoff',
    description: 'Thrust exceeded weight, vehicle left the pad',
  },
  {
    from: 'IGNITION',
    to: 'ASCENT',
    // Safety valve: if the vehicle somehow gained altitude without the liftoff
    // guard firing, do not strand the machine in a transient state.
    guard: ctx => ctx.altitude_m > 10,
    description: 'Vehicle climbing',
  },

  // --- Ascent -------------------------------------------------------------
  {
    from: 'LIFTOFF',
    to: 'ASCENT',
    guard: ctx => ctx.altitude_m > 50,
    description: 'Clear of the tower, entering the ascent phase',
  },
  {
    from: 'ASCENT',
    to: 'MAX_Q',
    // Dynamic pressure peaks and turns over: it was rising, now it is falling.
    // One-shot — q keeps falling afterwards, so this would otherwise re-fire.
    guard: ctx =>
      !ctx.maxQPassed &&
      ctx.dynamicPressure_Pa > 1_000 &&
      ctx.dynamicPressure_Pa < ctx.previousDynamicPressure_Pa,
    event: 'max_q',
    description: 'Dynamic pressure peaked — maximum aerodynamic load',
  },
  {
    from: 'MAX_Q',
    to: 'ASCENT',
    guard: () => true,
    description: 'Past maximum dynamic pressure',
  },
  {
    from: 'ASCENT',
    to: 'ENGINE_CUTOFF',
    guard: ctx => ctx.activeStageSpent,
    // No event here: the runner emits `meco` itself, because it knows which
    // stage cut off and this transition does not.
    description: 'Stage propellant exhausted, engines shut down',
  },
  {
    from: 'ENGINE_CUTOFF',
    to: 'STAGE_SEPARATION',
    guard: ctx => ctx.separationDue && ctx.hasRemainingStages,
    // The runner emits `staging` with the stage index.
    description: 'Spent stage jettisoned',
  },
  {
    from: 'ENGINE_CUTOFF',
    to: 'ORBIT_INSERTION',
    guard: ctx => ctx.isInStableOrbit,
    event: 'orbit_insertion',
    description: 'Final burn complete with a closed orbit achieved',
  },
  {
    from: 'ENGINE_CUTOFF',
    to: 'ASCENT',
    guard: ctx => ctx.isBurning,
    description: 'Next stage lit, ascent continues',
  },
  {
    from: 'ENGINE_CUTOFF',
    to: 'DESCENT',
    guard: ctx => !ctx.hasRemainingStages && ctx.verticalSpeed_ms < 0,
    description: 'No stages left and falling — ballistic descent',
  },
  {
    from: 'STAGE_SEPARATION',
    to: 'ASCENT',
    guard: () => true,
    description: 'Separation complete, ascent continues',
  },

  // --- Orbit --------------------------------------------------------------
  {
    from: 'ASCENT',
    to: 'ORBIT_INSERTION',
    guard: ctx => ctx.isInStableOrbit && !ctx.isBurning,
    event: 'orbit_insertion',
    description: 'Closed orbit achieved',
  },
  {
    from: 'ORBIT_INSERTION',
    to: 'ORBIT',
    guard: () => true,
    description: 'Coasting in orbit',
  },
  {
    from: 'ORBIT',
    to: 'PAYLOAD_DEPLOYMENT',
    guard: ctx => !ctx.payloadDeployed && ctx.timeInState_s > 5,
    event: 'payload_deployment',
    description: 'Payload released',
  },
  {
    from: 'PAYLOAD_DEPLOYMENT',
    to: 'ORBIT',
    guard: () => true,
    description: 'Payload away, vehicle continues in orbit',
  },
  {
    from: 'ORBIT',
    to: 'MANEUVER',
    guard: ctx => ctx.isBurning,
    description: 'Orbital burn underway',
  },
  {
    from: 'MANEUVER',
    to: 'ORBIT',
    guard: ctx => !ctx.isBurning,
    description: 'Burn complete',
  },
  {
    from: 'ORBIT',
    to: 'TRANSFER',
    guard: ctx => ctx.targetAltitudeReached && ctx.isBurning,
    description: 'Departing on a transfer trajectory',
  },
  {
    from: 'TRANSFER',
    to: 'ORBIT',
    guard: ctx => ctx.isInStableOrbit && !ctx.isBurning,
    description: 'Transfer complete, orbit re-established',
  },
  {
    from: 'ORBIT',
    to: 'COMPLETE',
    guard: ctx => ctx.objectivesComplete,
    event: 'mission_complete',
    description: 'Mission objectives satisfied',
  },
  {
    from: 'ORBIT',
    to: 'ENTRY',
    guard: ctx => ctx.isReentering,
    event: 'entry_interface',
    description: 'Orbit decayed into the atmosphere',
  },

  // --- Descent and landing ------------------------------------------------
  {
    from: 'ASCENT',
    to: 'DESCENT',
    guard: ctx => ctx.verticalSpeed_ms < 0 && !ctx.isBurning,
    event: 'apogee',
    description: 'Apogee passed, vehicle now falling',
  },
  {
    from: 'DESCENT',
    to: 'ENTRY',
    guard: ctx => ctx.isReentering,
    event: 'entry_interface',
    description: 'Vehicle entered the sensible atmosphere at high speed',
  },
  {
    from: 'ENTRY',
    to: 'DESCENT',
    guard: ctx => ctx.speed_ms < 1_000 && ctx.altitude_m < 50_000,
    description: 'Slowed below entry speeds',
  },
  {
    from: 'DESCENT',
    to: 'LANDING',
    guard: ctx => ctx.altitude_m < 1_000 && ctx.verticalSpeed_ms < 0,
    description: 'Approaching the surface',
  },
  {
    from: 'LANDING',
    to: 'SURFACE',
    guard: ctx => ctx.hasImpacted,
    event: 'landing',
    description: 'Vehicle reached the surface',
  },
  {
    from: 'DESCENT',
    to: 'SURFACE',
    // A vehicle that skips LANDING — because the profile excludes it, or
    // because it arrived too fast for the landing guard to catch a step.
    guard: ctx => ctx.hasImpacted,
    event: 'impact',
    description: 'Vehicle struck the surface',
  },
  {
    from: 'SURFACE',
    to: 'COMPLETE',
    guard: () => true,
    event: 'mission_complete',
    description: 'Flight over',
  },
]);

// ============================================================
// Mission profiles
// ============================================================

/** Which states a given kind of mission participates in. */
export interface MissionProfile {
  /** Stable identifier. */
  readonly id: string;
  /** Display name. */
  readonly name: string;
  /** What this profile is for. */
  readonly description: string;
  /** States this mission may enter. */
  readonly states: ReadonlySet<MissionState>;
  /** Reaching this state means the mission succeeded. */
  readonly successState: MissionState;
}

/** Build a profile from a state list, always including the terminal states. */
function profile(
  id: string,
  name: string,
  description: string,
  states: readonly MissionState[],
  successState: MissionState,
): MissionProfile {
  return {
    id,
    name,
    description,
    states: new Set<MissionState>([...states, 'FAILURE', 'COMPLETE']),
    successState,
  };
}

/**
 * A ballistic hop: up, over the top, and back down. No orbit states.
 */
export const SUBORBITAL_PROFILE: MissionProfile = profile(
  'suborbital',
  'Suborbital Flight',
  'Launch, coast through apogee, and return to the surface.',
  [
    'PREPARATION', 'COUNTDOWN', 'IGNITION', 'LIFTOFF', 'ASCENT', 'MAX_Q',
    'ENGINE_CUTOFF', 'STAGE_SEPARATION', 'DESCENT', 'LANDING', 'SURFACE',
  ],
  'SURFACE',
);

/**
 * Ascent to a closed orbit, then payload release.
 */
export const ORBITAL_PROFILE: MissionProfile = profile(
  'orbital',
  'Orbital Insertion',
  'Ascend to a stable orbit and release the payload.',
  [
    'PREPARATION', 'COUNTDOWN', 'IGNITION', 'LIFTOFF', 'ASCENT', 'MAX_Q',
    'ENGINE_CUTOFF', 'STAGE_SEPARATION', 'ORBIT_INSERTION', 'ORBIT',
    'MANEUVER', 'PAYLOAD_DEPLOYMENT',
  ],
  'COMPLETE',
);

/**
 * Orbital insertion followed by a deorbit, entry, and landing.
 */
export const RETURN_PROFILE: MissionProfile = profile(
  'return',
  'Orbit and Return',
  'Reach orbit, then deorbit, survive entry, and land.',
  [
    'PREPARATION', 'COUNTDOWN', 'IGNITION', 'LIFTOFF', 'ASCENT', 'MAX_Q',
    'ENGINE_CUTOFF', 'STAGE_SEPARATION', 'ORBIT_INSERTION', 'ORBIT',
    'MANEUVER', 'PAYLOAD_DEPLOYMENT', 'ENTRY', 'DESCENT', 'LANDING', 'SURFACE',
  ],
  'SURFACE',
);

/** Every built-in profile, keyed by id. */
export const MISSION_PROFILES: Readonly<Record<string, MissionProfile>> = Object.freeze({
  suborbital: SUBORBITAL_PROFILE,
  orbital: ORBITAL_PROFILE,
  return: RETURN_PROFILE,
});

// ============================================================
// Evaluation
// ============================================================

/** The outcome of advancing the state machine. */
export interface TransitionResult {
  /** The state the machine settled in. */
  readonly state: MissionState;
  /** Transitions taken this step, in order. Empty if nothing changed. */
  readonly taken: readonly MissionTransition[];
}

/**
 * Guard against a cycle in the transition table wedging the runner.
 *
 * Legitimate chains are short — the longest is
 * `ENGINE_CUTOFF → STAGE_SEPARATION → ASCENT`, three hops. Ten is generous
 * headroom while still catching a genuine loop immediately.
 */
const MAX_CHAINED_TRANSITIONS = 10;

/** Index the table by `from` state so evaluation does not rescan it. */
const TRANSITIONS_BY_STATE: ReadonlyMap<MissionState, readonly MissionTransition[]> =
  (() => {
    const map = new Map<MissionState, MissionTransition[]>();
    for (const transition of MISSION_TRANSITIONS) {
      const list = map.get(transition.from);
      if (list) {
        list.push(transition);
      } else {
        map.set(transition.from, [transition]);
      }
    }
    return map;
  })();

/**
 * Advance the mission state machine by evaluating guards.
 *
 * Chains through transient states within a single call, so a step that lands on
 * `ENGINE_CUTOFF` can come out the far side already back in `ASCENT`, with both
 * transitions reported.
 *
 * @param current - State to advance from.
 * @param ctx - What the guards may look at.
 * @param missionProfile - Restricts which states may be entered.
 * @returns The settled state and every transition taken to get there.
 */
export function advanceMissionState(
  current: MissionState,
  ctx: TransitionContext,
  missionProfile: MissionProfile,
): TransitionResult {
  const taken: MissionTransition[] = [];
  let state = current;

  for (let hop = 0; hop < MAX_CHAINED_TRANSITIONS; hop++) {
    if (TERMINAL_STATES.has(state)) break;

    const candidates = TRANSITIONS_BY_STATE.get(state);
    if (!candidates) break;

    const next = candidates.find(
      t => missionProfile.states.has(t.to) && t.guard(ctx),
    );
    if (!next) break;

    taken.push(next);
    state = next.to;

    // Non-transient states are where the machine rests until the next step.
    if (!TRANSIENT_STATES.has(state)) break;
  }

  return { state, taken };
}

/**
 * Whether a state means the mission is over, either way.
 *
 * @param state - State to test.
 * @returns True for `FAILURE` and `COMPLETE`.
 */
export function isTerminalState(state: MissionState): boolean {
  return TERMINAL_STATES.has(state);
}

/**
 * Whether a state is one the machine passes straight through.
 *
 * @param state - State to test.
 * @returns True for the moment-in-time states.
 */
export function isTransientState(state: MissionState): boolean {
  return TRANSIENT_STATES.has(state);
}
