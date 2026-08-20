"""Catalog routes — public, like the rest of the reference content.

Someone should be able to explore Mars, read about the rocket equation and
inspect a launch site before they create an account. Nothing here is per-user,
so nothing here is behind a token.

Path ordering matters: literal segments (`/objects/field`) are declared before
their parameterised siblings (`/objects/{object_id}`), or the literal is parsed
as an id.
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query

from src.catalog.service import (
    asset,
    assets,
    catalog_summary,
    experiment,
    experiments,
    launch_site,
    launch_sites,
    object_field,
    reference_mission,
    reference_missions,
    science_topic,
    science_topics,
    space_object,
    space_objects,
)
from src.core.envelope import success_envelope
from src.schemas.common import ErrorResponse, SuccessResponse

router = APIRouter()

_RESPONSES: dict = {
    503: {"model": ErrorResponse, "description": "The reference catalog is unavailable"},
}

_NOT_FOUND: dict = {
    404: {"model": ErrorResponse, "description": "No such record"},
    **_RESPONSES,
}

ObjectKindParam = Literal[
    "star", "planet", "dwarf_planet", "moon", "asteroid", "comet",
    "spacecraft", "telescope", "station", "launch_vehicle",
]

Query200 = Annotated[str | None, Query(max_length=200)]
Query100 = Annotated[str | None, Query(max_length=100)]


@router.get("", response_model=SuccessResponse[dict], responses=_RESPONSES)
async def summary() -> dict:
    """What the catalog holds. Cheap enough to call on every page load."""
    return success_envelope(catalog_summary())


# ── Space objects ─────────────────────────────────────────────


@router.get("/objects/field", response_model=SuccessResponse[dict], responses=_RESPONSES)
async def field() -> dict:
    """The curated object field for the landing page.

    A trimmed projection carrying only what is needed to draw and label a body.
    The full record is one request away when the user inspects one.
    """
    return success_envelope(object_field())


@router.get("/objects", response_model=SuccessResponse[list[dict]], responses=_RESPONSES)
async def objects(
    kind: ObjectKindParam | None = None,
    parent_id: Query100 = None,
    q: Query200 = None,
) -> dict:
    return success_envelope(space_objects(kind=kind, parent_id=parent_id, q=q))


@router.get(
    "/objects/{object_id}", response_model=SuccessResponse[dict], responses=_NOT_FOUND
)
async def object_detail(object_id: str) -> dict:
    return success_envelope(space_object(object_id))


# ── Launch sites ──────────────────────────────────────────────


@router.get("/launch-sites", response_model=SuccessResponse[list[dict]], responses=_RESPONSES)
async def sites() -> dict:
    """Real launch sites, with the latitude-derived constraints computed."""
    return success_envelope(launch_sites())


@router.get(
    "/launch-sites/{site_id}", response_model=SuccessResponse[dict], responses=_NOT_FOUND
)
async def site_detail(site_id: str) -> dict:
    return success_envelope(launch_site(site_id))


# ── Science ───────────────────────────────────────────────────


@router.get("/science", response_model=SuccessResponse[list[dict]], responses=_RESPONSES)
async def topics(
    strand: Query100 = None,
    level: Literal["foundation", "intermediate", "advanced"] | None = None,
    q: Query200 = None,
) -> dict:
    return success_envelope(science_topics(strand=strand, level=level, q=q))


@router.get("/science/{slug}", response_model=SuccessResponse[dict], responses=_NOT_FOUND)
async def topic_detail(slug: str) -> dict:
    return success_envelope(science_topic(slug))


# ── Experiments ───────────────────────────────────────────────


@router.get("/experiments", response_model=SuccessResponse[list[dict]], responses=_RESPONSES)
async def experiment_list(
    category: Query100 = None,
    level: Literal["foundation", "intermediate", "advanced"] | None = None,
) -> dict:
    return success_envelope(experiments(category=category, level=level))


@router.get(
    "/experiments/{experiment_id}", response_model=SuccessResponse[dict], responses=_NOT_FOUND
)
async def experiment_detail(experiment_id: str) -> dict:
    return success_envelope(experiment(experiment_id))


# ── Reference missions ────────────────────────────────────────


@router.get("/missions", response_model=SuccessResponse[list[dict]], responses=_RESPONSES)
async def mission_list(
    status: Literal["active", "completed", "failed", "planned"] | None = None,
    destination: Query100 = None,
    q: Query200 = None,
) -> dict:
    """Real flights. Distinct from `/missions`, which holds a user's own mission
    configurations — the two happen to share a word and nothing else."""
    return success_envelope(reference_missions(status=status, destination=destination, q=q))


@router.get(
    "/missions/{mission_id}", response_model=SuccessResponse[dict], responses=_NOT_FOUND
)
async def mission_detail(mission_id: str) -> dict:
    return success_envelope(reference_mission(mission_id))


# ── Assets ────────────────────────────────────────────────────


@router.get("/assets", response_model=SuccessResponse[list[dict]], responses=_RESPONSES)
async def asset_list(
    kind: Query100 = None,
    tag: Query100 = None,
    subject: Query100 = None,
    q: Query200 = None,
) -> dict:
    return success_envelope(assets(kind=kind, tag=tag, subject=subject, q=q))


@router.get("/assets/{asset_id}", response_model=SuccessResponse[dict], responses=_NOT_FOUND)
async def asset_detail(asset_id: str) -> dict:
    return success_envelope(asset(asset_id))
