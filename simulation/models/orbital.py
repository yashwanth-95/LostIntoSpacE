"""
Orbital state approximation — classical elements from a position/velocity pair.

Ported from packages/simulation-engine/src/physics/orbital.ts.

This is the standard two-body ("Keplerian") solution. Given r and v at one
instant it produces the conic section the vehicle would follow if thrust, drag,
and every perturbation stopped right now. That is what "orbital parameters" in
the telemetry stream mean.

Assumptions
-----------
- Two-body point-mass gravity: no J2, no drag, no third bodies, no thrust.
- Instantaneous ("osculating") elements. During powered flight or inside the
  atmosphere these change every step and should be read as *"the orbit you
  would coast into from here"*, not as a prediction.
- Angles are referenced to the frame the caller supplies. Pass ECI-aligned
  vectors (see :mod:`simulation.models.frames`) or inclination and RAAN are
  meaningless.

Reference: Vallado, *Fundamentals of Astrodynamics and Applications*, section 2.5.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from .constants import MU_EARTH, R_EARTH
from .gravity import Vec3, cross, dot, magnitude, scale, sub, vec3

#: Below this node-vector magnitude an orbit is treated as equatorial, leaving
#: RAAN undefined (reported as 0 by convention).
EQUATORIAL_TOLERANCE = 1e-8

#: Below this eccentricity an orbit is treated as circular, leaving the argument
#: of periapsis undefined (reported as 0 by convention).
CIRCULAR_TOLERANCE = 1e-8


class OrbitalElements(NamedTuple):
    """Classical orbital elements plus the derived quantities a UI wants."""

    #: Semi-major axis. Negative for hyperbolic orbits. Unit: m.
    semi_major_axis_m: float
    #: Eccentricity. 0 = circular, <1 = elliptical, >=1 = escape.
    eccentricity: float
    #: Inclination from the frame's reference plane. Unit: rad, [0, pi].
    inclination_rad: float
    #: Right ascension of the ascending node. Unit: rad, [0, 2pi).
    raan_rad: float
    #: Argument of periapsis. Unit: rad, [0, 2pi).
    argument_of_periapsis_rad: float
    #: True anomaly — angular position from periapsis. Unit: rad, [0, 2pi).
    true_anomaly_rad: float
    #: Periapsis radius from the body centre. Unit: m.
    periapsis_radius_m: float
    #: Apoapsis radius from the body centre. inf for escape orbits. Unit: m.
    apoapsis_radius_m: float
    #: Periapsis altitude. Negative means the orbit intersects the surface. Unit: m.
    periapsis_altitude_m: float
    #: Apoapsis altitude. inf for escape orbits. Unit: m.
    apoapsis_altitude_m: float
    #: Orbital period. inf for parabolic/hyperbolic orbits. Unit: s.
    period_s: float
    #: Specific orbital energy, eps = v^2/2 - mu/r. Unit: J/kg.
    specific_energy_Jkg: float
    #: Specific angular momentum magnitude. Unit: m^2/s.
    specific_angular_momentum_m2s: float
    #: Conic section classification.
    shape: str
    #: Closed and clear of the surface.
    is_stable_orbit: bool


def _safe_acos(x: float) -> float:
    """acos that tolerates floating-point overshoot just outside [-1, 1]."""
    return math.acos(min(1.0, max(-1.0, x)))


def _wrap_two_pi(angle: float) -> float:
    """Wrap an angle into [0, 2pi)."""
    return angle % (2.0 * math.pi)


def classify_orbit(eccentricity: float) -> str:
    """Classify a conic section by eccentricity."""
    if eccentricity < 1e-4:
        return "circular"
    if eccentricity < 1.0 - 1e-9:
        return "elliptical"
    if eccentricity < 1.0 + 1e-9:
        return "parabolic"
    return "hyperbolic"


def orbital_elements(
    position: Vec3,
    velocity: Vec3,
    mu_m3s2: float = MU_EARTH,
    body_radius_m: float = R_EARTH,
) -> OrbitalElements:
    """
    Classical orbital elements from an instantaneous state vector.

    Args:
        position: Position from the body centre, in ECI-aligned axes. Unit: m.
        velocity: Velocity in the same axes. Unit: m/s.
        mu_m3s2: Standard gravitational parameter. Unit: m^3/s^2.
        body_radius_m: Body radius, for altitude conversions. Unit: m.

    Returns:
        The osculating elements at this instant.

    Raises:
        ValueError: If the position is a zero vector.
    """
    r = magnitude(position)
    if r < 1e-6:
        raise ValueError("position must be a non-zero vector from the body centre")
    v = magnitude(velocity)

    # Specific angular momentum h = r x v
    h_vec = cross(position, velocity)
    h = magnitude(h_vec)

    # Node vector n = z_hat x h — points at the ascending node
    n_vec = vec3(-h_vec.y, h_vec.x, 0.0)
    n = magnitude(n_vec)

    # Eccentricity vector e = ((v^2 - mu/r)*r - (r.v)*v) / mu
    r_dot_v = dot(position, velocity)
    e_vec = scale(
        sub(scale(position, v * v - mu_m3s2 / r), scale(velocity, r_dot_v)),
        1.0 / mu_m3s2,
    )
    eccentricity = magnitude(e_vec)

    specific_energy = (v * v) / 2.0 - mu_m3s2 / r
    is_parabolic = abs(specific_energy) < 1e-9
    semi_major_axis = math.inf if is_parabolic else -mu_m3s2 / (2.0 * specific_energy)

    inclination = _safe_acos(h_vec.z / h) if h > 0 else 0.0

    # RAAN — undefined for an equatorial orbit, reported as 0 by convention
    raan = 0.0
    if n > EQUATORIAL_TOLERANCE:
        raan = _safe_acos(n_vec.x / n)
        if n_vec.y < 0:
            raan = 2.0 * math.pi - raan

    # Argument of periapsis — undefined for a circular orbit, reported as 0
    arg_periapsis = 0.0
    if n > EQUATORIAL_TOLERANCE and eccentricity > CIRCULAR_TOLERANCE:
        arg_periapsis = _safe_acos(dot(n_vec, e_vec) / (n * eccentricity))
        if e_vec.z < 0:
            arg_periapsis = 2.0 * math.pi - arg_periapsis
    elif eccentricity > CIRCULAR_TOLERANCE:
        # Equatorial but eccentric: fall back to the longitude of periapsis.
        arg_periapsis = _wrap_two_pi(math.atan2(e_vec.y, e_vec.x))

    # True anomaly — for a circular orbit, measure from the ascending node
    if eccentricity > CIRCULAR_TOLERANCE:
        true_anomaly = _safe_acos(dot(e_vec, position) / (eccentricity * r))
        if r_dot_v < 0:
            true_anomaly = 2.0 * math.pi - true_anomaly
    elif n > EQUATORIAL_TOLERANCE:
        true_anomaly = _safe_acos(dot(n_vec, position) / (n * r))
        if position.z < 0:
            true_anomaly = 2.0 * math.pi - true_anomaly
    else:
        true_anomaly = _wrap_two_pi(math.atan2(position.y, position.x))

    # Apsides. For open orbits only the periapsis exists.
    is_closed = eccentricity < 1.0 and math.isfinite(semi_major_axis)
    if is_closed:
        periapsis_radius = semi_major_axis * (1.0 - eccentricity)
        apoapsis_radius = semi_major_axis * (1.0 + eccentricity)
        period = 2.0 * math.pi * math.sqrt(semi_major_axis**3 / mu_m3s2)
    else:
        periapsis_radius = (h * h) / (mu_m3s2 * (1.0 + eccentricity))
        apoapsis_radius = math.inf
        period = math.inf

    return OrbitalElements(
        semi_major_axis_m=semi_major_axis,
        eccentricity=eccentricity,
        inclination_rad=inclination,
        raan_rad=raan,
        argument_of_periapsis_rad=arg_periapsis,
        true_anomaly_rad=true_anomaly,
        periapsis_radius_m=periapsis_radius,
        apoapsis_radius_m=apoapsis_radius,
        periapsis_altitude_m=periapsis_radius - body_radius_m,
        apoapsis_altitude_m=apoapsis_radius - body_radius_m,
        period_s=period,
        specific_energy_Jkg=specific_energy,
        specific_angular_momentum_m2s=h,
        shape=classify_orbit(eccentricity),
        # A "stable orbit" must be closed and clear the surface. No atmospheric
        # decay margin is applied here — that is a mission-profile decision,
        # made in simulation/engine/mission_state.py.
        is_stable_orbit=is_closed and periapsis_radius > body_radius_m,
    )


def circular_orbit_speed(radius_m: float, mu_m3s2: float = MU_EARTH) -> float:
    """
    Speed required for a circular orbit at a given radius.

    v = sqrt(mu / r)

    Args:
        radius_m: Orbital radius from the body centre. Unit: m.
        mu_m3s2: Standard gravitational parameter. Unit: m^3/s^2.

    Returns:
        Circular orbital speed. Unit: m/s.
    """
    if radius_m <= 0:
        return 0.0
    return math.sqrt(mu_m3s2 / radius_m)
