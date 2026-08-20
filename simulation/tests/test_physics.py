"""
Tests for physics models — cross-validated against the TypeScript engine.

Reference values are taken from the TypeScript test suite in
packages/simulation-engine/tests/physics/ to ensure numerical agreement.
"""

from __future__ import annotations

import math
import pytest

from simulation.models.constants import (
    G0, R_EARTH, MU_EARTH, T0, P0, RHO0, A0,
    G_GRAVITATIONAL, M_EARTH, R_UNIVERSAL, M_AIR,
    GAMMA_AIR, R_AIR, DEG_TO_RAD,
)
from simulation.models.gravity import (
    Vec3, vec3, magnitude, scale, add, sub, dot, cross, normalize,
    gravity_scalar, gravity_acceleration_central,
)
from simulation.models.atmosphere import (
    atmosphere, mach_number, dynamic_pressure,
)
from simulation.models.drag import (
    effective_drag_coefficient, drag_force,
)
from simulation.models.thrust import (
    thrust_at_pressure, mass_flow_rate, delta_v, burn_time, thrust_to_weight,
)


# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

class TestConstants:
    """Verify constants match NIST/WGS-84/USSA-1976 reference values."""

    def test_standard_gravity(self) -> None:
        assert G0 == pytest.approx(9.80665)

    def test_gravitational_constant(self) -> None:
        assert G_GRAVITATIONAL == pytest.approx(6.67430e-11, rel=1e-4)

    def test_earth_radius(self) -> None:
        assert R_EARTH == pytest.approx(6_371_000.0)

    def test_earth_mass(self) -> None:
        assert M_EARTH == pytest.approx(5.972e24, rel=1e-3)

    def test_sea_level_temperature(self) -> None:
        assert T0 == pytest.approx(288.15)

    def test_sea_level_pressure(self) -> None:
        assert P0 == pytest.approx(101_325.0)

    def test_sea_level_density(self) -> None:
        assert RHO0 == pytest.approx(1.225)

    def test_speed_of_sound_sea_level(self) -> None:
        assert A0 == pytest.approx(340.3, rel=1e-3)


# ──────────────────────────────────────────────────────────────
# Vec3
# ──────────────────────────────────────────────────────────────

class TestVec3:
    """Verify vector operations."""

    def test_magnitude(self) -> None:
        assert magnitude(Vec3(3, 4, 0)) == pytest.approx(5.0)

    def test_magnitude_3d(self) -> None:
        assert magnitude(Vec3(1, 2, 2)) == pytest.approx(3.0)

    def test_add(self) -> None:
        result = add(Vec3(1, 2, 3), Vec3(4, 5, 6))
        assert result == Vec3(5, 7, 9)

    def test_sub(self) -> None:
        result = sub(Vec3(4, 5, 6), Vec3(1, 2, 3))
        assert result == Vec3(3, 3, 3)

    def test_scale(self) -> None:
        result = scale(Vec3(1, 2, 3), 2)
        assert result == Vec3(2, 4, 6)

    def test_dot(self) -> None:
        assert dot(Vec3(1, 0, 0), Vec3(0, 1, 0)) == pytest.approx(0.0)
        assert dot(Vec3(1, 2, 3), Vec3(4, 5, 6)) == pytest.approx(32.0)

    def test_cross(self) -> None:
        result = cross(Vec3(1, 0, 0), Vec3(0, 1, 0))
        assert result.x == pytest.approx(0.0)
        assert result.y == pytest.approx(0.0)
        assert result.z == pytest.approx(1.0)

    def test_normalize(self) -> None:
        result = normalize(Vec3(3, 4, 0))
        assert magnitude(result) == pytest.approx(1.0)
        assert result.x == pytest.approx(0.6)
        assert result.y == pytest.approx(0.8)

    def test_normalize_zero(self) -> None:
        result = normalize(Vec3(0, 0, 0))
        assert magnitude(result) == pytest.approx(0.0)


# ──────────────────────────────────────────────────────────────
# Gravity
# ──────────────────────────────────────────────────────────────

class TestGravity:
    """Cross-validate against TS physics/gravity.test.ts."""

    def test_sea_level(self) -> None:
        assert gravity_scalar(0) == pytest.approx(G0)

    def test_decreases_with_altitude(self) -> None:
        g_0 = gravity_scalar(0)
        g_100km = gravity_scalar(100_000)
        g_400km = gravity_scalar(400_000)
        assert g_100km < g_0
        assert g_400km < g_100km

    def test_iss_altitude(self) -> None:
        """At ISS altitude (~408 km), g ≈ 8.67 m/s²."""
        g = gravity_scalar(408_000)
        assert g == pytest.approx(8.67, rel=0.02)

    def test_central_field_points_inward(self) -> None:
        """Acceleration at a point above Earth's centre should point down."""
        pos = Vec3(0, 0, R_EARTH)
        accel = gravity_acceleration_central(pos)
        assert accel.z < 0  # points toward centre
        assert magnitude(accel) == pytest.approx(G0, rel=0.01)

    def test_central_field_magnitude(self) -> None:
        """At the surface, central field ≈ G0."""
        pos = Vec3(R_EARTH, 0, 0)
        accel = gravity_acceleration_central(pos)
        assert magnitude(accel) == pytest.approx(G0, rel=0.01)


# ──────────────────────────────────────────────────────────────
# Atmosphere
# ──────────────────────────────────────────────────────────────

