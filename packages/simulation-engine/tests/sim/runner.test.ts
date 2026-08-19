import { describe, it, expect } from 'vitest';
import { toVehicle } from '../../src/core/vehicle.js';
import { analyzeRocket } from '../../src/core/builder.js';
import { createSimConfig, type SimConfig } from '../../src/sim/config.js';
import { Simulation, runSimulation, initializeMission } from '../../src/sim/runner.js';
import {
  SUBORBITAL_PROFILE,
  ORBITAL_PROFILE,
} from '../../src/sim/mission-state.js';
import {
  VERTICAL_GUIDANCE,
  DEFAULT_GUIDANCE,
} from '../../src/sim/guidance.js';
import {
  DEFAULT_LAUNCH_SITE,
  DEFAULT_ENVIRONMENT,
  type MissionConfig,
  type MissionType,
} from '../../src/core/types.js';
import {
  stockRegistry,
  soundingRocket,
  recoverableSoundingRocket,
  orbitalLauncher,
  underpoweredRocket,
} from '../core/reference-designs.js';

const registry = stockRegistry();

function mission(name: string, altitude_km: number, type: MissionType): MissionConfig {
  return {
    name,
    objective: `Reach ${altitude_km} km`,
    target: { type, targetAltitude_km: altitude_km, inclination_deg: 28 },
    launchSite: DEFAULT_LAUNCH_SITE,
    environment: DEFAULT_ENVIRONMENT,
  };
}

/** A vertical suborbital hop with a recoverable vehicle. */
function suborbitalConfig(): SimConfig {
  return createSimConfig(
    toVehicle(recoverableSoundingRocket(registry), registry),
    mission('Hop', 30, 'suborbital'),
    { profile: SUBORBITAL_PROFILE, guidance: VERTICAL_GUIDANCE },
  );
}

/** A full ascent to low Earth orbit. */
function orbitalConfig(): SimConfig {
  return createSimConfig(
    toVehicle(orbitalLauncher(registry), registry),
    mission('LEO Insertion', 200, 'leo'),
    {
      profile: ORBITAL_PROFILE,
      guidance: DEFAULT_GUIDANCE,
      settings: { maxTime_s: 2_000 },
    },
  );
}

describe('Simulation — lifecycle', () => {
  it('starts on the pad at T minus the countdown', () => {
    const sim = initializeMission(suborbitalConfig());
    const state = sim.getState();

    expect(state.status).toBe('ready');
    expect(state.time_s).toBeCloseTo(-3, 6);
    expect(state.missionState).toBe('PREPARATION');
    expect(state.vehicle.altitude_m).toBeCloseTo(DEFAULT_LAUNCH_SITE.altitude_m, 3);
    expect(state.vehicle.speed_ms).toBe(0);
  });

  it('advances time by one timestep per step', () => {
    const sim = new Simulation(suborbitalConfig());
    const before = sim.time_s;
    sim.step();
    expect(sim.time_s).toBeGreaterThan(before);
    expect(sim.getState().stepCount).toBe(1);
  });

  it('does not advance while paused', () => {
    const sim = new Simulation(suborbitalConfig());
    sim.step();
    sim.pause();

    const time = sim.time_s;
    const steps = sim.getState().stepCount;
    sim.step();
    sim.step();

    expect(sim.time_s).toBe(time);
    expect(sim.getState().stepCount).toBe(steps);
  });

  it('resumes after a pause', () => {
    const sim = new Simulation(suborbitalConfig());
    sim.step();
    sim.pause();
    sim.resume();
    const time = sim.time_s;
    sim.step();
    expect(sim.time_s).toBeGreaterThan(time);
  });

  it('returns to the starting state on reset', () => {
    const sim = new Simulation(suborbitalConfig());
    const initial = sim.getState();

    for (let i = 0; i < 200; i++) sim.step();
    expect(sim.getState().stepCount).toBe(200);

    sim.reset();
    const afterReset = sim.getState();

    expect(afterReset.time_s).toBe(initial.time_s);
    expect(afterReset.stepCount).toBe(0);
    expect(afterReset.missionState).toBe('PREPARATION');
    expect(afterReset.status).toBe('ready');
    expect(sim.getEvents()).toEqual([]);
    expect(sim.getTelemetry()).toEqual([]);
  });

  it('produces an identical flight after a reset', () => {
    const sim = new Simulation(suborbitalConfig());
    const first = sim.run();
    sim.reset();
    const second = sim.run();

    expect(second.summary).toEqual(first.summary);
    expect(second.totalSteps).toBe(first.totalSteps);
    expect(second.events.map(e => e.type)).toEqual(first.events.map(e => e.type));
  });

  it('treats stepping a finished simulation as a no-op', () => {
    const sim = new Simulation(suborbitalConfig());
    sim.run();
    expect(sim.isFinished).toBe(true);

    const state = sim.getState();
    sim.step();
    sim.step();
    expect(sim.getState().stepCount).toBe(state.stepCount);
  });
});

