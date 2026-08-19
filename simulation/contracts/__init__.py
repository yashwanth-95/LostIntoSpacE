"""
Shared simulation contracts — Pydantic models for the data exchanged between
the Python simulation engine and the TypeScript/React frontend.

These models define the canonical shapes for Vehicle, SimConfig, SimulationState,
TelemetryPoint, SimEvent, FailureDetail, and SimResult. They match the existing
TypeScript interfaces in packages/simulation-engine/src/ one-to-one.

All values are SI units unless documented otherwise.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ──────────────────────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────────────────────


class MissionType(str, Enum):
    """Mission type classification."""
    SUBORBITAL = "suborbital"
    LEO = "leo"
    MEO = "meo"
    GEO = "geo"
    ESCAPE = "escape"


class FlightPhase(str, Enum):
    """Coarse flight phase."""
    PRELAUNCH = "prelaunch"
    POWERED = "powered"
    COAST = "coast"
    DESCENT = "descent"
    TERMINATED = "terminated"


class StageStatus(str, Enum):
    """What a stage is doing right now."""
    STOWED = "stowed"
    IGNITING = "igniting"
    BURNING = "burning"
    SHUTDOWN = "shutdown"
    SEPARATED = "separated"
    FAILED = "failed"


class MissionState(str, Enum):
    """Every mission state the engine knows."""
    PREPARATION = "PREPARATION"
    COUNTDOWN = "COUNTDOWN"
    IGNITION = "IGNITION"
    LIFTOFF = "LIFTOFF"
    ASCENT = "ASCENT"
    MAX_Q = "MAX_Q"
    ENGINE_CUTOFF = "ENGINE_CUTOFF"
    STAGE_SEPARATION = "STAGE_SEPARATION"
    ORBIT_INSERTION = "ORBIT_INSERTION"
    ORBIT = "ORBIT"
    MANEUVER = "MANEUVER"
    PAYLOAD_DEPLOYMENT = "PAYLOAD_DEPLOYMENT"
    TRANSFER = "TRANSFER"
    ENTRY = "ENTRY"
    DESCENT = "DESCENT"
    LANDING = "LANDING"
    SURFACE = "SURFACE"
    FAILURE = "FAILURE"
    COMPLETE = "COMPLETE"


class SimStatus(str, Enum):
    """Whether the simulation is running, and why it stopped."""
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETE = "complete"
    FAILED = "failed"


class EventSeverity(str, Enum):
    """Event severity, ordered by impact."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    FATAL = "fatal"


class GravityModel(str, Enum):
    """Gravity model selection."""
    INVERSE_SQUARE = "inverse_square"


class AtmosphereModel(str, Enum):
    """Atmosphere model selection."""
    US_STANDARD_1976 = "us_standard_1976"


class IntegratorMethod(str, Enum):
    """Numerical integrator selection."""
    RK4 = "rk4"
    EULER = "euler"
    VELOCITY_VERLET = "velocity_verlet"


class GuidanceMode(str, Enum):
    """Which attitude program to fly."""
    VERTICAL = "vertical"
    PITCH_PROGRAM = "pitch_program"
    GRAVITY_TURN = "gravity_turn"


