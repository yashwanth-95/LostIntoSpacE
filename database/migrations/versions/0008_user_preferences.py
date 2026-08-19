"""add users.preferences

Phase 6 needs per-user preferences (GET/PATCH /users/me/preferences). The
finalized contract REJECTED a separate `profiles` table (SD-3: "users already
carries the fields; split adds a join for nothing"), so this is a column on
`users`, not a new table.

JSONB is the right storage here by the contract's own rule - "JSONB only where
flexibility is genuinely useful". Preference keys are UI concerns owned by P1
(theme, units, panel layout...) and will change without backend involvement;
modelling them as columns would mean a migration every time P1 adds a toggle.
Validation of size/shape happens in the Pydantic layer - see
src/schemas/user.py.

NOTE ON NUMBERING: `0008` was informally reserved in DATABASE_CONTRACT.md §10
for the P3-blocked `vehicle_stages`/`telemetry_points` tables. Those are still
blocked, and Alembic revisions are ordered by the down_revision chain rather
than by filename, so taking 0008 here is harmless - the P3 tables land as a
later revision whenever P3 signs off.

Revision ID: 0008_user_preferences
Revises: 0007_conversations_messages
Created: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_user_preferences"
down_revision: str | None = "0007_conversations_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "preferences")