describe('Simulation — the pad', () => {
  it('holds the vehicle at zero altitude through the countdown', () => {
    const sim = new Simulation(suborbitalConfig());

    while (sim.time_s < -0.1) {
      sim.step();
      // Without the ground constraint the vehicle falls through the Earth
      // before its engines ever light.
      expect(sim.getState().vehicle.altitude_m).toBeCloseTo(
        DEFAULT_LAUNCH_SITE.altitude_m,
        3,
      );
      expect(sim.getState().vehicle.speed_ms).toBeCloseTo(0, 6);
    }
  });

  it('never lets a vehicle with too little thrust leave the pad', () => {
    const config = createSimConfig(
      toVehicle(underpoweredRocket(registry), registry),
      mission('Doomed', 10, 'suborbital'),
      { profile: SUBORBITAL_PROFILE, guidance: VERTICAL_GUIDANCE },
    );
    const result = runSimulation(config);

    // maxAltitude is measured above sea level, and the pad itself is 4 m up.
    expect(result.summary.maxAltitude_m).toBeLessThan(
      DEFAULT_LAUNCH_SITE.altitude_m + 1,
    );
    expect(result.outcome).toBe('failure');
    expect(result.failures.map(f => f.id)).toContain('insufficient_thrust');
  });

  it('explains the pad abort with the numbers that caused it', () => {
    const config = createSimConfig(
      toVehicle(underpoweredRocket(registry), registry),
      mission('Doomed', 10, 'suborbital'),
      { profile: SUBORBITAL_PROFILE, guidance: VERTICAL_GUIDANCE },
    );
    const failure = runSimulation(config).failures.find(
      f => f.id === 'insufficient_thrust',
    )!;

    expect(failure.measuredValue).toBeLessThan(1);
    expect(failure.thresholdValue).toBe(1);
    expect(failure.unit).toBe('ratio');
    expect(failure.triggerState['mass_kg']).toBeGreaterThan(0);
    expect(failure.recommendedFix).toBeTruthy();
  });
});

describe('Simulation — suborbital flight', () => {
  const result = runSimulation(suborbitalConfig());

  it('completes and reaches the surface again', () => {
    expect(result.outcome).toBe('success');
    expect(result.finalState).toBe('SURFACE');
    expect(result.terminationReason).toMatch(/surface/i);
  });

  it('goes up and comes back down', () => {
    expect(result.summary.maxAltitude_m).toBeGreaterThan(100);
    expect(result.summary.apogeeTime_s).toBeGreaterThan(0);
    expect(result.summary.impactSpeed_ms).not.toBeNull();
  });

  it('emits the expected milestones in order', () => {
    const types = result.events.map(e => e.type);
    expect(types).toContain('ignition');
    expect(types).toContain('liftoff');
    expect(types).toContain('meco');
    expect(types).toContain('impact');

    // Events are recorded in time order.
    for (let i = 1; i < result.events.length; i++) {
      expect(result.events[i]!.t).toBeGreaterThanOrEqual(result.events[i - 1]!.t);
    }
  });

  it('emits each milestone exactly once', () => {
    const counts = new Map<string, number>();
    for (const event of result.events) {
      counts.set(event.type, (counts.get(event.type) ?? 0) + 1);
    }
    for (const type of ['ignition', 'liftoff', 'meco', 'impact']) {
      expect(counts.get(type), `${type} should fire once`).toBe(1);
    }
  });

  it('burns propellant monotonically down to zero', () => {
    let previous = Infinity;
    for (const point of result.telemetry) {
      expect(point.fuelRemaining_kg).toBeLessThanOrEqual(previous + 1e-6);
      previous = point.fuelRemaining_kg;
    }
    expect(previous).toBeCloseTo(0, 3);
  });

  it('loses mass only while burning', () => {
    for (let i = 1; i < result.telemetry.length; i++) {
      const before = result.telemetry[i - 1]!;
      const after = result.telemetry[i]!;
      // Both ends must be engine-off: a sample pair that straddles ignition
      // legitimately shows mass loss that neither endpoint reports.
      if (!before.engineOn && !after.engineOn) {
        expect(after.mass_kg).toBeCloseTo(before.mass_kg, 3);
      }
    }
  });

  it('produces a dynamic pressure peak part-way up, not at the ground', () => {
    expect(result.summary.maxDynamicPressure_Pa).toBeGreaterThan(0);
    expect(result.summary.maxQAltitude_m).toBeGreaterThanOrEqual(0);
  });

  it('records finite, physical telemetry throughout', () => {
    for (const point of result.telemetry) {
      expect(Number.isFinite(point.altitude_m)).toBe(true);
      expect(Number.isFinite(point.speed_ms)).toBe(true);
      expect(Number.isFinite(point.mass_kg)).toBe(true);
      expect(point.mass_kg).toBeGreaterThan(0);
      expect(point.speed_ms).toBeGreaterThanOrEqual(0);
      expect(point.airDensity_kgm3).toBeGreaterThan(0);
    }
  });
});

