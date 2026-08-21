"""Record types for the platform catalog.

These are deliberately *not* the canonical models in ``data/models/``. Those
describe an object as an archive would: every quantity dimensioned, every
solution carrying its own epoch and frame. This module describes an object as
the interface needs it — a name, an image, a handful of measured properties in
display order, the missions that went there, and enough appearance data to draw
it.

Keeping the two apart means the presentation layer can evolve (add a fact, drop
a property, reorder a panel) without touching the record types that ingestion
and validation depend on.

Every record carries `sources`, so a number rendered on screen can always be
traced back to where it came from.

Python floor for this tree is 3.9 (see ``pyproject.toml``): use ``Optional[X]``
and ``List[X]`` rather than ``X | None`` and ``list[X]``.
"""

from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from contracts.provenance import SourceReference

__all__ = [
    "ObjectKind",
    "SurfaceTexture",
    "Property",
    "RingSystem",
    "Appearance",
    "ImageRef",
    "CatalogObject",
    "LaunchSiteRecord",
    "ScienceTopic",
    "TopicSection",
    "InteractiveSpec",
    "InteractiveParameter",
    "Experiment",
    "ExperimentStep",
    "AssetRecord",
    "ReferenceMission",
    "MissionEvent",
]


class ObjectKind(str, Enum):
    """What kind of thing this is. Drives grouping, iconography and physics."""

    STAR = "star"
    PLANET = "planet"
    DWARF_PLANET = "dwarf_planet"
    MOON = "moon"
    ASTEROID = "asteroid"
    COMET = "comet"
    SPACECRAFT = "spacecraft"
    TELESCOPE = "telescope"
    STATION = "station"
    LAUNCH_VEHICLE = "launch_vehicle"


class SurfaceTexture(str, Enum):
    """How a body should be drawn.

    The renderer has no textures to load, so it synthesises a surface from this
    plus the palette in :class:`Appearance`. A cratered body gets pitting, a
    banded one gets latitudinal flow, a star gets granulation and a corona.
    """

    ROCKY = "rocky"
    CRATERED = "cratered"
    BANDED = "banded"
    GASEOUS = "gaseous"
    ICY = "icy"
    VOLCANIC = "volcanic"
    OCEANIC = "oceanic"
    METALLIC = "metallic"
    IRREGULAR = "irregular"
    STELLAR = "stellar"
    ENGINEERED = "engineered"


class Property(BaseModel):
    """One measured property, ready to render.

    `value` is kept numeric wherever a number exists, so the client can format,
    convert and compare it. `display` is the override for quantities that are
    genuinely not a single number ("CO₂ 95%, N₂ 2.6%").
    """

    model_config = ConfigDict(extra="forbid")

    label: str
    value: Optional[float] = None
    unit: Optional[str] = None
    #: Significant digits to render. None means "as given".
    precision: Optional[int] = None
    #: Pre-formatted alternative, for non-numeric quantities.
    display: Optional[str] = None
    #: Why this number matters, or what it is relative to.
    note: Optional[str] = None
    #: Compare against Earth, where a ratio is more meaningful than an absolute.
    earth_ratio: Optional[float] = None


class RingSystem(BaseModel):
    """A ring system, as fractions of the body's own radius."""

    model_config = ConfigDict(extra="forbid")

    inner_radius_ratio: float = Field(gt=1.0)
    outer_radius_ratio: float = Field(gt=1.0)
    color: str
    opacity: float = Field(ge=0.0, le=1.0, default=0.55)
    #: Ring plane tilt relative to the ecliptic. Unit: degrees.
    tilt_deg: float = 0.0
    #: Divisions drawn as gaps, as radius ratios.
    gaps: List[float] = Field(default_factory=list)


class Appearance(BaseModel):
    """Everything the renderer needs to draw this body without an image.

    The colours are not decorative: they come from how the body actually looks
    in visible light, which is why Mars is iron oxide and Titan is orange haze.
    A body's colour is data, and the object explorer uses it consistently in the
    field, in the detail view, and in the legend.
    """

    model_config = ConfigDict(extra="forbid")

    base_color: str
    accent_color: Optional[str] = None
    #: Latitudinal bands, poles first, for banded and gaseous bodies.
    band_colors: List[str] = Field(default_factory=list)
    #: Mean radius, used to scale the body in the field. Unit: km.
    radius_km: float = Field(gt=0)
    texture: SurfaceTexture = SurfaceTexture.ROCKY
    #: Geometric albedo (0–1). Drives how brightly it is lit.
    albedo: float = Field(ge=0.0, le=1.0, default=0.3)
    #: Limb glow colour, for bodies with an atmosphere.
    atmosphere_color: Optional[str] = None
    #: 0 = no atmosphere, 1 = an opaque haze such as Titan's.
    atmosphere_strength: float = Field(ge=0.0, le=1.0, default=0.0)
    #: Bodies that emit rather than reflect. Only the Sun, here.
    emissive: bool = False
    ring: Optional[RingSystem] = None
    #: Axial tilt, so the drawn pole is in the right place. Unit: degrees.
    axial_tilt_deg: float = 0.0


