"""The space-object hierarchy.

`SpaceObject` is the shared base; each concrete subclass adds only the fields
that are genuinely specific to that kind of object. `object_type` is pinned per
subclass so a deserialized record cannot claim to be a `Moon` while carrying
`ObjectType.STAR`.

Orbits are *not* embedded as a blob. An object references its orbit solutions,
which are full `OrbitRecord`s with their own epochs, frames and provenance.
"""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import NamedRecord, require_dimensions
from .enums import MissionStatus, ObjectType, OrbitRegime
from .orbit import OrbitRecord
from .physical import PhysicalProperties
from .units import Dimension, Quantity

__all__ = [
    "DiscoveryInfo",
    "SpaceObject",
    "Planet",
    "DwarfPlanet",
    "Moon",
    "Star",
    "Asteroid",
    "Comet",
    "Satellite",
    "Spacecraft",
    "SpaceStation",
    "LaunchVehicle",
    "MissionTarget",
]

_D = Dimension


class DiscoveryInfo(BaseModel):
    """How and when an object was discovered."""

    model_config = ConfigDict(extra="forbid")

    discovered_by: Optional[str] = None
    discovery_date: Optional[date] = None
    discovery_year: Optional[int] = None
    discovery_facility: Optional[str] = None
    #: For exoplanets: "Transit", "Radial Velocity", "Imaging", ...
    discovery_method: Optional[str] = None
    #: Literature reference the discovery is published in.
    reference: Optional[str] = None

    @model_validator(mode="after")
    def _check(self) -> "DiscoveryInfo":
        if self.discovery_date and self.discovery_year:
            if self.discovery_date.year != self.discovery_year:
                raise ValueError(
                    "discovery_year {0} contradicts discovery_date {1}".format(
                        self.discovery_year, self.discovery_date.isoformat()
                    )
                )
        if self.discovery_year is not None and not (1500 <= self.discovery_year <= 2200):
            raise ValueError(
                "discovery_year {0} is outside a plausible range".format(self.discovery_year)
            )
        return self


