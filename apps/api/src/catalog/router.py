"""Catalog routes.

Public and unauthenticated, like search: a visitor should be able to explore
the solar system, read the science and browse the mission library before
deciding whether to create an account. Nothing here is per-user.

Response models are deliberately not declared. The catalog records are Pydantic
models defined in the `data.catalog` tree, which is imported at request time
through the engine path shim rather than installed as a package — so the types
are not available at import time to annotate with. FastAPI serialises them
correctly either way; what is lost is OpenAPI detail, and `docs/api/CATALOG.md`
carries the shapes instead.
"""

from typing import Any, Optional

from fastapi import APIRouter, Query

from src.catalog import service
from src.core.envelope import success_envelope
from src.schemas.common import ErrorResponse

router = APIRouter()

_NOT_FOUND: dict = {404: {"model": ErrorResponse, "description": "No such catalog entry"}}


# ── Space objects ─────────────────────────────────────────────


@router.get("/objects", summary="Every object in the explorer")
async def list_objects(
    kind: Optional[str] = Query(None, description="star, planet, moon, asteroid, spacecraft…"),
    parent_id: Optional[str] = Query(None, description="Everything orbiting this body"),
    q: Optional[str] = Query(None, min_length=1, max_length=100),
) -> dict:
    return success_envelope(service.list_objects(kind=kind, parent_id=parent_id, q=q))


@router.get("/objects/field", summary="Objects placed in the landing-page field")
async def field_objects() -> dict:
    """The curated subset that carries explicit layout coordinates.

    Returns a *reduced* record: enough to draw the body, label it and show two
    headline numbers. The full property tables are fetched only when a body is
    actually approached, so the landing page's first paint is eleven small
    objects rather than the whole catalogue.

    Declared before `/objects/{object_id}` so the literal segment is not
    captured as a path parameter.
    """
    return success_envelope(service.field_objects())


@router.get("/objects/{object_id}", responses=_NOT_FOUND, summary="One object in full")
async def get_object(object_id: str) -> dict:
    return success_envelope(service.get_object(object_id))


# ── Launch sites ──────────────────────────────────────────────


@router.get("/launch-sites", summary="Real launch sites")
async def list_launch_sites() -> dict:
    return success_envelope(service.list_launch_sites())


@router.get("/launch-sites/{site_id}", responses=_NOT_FOUND, summary="One launch site")
async def get_launch_site(site_id: str) -> dict:
    return success_envelope(service.get_launch_site(site_id))


# ── Science ───────────────────────────────────────────────────


@router.get("/science", summary="The science library")
async def list_topics(
    strand: Optional[str] = Query(None),
    level: Optional[str] = Query(None, pattern="^(foundation|intermediate|advanced)$"),
    q: Optional[str] = Query(None, min_length=1, max_length=100),
) -> dict:
    return success_envelope(service.list_topics(strand=strand, level=level, q=q))


@router.get("/science/{slug}", responses=_NOT_FOUND, summary="One science topic")
async def get_topic(slug: str) -> dict:
    return success_envelope(service.get_topic(slug))


# ── Experiments ───────────────────────────────────────────────


@router.get("/experiments", summary="Runnable experiments")
async def list_experiments(
    category: Optional[str] = Query(None),
    level: Optional[str] = Query(None, pattern="^(foundation|intermediate|advanced)$"),
) -> dict:
    return success_envelope(service.list_experiments(category=category, level=level))


@router.get("/experiments/{experiment_id}", responses=_NOT_FOUND, summary="One experiment")
async def get_experiment(experiment_id: str) -> dict:
    return success_envelope(service.get_experiment(experiment_id))


# ── Reference missions ────────────────────────────────────────


@router.get("/missions", summary="The mission library")
async def list_missions(
    status: Optional[str] = Query(None),
    destination: Optional[str] = Query(None, description="A catalog object id"),
    q: Optional[str] = Query(None, min_length=1, max_length=100),
) -> dict:
    """Real flights.

    Distinct from `/missions` at the top level, which holds a *user's own*
    mission configurations. These are the reference library of flights that
    actually happened.
    """
    return success_envelope(service.list_missions(status=status, destination=destination, q=q))


@router.get("/missions/{mission_id}", responses=_NOT_FOUND, summary="One real mission")
async def get_mission(mission_id: str) -> dict:
    return success_envelope(service.get_mission(mission_id))


# ── Assets ────────────────────────────────────────────────────


@router.get("/assets", summary="The image library")
async def list_assets(
    kind: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    subject: Optional[str] = Query(None, description="A catalog object or mission id"),
    q: Optional[str] = Query(None, min_length=1, max_length=100),
) -> dict:
    return success_envelope(service.list_assets(kind=kind, tag=tag, subject=subject, q=q))


@router.get("", summary="What the catalog contains")
async def catalog_summary() -> dict:
    """Counts and groupings, for landing-page and navigation labels.

    Real numbers rather than round ones: "38 objects" is a claim the product can
    stand behind, and it drops the moment something is removed.
    """
    return success_envelope(service.catalog_summary())


@router.get("/assets/{asset_id}", responses=_NOT_FOUND, summary="One asset")
async def get_asset(asset_id: str) -> dict:
    return success_envelope(service.get_asset(asset_id))


@router.get("/health", summary="Whether the catalog loaded")
async def catalog_health() -> Any:
    """Counts per collection.

    An empty section on screen is either a data problem or a bug, and those need
    different fixes. This says which.
    """
    return success_envelope(service.catalog_health())
