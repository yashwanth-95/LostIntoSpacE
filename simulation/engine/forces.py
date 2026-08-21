"""
Force model — thrust, drag, and gravity summed into an acceleration.

Ported from packages/simulation-engine/src/sim/forces.ts.

This module is the bridge between the pure physics models in
:mod:`simulation.models` and the flight loop in :mod:`simulation.engine.runner`.
It is deliberately free of mutable state: the integrator calls it four times per
RK4 step at different substep times, so anything that remembers between calls
would corrupt the result.

Sign conventions
----------------
- Thrust acts along the commanded direction (see :mod:`simulation.engine.guidance`).
- Drag is anti-parallel to velocity.
- Gravity points at the centre of the Earth, which is *not* -Z once the vehicle
  is downrange — the central field is evaluated from the Earth-centred position.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from simulation.models.atmosphere import (
    STANDARD_DAY,
    AtmosphereConditions,
    AtmosphereState,
    atmosphere_with_conditions,
    dynamic_pressure,
    mach_number,
)
from simulation.models.drag import drag_force, effective_drag_coefficient
from simulation.models.frames import altitude_from_enu, enu_to_earth_centered
from simulation.models.gravity import (
    Vec3,
    add,
    gravity_acceleration_central,
    magnitude,
    scale,
    dot,
    sub,
    vec3,
)
from simulation.models.wind import WindProfile, WindState, wind_at_altitude


class ForceState(NamedTuple):
    """Everything the force model computed, for telemetry and failure checks."""

    #: Net acceleration in the launch-centred ENU frame. Unit: m/s².
    acceleration: Vec3
    #: Thrust force vector. Unit: N.
    thrust: Vec3
    #: Drag force vector. Unit: N.
    drag: Vec3
    #: Gravitational acceleration vector. Unit: m/s².
    gravity: Vec3
    #: Thrust magnitude. Unit: N.
    thrust_N: float
    #: Drag magnitude. Unit: N.
    drag_N: float
    #: Atmospheric conditions at this altitude.
    atmosphere: AtmosphereState
    #: Dynamic pressure. Unit: Pa.
    dynamic_pressure_Pa: float
    #: Mach number, computed from airspeed rather than ground speed.
    mach: float
    #: Altitude above mean sea level. Unit: m.
    altitude_m: float
    #: Wind at this altitude, in ENU axes.
    wind: WindState
    #: Speed relative to the air mass. Unit: m/s.
    airspeed_ms: float
    #: Angle between the airflow and the vehicle's own axis. Unit: rad.
    angle_of_attack_rad: float


def compute_forces(
    *,
    position: Vec3,
    velocity: Vec3,
    mass_kg: float,
    thrust_N: float,
    thrust_direction: Vec3,
    drag_coefficient: float,
    reference_area_m2: float,
    site_altitude_m: float,
    use_mach_drag_rise: bool = True,
    wind_profile: WindProfile | None = None,
    conditions: AtmosphereConditions = STANDARD_DAY,
) -> ForceState:
    """
    Evaluate thrust, drag, and gravity at one instant.

    Args:
        position: Position in the launch-centred ENU frame. Unit: m.
        velocity: Velocity in the same frame. Unit: m/s.
        mass_kg: Current total mass. Unit: kg.
        thrust_N: Thrust magnitude being produced right now. Unit: N.
        thrust_direction: Unit vector thrust acts along, in ENU axes.
        drag_coefficient: Subsonic drag coefficient.
        reference_area_m2: Aerodynamic reference area. Unit: m².
        site_altitude_m: Launch site elevation. Unit: m.
        use_mach_drag_rise: Apply the transonic drag-rise correction.
        wind_profile: Launch-day surface wind. `None` means still air.
        conditions: Measured surface weather. Defaults to a standard day.

    Returns:
        The net acceleration and every intermediate quantity.

    Notes:
        Aerodynamics act on the velocity *relative to the air*, not on the
        velocity relative to the ground. With wind present the two differ, and
        every aerodynamic quantity here — drag, dynamic pressure, Mach number,
        angle of attack — is computed from the relative velocity. Using ground
        speed instead is the mistake that makes a crosswind look free.
    """
    altitude_m = altitude_from_enu(position, site_altitude_m)
    atm = atmosphere_with_conditions(altitude_m, conditions)

    # Wind is profiled against height above the pad, which is what a surface
    # observation is referenced to.
    height_agl_m = altitude_m - site_altitude_m
    wind = (
        wind_at_altitude(height_agl_m, wind_profile)
        if wind_profile is not None
        else WindState(0.0, 0.0, 0.0, 0.0, 0.0)
    )
    wind_vector = vec3(wind.east_ms, wind.north_ms, wind.up_ms)

    # Airspeed: the vehicle's motion through the air mass it is flying in.
    air_velocity = sub(velocity, wind_vector)
    airspeed = magnitude(air_velocity)

    mach = mach_number(airspeed, atm)
    q = dynamic_pressure(airspeed, atm.density_kgm3)

    cd = (
        effective_drag_coefficient(drag_coefficient, mach)
        if use_mach_drag_rise
        else drag_coefficient
    )
    drag = drag_force(air_velocity, atm.density_kgm3, cd, reference_area_m2)

    # Angle of attack: the angle between where the vehicle points and where the
    # air is coming from. Its product with dynamic pressure is the lateral
    # structural load, which is why a launch is scrubbed for upper-level wind
    # shear even in clear weather at the pad.
    angle_of_attack_rad = 0.0
    if airspeed > 1.0:
        heading = scale(air_velocity, 1.0 / airspeed)
        axis_magnitude = magnitude(thrust_direction)
        if axis_magnitude > 1e-9:
            axis = scale(thrust_direction, 1.0 / axis_magnitude)
            cosine = max(-1.0, min(1.0, dot(heading, axis)))
            angle_of_attack_rad = math.acos(cosine)

    thrust = scale(thrust_direction, thrust_N)

    # Gravity from the Earth-centred position: a central field, not a constant
    # -Z. This is what lets the vehicle stay in orbit rather than flying off a
    # flat world.
    earth_centered = enu_to_earth_centered(position, site_altitude_m)
    gravity = gravity_acceleration_central(earth_centered)

    # a = F/m + g. Mass is floored to avoid a division blow-up if a vehicle is
    # configured with zero dry mass; the failure system catches that separately.
    safe_mass = max(mass_kg, 1e-6)
    acceleration = add(scale(add(thrust, drag), 1.0 / safe_mass), gravity)

    return ForceState(
        acceleration=acceleration,
        thrust=thrust,
        drag=drag,
        gravity=gravity,
        thrust_N=thrust_N,
        drag_N=magnitude(drag),
        atmosphere=atm,
        dynamic_pressure_Pa=q,
        mach=mach,
        altitude_m=altitude_m,
        wind=wind,
        airspeed_ms=airspeed,
        angle_of_attack_rad=angle_of_attack_rad,
    )


#: Height above the pad within which the vehicle still counts as resting on it.
#: Not exactly zero: the integrator moves the vehicle between steps, so a small
#: band avoids chatter as it lifts.
PAD_CONTACT_BAND_M = 0.5


def ground_constrained_acceleration(
    acceleration: Vec3, position: Vec3, velocity: Vec3, site_altitude_m: float
) -> Vec3:
    """
    Suppress downward acceleration while the vehicle is still resting on the pad.

    Without this a vehicle whose thrust-to-weight is below 1 sinks through the
    ground during the ignition transient instead of simply failing to lift off.
    The failure system reports the insufficient TWR; the pad just holds it up in
    the meantime.

    The ground is at the *launch site's elevation*, not at mean sea level.
    Comparing against 0 m MSL puts the pad underground at every real launch
    site — Cape Canaveral sits about 4 m up, Baikonur about 90 m — which
    silently disables this constraint and marks the vehicle as airborne before
    it has moved.
    """
    height_above_pad_m = altitude_from_enu(position, site_altitude_m) - site_altitude_m
    if height_above_pad_m > PAD_CONTACT_BAND_M:
        return acceleration
    if velocity.z > 0.0 or acceleration.z > 0.0:
        return acceleration
    return vec3(acceleration.x, acceleration.y, 0.0)
