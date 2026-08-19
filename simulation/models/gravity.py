"""
Gravity model — inverse-square central field.

Ported from packages/simulation-engine/src/physics/gravity.ts.
Pure functions, no side effects, no external dependencies beyond constants.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from .constants import G0, R_EARTH, MU_EARTH


class Vec3(NamedTuple):
    """Immutable 3-component vector. Used for position, velocity, force."""
    x: float
    y: float
    z: float


def vec3(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Vec3:
    """Create a Vec3."""
    return Vec3(x, y, z)


def magnitude(v: Vec3) -> float:
    """Euclidean magnitude of a vector."""
    return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)


def scale(v: Vec3, s: float) -> Vec3:
    """Scale a vector by a scalar."""
    return Vec3(v.x * s, v.y * s, v.z * s)


def add(a: Vec3, b: Vec3) -> Vec3:
    """Add two vectors."""
    return Vec3(a.x + b.x, a.y + b.y, a.z + b.z)


def sub(a: Vec3, b: Vec3) -> Vec3:
    """Subtract b from a."""
    return Vec3(a.x - b.x, a.y - b.y, a.z - b.z)


def dot(a: Vec3, b: Vec3) -> float:
    """Dot product of two vectors."""
    return a.x * b.x + a.y * b.y + a.z * b.z


def cross(a: Vec3, b: Vec3) -> Vec3:
    """Cross product of two vectors."""
    return Vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def normalize(v: Vec3) -> Vec3:
    """Normalize a vector to unit length. Returns zero vector if magnitude is near zero."""
    m = magnitude(v)
    if m < 1e-12:
        return Vec3(0.0, 0.0, 0.0)
    return Vec3(v.x / m, v.y / m, v.z / m)


# ──────────────────────────────────────────────────────────────
# Gravity
# ──────────────────────────────────────────────────────────────


def gravity_scalar(altitude_m: float) -> float:
    """
    Gravitational acceleration at a given altitude using the inverse-square law.

    g(h) = g₀ · (R / (R + h))²

    Args:
        altitude_m: Altitude above mean sea level. Unit: m.

    Returns:
        Gravitational acceleration magnitude. Unit: m/s².
    """
    ratio = R_EARTH / (R_EARTH + altitude_m)
    return G0 * ratio * ratio


def gravity_acceleration_central(position: Vec3, mu: float = MU_EARTH) -> Vec3:
    """
    Gravitational acceleration vector in a central field.

    a = -μ/r³ · r

    The acceleration points toward the centre of the body.

    Args:
        position: Position measured from the centre of the body. Unit: m.
        mu: Standard gravitational parameter. Unit: m³/s².

    Returns:
        Acceleration vector. Unit: m/s².

    Raises:
        ValueError: If the position is at or very near the centre.
    """
    r_sq = dot(position, position)
    if r_sq < 1.0:
        raise ValueError(f"Position too close to centre: |r|² = {r_sq}")

    r = math.sqrt(r_sq)
    factor = -mu / (r_sq * r)
    return Vec3(position.x * factor, position.y * factor, position.z * factor)
