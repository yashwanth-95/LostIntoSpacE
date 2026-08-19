import { describe, it, expect } from 'vitest';
import {
  TelemetrySampler,
  buildTelemetryPoint,
  decimateTelemetry,
  EMPTY_TELEMETRY,
  type TelemetryPoint,
} from '../../src/sim/telemetry.js';
import {
  computeGuidance,
  scheduledPitch,
  angleOfAttack,
  localUpVector,
  initialCommand,
  DEFAULT_GUIDANCE,
  VERTICAL_GUIDANCE,
  GRAVITY_TURN_GUIDANCE,
  type GuidanceConfig,
} from '../../src/sim/guidance.js';
import { vec3, magnitude } from '../../src/physics/vec3.js';
import { G0, R_EARTH, DEG_TO_RAD } from '../../src/physics/constants.js';

// ============================================================
// Telemetry
// ============================================================

/** A telemetry sample at a given time, with everything else nominal. */
function sample(t: number, overrides: Partial<TelemetryPoint> = {}): TelemetryPoint {
  return { ...EMPTY_TELEMETRY, t, ...overrides };
}

describe('buildTelemetryPoint', () => {
  const base = {
    t: 10,
    position: vec3(100, 200, 5_000),
    velocity: vec3(30, 40, 300),
    acceleration: vec3(0, 0, 20),
    altitude_m: 5_000,
    downrange_m: 224,
    verticalSpeed_ms: 300,
    mass_kg: 1_000,
    fuelRemaining_kg: 400,
    fuelFraction: 0.5,
    thrust_N: 30_000,
    massFlow_kgs: 12,
    drag_N: -500,
    dynamicPressure_Pa: 20_000,
    mach: 0.9,
    airDensity_kgm3: 0.7,
    ambientPressure_Pa: 54_000,
    localGravity_ms2: 9.79,
    pitch_rad: Math.PI / 2,
    yaw_rad: 0,
    angleOfAttack_rad: 0,
    orbit: null,
    stage: 0,
    stageStatus: 'burning' as const,
    engineOn: true,
    missionState: 'ASCENT' as const,
    phase: 'powered' as const,
  };

  it('computes speed from the velocity vector', () => {
    expect(buildTelemetryPoint(base).speed_ms).toBeCloseTo(magnitude(base.velocity), 9);
  });

  it('splits speed into vertical and horizontal components consistently', () => {
    const point = buildTelemetryPoint(base);
    expect(
      Math.hypot(point.verticalSpeed_ms, point.horizontalSpeed_ms),
    ).toBeCloseTo(point.speed_ms, 6);
  });

  it('reports load factor from non-gravitational forces only', () => {
    // An accelerometer reads thrust and drag, not gravity: a vehicle in free
    // fall reads zero even though it is accelerating at 9.8 m/s².
    const point = buildTelemetryPoint(base);
    expect(point.gLoad_g).toBeCloseTo((30_000 - 500) / 1_000 / G0, 6);
  });

  it('reports zero load factor in free fall', () => {
    const point = buildTelemetryPoint({ ...base, thrust_N: 0, drag_N: 0 });
    expect(point.gLoad_g).toBe(0);
  });

  it('computes thrust-to-weight against local gravity', () => {
    const point = buildTelemetryPoint(base);
    expect(point.twr).toBeCloseTo(30_000 / (1_000 * 9.79), 6);
  });

  it('reports zero orbital values when there is no orbit', () => {
    const point = buildTelemetryPoint(base);
    expect(point.semiMajorAxis_m).toBe(0);
    expect(point.eccentricity).toBe(0);
    expect(point.inOrbit).toBe(false);
  });

  it('never produces NaN for a zero-mass edge case', () => {
    const point = buildTelemetryPoint({ ...base, mass_kg: 0 });
    expect(Number.isFinite(point.gLoad_g)).toBe(true);
    expect(Number.isFinite(point.twr)).toBe(true);
  });

  it('is a flat record of primitives, for direct storage and charting', () => {
    const point = buildTelemetryPoint(base);
    for (const [key, value] of Object.entries(point)) {
      expect(
        ['number', 'string', 'boolean'].includes(typeof value),
        `${key} is ${typeof value}`,
      ).toBe(true);
    }
  });
});

