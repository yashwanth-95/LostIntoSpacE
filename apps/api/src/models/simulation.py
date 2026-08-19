"""Simulation run, event, and failure models.

`simulation_runs.id` is the STABLE PUBLIC ANCHOR for anything referring to "a
simulation result" - reports, AI failure analyses, conversation context, .rkt
`results_ref`. Outside the simulation module, reference the run, never its
contents: telemetry and events are internal detail and still in flux
(DATABASE_CONTRACT.md §8).

DELIBERATELY NOT IN THIS FILE — blocked pending P3 sign-off:

  * `telemetry_points` - whether the vectors are flat float8 columns or JSONB,
                         and whether attitude is persisted, both depend on P3's
                         output contract (SD-5 / DECISION_LOG #24). Nothing
                         references telemetry_points, so deferring it blocks
                         nothing else. See DATABASE_CONTRACT.md §4.9.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.project import Mission
    from src.models.vehicle import Vehicle

RUN_STATUSES = ("pending", "running", "completed", "failed", "cancelled")
RUN_OUTCOMES = ("success", "partial", "failure")
EVENT_SEVERITIES = ("info", "warning", "critical", "fatal")

# Vocabulary from docs/simulation/SIMULATION.md, which is the authority here.
# docs/architecture/DATABASE.md carried a stale list (had `landing`, lacked
# `liftoff`/`supersonic`); see KNOWN_ISSUES P-9 / DATABASE_CONTRACT.md C-4.
# Failure events are a `failure_*` family rather than a fixed set, so the CHECK
# allows the enumerated values plus that prefix.
EVENT_TYPES = (
    "ignition",
    "liftoff",
    "max_q",
    "meco",
    "staging",
    "apogee",
    "supersonic",
    "impact",
)


class SimulationRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "simulation_runs"

    mission_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT, not CASCADE: deleting a vehicle that has recorded flight history
    # would destroy results the user may still be analysing. Blocking the delete
    # is the safer failure mode (DATABASE_CONTRACT.md §6).
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False
    )
    # Mirrors P3's SimConfig shape. Deliberately JSONB: the backend must not
    # fossilize the simulation team's config structure into columns.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    duration_s: Mapped[float | None] = mapped_column(Float)  # wall clock
    sim_time_s: Mapped[float | None] = mapped_column(Float)  # simulated time
    total_steps: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(String(30))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    mission: Mapped["Mission"] = relationship(back_populates="simulation_runs")
    vehicle: Mapped["Vehicle"] = relationship(back_populates="simulation_runs")
    events: Mapped[list["SimulationEvent"]] = relationship(
        back_populates="simulation_run", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(f"status IN {RUN_STATUSES}", name="status_valid"),
        CheckConstraint(f"outcome IS NULL OR outcome IN {RUN_OUTCOMES}", name="outcome_valid"),
        Index("idx_simruns_mission", "mission_id"),
    )


class SimulationEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Events belong to a run, not to a mission (DECISION_LOG #21).

    One mission is simulated many times - the demo's core loop is
    fail -> understand -> improve -> re-simulate - and each run has its own
    event timeline.
    """

    __tablename__ = "simulation_events"

    simulation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False
    )
    t: Mapped[float] = mapped_column(Float, nullable=False)  # seconds since ignition
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(20))
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    description: Mapped[str | None] = mapped_column(Text)

    simulation_run: Mapped["SimulationRun"] = relationship(back_populates="events")
    failure: Mapped["FailureEvent | None"] = relationship(
        back_populates="event", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(
            f"event_type IN {EVENT_TYPES} OR event_type LIKE 'failure\\_%'",
            name="event_type_valid",
        ),
        CheckConstraint(
            f"severity IS NULL OR severity IN {EVENT_SEVERITIES}", name="severity_valid"
        ),
        Index("idx_events_sim", "simulation_id", "t"),
    )


class FailureEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The educational diagnosis of one simulation event.

    Content fields are produced by P4's AI layer and stored here; the backend
    persists, it does not generate them.

    NOTE: docs/architecture/DATABASE.md omits `created_at` on this table alone.
    DATABASE_CONTRACT.md §6 requires it on every table, so it is added here and
    DATABASE.md should be corrected to match.
    """

    __tablename__ = "failure_events"

    event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("simulation_events.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # at most one diagnosis per event
    )
    subsystem: Mapped[str | None] = mapped_column(String(50))
    failure_mode: Mapped[str | None] = mapped_column(String(100))
    trigger_condition: Mapped[str | None] = mapped_column(Text)
    trigger_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    contributing_factors: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    consequence: Mapped[str | None] = mapped_column(Text)
    educational_explanation: Mapped[str | None] = mapped_column(Text)
    recommended_fix: Mapped[str | None] = mapped_column(Text)
    related_lessons: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    event: Mapped["SimulationEvent"] = relationship(back_populates="failure")
