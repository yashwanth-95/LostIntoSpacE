"""
US Standard Atmosphere 1976.

Seven-layer piecewise model from 0 to 86 km, with exponential decay above.
Ported from packages/simulation-engine/src/physics/atmosphere.ts.
Pure functions, no side effects.

Reference: NASA TM-X-74335 (US Standard Atmosphere, 1976).
"""

from __future__ import annotations

import math
from typing import NamedTuple

from .constants import (
    G0,
    M_AIR,
    R_UNIVERSAL,
    GAMMA_AIR,
    R_AIR,
    T0,
    P0,
    RHO0,
)


class AtmosphereState(NamedTuple):
    """Atmospheric conditions at a given altitude."""
    #: Temperature. Unit: K.
    temperature_K: float
    #: Static pressure. Unit: Pa.
    pressure_Pa: float
    #: Air density. Unit: kg/m³.
    density_kgm3: float
    #: Speed of sound. Unit: m/s.
    speed_of_sound_ms: float


# ──────────────────────────────────────────────────────────────
# Layer table
# ──────────────────────────────────────────────────────────────

class _Layer(NamedTuple):
    """One layer of the standard atmosphere."""
    base_altitude_m: float
    base_temperature_K: float
    base_pressure_Pa: float
    lapse_rate_Km: float  # K/m (negative means temperature decreases with altitude)


#: US Standard Atmosphere 1976 layers.
#: Source: NASA TM-X-74335, Table 4.
_LAYERS: tuple[_Layer, ...] = (
    _Layer(0,          288.15,  101_325.0,     -0.0065),
    _Layer(11_000,     216.65,  22_632.1,       0.0),
    _Layer(20_000,     216.65,  5474.89,        0.001),
    _Layer(32_000,     228.65,  868.019,        0.0028),
    _Layer(47_000,     270.65,  110.906,        0.0),
    _Layer(51_000,     270.65,  66.9389,       -0.0028),
    _Layer(71_000,     214.65,  3.95642,       -0.002),
)


def _find_layer(altitude_m: float) -> int:
    """Find the index of the layer containing the given altitude."""
    for i in range(len(_LAYERS) - 1, -1, -1):
        if altitude_m >= _LAYERS[i].base_altitude_m:
            return i
    return 0


# ──────────────────────────────────────────────────────────────
# Geopotential altitude
# ──────────────────────────────────────────────────────────────

#: Effective radius for geopotential conversion. Unit: m.
_R_EFFECTIVE: float = 6_356_766.0


def _geometric_to_geopotential(h_geometric_m: float) -> float:
    """
    Convert geometric altitude to geopotential altitude.

    H = R·h / (R + h)

    The standard atmosphere is defined in geopotential altitude. Neglecting the
    conversion produces a ~0.3% density error at 80 km. Below 11 km the
    difference is negligible.
    """
    return _R_EFFECTIVE * h_geometric_m / (_R_EFFECTIVE + h_geometric_m)


# ──────────────────────────────────────────────────────────────
# Atmosphere model
# ──────────────────────────────────────────────────────────────

#: Ceiling of the piecewise model. Above this, exponential decay is used.
_PIECEWISE_CEILING_M: float = 86_000.0

#: Scale height for the exponential region above 86 km. Unit: m.
_UPPER_SCALE_HEIGHT_M: float = 6_500.0

#: Temperature at 86 km (approximately). Unit: K.
_T_86KM: float = 186.87


