"""
Flight-physics regression tests for the Python simulation engine.

These exist because the engine that shipped with the first prototype scaffolding
passed all 46 of its tests while being physically wrong: it divided by mass
twice, modelled no gravity, no drag, no staging, and no orbital mechanics. Every
one of those tests asserted plumbing — shapes, enums, serialisation — and none
asserted that the vehicle obeyed Newton.

Each test here fails against that old engine. Read them as the specification of
what "the simulation is real" means.
"""

from __future__ import annotations

import math

import pytest

from simulation.contracts import (
    EnvironmentConfig,
    GuidanceConfig,
    GuidanceMode,
    IntegratorMethod,
    LaunchSite,
    MissionConfig,
    MissionTarget,
    MissionType,
    MissionState,
    SimConfig,
    SimSettings,
    Stage,
    TerminationConfig,
    Vehicle,
)
from simulation.engine.runner import run_simulation
from simulation.models.constants import G0, R_EARTH

# ──────────────────────────────────────────────────────────────
# Fixtures — small, explicit vehicles rather than a component registry
# ──────────────────────────────────────────────────────────────


# Deliberately modest defaults: a 4:1 mass ratio at constant thrust peaks near
# 8 g, which stays inside the 15 g detection threshold. An earlier draft used a
# 6:1 ratio and pulled 34 g at burnout — the engine correctly flagged it, but a
# vehicle that fails by construction makes a poor baseline for "healthy flight"
# tests.
def _stage(
    *,
    number=0,
    dry=1500.0,
    propellant=4500.0,
    thrust_vac=120_000.0,
    thrust_sl=110_000.0,
    isp_vac=300.0,
    isp_sl=270.0,
    ignition_delay=0.0,
    separation_delay=0.5,
    can_fire=True,
):
    mdot = thrust_vac / (isp_vac * G0)
    return Stage(
        stage_number=number,
        name=f"Stage {number + 1}",
        dry_mass_kg=dry,
        propellant_mass_kg=propellant,
        thrust_vacuum_N=thrust_vac,
        thrust_sea_level_N=thrust_sl,
        isp_vacuum_s=isp_vac,
        isp_sea_level_s=isp_sl,
        mass_flow_rate_kgs=mdot,
        burn_time_s=propellant / mdot if mdot else 0.0,
        ignition_delay_s=ignition_delay,
        separation_delay_s=separation_delay,
        can_fire=can_fire,
    )


def _vehicle(stages=None, **kw):
    stages = stages or [_stage()]
    launch_mass = sum(s.dry_mass_kg + s.propellant_mass_kg for s in stages)
    defaults = dict(
        name="Test Vehicle",
        design_id="test",
        stages=stages,
        payload_mass_kg=0.0,
        launch_mass_kg=launch_mass,
        length_m=20.0,
        diameter_m=2.0,
        reference_area_m2=math.pi,
        drag_coefficient=0.3,
    )
    defaults.update(kw)
    return Vehicle(**defaults)


def _config(vehicle=None, *, target_km=100.0, guidance=None, settings=None, **kw):
    return SimConfig(
        vehicle=vehicle or _vehicle(),
        mission=MissionConfig(
            name="Test",
            objective=f"Reach {target_km} km",
            target=MissionTarget(
                type=MissionType.SUBORBITAL, target_altitude_km=target_km
            ),
            launch_site=LaunchSite(
                name="Test Pad", latitude_deg=28.5, longitude_deg=-80.6, altitude_m=0.0
            ),
            environment=EnvironmentConfig(),
        ),
        guidance=guidance
        or GuidanceConfig(mode=GuidanceMode.VERTICAL, cutoff_on_target_orbit=False),
        # Long enough for a high ballistic arc to come all the way back down;
        # the descent is half the point of these tests.
        settings=settings or SimSettings(max_time_s=3000.0),
        **kw,
    )


# ──────────────────────────────────────────────────────────────
# Gravity — the model that was entirely absent
# ──────────────────────────────────────────────────────────────


