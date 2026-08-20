"""
Guidance — the attitude program that decides where thrust points.

Ported from packages/simulation-engine/src/sim/guidance.ts.

The engine is 3-DOF: it integrates translation only, and attitude is
*commanded*, not derived from moments. Nothing here models a control loop,
gimbal actuators, or rotational inertia. What it does model is the shape of a
real ascent, which is what determines whether a vehicle reaches orbit or comes
straight back down.

Why a rocket does not fly straight up
-------------------------------------
A vehicle that thrusts vertically for its whole burn arrives at apogee with no
horizontal velocity and falls back. Orbit is almost entirely a *sideways*
problem: at 200 km you need about 7.8 km/s horizontally and essentially no
vertical speed. So a launch vehicle pitches over early and spends most of its
burn accelerating downrange.

Two programs are offered:

- ``pitch_program`` — pitch is a scheduled function of altitude. Fully
  deterministic and easy to reason about, which makes it the default.
- ``gravity_turn`` — after an initial pitchover kick, thrust follows the
  velocity vector and gravity does the steering. This is what real vehicles
  fly, and it costs nothing in steering losses because thrust and velocity
  stay aligned.
"""

from __future__ import annotations

import math
from typing import NamedTuple, Optional

from simulation.contracts import GuidanceConfig, GuidanceMode
from simulation.models.constants import DEG_TO_RAD
from simulation.models.frames import direction_from_pitch_azimuth
from simulation.models.gravity import Vec3, dot, magnitude, normalize, vec3


class GuidanceCommand(NamedTuple):
    """The attitude the guidance system is commanding."""

    #: Elevation above the local horizontal. pi/2 is straight up. Unit: rad.
    pitch_rad: float
    #: Compass bearing, clockwise from North. Unit: rad.
    yaw_rad: float
    #: Unit vector in the launch-centred ENU frame that thrust acts along.
    thrust_direction: Vec3


def scheduled_pitch(altitude_m: float, config: GuidanceConfig) -> float:
    """
    Scheduled pitch as a function of altitude.

    Vertical below the pitchover altitude, then linear in altitude down to the
    final pitch, then held. Linear-in-altitude rather than linear-in-time so the
    program does not depend on how fast the vehicle happens to be climbing.

    Args:
        altitude_m: Current altitude. Unit: m.
        config: Guidance configuration.

    Returns:
        Commanded pitch. Unit: rad.
    """
    vertical_rad = math.pi / 2.0
    final_rad = config.final_pitch_deg * DEG_TO_RAD

    if altitude_m <= config.pitchover_altitude_m:
        return vertical_rad

    span = config.pitch_program_end_altitude_m - config.pitchover_altitude_m
    if span <= 0:
        return final_rad

    fraction = min(1.0, (altitude_m - config.pitchover_altitude_m) / span)
    return vertical_rad + (final_rad - vertical_rad) * fraction


def initial_command(config: GuidanceConfig) -> GuidanceCommand:
    """The command held on the pad: straight up, along the launch azimuth."""
    azimuth_rad = config.launch_azimuth_deg * DEG_TO_RAD
    pitch_rad = math.pi / 2.0
    return GuidanceCommand(
        pitch_rad=pitch_rad,
        yaw_rad=azimuth_rad,
        thrust_direction=direction_from_pitch_azimuth(pitch_rad, azimuth_rad),
    )


def local_up_vector(position_enu: Vec3, site_altitude_m: float) -> Vec3:
    """
    The radial unit vector at the vehicle's position, in ENU axes.

    Not simply +Z: once the vehicle travels downrange, local "up" tilts away
    from the launch site's vertical.
    """
    from simulation.models.frames import enu_to_earth_centered

    return normalize(enu_to_earth_centered(position_enu, site_altitude_m))


