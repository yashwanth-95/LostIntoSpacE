import { describe, it, expect } from 'vitest';
import { toVehicle } from '../../src/core/vehicle.js';
import { createSimConfig, type SimConfig } from '../../src/sim/config.js';
import { runSimulation } from '../../src/sim/runner.js';
import { SUBORBITAL_PROFILE } from '../../src/sim/mission-state.js';
import { VERTICAL_GUIDANCE } from '../../src/sim/guidance.js';
import {
  FAILURE_MODES,
  combinedEffects,
  detectFailures,
  failureEventType,
  SeededRandom,
  checkInjections,
  DEFAULT_FAILURE_CONFIG,
  type FailureConfig,
  type FailureInjection,
} from '../../src/sim/failures.js';
import type { FailureDetail } from '../../src/sim/events.js';
import {
  DEFAULT_LAUNCH_SITE,
  DEFAULT_ENVIRONMENT,
  type MissionConfig,
} from '../../src/core/types.js';
import { stockRegistry, recoverableSoundingRocket } from '../core/reference-designs.js';

const registry = stockRegistry();

const mission: MissionConfig = {
  name: 'Failure Test',
  objective: 'Exercise the failure system',
  target: { type: 'suborbital', targetAltitude_km: 30 },
  launchSite: DEFAULT_LAUNCH_SITE,
  environment: DEFAULT_ENVIRONMENT,
};

function configWith(injections: readonly FailureInjection[]): SimConfig {
  return createSimConfig(
    toVehicle(recoverableSoundingRocket(registry), registry),
    mission,
    {
      profile: SUBORBITAL_PROFILE,
      guidance: VERTICAL_GUIDANCE,
      failures: { ...DEFAULT_FAILURE_CONFIG, injections },
    },
  );
}

/** Measurements for a healthy vehicle mid-ascent. */
const NOMINAL = {
  t: 20,
  dt_s: 0.05,
  altitude_m: 5_000,
  speed_ms: 300,
  verticalSpeed_ms: 300,
  gLoad_g: 3,
  dynamicPressure_Pa: 40_000,
  thrust_N: 30_000,
  mass_kg: 1_500,
  activeStage: 0,
  isBurning: true,
  hasLiftedOff: true,
  burnTimeOnPad_s: 0,
};

const vehicle = toVehicle(recoverableSoundingRocket(registry), registry);

describe('failure mode catalogue', () => {
  it('gives every mode a full educational record', () => {
    for (const [id, spec] of Object.entries(FAILURE_MODES)) {
      expect(spec.name, id).toBeTruthy();
      expect(spec.consequence, id).toBeTruthy();
      expect(spec.educationalExplanation.length, id).toBeGreaterThan(80);
      expect(spec.recommendedFix, id).toBeTruthy();
      expect(spec.relatedLessons.length, id).toBeGreaterThan(0);
      expect(spec.eventType, id).toMatch(/^failure/);
    }
  });

  it('gives every mode at least one effect', () => {
    for (const [id, spec] of Object.entries(FAILURE_MODES)) {
      const hasEffect = Object.values(spec.effects).some(Boolean);
      expect(hasEffect, `${id} does nothing`).toBe(true);
    }
  });
});

describe('combinedEffects', () => {
  const detail = (modeId: string): FailureDetail => ({
    id: `occurrence-of-${modeId}`,
    modeId,
    subsystem: 'propulsion',
    failureMode: modeId,
    severity: 'critical',
    t: 0,
    stageIndex: null,
    triggerCondition: '',
    measuredValue: 0,
    thresholdValue: 0,
    unit: '',
    triggerState: {},
    contributingFactors: [],
    consequence: '',
    educationalExplanation: '',
    recommendedFix: '',
    relatedLessons: [],
    isTerminal: false,
  });

  it('returns no effects for no failures', () => {
    const effects = combinedEffects([]);
    expect(Object.values(effects).every(v => v === false)).toBe(true);
  });

  it('accumulates the effects of several failures', () => {
    const effects = combinedEffects([
      detail('engine_shutdown'),
      detail('guidance_failure'),
    ]);
    expect(effects.killThrust).toBe(true);
    expect(effects.freezeGuidance).toBe(true);
    expect(effects.destroyVehicle).toBe(false);
  });

  it('ignores an unrecognised failure mode rather than throwing', () => {
    expect(() => combinedEffects([detail('not_a_real_mode')])).not.toThrow();
  });

  it('applies effects to a scripted failure whose id differs from its mode', () => {
    // The occurrence id is arbitrary; the mode is what carries the physics.
    const effects = combinedEffects([
      { ...detail('engine_shutdown'), id: 'lesson-3-fault-a' },
    ]);
    expect(effects.killThrust).toBe(true);
  });
});