def atmosphere(altitude_m: float) -> AtmosphereState:
    """
    Compute atmospheric conditions at a geometric altitude.

    Below 86 km uses the 7-layer piecewise model of US Standard Atmosphere 1976.
    Above 86 km uses exponential decay, which is a rough approximation but
    sufficient for drag calculations (drag is negligible above ~100 km anyway).

    Below 0 m the sea-level values are returned (clamped).

    Args:
        altitude_m: Geometric altitude above mean sea level. Unit: m.

    Returns:
        Temperature, pressure, density, and speed of sound at that altitude.
    """
    if altitude_m <= 0:
        return AtmosphereState(
            temperature_K=T0,
            pressure_Pa=P0,
            density_kgm3=RHO0,
            speed_of_sound_ms=math.sqrt(GAMMA_AIR * R_AIR * T0),
        )

    if altitude_m >= _PIECEWISE_CEILING_M:
        return _above_86km(altitude_m)

    # Convert to geopotential altitude for the layer lookup.
    h = _geometric_to_geopotential(altitude_m)
    idx = _find_layer(h)
    layer = _LAYERS[idx]

    dh = h - layer.base_altitude_m
    lapse = layer.lapse_rate_Km

    if abs(lapse) < 1e-10:
        # Isothermal layer: pressure decays exponentially.
        temperature = layer.base_temperature_K
        pressure = layer.base_pressure_Pa * math.exp(
            -G0 * M_AIR * dh / (R_UNIVERSAL * temperature)
        )
    else:
        # Gradient layer: temperature changes linearly with altitude.
        temperature = layer.base_temperature_K + lapse * dh
        exponent = G0 * M_AIR / (R_UNIVERSAL * lapse)
        pressure = layer.base_pressure_Pa * (
            temperature / layer.base_temperature_K
        ) ** (-exponent)

    density = pressure * M_AIR / (R_UNIVERSAL * temperature) if temperature > 0 else 0.0
    speed_of_sound = math.sqrt(GAMMA_AIR * R_AIR * temperature) if temperature > 0 else 0.0

    return AtmosphereState(
        temperature_K=temperature,
        pressure_Pa=pressure,
        density_kgm3=density,
        speed_of_sound_ms=speed_of_sound,
    )


def _above_86km(altitude_m: float) -> AtmosphereState:
    """Exponential decay model for the region above 86 km."""
    dh = altitude_m - _PIECEWISE_CEILING_M
    decay = math.exp(-dh / _UPPER_SCALE_HEIGHT_M)

    # Reference values at 86 km from the piecewise model.
    ref = atmosphere(_PIECEWISE_CEILING_M - 1)  # just below the ceiling

    temperature = max(100.0, _T_86KM)
    pressure = ref.pressure_Pa * decay
    density = pressure * M_AIR / (R_UNIVERSAL * temperature) if temperature > 0 else 0.0
    speed_of_sound = math.sqrt(GAMMA_AIR * R_AIR * temperature) if temperature > 0 else 0.0

    return AtmosphereState(
        temperature_K=temperature,
        pressure_Pa=pressure,
        density_kgm3=density,
        speed_of_sound_ms=speed_of_sound,
    )


# ──────────────────────────────────────────────────────────────
# Derived quantities
# ──────────────────────────────────────────────────────────────


def mach_number(speed_ms: float, atm: AtmosphereState) -> float:
    """
    Mach number.

    Args:
        speed_ms: Vehicle speed. Unit: m/s.
        atm: Atmospheric conditions at the current altitude.

    Returns:
        Mach number. Dimensionless.
    """
    if atm.speed_of_sound_ms < 1e-6:
        return 0.0
    return speed_ms / atm.speed_of_sound_ms


def dynamic_pressure(speed_ms: float, density_kgm3: float) -> float:
    """
    Dynamic pressure: q = ½ρv².

    Args:
        speed_ms: Vehicle speed. Unit: m/s.
        density_kgm3: Air density. Unit: kg/m³.

    Returns:
        Dynamic pressure. Unit: Pa.
    """
    return 0.5 * density_kgm3 * speed_ms * speed_ms


# ──────────────────────────────────────────────────────────────
# Non-standard day
# ──────────────────────────────────────────────────────────────
#
# The US Standard Atmosphere describes an average day, and a launch never
# happens on one. A hot, low-pressure, humid morning has measurably less dense
# air than the standard model says, and less dense air means less drag, less
# dynamic pressure, and less thrust from an air-breathing... — well, and a
# different max-Q altitude for a rocket. When the platform has a real weather
# observation for the pad, this is how it gets used.
#
# The corrections are the ones performance engineering actually applies:
#
#   * a surface temperature offset, decaying with altitude to zero in the
#     stratosphere (a "hot day" / "cold day" shift of the whole profile),
#   * a surface pressure ratio applied multiplicatively at every altitude,
#   * a humidity correction, because water vapour is lighter than dry air.
#
# What is *not* modelled: the real vertical temperature structure of the day.
# That needs a radiosonde. The offset approach is standard, documented, and
# deliberately conservative — it is stated here rather than hidden.


class AtmosphereConditions(NamedTuple):
    """Measured surface conditions on launch day."""

    #: Temperature at the surface. Unit: K.
    surface_temperature_K: float = T0
    #: Static pressure at the surface. Unit: Pa.
    surface_pressure_Pa: float = P0
    #: Relative humidity, 0–1.
    relative_humidity: float = 0.0
    #: Elevation the observation was taken at. Unit: m.
    station_altitude_m: float = 0.0


