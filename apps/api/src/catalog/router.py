"""Catalog routes.

Public and unauthenticated, like search: a visitor should be able to explore
the solar system, read the science and browse the mission library before
deciding whether to create an account. Nothing here is per-user.

## Response models

The catalog records are Pydantic models in the `data.catalog` tree, which is
imported through the engine path shim rather than installed as a package. They
are resolved once at import time and published as the response models, so the
OpenAPI schema carries the real shapes.

That matters more than it looks: the generated schema is the artifact the
frontend builds against, and a route documented as returning an untyped object
tells a client author nothing. An earlier version of this module skipped the
annotations for convenience and the contract test caught it.

When the engine tree is unavailable the models resolve to `None` and FastAPI
falls back to an undocumented dict — the routes still work, they are just less
described. That is the same degradation `ai/router.py` makes for the same
reason.
"""

from typing import Any, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.catalog import service
from src.core.engines import ensure_engine_paths
from src.core.envelope import success_envelope
from src.schemas.common import ErrorResponse, SuccessResponse

router = APIRouter()


def _catalog_models() -> dict:
    """Envelope response models for each catalog record type.

    Built once at import. A failure here is not fatal: the routes lose their
    documented shapes but keep working, which is the right trade for a content
    API whose Python tree may not be installed in every deployment.
    """
    try:
        ensure_engine_paths()
        from data.catalog.models import (
            AssetRecord,
            CatalogObject,
            Experiment,
            LaunchSiteRecord,
            ReferenceMission,
            ScienceTopic,
        )
    except ImportError:  # pragma: no cover - depends on the install
        return {}

    class FieldObject(BaseModel):
        """The reduced record the landing-page object field is drawn from."""

        id: str
        name: str
        kind: str
        classification: str
        tagline: str
        appearance: Any
        x: float
        y: float
        depth: float
        headline: List[Any]
        image: Any = None

    class FieldResponse(BaseModel):
        """The field, plus how much of the catalog it is a selection from."""

        objects: List[FieldObject]
        total_catalog: int

    class CountsByKind(BaseModel):
        total: int
        by_kind: dict = {}

    class ScienceCounts(BaseModel):
        total: int
        strands: List[dict] = []
        interactive: int = 0

    class CatalogSummary(BaseModel):
        """Counts per collection, for navigation and landing-page labels."""

        space_objects: CountsByKind
        launch_sites: dict
        science: ScienceCounts
        experiments: dict
        missions: dict
        assets: CountsByKind

    class CatalogHealth(BaseModel):
        """Whether the catalog tree loaded, and what it holds."""

        available: bool
        reason: Optional[str] = None
        objects: Optional[int] = None
        launch_sites: Optional[int] = None
        science_topics: Optional[int] = None
        experiments: Optional[int] = None
        missions: Optional[int] = None
        assets: Optional[int] = None

    return {
        "objects": SuccessResponse[List[CatalogObject]],
        "object": SuccessResponse[CatalogObject],
        "field": SuccessResponse[FieldResponse],
        "sites": SuccessResponse[List[LaunchSiteRecord]],
        "site": SuccessResponse[LaunchSiteRecord],
        "topics": SuccessResponse[List[ScienceTopic]],
        "topic": SuccessResponse[ScienceTopic],
        "experiments": SuccessResponse[List[Experiment]],
        "experiment": SuccessResponse[Experiment],
        "missions": SuccessResponse[List[ReferenceMission]],
        "mission": SuccessResponse[ReferenceMission],
        "assets": SuccessResponse[List[AssetRecord]],
        "asset": SuccessResponse[AssetRecord],
        "summary": SuccessResponse[CatalogSummary],
        "health": SuccessResponse[CatalogHealth],
    }


_MODELS = _catalog_models()

_NOT_FOUND: dict = {404: {"model": ErrorResponse, "description": "No such catalog entry"}}


# ── Space objects ─────────────────────────────────────────────