describe('TelemetrySampler', () => {
  it('rejects a non-positive interval', () => {
    expect(() => new TelemetrySampler(0)).toThrow(RangeError);
    expect(() => new TelemetrySampler(-1)).toThrow(RangeError);
  });

  it('emits on the interval grid', () => {
    const sampler = new TelemetrySampler(1, 0);

    expect(sampler.offer(sample(0))).toBe(true);
    expect(sampler.offer(sample(0.5))).toBe(false);
    expect(sampler.offer(sample(1.0))).toBe(true);
    expect(sampler.offer(sample(1.5))).toBe(false);
    expect(sampler.offer(sample(2.0))).toBe(true);

    expect(sampler.points.map(p => p.t)).toEqual([0, 1, 2]);
  });

  it('emits off-grid when forced by an event', () => {
    const sampler = new TelemetrySampler(10, 0);
    sampler.offer(sample(0));
    expect(sampler.offer(sample(3.7), true)).toBe(true);
    expect(sampler.points.map(p => p.t)).toEqual([0, 3.7]);
  });

  it('does not shift the grid after a forced emit', () => {
    const sampler = new TelemetrySampler(1, 0);
    sampler.offer(sample(0));
    sampler.offer(sample(0.3), true);
    // The next routine sample must still land on 1, not on 1.3.
    expect(sampler.offer(sample(0.9))).toBe(false);
    expect(sampler.offer(sample(1.0))).toBe(true);
  });

  it('catches up after a long gap without emitting a burst', () => {
    const sampler = new TelemetrySampler(1, 0);
    sampler.offer(sample(0));
    sampler.offer(sample(50));
    // One sample per offer, however far time jumped.
    expect(sampler.length).toBe(2);
    expect(sampler.offer(sample(50.5))).toBe(false);
    expect(sampler.offer(sample(51))).toBe(true);
  });

  it('exposes the latest sample', () => {
    const sampler = new TelemetrySampler(1, 0);
    expect(sampler.latest).toBeUndefined();
    sampler.offer(sample(0));
    sampler.offer(sample(1, { altitude_m: 500 }));
    expect(sampler.latest!.altitude_m).toBe(500);
  });

  it('clears on reset', () => {
    const sampler = new TelemetrySampler(1, 0);
    sampler.offer(sample(0));
    sampler.offer(sample(1));
    sampler.reset(0);

    expect(sampler.length).toBe(0);
    expect(sampler.offer(sample(0))).toBe(true);
  });
});

describe('decimateTelemetry', () => {
  /** A synthetic ascent with a clear apogee and a clear speed peak. */
  const series: TelemetryPoint[] = Array.from({ length: 1_000 }, (_, i) =>
    sample(i, {
      altitude_m: Math.sin((i / 1_000) * Math.PI) * 100_000,
      speed_ms: i < 400 ? i * 5 : 2_000 - (i - 400) * 2,
    }),
  );

  it('returns the series unchanged when it already fits', () => {
    const short = series.slice(0, 10);
    expect(decimateTelemetry(short, 100)).toEqual(short);
  });

  it('reduces a long series', () => {
    expect(decimateTelemetry(series, 100).length).toBeLessThanOrEqual(100);
  });

  it('keeps the apogee', () => {
    const peak = Math.max(...series.map(p => p.altitude_m));
    const reduced = decimateTelemetry(series, 100);
    expect(Math.max(...reduced.map(p => p.altitude_m))).toBe(peak);
  });

  it('keeps the speed peak', () => {
    const peak = Math.max(...series.map(p => p.speed_ms));
    const reduced = decimateTelemetry(series, 100);
    expect(Math.max(...reduced.map(p => p.speed_ms))).toBe(peak);
  });

  it('keeps the first and last samples', () => {
    const reduced = decimateTelemetry(series, 100);
    expect(reduced[0]!.t).toBe(series[0]!.t);
    expect(reduced.at(-1)!.t).toBe(series.at(-1)!.t);
  });

  it('stays in time order with no duplicates', () => {
    const reduced = decimateTelemetry(series, 100);
    for (let i = 1; i < reduced.length; i++) {
      expect(reduced[i]!.t).toBeGreaterThan(reduced[i - 1]!.t);
    }
  });
});