class ImageRef(BaseModel):
    """A real photograph of the object, with its attribution."""

    model_config = ConfigDict(extra="forbid")

    url: str
    #: NASA Image and Video Library identifier, where the image came from one.
    nasa_id: Optional[str] = None
    title: str
    credit: str = "NASA"
    #: Required: an image with no alternative text is not accessible.
    alt: str
    date: Optional[str] = None
    #: Instrument or mission that took it, when known.
    instrument: Optional[str] = None


class CatalogObject(BaseModel):
    """One object in the explorer."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    #: Formal or alternative designation: "Sol IV", "1 Ceres", "(101955) Bennu".
    designation: Optional[str] = None
    kind: ObjectKind
    #: What it orbits. `None` for the Sun and for interstellar spacecraft.
    parent_id: Optional[str] = None
    classification: str
    #: One line. Shown on hover in the field.
    tagline: str
    overview: str

    physical: List[Property] = Field(default_factory=list)
    orbital: List[Property] = Field(default_factory=list)
    atmosphere: List[Property] = Field(default_factory=list)

    #: Short, checkable statements. Not trivia for its own sake.
    facts: List[str] = Field(default_factory=list)
    #: Ids into the reference-mission catalog.
    mission_ids: List[str] = Field(default_factory=list)
    #: Ids of other catalog objects worth looking at next.
    related_ids: List[str] = Field(default_factory=list)
    #: Slugs into the science catalog.
    concept_slugs: List[str] = Field(default_factory=list)

    appearance: Appearance
    image: Optional[ImageRef] = None
    gallery: List[ImageRef] = Field(default_factory=list)

    #: Where this object sits in the field on the landing page, as fractions of
    #: the viewport. Absent objects are placed by the layout algorithm.
    field_x: Optional[float] = None
    field_y: Optional[float] = None
    #: Relative draw order and parallax depth. 0 = far, 1 = near.
    field_depth: float = 0.5

    sources: List[SourceReference] = Field(default_factory=list)


class LaunchSiteRecord(BaseModel):
    """A real launch site.

    Latitude is the field that matters most for mission design: it sets the
    lowest inclination reachable without a costly plane change, and the eastward
    velocity a launch inherits from Earth's rotation.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    short_name: str
    country: str
    operator: str
    latitude_deg: float = Field(ge=-90, le=90)
    longitude_deg: float = Field(ge=-180, le=180)
    elevation_m: float
    #: Named pads or complexes at this site.
    pads: List[str] = Field(default_factory=list)
    #: Azimuth range launches are permitted to fly, as (min, max) degrees.
    azimuth_range_deg: List[float] = Field(default_factory=list)
    #: Orbits this site is actually used for.
    typical_orbits: List[str] = Field(default_factory=list)
    #: Vehicles that fly from here.
    vehicles: List[str] = Field(default_factory=list)
    notes: str = ""
    #: The lowest inclination reachable without a plane change equals |latitude|.
    min_inclination_deg: Optional[float] = None
    #: Eastward boost from Earth's rotation at this latitude. Unit: m/s.
    earth_rotation_bonus_ms: Optional[float] = None
    established_year: Optional[int] = None
    image: Optional[ImageRef] = None
    sources: List[SourceReference] = Field(default_factory=list)


class InteractiveParameter(BaseModel):
    """One control on an interactive science figure."""

    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    unit: Optional[str] = None
    min: float
    max: float
    default: float
    step: Optional[float] = None
    logarithmic: bool = False
    precision: int = 2
    hint: Optional[str] = None