describe('detectFailures', () => {
  it('finds nothing wrong with a nominal flight', () => {
    expect(detectFailures(NOMINAL, vehicle, DEFAULT_FAILURE_CONFIG)).toEqual([]);
  });

  it('detects excessive load factor', () => {
    const detected = detectFailures(
      { ...NOMINAL, gLoad_g: 20 },
      vehicle,
      DEFAULT_FAILURE_CONFIG,
    );
    expect(detected.map(f => f.id)).toContain('excessive_g_load');
  });

  it('detects dynamic pressure beyond the airframe limit', () => {
    const detected = detectFailures(
      { ...NOMINAL, dynamicPressure_Pa: vehicle.maxDynamicPressure_Pa * 1.5 },
      vehicle,
      DEFAULT_FAILURE_CONFIG,
    );
    expect(detected.map(f => f.id)).toContain('aerodynamic_breakup');
  });

  it('detects a pad abort only after a couple of seconds of burning', () => {
    const stuck = {
      ...NOMINAL,
      hasLiftedOff: false,
      altitude_m: 0,
      speed_ms: 0,
      verticalSpeed_ms: 0,
      mass_kg: 100_000,
      thrust_N: 30_000,
    };

    // Thrust takes time to build, so a healthy launch briefly looks like this.
    expect(
      detectFailures({ ...stuck, burnTimeOnPad_s: 0.5 }, vehicle, DEFAULT_FAILURE_CONFIG),
    ).toEqual([]);

    const detected = detectFailures(
      { ...stuck, burnTimeOnPad_s: 3 },
      vehicle,
      DEFAULT_FAILURE_CONFIG,
    );
    expect(detected.map(f => f.id)).toContain('insufficient_thrust');
  });

  it('detects aerodynamic heating low and fast', () => {
    const detected = detectFailures(
      { ...NOMINAL, altitude_m: 30_000, speed_ms: 4_000 },
      vehicle,
      DEFAULT_FAILURE_CONFIG,
    );
    expect(detected.map(f => f.id)).toContain('thermal_problem');
  });

  it('ignores high speed once the air is thin', () => {
    const detected = detectFailures(
      { ...NOMINAL, altitude_m: 200_000, speed_ms: 7_800 },
      vehicle,
      DEFAULT_FAILURE_CONFIG,
    );
    expect(detected.map(f => f.id)).not.toContain('thermal_problem');
  });

  it('records the measurement and threshold that fired the rule', () => {
    const failure = detectFailures(
      { ...NOMINAL, gLoad_g: 20 },
      vehicle,
      DEFAULT_FAILURE_CONFIG,
    )[0]!;

    expect(failure.measuredValue).toBe(20);
    expect(failure.thresholdValue).toBe(DEFAULT_FAILURE_THRESHOLD_G);
    expect(failure.unit).toBe('g');
    expect(failure.triggerCondition).toContain('20');
  });

  it('detects nothing when detection is disabled', () => {
    const disabled: FailureConfig = { ...DEFAULT_FAILURE_CONFIG, detectionEnabled: false };
    expect(detectFailures({ ...NOMINAL, gLoad_g: 50 }, vehicle, disabled)).toEqual([]);
  });

  it('detects nothing when the whole system is off', () => {
    const off: FailureConfig = { ...DEFAULT_FAILURE_CONFIG, enabled: false };
    expect(detectFailures({ ...NOMINAL, gLoad_g: 50 }, vehicle, off)).toEqual([]);
  });

  it('honours an overridden threshold', () => {
    const strict: FailureConfig = {
      ...DEFAULT_FAILURE_CONFIG,
      thresholds: { ...DEFAULT_FAILURE_CONFIG.thresholds, maxGLoad_g: 2 },
    };
    expect(detectFailures(NOMINAL, vehicle, strict).map(f => f.id)).toContain(
      'excessive_g_load',
    );
  });
});

