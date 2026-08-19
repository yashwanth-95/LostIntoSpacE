"""Mission reference records.

**Contract boundary.** This `Mission` is the *reference catalogue* entry for a
real historical or planned mission (Apollo 11, Artemis I, Chandrayaan-3) — it is
read-only ingested data that the search and AI layers cite.

It is deliberately **not** the same thing as the `missions` database table
described in `docs/architecture/DATABASE.md`, which is a user's mission inside a
project and is owned by P2. Those two must not be merged: one has a `user_id`
and a `target_orbit` the user chose, the other has an agency and a launch date
that already happened. See docs/PERSON4_INTEGRATION_MAP.md §2 row 2.
"""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import NamedRecord, require_dimensions
from .enums import MissionStatus, MissionType
from .units import Dimension, Quantity

__all__ = ["LaunchSite", "MissionOutcome", "Mission"]

_D = Dimension


class LaunchSite(BaseModel):
    """A launch site, with coordinates when known."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    country: Optional[str] = None
    operator: Optional[str] = None
    latitude: Optional[Quantity] = None
    longitude: Optional[Quantity] = None
    elevation: Optional[Quantity] = None
    pad: Optional[str] = None

    @model_validator(mode="after")
    def _check(self) -> "LaunchSite":
        require_dimensions(
            self,
            {"latitude": _D.ANGLE, "longitude": _D.ANGLE, "elevation": _D.LENGTH},
        )
        if self.latitude is not None:
            degrees = self.latitude.to("deg").value
            if degrees < -90.0 or degrees > 90.0:
                raise ValueError("launch site latitude must be within [-90, 90] degrees")
        if self.longitude is not None:
            degrees = self.longitude.to("deg").value
            if degrees < -180.0 or degrees > 360.0:
                raise ValueError("launch site longitude is outside a plausible range")
        return self


class MissionOutcome(BaseModel):
    """What actually happened.

    Kept separate from `objectives` so the AI explanation layer can contrast
    intent with result without inferring either.
    """

    model_config = ConfigDict(extra="forbid")

    status: MissionStatus = MissionStatus.UNKNOWN
    summary: Optional[str] = None
    #: Objectives the mission achieved, as published.
    achievements: List[str] = Field(default_factory=list)
    #: Documented anomalies or failures. Feeds the failure-analysis material.
    anomalies: List[str] = Field(default_factory=list)
    #: Lessons the agency itself published. Never invented locally.
    published_lessons: List[str] = Field(default_factory=list)


class Mission(NamedRecord):
    """A real mission, as catalogued from public agency sources."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    record_type: str = "mission"

    #: Lead agency, e.g. "NASA", "ISRO", "ESA".
    agency: Optional[str] = None
    #: All participating agencies, including the lead.
    partner_agencies: List[str] = Field(default_factory=list)
    mission_type: MissionType = MissionType.UNKNOWN
    status: MissionStatus = MissionStatus.UNKNOWN

    launch_date: Optional[date] = None
    end_date: Optional[date] = None
    #: Duration as published, when it differs from end_date - launch_date
    #: (extended missions, hibernation periods).
    duration: Optional[Quantity] = None

    launch_site: Optional[LaunchSite] = None
    #: Canonical id of the launch vehicle used.
    launch_vehicle_canonical_id: Optional[str] = None
    #: Canonical ids of the spacecraft flown.
    spacecraft_canonical_ids: List[str] = Field(default_factory=list)
    #: Canonical ids of `MissionTarget` records.
    target_canonical_ids: List[str] = Field(default_factory=list)

    objectives: List[str] = Field(default_factory=list)
    outcome: Optional[MissionOutcome] = None
    instruments: List[str] = Field(default_factory=list)
    crew: List[str] = Field(default_factory=list)

    #: Topics for search faceting, e.g. ["lunar", "sample return"].
    topics: List[str] = Field(default_factory=list)
    reference_urls: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "Mission":
        require_dimensions(self, {"duration": _D.TIME})
        if self.launch_date and self.end_date and self.launch_date > self.end_date:
            raise ValueError("launch_date is after end_date")
        if self.launch_date is not None and self.launch_date.year < 1942:
            raise ValueError(
                "launch_date {0} predates spaceflight; likely a parsing error".format(
                    self.launch_date.isoformat()
                )
            )
        if self.crew and self.mission_type not in (MissionType.CREWED, MissionType.UNKNOWN):
            raise ValueError(
                "mission has crew but mission_type is {0}".format(self.mission_type.value)
            )
        if self.outcome is not None and self.outcome.status is not MissionStatus.UNKNOWN:
            if self.status is MissionStatus.UNKNOWN:
                self.__dict__["status"] = self.outcome.status
            elif self.status is not self.outcome.status:
                raise ValueError(
                    "mission.status ({0}) contradicts outcome.status ({1})".format(
                        self.status.value, self.outcome.status.value
                    )
                )
        return self

    @property
    def is_complete(self) -> bool:
        return self.status in (
            MissionStatus.COMPLETED,
            MissionStatus.FAILED,
            MissionStatus.PARTIAL_FAILURE,
            MissionStatus.CANCELLED,
        )
