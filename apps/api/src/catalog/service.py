"""Catalog access.

The catalog is authored in Python (``data/catalog/``) and loaded into
PostgreSQL by the seed loaders. This service reads the authored modules
directly, which has two consequences worth stating.

**It works with no database.** A fresh checkout serves a fully populated
explorer, learning library and component picker before anyone has run a
migration. An empty section because the fixture data is not finished yet is
exactly the failure mode this product was told not to ship.

**It is read-only.** Nothing here writes. The records are immutable reference
content; anything a *user* creates — projects, vehicles, simulation runs — lives
in PostgreSQL behind the existing ownership rules and is not served from here.

Everything is built once per process and cached. The catalog is a few hundred
kilobytes of frozen pydantic models, and rebuilding it per request would be
pure waste.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Iterable, Sequence

from src.core.engines import EngineUnavailableError, get_catalog
from src.core.exceptions import AppError, NotFoundError

__all__ = [
    "space_objects",
    "space_object",
    "object_field",
    "launch_sites",
    "launch_site",
    "science_topics",
    "science_topic",
    "experiments",
    "experiment",
    "reference_missions",
    "reference_mission",
    "assets",
    "asset",
    "catalog_summary",
]


def _unavailable(exc: Exception) -> AppError:
    return AppError(503, "CATALOG_UNAVAILABLE", "The reference catalog is not available")


@lru_cache(maxsize=1)
def _catalog() -> Any:
    try:
        return get_catalog()
    except EngineUnavailableError as exc:
        raise _unavailable(exc) from exc


@lru_cache(maxsize=1)
def _objects() -> Sequence[Any]:
    return tuple(_catalog().build_space_objects())


@lru_cache(maxsize=1)
def _sites() -> Sequence[Any]:
    return tuple(_catalog().build_launch_sites())


@lru_cache(maxsize=1)
def _topics() -> Sequence[Any]:
    return tuple(_catalog().build_science_topics())


@lru_cache(maxsize=1)
def _experiments() -> Sequence[Any]:
    return tuple(_catalog().build_experiments())


@lru_cache(maxsize=1)
def _missions() -> Sequence[Any]:
    return tuple(_catalog().build_reference_missions())


@lru_cache(maxsize=1)
def _assets() -> Sequence[Any]:
    return tuple(_catalog().build_assets())


def _matches(text: str, haystacks: Iterable[str]) -> bool:
    needle = text.lower()
    return any(needle in (h or "").lower() for h in haystacks)


# ── Space objects ─────────────────────────────────────────────


def space_objects(
    *, kind: str | None = None, parent_id: str | None = None, q: str | None = None
) -> list[dict[str, Any]]:
    """The object catalog, optionally filtered."""
    results = _objects()
    if kind:
        results = [o for o in results if o.kind.value == kind]
    if parent_id:
        results = [o for o in results if o.parent_id == parent_id]
    if q:
        results = [
            o
            for o in results
            if _matches(q, [o.name, o.designation or "", o.classification, o.tagline, o.overview])
        ]
    return [o.model_dump(mode="json") for o in results]


def space_object(object_id: str) -> dict[str, Any]:
    for obj in _objects():
        if obj.id == object_id:
            return obj.model_dump(mode="json")
    raise NotFoundError("No such space object")


def object_field() -> dict[str, Any]:
    """The landing page's object field.

    A trimmed projection: only what is needed to draw and label a body, so the
    landing page does not download every property table it will not show. The
    full record is one request away on hover-to-inspect.
    """
    field = []
    for obj in _objects():
        if obj.field_x is None or obj.field_y is None:
            # Objects without a placement are catalogue-only; the field is a
            # curated composition, not everything that exists.
            continue
        headline = obj.physical[:2] + obj.orbital[:2]
        field.append(
            {
                "id": obj.id,
                "name": obj.name,
                "kind": obj.kind.value,
                "classification": obj.classification,
                "tagline": obj.tagline,
                "appearance": obj.appearance.model_dump(mode="json"),
                "x": obj.field_x,
                "y": obj.field_y,
                "depth": obj.field_depth,
                "headline": [p.model_dump(mode="json") for p in headline],
                "image": obj.image.model_dump(mode="json") if obj.image else None,
            }
        )
    return {"objects": field, "total_catalog": len(_objects())}


# ── Launch sites ──────────────────────────────────────────────


def launch_sites() -> list[dict[str, Any]]:
    return [s.model_dump(mode="json") for s in _sites()]


def launch_site(site_id: str) -> dict[str, Any]:
    for site in _sites():
        if site.id == site_id:
            return site.model_dump(mode="json")
    raise NotFoundError("No such launch site")


# ── Science ───────────────────────────────────────────────────


def science_topics(
    *, strand: str | None = None, level: str | None = None, q: str | None = None
) -> list[dict[str, Any]]:
    results = _topics()
    if strand:
        results = [t for t in results if t.strand == strand]
    if level:
        results = [t for t in results if t.level == level]
    if q:
        results = [
            t
            for t in results
            if _matches(q, [t.title, t.summary, t.strand] + [s.body for s in t.sections])
        ]
    return [t.model_dump(mode="json") for t in results]


def science_topic(slug: str) -> dict[str, Any]:
    for topic in _topics():
        if topic.slug == slug:
            return topic.model_dump(mode="json")
    raise NotFoundError("No such science topic")


# ── Experiments ───────────────────────────────────────────────


def experiments(*, category: str | None = None, level: str | None = None) -> list[dict[str, Any]]:
    results = _experiments()
    if category:
        results = [e for e in results if e.category.lower() == category.lower()]
    if level:
        results = [e for e in results if e.level == level]
    return [e.model_dump(mode="json") for e in results]


def experiment(experiment_id: str) -> dict[str, Any]:
    for item in _experiments():
        if item.id == experiment_id:
            return item.model_dump(mode="json")
    raise NotFoundError("No such experiment")


# ── Reference missions ────────────────────────────────────────


def reference_missions(
    *, status: str | None = None, destination: str | None = None, q: str | None = None
) -> list[dict[str, Any]]:
    results = _missions()
    if status:
        results = [m for m in results if m.status == status]
    if destination:
        results = [m for m in results if destination in m.destination_ids]
    if q:
        results = [
            m for m in results if _matches(q, [m.name, m.objective, m.overview, m.operator])
        ]
    return [m.model_dump(mode="json") for m in results]


def reference_mission(mission_id: str) -> dict[str, Any]:
    for mission in _missions():
        if mission.id == mission_id:
            return mission.model_dump(mode="json")
    raise NotFoundError("No such mission")


# ── Assets ────────────────────────────────────────────────────


def assets(*, kind: str | None = None, tag: str | None = None, subject: str | None = None,
           q: str | None = None) -> list[dict[str, Any]]:
    results = _assets()
    if kind:
        results = [a for a in results if a.kind == kind]
    if tag:
        results = [a for a in results if tag.lower() in [t.lower() for t in a.tags]]
    if subject:
        results = [a for a in results if subject in a.subject_ids]
    if q:
        results = [a for a in results if _matches(q, [a.title, a.description, a.alt] + list(a.tags))]
    return [a.model_dump(mode="json") for a in results]


def asset(asset_id: str) -> dict[str, Any]:
    for item in _assets():
        if item.id == asset_id:
            return item.model_dump(mode="json")
    raise NotFoundError("No such asset")


# ── Summary ───────────────────────────────────────────────────


def catalog_summary() -> dict[str, Any]:
    """What the catalog holds, for navigation and for the help desk.

    Also the honest answer to "is anything actually populated here?" — a client
    can check the counts before rendering a section.
    """
    catalog = _catalog()
    kinds: dict[str, int] = {}
    for obj in _objects():
        kinds[obj.kind.value] = kinds.get(obj.kind.value, 0) + 1

    strands: dict[str, int] = {}
    for topic in _topics():
        strands[topic.strand] = strands.get(topic.strand, 0) + 1

    asset_kinds: dict[str, int] = {}
    for item in _assets():
        asset_kinds[item.kind] = asset_kinds.get(item.kind, 0) + 1

    return {
        "space_objects": {"total": len(_objects()), "by_kind": kinds},
        "launch_sites": {"total": len(_sites())},
        "science": {
            "total": len(_topics()),
            "strands": [{"name": s, "count": strands.get(s, 0)} for s in catalog.STRANDS],
            "interactive": sum(1 for t in _topics() if t.interactive is not None),
        },
        "experiments": {"total": len(_experiments())},
        "missions": {"total": len(_missions())},
        "assets": {"total": len(_assets()), "by_kind": asset_kinds},
    }
