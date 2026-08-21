"""
Wind profile.

The launch-day weather report gives one number: the wind at the surface, at the
standard 10 m measurement height. A vehicle flies through everything above
that, so this module turns a surface observation into a wind vector at any
altitude.

Three regimes, in order of how well they are known:

1. **Surface layer, 0–2 km.** The power law ``v(h) = v_ref · (h/h_ref)^α`` with
   α ≈ 0.143 over open terrain. This is the standard engineering profile and is
   accurate enough over the flat coastal sites rockets launch from.
2. **Free atmosphere, 2–25 km.** Wind speed rises toward a jet-stream maximum
   near the tropopause and falls away above it. Modelled as a smooth bump,
   because a real profile needs a radiosonde and the forecast APIs do not
   publish one.
3. **Above 25 km.** Taken as still. Dynamic pressure up there is small enough
   that wind contributes nothing measurable to the trajectory.

Direction veers with height — the Ekman spiral — clockwise in the northern
hemisphere and anticlockwise in the southern. The veer is capped at 30°, which
is typical over open ground.

**This is an approximation, stated as one.** A real launch commit uses balloon
soundings taken hours before the window and reflies the trajectory against the
measured profile. What is modelled here is good enough to show *why* wind
matters — that it displaces the vehicle, that it drives angle of attack, and
that angle of attack times dynamic pressure is a structural load — which is the
thing being taught.

Reference for the power law: Peterson & Hennessey (1978), *On the use of power
laws for estimates of wind power potential*, J. Appl. Meteorol. 17(3).
"""

from __future__ import annotations

import math
from typing import NamedTuple

__all__ = [
    "WindProfile",
    "WindState",
    "wind_at_altitude",
    "STANDARD_MEASUREMENT_HEIGHT_M",
]

#: Height at which surface wind is reported by convention. Unit: m.
STANDARD_MEASUREMENT_HEIGHT_M = 10.0

#: Power-law exponent over open, flat terrain. Dimensionless.
OPEN_TERRAIN_SHEAR_EXPONENT = 0.143

#: Top of the modelled surface layer. Unit: m.
_SURFACE_LAYER_TOP_M = 2_000.0

#: Altitude of the jet-stream maximum. Unit: m.
_JET_CORE_ALTITUDE_M = 11_000.0

#: Width of the jet bump, as a Gaussian standard deviation. Unit: m.
_JET_WIDTH_M = 5_000.0

#: Altitude above which wind is taken as zero. Unit: m.
_WIND_CEILING_M = 25_000.0

#: Largest directional veer between the surface and the free atmosphere. Unit: degrees.
_MAX_VEER_DEG = 30.0

#: Climatological mid-latitude jet core speed, used when no sounding is given. Unit: m/s.
_TYPICAL_JET_CORE_MS = 28.0

#: Ceiling on the estimated jet speed. Real cores rarely exceed this. Unit: m/s.
_MAX_ESTIMATED_JET_MS = 90.0


class WindProfile(NamedTuple):
    """The launch-day wind, as measured at the surface."""

    #: Wind speed at 10 m. Unit: m/s.
    surface_speed_ms: float
    #: Direction the wind is coming FROM, meteorological convention. Unit: degrees.
    surface_direction_deg: float
    #: Peak speed at the jet core. Unit: m/s. Defaults to a plausible multiple
    #: of the surface wind when no sounding is available.
    jet_speed_ms: float = 0.0
    #: Launch site latitude, which sets which way the wind veers. Unit: degrees.
    latitude_deg: float = 0.0
    #: Terrain roughness exponent. Higher over built-up ground.
    shear_exponent: float = OPEN_TERRAIN_SHEAR_EXPONENT


class WindState(NamedTuple):
    """Wind at one altitude, resolved into the launch-centred ENU frame."""

    #: Eastward component. Unit: m/s.
    east_ms: float
    #: Northward component. Unit: m/s.
    north_ms: float
    #: Vertical component. Always zero: this model has no updraughts. Unit: m/s.
    up_ms: float
    #: Wind speed at this altitude. Unit: m/s.
    speed_ms: float
    #: Direction the wind is coming from at this altitude. Unit: degrees.
    direction_deg: float


