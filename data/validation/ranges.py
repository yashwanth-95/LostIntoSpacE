"""Plausible ranges for scientific values.

These are sanity bounds, not measurements. They exist to catch the errors that
actually happen — a unit slip, a sign flip, a parser reading the wrong column —
not to second-guess an archive's physics.

Bounds are deliberately generous. A warning that fires on real data is worse
than useless, because people learn to ignore it.
"""

from typing import Dict, Optional, Tuple

from pydantic import BaseModel, ConfigDict

__all__ = ["RangeRule", "SI_RANGES", "OBJECT_TYPE_RANGES", "range_for"]


class RangeRule(BaseModel):
    """A plausible range for one field, expressed in canonical SI units."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Values outside [error_min, error_max] are almost certainly wrong.
    error_min: Optional[float] = None
    error_max: Optional[float] = None
    #: Values outside [warn_min, warn_max] are suspicious but possible.
    warn_min: Optional[float] = None
    warn_max: Optional[float] = None
    note: Optional[str] = None

    def classify(self, value: float) -> Optional[str]:
        """`"error"`, `"warning"` or `None`."""
        if self.error_min is not None and value < self.error_min:
            return "error"
        if self.error_max is not None and value > self.error_max:
            return "error"
        if self.warn_min is not None and value < self.warn_min:
            return "warning"
        if self.warn_max is not None and value > self.warn_max:
            return "warning"
        return None

    def describe(self) -> str:
        parts = []
        if self.error_min is not None or self.error_max is not None:
            parts.append(
                "plausible range [{0}, {1}]".format(self.error_min, self.error_max)
            )
        if self.note:
            parts.append(self.note)
        return "; ".join(parts) or "no bounds"


#: Field path -> range, in SI units. Field paths are relative to the record.
SI_RANGES: Dict[str, RangeRule] = {
    # -- mass (kg) -------------------------------------------------------
    "physical.mass": RangeRule(
        error_min=1e3,
        error_max=1e35,
        warn_max=1e33,
        note="from a small asteroid to a very massive star",
    ),
    # -- lengths (m) -----------------------------------------------------
    "physical.radius_mean": RangeRule(error_min=1.0, error_max=1e13),
    "physical.radius_equatorial": RangeRule(error_min=1.0, error_max=1e13),
    "physical.radius_polar": RangeRule(error_min=1.0, error_max=1e13),
    "physical.diameter": RangeRule(error_min=1.0, error_max=1e13),
    # -- density (kg/m^3) ------------------------------------------------
    "physical.density": RangeRule(
        error_min=10.0,
        error_max=1e5,
        warn_min=200.0,
        warn_max=3e4,
        note="comet nuclei are ~300; the densest solids are ~22600",
    ),
    # -- gravity (m/s^2) -------------------------------------------------
    "physical.surface_gravity": RangeRule(error_min=1e-6, error_max=1e6),
    "physical.escape_velocity": RangeRule(error_min=1e-4, error_max=3e8,
                                          note="cannot exceed the speed of light"),
    # -- temperature (K) -------------------------------------------------
    "physical.mean_temperature": RangeRule(error_min=0.0, error_max=1e6, warn_max=1e5),
    "physical.min_temperature": RangeRule(error_min=0.0, error_max=1e6),
    "physical.max_temperature": RangeRule(error_min=0.0, error_max=1e6),
    "physical.effective_temperature": RangeRule(error_min=0.0, error_max=1e6),
    "equilibrium_temperature": RangeRule(error_min=0.0, error_max=1e5),
    # -- dimensionless ---------------------------------------------------
    "physical.geometric_albedo": RangeRule(
        error_min=0.0,
        error_max=2.0,
        warn_max=1.0,
        note="albedo above 1 occurs for a few icy bodies but is rare",
    ),
    "physical.flattening": RangeRule(error_min=0.0, error_max=1.0),
    # -- magnitudes ------------------------------------------------------
    "physical.absolute_magnitude": RangeRule(error_min=-30.0, error_max=40.0),
    # -- rotation --------------------------------------------------------
    "physical.rotation.sidereal_rotation_period": RangeRule(
        error_min=1.0,
        error_max=1e10,
        warn_min=60.0,
        note="the fastest known rotators are minutes, not seconds",
    ),
    "physical.rotation.axial_tilt": RangeRule(error_min=0.0, error_max=3.15),
    # -- orbital elements (SI: m, rad, s) --------------------------------
    "orbits.elements.semi_major_axis": RangeRule(error_min=1.0, error_max=1e18),
    "orbits.elements.periapsis_distance": RangeRule(error_min=1.0, error_max=1e18),
    "orbits.elements.apoapsis_distance": RangeRule(error_min=1.0, error_max=1e18),
    "orbits.elements.eccentricity": RangeRule(
        error_min=0.0, error_max=100.0, warn_max=1.0,
        note="e >= 1 is an unbound orbit; valid but worth flagging",
    ),
    "orbits.elements.inclination": RangeRule(
        error_min=0.0, error_max=3.15, note="0 to pi radians",
    ),
    "orbits.elements.ascending_node_longitude": RangeRule(error_min=0.0, error_max=6.30),
    "orbits.elements.argument_of_periapsis": RangeRule(error_min=0.0, error_max=6.30),
    "orbits.elements.mean_anomaly": RangeRule(error_min=0.0, error_max=6.30),
    "orbits.elements.orbital_period": RangeRule(error_min=1.0, error_max=1e15),
    "orbits.elements.mean_motion": RangeRule(error_min=0.0, error_max=1.0),
    # -- EO --------------------------------------------------------------
    "cloud_cover": RangeRule(error_min=0.0, error_max=1.0),
}

#: Additional bounds that apply only to specific object types, layered on top of
#: the generic ones. Keyed by `ObjectType` value.
OBJECT_TYPE_RANGES: Dict[str, Dict[str, RangeRule]] = {
    "PLANET": {
        "physical.mass": RangeRule(error_min=1e20, error_max=1e29,
                                   note="planetary masses"),
    },
    "STAR": {
        "physical.mass": RangeRule(error_min=1e28, error_max=1e33,
                                   note="stellar masses"),
        "physical.effective_temperature": RangeRule(error_min=500.0, error_max=2e5),
    },
    "ASTEROID": {
        "physical.diameter": RangeRule(error_min=1.0, error_max=2e6,
                                       note="the largest minor planet is ~940 km"),
    },
    "SATELLITE": {
        "orbits.elements.eccentricity": RangeRule(error_min=0.0, error_max=1.0),
    },
    "SPACE_STATION": {
        "orbits.elements.eccentricity": RangeRule(error_min=0.0, error_max=1.0),
    },
}


def range_for(field: str, object_type: Optional[str] = None) -> Optional[RangeRule]:
    """The rule for `field`, preferring an object-type-specific one."""
    if object_type:
        specific = OBJECT_TYPE_RANGES.get(object_type, {}).get(field)
        if specific is not None:
            return specific
    return SI_RANGES.get(field)