// ============================================================
// Guidance
// ============================================================

describe('scheduledPitch', () => {
  it('holds vertical below the pitchover altitude', () => {
    expect(scheduledPitch(0, DEFAULT_GUIDANCE)).toBeCloseTo(Math.PI / 2, 9);
    expect(scheduledPitch(DEFAULT_GUIDANCE.pitchoverAltitude_m, DEFAULT_GUIDANCE))
      .toBeCloseTo(Math.PI / 2, 9);
  });

  it('reaches the final pitch by the end of the program', () => {
    expect(
      scheduledPitch(DEFAULT_GUIDANCE.pitchProgramEndAltitude_m, DEFAULT_GUIDANCE),
    ).toBeCloseTo(DEFAULT_GUIDANCE.finalPitch_deg * DEG_TO_RAD, 9);
  });

  it('holds the final pitch above the program', () => {
    expect(scheduledPitch(500_000, DEFAULT_GUIDANCE)).toBeCloseTo(
      DEFAULT_GUIDANCE.finalPitch_deg * DEG_TO_RAD,
      9,
    );
  });

  it('decreases monotonically with altitude', () => {
    let previous = Infinity;
    for (let altitude = 0; altitude <= 100_000; altitude += 1_000) {
      const pitch = scheduledPitch(altitude, DEFAULT_GUIDANCE);
      expect(pitch).toBeLessThanOrEqual(previous + 1e-12);
      previous = pitch;
    }
  });

  it('handles a degenerate program span without dividing by zero', () => {
    const degenerate: GuidanceConfig = {
      ...DEFAULT_GUIDANCE,
      pitchoverAltitude_m: 10_000,
      pitchProgramEndAltitude_m: 10_000,
    };
    expect(Number.isFinite(scheduledPitch(20_000, degenerate))).toBe(true);
  });
});