class SimOutcome(str, Enum):
    """Overall outcome of a completed run."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


class FailureSubsystem(str, Enum):
    """Which subsystem a failure originated in."""
    PROPULSION = "propulsion"
    STRUCTURE = "structure"
    AERODYNAMICS = "aerodynamics"
    TRAJECTORY = "trajectory"
    THERMAL = "thermal"
    AVIONICS = "avionics"
    POWER = "power"
    COMMUNICATION = "communication"
    RECOVERY = "recovery"


# ──────────────────────────────────────────────────────────────
# Vehicle / Domain
# ──────────────────────────────────────────────────────────────


class Stage(BaseModel):
    """One stage as the simulation sees it."""
    stage_number: int = Field(description="Stage index, 0 = bottom")
    name: str

    dry_mass_kg: float = Field(ge=0, description="Structural mass. Unit: kg")
    propellant_mass_kg: float = Field(ge=0, description="Propellant at ignition. Unit: kg")

    thrust_vacuum_N: float = Field(ge=0, description="Vacuum thrust. Unit: N")
    thrust_sea_level_N: float = Field(ge=0, description="Sea-level thrust. Unit: N")
    isp_vacuum_s: float = Field(ge=0, description="Vacuum Isp. Unit: s")
    isp_sea_level_s: float = Field(ge=0, description="Sea-level Isp. Unit: s")
    mass_flow_rate_kgs: float = Field(ge=0, description="Mass flow. Unit: kg/s")
    burn_time_s: float = Field(ge=0, description="Burn time. Unit: s")

    ignition_delay_s: float = Field(default=0.0, ge=0, description="Ignition delay. Unit: s")
    separation_delay_s: float = Field(default=0.0, ge=0, description="Separation delay. Unit: s")

    can_fire: bool = Field(default=True, description="Whether this stage can fire")

    model_config = ConfigDict(frozen=True)


class Vehicle(BaseModel):
    """A rocket reduced to the numbers the flight simulation needs."""
    name: str
    design_id: str

    stages: list[Stage]

    payload_mass_kg: float = Field(ge=0, description="Payload mass. Unit: kg")
    launch_mass_kg: float = Field(ge=0, description="Mass on the pad. Unit: kg")

    length_m: float = Field(ge=0, description="Nose to tail. Unit: m")
    diameter_m: float = Field(ge=0, description="Largest diameter. Unit: m")
    reference_area_m2: float = Field(ge=0, description="Aero reference area. Unit: m²")
    drag_coefficient: float = Field(ge=0, description="Subsonic Cd")

    stability_margin_wet_cal: float = Field(default=0.0, description="Static margin, full. Unit: calibers")
    stability_margin_dry_cal: float = Field(default=0.0, description="Static margin, empty. Unit: calibers")

    max_axial_load_N: float = Field(default=1e9, ge=0, description="Structural limit. Unit: N")
    max_dynamic_pressure_Pa: float = Field(default=1e6, ge=0, description="Max q limit. Unit: Pa")

    model_config = ConfigDict(frozen=True)


# ──────────────────────────────────────────────────────────────
# Launch site / Environment / Mission
# ──────────────────────────────────────────────────────────────


class LaunchSite(BaseModel):
    """Launch site location."""
    name: str
    latitude_deg: float = Field(ge=-90, le=90)
    longitude_deg: float = Field(ge=-180, le=180)
    altitude_m: float = Field(ge=0)

    model_config = ConfigDict(frozen=True)


class EnvironmentConfig(BaseModel):
    """Launch-day conditions."""
    temperature_K: float = Field(default=288.15, description="Surface temperature. Unit: K")
    pressure_Pa: float = Field(default=101_325.0, description="Surface pressure. Unit: Pa")
    wind_speed_ms: float = Field(default=0.0, ge=0, description="Wind speed. Unit: m/s")
    wind_direction_deg: float = Field(default=0.0, description="Wind from direction. Unit: degrees")

    model_config = ConfigDict(frozen=True)


class MissionTarget(BaseModel):
    """Mission target."""
    type: MissionType
    target_altitude_km: float = Field(ge=0, description="Target altitude. Unit: km")
    inclination_deg: float | None = Field(default=None, description="Target inclination. Unit: degrees")

    model_config = ConfigDict(frozen=True)


class MissionConfig(BaseModel):
    """Mission configuration."""
    name: str
    objective: str
    target: MissionTarget
    launch_site: LaunchSite
    environment: EnvironmentConfig

    model_config = ConfigDict(frozen=True)


# ──────────────────────────────────────────────────────────────
# Simulation configuration
# ──────────────────────────────────────────────────────────────


class SimSettings(BaseModel):
    """Numerical and sampling settings."""
    max_time_s: float = Field(default=1200.0, description="Hard stop. Unit: s")
    dt_powered_s: float = Field(default=0.05, description="Powered timestep. Unit: s")
    dt_coast_s: float = Field(default=0.5, description="Coast timestep. Unit: s")
    integrator: IntegratorMethod = Field(default=IntegratorMethod.RK4)
    gravity_model: GravityModel = Field(default=GravityModel.INVERSE_SQUARE)
    atmosphere_model: AtmosphereModel = Field(default=AtmosphereModel.US_STANDARD_1976)
    telemetry_sample_interval_s: float = Field(default=1.0, description="Sample interval. Unit: s")
    countdown_s: float = Field(default=3.0, description="Countdown. Unit: s")
    use_mach_drag_rise: bool = Field(default=True)
    use_altitude_compensation: bool = Field(default=True)
    max_steps: int = Field(default=2_000_000)

    model_config = ConfigDict(frozen=True)


class TerminationConfig(BaseModel):
    """When a run should stop."""
    on_impact: bool = Field(default=True)
    on_stable_orbit: bool = Field(default=False)
    on_target_altitude: bool = Field(default=False)
    on_fatal_failure: bool = Field(default=True)
    on_mission_complete: bool = Field(default=True)

    model_config = ConfigDict(frozen=True)


class GuidanceConfig(BaseModel):
    """Attitude program configuration."""
    mode: GuidanceMode = Field(default=GuidanceMode.PITCH_PROGRAM)
    launch_azimuth_deg: float = Field(default=90.0)
    pitchover_altitude_m: float = Field(default=200.0)
    pitch_program_end_altitude_m: float = Field(default=80_000.0)
    final_pitch_deg: float = Field(default=0.0)
    gravity_turn_kick_deg: float = Field(default=12.0)
    gravity_turn_kick_band: float = Field(default=4.0)
    gravity_turn_min_speed_ms: float = Field(default=80.0)
    cutoff_on_target_orbit: bool = Field(default=True)

    model_config = ConfigDict(frozen=True)


class FailureThresholds(BaseModel):
    """Thresholds the automatic detection rules compare against."""
    max_g_load_g: float = Field(default=15.0)
    max_dynamic_pressure_Pa: float | None = Field(default=None)
    min_liftoff_twr: float = Field(default=1.0)
    max_atmospheric_speed_ms: float = Field(default=3000.0)
    heating_altitude_ceiling_m: float = Field(default=60_000.0)

    model_config = ConfigDict(frozen=True)


class FailureConfig(BaseModel):
    """Failure detection and injection settings."""
    enabled: bool = Field(default=True)
    detection_enabled: bool = Field(default=True)
    seed: int = Field(default=1)
    injections: list[dict] = Field(default_factory=list)
    thresholds: FailureThresholds = Field(default_factory=FailureThresholds)

    model_config = ConfigDict(frozen=True)


class SimConfig(BaseModel):
    """The complete, immutable input to a simulation run."""
    vehicle: Vehicle
    mission: MissionConfig
    settings: SimSettings = Field(default_factory=SimSettings)
    guidance: GuidanceConfig = Field(default_factory=GuidanceConfig)
    failures: FailureConfig = Field(default_factory=FailureConfig)
    termination: TerminationConfig = Field(default_factory=TerminationConfig)

    model_config = ConfigDict(frozen=True)


# ──────────────────────────────────────────────────────────────
# Simulation state
# ──────────────────────────────────────────────────────────────


class Vec3Model(BaseModel):
    """3D vector for serialization."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    model_config = ConfigDict(frozen=True)


