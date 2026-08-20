/**
 * Simulation contract, as the API speaks it.
 *
 * These mirror the Python engine's Pydantic models (`simulation/contracts/`),
 * which FastAPI publishes in the OpenAPI schema as `SimConfig`, `SimResult`,
 * `TelemetryPoint`, `SimEvent` and `FailureDetail`. They are snake_case
 * because that is the wire format; the TypeScript engine's own camelCase types
 * are a different thing and live in `@lostintospace/simulation-engine`.
 *
 * Hand-written for the first prototype. They should be generated from
 * `/openapi.json` once a codegen step exists — the API already publishes the
 * real shapes, so nothing here needs to be invented, only transcribed.
 */

export type MissionState =
  | 'PREPARATION'
  | 'COUNTDOWN'
  | 'IGNITION'
  | 'LIFTOFF'
  | 'ASCENT'
  | 'MAX_Q'
  | 'ENGINE_CUTOFF'
  | 'STAGE_SEPARATION'
  | 'ORBIT_INSERTION'
  | 'ORBIT'
  | 'MANEUVER'
  | 'PAYLOAD_DEPLOYMENT'
  | 'TRANSFER'
  | 'ENTRY'
  | 'DESCENT'
  | 'LANDING'
  | 'SURFACE'
  | 'FAILURE'
  | 'COMPLETE';

export type StageStatus =
  | 'stowed'
  | 'igniting'
  | 'burning'
  | 'shutdown'
  | 'separated'
  | 'failed';

export type EventSeverity = 'info' | 'warning' | 'critical' | 'fatal';
export type SimOutcome = 'success' | 'partial' | 'failure';
export type MissionType = 'suborbital' | 'leo' | 'meo' | 'geo' | 'escape';
export type GuidanceMode = 'vertical' | 'pitch_program' | 'gravity_turn';

export interface SimStage {
  stage_number: number;
  name: string;
  dry_mass_kg: number;
  propellant_mass_kg: number;
  thrust_vacuum_N: number;
  thrust_sea_level_N: number;
  isp_vacuum_s: number;
  isp_sea_level_s: number;
  mass_flow_rate_kgs: number;
  burn_time_s: number;
  ignition_delay_s: number;
  separation_delay_s: number;
  can_fire: boolean;
}

export interface SimVehicle {
  name: string;
  design_id: string;
  stages: SimStage[];
  payload_mass_kg: number;
  launch_mass_kg: number;
  length_m: number;
  diameter_m: number;
  reference_area_m2: number;
  drag_coefficient: number;
  stability_margin_wet_cal?: number;
  stability_margin_dry_cal?: number;
  max_axial_load_N?: number;
  max_dynamic_pressure_Pa?: number;
}

export interface LaunchSite {
  name: string;
  latitude_deg: number;
  longitude_deg: number;
  altitude_m: number;
}

export interface SimMission {
  name: string;
  objective: string;
  target: {
    type: MissionType;
    target_altitude_km: number;
    inclination_deg?: number | null;
  };
  launch_site: LaunchSite;
  environment: {
    temperature_K: number;
    pressure_Pa: number;
    wind_speed_ms: number;
    wind_direction_deg: number;
  };
}

export interface SimSettings {
  max_time_s: number;
  dt_powered_s: number;
  dt_coast_s: number;
  integrator: 'rk4' | 'euler' | 'velocity_verlet';
  telemetry_sample_interval_s: number;
  countdown_s: number;
  use_mach_drag_rise: boolean;
  use_altitude_compensation: boolean;
}

export interface SimGuidance {
  mode: GuidanceMode;
  launch_azimuth_deg: number;
  pitchover_altitude_m: number;
  pitch_program_end_altitude_m: number;
  final_pitch_deg: number;
  cutoff_on_target_orbit: boolean;
}

export interface FailureInjection {
  mode_id: string;
  t: number;
  is_terminal?: boolean;
}

export interface SimConfig {
  vehicle: SimVehicle;
  mission: SimMission;
  settings?: Partial<SimSettings>;
  guidance?: Partial<SimGuidance>;
  failures?: { enabled?: boolean; injections?: FailureInjection[] };
  termination?: {
    on_impact?: boolean;
    on_stable_orbit?: boolean;
    on_target_altitude?: boolean;
    on_fatal_failure?: boolean;
    on_mission_complete?: boolean;
  };
}

/** One telemetry sample. Every field is a primitive — no nesting. */
export interface TelemetryPoint {
  t: number;
  altitude_m: number;
  downrange_m: number;
  position_x_m: number;
  position_y_m: number;
  position_z_m: number;
  speed_ms: number;
  vertical_speed_ms: number;
  horizontal_speed_ms: number;
  acceleration_ms2: number;
  g_load_g: number;
  mass_kg: number;
  fuel_remaining_kg: number;
  fuel_fraction: number;
  thrust_N: number;
  mass_flow_kgs: number;
  twr: number;
  drag_N: number;
  dynamic_pressure_Pa: number;
  mach: number;
  air_density_kgm3: number;
  ambient_pressure_Pa: number;
  pitch_rad: number;
  yaw_rad: number;
  angle_of_attack_rad: number;
  semi_major_axis_m: number;
  eccentricity: number;
  periapsis_altitude_m: number;
  apoapsis_altitude_m: number;
  inclination_rad: number;
  in_orbit: boolean;
  stage: number;
  stage_status: StageStatus;
  engine_on: boolean;
  mission_state: MissionState;
  phase: string;
}

export interface FailureDetail {
  id: string;
  mode_id: string;
  subsystem: string;
  failure_mode: string;
  severity: EventSeverity;
  t: number;
  stage_index: number | null;
  trigger_condition: string;
  measured_value: number;
  threshold_value: number;
  unit: string;
  trigger_state: Record<string, number>;
  contributing_factors: string[];
  consequence: string;
  educational_explanation: string;
  recommended_fix: string;
  related_lessons: string[];
  is_terminal: boolean;
}

export interface SimEvent {
  t: number;
  type: string;
  severity: EventSeverity;
  description: string;
  data: Record<string, number | string | boolean>;
  failure: FailureDetail | null;
}

export interface SimSummary {
  max_altitude_m: number;
  max_speed_ms: number;
  max_acceleration_g: number;
  max_dynamic_pressure_Pa: number;
  max_q_altitude_m: number;
  max_mach: number;
  flight_time_s: number;
  apogee_time_s: number;
  max_downrange_m: number;
  impact_speed_ms: number | null;
  stages_separated: number;
  propellant_used_kg: number;
  delta_v_achieved_ms: number;
  delta_v_ideal_ms: number;
  gravity_loss_ms: number;
  drag_loss_ms: number;
}

export interface SimResult {
  success: boolean;
  outcome: SimOutcome;
  final_state: MissionState;
  termination_reason: string;
  telemetry: TelemetryPoint[];
  events: SimEvent[];
  failures: FailureDetail[];
  summary: SimSummary;
  total_steps: number;
  flight_time_s: number;
}

/** Provenance for a run — how it was produced, and its fidelity caveat. */
export interface SimulationMeta {
  engine: string;
  engine_version: string;
  compute_time_s: number;
  telemetry_points_generated: number;
  telemetry_points_returned: number;
  telemetry_decimated: boolean;
  fidelity_notice?: string;
}

export interface SimulationLimits {
  max_time_s: number;
  min_timestep_s: number;
  max_steps: number;
  max_telemetry_points: number;
  max_stages: number;
  max_injections: number;
}
