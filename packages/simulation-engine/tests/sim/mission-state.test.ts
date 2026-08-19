import { describe, it, expect } from 'vitest';
import {
  advanceMissionState,
  isTerminalState,
  isTransientState,
  MISSION_STATES,
  MISSION_TRANSITIONS,
  TRANSIENT_STATES,
  TERMINAL_STATES,
  SUBORBITAL_PROFILE,
  ORBITAL_PROFILE,
  RETURN_PROFILE,
  MISSION_PROFILES,
  type MissionState,
  type TransitionContext,
} from '../../src/sim/mission-state.js';

/** A context describing a healthy vehicle mid-ascent. */
const ASCENDING: TransitionContext = {
  time_s: 30,
  altitude_m: 20_000,
  speed_ms: 900,
  verticalSpeed_ms: 700,
  dynamicPressure_Pa: 20_000,
  previousDynamicPressure_Pa: 22_000,
  maxQPassed: true,
  thrust_N: 500_000,
  isBurning: true,
  activeStage: 0,
  activeStageSpent: false,
  separationDue: false,
  hasRemainingStages: true,
  isInStableOrbit: false,
  targetAltitudeReached: false,
  payloadDeployed: false,
  hasFatalFailure: false,
  hasImpacted: false,
  isReentering: false,
  objectivesComplete: false,
  timeInState_s: 5,
};

const ctx = (overrides: Partial<TransitionContext>): TransitionContext => ({
  ...ASCENDING,
  ...overrides,
});

describe('state machine structure', () => {
  it('lists every state exactly once', () => {
    expect(new Set(MISSION_STATES).size).toBe(MISSION_STATES.length);
  });

  it('has all 19 states the mission model calls for', () => {
    expect(MISSION_STATES).toHaveLength(19);
  });

  it('gives every transition a described, existing source and target', () => {
    const known = new Set<MissionState>(MISSION_STATES);
    for (const t of MISSION_TRANSITIONS) {
      expect(known.has(t.from), `unknown from: ${t.from}`).toBe(true);
      expect(known.has(t.to), `unknown to: ${t.to}`).toBe(true);
      expect(t.description.length).toBeGreaterThan(5);
    }
  });

  it('lets a fatal failure interrupt every non-terminal state', () => {
    for (const state of MISSION_STATES) {
      if (TERMINAL_STATES.has(state)) continue;
      const result = advanceMissionState(state, ctx({ hasFatalFailure: true }), RETURN_PROFILE);
      expect(result.state, `${state} did not reach FAILURE`).toBe('FAILURE');
    }
  });

  it('never leaves a terminal state', () => {
    for (const state of ['FAILURE', 'COMPLETE'] as MissionState[]) {
      const result = advanceMissionState(state, ctx({ hasImpacted: true }), RETURN_PROFILE);
      expect(result.state).toBe(state);
      expect(result.taken).toEqual([]);
    }
  });

  it('does not treat ENGINE_CUTOFF as a moment', () => {
    // The vehicle genuinely coasts between cutoff and separation; marking it
    // transient made the machine bounce in and out of it on every step.
    expect(TRANSIENT_STATES.has('ENGINE_CUTOFF')).toBe(false);
    expect(isTransientState('MAX_Q')).toBe(true);
    expect(isTerminalState('COMPLETE')).toBe(true);
    expect(isTerminalState('ASCENT')).toBe(false);
  });
});

describe('pre-flight sequence', () => {
  it('moves straight from preparation into countdown', () => {
    expect(
      advanceMissionState('PREPARATION', ctx({ time_s: -3 }), SUBORBITAL_PROFILE).state,
    ).toBe('COUNTDOWN');
  });

  it('waits in countdown until T-zero', () => {
    expect(
      advanceMissionState('COUNTDOWN', ctx({ time_s: -1 }), SUBORBITAL_PROFILE).state,
    ).toBe('COUNTDOWN');
  });

  it('ignites at T-zero and passes straight through to liftoff when climbing', () => {
    const result = advanceMissionState(
      'COUNTDOWN',
      ctx({ time_s: 0, altitude_m: 5, verticalSpeed_ms: 2 }),
      SUBORBITAL_PROFILE,
    );
    // IGNITION is transient, so one call resolves both hops.
    expect(result.state).toBe('LIFTOFF');
    expect(result.taken.map(t => t.to)).toEqual(['IGNITION', 'LIFTOFF']);
  });

  it('emits the ignition event on the countdown transition', () => {
    const result = advanceMissionState(
      'COUNTDOWN',
      ctx({ time_s: 0, altitude_m: 0, verticalSpeed_ms: 0 }),
      SUBORBITAL_PROFILE,
    );
    expect(result.taken[0]!.event).toBe('ignition');
  });

  it('stays in ignition while the vehicle sits on the pad', () => {
    // The pad-abort case: engines lit, nothing moving.
    const result = advanceMissionState(
      'IGNITION',
      ctx({ time_s: 2, altitude_m: 0, verticalSpeed_ms: 0 }),
      SUBORBITAL_PROFILE,
    );
    expect(result.state).toBe('IGNITION');
  });
});