class SpaceObject(NamedRecord):
    """Any physical object in space that the product can describe.

    Subclasses pin `object_type` and `record_type`. Direct instantiation is
    allowed for objects that genuinely do not fit a subclass, in which case
    `object_type` stays `UNKNOWN` and the quality engine flags it.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    record_type: str = "space_object"
    object_type: ObjectType = ObjectType.UNKNOWN

    physical: Optional[PhysicalProperties] = None
    #: Orbit solutions for this object. Several are expected: different sources
    #: and different epochs are kept side by side, never averaged.
    orbits: List[OrbitRecord] = Field(default_factory=list)

    #: Canonical id of the body this object orbits or belongs to.
    parent_canonical_id: Optional[str] = None
    #: Name of the planetary system, e.g. "Solar System", "TRAPPIST-1".
    system_name: Optional[str] = None

    discovery: Optional[DiscoveryInfo] = None
    #: Distance from Earth or from the Sun as the source reports it; which one
    #: is recorded in `distance_context`.
    distance: Optional[Quantity] = None
    distance_context: Optional[str] = None

    #: Media/reference links, e.g. NASA imagery.
    image_urls: List[str] = Field(default_factory=list)
    reference_urls: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_space_object(self) -> "SpaceObject":
        require_dimensions(self, {"distance": _D.LENGTH})
        if self.distance is not None and self.distance_context is None:
            raise ValueError(
                "distance without distance_context is ambiguous; state what it is "
                "measured from (e.g. 'from Earth', 'from Sun')"
            )
        for orbit in self.orbits:
            if orbit.object_canonical_id != self.canonical_id:
                raise ValueError(
                    "orbit {0} belongs to {1}, not to {2}".format(
                        orbit.canonical_id, orbit.object_canonical_id, self.canonical_id
                    )
                )
        return self

    def latest_orbit(self) -> Optional[OrbitRecord]:
        """The orbit solution with the most recent epoch.

        "Most recent epoch" is not the same as "current" — callers must consult
        the record's freshness before describing it that way.
        """
        if not self.orbits:
            return None
        return sorted(self.orbits, key=lambda record: record.epoch)[-1]


class Planet(SpaceObject):
    """A planet, including exoplanets.

    Exoplanets are planets: they use `host_star_canonical_id` plus
    `data_status` (CONFIRMED / CANDIDATE) rather than a separate class, so the
    Exoplanet Archive integration does not need a parallel hierarchy.
    """

    record_type: str = "planet"
    object_type: ObjectType = ObjectType.PLANET

    host_star_canonical_id: Optional[str] = None
    host_star_name: Optional[str] = None
    #: True when this planet is outside the Solar System.
    is_exoplanet: bool = False
    moon_count: Optional[int] = None
    has_ring_system: Optional[bool] = None
    #: Number of planets in the host system, as the source reports it.
    system_planet_count: Optional[int] = None
    #: Insolation flux relative to Earth, published by exoplanet catalogues.
    insolation_flux: Optional[Quantity] = None
    equilibrium_temperature: Optional[Quantity] = None

    @model_validator(mode="after")
    def _check_planet(self) -> "Planet":
        require_dimensions(
            self,
            {
                "insolation_flux": _D.DIMENSIONLESS,
                "equilibrium_temperature": _D.TEMPERATURE,
            },
        )
        if self.is_exoplanet:
            if self.object_type is ObjectType.PLANET:
                self.__dict__["object_type"] = ObjectType.EXOPLANET
            if not (self.host_star_name or self.host_star_canonical_id):
                raise ValueError("an exoplanet needs its host star recorded")
        if self.moon_count is not None and self.moon_count < 0:
            raise ValueError("moon_count must not be negative")
        return self


class DwarfPlanet(SpaceObject):
    """A dwarf planet (Pluto, Ceres, Eris, ...)."""

    record_type: str = "dwarf_planet"
    object_type: ObjectType = ObjectType.DWARF_PLANET

    moon_count: Optional[int] = None
    #: Small-body designation, since several dwarf planets are also asteroids.
    designation: Optional[str] = None
    #: Dynamical population, e.g. "Kuiper Belt", "Main Belt", "Scattered Disc".
    population: Optional[str] = None


class Moon(SpaceObject):
    """A natural satellite. Requires the body it orbits."""

    record_type: str = "moon"
    object_type: ObjectType = ObjectType.MOON

    #: Discovery/naming index within its system, e.g. Jupiter's "JV".
    roman_numeral_designation: Optional[str] = None
    is_regular: Optional[bool] = None

    @model_validator(mode="after")
    def _check_moon(self) -> "Moon":
        if not self.parent_canonical_id:
            raise ValueError("a Moon requires parent_canonical_id — the body it orbits")
        return self


class Star(SpaceObject):
    """A star, including exoplanet host stars."""

    record_type: str = "star"
    object_type: ObjectType = ObjectType.STAR

    spectral_type: Optional[str] = None
    luminosity: Optional[Quantity] = None
    metallicity: Optional[Quantity] = None
    metallicity_ratio: Optional[str] = None
    apparent_magnitude: Optional[Quantity] = None
    #: Photometric band `apparent_magnitude` was measured in.
    magnitude_band: Optional[str] = None
    age: Optional[Quantity] = None
    is_host_star: bool = False
    planet_count: Optional[int] = None

    @model_validator(mode="after")
    def _check_star(self) -> "Star":
        require_dimensions(
            self,
            {
                "luminosity": _D.DIMENSIONLESS,
                "metallicity": _D.DIMENSIONLESS,
                "apparent_magnitude": _D.MAGNITUDE,
                "age": _D.TIME,
            },
        )
        if self.apparent_magnitude is not None and self.magnitude_band is None:
            raise ValueError("apparent_magnitude requires magnitude_band")
        if self.metallicity is not None and not self.metallicity_ratio:
            raise ValueError(
                "metallicity requires metallicity_ratio (e.g. '[Fe/H]') to be interpretable"
            )
        return self


class Asteroid(SpaceObject):
    """A minor planet."""

    record_type: str = "asteroid"
    object_type: ObjectType = ObjectType.ASTEROID

    #: Primary designation, e.g. "433 Eros", "2000 SG344".
    designation: Optional[str] = None
    #: MPC packed form, e.g. "00433".
    packed_designation: Optional[str] = None
    #: JPL SPK-ID.
    spk_id: Optional[str] = None
    #: MPC/JPL numbering, when the object is numbered.
    number: Optional[int] = None

    #: Dynamical class as published, e.g. "MBA", "APO", "ATE".
    orbit_class: Optional[str] = None
    is_near_earth_object: Optional[bool] = None
    is_potentially_hazardous: Optional[bool] = None
    #: Minimum orbit intersection distance with Earth.
    earth_moid: Optional[Quantity] = None
    spectral_type: Optional[str] = None
    #: Dynamical family, e.g. "Themis", "Vesta".
    family: Optional[str] = None

    @model_validator(mode="after")
    def _check_asteroid(self) -> "Asteroid":
        require_dimensions(self, {"earth_moid": _D.LENGTH})
        if self.number is not None and self.number <= 0:
            raise ValueError("asteroid number must be positive")
        if self.is_potentially_hazardous and self.is_near_earth_object is False:
            raise ValueError(
                "an object cannot be potentially hazardous and not a near-earth object"
            )
        return self


class Comet(SpaceObject):
    """A comet."""

    record_type: str = "comet"
    object_type: ObjectType = ObjectType.COMET

    designation: Optional[str] = None
    packed_designation: Optional[str] = None
    spk_id: Optional[str] = None
    #: Orbital family, e.g. "JFc" (Jupiter-family), "HTC", "COM".
    comet_class: Optional[str] = None
    is_periodic: Optional[bool] = None
    nucleus_radius: Optional[Quantity] = None
    #: Non-gravitational acceleration parameters, when published.
    has_nongravitational_parameters: Optional[bool] = None

    @model_validator(mode="after")
    def _check_comet(self) -> "Comet":
        require_dimensions(self, {"nucleus_radius": _D.LENGTH})
        return self


class Satellite(SpaceObject):
    """An artificial satellite in orbit around a body."""

    record_type: str = "satellite"
    object_type: ObjectType = ObjectType.SATELLITE

    #: NORAD catalog number, the de-facto operational identifier.
    norad_cat_id: Optional[int] = None
    #: COSPAR/international designator, e.g. "1998-067A".
    international_designator: Optional[str] = None
    operator: Optional[str] = None
    country: Optional[str] = None
    launch_date: Optional[date] = None
    decay_date: Optional[date] = None
    orbit_regime: OrbitRegime = OrbitRegime.UNKNOWN
    #: Constellation or group name, e.g. "Starlink", "GPS", "NAVIC".
    constellation: Optional[str] = None
    is_active: Optional[bool] = None
    purpose: Optional[str] = None

    @model_validator(mode="after")
    def _check_satellite(self) -> "Satellite":
        if self.norad_cat_id is not None and self.norad_cat_id <= 0:
            raise ValueError("norad_cat_id must be positive")
        if self.launch_date and self.decay_date and self.launch_date > self.decay_date:
            raise ValueError("launch_date is after decay_date")
        if self.decay_date is not None and self.is_active:
            raise ValueError("a satellite with a decay_date cannot be active")
        return self


class SpaceStation(Satellite):
    """A crewable orbital station. A satellite with people-related fields."""

    record_type: str = "space_station"
    object_type: ObjectType = ObjectType.SPACE_STATION

    crew_capacity: Optional[int] = None
    module_count: Optional[int] = None
    #: Agencies operating the station.
    partner_agencies: List[str] = Field(default_factory=list)
    pressurized_volume: Optional[Quantity] = None
    first_launch_date: Optional[date] = None

    @model_validator(mode="after")
    def _check_station(self) -> "SpaceStation":
        require_dimensions(self, {"pressurized_volume": _D.VOLUME})
        if self.crew_capacity is not None and self.crew_capacity < 0:
            raise ValueError("crew_capacity must not be negative")
        return self


class Spacecraft(SpaceObject):
    """A spacecraft: probe, orbiter, lander, rover or crewed vehicle."""

    record_type: str = "spacecraft"
    object_type: ObjectType = ObjectType.SPACECRAFT

    agency: Optional[str] = None
    operator: Optional[str] = None
    launch_date: Optional[date] = None
    end_of_mission_date: Optional[date] = None
    status: MissionStatus = MissionStatus.UNKNOWN
    #: Canonical ids of the missions this spacecraft flew.
    mission_canonical_ids: List[str] = Field(default_factory=list)
    #: Canonical ids of the bodies it visited or targeted.
    target_canonical_ids: List[str] = Field(default_factory=list)
    instruments: List[str] = Field(default_factory=list)
    launch_mass: Optional[Quantity] = None
    dry_mass: Optional[Quantity] = None
    power_source: Optional[str] = None

    @model_validator(mode="after")
    def _check_spacecraft(self) -> "Spacecraft":
        require_dimensions(self, {"launch_mass": _D.MASS, "dry_mass": _D.MASS})
        if self.launch_mass is not None and self.dry_mass is not None:
            if self.dry_mass.si_value() > self.launch_mass.si_value():
                raise ValueError("dry_mass exceeds launch_mass")
        if self.launch_date and self.end_of_mission_date:
            if self.launch_date > self.end_of_mission_date:
                raise ValueError("launch_date is after end_of_mission_date")
        return self


class LaunchVehicle(SpaceObject):
    """A launch vehicle family or configuration.

    Naming note: the project's simulation domain calls the user-built rocket a
    "vehicle" (`vehicles`, `VehicleConfig`), owned by P2/P3. This class is the
    *reference catalogue* entry for a real-world launcher — it is read-only
    reference data and does not replace or shadow that contract.
    """

    record_type: str = "launch_vehicle"
    object_type: ObjectType = ObjectType.LAUNCH_VEHICLE

    manufacturer: Optional[str] = None
    country: Optional[str] = None
    stage_count: Optional[int] = None
    status: MissionStatus = MissionStatus.UNKNOWN
    first_flight_date: Optional[date] = None
    height: Optional[Quantity] = None
    diameter: Optional[Quantity] = None
    liftoff_mass: Optional[Quantity] = None
    liftoff_thrust: Optional[Quantity] = None
    #: Payload capacity by destination regime, e.g. {"LEO": Quantity(...)}.
    payload_capacity_leo: Optional[Quantity] = None
    payload_capacity_gto: Optional[Quantity] = None
    is_reusable: Optional[bool] = None
    successful_launches: Optional[int] = None
    total_launches: Optional[int] = None

    @model_validator(mode="after")
    def _check_vehicle(self) -> "LaunchVehicle":
        require_dimensions(
            self,
            {
                "height": _D.LENGTH,
                "diameter": _D.LENGTH,
                "liftoff_mass": _D.MASS,
                "liftoff_thrust": _D.FORCE,
                "payload_capacity_leo": _D.MASS,
                "payload_capacity_gto": _D.MASS,
            },
        )
        if self.stage_count is not None and self.stage_count < 1:
            raise ValueError("stage_count must be at least 1")
        if self.total_launches is not None and self.successful_launches is not None:
            if self.successful_launches > self.total_launches:
                raise ValueError("successful_launches exceeds total_launches")
        return self

    def success_rate(self) -> Optional[float]:
        if not self.total_launches or self.successful_launches is None:
            return None
        return self.successful_launches / float(self.total_launches)


class MissionTarget(SpaceObject):
    """A destination a mission aims at.

    A target is not always a whole body: "Jezero Crater" and "Mars L2" are both
    valid targets. `target_object_canonical_id` links to the body when one
    exists, and stays `None` when it does not.
    """

    record_type: str = "mission_target"
    object_type: ObjectType = ObjectType.MISSION_TARGET

    #: "BODY", "SURFACE_SITE", "ORBIT", "LAGRANGE_POINT", "REGION", "TRAJECTORY".
    target_kind: str = "BODY"
    #: The body this target is on or around, when applicable.
    target_object_canonical_id: Optional[str] = None
    #: Selenographic/planetographic latitude and longitude of a surface site.
    latitude: Optional[Quantity] = None
    longitude: Optional[Quantity] = None
    #: Why this target was chosen — used by the AI explanation layer.
    rationale: Optional[str] = None

    @model_validator(mode="after")
    def _check_target(self) -> "MissionTarget":
        require_dimensions(self, {"latitude": _D.ANGLE, "longitude": _D.ANGLE})
        if self.target_kind == "SURFACE_SITE" and not self.target_object_canonical_id:
            raise ValueError("a SURFACE_SITE target must name the body it is on")
        if self.latitude is not None:
            degrees = self.latitude.to("deg").value
            if degrees < -90.0 or degrees > 90.0:
                raise ValueError("latitude must be within [-90, 90] degrees")
        return self


#: Concrete subclass lookup by `record_type`, for deserializing stored records.
SPACE_OBJECT_TYPES = {
    cls.model_fields["record_type"].default: cls
    for cls in (
        SpaceObject,
        Planet,
        DwarfPlanet,
        Moon,
        Star,
        Asteroid,
        Comet,
        Satellite,
        SpaceStation,
        Spacecraft,
        LaunchVehicle,
        MissionTarget,
    )
}
