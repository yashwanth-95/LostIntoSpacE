"""Units and physical quantities.

Every physical value in the canonical model is a `Quantity`, which preserves
value, unit, uncertainty (when the source publishes one) and the source it came
from. Bare floats are not allowed for physical values — that is what makes a
unit mismatch a detectable error rather than a silent one.

Conversion is affine (`factor` + `offset`) so temperature works correctly:
`K = degC * 1 + 273.15`.
"""

import math
from enum import Enum
from typing import Dict, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts.provenance import SourceReference

__all__ = [
    "Dimension",
    "UnitDef",
    "UnitError",
    "Quantity",
    "convert",
    "get_unit",
    "canonical_unit_for",
    "dimension_of",
    "is_known_unit",
]


class UnitError(ValueError):
    """Raised for unknown units or dimension mismatches."""


class Dimension(str, Enum):
    DIMENSIONLESS = "DIMENSIONLESS"
    MASS = "MASS"
    LENGTH = "LENGTH"
    TIME = "TIME"
    TEMPERATURE = "TEMPERATURE"
    ANGLE = "ANGLE"
    VELOCITY = "VELOCITY"
    ACCELERATION = "ACCELERATION"
    DENSITY = "DENSITY"
    PRESSURE = "PRESSURE"
    AREA = "AREA"
    VOLUME = "VOLUME"
    ANGULAR_VELOCITY = "ANGULAR_VELOCITY"
    ENERGY = "ENERGY"
    FORCE = "FORCE"
    IRRADIANCE = "IRRADIANCE"
    #: Astronomical magnitudes are logarithmic; kept separate so they can never
    #: be silently converted to or compared with a plain ratio.
    MAGNITUDE = "MAGNITUDE"
    #: GM, the standard gravitational parameter.
    GRAVITATIONAL_PARAMETER = "GRAVITATIONAL_PARAMETER"
    #: Inverse length, used by SGP4 B* drag terms.
    INVERSE_LENGTH = "INVERSE_LENGTH"


