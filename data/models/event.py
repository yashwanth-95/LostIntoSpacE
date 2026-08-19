"""Natural-event records.

A wildfire is not a space object. EONET events get their own record type rather
than being forced into `SpaceObject`, which would require inventing a mass, an
orbit and a parent body that do not exist.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts._time import as_utc

from .base import NamedRecord, require_dimensions
from .enums import ObjectType
from .units import Dimension, Quantity

__all__ = ["EventGeometry", "EventCategory", "EventSource", "NaturalEvent"]

_D = Dimension


class EventCategory(BaseModel):
    """A category the source assigns, e.g. `wildfires`."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: Optional[str] = None


class EventSource(BaseModel):
    """The agency that reported the event.

    EONET aggregates from other agencies, so an event's real origin is here.
    Citing EONET alone would credit the aggregator instead of the observer.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    url: Optional[str] = None


class EventGeometry(BaseModel):
    """Where and when one observation of an event was located.

    An event has a *list* of these: a storm moves, and each entry is its
    position at one time. Collapsing them to a single point would discard the
    track.
    """

    model_config = ConfigDict(extra="forbid")

    date: datetime
    #: GeoJSON geometry type, "Point" or "Polygon".
    geometry_type: str = "Point"
    #: GeoJSON coordinates: [longitude, latitude] for a Point.
    coordinates: List[Any] = Field(default_factory=list)
    #: Event magnitude in the source's own unit (acres burned, mm of rain, ...).
    magnitude: Optional[Quantity] = None
    #: The magnitude unit as the source words it, kept verbatim because event
    #: magnitudes use units outside any physical unit system.
    magnitude_unit_label: Optional[str] = None

    @field_validator("date")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return as_utc(value)

    @model_validator(mode="after")
    def _check(self) -> "EventGeometry":
        if self.geometry_type not in ("Point", "Polygon", "MultiPolygon", "LineString"):
            raise ValueError("unsupported geometry type {0!r}".format(self.geometry_type))
        if self.geometry_type == "Point":
            if len(self.coordinates) != 2:
                raise ValueError(
                    "a Point needs exactly [longitude, latitude], got {0} value(s)".format(
                        len(self.coordinates)
                    )
                )
            longitude, latitude = self.coordinates
            if not (-180.0 <= float(longitude) <= 180.0):
                raise ValueError("longitude {0} is out of range".format(longitude))
            if not (-90.0 <= float(latitude) <= 90.0):
                raise ValueError("latitude {0} is out of range".format(latitude))
        if self.magnitude is not None and not self.magnitude_unit_label:
            raise ValueError(
                "an event magnitude needs magnitude_unit_label; event units are "
                "source-specific and not interpretable without it"
            )
        return self

    @property
    def longitude(self) -> Optional[float]:
        return float(self.coordinates[0]) if self.geometry_type == "Point" else None

    @property
    def latitude(self) -> Optional[float]:
        return float(self.coordinates[1]) if self.geometry_type == "Point" else None


class NaturalEvent(NamedRecord):
    """A natural event on Earth, as reported by an event-tracking service."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    record_type: str = "natural_event"
    object_type: ObjectType = ObjectType.NATURAL_EVENT

    categories: List[EventCategory] = Field(default_factory=list)
    #: Reporting agencies. Cited alongside the aggregator, never instead of it.
    event_sources: List[EventSource] = Field(default_factory=list)
    geometries: List[EventGeometry] = Field(default_factory=list)

    #: When the source marked the event closed. `None` means still open.
    closed_at: Optional[datetime] = None
    link: Optional[str] = None
    #: Anything the source publishes that has no canonical home.
    extra: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("closed_at")
    @classmethod
    def _utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return as_utc(value)

    @model_validator(mode="after")
    def _check(self) -> "NaturalEvent":
        if self.closed_at and self.geometries:
            first = min(geometry.date for geometry in self.geometries)
            if self.closed_at < first:
                raise ValueError("event closed before its first observation")
        return self

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    def temporal_anchor(self) -> Optional[datetime]:
        """An event's content describes its most recent observation."""
        if self.geometries:
            return max(geometry.date for geometry in self.geometries)
        return self.closed_at or self.valid_at

    @property
    def category_ids(self) -> List[str]:
        return [category.id for category in self.categories]

    def latest_position(self) -> Optional[EventGeometry]:
        if not self.geometries:
            return None
        return sorted(self.geometries, key=lambda geometry: geometry.date)[-1]
