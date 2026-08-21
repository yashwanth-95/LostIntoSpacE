"""Reading the platform catalog.

The catalog is content, not user data: space objects, launch sites, science
topics, experiments, reference missions and assets. It is identical for every
user and it changes when someone edits a content module, not when a request
comes in.

That shape makes it worth caching in-process. `functools.lru_cache` builds each
collection once per worker and every subsequent request is a dictionary lookup,
which keeps the object field responsive without a database round trip.

The database is the persistent store for *user* data — projects, vehicles,
simulation runs. The seed loaders in `database/seeds/` copy this catalog into
Postgres so the two agree, but the API reads it from here so that a missing or
unseeded database degrades the product to "no saved projects" rather than to
"no content at all".
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional

from src.core.engines import EngineUnavailableError, ensure_engine_paths
from src.core.exceptions import NotFoundError


def _catalog_module(name: str):
    """Import one catalog content module, with engine paths set up."""
    ensure_engine_paths()
    import importlib

    return importlib.import_module("data.catalog.{0}".format(name))


@lru_cache(maxsize=1)
def _objects() -> List[Any]:
    return _catalog_module("space_objects").build_space_objects()


@lru_cache(maxsize=1)
def _objects_by_id() -> Dict[str, Any]:
    return {obj.id: obj for obj in _objects()}


@lru_cache(maxsize=1)
def _launch_sites() -> List[Any]:
    return _catalog_module("launch_sites").build_launch_sites()


@lru_cache(maxsize=1)
def _launch_sites_by_id() -> Dict[str, Any]:
    return {site.id: site for site in _launch_sites()}


@lru_cache(maxsize=1)
def _topics() -> List[Any]:
    return _catalog_module("science").build_science_topics()


@lru_cache(maxsize=1)
def _topics_by_slug() -> Dict[str, Any]:
    return {topic.slug: topic for topic in _topics()}


@lru_cache(maxsize=1)
def _experiments() -> List[Any]:
    return _catalog_module("experiments").build_experiments()


@lru_cache(maxsize=1)
def _experiments_by_id() -> Dict[str, Any]:
    return {experiment.id: experiment for experiment in _experiments()}


@lru_cache(maxsize=1)
def _missions() -> List[Any]:
    return _catalog_module("reference_missions").build_reference_missions()


@lru_cache(maxsize=1)
def _missions_by_id() -> Dict[str, Any]:
    return {mission.id: mission for mission in _missions()}


@lru_cache(maxsize=1)
def _assets() -> List[Any]:
    return _catalog_module("assets").build_assets()


def _matches(haystacks: List[str], needle: str) -> bool:
    lowered = needle.lower()
    return any(lowered in (text or "").lower() for text in haystacks)


# ── Space objects ─────────────────────────────────────────────


def list_objects(
    *,
    kind: Optional[str] = None,
    parent_id: Optional[str] = None,
    q: Optional[str] = None,
) -> List[Any]:
    objects = _objects()
    if kind:
        objects = [obj for obj in objects if obj.kind.value == kind]
    if parent_id:
        objects = [obj for obj in objects if obj.parent_id == parent_id]
    if q:
        objects = [
            obj
            for obj in objects
            if _matches([obj.name, obj.designation or "", obj.classification, obj.tagline], q)
        ]
    return objects


def get_object(object_id: str) -> Any:
    obj = _objects_by_id().get(object_id)
    if obj is None:
        raise NotFoundError("No catalog object with id '{0}'".format(object_id))
    return obj


def field_objects() -> Dict[str, Any]:
    """The objects placed in the landing-page field, reduced for first paint.

    Only those carrying explicit layout coordinates. An object without them
    would have to be positioned by an algorithm, and a solar system arranged by
    an algorithm looks like a scatter plot rather than like a curated map.

    Each entry carries what is needed to *draw* the body and label it — the
    appearance record, the tagline, and two headline properties — but not the
    full property tables. Those are fetched per object when one is approached,
    which keeps the landing payload to a few kilobytes.
    """
    placed = [obj for obj in _objects() if obj.field_x is not None and obj.field_y is not None]
    return {
        "objects": [
            {
                "id": obj.id,
                "name": obj.name,
                "kind": obj.kind.value,
                "classification": obj.classification,
                "tagline": obj.tagline,
                "appearance": obj.appearance,
                "x": obj.field_x,
                "y": obj.field_y,
                "depth": obj.field_depth,
                # Two numbers, chosen for recognisability rather than
                # completeness: the ones worth reading at a glance.
                "headline": _headline_properties(obj),
                "image": obj.image,
            }
            for obj in placed
        ],
        "total_catalog": len(_objects()),
    }


#: Properties worth showing on hover, in order of preference.
_HEADLINE_LABELS = (
    "Mean radius",
    "Surface gravity",
    "Orbital period",
    "Mean distance from Sun",
    "Mass",
    "Orbital velocity",
    "Mean altitude",
)


def _headline_properties(obj: Any, limit: int = 2) -> List[Any]:
    """The two properties most worth reading on hover.

    Preferring a fixed order rather than "the first two" keeps the field
    consistent — every body shows its size and then its motion, so the numbers
    are comparable across objects instead of being whatever the record happened
    to list first.
    """
    available = list(obj.physical) + list(obj.orbital)
    by_label = {prop.label: prop for prop in available}
    chosen = [by_label[label] for label in _HEADLINE_LABELS if label in by_label]
    if len(chosen) < limit:
        chosen += [prop for prop in available if prop not in chosen]
    return chosen[:limit]


# ── Launch sites ──────────────────────────────────────────────


def list_launch_sites() -> List[Any]:
    return _launch_sites()


def get_launch_site(site_id: str) -> Any:
    site = _launch_sites_by_id().get(site_id)
    if site is None:
        raise NotFoundError("No launch site with id '{0}'".format(site_id))
    return site


# ── Science ───────────────────────────────────────────────────


def list_topics(
    *,
    strand: Optional[str] = None,
    level: Optional[str] = None,
    q: Optional[str] = None,
) -> List[Any]:
    topics = _topics()
    if strand:
        topics = [topic for topic in topics if topic.strand.lower() == strand.lower()]
    if level:
        topics = [topic for topic in topics if topic.level == level]
    if q:
        topics = [
            topic
            for topic in topics
            if _matches([topic.title, topic.summary, topic.strand] + list(topic.glossary), q)
        ]
    return topics


def get_topic(slug: str) -> Any:
    topic = _topics_by_slug().get(slug)
    if topic is None:
        raise NotFoundError("No science topic with slug '{0}'".format(slug))
    return topic


# ── Experiments ───────────────────────────────────────────────


def list_experiments(
    *, category: Optional[str] = None, level: Optional[str] = None
) -> List[Any]:
    experiments = _experiments()
    if category:
        experiments = [e for e in experiments if e.category.lower() == category.lower()]
    if level:
        experiments = [e for e in experiments if e.level == level]
    return experiments


def get_experiment(experiment_id: str) -> Any:
    experiment = _experiments_by_id().get(experiment_id)
    if experiment is None:
        raise NotFoundError("No experiment with id '{0}'".format(experiment_id))
    return experiment


# ── Reference missions ────────────────────────────────────────


def list_missions(
    *,
    status: Optional[str] = None,
    destination: Optional[str] = None,
    q: Optional[str] = None,
) -> List[Any]:
    missions = _missions()
    if status:
        missions = [m for m in missions if m.status == status]
    if destination:
        missions = [m for m in missions if destination in m.destination_ids]
    if q:
        missions = [
            m
            for m in missions
            if _matches([m.name, m.objective, m.operator, m.mission_type], q)
        ]
    return missions


def get_mission(mission_id: str) -> Any:
    mission = _missions_by_id().get(mission_id)
    if mission is None:
        raise NotFoundError("No reference mission with id '{0}'".format(mission_id))
    return mission


# ── Assets ────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _assets_by_id() -> Dict[str, Any]:
    return {asset.id: asset for asset in _assets()}


def list_assets(
    *,
    kind: Optional[str] = None,
    tag: Optional[str] = None,
    subject: Optional[str] = None,
    q: Optional[str] = None,
) -> List[Any]:
    assets = _assets()
    if kind:
        assets = [asset for asset in assets if asset.kind == kind]
    if tag:
        assets = [asset for asset in assets if tag in asset.tags]
    if subject:
        assets = [asset for asset in assets if subject in asset.subject_ids]
    if q:
        assets = [
            asset
            for asset in assets
            if _matches([asset.title, asset.description] + list(asset.tags), q)
        ]
    return assets


def get_asset(asset_id: str) -> Any:
    asset = _assets_by_id().get(asset_id)
    if asset is None:
        raise NotFoundError("No asset with id '{0}'".format(asset_id))
    return asset


def catalog_summary() -> Dict[str, Any]:
    """Counts and groupings, for landing-page and navigation labels.

    Real numbers, computed from the catalog itself rather than typed into a
    template, so a claim on the landing page cannot outlive the content that
    justified it.
    """
    objects = _objects()
    assets = _assets()
    topics = _topics()

    by_kind: Dict[str, int] = {}
    for obj in objects:
        by_kind[obj.kind.value] = by_kind.get(obj.kind.value, 0) + 1

    assets_by_kind: Dict[str, int] = {}
    for asset in assets:
        assets_by_kind[asset.kind] = assets_by_kind.get(asset.kind, 0) + 1

    strand_counts: Dict[str, int] = {}
    for topic in topics:
        strand_counts[topic.strand] = strand_counts.get(topic.strand, 0) + 1

    return {
        "space_objects": {"total": len(objects), "by_kind": by_kind},
        "launch_sites": {"total": len(_launch_sites())},
        "science": {
            "total": len(topics),
            "strands": [
                {"name": name, "count": count} for name, count in strand_counts.items()
            ],
            "interactive": sum(1 for topic in topics if topic.interactive is not None),
        },
        "experiments": {"total": len(_experiments())},
        "missions": {"total": len(_missions())},
        "assets": {"total": len(assets), "by_kind": assets_by_kind},
    }


def catalog_health() -> Dict[str, Any]:
    """Counts, so an empty section is visible as a data problem rather than a bug."""
    try:
        return {
            "available": True,
            "objects": len(_objects()),
            "launch_sites": len(_launch_sites()),
            "science_topics": len(_topics()),
            "experiments": len(_experiments()),
            "missions": len(_missions()),
            "assets": len(_assets()),
            "reason": None,
        }
    except (EngineUnavailableError, ImportError) as exc:
        return {"available": False, "reason": str(exc)}
