/**
 * The Python/TypeScript boundary, in one file.
 *
 * The rocket builder is TypeScript: `@lostintospace/simulation-engine` owns the
 * component catalog, the design model, and the engineering analysis that
 * produces a `Vehicle`. The flight simulation is Python: the API owns physics,
 * and speaks the snake_case contract in `types/simulation.ts`.
 *
 * Those two models describe the same rocket in different dialects. This module
 * translates, and it is the *only* place that does. Everything else on either
 * side stays in its own dialect, so a field rename in either engine breaks here
 * — loudly, in one file — rather than in a dozen components.
 *
 * What deliberately does not happen here: no physics. The builder computes
 * masses, thrust and Isp; the Python engine flies them. This file moves numbers
 * between the two and adds nothing.
 */

import type { Vehicle } from '@lostintospace/simulation-engine/core/types';
import type {
  LaunchSite,
  MissionType,
  SimConfig,
  SimGuidance,
  SimSettings,
  SimVehicle,
} from '@/types/simulation';

/**
 * Launch sites offered in the UI.
 *
 * Real coordinates: inclination and downrange depend on latitude, so these are
 * not decoration. The engine does not model Earth's rotation, so an eastward
 * equatorial launch does not get the ~465 m/s it would in reality — noted in
 * docs/simulation/ASSUMPTIONS.md and surfaced in the Launch page.
 */
export const LAUNCH_SITES: readonly (LaunchSite & { agency: string })[] = [
  {
    name: 'Cape Canaveral, USA',
    agency: 'NASA / USSF',
    latitude_deg: 28.396,
    longitude_deg: -80.605,
    altitude_m: 3,
  },
  {
    name: 'Satish Dhawan, India',
    agency: 'ISRO',
    latitude_deg: 13.733,
    longitude_deg: 80.235,
    altitude_m: 12,
  },
  {
    name: 'Kourou, French Guiana',
    agency: 'ESA / CNES',
    latitude_deg: 5.239,
    longitude_deg: -52.768,
    altitude_m: 12,
  },
  {
    name: 'Baikonur, Kazakhstan',
    agency: 'Roscosmos',
    latitude_deg: 45.965,
    longitude_deg: 63.305,
    altitude_m: 90,
  },
  {
    name: 'Vandenberg, USA',
    agency: 'USSF',
    latitude_deg: 34.742,
    longitude_deg: -120.573,
    altitude_m: 100,
  },
] as const;

/** Mission profiles offered in the Launch page. */
export const MISSION_PROFILES: readonly {
  id: MissionType;
  label: string;
  altitude_km: number;
  description: string;
  guidance: SimGuidance['mode'];
}[] = [
  {
    id: 'suborbital',
    label: 'Suborbital hop',
    altitude_km: 100,
    description: 'Straight up past the Kármán line and back down. No orbit attempted.',
    guidance: 'vertical',
  },
  {
    id: 'leo',
    label: 'Low Earth orbit',
    altitude_km: 200,
    description: 'The standard ascent: pitch over early and build horizontal speed.',
    guidance: 'pitch_program',
  },
  {
    id: 'leo',
    label: 'ISS altitude',
    altitude_km: 420,
    description: 'A higher circular orbit — needs noticeably more delta-v.',
    guidance: 'pitch_program',
  },
  {
    id: 'meo',
    label: 'Medium Earth orbit',
    altitude_km: 2000,
    description: 'Well beyond LEO. Most single-stage designs will not reach this.',
    guidance: 'gravity_turn',
  },
] as const;

/** Defaults matching the engine's own, so an unset field means the same thing. */
export const DEFAULT_SETTINGS: SimSettings = {
  max_time_s: 2000,
  dt_powered_s: 0.05,
  dt_coast_s: 0.5,
  integrator: 'rk4',
  telemetry_sample_interval_s: 1,
  countdown_s: 3,
  use_mach_drag_rise: true,
  use_altitude_compensation: true,
};

/**
 * Translate the builder's `Vehicle` into the API's `SimVehicle`.
 *
 * Field-for-field, with no computation. The only judgement here is the
 * fallbacks: the builder leaves structural limits as `Infinity` for a design
 * that declares none, and `Infinity` is not valid JSON — it serialises to
 * `null` and then fails Pydantic validation. A missing limit means "no limit",
 * so it becomes a number large enough never to trigger.
 */
