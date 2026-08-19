"""
Aerodynamic drag model.

Ported from packages/simulation-engine/src/physics/drag.ts.
Pure functions, no side effects.
"""

from __future__ import annotations

import math

from .gravity import Vec3, magnitude, scale


def effective_drag_coefficient(cd_subsonic: float, mach: float) -> float:
    """
    Drag coefficient corrected for the transonic drag rise.

    Below Mach 0.8 the subsonic value is used directly. Between 0.8 and 1.2
    there is a smooth bump that peaks at about 1.5× the subsonic value.
    Above Mach 1.2 the coefficient decays back toward the subsonic value.

    This is a simplified model — real transonic drag depends on the vehicle's
    exact geometry — but it captures the qualitative behaviour that makes
    max-Q happen where it does.

    Args:
        cd_subsonic: Subsonic drag coefficient. Dimensionless.
        mach: Mach number. Dimensionless.

    Returns:
        Effective drag coefficient. Dimensionless.
    """
    if mach < 0.8:
        return cd_subsonic

    if mach < 1.2:
        # Smooth bump peaking near Mach 1.0.
        t = (mach - 0.8) / 0.4
        bump = 0.5 * (1.0 - math.cos(math.pi * t))
        return cd_subsonic * (1.0 + 0.5 * bump)

    # Supersonic: decays back from 1.5× toward 1.0× over a wide Mach range.
    decay = max(0.0, 1.0 - (mach - 1.2) / 4.0)
    return cd_subsonic * (1.0 + 0.5 * decay)


def drag_force(
    velocity: Vec3,
    density_kgm3: float,
    cd: float,
    reference_area_m2: float,
) -> Vec3:
    """
    Aerodynamic drag force vector.

    F_drag = -½ · ρ · |v|² · Cd · A · v̂

    Drag is anti-parallel to the velocity vector.

    Args:
        velocity: Vehicle velocity. Unit: m/s.
        density_kgm3: Air density. Unit: kg/m³.
        cd: Drag coefficient. Dimensionless.
        reference_area_m2: Aerodynamic reference area. Unit: m².

    Returns:
        Drag force vector. Unit: N.
    """
    speed = magnitude(velocity)
    if speed < 1e-8 or density_kgm3 < 1e-15:
        return Vec3(0.0, 0.0, 0.0)

    drag_magnitude = 0.5 * density_kgm3 * speed * speed * cd * reference_area_m2
    # Anti-parallel to velocity.
    return scale(velocity, -drag_magnitude / speed)
