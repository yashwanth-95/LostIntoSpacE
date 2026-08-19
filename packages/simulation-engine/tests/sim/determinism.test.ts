/**
 * Determinism tests.
 *
 * The engine's central promise is that a `SimConfig` fully determines a flight.
 * Everything else depends on it: P2 can store a config instead of a result, P4
 * can re-derive a flight to explain it, a lesson can guarantee every student
 * sees the same failure, and these tests can assert on exact numbers rather
 * than ranges.
 *
 * A single stray `Math.random()` or `Date.now()` would break it silently — the
 * flights would still look plausible, they would just stop matching. So it is
 * checked directly, at the level of complete telemetry equality.
 */

import { describe, it, expect } from 'vitest';
import { toVehicle } from '../../src/core/vehicle.js';
import { createSimConfig, type SimConfig } from '../../src/sim/config.js';
import { Simulation, runSimulation } from '../../src/sim/runner.js';
import { SUBORBITAL_PROFILE, ORBITAL_PROFILE } from '../../src/sim/mission-state.js';
import { VERTICAL_GUIDANCE, DEFAULT_GUIDANCE } from '../../src/sim/guidance.js';
import { SeededRandom } from '../../src/sim/failures.js';
import {
  DEFAULT_LAUNCH_SITE,
  DEFAULT_ENVIRONMENT,
  type MissionConfig,
} from '../../src/core/types.js';
import {
  stockRegistry,
  recoverableSoundingRocket,
  orbitalLauncher,
} from '../core/reference-designs.js';

const mission: MissionConfig = {
  name: 'Determinism Check',
  objective: 'Fly the same flight twice',
  target: { type: 'suborbital', targetAltitude_km: 30, inclination_deg: 28 },
  launchSite: DEFAULT_LAUNCH_SITE,
  environment: DEFAULT_ENVIRONMENT,
};

/** Build a config from scratch, sharing nothing with any other build. */
function freshSuborbital(seed = 1): SimConfig {
  const registry = stockRegistry();
  return createSimConfig(
    toVehicle(recoverableSoundingRocket(registry), registry),
    mission,
    {
      profile: SUBORBITAL_PROFILE,
      guidance: VERTICAL_GUIDANCE,
      failures: { seed },
    },
  );
}

/** Build an orbital config from scratch. */
function freshOrbital(): SimConfig {
  const registry = stockRegistry();
  return createSimConfig(
    toVehicle(orbitalLauncher(registry), registry),
    {
      ...mission,
      target: { type: 'leo', targetAltitude_km: 200, inclination_deg: 28 },
    },
    {
      profile: ORBITAL_PROFILE,
      guidance: DEFAULT_GUIDANCE,
      settings: { maxTime_s: 2_000 },
    },
  );
}

describe('SeededRandom', () => {
  it('produces the same sequence for the same seed', () => {
    const a = new SeededRandom(12345);
    const b = new SeededRandom(12345);
    for (let i = 0; i < 500; i++) {
      expect(a.next()).toBe(b.next());
    }
  });

  it('produces different sequences for different seeds', () => {
    const a = new SeededRandom(1);
    const b = new SeededRandom(2);
    const first = Array.from({ length: 20 }, () => a.next());
    const second = Array.from({ length: 20 }, () => b.next());
    expect(first).not.toEqual(second);
  });

  it('stays inside [0, 1)', () => {
    const rng = new SeededRandom(99);
    for (let i = 0; i < 10_000; i++) {
      const value = rng.next();
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(1);
    }
  });

  it('is roughly uniform', () => {
    const rng = new SeededRandom(7);
    const buckets = new Array<number>(10).fill(0);
    const samples = 100_000;
    for (let i = 0; i < samples; i++) {
      buckets[Math.floor(rng.next() * 10)]!++;
    }
    // Each bucket should hold about a tenth; allow generous slack.
    for (const count of buckets) {
      expect(count).toBeGreaterThan(samples * 0.08);
      expect(count).toBeLessThan(samples * 0.12);
    }
  });

  it('makes hazard rates timestep-independent', () => {
    // A 0.1/s hazard over 10 s should fire about 63 % of the time whether it is
    // evaluated in one 10 s call or a hundred 0.1 s calls.
    const trials = 4_000;

    const count = (dt: number, steps: number): number => {
      let fired = 0;
      for (let trial = 0; trial < trials; trial++) {
        const rng = new SeededRandom(trial);
        for (let step = 0; step < steps; step++) {
          if (rng.occursIn(0.1, dt)) {
            fired++;
            break;
          }
        }
      }
      return fired / trials;
    };

    const coarse = count(10, 1);
    const fine = count(0.1, 100);
    expect(fine).toBeCloseTo(coarse, 1);
    expect(coarse).toBeCloseTo(1 - Math.exp(-1), 1);
  });

  it('never fires for a zero or negative rate', () => {
    const rng = new SeededRandom(3);
    for (let i = 0; i < 100; i++) {
      expect(rng.occursIn(0, 1)).toBe(false);
      expect(rng.occursIn(-1, 1)).toBe(false);
      expect(rng.occursIn(1, 0)).toBe(false);
    }
  });
});