class UnitDef(BaseModel):
    """Definition of one unit, expressed relative to its SI base unit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    dimension: Dimension
    #: si_value = value * factor + offset
    factor: float
    offset: float = 0.0
    aliases: Tuple[str, ...] = ()


def _u(symbol, dimension, factor, offset=0.0, aliases=()):
    return UnitDef(
        symbol=symbol,
        dimension=dimension,
        factor=factor,
        offset=offset,
        aliases=tuple(aliases),
    )


_D = Dimension

# Reference constants. Values follow IAU 2015 nominal conversion constants
# where one exists, so that mass/radius expressed in solar or planetary units
# round-trips predictably.
_M_SUN = 1.98841e30
_M_EARTH = 5.97217e24
_M_JUP = 1.89813e27
_R_SUN = 6.957e8
_R_EARTH = 6.3781e6
_R_JUP = 7.1492e7
_AU = 1.495978707e11
_JULIAN_YEAR_S = 365.25 * 86400.0

_UNIT_DEFS = (
    # Dimensionless
    _u("1", _D.DIMENSIONLESS, 1.0, aliases=("", "-", "none", "ratio", "unitless", "dimensionless")),
    _u("percent", _D.DIMENSIONLESS, 0.01, aliases=("%", "pct")),
    # Mass
    _u("kg", _D.MASS, 1.0, aliases=("kilogram", "kilograms")),
    _u("g", _D.MASS, 1e-3, aliases=("gram", "grams")),
    _u("mg", _D.MASS, 1e-6),
    _u("t", _D.MASS, 1e3, aliases=("tonne", "tonnes", "metric_ton")),
    _u("M_sun", _D.MASS, _M_SUN, aliases=("msun", "solar_mass", "m_solar")),
    _u("M_earth", _D.MASS, _M_EARTH, aliases=("mearth", "earth_mass")),
    _u("M_jup", _D.MASS, _M_JUP, aliases=("mjup", "jupiter_mass", "m_jupiter")),
    # Length
    _u("m", _D.LENGTH, 1.0, aliases=("metre", "meter", "metres", "meters")),
    _u("km", _D.LENGTH, 1e3, aliases=("kilometre", "kilometer", "kilometres", "kilometers")),
    _u("cm", _D.LENGTH, 1e-2),
    _u("mm", _D.LENGTH, 1e-3),
    _u("au", _D.LENGTH, _AU, aliases=("astronomical_unit", "a.u.")),
    _u("R_sun", _D.LENGTH, _R_SUN, aliases=("rsun", "solar_radius")),
    _u("R_earth", _D.LENGTH, _R_EARTH, aliases=("rearth", "earth_radius")),
    _u("R_jup", _D.LENGTH, _R_JUP, aliases=("rjup", "jupiter_radius")),
    _u("ly", _D.LENGTH, 9.4607304725808e15, aliases=("light_year", "lightyear")),
    _u("pc", _D.LENGTH, 3.0856775814913673e16, aliases=("parsec",)),
    # Time
    _u("s", _D.TIME, 1.0, aliases=("sec", "secs", "second", "seconds")),
    _u("ms", _D.TIME, 1e-3, aliases=("millisecond", "milliseconds")),
    _u("min", _D.TIME, 60.0, aliases=("minute", "minutes")),
    _u("h", _D.TIME, 3600.0, aliases=("hr", "hour", "hours")),
    _u("d", _D.TIME, 86400.0, aliases=("day", "days")),
    _u("yr", _D.TIME, _JULIAN_YEAR_S, aliases=("year", "years", "a")),
    _u("Myr", _D.TIME, _JULIAN_YEAR_S * 1e6),
    _u("Gyr", _D.TIME, _JULIAN_YEAR_S * 1e9),
    # Temperature (affine)
    _u("K", _D.TEMPERATURE, 1.0, aliases=("kelvin",)),
    _u("degC", _D.TEMPERATURE, 1.0, 273.15, aliases=("c", "celsius", "degreec", "deg_c")),
    _u(
        "degF",
        _D.TEMPERATURE,
        5.0 / 9.0,
        459.67 * 5.0 / 9.0,
        aliases=("f", "fahrenheit", "deg_f"),
    ),
    # Angle
    _u("rad", _D.ANGLE, 1.0, aliases=("radian", "radians")),
    _u("deg", _D.ANGLE, math.pi / 180.0, aliases=("degree", "degrees", "°")),
    _u("arcmin", _D.ANGLE, math.pi / (180.0 * 60.0)),
    _u("arcsec", _D.ANGLE, math.pi / (180.0 * 3600.0), aliases=("as",)),
    _u("mas", _D.ANGLE, math.pi / (180.0 * 3600.0 * 1e3), aliases=("milliarcsec",)),
    _u("rev", _D.ANGLE, 2.0 * math.pi, aliases=("revolution", "revolutions", "turn")),
    # Velocity
    _u("m/s", _D.VELOCITY, 1.0, aliases=("mps", "m s^-1", "m.s-1")),
    _u("km/s", _D.VELOCITY, 1e3, aliases=("kmps", "km s^-1")),
    _u("km/h", _D.VELOCITY, 1.0 / 3.6, aliases=("kph", "kmph")),
    _u("au/d", _D.VELOCITY, _AU / 86400.0, aliases=("au/day",)),
    # Acceleration
    _u("m/s2", _D.ACCELERATION, 1.0, aliases=("m/s^2", "m s^-2", "mps2")),
    _u("km/s2", _D.ACCELERATION, 1e3, aliases=("km/s^2",)),
    _u("g0", _D.ACCELERATION, 9.80665, aliases=("gee", "standard_gravity")),
    # Density
    _u("kg/m3", _D.DENSITY, 1.0, aliases=("kg/m^3", "kg m^-3")),
    _u("g/cm3", _D.DENSITY, 1e3, aliases=("g/cm^3", "g cm^-3")),
    # Pressure
    _u("Pa", _D.PRESSURE, 1.0, aliases=("pascal",)),
    _u("hPa", _D.PRESSURE, 100.0, aliases=("mbar", "millibar")),
    _u("kPa", _D.PRESSURE, 1e3),
    _u("bar", _D.PRESSURE, 1e5),
    _u("atm", _D.PRESSURE, 101325.0, aliases=("atmosphere",)),
    # Area / volume
    _u("m2", _D.AREA, 1.0, aliases=("m^2", "sqm")),
    _u("km2", _D.AREA, 1e6, aliases=("km^2",)),
    _u("m3", _D.VOLUME, 1.0, aliases=("m^3",)),
    _u("km3", _D.VOLUME, 1e9, aliases=("km^3",)),
    # Angular velocity — mean motion arrives as deg/day or rev/day
    _u("rad/s", _D.ANGULAR_VELOCITY, 1.0, aliases=("rad s^-1",)),
    _u("deg/d", _D.ANGULAR_VELOCITY, (math.pi / 180.0) / 86400.0, aliases=("deg/day",)),
    _u("rev/d", _D.ANGULAR_VELOCITY, (2.0 * math.pi) / 86400.0, aliases=("rev/day", "revs/day")),
    # Energy / force
    _u("J", _D.ENERGY, 1.0, aliases=("joule",)),
    _u("kJ", _D.ENERGY, 1e3),
    _u("MJ", _D.ENERGY, 1e6),
    _u("N", _D.FORCE, 1.0, aliases=("newton",)),
    _u("kN", _D.FORCE, 1e3),
    # Irradiance
    _u("W/m2", _D.IRRADIANCE, 1.0, aliases=("W/m^2",)),
    # Magnitude (logarithmic — never convertible to a ratio)
    _u("mag", _D.MAGNITUDE, 1.0, aliases=("magnitude",)),
    # Gravitational parameter
    _u("m3/s2", _D.GRAVITATIONAL_PARAMETER, 1.0, aliases=("m^3/s^2",)),
    _u("km3/s2", _D.GRAVITATIONAL_PARAMETER, 1e9, aliases=("km^3/s^2",)),
    # Inverse length (SGP4 B*)
    _u("1/R_earth", _D.INVERSE_LENGTH, 1.0 / _R_EARTH, aliases=("er^-1", "1/er")),
    _u("1/m", _D.INVERSE_LENGTH, 1.0, aliases=("m^-1",)),
)

#: Canonical (SI) unit per dimension, used when normalizing.
_CANONICAL: Dict[Dimension, str] = {
    _D.DIMENSIONLESS: "1",
    _D.MASS: "kg",
    _D.LENGTH: "m",
    _D.TIME: "s",
    _D.TEMPERATURE: "K",
    _D.ANGLE: "rad",
    _D.VELOCITY: "m/s",
    _D.ACCELERATION: "m/s2",
    _D.DENSITY: "kg/m3",
    _D.PRESSURE: "Pa",
    _D.AREA: "m2",
    _D.VOLUME: "m3",
    _D.ANGULAR_VELOCITY: "rad/s",
    _D.ENERGY: "J",
    _D.FORCE: "N",
    _D.IRRADIANCE: "W/m2",
    _D.MAGNITUDE: "mag",
    _D.GRAVITATIONAL_PARAMETER: "m3/s2",
    _D.INVERSE_LENGTH: "1/m",
}


def _build_lookup():
    table = {}
    for unit in _UNIT_DEFS:
        keys = [unit.symbol] + list(unit.aliases)
        for key in keys:
            normalized = key.strip().lower()
            if normalized in table and table[normalized].symbol != unit.symbol:
                raise RuntimeError(
                    "duplicate unit key {0!r}: {1} vs {2}".format(
                        normalized, table[normalized].symbol, unit.symbol
                    )
                )
            table[normalized] = unit
    return table


_LOOKUP: Dict[str, UnitDef] = _build_lookup()


def get_unit(symbol: str) -> UnitDef:
    """Resolve a unit symbol or alias, case-insensitively."""
    if symbol is None:
        raise UnitError("unit must not be None")
    key = str(symbol).strip().lower()
    try:
        return _LOOKUP[key]
    except KeyError:
        raise UnitError("unknown unit: {0!r}".format(symbol))


def is_known_unit(symbol: str) -> bool:
    try:
        get_unit(symbol)
        return True
    except UnitError:
        return False


def dimension_of(symbol: str) -> Dimension:
    return get_unit(symbol).dimension


def canonical_unit_for(dimension: Dimension) -> str:
    return _CANONICAL[dimension]


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a scalar between two units of the same dimension."""
    src = get_unit(from_unit)
    dst = get_unit(to_unit)
    if src.dimension is not dst.dimension:
        raise UnitError(
            "cannot convert {0} ({1}) to {2} ({3}): different dimensions".format(
                src.symbol, src.dimension.value, dst.symbol, dst.dimension.value
            )
        )
    si = value * src.factor + src.offset
    return (si - dst.offset) / dst.factor