class TestGravityActsOnTheVehicle:
    def test_an_unpowered_vehicle_never_leaves_the_pad(self):
        """With no thrust there is nothing to lift the vehicle."""
        vehicle = _vehicle([_stage(thrust_vac=0.0, thrust_sl=0.0, can_fire=False)])
        result = run_simulation(_config(vehicle))
        assert result.summary.max_altitude_m < 1.0

    def test_a_ballistic_vehicle_comes_back_down(self):
        """What goes up must come down. The old engine's vehicles never fell."""
        result = run_simulation(_config(target_km=500.0))

        assert result.summary.max_altitude_m > 1000.0, "should actually fly"
        assert result.final_state == MissionState.SURFACE
        # It reached apogee strictly before the flight ended, i.e. it descended.
        assert result.summary.apogee_time_s < result.flight_time_s

    def test_apogee_is_followed_by_descent_in_the_telemetry(self):
        result = run_simulation(_config(target_km=500.0))
        altitudes = [p.altitude_m for p in result.telemetry]
        peak = max(range(len(altitudes)), key=lambda i: altitudes[i])

        assert peak > 0, "peak should not be the first sample"
        assert peak < len(altitudes) - 1, "peak should not be the last sample"
        assert altitudes[-1] < altitudes[peak], "vehicle must come down"

    def test_gravity_loss_is_positive_and_physically_sized(self):
        """A vertical ascent pays roughly g per second of powered flight."""
        result = run_simulation(_config(target_km=500.0))
        assert result.summary.gravity_loss_ms > 0.0
        # Loose bound: the loss cannot exceed g0 times the whole flight time.
        assert result.summary.gravity_loss_ms < G0 * result.flight_time_s


# ──────────────────────────────────────────────────────────────
# Acceleration — the double mass division
# ──────────────────────────────────────────────────────────────


class TestAccelerationHasCorrectUnits:
    def test_initial_acceleration_matches_thrust_over_mass_minus_g(self):
        """
        a = T/m - g at liftoff.

        This is the test that fails hardest against the old engine, which
        computed T/m/m and so produced an "acceleration" that scaled as the
        inverse square of mass.
        """
        vehicle = _vehicle([_stage(dry=1500.0, propellant=4500.0, thrust_sl=110_000.0)])
        result = run_simulation(_config(vehicle))

        # Sample shortly after liftoff, before much propellant has burned.
        early = next(p for p in result.telemetry if p.t > 0.2)
        expected = 110_000.0 / 6000.0 - G0  # ~8.5 m/s²

        assert early.acceleration_ms2 == pytest.approx(expected, rel=0.10)

    def test_doubling_mass_roughly_halves_the_specific_force(self):
        """
        Load factor is T/m, so twice the mass gives half the g-load.

        Under a T/m/m bug the ratio would be 4, not 2.
        """
        light = run_simulation(_config(_vehicle([_stage(dry=1500.0, propellant=4500.0)])))
        heavy = run_simulation(_config(_vehicle([_stage(dry=3000.0, propellant=9000.0)])))

        a_light = next(p for p in light.telemetry if p.t > 0.2).g_load_g
        a_heavy = next(p for p in heavy.telemetry if p.t > 0.2).g_load_g

        assert a_light / a_heavy == pytest.approx(2.0, rel=0.05)

    def test_g_load_excludes_gravity(self):
        """Load factor is what an accelerometer reads: T and D only, not weight."""
        vehicle = _vehicle([_stage(dry=1500.0, propellant=4500.0, thrust_sl=110_000.0)])
        result = run_simulation(_config(vehicle))
        early = next(p for p in result.telemetry if p.t > 0.2)

        expected_g = (early.thrust_N + early.drag_N) / early.mass_kg / G0
        assert early.g_load_g == pytest.approx(expected_g, rel=1e-6)


# ──────────────────────────────────────────────────────────────
# Mass flow
# ──────────────────────────────────────────────────────────────