export function toSimVehicle(vehicle: Vehicle): SimVehicle {
  const finite = (value: number, fallback: number) =>
    Number.isFinite(value) ? value : fallback;

  return {
    name: vehicle.name,
    design_id: vehicle.designId,
    payload_mass_kg: vehicle.payloadMass_kg,
    launch_mass_kg: vehicle.launchMass_kg,
    length_m: vehicle.length_m,
    diameter_m: vehicle.diameter_m,
    reference_area_m2: vehicle.referenceArea_m2,
    drag_coefficient: vehicle.dragCoefficient,
    stability_margin_wet_cal: finite(vehicle.stabilityMarginWet_cal, 0),
    stability_margin_dry_cal: finite(vehicle.stabilityMarginDry_cal, 0),
    max_axial_load_N: finite(vehicle.maxAxialLoad_N, 1e12),
    max_dynamic_pressure_Pa: finite(vehicle.maxDynamicPressure_Pa, 1e9),
    stages: vehicle.stages.map((stage) => ({
      stage_number: stage.stageNumber,
      name: stage.name,
      dry_mass_kg: stage.dryMass_kg,
      propellant_mass_kg: stage.propellantMass_kg,
      thrust_vacuum_N: stage.thrustVacuum_N,
      thrust_sea_level_N: stage.thrustSeaLevel_N,
      isp_vacuum_s: stage.ispVacuum_s,
      isp_sea_level_s: stage.ispSeaLevel_s,
      mass_flow_rate_kgs: stage.massFlowRate_kgs,
      burn_time_s: stage.burnTime_s,
      ignition_delay_s: stage.ignitionDelay_s,
      separation_delay_s: stage.separationDelay_s,
      can_fire: stage.canFire,
    })),
  };
}

export interface BuildConfigOptions {
  vehicle: Vehicle;
  missionName: string;
  objective: string;
  targetAltitudeKm: number;
  missionType: MissionType;
  launchSite: LaunchSite;
  guidanceMode: SimGuidance['mode'];
  launchAzimuthDeg?: number;
  windSpeedMs?: number;
  injections?: { mode_id: string; t: number; is_terminal?: boolean }[];
}

/**
 * Assemble the complete request body for `POST /api/v1/simulations/run`.
 *
 * The pitch program is scheduled against altitude, so its end altitude is tied
 * to the target: a program that flattens out at 80 km is right for a 200 km
 * orbit and wrong for a 100 km hop, where the vehicle would still be pitching
 * over as it arrived.
 */
export function buildSimConfig(options: BuildConfigOptions): SimConfig {
  const targetAltitudeM = options.targetAltitudeKm * 1000;
  const isOrbital = options.missionType !== 'suborbital';

  return {
    vehicle: toSimVehicle(options.vehicle),
    mission: {
      name: options.missionName,
      objective: options.objective,
      target: {
        type: options.missionType,
        target_altitude_km: options.targetAltitudeKm,
        inclination_deg: options.launchSite.latitude_deg,
      },
      launch_site: {
        name: options.launchSite.name,
        latitude_deg: options.launchSite.latitude_deg,
        longitude_deg: options.launchSite.longitude_deg,
        altitude_m: options.launchSite.altitude_m,
      },
      environment: {
        temperature_K: 288.15,
        pressure_Pa: 101325,
        wind_speed_ms: options.windSpeedMs ?? 0,
        wind_direction_deg: 0,
      },
    },
    settings: {
      ...DEFAULT_SETTINGS,
      // A high target needs a longer window; a hop does not need 2000 s.
      max_time_s: isOrbital ? 2000 : 600,
    },
    guidance: {
      mode: options.guidanceMode,
      launch_azimuth_deg: options.launchAzimuthDeg ?? 90,
      pitchover_altitude_m: 200,
      pitch_program_end_altitude_m: Math.max(20_000, targetAltitudeM * 0.4),
      final_pitch_deg: 0,
      cutoff_on_target_orbit: isOrbital,
    },
    failures: {
      enabled: true,
      injections: options.injections ?? [],
    },
    termination: {
      on_impact: true,
      on_fatal_failure: true,
      on_mission_complete: true,
      on_stable_orbit: false,
      on_target_altitude: false,
    },
  };
}
