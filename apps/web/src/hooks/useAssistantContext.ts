import { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { createStockRegistry } from '@lostintospace/simulation-engine/core/catalog';
import { analyzeRocket } from '@lostintospace/simulation-engine/core/builder';

import type { AssistantContext } from '@/services/api';
import { useMissionStore } from '@/stores/missionStore';

/**
 * What the assistant needs to answer about *your* rocket.
 *
 * Sent with every question. Without it, "why is my rocket unstable?" can only
 * be answered with the general theory of static margin — correct, and useless,
 * because the user has a particular vehicle with a particular margin and what
 * they need is the number and what to change.
 *
 * Everything here is already computed elsewhere: the analysis comes from the
 * same `analyzeRocket` the builder displays, the flight result from the store,
 * the weather from whatever the launch page fetched. Nothing is measured twice,
 * so the assistant cannot disagree with the readout the user is looking at.
 *
 * Deliberately a *summary*, not a dump. The server caps the context at 64 KB,
 * and a full telemetry series is megabytes — the assistant needs the peaks and
 * the failures, not five thousand samples.
 */
export function useAssistantContext(extra?: Partial<AssistantContext>): AssistantContext {
  const location = useLocation();
  const design = useMissionStore((s) => s.design);
  const mission = useMissionStore((s) => s.mission);
  const result = useMissionStore((s) => s.result);
  const meta = useMissionStore((s) => s.resultMeta);

  const registry = useMemo(() => createStockRegistry(), []);

  return useMemo(() => {
    const context: AssistantContext = { page: location.pathname, ...extra };

    if (design) {
      try {
        const analysis = analyzeRocket(design, registry);
        context.rocket = {
          name: design.name,
          stage_count: design.stages.length,
          component_count: design.components.length,
          total_wet_mass_kg: round(analysis.totalWetMass_kg, 1),
          total_dry_mass_kg: round(analysis.totalDryMass_kg, 1),
          payload_mass_kg: round(analysis.payloadMass_kg, 1),
          total_delta_v_ms: round(analysis.totalDeltaV_ms, 0),
          liftoff_twr: round(analysis.liftoffTWR, 3),
          stability_margin_wet_cal: round(analysis.stabilityWet.stabilityMargin_cal, 3),
          stability_margin_dry_cal: round(analysis.stabilityDry.stabilityMargin_cal, 3),
          cg_wet_m: round(analysis.stabilityWet.cg_m, 3),
          cp_m: round(analysis.stabilityWet.cp_m, 3),
          length_m: round(analysis.totalLength_m, 3),
          diameter_m: round(analysis.maxDiameter_m, 3),
          validation_errors: [],
          validation_warnings: [],
        };
      } catch {
        // An un-analysable design is a builder problem, not a reason to send
        // no context at all — the mission and the last flight are still useful.
      }
    }

    context.mission = {
      name: mission.name,
      objective: mission.objective,
      target_altitude_km: mission.targetAltitudeKm,
      mission_type: mission.missionType,
      launch_site: mission.launchSite.name,
      guidance_mode: mission.guidanceMode,
    };

    if (result) {
      const summary = result.summary;
      context.simulation = {
        outcome: result.outcome,
        success: result.success,
        termination_reason: result.termination_reason,
        final_state: result.final_state,
        max_altitude_m: round(summary.max_altitude_m, 0),
        max_speed_ms: round(summary.max_speed_ms, 0),
        max_acceleration_g: round(summary.max_acceleration_g, 2),
        max_dynamic_pressure_Pa: round(summary.max_dynamic_pressure_Pa, 0),
        max_q_alpha_Padeg: round(summary.max_q_alpha_Padeg, 0),
        max_lateral_deviation_m: round(summary.max_lateral_deviation_m, 0),
        flight_time_s: round(summary.flight_time_s, 1),
        delta_v_ideal_ms: round(summary.delta_v_ideal_ms, 0),
        delta_v_achieved_ms: round(summary.delta_v_achieved_ms, 0),
        gravity_loss_ms: round(summary.gravity_loss_ms, 0),
        drag_loss_ms: round(summary.drag_loss_ms, 0),
        // Capped: a pathological design can produce a long failure list, and
        // the first few are the ones that ended the flight.
        failures: result.failures.slice(0, 8).map((failure) => ({
          mode_id: failure.mode_id,
          failure_mode: failure.failure_mode,
          subsystem: failure.subsystem,
          severity: failure.severity,
          t: round(failure.t, 2),
          measured_value: round(failure.measured_value, 4),
          threshold_value: round(failure.threshold_value, 4),
          unit: failure.unit,
          recommended_fix: failure.recommended_fix,
        })),
      };
    }

    const evaluation = (meta as { evaluation?: EvaluationShape } | null)?.evaluation;
    if (evaluation) {
      context.evaluation = {
        overall_score: evaluation.overall_score,
        categories: evaluation.categories.map((category) => ({
          id: category.id,
          label: category.label,
          score: category.score,
        })),
        weaknesses: evaluation.weaknesses.slice(0, 6),
      };
    }

    return context;
    // `extra` is a fresh object each render on most call sites; comparing its
    // fields rather than its identity keeps this from recomputing constantly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, design, mission, result, meta, registry, JSON.stringify(extra ?? {})]);
}

interface EvaluationShape {
  overall_score: number;
  categories: { id: string; label: string; score: number }[];
  weaknesses: string[];
}

/** Round for transport. Sixteen significant figures help nobody and cost bytes. */
function round(value: number, digits: number): number {
  if (!Number.isFinite(value)) return 0;
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}