class TestMassDecreasesCorrectly:
    def test_mass_falls_monotonically_while_burning(self):
        result = run_simulation(_config())
        burning = [p for p in result.telemetry if p.engine_on and p.t > 0]
        assert len(burning) > 5

        for earlier, later in zip(burning, burning[1:]):
            assert later.mass_kg <= earlier.mass_kg + 1e-6

    def test_propellant_consumed_matches_isp_and_burn_time(self):
        """mdot = T/(Isp*g0), so the propellant load sets the burn time.

        Sea-level and vacuum figures are set equal so altitude compensation is
        a no-op: otherwise the burn stretches as the vehicle climbs into
        thinner air and gains Isp, and the closed-form answer no longer applies.
        """
        stage = _stage(
            propellant=5000.0,
            thrust_vac=200_000.0,
            thrust_sl=200_000.0,
            isp_vac=300.0,
            isp_sl=300.0,
        )
        result = run_simulation(_config(_vehicle([stage])))

        expected_mdot = 200_000.0 / (300.0 * G0)
        expected_burn_s = 5000.0 / expected_mdot

        cutoff = next(
            (e for e in result.events if e.type == "STAGE_CUTOFF"), None
        )
        assert cutoff is not None, "the stage should run out of propellant"
        assert cutoff.t == pytest.approx(expected_burn_s, rel=0.05)

    def test_all_propellant_is_accounted_for(self):
        result = run_simulation(_config())
        assert result.summary.propellant_used_kg == pytest.approx(4500.0, rel=0.01)

    def test_propellant_used_never_exceeds_propellant_loaded(self):
        """Guards the 'launch mass minus final mass' accounting bug, which
        counted jettisoned stage structure as burned propellant."""
        stages = [_stage(number=0, propellant=4500.0), _stage(number=1, propellant=2000.0)]
        result = run_simulation(_config(_vehicle(stages), target_km=200.0))
        assert result.summary.propellant_used_kg <= 6500.0 + 1e-6

    def test_fuel_fraction_tracks_remaining_propellant(self):
        """The old engine hardcoded fuel_fraction to 1.0 while draining mass."""
        result = run_simulation(_config())
        fractions = [p.fuel_fraction for p in result.telemetry if p.t > 0]
        assert fractions[0] > fractions[-1]
        assert min(fractions) < 0.5


# ──────────────────────────────────────────────────────────────
# Atmosphere and drag
# ──────────────────────────────────────────────────────────────


class TestAtmosphereAndDrag:
    def test_drag_is_nonzero_in_the_lower_atmosphere(self):
        """The old engine hardcoded drag_N to 0.0."""
        result = run_simulation(_config())
        low = [p for p in result.telemetry if 0 < p.altitude_m < 20_000 and p.speed_ms > 50]
        assert low, "vehicle should pass through the lower atmosphere with speed"
        assert any(p.drag_N > 0 for p in low)

    def test_air_density_falls_with_altitude(self):
        result = run_simulation(_config(target_km=500.0))
        samples = sorted(
            (p for p in result.telemetry if p.altitude_m > 0),
            key=lambda p: p.altitude_m,
        )
        assert samples[0].air_density_kgm3 > samples[-1].air_density_kgm3

    def test_dynamic_pressure_peaks_inside_the_atmosphere(self):
        """Max-Q is a real event, not a hardcoded zero."""
        result = run_simulation(_config(target_km=500.0))
        assert result.summary.max_dynamic_pressure_Pa > 1000.0
        assert 0 <= result.summary.max_q_altitude_m < 100_000

    def test_drag_opposes_motion_and_costs_velocity(self):
        result = run_simulation(_config(target_km=500.0))
        assert result.summary.drag_loss_ms > 0.0


# ──────────────────────────────────────────────────────────────
# Staging
# ──────────────────────────────────────────────────────────────


class TestStaging:
    def test_a_two_stage_vehicle_separates(self):
        """The old engine only ever read stages[0] and never separated."""
        stages = [_stage(number=0, propellant=5000.0), _stage(number=1, propellant=2000.0)]
        result = run_simulation(_config(_vehicle(stages), target_km=200.0))

        assert result.summary.stages_separated == 1
        assert any(e.type == "STAGE_SEPARATED" for e in result.events)

    def test_separation_drops_the_spent_stage_mass(self):
        stages = [
            _stage(number=0, dry=1000.0, propellant=5000.0),
            _stage(number=1, dry=500.0, propellant=2000.0),
        ]
        result = run_simulation(_config(_vehicle(stages), target_km=200.0))

        sep = next(e for e in result.events if e.type == "STAGE_SEPARATED")
        before = [p for p in result.telemetry if p.t < sep.t]
        after = [p for p in result.telemetry if p.t > sep.t]

        assert before and after
        # The 1000 kg of first-stage structure is gone.
        assert before[-1].mass_kg - after[0].mass_kg == pytest.approx(1000.0, abs=50.0)

    def test_the_upper_stage_ignites_after_separation(self):
        stages = [_stage(number=0, propellant=5000.0), _stage(number=1, propellant=2000.0)]
        result = run_simulation(_config(_vehicle(stages), target_km=200.0))

        ignitions = [e for e in result.events if e.type == "STAGE_IGNITION"]
        assert len(ignitions) == 2
        assert ignitions[1].t > ignitions[0].t

    def test_a_two_stage_vehicle_outperforms_its_first_stage_alone(self):
        """Staging exists because dropping dead mass buys altitude."""
        two = _vehicle(
            [_stage(number=0, propellant=5000.0), _stage(number=1, propellant=2000.0)]
        )
        one = _vehicle([_stage(number=0, propellant=5000.0)])

        high = run_simulation(_config(two, target_km=200.0)).summary.max_altitude_m
        low = run_simulation(_config(one, target_km=200.0)).summary.max_altitude_m
        assert high > low