def _speed_at(altitude_agl_m: float, profile: WindProfile) -> float:
    """Wind speed at a height above ground level. Unit: m/s."""
    if altitude_agl_m >= _WIND_CEILING_M:
        return 0.0

    reference = max(profile.surface_speed_ms, 0.0)

    if altitude_agl_m <= STANDARD_MEASUREMENT_HEIGHT_M:
        # Below the measurement height the power law still applies, and takes
        # the wind to zero at the ground where the no-slip condition holds.
        if altitude_agl_m <= 0.0:
            return 0.0
        return reference * (altitude_agl_m / STANDARD_MEASUREMENT_HEIGHT_M) ** profile.shear_exponent

    # Surface layer: the power law.
    surface_layer = reference * (
        min(altitude_agl_m, _SURFACE_LAYER_TOP_M) / STANDARD_MEASUREMENT_HEIGHT_M
    ) ** profile.shear_exponent

    if altitude_agl_m <= _SURFACE_LAYER_TOP_M:
        return surface_layer

    # Free atmosphere: a Gaussian bump toward the jet core, added on top of the
    # value the surface layer reached, then faded out toward the ceiling.
    #
    # When no sounding is supplied the jet speed is estimated from the surface
    # wind, but only weakly: the correlation between the two is poor, and
    # scaling the boundary-layer value straight through produces 130 m/s jets
    # from a merely blustery morning. The estimate is anchored on a
    # climatological mid-latitude core speed and capped.
    jet_peak = (
        profile.jet_speed_ms
        if profile.jet_speed_ms > 0.0
        else min(_TYPICAL_JET_CORE_MS + 1.5 * reference, _MAX_ESTIMATED_JET_MS)
    )
    bump = (jet_peak - surface_layer) * math.exp(
        -(((altitude_agl_m - _JET_CORE_ALTITUDE_M) / _JET_WIDTH_M) ** 2)
    )
    speed = surface_layer + max(bump, 0.0)

    # Fade linearly to zero over the last 5 km before the ceiling, so there is
    # no discontinuity for the integrator to trip over.
    fade_start = _WIND_CEILING_M - 5_000.0
    if altitude_agl_m > fade_start:
        speed *= max(0.0, (_WIND_CEILING_M - altitude_agl_m) / 5_000.0)

    return max(speed, 0.0)


def _direction_at(altitude_agl_m: float, profile: WindProfile) -> float:
    """Direction the wind comes from at this height. Unit: degrees."""
    if altitude_agl_m <= STANDARD_MEASUREMENT_HEIGHT_M:
        return profile.surface_direction_deg % 360.0

    # Veer saturates at the top of the surface layer and holds above it.
    fraction = min(1.0, math.log10(altitude_agl_m / STANDARD_MEASUREMENT_HEIGHT_M) / math.log10(
        _SURFACE_LAYER_TOP_M / STANDARD_MEASUREMENT_HEIGHT_M
    ))
    # Northern hemisphere veers clockwise with height; southern backs.
    sign = 1.0 if profile.latitude_deg >= 0.0 else -1.0
    return (profile.surface_direction_deg + sign * _MAX_VEER_DEG * fraction) % 360.0


def wind_at_altitude(altitude_agl_m: float, profile: WindProfile) -> WindState:
    """
    Wind vector at a height above the launch site.

    Meteorological convention: `direction_deg` is the direction the wind blows
    *from*. A 270° wind is a westerly, and it pushes a vehicle toward the east,
    so the eastward component is ``+speed·sin(direction)``. Getting this sign
    backwards is the classic error, and it silently flips every crosswind
    result, so the conversion lives here and nowhere else.

    Args:
        altitude_agl_m: Height above the launch site, not above sea level. Unit: m.
        profile: The launch-day surface observation.

    Returns:
        The wind vector in launch-centred ENU axes.
    """
    speed = _speed_at(altitude_agl_m, profile)
    direction = _direction_at(altitude_agl_m, profile)

    if speed <= 0.0:
        return WindState(0.0, 0.0, 0.0, 0.0, direction)

    radians = math.radians(direction)
    # From-direction to blowing-toward vector: negate the unit vector pointing
    # at the source.
    east = -speed * math.sin(radians)
    north = -speed * math.cos(radians)

    return WindState(
        east_ms=east,
        north_ms=north,
        up_ms=0.0,
        speed_ms=speed,
        direction_deg=direction,
    )
