"""Project and Mission models.

Contract: docs/backend/DATABASE_CONTRACT.md §4, §3 (cardinality)
Decision: SD-8 - `projects` is the only table with soft delete, because
DELETE /projects/{id} cascades four levels down to simulation results.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.simulation import SimulationRun
    from src.models.user import User
    from src.models.vehicle import Vehicle

PROJECT_STATUSES = ("draft", "active", "completed", "archived")
MISSION_STATUSES = ("planning", "ready", "simulated", "analyzed")


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    # `metadata` is reserved on DeclarativeBase, so the attribute is renamed while
    # the column keeps its contracted name.
    project_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Soft delete (SD-8). Distinct from status='archived': archived is a
    # user-chosen shelf, deleted_at is removal with a recovery window.
    # Every project-scoped query must filter `deleted_at IS NULL`.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="projects")
    missions: Mapped[list["Mission"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(f"status IN {PROJECT_STATUSES}", name="status_valid"),
        # Partial index: the dashboard only ever lists live projects.
        Index(
            "idx_projects_user_active",
            "user_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class Mission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A mission belongs to exactly one project and is never shared between them.

    The JSONB columns hold shapes that vary by mission type and are consumed
    wholesale by the simulation engine rather than queried field-by-field. If we
    ever filter missions by launch site, `launch_site.name` should be promoted to
    a real column.
    """

    __tablename__ = "missions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)
    target_orbit: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    launch_site: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    environment: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="planning")

    project: Mapped["Project"] = relationship(back_populates="missions")
    # 1:1 - enforced by the UNIQUE constraint on vehicles.mission_id.
    vehicle: Mapped["Vehicle | None"] = relationship(
        back_populates="mission", cascade="all, delete-orphan", passive_deletes=True
    )
    simulation_runs: Mapped[list["SimulationRun"]] = relationship(
        back_populates="mission", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(f"status IN {MISSION_STATUSES}", name="status_valid"),
        Index("idx_missions_project", "project_id"),
    )
