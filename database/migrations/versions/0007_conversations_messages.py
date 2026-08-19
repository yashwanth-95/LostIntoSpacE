"""conversations and messages

docs/backend/DATABASE_CONTRACT.md §10 step 7, §2.6 (ownership).

`messages` deliberately carries no user_id: ownership is inherited through
conversation_id. Messages are always fetched in conversation context, so the
authorization join is on a path already being taken, and a denormalized owner
column could contradict its parent.

Revision ID: 0007_conversations_messages
Revises: 0006_learning_progress
Created: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_conversations_messages"
down_revision: str | None = "0006_learning_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("context_type", sa.String(length=30), server_default="general", nullable=False),
        # Soft link, intentionally not a FK: a conversation should survive
        # deletion of the mission/run/lesson it was about.
        sa.Column("context_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_conversations_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "context_type IN ('general', 'tutor', 'failure_analysis', 'recommendation')",
            name="context_type_valid",
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name="status_valid"),
    )
    op.create_index(
        "idx_conversations_user", "conversations", ["user_id", sa.text("updated_at DESC")]
    )

    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # Provenance for "AI explains, models calculate".
        sa.Column(
            "grounding",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("role IN ('user', 'assistant', 'system')", name="role_valid"),
    )
    op.create_index("idx_messages_conversation", "messages", ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_messages_conversation", table_name="messages")
    op.drop_table("messages")
    op.drop_index("idx_conversations_user", table_name="conversations")
    op.drop_table("conversations")
