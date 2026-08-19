"""Lesson reads (public) and progress writes (per-user).

Progress uses PostgreSQL's ON CONFLICT DO UPDATE against the
`uq_progress_user_lesson` unique index rather than a read-then-write. That
makes it genuinely idempotent and free of the race where two concurrent
requests both see "no row" and both try to insert - the second would hit the
UNIQUE constraint and 500.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.authz import count_query
from src.core.exceptions import NotFoundError
from src.models.content import Lesson
from src.models.learning import LearningProgress
from src.schemas.common import PaginationParams


async def list_lessons(
    session: AsyncSession,
    *,
    pagination: PaginationParams,
    category: str | None = None,
    difficulty: str | None = None,
) -> tuple[list[Lesson], int]:
    statement = select(Lesson)
    if category is not None:
        statement = statement.where(Lesson.category == category)
    if difficulty is not None:
        statement = statement.where(Lesson.difficulty == difficulty)

    total = await count_query(session, statement)
    result = await session.execute(
        statement.order_by(Lesson.sort_order, Lesson.title)
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    return list(result.scalars().all()), total


async def get_lesson(session: AsyncSession, *, identifier: str) -> Lesson:
    """Accepts a UUID or a slug.

    docs/api/API.md publishes `GET /lessons/{slug}` while the Phase 9 brief
    asks for `/lessons/{id}`. Supporting both keeps the published contract
    working without P1 having to change anything, and costs one branch.
    """
    try:
        lesson_uuid = uuid.UUID(identifier)
    except ValueError:
        statement = select(Lesson).where(Lesson.slug == identifier)
    else:
        statement = select(Lesson).where(Lesson.id == lesson_uuid)

    result = await session.execute(statement)
    lesson = result.scalar_one_or_none()
    if lesson is None:
        raise NotFoundError("Lesson not found")
    return lesson


async def list_categories(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(Lesson.category)
        .where(Lesson.category.is_not(None))
        .distinct()
        .order_by(Lesson.category)
    )
    return [row for row in result.scalars().all() if row is not None]


async def list_progress(
    session: AsyncSession, *, user_id: uuid.UUID, pagination: PaginationParams
) -> tuple[list[LearningProgress], int]:
    statement = select(LearningProgress).where(LearningProgress.user_id == user_id)
    total = await count_query(session, statement)
    result = await session.execute(
        statement.order_by(LearningProgress.updated_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    return list(result.scalars().all()), total


def _derive_progress_values(status: str | None, progress_percent: int | None) -> dict[str, Any]:
    """Keeps status/percent/completed_at mutually consistent.

    The DB CHECK `(status = 'completed') = (completed_at IS NOT NULL)` will
    reject any row where those disagree, so the rules are applied here rather
    than letting an inconsistent request become an opaque IntegrityError:
      - status='completed'      -> percent 100, completed_at now
      - percent=100 (no status) -> status='completed', completed_at now
      - anything else           -> completed_at cleared
    """
    values: dict[str, Any] = {}
    now = datetime.now(UTC)

    if status == "completed" or (status is None and progress_percent == 100):
        values["status"] = "completed"
        values["progress_percent"] = 100
        values["completed_at"] = now
    else:
        if status is not None:
            values["status"] = status
        if progress_percent is not None:
            values["progress_percent"] = progress_percent
        values["completed_at"] = None

    values["last_viewed_at"] = now
    return values


async def upsert_progress(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    lesson_id: uuid.UUID,
    status: str | None,
    progress_percent: int | None,
) -> LearningProgress:
    # Verify the lesson exists first: the FK would otherwise raise an opaque
    # IntegrityError, and "lesson not found" is the useful answer.
    lesson_exists = await session.execute(
        select(func.count()).select_from(Lesson).where(Lesson.id == lesson_id)
    )
    if int(lesson_exists.scalar_one()) == 0:
        raise NotFoundError("Lesson not found")

    values = _derive_progress_values(status, progress_percent)
    insert_values = {
        "user_id": user_id,
        "lesson_id": lesson_id,
        "status": values.get("status", "in_progress"),
        "progress_percent": values.get("progress_percent", 0),
        "completed_at": values.get("completed_at"),
        "last_viewed_at": values["last_viewed_at"],
    }

    statement = (
        pg_insert(LearningProgress)
        .values(**insert_values)
        .on_conflict_do_update(
            index_elements=["user_id", "lesson_id"],
            set_={k: v for k, v in values.items()},
        )
        .returning(LearningProgress)
    )
    result = await session.execute(statement)
    await session.flush()
    return result.scalar_one()


async def update_progress(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    lesson_id: uuid.UUID,
    changes: dict[str, Any],
) -> LearningProgress:
    """PATCH an existing progress row. 404s if the user has none for this
    lesson - unlike POST, this does not create one."""
    result = await session.execute(
        select(LearningProgress).where(
            LearningProgress.user_id == user_id, LearningProgress.lesson_id == lesson_id
        )
    )
    progress = result.scalar_one_or_none()
    if progress is None:
        raise NotFoundError("No progress recorded for this lesson")

    values = _derive_progress_values(changes.get("status"), changes.get("progress_percent"))
    for field, value in values.items():
        setattr(progress, field, value)

    await session.flush()
    await session.refresh(progress)
    return progress
