"""Orbital and ephemeris records.

Orbital data is *not* stored as a generic JSON blob. Each element is a typed
`Quantity` with its own uncertainty, and every record carries the frame context
needed to interpret it: epoch, time scale, reference frame, coordinate system,
origin type and central body.

The two rules this module exists to enforce:

1. Heliocentric, geocentric, topocentric and barycentric data may coexist, but
   never without recording which is which (`FrameContext`).
2. Osculating Keplerian elements and SGP4 mean elements are different things
   even though they share field names (`ElementTheory`).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts._time import as_utc

from .base import CanonicalRecord, require_dimensions
from .enums import (
    CoordinateSystem,
    ElementTheory,
    OriginType,
    ReferenceFrame,
    TimeScale,
)
from .units import Dimension, Quantity

__all__ = [
    "FrameContext",
    "OrbitalElements",
    "Covariance",
    "OrbitFitInfo",
    "OrbitRecord",
    "StateVector",
    "EphemerisRecord",
]

_D = Dimension

#: Central bodies each origin type is allowed to name. Guards against the
#: classic "heliocentric elements centred on Earth" mislabelling.
_ORIGIN_CENTERS = {
    OriginType.HELIOCENTRIC: {"sun"},
    OriginType.GEOCENTRIC: {"earth"},
    OriginType.BARYCENTRIC: {
        "ssb",
        "solar system barycenter",
        "sun-earth barycenter",
        "earth-moon barycenter",
    },
}


class FrameContext(BaseModel):
    """Everything needed to interpret a set of coordinates.

    Required on every orbit, ephemeris and observation record. Without it,
    numbers that look comparable are not.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin_type: OriginType
    #: Lowercase name of the central body / origin, e.g. "sun", "earth", "ssb".
    center_body: str = Field(min_length=1)
    reference_frame: ReferenceFrame = ReferenceFrame.UNKNOWN
    coordinate_system: CoordinateSystem = CoordinateSystem.KEPLERIAN
    time_scale: TimeScale = TimeScale.UNKNOWN
    #: MPC observatory code, required for topocentric data.
    observatory_code: Optional[str] = None
    observatory_name: Optional[str] = None

    @field_validator("center_body")
    @classmethod
    def _normalize_center(cls, value: str) -> str:
        return " ".join(str(value).split()).lower()

    @model_validator(mode="after")
    def _check(self) -> "FrameContext":
        allowed = _ORIGIN_CENTERS.get(self.origin_type)
        if allowed is not None and self.center_body not in allowed:
            raise ValueError(
                "origin_type {0} requires center_body in {1}, got {2!r}".format(
                    self.origin_type.value, sorted(allowed), self.center_body
                )
            )
        if self.origin_type is OriginType.TOPOCENTRIC and not (
            self.observatory_code or self.observatory_name
        ):
            raise ValueError(
                "topocentric data requires observatory_code or observatory_name; "
                "without an observing site the coordinates cannot be reduced"
            )
        return self

    def describe(self) -> str:
        """Short human-readable frame description for display and citations."""
        parts = [
            self.origin_type.value.lower(),
            self.coordinate_system.value.lower(),
            "centred on {0}".format(self.center_body),
        ]
        if self.reference_frame is not ReferenceFrame.UNKNOWN:
            parts.append("frame {0}".format(self.reference_frame.value))
        if self.time_scale is not TimeScale.UNKNOWN:
            parts.append("epoch in {0}".format(self.time_scale.value))
        if self.observatory_code:
            parts.append("site {0}".format(self.observatory_code))
        return ", ".join(parts)

    def is_comparable_to(self, other: "FrameContext") -> bool:
        """True when two records may be numerically compared without conversion."""
        return (
            self.origin_type is other.origin_type
            and self.center_body == other.center_body
            and self.reference_frame is other.reference_frame
            and self.coordinate_system is other.coordinate_system
        )


