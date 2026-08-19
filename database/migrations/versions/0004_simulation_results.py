"""simulation_runs, simulation_events, failure_events

docs/backend/DATABASE_CONTRACT.md §10 step 4.

NOT CREATED HERE, blocked pending P3 sign-off:
  * telemetry_points - flat float8 columns vs JSONB, and whether attitude is
                       persisted (SD-5/#24). Nothing references telemetry_points,
                       so deferring it blocks nothing else.

Revision ID: 0004_simulation_results
Revises: 0003_project_spine
Created: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_simulation_results"
down_revision: str | None = "0003_project_spine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Vocabulary from docs/simulation/SIMULATION.md (the authority). DATABASE.md
# carried a stale list - see KNOWN_ISSUES P-9 / DATABASE_CONTRACT.md C-4.
EVENT_TYPE_CHECK = (
    "event_type IN ('ignition', 'liftoff', 'max_q', 'meco', 'staging', "
    "'apogee', 'supersonic', 'impact') OR event_type LIKE 'failure\\_%'"
)


def upgrade() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("result_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("sim_time_s", sa.Float(), nullable=True),
        sa.Column("total_steps", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=30), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_simulation_runs"),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["missions.id"],
            name="fk_simulation_runs_mission_id_missions",
            ondelete="CASCADE",
        ),
        # RESTRICT: deleting a vehicle with recorded flight history would destroy
        # results the user may still be analysing.
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name="fk_simulation_runs_vehicle_id_vehicles",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="status_valid",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('success', 'partial', 'failure')",
            name="outcome_valid",
        ),
    )
    op.create_index("idx_simruns_mission", "simulation_runs", ["mission_id"])

    op.create_table(
        "simulation_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("simulation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("t", sa.Float(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_simulation_events"),
        sa.ForeignKeyConstraint(
            ["simulation_id"],
            ["simulation_runs.id"],
            name="fk_simulation_events_simulation_id_simulation_runs",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(EVENT_TYPE_CHECK, name="event_type_valid"),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('info', 'warning', 'critical', 'fatal')",
            name="severity_valid",
        ),
    )
    op.create_index("idx_events_sim", "simulation_events", ["simulation_id", "t"])

    op.create_table(
        "failure_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subsystem", sa.String(length=50), nullable=True),
        sa.Column("failure_mode", sa.String(length=100), nullable=True),
        sa.Column("trigger_condition", sa.Text(), nullable=True),
        sa.Column("trigger_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "contributing_factors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("consequence", sa.Text(), nullable=True),
        sa.Column("educational_explanation", sa.Text(), nullable=True),
        sa.Column("recommended_fix", sa.Text(), nullable=True),
        sa.Column(
            "related_lessons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        # DATABASE.md omits created_at on this table alone; DATABASE_CONTRACT.md
        # §6 requires it everywhere, so it is added here.
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_failure_events"),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["simulation_events.id"],
            name="fk_failure_events_event_id_simulation_events",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("event_id", name="uq_failure_events_event_id"),
    )


def downgrade() -> None:
    op.drop_table("failure_events")
    op.drop_index("idx_events_sim", table_name="simulation_events")
    op.drop_table("simulation_events")
    op.drop_index("idx_simruns_mission", table_name="simulation_runs")
    op.drop_table("simulation_runs")
