import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PLAYBACK_SPEEDS, useTelemetryPlayback } from './useTelemetryPlayback';
import type { TelemetryPoint } from '@/types/simulation';

/**
 * Playback is where "simulation speed" and "frame rate" must stay separate.
 * These tests drive requestAnimationFrame manually so timing is deterministic.
 */

function sample(t: number, altitude = t * 100): TelemetryPoint {
  return {
    t,
    altitude_m: altitude,
    downrange_m: 0,
    position_x_m: 0,
    position_y_m: 0,
    position_z_m: altitude,
    speed_ms: t * 10,
    vertical_speed_ms: t * 10,
    horizontal_speed_ms: 0,
    acceleration_ms2: 10,
    g_load_g: 1,
    mass_kg: 1000 - t,
    fuel_remaining_kg: 500,
    fuel_fraction: 0.5,
    thrust_N: 10_000,
    mass_flow_kgs: 1,
    twr: 1.5,
    drag_N: 100,
    airspeed_ms: t * 10,
    wind_speed_ms: 0,
    wind_direction_deg: 0,
    q_alpha_Padeg: 0,
    lateral_deviation_m: 0,
    dynamic_pressure_Pa: 1000,
    mach: 0.5,
    air_density_kgm3: 1.2,
    ambient_pressure_Pa: 101_325,
    pitch_rad: 1.5,
    yaw_rad: 0,
    angle_of_attack_rad: 0,
    semi_major_axis_m: 0,
    eccentricity: 0,
    periapsis_altitude_m: 0,
    apoapsis_altitude_m: 0,
    inclination_rad: 0,
    in_orbit: false,
    stage: 0,
    stage_status: 'burning',
    engine_on: true,
    mission_state: 'ASCENT',
    phase: 'powered',
  };
}

const telemetry = Array.from({ length: 101 }, (_, i) => sample(i));

/**
 * A controllable animation clock.
 *
 * `cancelAnimationFrame` genuinely removes the callback rather than being a
 * no-op. That matters: when the hook's effect re-runs (on a speed change, say)
 * it cancels the previous frame and schedules a new one. A no-op cancel leaves
 * the stale closure running alongside the new one, still holding the *old*
 * speed — so the flight advances at the wrong rate and the test appears to
 * catch a bug in the hook that is really a bug in the harness.
 */
let frameCallbacks = new Map<number, FrameRequestCallback>();
let nextFrameId = 1;
let now = 0;

/** Advance the animation clock by `ms`, running the frames scheduled for it. */
function advance(ms: number) {
  now += ms;
  const scheduled = [...frameCallbacks.entries()];
  frameCallbacks = new Map();
  act(() => {
    for (const [, callback] of scheduled) callback(now);
  });
}

