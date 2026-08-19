"""Learning progress.

Contract: docs/backend/DATABASE_CONTRACT.md §4.11
Decision: DECISION_LOG #22 - lessons + learning_progress only. No
learning_paths, courses, quizzes, or quiz_attempts: none is referenced by any
endpoint in API.md or by any of the 8 acts in DEMO_RUNBOOK.md.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.content import Lesson
    from src.models.user import User

PROGRESS_STATUSES = ("not_started", "in_progress", "completed")


class LearningProgress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per (user, lesson) the user has actually interacted with.

    ABSENCE OF A ROW MEANS "NOT STARTED". Do not pre-create rows for every
    user x lesson pair - that cross product grows with the catalog and carries no
    information. `not_started` exists in the enum only for rows that regress.

    The UNIQUE (user_id, lesson_id) makes POST /learning/progress a natural
    idempotent upsert (ON CONFLICT ... DO UPDATE).
    """

    __tablename__ = "learning_progress"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="in_progress")
    progress_percent: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="learning_progress")
    lesson: Mapped["Lesson"] = relationship(back_populates="progress")

    __table_args__ = (
        CheckConstraint(f"status IN {PROGRESS_STATUSES}", name="status_valid"),
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="percent_range"),
        # Keeps status and completed_at from ever disagreeing - cheap guard
        # against a bug class that is otherwise invisible until reporting time.
        CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)", name="completed_consistent"
        ),
        Index("uq_progress_user_lesson", "user_id", "lesson_id", unique=True),
        Index("idx_progress_user", "user_id", "status"),
    )