/** The default g-limit, referenced by the assertion above. */
const DEFAULT_FAILURE_THRESHOLD_G = DEFAULT_FAILURE_CONFIG.thresholds.maxGLoad_g;

describe('checkInjections', () => {
  const injectionInputs = {
    ...NOMINAL,
    stagesIgnitedThisStep: [] as number[],
    stagesSeparatingThisStep: [] as number[],
    maxAltitudeSoFar_m: 5_000,
  };

  it('fires a time trigger once the time is reached', () => {
    const config: FailureConfig = {
      ...DEFAULT_FAILURE_CONFIG,
      injections: [
        { id: 'x', mode: 'engine_shutdown', trigger: { type: 'time', t_s: 15 } },
      ],
    };
    const rng = new SeededRandom(1);
    const fired = new Set<string>();

    expect(
      checkInjections({ ...injectionInputs, t: 10 }, config, rng, fired),
    ).toEqual([]);
    expect(
      checkInjections({ ...injectionInputs, t: 20 }, config, rng, fired),
    ).toHaveLength(1);
  });

  it('fires each injection at most once', () => {
    const config: FailureConfig = {
      ...DEFAULT_FAILURE_CONFIG,
      injections: [
        { id: 'x', mode: 'engine_shutdown', trigger: { type: 'time', t_s: 5 } },
      ],
    };
    const rng = new SeededRandom(1);
    const fired = new Set<string>();

    expect(checkInjections(injectionInputs, config, rng, fired)).toHaveLength(1);
    expect(checkInjections(injectionInputs, config, rng, fired)).toHaveLength(0);
  });

  it('fires an altitude trigger only while climbing', () => {
    const config: FailureConfig = {
      ...DEFAULT_FAILURE_CONFIG,
      injections: [
        { id: 'x', mode: 'tank_failure', trigger: { type: 'altitude', altitude_m: 4_000 } },
      ],
    };

    // Descending past the same altitude must not arm it.
    expect(
      checkInjections(
        { ...injectionInputs, verticalSpeed_ms: -100 },
        config,
        new SeededRandom(1),
        new Set(),
      ),
    ).toEqual([]);

    expect(
      checkInjections(injectionInputs, config, new SeededRandom(1), new Set()),
    ).toHaveLength(1);
  });

  it('fires a stage-ignition trigger', () => {
    const config: FailureConfig = {
      ...DEFAULT_FAILURE_CONFIG,
      injections: [
        {
          id: 'x',
          mode: 'engine_shutdown',
          trigger: { type: 'stage_ignition', stageIndex: 1 },
        },
      ],
    };

    expect(
      checkInjections(injectionInputs, config, new SeededRandom(1), new Set()),
    ).toEqual([]);
    expect(
      checkInjections(
        { ...injectionInputs, stagesIgnitedThisStep: [1] },
        config,
        new SeededRandom(1),
        new Set(),
      ),
    ).toHaveLength(1);
  });

  it('marks an injected failure as scripted, not caused by the design', () => {
    const config: FailureConfig = {
      ...DEFAULT_FAILURE_CONFIG,
      injections: [
        { id: 'x', mode: 'engine_shutdown', trigger: { type: 'time', t_s: 5 } },
      ],
    };
    const failure = checkInjections(
      injectionInputs,
      config,
      new SeededRandom(1),
      new Set(),
    )[0]!;

    expect(failure.contributingFactors.join(' ')).toMatch(/scripted/i);
    expect(failure.triggerCondition).toMatch(/scripted/i);
  });
});

