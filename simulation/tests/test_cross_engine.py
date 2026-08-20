"""
Cross-engine agreement: the Python engine against the TypeScript engine.

LostIntoSpacE has two simulation implementations. The TypeScript engine
(``packages/simulation-engine``) has 570 tests and predates the Python one; the
Python engine is the one served over the API. They must not silently drift
apart, so this suite flies *the same vehicle and mission* through the Python
engine and compares the answer with a recorded TypeScript run.

The fixtures in ``fixtures/`` were produced by the TypeScript engine itself
(``runSimulation`` over its own reference designs) and are checked in so this
test needs no Node toolchain.

What is compared, and what is not
---------------------------------
Physics is compared: altitude, speed, load factor, dynamic pressure, Mach,
propellant consumption, and the velocity-loss budget.

Guidance *policy* is not. The orbital fixture disables
``cutoff_on_target_orbit`` for the comparison, because the two engines make
different — and independently defensible — choices about when to stop burning.
Left enabled, the Python engine cuts off on reaching a 200 km orbit at
essentially exact circular speed and keeps its remaining propellant; the
recorded TypeScript run burns to depletion and ends up markedly elliptical.
That is a mission-policy difference, not a disagreement about physics, and
folding it into this comparison would hide the physics signal. The cutoff
behaviour itself is tested separately, below.

Tolerance
---------
2% on trajectory-scale quantities. The engines share model *definitions* but
not their step sequencing, so exact agreement is neither expected nor required;
what matters is that neither drifts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simulation.contracts import SimConfig
from simulation.engine.runner import run_simulation

FIXTURES = Path(__file__).parent / "fixtures"

#: Trajectory-scale quantities must agree this closely. Dimensionless fraction.
TOLERANCE = 0.02


def _load(name: str):
    config = SimConfig.model_validate(json.loads((FIXTURES / f"{name}.config.json").read_text()))
    expected = json.loads((FIXTURES / f"{name}.ts-result.json").read_text())
    return config, expected["summary"]


def _burn_to_depletion(config: SimConfig) -> SimConfig:
    """Disable guidance cutoff so both engines fly the same propellant policy."""
    return config.model_copy(
        update={"guidance": config.guidance.model_copy(update={"cutoff_on_target_orbit": False})}
    )


@pytest.fixture(scope="module")
def orbital():
    config, expected = _load("orbital")
    return run_simulation(_burn_to_depletion(config)).summary, expected


@pytest.fixture(scope="module")
def suborbital():
    config, expected = _load("suborbital")
    return run_simulation(config).summary, expected


def _assert_close(actual: float, expected: float, label: str, tolerance=TOLERANCE):
    assert actual == pytest.approx(expected, rel=tolerance), (
        f"{label}: Python {actual:,.2f} vs TypeScript {expected:,.2f} "
        f"({(actual - expected) / expected * 100:+.1f}%)"
    )


class TestOrbitalAscentAgrees:
    """A two-stage 127 t launcher flying a pitch program to 200 km."""

    def test_max_altitude(self, orbital):
        py, ts = orbital
        _assert_close(py.max_altitude_m, ts["maxAltitude_m"], "max altitude")

    def test_max_speed(self, orbital):
        py, ts = orbital
        _assert_close(py.max_speed_ms, ts["maxSpeed_ms"], "max speed")

    def test_max_acceleration(self, orbital):
        py, ts = orbital
        _assert_close(py.max_acceleration_g, ts["maxAcceleration_g"], "max g-load")

    def test_max_dynamic_pressure(self, orbital):
        py, ts = orbital
        _assert_close(py.max_dynamic_pressure_Pa, ts["maxDynamicPressure_Pa"], "max q")

    def test_max_q_altitude(self, orbital):
        py, ts = orbital
        _assert_close(py.max_q_altitude_m, ts["maxQAltitude_m"], "max-q altitude")

    def test_max_mach(self, orbital):
        py, ts = orbital
        _assert_close(py.max_mach, ts["maxMach"], "max Mach")

    def test_propellant_used(self, orbital):
        py, ts = orbital
        _assert_close(py.propellant_used_kg, ts["propellantUsed_kg"], "propellant used")

    def test_ideal_delta_v(self, orbital):
        """Tsiolkovsky is closed-form; the two engines must agree exactly."""
        py, ts = orbital
        _assert_close(py.delta_v_ideal_ms, ts["deltaVIdeal_ms"], "ideal delta-v", 1e-6)

    def test_gravity_loss(self, orbital):
        py, ts = orbital
        _assert_close(py.gravity_loss_ms, ts["gravityLoss_ms"], "gravity loss")

    def test_drag_loss(self, orbital):
        py, ts = orbital
        _assert_close(py.drag_loss_ms, ts["dragLoss_ms"], "drag loss")

    def test_staging(self, orbital):
        py, ts = orbital
        assert py.stages_separated == ts["stagesSeparated"]


class TestSuborbitalHopAgrees:
    """A single-stage solid sounding rocket flying vertically."""

    def test_max_altitude(self, suborbital):
        py, ts = suborbital
        _assert_close(py.max_altitude_m, ts["maxAltitude_m"], "max altitude")

    def test_max_speed(self, suborbital):
        py, ts = suborbital
        _assert_close(py.max_speed_ms, ts["maxSpeed_ms"], "max speed")

    def test_max_acceleration(self, suborbital):
        py, ts = suborbital
        _assert_close(py.max_acceleration_g, ts["maxAcceleration_g"], "max g-load")

    def test_max_dynamic_pressure(self, suborbital):
        py, ts = suborbital
        _assert_close(py.max_dynamic_pressure_Pa, ts["maxDynamicPressure_Pa"], "max q")

    def test_max_mach(self, suborbital):
        py, ts = suborbital
        _assert_close(py.max_mach, ts["maxMach"], "max Mach")

    def test_flight_time(self, suborbital):
        py, ts = suborbital
        _assert_close(py.flight_time_s, ts["flightTime_s"], "flight time")

    def test_propellant_used(self, suborbital):
        py, ts = suborbital
        _assert_close(py.propellant_used_kg, ts["propellantUsed_kg"], "propellant used")

    def test_drag_loss(self, suborbital):
        py, ts = suborbital
        _assert_close(py.drag_loss_ms, ts["dragLoss_ms"], "drag loss")

    def test_gravity_loss(self, suborbital):
        py, ts = suborbital
        _assert_close(py.gravity_loss_ms, ts["gravityLoss_ms"], "gravity loss")


@pytest.fixture(scope="module")
def cutoff_result():
    config, _ = _load("orbital")
    assert config.guidance.cutoff_on_target_orbit, "fixture should have it enabled"
    return run_simulation(config)


class TestGuidanceCutoffOnTargetOrbit:
    """The policy deliberately excluded from the comparison above."""

    def test_it_stops_burning_before_the_tanks_run_dry(self, cutoff_result):
        assert any(e.type == "GUIDANCE_CUTOFF" for e in cutoff_result.events)

    def test_it_arrives_at_roughly_circular_speed(self, cutoff_result):
        """
        Circular speed at 200 km is about 7.78 km/s.

        Burning to depletion instead overshoots to nearly 9.7 km/s, which is a
        strongly elliptical orbit rather than the circular one the mission
        asked for.
        """
        assert 7_400 < cutoff_result.summary.max_speed_ms < 8_200

    def test_it_keeps_the_unburned_propellant(self, cutoff_result):
        config, _ = _load("orbital")
        loaded = sum(s.propellant_mass_kg for s in config.vehicle.stages)
        assert cutoff_result.summary.propellant_used_kg < loaded

    def test_it_still_reaches_orbit(self, cutoff_result):
        assert any(p.in_orbit for p in cutoff_result.telemetry)
