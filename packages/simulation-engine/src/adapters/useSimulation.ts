/**
 * `useSimulation` — run a flight from React.
 *
 * ## The problem this solves
 *
 * The simulation ticks at 20 Hz. React state updates at that rate would
 * re-render the component tree twenty times a second, which is both wasteful
 * and jerky. But the UI genuinely does need to show live telemetry.
 *
 * The resolution is to run at two different rates:
 *
 * - The **simulation and the 3D view** advance every animation frame, through a
 *   ref. React is not involved and does not re-render.
 * - **React state** updates on a slower, configurable cadence — four times a
 *   second by default, which is faster than anyone can read a number changing
 *   and 5× cheaper than every frame.
 *
 * Callers who want every frame can read `simulationRef.current.getState()`
 * inside their own `requestAnimationFrame`, which is exactly what the 3D
 * viewer does.
 *
 * @module adapters/useSimulation
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { SimConfig } from '../sim/config.js';
import { Simulation, type SimResult } from '../sim/runner.js';
import type { SimulationState, SimStatus } from '../sim/state.js';
import type { SimEvent } from '../sim/events.js';
import type { TelemetryPoint } from '../sim/telemetry.js';
import type { MissionState } from '../sim/mission-state.js';

/** Options for {@link useSimulation}. */
export interface UseSimulationOptions {
  /** The flight to run. Changing it rebuilds the simulation. */
  readonly config: SimConfig | null;
  /**
   * Simulated seconds per real second. 1 is real time; 10 runs ten times
   * faster. The engine's step size does not change — more steps are taken per
   * frame — so accuracy is unaffected.
   */
  readonly timeScale?: number;
  /** How often React state is refreshed. Unit: Hz. */
  readonly uiUpdateRate_hz?: number;
  /** Start as soon as the config is available. */
  readonly autoStart?: boolean;
  /**
   * Cap on integration steps per animation frame.
   *
   * At high time scales an unbounded loop can spend longer than a frame budget
   * inside `step`, which stalls the browser. This bounds the work and lets the
   * simulation fall behind real time instead — visibly slower, but never frozen.
   */
  readonly maxStepsPerFrame?: number;
  /** Called once when the flight terminates. */
  readonly onComplete?: (result: SimResult) => void;
  /** Called for each new event as it is emitted. */
  readonly onEvent?: (event: SimEvent) => void;
}

/** What {@link useSimulation} returns. */
export interface UseSimulationResult {
  /** Current run status. */
  readonly status: SimStatus;
  /** Simulated time. Unit: s. Refreshed at the UI rate. */
  readonly time_s: number;
  /** Current mission state. Refreshed at the UI rate. */
  readonly missionState: MissionState;
  /** Latest telemetry sample. Refreshed at the UI rate. */
  readonly telemetry: TelemetryPoint | null;
  /** Every event so far. Refreshed at the UI rate. */
  readonly events: readonly SimEvent[];
  /** The full result once the flight ends, or null while it is running. */
  readonly result: SimResult | null;

  /**
   * The live simulation.
   *
   * Read `.getState()` from here inside your own animation frame when you need
   * per-frame data. Do not call `step` on it — the hook owns the clock.
   */
  readonly simulationRef: React.RefObject<Simulation | null>;

  /** Start, or resume after a pause. */
  readonly start: () => void;
  /** Pause. */
  readonly pause: () => void;
  /** Reset to T−countdown and discard the flight. */
  readonly reset: () => void;
  /** Advance exactly one step, for frame-by-frame inspection. */
  readonly stepOnce: () => void;
  /** Run to termination immediately, without animating. */
  readonly runToCompletion: () => SimResult | null;
  /** Change the time scale. */
  readonly setTimeScale: (scale: number) => void;
  /** The current time scale. */
  readonly timeScale: number;
}

/**
 * Drive a simulation from a React component.
 *
 * @param options - Config and playback settings.
 * @returns Playback controls and UI-rate state.
 */