class StageState(BaseModel):
    """Per-stage state."""
    index: int
    status: StageStatus
    propellant_remaining_kg: float = Field(ge=0)
    ignition_time_s: float | None = None
    cutoff_time_s: float | None = None
    separation_time_s: float | None = None
    propellant_fraction: float = Field(ge=0, le=1)

    model_config = ConfigDict(frozen=True)


class Attitude(BaseModel):
    """Commanded attitude."""
    pitch_rad: float
    yaw_rad: float
    roll_rad: float = 0.0

    model_config = ConfigDict(frozen=True)


class OrbitalElements(BaseModel):
    """Classical Keplerian orbital elements."""
    semi_major_axis_m: float
    eccentricity: float
    inclination_rad: float
    raan_rad: float
    argument_of_periapsis_rad: float
    true_anomaly_rad: float
    periapsis_altitude_m: float
    apoapsis_altitude_m: float
    period_s: float
    is_stable_orbit: bool

    model_config = ConfigDict(frozen=True)


# ──────────────────────────────────────────────────────────────
# Telemetry
# ──────────────────────────────────────────────────────────────


class TelemetryPoint(BaseModel):
    """
    One telemetry sample. Every field is a primitive — no nesting.
    Maps directly to a database row or chart series.
    """
    t: float

    # Position and motion
    altitude_m: float = 0.0
    downrange_m: float = 0.0
    position_x_m: float = 0.0
    position_y_m: float = 0.0
    position_z_m: float = 0.0
    speed_ms: float = 0.0
    vertical_speed_ms: float = 0.0
    horizontal_speed_ms: float = 0.0
    acceleration_ms2: float = 0.0
    g_load_g: float = 0.0

    # Mass and propulsion
    mass_kg: float = 0.0
    fuel_remaining_kg: float = 0.0
    fuel_fraction: float = 0.0
    thrust_N: float = 0.0
    mass_flow_kgs: float = 0.0
    twr: float = 0.0

    # Atmosphere and aerodynamics
    drag_N: float = 0.0
    dynamic_pressure_Pa: float = 0.0
    mach: float = 0.0
    air_density_kgm3: float = 0.0
    ambient_pressure_Pa: float = 0.0

    # Attitude
    pitch_rad: float = 0.0
    yaw_rad: float = 0.0
    angle_of_attack_rad: float = 0.0

    # Orbital state
    semi_major_axis_m: float = 0.0
    eccentricity: float = 0.0
    periapsis_altitude_m: float = 0.0
    apoapsis_altitude_m: float = 0.0
    inclination_rad: float = 0.0
    in_orbit: bool = False

    # Discrete state
    stage: int = 0
    stage_status: StageStatus = StageStatus.STOWED
    engine_on: bool = False
    mission_state: MissionState = MissionState.PREPARATION
    phase: FlightPhase = FlightPhase.PRELAUNCH

    model_config = ConfigDict(frozen=True)