class TestAtmosphere:
    """Cross-validate against TS physics/atmosphere.test.ts and USSA-1976 tables."""

    def test_sea_level(self) -> None:
        atm = atmosphere(0)
        assert atm.temperature_K == pytest.approx(288.15)
        assert atm.pressure_Pa == pytest.approx(101_325, rel=1e-4)
        assert atm.density_kgm3 == pytest.approx(1.225, rel=1e-2)

    def test_tropopause(self) -> None:
        """At 11 km, temperature should be ~216.65 K."""
        atm = atmosphere(11_000)
        assert atm.temperature_K == pytest.approx(216.65, rel=1e-2)
        assert atm.pressure_Pa == pytest.approx(22_632, rel=0.05)

    def test_decreasing_density(self) -> None:
        """Density should decrease with altitude."""
        d0 = atmosphere(0).density_kgm3
        d10 = atmosphere(10_000).density_kgm3
        d30 = atmosphere(30_000).density_kgm3
        assert d10 < d0
        assert d30 < d10

    def test_above_86km(self) -> None:
        """Above 86 km, exponential decay should produce small but positive values."""
        atm = atmosphere(100_000)
        assert atm.density_kgm3 > 0
        assert atm.pressure_Pa > 0
        assert atm.density_kgm3 < atmosphere(80_000).density_kgm3

    def test_negative_altitude_clamp(self) -> None:
        """Below 0 m returns sea level."""
        atm = atmosphere(-100)
        assert atm.temperature_K == pytest.approx(T0)

    def test_mach_number(self) -> None:
        atm = atmosphere(0)
        m = mach_number(340.3, atm)
        assert m == pytest.approx(1.0, rel=1e-2)

    def test_dynamic_pressure(self) -> None:
        q = dynamic_pressure(100.0, 1.225)
        assert q == pytest.approx(6125.0)


# ──────────────────────────────────────────────────────────────
# Drag
# ──────────────────────────────────────────────────────────────

class TestDrag:
    """Cross-validate against TS physics/drag.test.ts."""

    def test_subsonic_coefficient(self) -> None:
        """Below Mach 0.8, Cd is unmodified."""
        assert effective_drag_coefficient(0.5, 0.3) == pytest.approx(0.5)
        assert effective_drag_coefficient(0.5, 0.79) == pytest.approx(0.5)

    def test_transonic_bump(self) -> None:
        """Between 0.8 and 1.2, Cd rises linearly to 2.5x the subsonic value.

        Reference values from machDragFactor in
        packages/simulation-engine/src/physics/drag.ts — the two engines must
        agree, because a weaker transonic rise silently understates max-Q.
        """
        cd_sub = 0.5
        assert effective_drag_coefficient(cd_sub, 1.0) == pytest.approx(cd_sub * 1.75)
        assert effective_drag_coefficient(cd_sub, 1.2) == pytest.approx(cd_sub * 2.5)

    def test_supersonic_decay(self) -> None:
        """Above Mach 1.2, Cd decays linearly toward the hypersonic floor."""
        cd_sub = 0.5
        cd_12 = effective_drag_coefficient(cd_sub, 1.2)
        cd_3 = effective_drag_coefficient(cd_sub, 3.0)
        assert cd_3 < cd_12

    def test_hypersonic_floor(self) -> None:
        """Beyond Mach 5 the multiplier settles at 1.1 and stops falling."""
        cd_sub = 0.5
        assert effective_drag_coefficient(cd_sub, 5.0) == pytest.approx(cd_sub * 1.1)
        assert effective_drag_coefficient(cd_sub, 35.0) == pytest.approx(cd_sub * 1.1)

    def test_drag_anti_parallel(self) -> None:
        """Drag force should oppose the velocity vector."""
        v = Vec3(100, 0, 0)
        d = drag_force(v, 1.225, 0.5, 1.0)
        assert d.x < 0  # opposes eastward velocity
        assert abs(d.y) < 1e-10
        assert abs(d.z) < 1e-10

    def test_drag_zero_velocity(self) -> None:
        d = drag_force(Vec3(0, 0, 0), 1.225, 0.5, 1.0)
        assert magnitude(d) == pytest.approx(0.0)


# ──────────────────────────────────────────────────────────────
# Thrust
# ──────────────────────────────────────────────────────────────

class TestThrust:
    """Cross-validate against TS physics/thrust.test.ts."""

    def test_thrust_at_vacuum(self) -> None:
        t = thrust_at_pressure(300_000, 250_000, 0)
        assert t == pytest.approx(300_000)

    def test_thrust_at_sea_level(self) -> None:
        t = thrust_at_pressure(300_000, 250_000, P0)
        assert t == pytest.approx(250_000)

    def test_mass_flow(self) -> None:
        mdot = mass_flow_rate(250_000, 300)
        expected = 250_000 / (300 * G0)
        assert mdot == pytest.approx(expected, rel=1e-6)

    def test_delta_v(self) -> None:
        """Tsiolkovsky rocket equation: Δv = Isp·g₀·ln(m₀/m_f)."""
        dv = delta_v(300, 10_000, 3_000)
        expected = 300 * G0 * math.log(10_000 / 3_000)
        assert dv == pytest.approx(expected, rel=1e-6)

    def test_delta_v_empty(self) -> None:
        assert delta_v(300, 10_000, 10_000) == pytest.approx(0.0)

    def test_burn_time_calc(self) -> None:
        bt = burn_time(7000, 85)
        assert bt == pytest.approx(7000 / 85, rel=1e-6)

    def test_twr(self) -> None:
        twr = thrust_to_weight(300_000, 20_000)
        expected = 300_000 / (20_000 * G0)
        assert twr == pytest.approx(expected, rel=1e-6)

    def test_twr_exceeds_one(self) -> None:
        """A launchable rocket must have TWR > 1."""
        twr = thrust_to_weight(300_000, 20_000)
        assert twr > 1.0
