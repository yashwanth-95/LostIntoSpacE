"""Lesson and learning-progress schemas.

SCOPE (DECISION_LOG #22): lessons + learning_progress ONLY. `learning_paths`,
`courses`, `quizzes`, and `quiz_attempts` were deliberately deferred - lessons
already carry `category`, `sort_order`, and `prerequisites`, which is a
learning path expressed in columns that already exist. Nothing here
reintroduces them.

Lessons are a PUBLIC catalog (unowned, per DATABASE_CONTRACT.md §5): readable
without a token, writable only by seed loaders. Progress is private per user.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ProgressStatus = Literal["not_started", "in_progress", "completed"]


class LessonSummary(BaseModel):
    """List view - omits `content`, which is full Markdown and would make a
    catalog page enormous."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    slug: str
    category: str | None
    difficulty: str | None
    summary: str | None
    prerequisites: list[Any]
    sort_order: int


class LessonDetail(LessonSummary):
    content: str
    equations: list[Any]
    related_objects: list[Any]
    related_lessons: list[Any]
    created_at: datetime


class ProgressUpsert(BaseModel):
    """POST /learning/progress - create or update in one idempotent call.

    The UNIQUE (user_id, lesson_id) constraint makes this a natural upsert,
    which is why there is no separate create-vs-update distinction and why
    calling it twice is not an error (DATABASE_CONTRACT.md §4.11).
    """

    model_config = ConfigDict(extra="forbid")

    lesson_id: UUID
    status: ProgressStatus | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)


class ProgressUpdate(BaseModel):
    """PATCH /learning/progress/{lesson_id} - lesson_id comes from the path."""

    model_config = ConfigDict(extra="forbid")

    status: ProgressStatus | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)

    def changed_fields(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class ProgressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    lesson_id: UUID
    status: str
    progress_percent: int
    last_viewed_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
