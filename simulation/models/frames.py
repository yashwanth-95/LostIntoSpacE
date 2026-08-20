"""
Coordinate frame conversions.

Ported from packages/simulation-engine/src/physics/frames.ts.

The engine integrates trajectories in a **launch-centred ENU frame**::

    origin  - the launch site
    +X      - East
    +Y      - North
    +Z      - Up (the local vertical at the launch site)

The axes are *fixed at t = 0* and do not follow the vehicle, so the frame is
inertial under the engine's non-rotating-Earth assumption. That makes it a valid
frame for Newtonian integration all the way to orbit: "up" stops being the
direction of gravity once the vehicle travels downrange, which is exactly why
the force model uses a central field rather than a constant -Z.

Two derived frames matter:

- **Earth-centred ENU** - the same axes, origin moved to the centre of the
  Earth. This is what the gravity model needs.
- **ECI-aligned** - Earth-centred with +Z through the North pole and +X through
  the prime meridian at t = 0. Orbital elements are only meaningful here:
  inclination measured in the ENU frame would be relative to the launch site's
  horizon, not the equator.

Assumptions
-----------
- Spherical Earth of radius ``R_EARTH`` (no WGS-84 flattening, so geodetic and
  geocentric latitude are treated as equal).
- Non-rotating Earth: the engine never advances Earth rotation. A real eastward
  equatorial launch gains ~465 m/s that this engine does not model.

Both assumptions are recorded in docs/simulation/ASSUMPTIONS.md.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from .constants import DEG_TO_RAD, R_EARTH
from .gravity import Vec3, add, magnitude, scale, vec3


class SiteLocation(NamedTuple):
    """A launch site on a spherical Earth."""

    #: Geodetic latitude. Unit: degrees, [-90, 90].
    latitude_deg: float
    #: Longitude. Unit: degrees, [-180, 180].
    longitude_deg: float
    #: Site elevation above mean sea level. Unit: m.
    altitude_m: float


class EnuBasis(NamedTuple):
    """The three ENU basis vectors of a site, expressed in ECI-aligned axes."""

    east: Vec3
    north: Vec3
    up: Vec3
    #: The site's position vector from Earth's centre, in ECI-aligned axes. Unit: m.
    origin: Vec3


def enu_basis(site: SiteLocation) -> EnuBasis:
    """
    Build the ENU basis of a site in ECI-aligned axes.

    Args:
        site: Launch site location.

    Returns:
        The east/north/up unit vectors and the site's position vector.
    """
    lat = site.latitude_deg * DEG_TO_RAD
    lon = site.longitude_deg * DEG_TO_RAD

    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)

    up = vec3(cos_lat * cos_lon, cos_lat * sin_lon, sin_lat)

    return EnuBasis(
        east=vec3(-sin_lon, cos_lon, 0.0),
        north=vec3(-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat),
        up=up,
        origin=scale(up, R_EARTH + site.altitude_m),
    )


def enu_to_earth_centered(enu_position: Vec3, site_altitude_m: float) -> Vec3:
    """
    Convert a launch-centred ENU position to Earth-centred, in the *same* axes.

    This is a pure translation along +Z by the site's geocentric radius, and it
    is all the gravity model needs: a central field is rotationally symmetric,
    so it does not care how the axes are oriented.

    Args:
        enu_position: Position relative to the launch site. Unit: m.
        site_altitude_m: Site elevation above sea level. Unit: m.

    Returns:
        Position from Earth's centre, in ENU axes. Unit: m.
    """
    return vec3(
        enu_position.x,
        enu_position.y,
        enu_position.z + R_EARTH + site_altitude_m,
    )


def altitude_from_enu(enu_position: Vec3, site_altitude_m: float) -> float:
    """
    Geometric altitude above the spherical surface.

    Altitude is ``|r| - R``, not simply the ENU z component: a vehicle 500 km
    downrange at ``z = 0`` is genuinely ~20 km above the curved surface.

    Returns:
        Altitude above mean sea level. Unit: m. May be negative below ground.
    """
    return magnitude(enu_to_earth_centered(enu_position, site_altitude_m)) - R_EARTH


def downrange_from_enu(enu_position: Vec3, site_altitude_m: float) -> float:
    """
    Great-circle downrange distance from the launch site.

    Computed as the arc length ``R * theta``, the distance a ground observer
    would measure, not the straight-line chord.

    Returns:
        Downrange distance along the surface. Unit: m.
    """
    site_radius = R_EARTH + site_altitude_m
    r = enu_to_earth_centered(enu_position, site_altitude_m)
    r_mag = magnitude(r)
    if r_mag < 1e-6:
        return 0.0

    # The site direction is +Z in ENU axes, so cos(theta) is the normalised z.
    cos_theta = min(1.0, max(-1.0, r.z / r_mag))
    return site_radius * math.acos(cos_theta)


def enu_vector_to_eci(enu_vector: Vec3, basis: EnuBasis) -> Vec3:
    """
    Rotate a vector from launch-centred ENU axes into ECI-aligned axes.

    Use this for velocities and other free vectors; use :func:`enu_position_to_eci`
    for positions, which also need the site translation.
    """
    return add(
        add(scale(basis.east, enu_vector.x), scale(basis.north, enu_vector.y)),
        scale(basis.up, enu_vector.z),
    )


def enu_position_to_eci(enu_position: Vec3, basis: EnuBasis) -> Vec3:
    """Convert a launch-centred ENU position into an Earth-centred ECI-aligned one."""
    return add(basis.origin, enu_vector_to_eci(enu_position, basis))


def direction_from_pitch_azimuth(pitch_rad: float, azimuth_rad: float) -> Vec3:
    """
    Unit vector in the ENU frame from a flight-path elevation and compass azimuth.

    Args:
        pitch_rad: Elevation above the local horizontal. pi/2 is straight up,
            0 is horizontal. Unit: rad.
        azimuth_rad: Compass bearing clockwise from North. 0 is North, pi/2 is
            East. Unit: rad.

    Returns:
        Unit direction vector in ENU axes.
    """
    horizontal = math.cos(pitch_rad)
    return vec3(
        horizontal * math.sin(azimuth_rad),  # East
        horizontal * math.cos(azimuth_rad),  # North
        math.sin(pitch_rad),  # Up
    )
