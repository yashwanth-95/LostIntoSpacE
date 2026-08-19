"""learning_progress

Needs both users (0002) and lessons (0005). Backs POST /learning/progress, which
API.md already publishes with no table behind it
(docs/backend/DATABASE_CONTRACT.md §4.11, DECISION_LOG #22).

Revision ID: 0006_learning_progress
Revises: 0005_catalogs
Created: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_learning_progress"
down_revision: str | None = "0005_catalogs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_progress",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="in_progress", nullable=False),
        sa.Column("progress_percent", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_progress"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_learning_progress_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["lessons.id"],
            name="fk_learning_progress_lesson_id_lessons",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('not_started', 'in_progress', 'completed')",
            name="status_valid",
        ),
        sa.CheckConstraint("progress_percent BETWEEN 0 AND 100", name="percent_range"),
        # Keeps status and completed_at from ever disagreeing.
        sa.CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)",
            name="completed_consistent",
        ),
    )
    # Makes POST /learning/progress a natural idempotent upsert.
    op.create_index(
        "uq_progress_user_lesson", "learning_progress", ["user_id", "lesson_id"], unique=True
    )
    op.create_index("idx_progress_user", "learning_progress", ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_progress_user", table_name="learning_progress")
    op.drop_index("uq_progress_user_lesson", table_name="learning_progress")
    op.drop_table("learning_progress")
