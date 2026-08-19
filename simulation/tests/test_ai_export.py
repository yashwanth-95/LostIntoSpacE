from __future__ import annotations

from simulation.contracts import (
    EnvironmentConfig,
    LaunchSite,
    MissionConfig,
    MissionTarget,
    MissionType,
    SimConfig,
    SimSettings,
    Stage,
    Vehicle,
)
from simulation.engine.runner import run_simulation
from simulation.integration.ai_export import build_mission_report


def test_build_mission_report_includes_measurements_and_timeline() -> None:
    stage = Stage(
        stage_number=0,
        name="Core",
        dry_mass_kg=1200.0,
        propellant_mass_kg=3500.0,
        thrust_vacuum_N=120_000.0,
        thrust_sea_level_N=110_000.0,
        isp_vacuum_s=280.0,
        isp_sea_level_s=260.0,
        mass_flow_rate_kgs=35.0,
        burn_time_s=100.0,
        ignition_delay_s=0.0,
        separation_delay_s=0.0,
        can_fire=True,
    )

    vehicle = Vehicle(
        name="Test Rocket",
        design_id="test-rocket",
        stages=[stage],
        payload_mass_kg=100.0,
        launch_mass_kg=1200.0 + 3500.0 + 100.0,
        length_m=18.0,
        diameter_m=1.8,
        reference_area_m2=2.5,
        drag_coefficient=0.35,
        stability_margin_wet_cal=1.2,
        stability_margin_dry_cal=1.5,
        max_axial_load_N=4_000_000.0,
        max_dynamic_pressure_Pa=60_000.0,
    )

    config = SimConfig(
        vehicle=vehicle,
        mission=MissionConfig(
            name="Basic ascent",
            objective="Reach altitude",
            target=MissionTarget(type=MissionType.SUBORBITAL, target_altitude_km=20.0),
            launch_site=LaunchSite(
                name="Launch Site",
                latitude_deg=0.0,
                longitude_deg=0.0,
                altitude_m=0.0,
            ),
            environment=EnvironmentConfig(
                temperature_K=288.15,
                pressure_Pa=101_325.0,
                wind_speed_ms=0.0,
                wind_direction_deg=0.0,
            ),
        ),
        settings=SimSettings(
            max_time_s=30.0,
            dt_powered_s=0.1,
            dt_coast_s=0.5,
            telemetry_sample_interval_s=0.5,
            countdown_s=1.0,
        ),
    )

    result = run_simulation(config)
    report = build_mission_report(result, config)

    assert report.report_version == "1.0.0"
    assert report.measurements
    assert report.timeline
    assert report.delta_v_budget["achieved_ms"] >= 0.0
    assert report.model_limitations.caveat