beforeEach(() => {
  now = 0;
  nextFrameId = 1;
  frameCallbacks = new Map();
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    const id = nextFrameId;
    nextFrameId += 1;
    frameCallbacks.set(id, callback);
    return id;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => {
    frameCallbacks.delete(id);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useTelemetryPlayback', () => {
  it('starts at the beginning of the flight', () => {
    const { result } = renderHook(() => useTelemetryPlayback(telemetry, { autoPlay: false }));
    expect(result.current.missionTime).toBe(0);
    expect(result.current.frame?.t).toBe(0);
  });

  it('reports the flight duration', () => {
    const { result } = renderHook(() => useTelemetryPlayback(telemetry, { autoPlay: false }));
    expect(result.current.duration).toBe(100);
  });

  it('does not advance while paused', () => {
    const { result } = renderHook(() => useTelemetryPlayback(telemetry, { autoPlay: false }));
    advance(1000);
    advance(1000);
    expect(result.current.missionTime).toBe(0);
  });

  it('advances one simulated second per real second at 1x', () => {
    const { result } = renderHook(() => useTelemetryPlayback(telemetry, { autoPlay: true }));
    advance(0); // establish the clock baseline
    advance(200);
    advance(200);
    expect(result.current.missionTime).toBeCloseTo(0.4, 2);
  });

  it('advances ten times as fast at 10x', () => {
    const { result } = renderHook(() => useTelemetryPlayback(telemetry, { autoPlay: true }));
    act(() => result.current.setSpeed(10));
    advance(0);
    advance(200);
    expect(result.current.missionTime).toBeCloseTo(2, 1);
  });

  it('is unaffected by how many frames the browser delivers', () => {
    // The same elapsed wall-clock time must produce the same mission time,
    // whether it arrived as one frame or ten. This is the property that keeps
    // playback speed independent of frame rate.
    const coarse = renderHook(() => useTelemetryPlayback(telemetry, { autoPlay: true }));
    advance(0);
    advance(200);
    const afterOneFrame = coarse.result.current.missionTime;

    now = 0;
    frameCallbacks = new Map();
    const fine = renderHook(() => useTelemetryPlayback(telemetry, { autoPlay: true }));
    advance(0);
    for (let i = 0; i < 10; i += 1) advance(20);

    expect(fine.result.current.missionTime).toBeCloseTo(afterOneFrame, 3);
  });

  it('clamps a huge frame gap so a backgrounded tab does not skip the flight', () => {
    const { result } = renderHook(() => useTelemetryPlayback(telemetry, { autoPlay: true }));
    advance(0);
    advance(60_000); // the tab was hidden for a minute
    // Clamped to 0.25 s of simulated time rather than jumping 60 s ahead.
    expect(result.current.missionTime).toBeLessThanOrEqual(0.25);
  });

  it('stops at the end rather than running past it', () => {
    const { result } = renderHook(() => useTelemetryPlayback(telemetry, { autoPlay: true }));
    act(() => result.current.setSpeed(10));
    advance(0);
    for (let i = 0; i < 80; i += 1) advance(200);

    expect(result.current.missionTime).toBe(100);
    expect(result.current.isPlaying).toBe(false);
  });

  it('seeks to a time and selects the matching sample', () => {
    const { result } = renderHook(() => useTelemetryPlayback(telemetry, { autoPlay: false }));
    act(() => result.current.seek(42.7));
    expect(result.current.missionTime).toBeCloseTo(42.7, 5);
    // The sample at or before the requested time, never after it.
    expect(result.current.frame?.t).toBe(42);
  });

  it('refuses to seek outside the flight', () => {
    const { result } = renderHook(() => useTelemetryPlayback(telemetry, { autoPlay: false }));
    act(() => result.current.seek(-50));
    expect(result.current.missionTime).toBe(0);
    act(() => result.current.seek(9999));
    expect(result.current.missionTime).toBe(100);
  });

  it('resets to the start and pauses', () => {
    const { result } = renderHook(() => useTelemetryPlayback(telemetry, { autoPlay: true }));
    act(() => result.current.seek(50));
    act(() => result.current.reset());
    expect(result.current.missionTime).toBe(0);
    expect(result.current.isPlaying).toBe(false);
  });

  it('replays from the start when played after finishing', () => {
    const { result } = renderHook(() => useTelemetryPlayback(telemetry, { autoPlay: false }));
    act(() => result.current.seek(100));
    act(() => result.current.play());
    expect(result.current.missionTime).toBe(0);
    expect(result.current.isPlaying).toBe(true);
  });

  it('handles an empty flight without crashing', () => {
    const { result } = renderHook(() => useTelemetryPlayback([], { autoPlay: true }));
    expect(result.current.frame).toBeNull();
    expect(result.current.duration).toBe(0);
    advance(1000);
    expect(result.current.missionTime).toBe(0);
  });

  it('offers the documented speed range', () => {
    expect(PLAYBACK_SPEEDS).toContain(0.25);
    expect(PLAYBACK_SPEEDS).toContain(1);
    expect(PLAYBACK_SPEEDS).toContain(10);
  });
});
