"""Space-object routes - Public per docs/api/API.md (no token required).

Sorting is restricted to an allow-list (`SORTABLE_FIELDS` in the service) via
a Literal here, so a `sort` value can never reach SQL as arbitrary text.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.envelope import success_envelope
from src.schemas.common import (
    PUBLIC_RESOURCE_RESPONSES,
    PaginatedResponse,
    PaginationParams,
    SuccessResponse,
    pagination_meta,
    pagination_params,
)
from src.schemas.space_object import SpaceObjectDetail, SpaceObjectSummary
from src.space_data.service import (
    get_space_object,
    list_space_object_categories,
    list_space_objects,
)

router = APIRouter()


@router.get("", response_model=PaginatedResponse[SpaceObjectSummary])
async def list_(
    category: str | None = Query(default=None, max_length=50),
    source: str | None = Query(default=None, max_length=100),
    q: str | None = Query(default=None, max_length=200),
    sort: Literal["name", "category", "created_at", "last_updated"] = "name",
    order: Literal["asc", "desc"] = "asc",
    pagination: PaginationParams = Depends(pagination_params),
    session: AsyncSession = Depends(get_db),
) -> dict:
    objects, total = await list_space_objects(
        session,
        pagination=pagination,
        category=category,
        source=source,
        q=q,
        sort=sort,
        order=order,
    )
    return success_envelope(
        [SpaceObjectSummary.model_validate(o).model_dump(mode="json") for o in objects],
        meta=pagination_meta(pagination, total),
    )


@router.get("/categories", response_model=SuccessResponse[list[str]])
async def categories(session: AsyncSession = Depends(get_db)) -> dict:
    # Before /{object_id} so "categories" isn't parsed as a UUID.
    return success_envelope(await list_space_object_categories(session))


@router.get(
    "/{object_id}",
    response_model=SuccessResponse[SpaceObjectDetail],
    responses=PUBLIC_RESOURCE_RESPONSES,
)
async def read(object_id: uuid.UUID, session: AsyncSession = Depends(get_db)) -> dict:
    space_object = await get_space_object(session, object_id=object_id)
    return success_envelope(SpaceObjectDetail.model_validate(space_object).model_dump(mode="json"))