describe('Simulation — orbital flight', () => {
  const result = runSimulation(orbitalConfig());

  it('reaches a stable orbit and completes the mission', () => {
    expect(result.outcome).toBe('success');
    expect(result.finalState).toBe('COMPLETE');
  });

  it('walks the full mission state machine', () => {
    const types = result.events.map(e => e.type);
    expect(types).toContain('ignition');
    expect(types).toContain('liftoff');
    expect(types).toContain('supersonic');
    expect(types).toContain('max_q');
    expect(types).toContain('meco');
    expect(types).toContain('staging');
    expect(types).toContain('orbit_insertion');
    expect(types).toContain('payload_deployment');
    expect(types).toContain('mission_complete');
  });

  it('separates its first stage exactly once', () => {
    expect(result.summary.stagesSeparated).toBe(1);
    expect(result.events.filter(e => e.type === 'staging')).toHaveLength(1);
  });

  it('ends in a closed orbit clear of the surface', () => {
    const orbit = result.finalSimState.orbit;
    expect(orbit).not.toBeNull();
    expect(orbit!.isStableOrbit).toBe(true);
    expect(orbit!.periapsisAltitude_m).toBeGreaterThan(100_000);
    expect(orbit!.eccentricity).toBeLessThan(1);
  });

  it('reaches roughly orbital velocity', () => {
    // Circular orbit at these altitudes needs ~7.8 km/s; an ascent that also
    // climbs and fights drag peaks somewhat higher.
    expect(result.summary.maxSpeed_ms).toBeGreaterThan(7_000);
    expect(result.summary.maxSpeed_ms).toBeLessThan(12_000);
  });

  it('pays a gravity loss in the range real launch vehicles do', () => {
    // Real ascents lose roughly 1.2–1.8 km/s to gravity.
    expect(result.summary.gravityLoss_ms).toBeGreaterThan(800);
    expect(result.summary.gravityLoss_ms).toBeLessThan(2_500);
  });

  it('pays a much smaller drag loss than gravity loss', () => {
    // Drag costs a launch vehicle well under 200 m/s; gravity dominates.
    expect(result.summary.dragLoss_ms).toBeLessThan(result.summary.gravityLoss_ms);
    expect(result.summary.dragLoss_ms).toBeLessThan(300);
  });

  it('peaks its dynamic pressure in the lower atmosphere', () => {
    // Max-Q happens where rising speed and falling density cross, typically
    // 10–15 km up.
    expect(result.summary.maxQAltitude_m).toBeGreaterThan(5_000);
    expect(result.summary.maxQAltitude_m).toBeLessThan(25_000);
  });

  it('shuts down early when the target orbit is reachable', () => {
    // Guidance cuts off once periapsis clears the target altitude, so a vehicle
    // with margin keeps its leftover propellant rather than burning dry.
    const reachable = createSimConfig(
      toVehicle(orbitalLauncher(registry), registry),
      mission('Low LEO', 140, 'leo'),
      {
        profile: ORBITAL_PROFILE,
        guidance: DEFAULT_GUIDANCE,
        settings: { maxTime_s: 2_000 },
      },
    );
    const early = runSimulation(reachable);
    const finalStage = early.finalSimState.vehicle.stages.at(-1)!;

    expect(finalStage.propellantRemaining_kg).toBeGreaterThan(0);
    expect(early.finalSimState.orbit!.periapsisAltitude_m).toBeGreaterThanOrEqual(140_000);
  });

  it('burns to depletion when the target orbit is out of reach', () => {
    // This vehicle cannot raise periapsis to 200 km, so nothing commands a
    // cutoff and it uses everything it has. It still reaches a stable orbit,
    // just a more eccentric one than the mission asked for.
    const finalStage = result.finalSimState.vehicle.stages.at(-1)!;
    expect(finalStage.propellantRemaining_kg).toBeCloseTo(0, 3);
    expect(result.finalSimState.orbit!.isStableOrbit).toBe(true);
  });

  it('never exceeds a survivable load factor', () => {
    expect(result.summary.maxAcceleration_g).toBeLessThan(15);
  });
});