def compute_guidance(
    *,
    altitude_m: float,
    velocity: Vec3,
    local_up: Vec3,
    guidance_failed: bool,
    last_command: Optional[GuidanceCommand],
    config: GuidanceConfig,
) -> GuidanceCommand:
    """
    Compute the attitude command for the current state.

    Args:
        altitude_m: Altitude above mean sea level. Unit: m.
        velocity: Velocity in the launch-centred ENU frame. Unit: m/s.
        local_up: Radial unit vector at the vehicle's position.
        guidance_failed: Whether guidance has failed. A failed guidance system
            holds its last command rather than updating.
        last_command: The command to hold when guidance has failed.
        config: Guidance configuration.

    Returns:
        The commanded pitch, yaw, and thrust direction.
    """
    # A failed guidance system stops updating and holds whatever it last had.
    if guidance_failed and last_command is not None:
        return last_command

    azimuth_rad = config.launch_azimuth_deg * DEG_TO_RAD

    if config.mode == GuidanceMode.VERTICAL:
        # Straight up means along the *local* vertical, which drifts from the
        # launch site's +Z as the vehicle travels downrange.
        return GuidanceCommand(
            pitch_rad=math.pi / 2.0,
            yaw_rad=azimuth_rad,
            thrust_direction=local_up,
        )

    if config.mode == GuidanceMode.GRAVITY_TURN:
        return _gravity_turn_command(
            altitude_m=altitude_m,
            velocity=velocity,
            azimuth_rad=azimuth_rad,
            config=config,
        )

    # pitch_program (the default)
    pitch = scheduled_pitch(altitude_m, config)
    return GuidanceCommand(
        pitch_rad=pitch,
        yaw_rad=azimuth_rad,
        thrust_direction=direction_from_pitch_azimuth(pitch, azimuth_rad),
    )


def _gravity_turn_command(
    *,
    altitude_m: float,
    velocity: Vec3,
    azimuth_rad: float,
    config: GuidanceConfig,
) -> GuidanceCommand:
    """
    Gravity turn: kick over, then follow the velocity vector.

    Below the pitchover altitude the vehicle flies vertically. Across the kick
    band the commanded pitch is ramped from vertical to (vertical - kick), which
    keeps the attitude continuous — a step would make the velocity vector, which
    follows it, discontinuous too. Above the band, thrust simply points along
    velocity and gravity does the rest of the steering.
    """
    speed = magnitude(velocity)
    kick_rad = config.gravity_turn_kick_deg * DEG_TO_RAD
    vertical_rad = math.pi / 2.0

    band_top = config.pitchover_altitude_m * max(1.0001, config.gravity_turn_kick_band)

    if altitude_m <= config.pitchover_altitude_m:
        pitch = vertical_rad
    elif altitude_m < band_top or speed < config.gravity_turn_min_speed_ms:
        # Ramp the kick in smoothly across the band.
        span = band_top - config.pitchover_altitude_m
        fraction = 1.0 if span <= 0 else min(
            1.0, (altitude_m - config.pitchover_altitude_m) / span
        )
        pitch = vertical_rad - kick_rad * fraction
    else:
        # Follow velocity. Pitch is the flight-path angle above the horizontal.
        horizontal = math.sqrt(velocity.x * velocity.x + velocity.y * velocity.y)
        pitch = math.atan2(velocity.z, horizontal)
        # Keep thrust pointing along the actual velocity vector, azimuth included.
        return GuidanceCommand(
            pitch_rad=pitch,
            yaw_rad=math.atan2(velocity.x, velocity.y) if horizontal > 1e-6 else azimuth_rad,
            thrust_direction=normalize(velocity),
        )

    return GuidanceCommand(
        pitch_rad=pitch,
        yaw_rad=azimuth_rad,
        thrust_direction=direction_from_pitch_azimuth(pitch, azimuth_rad),
    )


def angle_of_attack(velocity: Vec3, thrust_direction: Vec3) -> float:
    """
    Angle between the velocity vector and the commanded thrust direction.

    A large angle of attack in dense air is what tears a vehicle apart, so this
    is both a telemetry field and a failure-detection input.

    Returns:
        Angle. Unit: rad, [0, pi]. Zero when the vehicle is not moving.
    """
    speed = magnitude(velocity)
    if speed < 1e-6:
        return 0.0
    cos_alpha = dot(normalize(velocity), normalize(thrust_direction))
    return math.acos(min(1.0, max(-1.0, cos_alpha)))