describe('failureEventType', () => {
  it('maps a known mode to its event type', () => {
    expect(
      failureEventType({ modeId: 'engine_shutdown' } as FailureDetail),
    ).toBe('failure_engine');
  });

  it('reads modeId, not the occurrence id', () => {
    // A scripted failure's `id` names the script entry; only `modeId` says what
    // kind of failure it is. Looking up the wrong one silently loses the
    // failure's effects, which is a bug this package has already had once.
    expect(
      failureEventType({
        id: 'my-scripted-fault',
        modeId: 'tank_failure',
      } as FailureDetail),
    ).toBe('failure_tank');
  });

  it('falls back to the generic type for an unknown mode', () => {
    expect(failureEventType({ modeId: 'mystery' } as FailureDetail)).toBe('failure');
  });
});

describe('injected failures in flight', () => {
  it('stops the engine when an engine shutdown is scripted', () => {
    const result = runSimulation(
      configWith([
        { id: 'shutdown', mode: 'engine_shutdown', trigger: { type: 'time', t_s: 10 } },
      ]),
    );

    expect(result.failures.map(f => f.id)).toContain('shutdown');

    // Propellant is still aboard, unburnt, because the engine stopped early.
    const finalStage = result.finalSimState.vehicle.stages[0]!;
    expect(finalStage.propellantRemaining_kg).toBeGreaterThan(0);
  });

  it('reaches a lower apogee than the same flight without the failure', () => {
    const nominal = runSimulation(configWith([]));
    const failed = runSimulation(
      configWith([
        { id: 'shutdown', mode: 'engine_shutdown', trigger: { type: 'time', t_s: 10 } },
      ]),
    );

    expect(failed.summary.maxAltitude_m).toBeLessThan(nominal.summary.maxAltitude_m);
  });

  it('records the failure in the event stream with its full detail', () => {
    const result = runSimulation(
      configWith([
        { id: 'shutdown', mode: 'engine_shutdown', trigger: { type: 'time', t_s: 10 } },
      ]),
    );

    const event = result.events.find(e => e.type === 'failure_engine')!;
    expect(event).toBeDefined();
    expect(event.failure).toBeDefined();
    expect(event.failure!.educationalExplanation).toBeTruthy();
    expect(event.severity).toBe('critical');
  });

  it('holds the last attitude when guidance fails', () => {
    const result = runSimulation(
      configWith([
        { id: 'blind', mode: 'guidance_failure', trigger: { type: 'time', t_s: 5 } },
      ]),
    );

    const afterFailure = result.telemetry.filter(p => p.t > 6);
    const pitches = new Set(afterFailure.map(p => p.pitch_rad.toFixed(9)));
    // A frozen guidance system stops updating, so every later sample matches.
    expect(pitches.size).toBe(1);
  });

  it('ends the flight when a fatal failure destroys the vehicle', () => {
    const result = runSimulation(
      configWith([
        { id: 'boom', mode: 'structural_problem', trigger: { type: 'time', t_s: 8 } },
      ]),
    );

    expect(result.outcome).toBe('failure');
    expect(result.finalState).toBe('FAILURE');
    expect(result.terminationReason).toMatch(/fatal/i);
    expect(result.flightTime_s).toBeLessThan(15);
  });

  it('leaves the flight otherwise unchanged for a comms failure', () => {
    const nominal = runSimulation(configWith([]));
    const noComms = runSimulation(
      configWith([
        { id: 'quiet', mode: 'communication_failure', trigger: { type: 'time', t_s: 5 } },
      ]),
    );

    // Losing the downlink changes what is known, not what happens.
    expect(noComms.summary.maxAltitude_m).toBeCloseTo(nominal.summary.maxAltitude_m, 3);
  });

  it('runs an entirely clean flight when the failure system is disabled', () => {
    const base = configWith([
      { id: 'shutdown', mode: 'engine_shutdown', trigger: { type: 'time', t_s: 10 } },
    ]);
    const disabled: SimConfig = {
      ...base,
      failures: { ...base.failures, enabled: false },
    };

    expect(runSimulation(disabled).failures).toEqual([]);
  });
});