class InteractiveSpec(BaseModel):
    """The interactive figure attached to a science topic.

    `kind` names a visualisation the client knows how to draw; `parameters` are
    the variables the reader manipulates. The *maths* is never in this record —
    it lives in the scientific engine, so the figure and the simulation cannot
    disagree.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str
    title: str
    instruction: str
    parameters: List[InteractiveParameter] = Field(default_factory=list)
    #: Which computed outputs to show, in order.
    outputs: List[str] = Field(default_factory=list)
    #: The governing equation, in LaTeX-free plain notation.
    equation: Optional[str] = None
    equation_note: Optional[str] = None


class TopicSection(BaseModel):
    """A passage of a science topic."""

    model_config = ConfigDict(extra="forbid")

    heading: str
    body: str
    #: An equation this passage establishes.
    equation: Optional[str] = None
    #: A worked number, so the reader sees the formula used once.
    worked_example: Optional[str] = None
    image: Optional[ImageRef] = None


class ScienceTopic(BaseModel):
    """A lesson in the science library."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    title: str
    strand: str
    level: str = Field(pattern="^(foundation|intermediate|advanced)$")
    summary: str
    #: What the reader will be able to do afterwards.
    outcomes: List[str] = Field(default_factory=list)
    #: Slugs that should be read first.
    prerequisites: List[str] = Field(default_factory=list)
    sections: List[TopicSection] = Field(default_factory=list)
    interactive: Optional[InteractiveSpec] = None
    #: Terms defined by this topic, for the glossary and the assistant.
    glossary: Dict[str, str] = Field(default_factory=dict)
    #: Ids of catalog objects that illustrate this topic.
    object_ids: List[str] = Field(default_factory=list)
    #: Ids of experiments that put it into practice.
    experiment_ids: List[str] = Field(default_factory=list)
    #: Failure mode ids this topic explains.
    explains_failures: List[str] = Field(default_factory=list)
    estimated_minutes: int = 6
    image: Optional[ImageRef] = None
    sources: List[SourceReference] = Field(default_factory=list)


class ExperimentStep(BaseModel):
    """One step of an experiment's procedure."""

    model_config = ConfigDict(extra="forbid")

    instruction: str
    #: Parameter overrides applied to the base design at this step.
    changes: Dict[str, Union[float, str, bool]] = Field(default_factory=dict)
    expectation: Optional[str] = None


class Experiment(BaseModel):
    """A runnable, configurable investigation.

    An experiment is not a snippet. It states a question, fixes everything
    except one variable, says what it expects to happen, and then actually runs
    — which is what makes the result trustworthy rather than illustrative.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    objective: str
    question: str
    category: str
    level: str = Field(pattern="^(foundation|intermediate|advanced)$")
    #: The design this experiment starts from, by preset id.
    base_design: str
    #: The variable being swept.
    variable: str
    variable_label: str
    variable_unit: Optional[str] = None
    #: Values to run, in order.
    sweep: List[float] = Field(default_factory=list)
    #: Everything deliberately held constant.
    controls: List[str] = Field(default_factory=list)
    #: Telemetry or evaluation fields to compare across runs.
    measures: List[str] = Field(default_factory=list)
    procedure: List[ExperimentStep] = Field(default_factory=list)
    hypothesis: str
    explanation: str
    #: Science topics this experiment demonstrates.
    topic_slugs: List[str] = Field(default_factory=list)
    estimated_runs: int = 3


class AssetRecord(BaseModel):
    """One item in the asset library."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    kind: str
    url: str
    thumbnail_url: Optional[str] = None
    credit: str
    license: str
    alt: str
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    #: Catalog objects, missions or components this asset depicts.
    subject_ids: List[str] = Field(default_factory=list)
    width: Optional[int] = None
    height: Optional[int] = None
    nasa_id: Optional[str] = None
    date: Optional[str] = None
    sources: List[SourceReference] = Field(default_factory=list)


class MissionEvent(BaseModel):
    """A dated moment on a mission timeline."""

    model_config = ConfigDict(extra="forbid")

    date: str
    title: str
    detail: str = ""
    #: Milestones worth emphasising on the timeline.
    significant: bool = False


class ReferenceMission(BaseModel):
    """A real flight, in the mission library."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    operator: str
    status: str
    mission_type: str
    objective: str
    overview: str
    launch_date: Optional[str] = None
    end_date: Optional[str] = None
    launch_vehicle: Optional[str] = None
    launch_site_id: Optional[str] = None
    destination_ids: List[str] = Field(default_factory=list)
    crew: List[str] = Field(default_factory=list)
    timeline: List[MissionEvent] = Field(default_factory=list)
    discoveries: List[str] = Field(default_factory=list)
    #: Engineering numbers worth putting next to a user's own design.
    vehicle_facts: List[Property] = Field(default_factory=list)
    #: What went wrong, where something did. Failure is the lesson.
    failures: List[str] = Field(default_factory=list)
    concept_slugs: List[str] = Field(default_factory=list)
    image: Optional[ImageRef] = None
    sources: List[SourceReference] = Field(default_factory=list)