class OrbitalElements(BaseModel):
    """Orbital elements as individually typed, individually sourced values.

    Includes the SGP4-specific drag terms because dropping them would make a
    CelesTrak element set unusable for propagation — `ElementTheory` on the
    parent record records which theory they belong to.
    """

    model_config = ConfigDict(extra="forbid")

    semi_major_axis: Optional[Quantity] = None
    eccentricity: Optional[Quantity] = None
    inclination: Optional[Quantity] = None
    #: Right ascension / longitude of the ascending node.
    ascending_node_longitude: Optional[Quantity] = None
    argument_of_periapsis: Optional[Quantity] = None
    mean_anomaly: Optional[Quantity] = None
    true_anomaly: Optional[Quantity] = None

    periapsis_distance: Optional[Quantity] = None
    apoapsis_distance: Optional[Quantity] = None
    orbital_period: Optional[Quantity] = None
    mean_motion: Optional[Quantity] = None

    #: Time of periapsis passage — comets are usually catalogued by this.
    periapsis_time: Optional[datetime] = None

    # -- SGP4 / general-perturbation specific ------------------------------
    #: B* drag term (inverse length). Meaningless outside SGP4.
    bstar: Optional[Quantity] = None
    mean_motion_dot: Optional[float] = None
    mean_motion_ddot: Optional[float] = None
    revolution_number_at_epoch: Optional[int] = None

    @field_validator("periapsis_time")
    @classmethod
    def _utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return as_utc(value)

    @model_validator(mode="after")
    def _check(self) -> "OrbitalElements":
        require_dimensions(
            self,
            {
                "semi_major_axis": _D.LENGTH,
                "eccentricity": _D.DIMENSIONLESS,
                "inclination": _D.ANGLE,
                "ascending_node_longitude": _D.ANGLE,
                "argument_of_periapsis": _D.ANGLE,
                "mean_anomaly": _D.ANGLE,
                "true_anomaly": _D.ANGLE,
                "periapsis_distance": _D.LENGTH,
                "apoapsis_distance": _D.LENGTH,
                "orbital_period": _D.TIME,
                "mean_motion": _D.ANGULAR_VELOCITY,
                "bstar": _D.INVERSE_LENGTH,
            },
        )
        if self.eccentricity is not None:
            ecc = self.eccentricity.to("1").value
            if ecc < 0.0:
                raise ValueError("eccentricity must not be negative, got {0}".format(ecc))
        if self.periapsis_distance is not None and self.apoapsis_distance is not None:
            if self.periapsis_distance.si_value() > self.apoapsis_distance.si_value():
                raise ValueError("periapsis_distance exceeds apoapsis_distance")
        return self

    @property
    def is_closed_orbit(self) -> Optional[bool]:
        """True for elliptical orbits, False for parabolic/hyperbolic, else `None`."""
        if self.eccentricity is None:
            return None
        return self.eccentricity.to("1").value < 1.0

    def provided_element_names(self) -> List[str]:
        """Names of the elements this set actually carries."""
        return [
            name
            for name in (
                "semi_major_axis",
                "eccentricity",
                "inclination",
                "ascending_node_longitude",
                "argument_of_periapsis",
                "mean_anomaly",
                "true_anomaly",
                "periapsis_distance",
                "apoapsis_distance",
                "orbital_period",
                "mean_motion",
            )
            if getattr(self, name) is not None
        ]


class Covariance(BaseModel):
    """Covariance matrix supplied by a source, with labelled axes and units.

    Stored only when the source publishes it. A covariance without labels is
    unusable, so labels are required and must match the matrix dimensions.
    """

    model_config = ConfigDict(extra="forbid")

    #: Element names, in matrix order (e.g. ["e", "q", "tp", "node", "peri", "i"]).
    labels: List[str] = Field(min_length=1)
    #: Unit of each labelled element, same order as `labels`.
    units: List[str] = Field(default_factory=list)
    matrix: List[List[float]]
    #: Epoch the covariance applies at, when it differs from the orbit epoch.
    epoch: Optional[datetime] = None
    notes: Optional[str] = None

    @field_validator("epoch")
    @classmethod
    def _utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return as_utc(value)

    @model_validator(mode="after")
    def _check(self) -> "Covariance":
        size = len(self.labels)
        if len(self.matrix) != size:
            raise ValueError(
                "covariance matrix has {0} rows but {1} labels".format(len(self.matrix), size)
            )
        for index, row in enumerate(self.matrix):
            if len(row) != size:
                raise ValueError(
                    "covariance row {0} has {1} entries, expected {2}".format(
                        index, len(row), size
                    )
                )
        if self.units and len(self.units) != size:
            raise ValueError(
                "covariance units has {0} entries but {1} labels".format(len(self.units), size)
            )
        # Symmetry with a generous relative tolerance: sources round the values
        # they publish, so exact symmetry is not expected.
        for i in range(size):
            for j in range(i + 1, size):
                upper = self.matrix[i][j]
                lower = self.matrix[j][i]
                scale = max(abs(upper), abs(lower), 1e-300)
                if abs(upper - lower) / scale > 1e-6:
                    raise ValueError(
                        "covariance matrix is not symmetric at ({0},{1}): {2} vs {3}".format(
                            i, j, upper, lower
                        )
                    )
        for i in range(size):
            if self.matrix[i][i] < 0.0:
                raise ValueError(
                    "covariance diagonal entry {0} ({1}) is negative; variances cannot "
                    "be negative".format(i, self.labels[i])
                )
        return self

    def sigma(self, label: str) -> Optional[float]:
        """1-sigma uncertainty for one labelled element, in that element's unit."""
        if label not in self.labels:
            return None
        index = self.labels.index(label)
        variance = self.matrix[index][index]
        return variance ** 0.5