describe('ascent', () => {
  it('enters ascent once clear of the tower', () => {
    expect(
      advanceMissionState('LIFTOFF', ctx({ altitude_m: 100 }), SUBORBITAL_PROFILE).state,
    ).toBe('ASCENT');
  });

  it('detects max-Q when dynamic pressure turns over', () => {
    const result = advanceMissionState(
      'ASCENT',
      ctx({
        maxQPassed: false,
        dynamicPressure_Pa: 30_000,
        previousDynamicPressure_Pa: 31_000,
      }),
      SUBORBITAL_PROFILE,
    );
    // MAX_Q is transient, so the machine passes through and returns to ASCENT.
    expect(result.state).toBe('ASCENT');
    expect(result.taken.map(t => t.to)).toEqual(['MAX_Q', 'ASCENT']);
    expect(result.taken[0]!.event).toBe('max_q');
  });

  it('does not re-detect max-Q once it has passed', () => {
    // Dynamic pressure keeps falling for the whole rest of the ascent, so
    // without the one-shot guard this fired on every subsequent step.
    const result = advanceMissionState(
      'ASCENT',
      ctx({
        maxQPassed: true,
        dynamicPressure_Pa: 10_000,
        previousDynamicPressure_Pa: 12_000,
      }),
      SUBORBITAL_PROFILE,
    );
    expect(result.taken).toEqual([]);
  });

  it('does not call a low-pressure wobble max-Q', () => {
    const result = advanceMissionState(
      'ASCENT',
      ctx({ maxQPassed: false, dynamicPressure_Pa: 500, previousDynamicPressure_Pa: 600 }),
      SUBORBITAL_PROFILE,
    );
    expect(result.state).toBe('ASCENT');
  });

  it('enters engine cutoff when the stage is spent', () => {
    expect(
      advanceMissionState(
        'ASCENT',
        ctx({ activeStageSpent: true, isBurning: false }),
        SUBORBITAL_PROFILE,
      ).state,
    ).toBe('ENGINE_CUTOFF');
  });

  it('stays in engine cutoff until a stage actually separates', () => {
    const waiting = advanceMissionState(
      'ENGINE_CUTOFF',
      ctx({ activeStageSpent: true, isBurning: false, separationDue: false }),
      ORBITAL_PROFILE,
    );
    expect(waiting.state).toBe('ENGINE_CUTOFF');
    expect(waiting.taken).toEqual([]);
  });

  it('passes through staging on the step separation happens', () => {
    const result = advanceMissionState(
      'ENGINE_CUTOFF',
      ctx({ separationDue: true, hasRemainingStages: true, isBurning: false }),
      ORBITAL_PROFILE,
    );
    expect(result.state).toBe('ASCENT');
    expect(result.taken.map(t => t.to)).toEqual(['STAGE_SEPARATION', 'ASCENT']);
  });

  it('returns to ascent when the next stage lights', () => {
    expect(
      advanceMissionState(
        'ENGINE_CUTOFF',
        ctx({ isBurning: true, separationDue: false, hasRemainingStages: false }),
        ORBITAL_PROFILE,
      ).state,
    ).toBe('ASCENT');
  });

  it('falls into descent when nothing is left to burn', () => {
    expect(
      advanceMissionState(
        'ENGINE_CUTOFF',
        ctx({
          isBurning: false,
          separationDue: false,
          hasRemainingStages: false,
          verticalSpeed_ms: -50,
        }),
        SUBORBITAL_PROFILE,
      ).state,
    ).toBe('DESCENT');
  });

  it('marks apogee when the vehicle starts falling', () => {
    const result = advanceMissionState(
      'ASCENT',
      ctx({ verticalSpeed_ms: -10, isBurning: false, activeStageSpent: false }),
      SUBORBITAL_PROFILE,
    );
    expect(result.state).toBe('DESCENT');
    expect(result.taken[0]!.event).toBe('apogee');
  });
});

