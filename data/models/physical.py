"""Physical properties of space objects.

Every value is a `Quantity`, and every field declares the dimension it must
have. A record that puts a mass in a radius field fails validation instead of
propagating into the search index.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .base import require_dimensions
from .units import Dimension, Quantity

__all__ = [
    "CompositionComponent",
    "Composition",
    "AtmosphereProfile",
    "RotationProperties",
    "PhysicalProperties",
]

_D = Dimension


class CompositionComponent(BaseModel):
    """One constituent of a composition, as a fraction of the whole."""

    model_config = ConfigDict(extra="forbid")

    species: str = Field(min_length=1)
    #: Abundance as a dimensionless fraction or a percentage.
    fraction: Optional[Quantity] = None
    #: Free-text qualifier when a source gives "trace" rather than a number.
    qualifier: Optional[str] = None

    @model_validator(mode="after")
    def _check(self) -> "CompositionComponent":
        require_dimensions(self, {"fraction": _D.DIMENSIONLESS})
        if self.fraction is None and not self.qualifier:
            raise ValueError(
                "composition component {0!r} needs either a fraction or a "
                "qualifier".format(self.species)
            )
        return self


class Composition(BaseModel):
    """A set of constituents plus what they are a composition *of*.

    `basis` matters: an atmospheric composition and a bulk composition for the
    same body are different measurements and must not be merged.
    """

    model_config = ConfigDict(extra="forbid")

    #: One of "bulk", "atmosphere", "surface", "crust", "core", "coma".
    basis: str = "bulk"
    components: List[CompositionComponent] = Field(default_factory=list)
    notes: Optional[str] = None

    def total_fraction(self) -> Optional[float]:
        """Sum of known fractions as a dimensionless value, or `None`.

        Returns `None` when no component carries a number — a composition of
        purely qualitative entries has no meaningful total.
        """
        values = [
            component.fraction.to("1").value
            for component in self.components
            if component.fraction is not None
        ]
        if not values:
            return None
        return sum(values)


class AtmosphereProfile(BaseModel):
    """Atmospheric properties. `present=False` is a real, useful statement."""

    model_config = ConfigDict(extra="forbid")

    present: Optional[bool] = None
    surface_pressure: Optional[Quantity] = None
    scale_height: Optional[Quantity] = None
    mean_molecular_mass: Optional[Quantity] = None
    surface_temperature: Optional[Quantity] = None
    composition: Optional[Composition] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _check(self) -> "AtmosphereProfile":
        require_dimensions(
            self,
            {
                "surface_pressure": _D.PRESSURE,
                "scale_height": _D.LENGTH,
                "mean_molecular_mass": _D.MASS,
                "surface_temperature": _D.TEMPERATURE,
            },
        )
        if self.composition is not None and self.composition.basis != "atmosphere":
            raise ValueError(
                "AtmosphereProfile.composition must have basis='atmosphere', got "
                "{0!r}".format(self.composition.basis)
            )
        return self


class RotationProperties(BaseModel):
    """Spin state."""

    model_config = ConfigDict(extra="forbid")

    sidereal_rotation_period: Optional[Quantity] = None
    angular_velocity: Optional[Quantity] = None
    axial_tilt: Optional[Quantity] = None
    #: Orientation of the spin axis (ICRF right ascension / declination).
    pole_right_ascension: Optional[Quantity] = None
    pole_declination: Optional[Quantity] = None
    is_tidally_locked: Optional[bool] = None
    #: True when the body rotates opposite to its orbital direction.
    is_retrograde: Optional[bool] = None

    @model_validator(mode="after")
    def _check(self) -> "RotationProperties":
        require_dimensions(
            self,
            {
                "sidereal_rotation_period": _D.TIME,
                "angular_velocity": _D.ANGULAR_VELOCITY,
                "axial_tilt": _D.ANGLE,
                "pole_right_ascension": _D.ANGLE,
                "pole_declination": _D.ANGLE,
            },
        )
        return self


class PhysicalProperties(BaseModel):
    """Bulk physical parameters of a body.

    All fields are optional: sources publish wildly different subsets, and an
    absent value must stay absent rather than being defaulted to zero.
    """

    model_config = ConfigDict(extra="forbid")

    mass: Optional[Quantity] = None
    #: Standard gravitational parameter. More precisely known than mass for
    #: most bodies, so it is stored rather than derived.
    gm: Optional[Quantity] = None

    radius_mean: Optional[Quantity] = None
    radius_equatorial: Optional[Quantity] = None
    radius_polar: Optional[Quantity] = None
    diameter: Optional[Quantity] = None
    flattening: Optional[Quantity] = None

    volume: Optional[Quantity] = None
    density: Optional[Quantity] = None
    surface_gravity: Optional[Quantity] = None
    escape_velocity: Optional[Quantity] = None

    mean_temperature: Optional[Quantity] = None
    min_temperature: Optional[Quantity] = None
    max_temperature: Optional[Quantity] = None
    effective_temperature: Optional[Quantity] = None

    geometric_albedo: Optional[Quantity] = None
    absolute_magnitude: Optional[Quantity] = None
    #: Asteroid photometric slope parameter G.
    magnitude_slope: Optional[Quantity] = None

    rotation: Optional[RotationProperties] = None
    atmosphere: Optional[AtmosphereProfile] = None
    #: Bulk/surface composition. Atmospheric composition lives on `atmosphere`.
    composition: Optional[Composition] = None

    #: Additional typed physical values a source publishes that have no
    #: canonical field yet. Keeps scientific content instead of dropping it.
    extra: Dict[str, Quantity] = Field(default_factory=dict)

    @field_validator("extra")
    @classmethod
    def _extra_are_quantities(cls, value: Dict[str, Quantity]) -> Dict[str, Quantity]:
        for key, item in (value or {}).items():
            if not isinstance(item, Quantity):
                raise ValueError(
                    "PhysicalProperties.extra[{0!r}] must be a Quantity so its unit "
                    "and source survive".format(key)
                )
        return value

    @model_validator(mode="after")
    def _check(self) -> "PhysicalProperties":
        require_dimensions(
            self,
            {
                "mass": _D.MASS,
                "gm": _D.GRAVITATIONAL_PARAMETER,
                "radius_mean": _D.LENGTH,
                "radius_equatorial": _D.LENGTH,
                "radius_polar": _D.LENGTH,
                "diameter": _D.LENGTH,
                "flattening": _D.DIMENSIONLESS,
                "volume": _D.VOLUME,
                "density": _D.DENSITY,
                "surface_gravity": _D.ACCELERATION,
                "escape_velocity": _D.VELOCITY,
                "mean_temperature": _D.TEMPERATURE,
                "min_temperature": _D.TEMPERATURE,
                "max_temperature": _D.TEMPERATURE,
                "effective_temperature": _D.TEMPERATURE,
                "geometric_albedo": _D.DIMENSIONLESS,
                "absolute_magnitude": _D.MAGNITUDE,
                "magnitude_slope": _D.DIMENSIONLESS,
            },
        )
        if self.composition is not None and self.composition.basis == "atmosphere":
            raise ValueError(
                "atmospheric composition belongs on PhysicalProperties.atmosphere."
                "composition, not PhysicalProperties.composition"
            )
        if self.min_temperature is not None and self.max_temperature is not None:
            if self.min_temperature.si_value() > self.max_temperature.si_value():
                raise ValueError("min_temperature exceeds max_temperature")
        if self.radius_polar is not None and self.radius_equatorial is not None:
            if self.radius_polar.si_value() > self.radius_equatorial.si_value():
                raise ValueError(
                    "radius_polar exceeds radius_equatorial; the values are probably swapped"
                )
        return self

    def effective_radius(self) -> Optional[Quantity]:
        """Best available radius: mean, else equatorial, else diameter/2."""
        if self.radius_mean is not None:
            return self.radius_mean
        if self.radius_equatorial is not None:
            return self.radius_equatorial
        if self.diameter is not None:
            halved = self.diameter.to_si()
            return Quantity(
                value=halved.value / 2.0,
                unit=halved.unit,
                uncertainty=None if halved.uncertainty is None else halved.uncertainty / 2.0,
                source=halved.source,
            )
        return None