class OrbitFitInfo(BaseModel):
    """Quality metadata for an orbit solution.

    This is what distinguishes a well-determined orbit from a two-night arc.
    """

    model_config = ConfigDict(extra="forbid")

    observations_used: Optional[int] = None
    #: Length of the observed arc, in days.
    data_arc_days: Optional[float] = None
    first_observation: Optional[datetime] = None
    last_observation: Optional[datetime] = None
    rms_residual_arcsec: Optional[float] = None
    #: MPC/JPL orbit condition code, 0 (best) to 9 (worst), when published.
    condition_code: Optional[str] = None
    solution_date: Optional[datetime] = None
    solution_id: Optional[str] = None

    @field_validator("first_observation", "last_observation", "solution_date")
    @classmethod
    def _utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return as_utc(value)

    @model_validator(mode="after")
    def _check(self) -> "OrbitFitInfo":
        if self.first_observation and self.last_observation:
            if self.first_observation > self.last_observation:
                raise ValueError("first_observation is after last_observation")
        if self.observations_used is not None and self.observations_used < 0:
            raise ValueError("observations_used must not be negative")
        return self


class OrbitRecord(CanonicalRecord):
    """One orbit solution for one object, at one epoch, from one source.

    Multiple `OrbitRecord`s for the same object are expected and normal — a JPL
    osculating solution and a CelesTrak SGP4 element set are both valid and are
    kept separately rather than merged.
    """

    record_type: str = "orbit_record"

    #: Canonical id of the object this orbit describes.
    object_canonical_id: str
    #: The designation the source used, kept verbatim for traceability.
    source_designation: Optional[str] = None

    #: Epoch of the elements. Interpreted in `frame.time_scale`.
    epoch: datetime
    frame: FrameContext
    element_theory: ElementTheory = ElementTheory.UNKNOWN
    elements: OrbitalElements

    covariance: Optional[Covariance] = None
    fit: Optional[OrbitFitInfo] = None
    #: Dynamical class the source assigns, e.g. "APO", "MBA", "JFc".
    orbit_class: Optional[str] = None
    orbit_class_description: Optional[str] = None

    #: Window in which this solution is intended to be used, when the source
    #: states one. Outside it, the record is historical, not current.
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None

    @field_validator("epoch", "valid_from", "valid_until")
    @classmethod
    def _utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return as_utc(value)

    @model_validator(mode="after")
    def _check(self) -> "OrbitRecord":
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValueError("valid_from is after valid_until")
        if self.frame.coordinate_system is CoordinateSystem.CARTESIAN:
            raise ValueError(
                "OrbitRecord holds element sets; use EphemerisRecord for Cartesian states"
            )
        if self.element_theory is ElementTheory.SGP4_MEAN:
            if self.frame.origin_type is not OriginType.GEOCENTRIC:
                raise ValueError(
                    "SGP4 mean elements are geocentric by definition, got origin_type "
                    "{0}".format(self.frame.origin_type.value)
                )
            if self.frame.reference_frame not in (ReferenceFrame.TEME, ReferenceFrame.UNKNOWN):
                raise ValueError(
                    "SGP4 mean elements are expressed in TEME, got {0}".format(
                        self.frame.reference_frame.value
                    )
                )
        if self.elements.bstar is not None and self.element_theory is not ElementTheory.SGP4_MEAN:
            raise ValueError(
                "a B* drag term is only meaningful for SGP4 mean elements; "
                "element_theory is {0}".format(self.element_theory.value)
            )
        return self

    def temporal_anchor(self) -> Optional[datetime]:
        """An orbit's content describes its epoch, not its retrieval time."""
        return self.epoch

    def describe_context(self) -> str:
        """One-line statement of what this orbit actually is."""
        return "{0} elements at epoch {1} ({2})".format(
            self.element_theory.value.replace("_", " ").lower(),
            self.epoch.isoformat(),
            self.frame.describe(),
        )