export function useSimulation(options: UseSimulationOptions): UseSimulationResult {
  const {
    config,
    uiUpdateRate_hz = 4,
    autoStart = false,
    maxStepsPerFrame = 2_000,
    onComplete,
    onEvent,
  } = options;

  const simulationRef = useRef<Simulation | null>(null);
  const frameRef = useRef<number | null>(null);
  const lastFrameTimeRef = useRef<number>(0);
  const lastUiUpdateRef = useRef<number>(0);
  const eventCursorRef = useRef<number>(0);
  const runningRef = useRef<boolean>(false);
  const timeScaleRef = useRef<number>(options.timeScale ?? 1);

  // Callbacks live in refs so changing them does not restart the animation loop.
  const onCompleteRef = useRef(onComplete);
  const onEventRef = useRef(onEvent);
  onCompleteRef.current = onComplete;
  onEventRef.current = onEvent;

  const [status, setStatus] = useState<SimStatus>('ready');
  const [time_s, setTime] = useState(0);
  const [missionState, setMissionState] = useState<MissionState>('PREPARATION');
  const [telemetry, setTelemetry] = useState<TelemetryPoint | null>(null);
  const [events, setEvents] = useState<readonly SimEvent[]>([]);
  const [result, setResult] = useState<SimResult | null>(null);
  const [timeScale, setTimeScaleState] = useState(options.timeScale ?? 1);

  /** Copy the simulation's state into React state. */
  const publish = useCallback((simulation: Simulation): void => {
    const state: SimulationState = simulation.getState();
    setStatus(state.status);
    setTime(state.time_s);
    setMissionState(state.missionState);
    setTelemetry(state.telemetry);
    setEvents(state.events.slice());
  }, []);

  /** Fire onEvent for anything emitted since the last check. */
  const drainEvents = useCallback((simulation: Simulation): void => {
    const handler = onEventRef.current;
    const all = simulation.getEvents();
    if (handler) {
      for (let i = eventCursorRef.current; i < all.length; i++) {
        handler(all[i]!);
      }
    }
    eventCursorRef.current = all.length;
  }, []);

  // Build the simulation whenever the config changes.
  useEffect(() => {
    if (!config) {
      simulationRef.current = null;
      return;
    }

    const simulation = new Simulation(config);
    simulationRef.current = simulation;
    eventCursorRef.current = 0;
    setResult(null);
    publish(simulation);

    if (autoStart) runningRef.current = true;

    return () => {
      runningRef.current = false;
      simulationRef.current = null;
    };
  }, [config, autoStart, publish]);

  // The animation loop. Mounted once and left running; `runningRef` gates the
  // work, so starting and pausing never tears down the loop.
  useEffect(() => {
    const tick = (now: number): void => {
      frameRef.current = requestAnimationFrame(tick);

      const simulation = simulationRef.current;
      if (!simulation || !runningRef.current) {
        lastFrameTimeRef.current = now;
        return;
      }

      // Clamp the frame delta. A backgrounded tab can produce a delta of many
      // seconds, and simulating all of it at once would freeze the page on
      // return.
      const frameDelta_s = Math.min(0.25, (now - lastFrameTimeRef.current) / 1000);
      lastFrameTimeRef.current = now;

      const targetSimSeconds = frameDelta_s * timeScaleRef.current;
      const dt = simulation.config.settings.dt_powered_s;
      const stepBudget = Math.min(
        maxStepsPerFrame,
        Math.max(1, Math.ceil(targetSimSeconds / dt)),
      );

      for (let i = 0; i < stepBudget && !simulation.isFinished; i++) {
        simulation.step();
      }

      drainEvents(simulation);

      if (simulation.isFinished) {
        runningRef.current = false;
        publish(simulation);
        const finalResult = simulation.getResult();
        setResult(finalResult);
        onCompleteRef.current?.(finalResult);
        return;
      }

      // Throttle React updates to the UI rate.
      const uiInterval_ms = 1000 / uiUpdateRate_hz;
      if (now - lastUiUpdateRef.current >= uiInterval_ms) {
        lastUiUpdateRef.current = now;
        publish(simulation);
      }
    };

    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    };
  }, [uiUpdateRate_hz, maxStepsPerFrame, publish, drainEvents]);

  const start = useCallback((): void => {
    const simulation = simulationRef.current;
    if (!simulation || simulation.isFinished) return;
    simulation.resume();
    runningRef.current = true;
    lastFrameTimeRef.current = performance.now();
    setStatus('running');
  }, []);

  const pause = useCallback((): void => {
    const simulation = simulationRef.current;
    if (!simulation) return;
    runningRef.current = false;
    simulation.pause();
    publish(simulation);
  }, [publish]);

  const reset = useCallback((): void => {
    const simulation = simulationRef.current;
    if (!simulation) return;
    runningRef.current = false;
    simulation.reset();
    eventCursorRef.current = 0;
    setResult(null);
    publish(simulation);
  }, [publish]);

  const stepOnce = useCallback((): void => {
    const simulation = simulationRef.current;
    if (!simulation || simulation.isFinished) return;
    // `step` is a no-op while paused, so resume for exactly one step.
    simulation.resume();
    simulation.step();
    simulation.pause();
    drainEvents(simulation);
    publish(simulation);
  }, [publish, drainEvents]);

  const runToCompletion = useCallback((): SimResult | null => {
    const simulation = simulationRef.current;
    if (!simulation) return null;
    runningRef.current = false;
    simulation.resume();
    const finalResult = simulation.run();
    drainEvents(simulation);
    publish(simulation);
    setResult(finalResult);
    onCompleteRef.current?.(finalResult);
    return finalResult;
  }, [publish, drainEvents]);

  const setTimeScale = useCallback((scale: number): void => {
    const clamped = Math.max(0.1, Math.min(1_000, scale));
    timeScaleRef.current = clamped;
    setTimeScaleState(clamped);
  }, []);

  return {
    status,
    time_s,
    missionState,
    telemetry,
    events,
    result,
    simulationRef,
    start,
    pause,
    reset,
    stepOnce,
    runToCompletion,
    setTimeScale,
    timeScale,
  };
}