describe('flight determinism — suborbital', () => {
  it('produces byte-identical telemetry across independent runs', () => {
    const first = runSimulation(freshSuborbital());
    const second = runSimulation(freshSuborbital());

    expect(second.telemetry).toEqual(first.telemetry);
  });

  it('produces identical events', () => {
    const first = runSimulation(freshSuborbital());
    const second = runSimulation(freshSuborbital());

    expect(second.events).toEqual(first.events);
  });

  it('produces an identical summary and step count', () => {
    const first = runSimulation(freshSuborbital());
    const second = runSimulation(freshSuborbital());

    expect(second.summary).toEqual(first.summary);
    expect(second.totalSteps).toBe(first.totalSteps);
    expect(second.flightTime_s).toBe(first.flightTime_s);
    expect(second.outcome).toBe(first.outcome);
  });

  it('gives the same answer whether stepped or run in one go', () => {
    const batched = runSimulation(freshSuborbital());

    const stepped = new Simulation(freshSuborbital());
    while (!stepped.isFinished) stepped.step();
    const steppedResult = stepped.getResult();

    expect(steppedResult.telemetry).toEqual(batched.telemetry);
    expect(steppedResult.summary).toEqual(batched.summary);
  });

  it('is unaffected by pausing and resuming', () => {
    const straight = runSimulation(freshSuborbital());

    const interrupted = new Simulation(freshSuborbital());
    let steps = 0;
    while (!interrupted.isFinished) {
      interrupted.step();
      if (++steps % 37 === 0) {
        interrupted.pause();
        interrupted.resume();
      }
    }

    expect(interrupted.getResult().telemetry).toEqual(straight.telemetry);
  });
});

describe('flight determinism — orbital', () => {
  it('produces identical telemetry for a long multi-stage ascent', () => {
    const first = runSimulation(freshOrbital());
    const second = runSimulation(freshOrbital());

    expect(second.totalSteps).toBe(first.totalSteps);
    expect(second.telemetry).toEqual(first.telemetry);
    expect(second.events).toEqual(first.events);
  });

  it('reaches an identical final orbit', () => {
    const first = runSimulation(freshOrbital()).finalSimState.orbit!;
    const second = runSimulation(freshOrbital()).finalSimState.orbit!;

    expect(second.semiMajorAxis_m).toBe(first.semiMajorAxis_m);
    expect(second.eccentricity).toBe(first.eccentricity);
    expect(second.inclination_rad).toBe(first.inclination_rad);
  });
});

describe('seed sensitivity', () => {
  it('gives the same flight for the same seed when failures are injected', () => {
    const withInjection = (seed: number): SimConfig => {
      const base = freshSuborbital(seed);
      return {
        ...base,
        failures: {
          ...base.failures,
          seed,
          injections: [
            {
              id: 'random-engine-fault',
              mode: 'engine_shutdown',
              trigger: { type: 'probability', perSecond: 0.05 },
            },
          ],
        },
      };
    };

    const a = runSimulation(withInjection(42));
    const b = runSimulation(withInjection(42));
    expect(b.events).toEqual(a.events);
    expect(b.failures).toEqual(a.failures);
  });

  it('gives different flights for different seeds under probabilistic injection', () => {
    const withInjection = (seed: number): SimConfig => {
      const base = freshSuborbital(seed);
      return {
        ...base,
        failures: {
          ...base.failures,
          seed,
          injections: [
            {
              id: 'random-engine-fault',
              mode: 'engine_shutdown',
              trigger: { type: 'probability', perSecond: 0.05 },
            },
          ],
        },
      };
    };

    // Across a spread of seeds the failure time must vary; a single fixed
    // outcome would mean the seed is not reaching the generator.
    const failureTimes = new Set<number>();
    for (let seed = 1; seed <= 12; seed++) {
      const failure = runSimulation(withInjection(seed)).failures[0];
      failureTimes.add(failure ? Math.round(failure.t * 100) : -1);
    }
    expect(failureTimes.size).toBeGreaterThan(1);
  });

  it('leaves a flight with no probabilistic injections seed-independent', () => {
    const a = runSimulation(freshSuborbital(1));
    const b = runSimulation(freshSuborbital(999));
    expect(b.telemetry).toEqual(a.telemetry);
  });
});