class Quantity(BaseModel):
    """A physical value with its unit, uncertainty and source.

    `uncertainty` is the symmetric 1-sigma value in the same unit as `value`.
    When a source publishes asymmetric error bars, use
    `uncertainty_lower`/`uncertainty_upper` instead — the Exoplanet Archive
    publishes those for most parameters.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: float
    unit: str = "1"
    uncertainty: Optional[float] = Field(default=None, ge=0.0)
    uncertainty_lower: Optional[float] = Field(default=None, ge=0.0)
    uncertainty_upper: Optional[float] = Field(default=None, ge=0.0)
    #: Where this specific number came from. Records assembled from multiple
    #: archives keep per-value attribution here.
    source: Optional[SourceReference] = None

    @field_validator("value", "uncertainty", "uncertainty_lower", "uncertainty_upper")
    @classmethod
    def _finite(cls, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            raise ValueError("physical values must be finite, got {0!r}".format(value))
        return number

    @field_validator("unit")
    @classmethod
    def _known_unit(cls, value: str) -> str:
        return get_unit(value).symbol

    @model_validator(mode="after")
    def _consistent_uncertainty(self) -> "Quantity":
        symmetric = self.uncertainty is not None
        asymmetric = self.uncertainty_lower is not None or self.uncertainty_upper is not None
        if symmetric and asymmetric:
            raise ValueError(
                "specify either `uncertainty` or `uncertainty_lower`/`uncertainty_upper`, "
                "not both"
            )
        return self

    # -- introspection -----------------------------------------------------
    @property
    def dimension(self) -> Dimension:
        return get_unit(self.unit).dimension

    @property
    def has_uncertainty(self) -> bool:
        return (
            self.uncertainty is not None
            or self.uncertainty_lower is not None
            or self.uncertainty_upper is not None
        )

    # -- conversion --------------------------------------------------------
    def to(self, unit: str) -> "Quantity":
        """Return this quantity expressed in `unit`, converting uncertainties.

        Uncertainties scale by the factor ratio only: an affine offset shifts
        the value but not the width of the error bar.
        """
        target = get_unit(unit)
        source_def = get_unit(self.unit)
        if source_def.dimension is not target.dimension:
            raise UnitError(
                "cannot convert {0} ({1}) to {2} ({3}): different dimensions".format(
                    source_def.symbol,
                    source_def.dimension.value,
                    target.symbol,
                    target.dimension.value,
                )
            )
        ratio = source_def.factor / target.factor

        def _scale(component):
            return None if component is None else component * ratio

        return Quantity(
            value=convert(self.value, self.unit, target.symbol),
            unit=target.symbol,
            uncertainty=_scale(self.uncertainty),
            uncertainty_lower=_scale(self.uncertainty_lower),
            uncertainty_upper=_scale(self.uncertainty_upper),
            source=self.source,
        )

    def to_si(self) -> "Quantity":
        """Return this quantity in the canonical SI unit for its dimension."""
        return self.to(canonical_unit_for(self.dimension))

    def si_value(self) -> float:
        """Numeric value in canonical SI units."""
        return convert(self.value, self.unit, canonical_unit_for(self.dimension))

    def with_source(self, source: SourceReference) -> "Quantity":
        """Return a copy carrying `source`. Quantities are immutable."""
        return self.model_copy(update={"source": source})

    def approx_equals(self, other: "Quantity", rel_tol: float = 1e-9) -> bool:
        """Dimension-aware numeric comparison, unit-independent."""
        if not isinstance(other, Quantity):
            return False
        if self.dimension is not other.dimension:
            return False
        return math.isclose(self.si_value(), other.si_value(), rel_tol=rel_tol, abs_tol=0.0)

    def __str__(self) -> str:
        text = "{0:g}".format(self.value)
        if self.uncertainty is not None:
            text += " ± {0:g}".format(self.uncertainty)
        elif self.uncertainty_upper is not None or self.uncertainty_lower is not None:
            text += " +{0:g}/-{1:g}".format(
                self.uncertainty_upper or 0.0, self.uncertainty_lower or 0.0
            )
        if self.unit != "1":
            text += " {0}".format(self.unit)
        return text
