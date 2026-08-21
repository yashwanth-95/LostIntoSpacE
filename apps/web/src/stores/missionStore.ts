import { create } from 'zustand';
import type { RocketDesign } from '@lostintospace/simulation-engine/core/component-types';
import type { LaunchSite, MissionType, SimConfig, SimResult, SimGuidance } from '@/types/simulation';
import { LAUNCH_SITES, type SimEnvironmentInput } from '@/lib/simConfig';

/**
 * The workbench: one rocket, one mission, one flight, carried across pages.
 *
 * Rocket Lab → Builder → Launch → Mission Control is a single continuous task,
 * and it should feel like one. Holding the design and the flight result here
 * means walking back to the Builder to fix a stage does not lose the launch
 * configuration, and Mission Control does not have to re-run a flight the user
 * already watched.
 *
 * Deliberately in memory, not persisted. Saving belongs to the workspace and
 * needs an account; silently keeping a half-finished rocket in localStorage
 * across sessions would be a surprise, not a feature.
 */

export interface MissionSetup {
  name: string;
  objective: string;
  missionType: MissionType;
  targetAltitudeKm: number;
  launchSite: LaunchSite;
  guidanceMode: SimGuidance['mode'];
  launchAzimuthDeg: number;
  /** Measured conditions at the pad, or null until they are fetched. */
  environment: SimEnvironmentInput | null;
  /** The site the environment was fetched for, so a site change invalidates it. */
  environmentSiteId: string | null;
}

export const DEFAULT_MISSION: MissionSetup = {
  name: 'First Flight',
  objective: 'Reach a 200 km low Earth orbit',
  missionType: 'leo',
  targetAltitudeKm: 200,
  launchSite: LAUNCH_SITES[0],
  guidanceMode: 'pitch_program',
  launchAzimuthDeg: 90,
  environment: null,
  environmentSiteId: null,
};

interface MissionState {
  /** The design being worked on, or null before one is chosen. */
  design: RocketDesign | null;
  /** Where the design came from, for the "how did I get here" breadcrumb. */
  designSource: 'blank' | 'preset' | 'loaded';

  mission: MissionSetup;

  /** The last completed flight, or null. */
  result: SimResult | null;
  /** The config that produced `result`, kept so a re-run is reproducible. */
  lastConfig: SimConfig | null;
  /** Engine provenance for `result`, including the evaluation report. */
  resultMeta: Record<string, unknown> | null;

  /**
   * A flight deliberately kept for comparison.
   *
   * Survives changes to the design, unlike `result` — that is the entire
   * point. You keep a baseline, change one thing, fly again, and the
   * comparison shows what your change did.
   */
  baseline: (SimResult & { label: string }) | null;

  setDesign: (design: RocketDesign, source?: MissionState['designSource']) => void;
  clearDesign: () => void;
  updateMission: (patch: Partial<MissionSetup>) => void;
  setResult: (
    result: SimResult,
    config: SimConfig,
    meta: Record<string, unknown> | null,
  ) => void;
  clearResult: () => void;
  setBaseline: (result: SimResult, label: string) => void;
  clearBaseline: () => void;
}

export const useMissionStore = create<MissionState>((set) => ({
  design: null,
  designSource: 'blank',
  mission: DEFAULT_MISSION,
  result: null,
  lastConfig: null,
  resultMeta: null,
  baseline: null,

  setDesign: (design, source = 'blank') =>
    // A new design invalidates the previous flight: showing telemetry from a
    // rocket the user has since changed is worse than showing none.
    set({ design, designSource: source, result: null, lastConfig: null, resultMeta: null }),

  clearDesign: () =>
    set({ design: null, designSource: 'blank', result: null, lastConfig: null, resultMeta: null }),

  updateMission: (patch) => set((s) => ({ mission: { ...s.mission, ...patch } })),

  setResult: (result, config, meta) => set({ result, lastConfig: config, resultMeta: meta }),

  clearResult: () => set({ result: null, lastConfig: null, resultMeta: null }),

  setBaseline: (result, label) => set({ baseline: { ...result, label } }),

  clearBaseline: () => set({ baseline: null }),
}));
