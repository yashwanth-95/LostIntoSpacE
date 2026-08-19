"""space_objects, lessons, search_history

Public catalogs plus per-user search history
(docs/backend/DATABASE_CONTRACT.md §10 step 5).

`search_vector` is a STORED GENERATED column, not a trigger: the database
maintains it and there is no trigger function to keep in sync with the model.
`to_tsvector` with a literal regconfig is IMMUTABLE, which is what makes this
legal. Requires PostgreSQL 12+ (0001 enforces 13+).

Revision ID: 0005_catalogs
Revises: 0004_simulation_results
Created: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_catalogs"
down_revision: str | None = "0004_simulation_results"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SPACE_OBJECT_TSV = "to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, ''))"
LESSON_TSV = (
    "to_tsvector('english', coalesce(title, '') || ' ' || "
    "coalesce(summary, '') || ' ' || coalesce(content, ''))"
)


def upgrade() -> None:
    op.create_table(
        "space_objects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("subcategory", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("physical_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("orbital_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("discovery", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "images",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("source_id", sa.String(length=200), nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(SPACE_OBJECT_TSV, persisted=True),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_space_objects"),
    )
    op.create_index("idx_spaceobj_category", "space_objects", ["category"])
    op.create_index(
        "idx_spaceobj_search", "space_objects", ["search_vector"], postgresql_using="gin"
    )
    # Partial unique: makes re-running a seed loader an upsert rather than a
    # duplicate insert. Bundled records without a source_id are exempt.
    op.create_index(
        "idx_spaceobj_source",
        "space_objects",
        ["source", "source_id"],
        unique=True,
        postgresql_where=sa.text("source_id IS NOT NULL"),
    )

    op.create_table(
        "lessons",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("slug", sa.String(length=300), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("difficulty", sa.String(length=20), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "equations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "related_objects",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "related_lessons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "prerequisites",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(LESSON_TSV, persisted=True),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lessons"),
        sa.UniqueConstraint("slug", name="uq_lessons_slug"),
    )
    op.create_index("idx_lessons_category", "lessons", ["category"])
    op.create_index("idx_lessons_search", "lessons", ["search_vector"], postgresql_using="gin")

    op.create_table(
        "search_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        # Nullable: API.md marks /search auth as Optional, so anonymous searches
        # are recorded with no owner.
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_search_history"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_search_history_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index(
        "idx_searchhist_user", "search_history", ["user_id", sa.text("created_at DESC")]
    )


def downgrade() -> None:
    op.drop_index("idx_searchhist_user", table_name="search_history")
    op.drop_table("search_history")
    op.drop_index("idx_lessons_search", table_name="lessons")
    op.drop_index("idx_lessons_category", table_name="lessons")
    op.drop_table("lessons")
    op.drop_index("idx_spaceobj_source", table_name="space_objects")
    op.drop_index("idx_spaceobj_search", table_name="space_objects")
    op.drop_index("idx_spaceobj_category", table_name="space_objects")
    op.drop_table("space_objects")