class StateVector(BaseModel):
    """A position/velocity state at one instant.

    Components stay as separate `Quantity` values so units and precision are
    preserved; they are never flattened into a bare "position" triple.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    epoch: datetime
    x: Quantity
    y: Quantity
    z: Quantity
    vx: Optional[Quantity] = None
    vy: Optional[Quantity] = None
    vz: Optional[Quantity] = None
    #: One-way light time to the target, when the source reports it.
    light_time: Optional[Quantity] = None
    range_: Optional[Quantity] = Field(default=None, alias="range")
    range_rate: Optional[Quantity] = None

    @field_validator("epoch")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return as_utc(value)

    @model_validator(mode="after")
    def _check(self) -> "StateVector":
        require_dimensions(
            self,
            {
                "x": _D.LENGTH,
                "y": _D.LENGTH,
                "z": _D.LENGTH,
                "vx": _D.VELOCITY,
                "vy": _D.VELOCITY,
                "vz": _D.VELOCITY,
                "light_time": _D.TIME,
                "range_": _D.LENGTH,
                "range_rate": _D.VELOCITY,
            },
        )
        velocity = (self.vx, self.vy, self.vz)
        if any(component is not None for component in velocity) and not all(
            component is not None for component in velocity
        ):
            raise ValueError("velocity must be fully specified (vx, vy, vz) or omitted entirely")
        return self

    @property
    def has_velocity(self) -> bool:
        return self.vx is not None and self.vy is not None and self.vz is not None

    def position_si(self):
        """Position triple in metres."""
        return (self.x.si_value(), self.y.si_value(), self.z.si_value())

    def velocity_si(self):
        """Velocity triple in m/s, or `None` when no velocity was supplied."""
        if not self.has_velocity:
            return None
        return (self.vx.si_value(), self.vy.si_value(), self.vz.si_value())


class EphemerisRecord(CanonicalRecord):
    """A computed ephemeris: a target's states relative to an observer.

    The query that produced it is stored verbatim, because an ephemeris is only
    reproducible if the request is known.
    """

    record_type: str = "ephemeris_record"

    #: Canonical id of the target body.
    target_canonical_id: str
    target_designation: Optional[str] = None
    #: Observer/centre used for the computation, as the source names it.
    observer: str = Field(min_length=1)
    frame: FrameContext

    start_time: Optional[datetime] = None
    stop_time: Optional[datetime] = None
    step_size: Optional[str] = None

    states: List[StateVector] = Field(default_factory=list)

    #: Exact request parameters, so the result can be reproduced or refreshed.
    query_parameters: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("start_time", "stop_time")
    @classmethod
    def _utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return as_utc(value)

    @model_validator(mode="after")
    def _check(self) -> "EphemerisRecord":
        if self.start_time and self.stop_time and self.start_time > self.stop_time:
            raise ValueError("start_time is after stop_time")
        if self.frame.coordinate_system not in (
            CoordinateSystem.CARTESIAN,
            CoordinateSystem.SPHERICAL,
            CoordinateSystem.OBSERVED_ANGLES,
        ):
            raise ValueError(
                "EphemerisRecord holds states, so coordinate_system must be CARTESIAN, "
                "SPHERICAL or OBSERVED_ANGLES, got {0}".format(
                    self.frame.coordinate_system.value
                )
            )
        for state in self.states:
            if self.start_time and state.epoch < self.start_time:
                raise ValueError(
                    "state at {0} is before start_time {1}".format(
                        state.epoch.isoformat(), self.start_time.isoformat()
                    )
                )
            if self.stop_time and state.epoch > self.stop_time:
                raise ValueError(
                    "state at {0} is after stop_time {1}".format(
                        state.epoch.isoformat(), self.stop_time.isoformat()
                    )
                )
        return self

    def temporal_anchor(self) -> Optional[datetime]:
        """An ephemeris describes the span it covers; anchor on its start."""
        if self.start_time is not None:
            return self.start_time
        span = self.epoch_range
        return span[0] if span else self.valid_at

    @property
    def epoch_range(self):
        """(first, last) state epoch, or `None` when there are no states."""
        if not self.states:
            return None
        epochs = [state.epoch for state in self.states]
        return (min(epochs), max(epochs))

    def describe_context(self) -> str:
        return "{0} states of {1} relative to {2} ({3})".format(
            len(self.states), self.target_designation or self.target_canonical_id,
            self.observer, self.frame.describe(),
        )
