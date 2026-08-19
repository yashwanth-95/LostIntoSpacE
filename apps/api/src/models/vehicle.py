"""Vehicle and VehicleComponent models.

Canonical entity name is `vehicle`, not `rocket` (DECISION_LOG #20). The UI says
"Rocket"; the database, API, .rkt format, and P3's SimConfig all say vehicle.

DELIBERATELY NOT IN THIS FILE — blocked pending P3 sign-off:

  * `vehicle_stages`            - its mass field (SD-6 / DECISION_LOG #25) and
                                  propulsion field authority (SD-7 / #26) are
                                  both unresolved. Guessing either would bake a
                                  contradiction into a migration.
  * `VehicleComponent.stage_id` - a foreign key INTO vehicle_stages, so it
                                  cannot exist before that table does. This is a
                                  knock-on consequence of the same blocker, not
                                  an oversight; components are fully usable
                                  without it because `vehicle_id` (not stage_id)
                                  is their real ownership link.

Both land together in a follow-up migration once P3 answers. See
docs/backend/DATABASE_CONTRACT.md §10.
"""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from src.models.project import Mission
    from src.models.simulation import SimulationRun


class Vehicle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One vehicle per mission (1:1, enforced by UNIQUE on mission_id).

    `total_mass_kg`, `cg_position`, `cp_position`, `stability_margin`,
    `is_valid`, and `validation_errors` are DERIVED CACHES, not authored values.
    They must be recomputed by a single service function on every mutation of
    components (and, later, stages). A route that writes a component without
    triggering recomputation leaves the UI showing a green checkmark on a broken
    rocket - see DATABASE_CONTRACT.md §4.1-4.8.
    """

    __tablename__ = "vehicles"

    mission_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("missions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # enforces the documented 1:1 that GET /missions/{id}/vehicle assumes
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    total_mass_kg: Mapped[float | None] = mapped_column(Float)
    total_height_m: Mapped[float | None] = mapped_column(Float)
    cg_position: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cp_position: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    stability_margin: Mapped[float | None] = mapped_column(Float)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    validation_errors: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    mission: Mapped["Mission"] = relationship(back_populates="vehicle")
    components: Mapped[list["VehicleComponent"]] = relationship(
        back_populates="vehicle", cascade="all, delete-orphan", passive_deletes=True
    )
    simulation_runs: Mapped[list["SimulationRun"]] = relationship(back_populates="vehicle")

    __table_args__ = (Index("idx_vehicles_mission", "mission_id"),)


class VehicleComponent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A discrete, positioned part.

    `mass_kg` is the AUTHORITATIVE mass for every modelled part (SD-6): the
    stability model needs individual masses at positions to compute
    CG = Sigma(m_i * x_i) / Sigma(m_i).

    `dimensions` and `properties` are JSONB because the shape is genuinely
    type-dependent - a nose cone has {length, diameter}, a fin has {span, chord}.
    Modelling that relationally would mean a sparse table of every possible
    dimension, or one table per component type.
    """

    __tablename__ = "vehicle_components"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    # stage_id: deferred with vehicle_stages - see module docstring.
    component_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    mass_kg: Mapped[float] = mapped_column(Float, nullable=False)
    position: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    properties: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Self-reference for assembly nesting (fins attached to a body tube).
    # SET NULL: removing an assembly must not delete its children.
    # NOTE: nothing here prevents a cycle (A parent of B, B parent of A) - the
    # service layer must enforce acyclicity on write. KNOWN_ISSUES risk 5.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vehicle_components.id", ondelete="SET NULL")
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    vehicle: Mapped["Vehicle"] = relationship(back_populates="components")

    __table_args__ = (
        # Physical impossibility, so it belongs in the database: "never trust
        # frontend validation" means the last line of defence is here.
        CheckConstraint("mass_kg >= 0", name="mass_non_negative"),
        Index("idx_components_vehicle", "vehicle_id"),
    )
