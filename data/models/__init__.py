"""Canonical scientific data models (P4).

Single definition of every scientific record shape in the project. Source
adapters normalize into these; search indexes them; the AI layer cites them.

Design rules enforced here:

* Every physical value is a `Quantity` — value, unit, uncertainty, source.
* Orbital data is structured (`OrbitRecord`, `OrbitalElements`, `Covariance`),
  never a generic JSON blob.
* Every coordinate-bearing record carries a `FrameContext`, so heliocentric,
  geocentric, topocentric and barycentric data can never be silently mixed.
* Provenance (`SourceReference`, from `packages/contracts/`) is part of the
  record, not a side table.
"""

from contracts.provenance import FreshnessClass, SourceReference, SourceType

from .base import (
    CANONICAL_ID_PATTERN,
    CanonicalRecord,
    NamedRecord,
    make_canonical_id,
    require_dimensions,
    slugify,
)
from .enums import (
    CoordinateSystem,
    DataStatus,
    ElementTheory,
    MissionStatus,
    MissionType,
    ObjectType,
    ObservationType,
    OrbitRegime,
    OriginType,
    ReferenceFrame,
    TimeScale,
)
from .document import DocumentAuthor, DocumentLink, DocumentRecord
from .eo import AccessStatus, EOProduct, ProductFootprint
from .event import EventCategory, EventGeometry, EventSource, NaturalEvent
from .learning import ContentKind, DifficultyLevel, Equation, LearningContent
from .mission import LaunchSite, Mission, MissionOutcome
from .observation import Observation
from .orbit import (
    Covariance,
    EphemerisRecord,
    FrameContext,
    OrbitFitInfo,
    OrbitRecord,
    OrbitalElements,
    StateVector,
)
from .physical import (
    AtmosphereProfile,
    Composition,
    CompositionComponent,
    PhysicalProperties,
    RotationProperties,
)
from .space_object import (
    SPACE_OBJECT_TYPES,
    Asteroid,
    Comet,
    DiscoveryInfo,
    DwarfPlanet,
    LaunchVehicle,
    MissionTarget,
    Moon,
    Planet,
    Satellite,
    SpaceObject,
    SpaceStation,
    Spacecraft,
    Star,
)
from .units import (
    Dimension,
    Quantity,
    UnitDef,
    UnitError,
    canonical_unit_for,
    convert,
    dimension_of,
    get_unit,
    is_known_unit,
)

__all__ = [
    # provenance (re-exported from packages/contracts)
    "SourceReference",
    "SourceType",
    "FreshnessClass",
    # units
    "Dimension",
    "Quantity",
    "UnitDef",
    "UnitError",
    "convert",
    "get_unit",
    "is_known_unit",
    "dimension_of",
    "canonical_unit_for",
    # base
    "CanonicalRecord",
    "NamedRecord",
    "CANONICAL_ID_PATTERN",
    "make_canonical_id",
    "slugify",
    "require_dimensions",
    # enums
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
    # physical
    "PhysicalProperties",
    "RotationProperties",
    "AtmosphereProfile",
    "Composition",
    "CompositionComponent",
    # orbit
    "FrameContext",
    "OrbitalElements",
    "Covariance",
    "OrbitFitInfo",
    "OrbitRecord",
    "StateVector",
    "EphemerisRecord",
    # observation
    "Observation",
    # non-object records: NASA products that are not space objects
    "NaturalEvent",
    "EventGeometry",
    "EventCategory",
    "EventSource",
    "DocumentRecord",
    "DocumentAuthor",
    "DocumentLink",
    "EOProduct",
    "ProductFootprint",
    "AccessStatus",
    # editorial content
    "LearningContent",
    "ContentKind",
    "DifficultyLevel",
    "Equation",
    # objects
    "SpaceObject",
    "Planet",
    "DwarfPlanet",
    "Moon",
    "Star",
    "Asteroid",
    "Comet",
    "Satellite",
    "SpaceStation",
    "Spacecraft",
    "LaunchVehicle",
    "MissionTarget",
    "DiscoveryInfo",
    "SPACE_OBJECT_TYPES",
    # mission catalogue
    "Mission",
    "MissionOutcome",
    "LaunchSite",
]
