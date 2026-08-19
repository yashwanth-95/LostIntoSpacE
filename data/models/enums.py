"""Controlled vocabularies for the canonical scientific model.

These are deliberately explicit enums rather than free strings: the data-quality
engine cannot detect an inconsistent object type or a mixed reference frame if
those values are arbitrary text.
"""

from enum import Enum

__all__ = [
    "ObjectType",
    "DataStatus",
    "TimeScale",
    "ReferenceFrame",
    "CoordinateSystem",
    "OriginType",
    "ElementTheory",
    "ObservationType",
    "MissionStatus",
    "MissionType",
    "OrbitRegime",
]


class ObjectType(str, Enum):
    """What kind of thing a `SpaceObject` is.

    One value per concrete model class in `space_object.py`, so a record's
    declared type and its Python class can be cross-checked.
    """

    PLANET = "PLANET"
    DWARF_PLANET = "DWARF_PLANET"
    MOON = "MOON"
    STAR = "STAR"
    ASTEROID = "ASTEROID"
    COMET = "COMET"
    SATELLITE = "SATELLITE"
    SPACECRAFT = "SPACECRAFT"
    SPACE_STATION = "SPACE_STATION"
    LAUNCH_VEHICLE = "LAUNCH_VEHICLE"
    MISSION_TARGET = "MISSION_TARGET"
    EXOPLANET = "EXOPLANET"
    NATURAL_EVENT = "NATURAL_EVENT"
    EO_PRODUCT = "EO_PRODUCT"
    DOCUMENT = "DOCUMENT"
    UNKNOWN = "UNKNOWN"


class DataStatus(str, Enum):
    """Epistemic status of a record.

    Required by the Exoplanet Archive integration, which distinguishes confirmed
    planets from candidates. Never promote a CANDIDATE to CONFIRMED locally.
    """

    CONFIRMED = "CONFIRMED"
    CANDIDATE = "CANDIDATE"
    #: Superseded by a newer record but retained for reference.
    HISTORICAL = "HISTORICAL"
    #: The source has withdrawn or retracted the record (e.g. a false positive).
    DEPRECATED = "DEPRECATED"
    #: Computed by this project rather than published by a source.
    DERIVED = "DERIVED"
    UNKNOWN = "UNKNOWN"


class TimeScale(str, Enum):
    """Time scale an epoch is expressed in.

    JPL Horizons returns TDB by default for barycentric ephemerides; CelesTrak
    epochs are UTC. Storing an epoch without its scale loses up to ~70 s of
    accuracy, which matters for close approaches.
    """

    UTC = "UTC"
    TAI = "TAI"
    TT = "TT"
    TDB = "TDB"
    UT1 = "UT1"
    UNKNOWN = "UNKNOWN"


class ReferenceFrame(str, Enum):
    """Inertial or body-fixed frame the coordinates are expressed in."""

    ICRF = "ICRF"
    J2000 = "J2000"
    EME2000 = "EME2000"
    ECLIPJ2000 = "ECLIPJ2000"
    #: True equator, mean equinox — the frame SGP4/TLE element sets live in.
    TEME = "TEME"
    ITRF = "ITRF"
    BODY_FIXED = "BODY_FIXED"
    UNKNOWN = "UNKNOWN"


class CoordinateSystem(str, Enum):
    """How the state is parameterized."""

    KEPLERIAN = "KEPLERIAN"
    CARTESIAN = "CARTESIAN"
    EQUINOCTIAL = "EQUINOCTIAL"
    SPHERICAL = "SPHERICAL"
    GEODETIC = "GEODETIC"
    #: Right ascension / declination as observed.
    OBSERVED_ANGLES = "OBSERVED_ANGLES"


class OriginType(str, Enum):
    """Where the origin of the coordinate system sits.

    Mixing these without recording which is which is the single most common
    silent error in small-body work, so it is a required field on every orbit,
    ephemeris and observation record.
    """

    HELIOCENTRIC = "HELIOCENTRIC"
    GEOCENTRIC = "GEOCENTRIC"
    #: Observer on a rotating body's surface — needs an observatory code.
    TOPOCENTRIC = "TOPOCENTRIC"
    BARYCENTRIC = "BARYCENTRIC"
    #: Centred on a body other than the Sun or Earth.
    PLANETOCENTRIC = "PLANETOCENTRIC"
    UNKNOWN = "UNKNOWN"


class ElementTheory(str, Enum):
    """Which dynamical theory the orbital elements belong to.

    Osculating Keplerian elements from JPL and SGP4 mean elements from CelesTrak
    are *not* interchangeable, even though both have six angles with the same
    names. This field is what prevents them being averaged together.
    """

    #: Instantaneous two-body elements. JPL SBDB / Horizons.
    OSCULATING_KEPLERIAN = "OSCULATING_KEPLERIAN"
    #: Mean elements consumable only by SGP4/SDP4. CelesTrak GP/OMM, TLEs.
    SGP4_MEAN = "SGP4_MEAN"
    #: Mean elements from a general-perturbation fit that is not SGP4.
    MEAN_ELEMENTS = "MEAN_ELEMENTS"
    UNKNOWN = "UNKNOWN"


class ObservationType(str, Enum):
    OPTICAL_ASTROMETRY = "OPTICAL_ASTROMETRY"
    RADAR = "RADAR"
    PHOTOMETRY = "PHOTOMETRY"
    SPECTROSCOPY = "SPECTROSCOPY"
    SPACE_BASED = "SPACE_BASED"
    OCCULTATION = "OCCULTATION"
    TRANSIT = "TRANSIT"
    RADIAL_VELOCITY = "RADIAL_VELOCITY"
    UNKNOWN = "UNKNOWN"


class MissionStatus(str, Enum):
    PROPOSED = "PROPOSED"
    IN_DEVELOPMENT = "IN_DEVELOPMENT"
    ACTIVE = "ACTIVE"
    EXTENDED = "EXTENDED"
    COMPLETED = "COMPLETED"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class MissionType(str, Enum):
    FLYBY = "FLYBY"
    ORBITER = "ORBITER"
    LANDER = "LANDER"
    ROVER = "ROVER"
    SAMPLE_RETURN = "SAMPLE_RETURN"
    CREWED = "CREWED"
    SPACE_TELESCOPE = "SPACE_TELESCOPE"
    TECHNOLOGY_DEMO = "TECHNOLOGY_DEMO"
    EARTH_OBSERVATION = "EARTH_OBSERVATION"
    COMMUNICATIONS = "COMMUNICATIONS"
    IMPACTOR = "IMPACTOR"
    UNKNOWN = "UNKNOWN"


class OrbitRegime(str, Enum):
    LEO = "LEO"
    MEO = "MEO"
    GEO = "GEO"
    GTO = "GTO"
    HEO = "HEO"
    SSO = "SSO"
    POLAR = "POLAR"
    LAGRANGE = "LAGRANGE"
    HELIOCENTRIC = "HELIOCENTRIC"
    ESCAPE = "ESCAPE"
    UNKNOWN = "UNKNOWN"
