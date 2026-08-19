/**
 * Performance tests.
 *
 * Two budgets matter, and they are different problems:
 *
 * 1. **Throughput** — a full mission must complete fast enough to run in a
 *    Web Worker without the user waiting. A few hundred milliseconds is fine.
 * 2. **Per-step cost** — the interactive path steps the simulation inside
 *    `requestAnimationFrame`, so a step has to fit comfortably inside a 16 ms
 *    frame budget alongside the render.
 *
 * The thresholds are deliberately loose. These tests exist to catch a
 * regression that makes the engine an order of magnitude slower, not to police
 * small variations on shared CI hardware.
 */

import { describe, it, expect } from 'vitest';
import { toVehicle } from '../../src/core/vehicle.js';
import { analyzeRocket } from '../../src/core/builder.js';
import { createSimConfig } from '../../src/sim/config.js';
import { Simulation, runSimulation } from '../../src/sim/runner.js';
import { SUBORBITAL_PROFILE, ORBITAL_PROFILE } from '../../src/sim/mission-state.js';
import { VERTICAL_GUIDANCE, DEFAULT_GUIDANCE } from '../../src/sim/guidance.js';
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

const registry = stockRegistry();

const mission: MissionConfig = {
  name: 'Performance',
  objective: 'Measure',
  target: { type: 'leo', targetAltitude_km: 200, inclination_deg: 28 },
  launchSite: DEFAULT_LAUNCH_SITE,
  environment: DEFAULT_ENVIRONMENT,
};

describe('simulation throughput', () => {
  it('runs a full orbital ascent in well under a second', () => {
    const config = createSimConfig(
      toVehicle(orbitalLauncher(registry), registry),
      mission,
      {
        profile: ORBITAL_PROFILE,
        guidance: DEFAULT_GUIDANCE,
        settings: { maxTime_s: 2_000 },
      },
    );

    const start = performance.now();
    const result = runSimulation(config);
    const elapsed = performance.now() - start;

    expect(result.totalSteps).toBeGreaterThan(5_000);
    expect(elapsed, `${result.totalSteps} steps took ${elapsed.toFixed(0)} ms`)
      .toBeLessThan(2_000);
  });

  it('sustains at least 20 000 integration steps per second', () => {
    const config = createSimConfig(
      toVehicle(orbitalLauncher(registry), registry),
      mission,
      {
        profile: ORBITAL_PROFILE,
        guidance: DEFAULT_GUIDANCE,
        settings: { maxTime_s: 2_000 },
      },
    );

    const start = performance.now();
    const result = runSimulation(config);
    const elapsed_s = (performance.now() - start) / 1000;
    const stepsPerSecond = result.totalSteps / elapsed_s;

    expect(stepsPerSecond, `${Math.round(stepsPerSecond)} steps/s`).toBeGreaterThan(20_000);
  });

  it('runs a suborbital flight fast enough to feel instant', () => {
    const config = createSimConfig(
      toVehicle(recoverableSoundingRocket(registry), registry),
      { ...mission, target: { type: 'suborbital', targetAltitude_km: 30 } },
      { profile: SUBORBITAL_PROFILE, guidance: VERTICAL_GUIDANCE },
    );

    const start = performance.now();
    runSimulation(config);
    expect(performance.now() - start).toBeLessThan(500);
  });
});

describe('per-step cost', () => {
  it('keeps a single step far inside a frame budget', () => {
    const config = createSimConfig(
      toVehicle(orbitalLauncher(registry), registry),
      mission,
      { profile: ORBITAL_PROFILE, guidance: DEFAULT_GUIDANCE },
    );
    const sim = new Simulation(config);

    // Warm up past the countdown and into powered flight.
    for (let i = 0; i < 500; i++) sim.step();

    const samples = 2_000;
    const start = performance.now();
    for (let i = 0; i < samples; i++) sim.step();
    const perStep_ms = (performance.now() - start) / samples;

    // A 16 ms frame has to fit a step plus a render; 0.5 ms leaves ample room
    // to run several steps per frame at high time scales.
    expect(perStep_ms, `${perStep_ms.toFixed(4)} ms/step`).toBeLessThan(0.5);
  });

  it('reads state cheaply enough to call every frame', () => {
    const config = createSimConfig(
      toVehicle(orbitalLauncher(registry), registry),
      mission,
      { profile: ORBITAL_PROFILE, guidance: DEFAULT_GUIDANCE },
    );
    const sim = new Simulation(config);
    for (let i = 0; i < 1_000; i++) sim.step();

    // The renderer calls getState() once per frame, so it must not be
    // proportional to how long the flight has been running.
    const samples = 5_000;
    const start = performance.now();
    for (let i = 0; i < samples; i++) sim.getState();
    const perCall_ms = (performance.now() - start) / samples;

    expect(perCall_ms, `${perCall_ms.toFixed(5)} ms/call`).toBeLessThan(0.1);
  });
});

describe('builder responsiveness', () => {
  it('analyses a design fast enough to run on every keystroke', () => {
    const design = orbitalLauncher(registry);

    const samples = 500;
    const start = performance.now();
    for (let i = 0; i < samples; i++) analyzeRocket(design, registry);
    const perCall_ms = (performance.now() - start) / samples;

    // The builder recomputes this whenever the design changes, so it has to be
    // cheap enough that dragging a component stays smooth.
    expect(perCall_ms, `${perCall_ms.toFixed(4)} ms/call`).toBeLessThan(2);
  });

  it('converts a design to a vehicle cheaply', () => {
    const design = orbitalLauncher(registry);

    const samples = 500;
    const start = performance.now();
    for (let i = 0; i < samples; i++) toVehicle(design, registry);
    const perCall_ms = (performance.now() - start) / samples;

    expect(perCall_ms, `${perCall_ms.toFixed(4)} ms/call`).toBeLessThan(2);
  });
});

describe('memory behaviour', () => {
  it('keeps telemetry proportional to the sampling rate, not the step count', () => {
    const config = createSimConfig(
      toVehicle(orbitalLauncher(registry), registry),
      mission,
      {
        profile: ORBITAL_PROFILE,
        guidance: DEFAULT_GUIDANCE,
        settings: { maxTime_s: 2_000, telemetrySampleInterval_s: 1 },
      },
    );
    const result = runSimulation(config);

    // Tens of thousands of steps must not become tens of thousands of rows.
    expect(result.totalSteps).toBeGreaterThan(5_000);
    expect(result.telemetry.length).toBeLessThan(result.totalSteps / 5);
  });

  it('does not grow the event list without bound', () => {
    const config = createSimConfig(
      toVehicle(orbitalLauncher(registry), registry),
      mission,
      {
        profile: ORBITAL_PROFILE,
        guidance: DEFAULT_GUIDANCE,
        settings: { maxTime_s: 2_000 },
      },
    );
    const result = runSimulation(config);

    // A mission has a handful of milestones. Hundreds would mean a state
    // machine re-firing, which is a bug this package has already had once.
    expect(result.events.length).toBeLessThan(40);
  });
});