describe('Simulation — telemetry sampling', () => {
  it('samples at roughly the configured interval', () => {
    const config = createSimConfig(
      toVehicle(recoverableSoundingRocket(registry), registry),
      mission('Hop', 30, 'suborbital'),
      {
        profile: SUBORBITAL_PROFILE,
        guidance: VERTICAL_GUIDANCE,
        settings: { telemetrySampleInterval_s: 2 },
      },
    );
    const result = runSimulation(config);

    // One sample every 2 s over the flight, plus a few forced by events.
    const expected = result.flightTime_s / 2;
    expect(result.telemetry.length).toBeGreaterThan(expected * 0.8);
    expect(result.telemetry.length).toBeLessThan(expected + 20);
  });

  it('records a sample at every event, whatever the interval', () => {
    const config = createSimConfig(
      toVehicle(recoverableSoundingRocket(registry), registry),
      mission('Hop', 30, 'suborbital'),
      {
        profile: SUBORBITAL_PROFILE,
        guidance: VERTICAL_GUIDANCE,
        settings: { telemetrySampleInterval_s: 30 },
      },
    );
    const result = runSimulation(config);

    for (const event of result.events) {
      const matching = result.telemetry.some(p => Math.abs(p.t - event.t) < 1e-9);
      expect(matching, `no telemetry sample at ${event.type} (t=${event.t})`).toBe(true);
    }
  });

  it('keeps telemetry in time order', () => {
    const result = runSimulation(suborbitalConfig());
    for (let i = 1; i < result.telemetry.length; i++) {
      expect(result.telemetry[i]!.t).toBeGreaterThan(result.telemetry[i - 1]!.t);
    }
  });
});

describe('Simulation — termination', () => {
  it('stops at the time limit', () => {
    const config = createSimConfig(
      toVehicle(soundingRocket(registry), registry),
      mission('Long', 100, 'suborbital'),
      {
        profile: SUBORBITAL_PROFILE,
        guidance: VERTICAL_GUIDANCE,
        settings: { maxTime_s: 20 },
        termination: { onImpact: false, onFatalFailure: false },
      },
    );
    const result = runSimulation(config);

    expect(result.flightTime_s).toBeLessThanOrEqual(20.5);
    expect(result.terminationReason).toMatch(/time limit/i);
  });

  it('stops on reaching the target altitude when configured to', () => {
    const config = createSimConfig(
      toVehicle(soundingRocket(registry), registry),
      mission('Ceiling', 10, 'suborbital'),
      {
        profile: SUBORBITAL_PROFILE,
        guidance: VERTICAL_GUIDANCE,
        termination: { onTargetAltitude: true },
      },
    );
    const result = runSimulation(config);

    expect(result.summary.maxAltitude_m).toBeGreaterThanOrEqual(10_000);
    expect(result.events.map(e => e.type)).toContain('target_reached');
  });

  it('respects the step limit rather than running forever', () => {
    const config = createSimConfig(
      toVehicle(soundingRocket(registry), registry),
      mission('Capped', 100, 'suborbital'),
      {
        profile: SUBORBITAL_PROFILE,
        guidance: VERTICAL_GUIDANCE,
        settings: { maxSteps: 50 },
      },
    );
    const result = runSimulation(config);
    expect(result.totalSteps).toBeLessThanOrEqual(50);
  });
});

describe('Simulation — analysis consistency', () => {
  it('reports an ideal delta-v close to the pre-flight analysis', () => {
    const design = recoverableSoundingRocket(registry);
    const analysis = analyzeRocket(design, registry);
    const result = runSimulation(suborbitalConfig());

    // The runner's figure counts only propellant actually burnt; for a stage
    // that burns to depletion the two should be within a fraction of a percent.
    expect(result.summary.deltaVIdeal_ms).toBeGreaterThan(analysis.totalDeltaV_ms * 0.95);
    expect(result.summary.deltaVIdeal_ms).toBeLessThan(analysis.totalDeltaV_ms * 1.05);
  });

  it('starts at exactly the analysed launch mass', () => {
    const analysis = analyzeRocket(recoverableSoundingRocket(registry), registry);
    const sim = new Simulation(suborbitalConfig());
    expect(sim.getState().vehicle.mass_kg).toBeCloseTo(analysis.totalWetMass_kg, 6);
  });

  it('never achieves more speed than its ideal delta-v allows', () => {
    const result = runSimulation(orbitalConfig());
    expect(result.summary.maxSpeed_ms).toBeLessThan(result.summary.deltaVIdeal_ms);
  });
});