@router.get("/objects", summary="Every object in the explorer", response_model=_MODELS.get("objects"))
async def list_objects(
    kind: Optional[str] = Query(None, description="star, planet, moon, asteroid, spacecraft…"),
    parent_id: Optional[str] = Query(None, description="Everything orbiting this body"),
    q: Optional[str] = Query(None, min_length=1, max_length=100),
) -> dict:
    return success_envelope(service.list_objects(kind=kind, parent_id=parent_id, q=q))


@router.get("/objects/field", summary="Objects placed in the landing-page field", response_model=_MODELS.get("field"))
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


@router.get("/objects/{object_id}", responses=_NOT_FOUND, summary="One object in full", response_model=_MODELS.get("object"))
async def get_object(object_id: str) -> dict:
    return success_envelope(service.get_object(object_id))


# ── Launch sites ──────────────────────────────────────────────


@router.get("/launch-sites", summary="Real launch sites", response_model=_MODELS.get("sites"))
async def list_launch_sites() -> dict:
    return success_envelope(service.list_launch_sites())


@router.get("/launch-sites/{site_id}", responses=_NOT_FOUND, summary="One launch site", response_model=_MODELS.get("site"))
async def get_launch_site(site_id: str) -> dict:
    return success_envelope(service.get_launch_site(site_id))


# ── Science ───────────────────────────────────────────────────


@router.get("/science", summary="The science library", response_model=_MODELS.get("topics"))
async def list_topics(
    strand: Optional[str] = Query(None),
    level: Optional[str] = Query(None, pattern="^(foundation|intermediate|advanced)$"),
    q: Optional[str] = Query(None, min_length=1, max_length=100),
) -> dict:
    return success_envelope(service.list_topics(strand=strand, level=level, q=q))


@router.get("/science/{slug}", responses=_NOT_FOUND, summary="One science topic", response_model=_MODELS.get("topic"))
async def get_topic(slug: str) -> dict:
    return success_envelope(service.get_topic(slug))


# ── Experiments ───────────────────────────────────────────────


@router.get("/experiments", summary="Runnable experiments", response_model=_MODELS.get("experiments"))
async def list_experiments(
    category: Optional[str] = Query(None),
    level: Optional[str] = Query(None, pattern="^(foundation|intermediate|advanced)$"),
) -> dict:
    return success_envelope(service.list_experiments(category=category, level=level))


@router.get("/experiments/{experiment_id}", responses=_NOT_FOUND, summary="One experiment", response_model=_MODELS.get("experiment"))
async def get_experiment(experiment_id: str) -> dict:
    return success_envelope(service.get_experiment(experiment_id))


# ── Reference missions ────────────────────────────────────────


@router.get("/missions", summary="The mission library", response_model=_MODELS.get("missions"))
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


@router.get("/missions/{mission_id}", responses=_NOT_FOUND, summary="One real mission", response_model=_MODELS.get("mission"))
async def get_mission(mission_id: str) -> dict:
    return success_envelope(service.get_mission(mission_id))


# ── Assets ────────────────────────────────────────────────────


@router.get("/assets", summary="The image library", response_model=_MODELS.get("assets"))
async def list_assets(
    kind: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    subject: Optional[str] = Query(None, description="A catalog object or mission id"),
    q: Optional[str] = Query(None, min_length=1, max_length=100),
) -> dict:
    return success_envelope(service.list_assets(kind=kind, tag=tag, subject=subject, q=q))


@router.get("", summary="What the catalog contains", response_model=_MODELS.get("summary"))
async def catalog_summary() -> dict:
    """Counts and groupings, for landing-page and navigation labels.

    Real numbers rather than round ones: "38 objects" is a claim the product can
    stand behind, and it drops the moment something is removed.
    """
    return success_envelope(service.catalog_summary())


@router.get("/assets/{asset_id}", responses=_NOT_FOUND, summary="One asset", response_model=_MODELS.get("asset"))
async def get_asset(asset_id: str) -> dict:
    return success_envelope(service.get_asset(asset_id))


@router.get("/health", summary="Whether the catalog loaded", response_model=_MODELS.get("health"))
async def catalog_health() -> Any:
    """Counts per collection.

    An empty section on screen is either a data problem or a bug, and those need
    different fixes. This says which.
    """
    return success_envelope(service.catalog_health())