# ──────────────────────────────────────────────────────────────
# Orbital mechanics
# ──────────────────────────────────────────────────────────────


class TestOrbit:
    def _orbital_vehicle(self):
        return _vehicle(
            [
                _stage(
                    number=0,
                    dry=10_820.0,
                    propellant=96_000.0,
                    thrust_vac=2_400_000.0,
                    thrust_sl=2_100_000.0,
                    isp_vac=311.0,
                    isp_sl=272.0,
                ),
                _stage(
                    number=1,
                    dry=3683.0,
                    propellant=17_000.0,
                    thrust_vac=180_000.0,
                    thrust_sl=110_000.0,
                    isp_vac=440.0,
                    isp_sl=269.0,
                ),
            ],
            reference_area_m2=math.pi,
            drag_coefficient=0.29,
        )

    def _orbital_config(self):
        return _config(
            self._orbital_vehicle(),
            target_km=200.0,
            guidance=GuidanceConfig(
                mode=GuidanceMode.PITCH_PROGRAM,
                launch_azimuth_deg=90.0,
                pitchover_altitude_m=200.0,
                pitch_program_end_altitude_m=80_000.0,
                final_pitch_deg=0.0,
            ),
            settings=SimSettings(max_time_s=2000.0),
        )

    def test_a_launch_vehicle_reaches_orbit(self):
        result = run_simulation(self._orbital_config())
        assert result.summary.max_altitude_m > 150_000
        assert any(p.in_orbit for p in result.telemetry)

    def test_orbital_elements_are_reported_above_the_karman_line(self):
        """The old engine hardcoded every orbital field to zero."""
        result = run_simulation(self._orbital_config())
        high = [p for p in result.telemetry if p.altitude_m > 150_000]
        assert high
        assert any(p.semi_major_axis_m > R_EARTH for p in high)

    def test_orbital_speed_is_near_the_circular_value(self):
        """At 200 km, circular speed is about 7.8 km/s."""
        result = run_simulation(self._orbital_config())
        in_orbit = [p for p in result.telemetry if p.in_orbit]
        assert in_orbit
        assert 6500 < max(p.speed_ms for p in in_orbit) < 11_000

    def test_a_vertical_launch_does_not_reach_orbit(self):
        """Orbit is a sideways problem — straight up always comes back.

        The same vehicle that reaches orbit on a pitch program never does on a
        vertical ascent, however much propellant it has: orbit needs horizontal
        speed, and a vertical climb builds none.
        """
        config = self._orbital_config().model_copy(
            update={
                "guidance": GuidanceConfig(
                    mode=GuidanceMode.VERTICAL, cutoff_on_target_orbit=False
                )
            }
        )
        result = run_simulation(config)

        assert not any(p.in_orbit for p in result.telemetry)
        # No horizontal velocity is ever built, which is precisely why it
        # cannot orbit however high it climbs.
        assert result.summary.max_downrange_m < 1000.0
        assert all(p.horizontal_speed_ms < 10.0 for p in result.telemetry)


# ──────────────────────────────────────────────────────────────
# Failures
# ──────────────────────────────────────────────────────────────