# ──────────────────────────────────────────────────────────────
# Events and failures
# ──────────────────────────────────────────────────────────────


class FailureDetail(BaseModel):
    """Complete record of one failure occurrence."""
    id: str
    mode_id: str
    subsystem: FailureSubsystem
    failure_mode: str
    severity: EventSeverity
    t: float
    stage_index: int | None = None
    trigger_condition: str
    measured_value: float
    threshold_value: float
    unit: str
    trigger_state: dict[str, float]
    contributing_factors: list[str]
    consequence: str
    educational_explanation: str
    recommended_fix: str
    related_lessons: list[str]
    is_terminal: bool

    model_config = ConfigDict(frozen=True)


class SimEvent(BaseModel):
    """A significant moment during flight."""
    t: float
    type: str
    severity: EventSeverity
    description: str
    data: dict[str, float | str | bool] = Field(default_factory=dict)
    failure: FailureDetail | None = None

    model_config = ConfigDict(frozen=True)


# ──────────────────────────────────────────────────────────────
# Simulation result
# ──────────────────────────────────────────────────────────────


class SimSummary(BaseModel):
    """Aggregate statistics for a completed run."""
    max_altitude_m: float = 0.0
    max_speed_ms: float = 0.0
    max_acceleration_g: float = 0.0
    max_dynamic_pressure_Pa: float = 0.0
    max_q_altitude_m: float = 0.0
    max_mach: float = 0.0
    flight_time_s: float = 0.0
    apogee_time_s: float = 0.0
    max_downrange_m: float = 0.0
    impact_speed_ms: float | None = None
    stages_separated: int = 0
    propellant_used_kg: float = 0.0
    delta_v_achieved_ms: float = 0.0
    delta_v_ideal_ms: float = 0.0
    gravity_loss_ms: float = 0.0
    drag_loss_ms: float = 0.0

    model_config = ConfigDict(frozen=True)


class SimResult(BaseModel):
    """The complete result of a finished run."""
    success: bool
    outcome: SimOutcome
    final_state: MissionState
    termination_reason: str
    telemetry: list[TelemetryPoint]
    events: list[SimEvent]
    failures: list[FailureDetail]
    summary: SimSummary
    total_steps: int
    flight_time_s: float

    model_config = ConfigDict(frozen=True)
