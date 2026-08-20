"""
Aerodynamic drag model.

Ported from packages/simulation-engine/src/physics/drag.ts.
Pure functions, no side effects.
"""

from __future__ import annotations

import math

from .gravity import Vec3, magnitude, scale


#: Multiplier at the transonic peak, relative to the subsonic coefficient.
TRANSONIC_PEAK = 2.5

#: Multiplier the curve settles at in the hypersonic regime.
HYPERSONIC_FLOOR = 1.1


def mach_drag_factor(mach: float) -> float:
    """
    Mach-dependent multiplier applied to the base (subsonic) drag coefficient.

    Real slender bodies show a sharp transonic drag rise: Cd roughly triples
    between M 0.8 and M 1.2, then falls away again as the shock system
    stabilises. Ignoring this makes the simulation understate max-Q and mislead
    students about why vehicles throttle down through the transonic region.

    This is a **shape-agnostic educational curve**, not wind-tunnel data. It is
    piecewise-linear in four regions:

    ==============  ==========================================
    Mach range      Behaviour
    ==============  ==========================================
    0 - 0.8         1.0 (incompressible)
    0.8 - 1.2       rises linearly to the transonic peak (2.5x)
    1.2 - 5.0       decays linearly toward the hypersonic floor
    > 5.0           1.1 (hypersonic floor)
    ==============  ==========================================

    Args:
        mach: Mach number. Negative values are treated as 0.

    Returns:
        Multiplier for the base drag coefficient. Dimensionless, >= 1.
    """
    m = max(0.0, mach)

    if m < 0.8:
        return 1.0
    if m < 1.2:
        return 1.0 + (TRANSONIC_PEAK - 1.0) * (m - 0.8) / 0.4
    if m < 5.0:
        return TRANSONIC_PEAK - (TRANSONIC_PEAK - HYPERSONIC_FLOOR) * (m - 1.2) / 3.8
    return HYPERSONIC_FLOOR


def effective_drag_coefficient(cd_subsonic: float, mach: float) -> float:
    """
    Drag coefficient corrected for the transonic drag rise.

    Args:
        cd_subsonic: Subsonic drag coefficient. Dimensionless.
        mach: Mach number. Dimensionless.

    Returns:
        Effective drag coefficient. Dimensionless.
    """
    return cd_subsonic * mach_drag_factor(mach)


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