#: Standard-day conditions. Using this reproduces `atmosphere()` exactly.
STANDARD_DAY = AtmosphereConditions()

#: Altitude at which a surface temperature anomaly has fully decayed. Unit: m.
_ANOMALY_DECAY_CEILING_M: float = 20_000.0

#: Specific gas constant for dry air. Unit: J/(kg·K).
R_DRY_AIR: float = 287.058

#: Specific gas constant for water vapour. Unit: J/(kg·K).
R_WATER_VAPOUR: float = 461.495


def saturation_vapour_pressure(temperature_K: float) -> float:
    """
    Saturation vapour pressure of water over liquid, by the Tetens formula.

    Args:
        temperature_K: Air temperature. Unit: K.

    Returns:
        Saturation vapour pressure. Unit: Pa.

    Reference: Tetens (1930), as given in Murray (1967), J. Appl. Meteorol. 6(1).
    """
    celsius = temperature_K - 273.15
    if celsius <= -35.0:
        # The formula's denominator approaches zero below about -35 °C. Air that
        # cold holds so little water that treating it as dry is exact enough.
        return 0.0
    return 610.78 * math.exp(17.27 * celsius / (celsius + 237.3))


def humid_air_density(
    pressure_Pa: float, temperature_K: float, relative_humidity: float = 0.0
) -> float:
    """
    Density of moist air.

    Counter-intuitively, humid air is *less* dense than dry air at the same
    pressure and temperature: a water molecule (18 g/mol) is lighter than the
    nitrogen and oxygen (~29 g/mol) it displaces. The effect is small — a few
    tenths of a percent — but it is real and free to include.

    Args:
        pressure_Pa: Total static pressure. Unit: Pa.
        temperature_K: Air temperature. Unit: K.
        relative_humidity: Relative humidity, 0–1.

    Returns:
        Air density. Unit: kg/m³.
    """
    if temperature_K <= 0.0:
        return 0.0

    humidity = min(max(relative_humidity, 0.0), 1.0)
    vapour_pressure = humidity * saturation_vapour_pressure(temperature_K)
    # Vapour pressure cannot exceed the total pressure.
    vapour_pressure = min(vapour_pressure, pressure_Pa)
    dry_pressure = pressure_Pa - vapour_pressure

    return (
        dry_pressure / (R_DRY_AIR * temperature_K)
        + vapour_pressure / (R_WATER_VAPOUR * temperature_K)
    )


def atmosphere_with_conditions(
    altitude_m: float, conditions: AtmosphereConditions = STANDARD_DAY
) -> AtmosphereState:
    """
    Atmospheric conditions at an altitude, corrected for the measured weather.

    Passing :data:`STANDARD_DAY` returns exactly what :func:`atmosphere` returns,
    so the corrected path and the standard path agree by construction rather
    than by coincidence.

    Args:
        altitude_m: Geometric altitude above mean sea level. Unit: m.
        conditions: Measured surface conditions.

    Returns:
        Temperature, pressure, density and speed of sound, corrected.
    """
    standard = atmosphere(altitude_m)

    # What the standard model says the surface looks like, so the anomaly is
    # measured against the right baseline for a site at 90 m rather than 0 m.
    station = atmosphere(conditions.station_altitude_m)

    temperature_anomaly_K = conditions.surface_temperature_K - station.temperature_K
    pressure_ratio = (
        conditions.surface_pressure_Pa / station.pressure_Pa
        if station.pressure_Pa > 0.0
        else 1.0
    )

    # The temperature offset fades out with altitude: surface weather does not
    # reach the stratosphere.
    if altitude_m >= _ANOMALY_DECAY_CEILING_M:
        decay = 0.0
    else:
        decay = max(0.0, 1.0 - altitude_m / _ANOMALY_DECAY_CEILING_M)

    temperature = max(standard.temperature_K + temperature_anomaly_K * decay, 1.0)
    pressure = max(standard.pressure_Pa * pressure_ratio, 0.0)

    # Humidity is a surface-layer effect; above the troposphere the air is dry.
    humidity = conditions.relative_humidity * decay

    density = humid_air_density(pressure, temperature, humidity)
    speed_of_sound = math.sqrt(GAMMA_AIR * R_AIR * temperature)

    return AtmosphereState(
        temperature_K=temperature,
        pressure_Pa=pressure,
        density_kgm3=density,
        speed_of_sound_ms=speed_of_sound,
    )
