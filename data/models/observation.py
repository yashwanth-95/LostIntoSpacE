"""Observation records.

An observation is a *measurement*, not a solution. `is_orbital_solution` is
False and cannot be set True unless the source itself publishes the record as a
fitted orbit — this is the rule that stops raw MPC astrometry being presented as
an orbit determination.
"""

from datetime import datetime
from typing import Optional

from pydantic import ConfigDict, Field, field_validator, model_validator

from contracts._time import as_utc

from .base import CanonicalRecord, require_dimensions
from .enums import ObservationType, OriginType
from .orbit import FrameContext
from .units import Dimension, Quantity

__all__ = ["Observation"]

_D = Dimension


class Observation(CanonicalRecord):
    """A single observation of an object by one observatory at one time."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    record_type: str = "observation"

    #: Canonical id of the observed object.
    object_canonical_id: str
    #: Designation exactly as the observation record carries it.
    source_designation: Optional[str] = None
    #: MPC packed designation, when present.
    packed_designation: Optional[str] = None

    observed_at: datetime
    observation_type: ObservationType = ObservationType.UNKNOWN
    #: Frame the measurement is expressed in. Astrometry is topocentric, so the
    #: observatory code is mandatory there via `FrameContext`.
    frame: FrameContext

    right_ascension: Optional[Quantity] = None
    declination: Optional[Quantity] = None
    magnitude: Optional[Quantity] = None
    #: Photometric band the magnitude was measured in, e.g. "V", "R", "G".
    magnitude_band: Optional[str] = None

    #: Radar measurements report range and range rate instead of angles.
    range_: Optional[Quantity] = Field(default=None, alias="range")
    range_rate: Optional[Quantity] = None

    #: True when the source flags this as a discovery observation.
    is_discovery: bool = False

    #: Raw observation notes/codes the source supplies (MPC note1/note2, etc.).
    note: Optional[str] = None
    program_code: Optional[str] = None
    catalog_code: Optional[str] = None

    @field_validator("observed_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return as_utc(value)

    @model_validator(mode="after")
    def _check(self) -> "Observation":
        require_dimensions(
            self,
            {
                "right_ascension": _D.ANGLE,
                "declination": _D.ANGLE,
                "magnitude": _D.MAGNITUDE,
                "range_": _D.LENGTH,
                "range_rate": _D.VELOCITY,
            },
        )
        if self.declination is not None:
            degrees = self.declination.to("deg").value
            if degrees < -90.0 or degrees > 90.0:
                raise ValueError(
                    "declination must be within [-90, 90] degrees, got {0}".format(degrees)
                )
        if self.right_ascension is not None:
            degrees = self.right_ascension.to("deg").value
            if degrees < 0.0 or degrees > 360.0:
                raise ValueError(
                    "right_ascension must be within [0, 360] degrees, got {0}".format(degrees)
                )
        if self.magnitude is not None and self.magnitude_band is None:
            raise ValueError(
                "a magnitude without its photometric band is not comparable; set "
                "magnitude_band"
            )
        if (
            self.observation_type is ObservationType.OPTICAL_ASTROMETRY
            and self.frame.origin_type is OriginType.UNKNOWN
        ):
            raise ValueError(
                "optical astrometry needs a known origin_type (normally TOPOCENTRIC)"
            )
        return self

    def temporal_anchor(self) -> Optional[datetime]:
        """An observation describes the moment it was taken."""
        return self.observed_at

    @property
    def has_astrometry(self) -> bool:
        return self.right_ascension is not None and self.declination is not None

    @property
    def is_orbital_solution(self) -> bool:
        """Always False, by construction.

        An `Observation` carries measurements and deliberately has no fields for
        orbital elements. Deriving an orbit from observations is an orbit
        *determination*; only a source that publishes a fitted solution may
        produce an `OrbitRecord`.
        """
        return False

    def describe_context(self) -> str:
        return "{0} of {1} at {2} ({3})".format(
            self.observation_type.value.replace("_", " ").lower(),
            self.source_designation or self.object_canonical_id,
            self.observed_at.isoformat(),
            self.frame.describe(),
        )
