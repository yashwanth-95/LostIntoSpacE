"""
Thrust model — Isp, mass flow, delta-v, thrust at pressure.

Ported from packages/simulation-engine/src/physics/thrust.ts.
Pure functions, no side effects.
"""

from __future__ import annotations

import math

from .constants import G0, P0


def specific_impulse_at_pressure(
    isp_vacuum_s: float,
    isp_sea_level_s: float,
    ambient_pressure_Pa: float,
) -> float:
    """
    Specific impulse at a given ambient pressure, linearly interpolated.

    Args:
        isp_vacuum_s: Vacuum Isp. Unit: s.
        isp_sea_level_s: Sea-level Isp. Unit: s.
        ambient_pressure_Pa: Ambient pressure. Unit: Pa.

    Returns:
        Interpolated Isp. Unit: s.
    """
    if P0 < 1e-6:
        return isp_vacuum_s
    fraction = max(0.0, min(1.0, ambient_pressure_Pa / P0))
    return isp_vacuum_s + (isp_sea_level_s - isp_vacuum_s) * fraction


def thrust_at_pressure(
    thrust_vacuum_N: float,
    thrust_sea_level_N: float,
    ambient_pressure_Pa: float,
) -> float:
    """
    Thrust at a given ambient pressure, linearly interpolated between
    sea-level and vacuum values.

    Args:
        thrust_vacuum_N: Vacuum thrust. Unit: N.
        thrust_sea_level_N: Sea-level thrust. Unit: N.
        ambient_pressure_Pa: Ambient pressure. Unit: Pa.

    Returns:
        Interpolated thrust. Unit: N.
    """
    if P0 < 1e-6:
        return thrust_vacuum_N
    fraction = max(0.0, min(1.0, ambient_pressure_Pa / P0))
    return thrust_vacuum_N + (thrust_sea_level_N - thrust_vacuum_N) * fraction


def mass_flow_rate(thrust_N: float, isp_s: float) -> float:
    """
    Propellant mass flow rate.

    ṁ = F / (Isp · g₀)

    Args:
        thrust_N: Thrust. Unit: N.
        isp_s: Specific impulse. Unit: s.

    Returns:
        Mass flow rate. Unit: kg/s.
    """
    if isp_s <= 0 or G0 <= 0:
        return 0.0
    return thrust_N / (isp_s * G0)


def delta_v(isp_s: float, mass_initial_kg: float, mass_final_kg: float) -> float:
    """
    Ideal delta-v from the Tsiolkovsky rocket equation.

    Δv = Isp · g₀ · ln(m₀ / m_f)

    Args:
        isp_s: Specific impulse. Unit: s.
        mass_initial_kg: Mass before the burn. Unit: kg.
        mass_final_kg: Mass after the burn. Unit: kg.

    Returns:
        Ideal velocity change. Unit: m/s.
    """
    if mass_final_kg <= 0 or mass_initial_kg <= mass_final_kg:
        return 0.0
    return isp_s * G0 * math.log(mass_initial_kg / mass_final_kg)


def burn_time(propellant_mass_kg: float, mass_flow_kgs: float) -> float:
    """
    How long a burn lasts at constant mass flow.

    Args:
        propellant_mass_kg: Propellant available. Unit: kg.
        mass_flow_kgs: Mass flow rate. Unit: kg/s.

    Returns:
        Burn time. Unit: s.
    """
    if mass_flow_kgs <= 0:
        return 0.0
    return propellant_mass_kg / mass_flow_kgs


def thrust_to_weight(thrust_N: float, mass_kg: float) -> float:
    """
    Thrust-to-weight ratio.

    Args:
        thrust_N: Thrust. Unit: N.
        mass_kg: Total mass. Unit: kg.

    Returns:
        TWR. Dimensionless.
    """
    weight = mass_kg * G0
    if weight <= 0:
        return 0.0
    return thrust_N / weight
