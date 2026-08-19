"""projects, missions, vehicles, vehicle_components

Strict FK order: projects -> missions -> vehicles -> vehicle_components
(docs/backend/DATABASE_CONTRACT.md §10 step 3).

NOT CREATED HERE, blocked pending P3 sign-off:
  * vehicle_stages              - SD-6/#25 (mass) and SD-7/#26 (propulsion)
  * vehicle_components.stage_id - an FK into vehicle_stages, so it cannot exist
                                  before that table. Added in the same follow-up
                                  migration.

Revision ID: 0003_project_spine
Revises: 0002_users_and_refresh_tokens
Created: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_project_spine"
down_revision: str | None = "0002_users_and_refresh_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        # Soft delete (SD-8): DELETE /projects/{id} cascades four levels.
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_projects_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'completed', 'archived')",
            name="status_valid",
        ),
    )
    op.create_index(
        "idx_projects_user_active",
        "projects",
        ["user_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "missions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("target_orbit", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("launch_site", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("environment", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="planning", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_missions"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_missions_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('planning', 'ready', 'simulated', 'analyzed')",
            name="status_valid",
        ),
    )
    op.create_index("idx_missions_project", "missions", ["project_id"])

    op.create_table(
        "vehicles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        # UNIQUE enforces the 1:1 that GET /missions/{mid}/vehicle assumes.
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        # Derived caches - recomputed on every component mutation, never authored.
        sa.Column("total_mass_kg", sa.Float(), nullable=True),
        sa.Column("total_height_m", sa.Float(), nullable=True),
        sa.Column("cg_position", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cp_position", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stability_margin", sa.Float(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "validation_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_vehicles"),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["missions.id"],
            name="fk_vehicles_mission_id_missions",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("mission_id", name="uq_vehicles_mission_id"),
    )
    op.create_index("idx_vehicles_mission", "vehicles", ["mission_id"])

    op.create_table(
        "vehicle_components",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        # stage_id deliberately absent - see module docstring.
        sa.Column("component_type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("mass_kg", sa.Float(), nullable=False),
        sa.Column("position", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dimensions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "properties",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_vehicle_components"),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name="fk_vehicle_components_vehicle_id_vehicles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["vehicle_components.id"],
            name="fk_vehicle_components_parent_id_vehicle_components",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("mass_kg >= 0", name="mass_non_negative"),
    )
    op.create_index("idx_components_vehicle", "vehicle_components", ["vehicle_id"])


def downgrade() -> None:
    op.drop_index("idx_components_vehicle", table_name="vehicle_components")
    op.drop_table("vehicle_components")
    op.drop_index("idx_vehicles_mission", table_name="vehicles")
    op.drop_table("vehicles")
    op.drop_index("idx_missions_project", table_name="missions")
    op.drop_table("missions")
    op.drop_index("idx_projects_user_active", table_name="projects")
    op.drop_table("projects")
