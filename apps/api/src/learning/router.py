"""Lesson (public) and learning-progress (private) routes.

Auth split per docs/api/API.md: `/lessons*` is Public, `/learning/progress` is
Bearer. Lessons are an unowned catalog; progress is per-user and a caller can
only ever read or write their own, because `user_id` comes from the token.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.core.database import get_db
from src.core.envelope import success_envelope
from src.learning.service import (
    get_lesson,
    list_categories,
    list_lessons,
    list_progress,
    update_progress,
    upsert_progress,
)
from src.models.user import User
from src.schemas.common import (
    AUTH_ERROR_RESPONSES,
    OWNED_RESOURCE_RESPONSES,
    PUBLIC_RESOURCE_RESPONSES,
    PaginatedResponse,
    PaginationParams,
    SuccessResponse,
    pagination_meta,
    pagination_params,
)
from src.schemas.learning import (
    LessonDetail,
    LessonSummary,
    ProgressResponse,
    ProgressUpdate,
    ProgressUpsert,
)

lessons_router = APIRouter()
progress_router = APIRouter()


@lessons_router.get("", response_model=PaginatedResponse[LessonSummary])
async def list_all(
    category: str | None = Query(default=None, max_length=50),
    difficulty: str | None = Query(default=None, max_length=20),
    pagination: PaginationParams = Depends(pagination_params),
    session: AsyncSession = Depends(get_db),
) -> dict:
    lessons, total = await list_lessons(
        session, pagination=pagination, category=category, difficulty=difficulty
    )
    return success_envelope(
        [LessonSummary.model_validate(x).model_dump(mode="json") for x in lessons],
        meta=pagination_meta(pagination, total),
    )


@lessons_router.get("/categories", response_model=SuccessResponse[list[str]])
async def categories(session: AsyncSession = Depends(get_db)) -> dict:
    # Declared before /{identifier} so "categories" isn't captured as a slug.
    return success_envelope(await list_categories(session))


@lessons_router.get(
    "/{identifier}",
    response_model=SuccessResponse[LessonDetail],
    responses=PUBLIC_RESOURCE_RESPONSES,
)
async def read(identifier: str, session: AsyncSession = Depends(get_db)) -> dict:
    lesson = await get_lesson(session, identifier=identifier)
    return success_envelope(LessonDetail.model_validate(lesson).model_dump(mode="json"))


@progress_router.get(
    "", response_model=PaginatedResponse[ProgressResponse], responses=AUTH_ERROR_RESPONSES
)
async def read_progress(
    pagination: PaginationParams = Depends(pagination_params),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    rows, total = await list_progress(session, user_id=current_user.id, pagination=pagination)
    return success_envelope(
        [ProgressResponse.model_validate(r).model_dump(mode="json") for r in rows],
        meta=pagination_meta(pagination, total),
    )


@progress_router.post(
    "", response_model=SuccessResponse[ProgressResponse], responses=OWNED_RESOURCE_RESPONSES
)
async def create_or_update_progress(
    body: ProgressUpsert,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    progress = await upsert_progress(
        session,
        user_id=current_user.id,
        lesson_id=body.lesson_id,
        status=body.status,
        progress_percent=body.progress_percent,
    )
    return success_envelope(ProgressResponse.model_validate(progress).model_dump(mode="json"))


@progress_router.patch(
    "/{lesson_id}",
    response_model=SuccessResponse[ProgressResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def patch_progress(
    lesson_id: uuid.UUID,
    body: ProgressUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    progress = await update_progress(
        session,
        user_id=current_user.id,
        lesson_id=lesson_id,
        changes=body.changed_fields(),
    )
    return success_envelope(ProgressResponse.model_validate(progress).model_dump(mode="json"))
