import { useCallback, useEffect, useRef, useState } from 'react';
import type { TelemetryPoint } from '@/types/simulation';

/**
 * Replays a completed flight against a wall clock.
 *
 * ## Why replay rather than stream
 *
 * The Python engine computes the whole flight in well under a second and
 * returns every sample at once. Streaming it back frame by frame would add a
 * network round trip per frame for data the client already holds, and would
 * make the simulation non-deterministic for no gain. So the flight is computed
 * once, and *watched* here.
 *
 * ## Simulation speed is not frame rate
 *
 * `speed` scales simulated seconds per real second. The animation frame rate is
 * whatever the browser gives us. Advancing `missionTime` by `delta * speed`
 * keeps those independent, so 10× playback shows the same flight faster rather
 * than a different, coarser one — and a browser that drops to 30 fps still
 * plays the mission at the right speed.
 */

export interface PlaybackState {
  /** Current simulated time. Unit: s. */
  missionTime: number;
  /** The telemetry sample at `missionTime`. */
  frame: TelemetryPoint | null;
  /** Index of that sample. */
  index: number;
  isPlaying: boolean;
  speed: number;
  /** Simulated duration of the whole flight. Unit: s. */
  duration: number;

  play: () => void;
  pause: () => void;
  toggle: () => void;
  reset: () => void;
  setSpeed: (speed: number) => void;
  seek: (time: number) => void;
}

export const PLAYBACK_SPEEDS = [0.25, 0.5, 1, 2, 5, 10] as const;

export function useTelemetryPlayback(
  telemetry: readonly TelemetryPoint[],
  options: { autoPlay?: boolean } = {},
): PlaybackState {
  const [missionTime, setMissionTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(options.autoPlay ?? true);
  const [speed, setSpeed] = useState(1);

  const frameRef = useRef<number>();
  const lastTickRef = useRef<number>();

  const first = telemetry[0]?.t ?? 0;
  const duration = telemetry.length ? telemetry[telemetry.length - 1].t : 0;

  // A new flight starts from the beginning rather than mid-air at the previous
  // one's timestamp.
  useEffect(() => {
    setMissionTime(first);
    setIsPlaying(options.autoPlay ?? true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [telemetry]);

  useEffect(() => {
    if (!isPlaying || telemetry.length === 0) {
      lastTickRef.current = undefined;
      return;
    }

    const tick = (now: number) => {
      const last = lastTickRef.current;
      lastTickRef.current = now;

      if (last !== undefined) {
        // Clamp the delta so returning to a backgrounded tab does not jump the
        // mission forward by however long the tab was hidden.
        const deltaSeconds = Math.min((now - last) / 1000, 0.25);
        setMissionTime((current) => {
          const next = current + deltaSeconds * speed;
          if (next >= duration) {
            setIsPlaying(false);
            return duration;
          }
          return next;
        });
      }

      frameRef.current = requestAnimationFrame(tick);
    };

    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
      lastTickRef.current = undefined;
    };
  }, [isPlaying, speed, duration, telemetry.length]);

  // Binary search: a 5,000-sample flight scanned linearly every frame is
  // wasted work, and the samples are already sorted by time.
  const index = findSampleIndex(telemetry, missionTime);
  const frame = telemetry[index] ?? null;

  const play = useCallback(() => {
    setMissionTime((t) => (t >= duration ? first : t));
    setIsPlaying(true);
  }, [duration, first]);

  const pause = useCallback(() => setIsPlaying(false), []);
  const toggle = useCallback(() => (isPlaying ? pause() : play()), [isPlaying, pause, play]);

  const reset = useCallback(() => {
    setMissionTime(first);
    setIsPlaying(false);
  }, [first]);

  const seek = useCallback(
    (time: number) => setMissionTime(Math.max(first, Math.min(duration, time))),
    [first, duration],
  );

  return {
    missionTime,
    frame,
    index,
    isPlaying,
    speed,
    duration,
    play,
    pause,
    toggle,
    reset,
    setSpeed,
    seek,
  };
}

function findSampleIndex(telemetry: readonly TelemetryPoint[], time: number): number {
  if (telemetry.length === 0) return -1;
  let low = 0;
  let high = telemetry.length - 1;
  while (low < high) {
    const mid = (low + high + 1) >> 1;
    if (telemetry[mid].t <= time) low = mid;
    else high = mid - 1;
  }
  return low;
}