describe('orbit', () => {
  it('inserts into orbit and settles there', () => {
    const result = advanceMissionState(
      'ASCENT',
      ctx({ isInStableOrbit: true, isBurning: false, altitude_m: 250_000 }),
      ORBITAL_PROFILE,
    );
    expect(result.state).toBe('ORBIT');
    expect(result.taken.map(t => t.to)).toEqual(['ORBIT_INSERTION', 'ORBIT']);
  });

  it('deploys the payload after a settling period', () => {
    const early = advanceMissionState(
      'ORBIT',
      ctx({ isInStableOrbit: true, isBurning: false, timeInState_s: 1 }),
      ORBITAL_PROFILE,
    );
    expect(early.state).toBe('ORBIT');

    const later = advanceMissionState(
      'ORBIT',
      ctx({ isInStableOrbit: true, isBurning: false, timeInState_s: 10 }),
      ORBITAL_PROFILE,
    );
    expect(later.state).toBe('ORBIT');
    expect(later.taken.map(t => t.to)).toEqual(['PAYLOAD_DEPLOYMENT', 'ORBIT']);
  });

  it('completes once the objectives are met', () => {
    expect(
      advanceMissionState(
        'ORBIT',
        ctx({ payloadDeployed: true, objectivesComplete: true, isBurning: false }),
        ORBITAL_PROFILE,
      ).state,
    ).toBe('COMPLETE');
  });

  it('enters a manoeuvre when the engines relight in orbit', () => {
    expect(
      advanceMissionState(
        'ORBIT',
        ctx({ payloadDeployed: true, isBurning: true, isInStableOrbit: true }),
        ORBITAL_PROFILE,
      ).state,
    ).toBe('MANEUVER');
  });
});

describe('mission profiles', () => {
  it('keeps a suborbital flight out of the orbit states', () => {
    const result = advanceMissionState(
      'ASCENT',
      ctx({ isInStableOrbit: true, isBurning: false, altitude_m: 300_000 }),
      SUBORBITAL_PROFILE,
    );
    // ORBIT_INSERTION is not in the suborbital profile, so it is skipped.
    expect(result.state).not.toBe('ORBIT');
  });

  it('keeps an orbital insertion mission out of the landing states', () => {
    const result = advanceMissionState(
      'DESCENT',
      ctx({ altitude_m: 500, verticalSpeed_ms: -20 }),
      ORBITAL_PROFILE,
    );
    expect(result.state).not.toBe('LANDING');
  });

  it('gives every profile the terminal states', () => {
    for (const profile of Object.values(MISSION_PROFILES)) {
      expect(profile.states.has('FAILURE')).toBe(true);
      expect(profile.states.has('COMPLETE')).toBe(true);
    }
  });

  it('names a success state each profile can actually reach', () => {
    for (const profile of Object.values(MISSION_PROFILES)) {
      expect(profile.states.has(profile.successState)).toBe(true);
    }
  });
});

describe('descent and landing', () => {
  it('recognises entry from a fast, descending trajectory', () => {
    expect(
      advanceMissionState(
        'DESCENT',
        ctx({ isReentering: true, verticalSpeed_ms: -2_000, speed_ms: 6_000 }),
        RETURN_PROFILE,
      ).state,
    ).toBe('ENTRY');
  });

  it('leaves entry once the vehicle has slowed', () => {
    expect(
      advanceMissionState(
        'ENTRY',
        ctx({ speed_ms: 400, altitude_m: 30_000, verticalSpeed_ms: -300, isReentering: false }),
        RETURN_PROFILE,
      ).state,
    ).toBe('DESCENT');
  });

  it('lands and completes', () => {
    const landing = advanceMissionState(
      'DESCENT',
      ctx({ altitude_m: 500, verticalSpeed_ms: -30, isReentering: false }),
      SUBORBITAL_PROFILE,
    );
    expect(landing.state).toBe('LANDING');

    const down = advanceMissionState(
      'LANDING',
      ctx({ hasImpacted: true, altitude_m: 0, verticalSpeed_ms: -5 }),
      SUBORBITAL_PROFILE,
    );
    expect(down.state).toBe('SURFACE');
  });

  it('goes straight to the surface for a vehicle that arrives too fast to catch', () => {
    const result = advanceMissionState(
      'DESCENT',
      ctx({ hasImpacted: true, altitude_m: 0, verticalSpeed_ms: -400, isReentering: false }),
      ORBITAL_PROFILE,
    );
    // The orbital profile has no LANDING state, so DESCENT → SURFACE is used.
    expect(result.state).not.toBe('LANDING');
  });
});

describe('guard purity', () => {
  it('leaves the context untouched', () => {
    const context = ctx({ separationDue: true });
    const snapshot = JSON.stringify(context);
    advanceMissionState('ENGINE_CUTOFF', context, ORBITAL_PROFILE);
    expect(JSON.stringify(context)).toBe(snapshot);
  });

  it('gives the same answer when evaluated repeatedly', () => {
    const context = ctx({ activeStageSpent: true, isBurning: false });
    const first = advanceMissionState('ASCENT', context, ORBITAL_PROFILE);
    const second = advanceMissionState('ASCENT', context, ORBITAL_PROFILE);
    expect(second.state).toBe(first.state);
  });
});