class TestFailures:
    def test_an_underpowered_vehicle_fails_to_lift_off(self):
        """TWR below 1 is a real, detectable, educational failure."""
        vehicle = _vehicle(
            [_stage(dry=5000.0, propellant=5000.0, thrust_vac=20_000.0, thrust_sl=20_000.0)]
        )
        result = run_simulation(_config(vehicle))

        assert result.failures, "an underpowered vehicle should fail"
        assert any(f.mode_id == "INSUFFICIENT_THRUST" for f in result.failures)
        assert result.final_state == MissionState.FAILURE

    def test_a_failure_carries_machine_readable_fields(self):
        vehicle = _vehicle(
            [_stage(dry=5000.0, propellant=5000.0, thrust_vac=20_000.0, thrust_sl=20_000.0)]
        )
        failure = run_simulation(_config(vehicle)).failures[0]

        assert failure.mode_id
        assert failure.t >= 0
        assert failure.unit
        assert failure.measured_value != failure.threshold_value
        assert failure.educational_explanation
        assert failure.recommended_fix

    def test_a_healthy_vehicle_reports_no_failures_during_ascent(self):
        """
        Ascent only, on purpose.

        This vehicle has no heat shield and no parachute, so falling back from
        a 500 km apogee genuinely does exceed the g-load limit on re-entry. The
        engine is right to flag that; what "healthy" means here is that nothing
        goes wrong on the way up.
        """
        result = run_simulation(_config())
        apogee_t = result.summary.apogee_time_s
        ascent_failures = [f for f in result.failures if f.t <= apogee_t]
        assert ascent_failures == []

    def test_an_injected_failure_fires_at_its_scheduled_time(self):
        from simulation.contracts import FailureConfig

        config = _config().model_copy(
            update={
                "failures": FailureConfig(
                    injections=[
                        {
                            "mode_id": "ENGINE_SHUTDOWN",
                            "t": 5.0,
                            "subsystem": "propulsion",
                            "is_terminal": False,
                        }
                    ]
                )
            }
        )
        result = run_simulation(config)

        fired = [f for f in result.failures if f.mode_id == "ENGINE_SHUTDOWN"]
        assert len(fired) == 1
        assert fired[0].t == pytest.approx(5.0, abs=0.2)

    def test_an_engine_shutdown_actually_stops_the_thrust(self):
        """A failure that changes nothing is decoration, not simulation."""
        from simulation.contracts import FailureConfig

        config = _config(target_km=500.0).model_copy(
            update={
                "failures": FailureConfig(
                    injections=[{"mode_id": "ENGINE_SHUTDOWN", "t": 5.0}]
                )
            }
        )
        result = run_simulation(config)

        after = [p for p in result.telemetry if p.t > 6.0]
        assert after
        assert all(p.thrust_N == 0.0 for p in after)


# ──────────────────────────────────────────────────────────────
# Determinism and integrator
# ──────────────────────────────────────────────────────────────


class TestDeterminism:
    def test_the_same_config_produces_identical_telemetry(self):
        config = _config(target_km=500.0)
        a = run_simulation(config)
        b = run_simulation(config)

        assert len(a.telemetry) == len(b.telemetry)
        for pa, pb in zip(a.telemetry, b.telemetry):
            assert pa.t == pb.t
            assert pa.altitude_m == pb.altitude_m
            assert pa.speed_ms == pb.speed_ms

    def test_the_same_config_produces_identical_events(self):
        config = _config(target_km=500.0)
        a = run_simulation(config)
        b = run_simulation(config)
        assert [(e.t, e.type) for e in a.events] == [(e.t, e.type) for e in b.events]

    def test_rk4_and_euler_disagree_measurably(self):
        """If the integrator choice changed nothing, it would not be integrating."""
        rk4 = run_simulation(
            _config(target_km=500.0, settings=SimSettings(integrator=IntegratorMethod.RK4))
        )
        euler = run_simulation(
            _config(
                target_km=500.0, settings=SimSettings(integrator=IntegratorMethod.EULER)
            )
        )
        assert rk4.summary.max_altitude_m != euler.summary.max_altitude_m


# ──────────────────────────────────────────────────────────────
# Mission state machine
# ──────────────────────────────────────────────────────────────


class TestMissionStates:
    def test_a_normal_flight_walks_through_the_expected_states(self):
        result = run_simulation(_config(target_km=500.0))
        seen = [e.type for e in result.events if e.type.startswith("STATE_")]

        for expected in (
            "STATE_COUNTDOWN",
            "STATE_IGNITION",
            "STATE_LIFTOFF",
            "STATE_ASCENT",
            "STATE_ENGINE_CUTOFF",
        ):
            assert expected in seen, f"{expected} missing from {seen}"

    def test_state_events_are_ordered_in_time(self):
        result = run_simulation(_config(target_km=500.0))
        times = [e.t for e in result.events]
        assert times == sorted(times)

    def test_a_mission_state_event_is_distinct_from_a_hardware_event(self):
        """STATE_IGNITION (phase) and STAGE_IGNITION (an engine lit) are
        different facts and must not share an event type."""
        result = run_simulation(_config())
        types = {e.type for e in result.events}
        assert "STATE_IGNITION" in types
        assert "STAGE_IGNITION" in types