describe('computeGuidance', () => {
  const inputs = {
    altitude_m: 10_000,
    velocity: vec3(0, 0, 500),
    localUp: vec3(0, 0, 1),
    guidanceFailed: false,
    lastCommand: null,
  };

  it('flies straight up in vertical mode, at any altitude', () => {
    for (const altitude_m of [0, 10_000, 200_000]) {
      const command = computeGuidance({ ...inputs, altitude_m }, VERTICAL_GUIDANCE);
      expect(command.pitch_rad).toBeCloseTo(Math.PI / 2, 9);
      expect(command.thrustDirection.z).toBeCloseTo(1, 9);
    }
  });

  it('always returns a unit thrust direction', () => {
    for (const config of [VERTICAL_GUIDANCE, DEFAULT_GUIDANCE, GRAVITY_TURN_GUIDANCE]) {
      for (const altitude_m of [0, 500, 5_000, 50_000, 200_000]) {
        const command = computeGuidance(
          { ...inputs, altitude_m, velocity: vec3(100, 0, 400) },
          config,
        );
        expect(magnitude(command.thrustDirection)).toBeCloseTo(1, 9);
      }
    }
  });

  it('pitches over as the vehicle climbs in pitch-program mode', () => {
    const low = computeGuidance({ ...inputs, altitude_m: 100 }, DEFAULT_GUIDANCE);
    const high = computeGuidance({ ...inputs, altitude_m: 60_000 }, DEFAULT_GUIDANCE);
    expect(high.pitch_rad).toBeLessThan(low.pitch_rad);
  });

  it('points along the launch azimuth', () => {
    // Due east: the horizontal component should be entirely +X.
    const east = computeGuidance(
      { ...inputs, altitude_m: 80_000 },
      { ...DEFAULT_GUIDANCE, launchAzimuth_deg: 90, finalPitch_deg: 0 },
    );
    expect(east.thrustDirection.x).toBeCloseTo(1, 6);
    expect(east.thrustDirection.y).toBeCloseTo(0, 6);
  });

  it('holds vertical in gravity-turn mode before the pitchover', () => {
    const command = computeGuidance(
      { ...inputs, altitude_m: 100 },
      GRAVITY_TURN_GUIDANCE,
    );
    expect(command.pitch_rad).toBeCloseTo(Math.PI / 2, 9);
  });

  it('ramps the gravity-turn kick in rather than stepping it', () => {
    const config = GRAVITY_TURN_GUIDANCE;
    const justAfter = computeGuidance(
      { ...inputs, altitude_m: config.pitchoverAltitude_m + 1 },
      config,
    );
    const wellInto = computeGuidance(
      { ...inputs, altitude_m: config.pitchoverAltitude_m * 3 },
      config,
    );

    expect(justAfter.pitch_rad).toBeLessThan(Math.PI / 2);
    expect(wellInto.pitch_rad).toBeLessThan(justAfter.pitch_rad);
  });

  it('follows the velocity vector once the gravity turn is established', () => {
    const config = GRAVITY_TURN_GUIDANCE;
    const velocity = vec3(300, 0, 400);
    const command = computeGuidance(
      {
        ...inputs,
        altitude_m: config.pitchoverAltitude_m * 10,
        velocity,
      },
      config,
    );

    // Thrust parallel to velocity is what makes a gravity turn cost no
    // steering losses.
    expect(command.thrustDirection.x).toBeCloseTo(300 / magnitude(velocity), 6);
    expect(command.thrustDirection.z).toBeCloseTo(400 / magnitude(velocity), 6);
  });

  it('falls back to the schedule when too slow to trust the velocity vector', () => {
    const config = GRAVITY_TURN_GUIDANCE;
    const command = computeGuidance(
      {
        ...inputs,
        altitude_m: config.pitchoverAltitude_m * 10,
        velocity: vec3(1, 0, 2),
      },
      config,
    );
    expect(command.pitch_rad).toBeCloseTo(Math.PI / 2, 9);
  });

  it('holds the last command when guidance has failed', () => {
    const last = initialCommand(DEFAULT_GUIDANCE);
    const command = computeGuidance(
      { ...inputs, altitude_m: 70_000, guidanceFailed: true, lastCommand: last },
      DEFAULT_GUIDANCE,
    );
    expect(command).toBe(last);
  });

  it('still produces a command when guidance fails with no history', () => {
    const command = computeGuidance(
      { ...inputs, guidanceFailed: true, lastCommand: null },
      DEFAULT_GUIDANCE,
    );
    expect(magnitude(command.thrustDirection)).toBeCloseTo(1, 9);
  });
});

describe('angleOfAttack', () => {
  it('is zero when thrust and velocity align', () => {
    expect(angleOfAttack(vec3(0, 0, 1), vec3(0, 0, 500))).toBeCloseTo(0, 9);
  });

  it('is a right angle when thrust is perpendicular to velocity', () => {
    expect(angleOfAttack(vec3(1, 0, 0), vec3(0, 0, 500))).toBeCloseTo(Math.PI / 2, 9);
  });

  it('is π when thrust opposes velocity', () => {
    expect(angleOfAttack(vec3(0, 0, -1), vec3(0, 0, 500))).toBeCloseTo(Math.PI, 9);
  });

  it('is zero for a stationary vehicle rather than NaN', () => {
    expect(angleOfAttack(vec3(0, 0, 1), vec3(0, 0, 0))).toBe(0);
  });
});

describe('localUpVector', () => {
  it('points along +Z directly above the launch site', () => {
    const up = localUpVector(vec3(0, 0, 10_000), R_EARTH);
    expect(up.z).toBeCloseTo(1, 9);
    expect(up.x).toBeCloseTo(0, 9);
  });

  it('tilts as the vehicle travels downrange', () => {
    const up = localUpVector(vec3(500_000, 0, 0), R_EARTH);
    expect(up.x).toBeGreaterThan(0);
    expect(up.z).toBeLessThan(1);
    expect(magnitude(up)).toBeCloseTo(1, 9);
  });

  it('always returns a unit vector', () => {
    for (const downrange of [0, 1_000, 100_000, 3_000_000]) {
      expect(magnitude(localUpVector(vec3(downrange, 0, 0), R_EARTH))).toBeCloseTo(1, 9);
    }
  });
});
