"""Weather records, in SI units.

Providers report in whatever units they like — hPa, km/h, degrees Celsius. All
of that conversion happens at the provider boundary, so everything downstream
of this module works in kelvin, pascals and metres per second, which is what
the simulation speaks. A unit conversion that happens twice, or not at all, is
the classic way to lose a spacecraft.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

__all__ = [
    "WindObservation",
    "WeatherObservation",
    "LaunchConstraint",
    "LaunchSuitability",
]


class WindObservation(BaseModel):
    """Wind at the standard 10 m measurement height."""

    model_config = ConfigDict(extra="forbid")

    speed_ms: float = Field(ge=0, description="Sustained wind speed. Unit: m/s")
    direction_deg: float = Field(
        ge=0, le=360, description="Direction the wind comes FROM. Unit: degrees"
    )
    gust_ms: Optional[float] = Field(
        default=None, ge=0, description="Peak gust. Unit: m/s"
    )


class WeatherObservation(BaseModel):
    """Conditions at a launch site, right now.

    `air_density_kgm3` is derived rather than reported: no weather API publishes
    it, and it is the single number the drag calculation actually wants.
    """

    model_config = ConfigDict(extra="forbid")

    site_id: str
    latitude_deg: float
    longitude_deg: float
    elevation_m: float

    observed_at: datetime
    temperature_K: float = Field(gt=0, description="Air temperature. Unit: K")
    dew_point_K: Optional[float] = Field(default=None, description="Dew point. Unit: K")
    #: Station pressure at the site's own elevation, not reduced to sea level.
    #: The simulation needs the pressure the vehicle will actually fly through.
    pressure_Pa: float = Field(gt=0, description="Station pressure. Unit: Pa")
    sea_level_pressure_Pa: Optional[float] = Field(default=None, description="Unit: Pa")
    relative_humidity: float = Field(ge=0, le=1, description="0-1")
    wind: WindObservation
    precipitation_mm_h: float = Field(default=0.0, ge=0, description="Unit: mm/h")
    cloud_cover: float = Field(default=0.0, ge=0, le=1, description="0-1")
    visibility_m: Optional[float] = Field(default=None, ge=0, description="Unit: m")
    #: Derived from temperature, pressure and humidity. Unit: kg/m³.
    air_density_kgm3: float = Field(gt=0)
    #: Speed of sound at the surface, which sets where Mach 1 is. Unit: m/s.
    speed_of_sound_ms: float = Field(gt=0)
    #: Estimated wind at the tropopause, when the provider supplies upper-level
    #: data. `None` means the simulation should estimate it.
    jet_wind_speed_ms: Optional[float] = Field(default=None, ge=0)

    provider: str
    #: True when this came from a live request rather than a cache or a fallback.
    is_live: bool = True
    #: Set when the observation is a documented fallback, explaining why.
    fallback_reason: Optional[str] = None
    attribution: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def temperature_C(self) -> float:
        """Temperature in Celsius, for display.

        A computed field rather than a bare property, so it serialises with the
        observation and appears in the OpenAPI schema. The API previously
        injected it into the payload by hand, which meant the documented shape
        and the actual shape disagreed.
        """
        return round(self.temperature_K - 273.15, 2)


class LaunchConstraint(BaseModel):
    """One launch commit criterion, evaluated against the observation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    #: "go", "caution" or "no-go".
    status: str = Field(pattern="^(go|caution|no-go)$")
    measured: float
    limit: float
    unit: str
    explanation: str


class LaunchSuitability(BaseModel):
    """Whether the pad is flyable, and what would stop it.

    Modelled on real launch commit criteria, simplified and stated as such.
    A real range safety review covers lightning, triboelectrification, cloud
    layers, upper-level shear and surface conditions across a whole window; this
    covers the subset the simulation can actually act on.
    """

    model_config = ConfigDict(extra="forbid")

    #: "go", "caution" or "no-go".
    status: str = Field(pattern="^(go|caution|no-go)$")
    summary: str
    constraints: List[LaunchConstraint] = Field(default_factory=list)
    #: Constraint ids currently violated.
    violations: List[str] = Field(default_factory=list)
