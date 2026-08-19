"""Vehicle + component persistence.

Ownership runs vehicle -> mission -> project -> user (2 joins), per
DATABASE_CONTRACT.md §5. A vehicle is reachable only through a mission the
caller's project owns, so there is no way to touch another user's design by
guessing an id.

NO PHYSICS HERE. Validation is limited to structural/referential integrity -
does the mission exist and belong to you, is the parent component part of this
same vehicle, is mass non-negative. Whether a design will actually fly (thrust
-to-weight, stability margin, staging feasibility) is P3's simulation engine's
job and is deliberately not duplicated.
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.authz import count_query, get_owned_mission, get_owned_vehicle
from src.core.exceptions import BadRequestError, ConflictError, NotFoundError
from src.models.project import Mission, Project
from src.models.vehicle import Vehicle, VehicleComponent
from src.schemas.common import PaginationParams


async def _vehicle_with_components(session: AsyncSession, vehicle_id: uuid.UUID) -> Vehicle:
    result = await session.execute(
        select(Vehicle).options(selectinload(Vehicle.components)).where(Vehicle.id == vehicle_id)
    )
    return result.scalar_one()


async def create_vehicle(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    mission_id: uuid.UUID,
    name: str,
    total_height_m: float | None,
    components: list[dict[str, Any]],
) -> Vehicle:
    # Verifying the mission through get_owned_mission is what stops a caller
    # attaching a vehicle to someone else's mission: an unowned mission_id is
    # indistinguishable from a nonexistent one (404).
    await get_owned_mission(session, mission_id=mission_id, user_id=user_id)

    existing = await session.execute(select(Vehicle).where(Vehicle.mission_id == mission_id))
    if existing.scalar_one_or_none() is not None:
        # The DB UNIQUE on mission_id would raise an opaque IntegrityError;
        # this turns the 1:1 rule into a readable 409 instead.
        raise ConflictError("This mission already has a vehicle", code="VEHICLE_ALREADY_EXISTS")

    vehicle = Vehicle(mission_id=mission_id, name=name, total_height_m=total_height_m)
    session.add(vehicle)
    await session.flush()

    for component in components:
        # parent_id is dropped on inline creation: a client cannot know the ids
        # of components being created in the same request, so any value here
        # would necessarily reference a component of some OTHER vehicle.
        # Nesting is established afterwards via PATCH on the component.
        payload = {k: v for k, v in component.items() if k != "parent_id"}
        session.add(VehicleComponent(vehicle_id=vehicle.id, **payload))

    await session.flush()
    return await _vehicle_with_components(session, vehicle.id)


async def list_vehicles(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    pagination: PaginationParams,
    mission_id: uuid.UUID | None = None,
) -> tuple[list[Vehicle], int]:
    """All vehicles the user owns, across their projects."""
    statement = (
        select(Vehicle)
        .join(Mission, Vehicle.mission_id == Mission.id)
        .join(Project, Mission.project_id == Project.id)
        .where(Project.user_id == user_id, Project.deleted_at.is_(None))
    )
    if mission_id is not None:
        statement = statement.where(Vehicle.mission_id == mission_id)

    total = await count_query(session, statement)
    result = await session.execute(
        statement.order_by(Vehicle.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    return list(result.scalars().all()), total


async def get_vehicle_detail(
    session: AsyncSession, *, vehicle_id: uuid.UUID, user_id: uuid.UUID
) -> Vehicle:
    await get_owned_vehicle(session, vehicle_id=vehicle_id, user_id=user_id)
    return await _vehicle_with_components(session, vehicle_id)


async def update_vehicle(
    session: AsyncSession,
    *,
    vehicle_id: uuid.UUID,
    user_id: uuid.UUID,
    changes: dict[str, Any],
) -> Vehicle:
    vehicle = await get_owned_vehicle(session, vehicle_id=vehicle_id, user_id=user_id)
    for field, value in changes.items():
        setattr(vehicle, field, value)
    await session.flush()
    return await _vehicle_with_components(session, vehicle_id)


async def delete_vehicle(
    session: AsyncSession, *, vehicle_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Hard delete - components cascade with it.

    Not soft-deleted: SD-8 scoped soft delete to `projects` alone, because
    that is where the destructive four-level cascade lives. A vehicle is
    rebuildable and its deletion is already protected by the RESTRICT on
    simulation_runs.vehicle_id, which blocks removing a design that has
    recorded flight history.
    """
    vehicle = await get_owned_vehicle(session, vehicle_id=vehicle_id, user_id=user_id)
    await session.delete(vehicle)
    await session.flush()


# ---------- components ----------


async def add_component(
    session: AsyncSession,
    *,
    vehicle_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: dict[str, Any],
) -> VehicleComponent:
    await get_owned_vehicle(session, vehicle_id=vehicle_id, user_id=user_id)
    parent_id = payload.get("parent_id")
    if parent_id is not None:
        await _require_same_vehicle(session, vehicle_id=vehicle_id, component_id=parent_id)

    component = VehicleComponent(vehicle_id=vehicle_id, **payload)
    session.add(component)
    await session.flush()
    await session.refresh(component)
    return component


async def list_components(
    session: AsyncSession, *, vehicle_id: uuid.UUID, user_id: uuid.UUID
) -> list[VehicleComponent]:
    await get_owned_vehicle(session, vehicle_id=vehicle_id, user_id=user_id)
    result = await session.execute(
        select(VehicleComponent)
        .where(VehicleComponent.vehicle_id == vehicle_id)
        .order_by(VehicleComponent.sort_order, VehicleComponent.created_at)
    )
    return list(result.scalars().all())


async def update_component(
    session: AsyncSession,
    *,
    component_id: uuid.UUID,
    user_id: uuid.UUID,
    changes: dict[str, Any],
) -> VehicleComponent:
    component = await _get_owned_component(session, component_id=component_id, user_id=user_id)

    if "parent_id" in changes and changes["parent_id"] is not None:
        new_parent = changes["parent_id"]
        if new_parent == component_id:
            # Direct self-parenting. Deeper cycles are still possible - see the
            # cycle-risk note in models/vehicle.py; a full ancestry walk is
            # deferred until nesting is actually used by the builder.
            raise BadRequestError("A component cannot be its own parent")
        await _require_same_vehicle(
            session, vehicle_id=component.vehicle_id, component_id=new_parent
        )

    for field, value in changes.items():
        setattr(component, field, value)
    await session.flush()
    await session.refresh(component)
    return component


async def delete_component(
    session: AsyncSession, *, component_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    component = await _get_owned_component(session, component_id=component_id, user_id=user_id)
    await session.delete(component)
    await session.flush()


async def _get_owned_component(
    session: AsyncSession, *, component_id: uuid.UUID, user_id: uuid.UUID
) -> VehicleComponent:
    """component -> vehicle -> mission -> project -> user (3 joins)."""
    result = await session.execute(
        select(VehicleComponent)
        .join(Vehicle, VehicleComponent.vehicle_id == Vehicle.id)
        .join(Mission, Vehicle.mission_id == Mission.id)
        .join(Project, Mission.project_id == Project.id)
        .where(
            VehicleComponent.id == component_id,
            Project.user_id == user_id,
            Project.deleted_at.is_(None),
        )
    )
    component = result.scalar_one_or_none()
    if component is None:
        raise NotFoundError("Component not found")
    return component


async def _require_same_vehicle(
    session: AsyncSession, *, vehicle_id: uuid.UUID, component_id: uuid.UUID
) -> None:
    """A parent must belong to the same vehicle.

    Without this, a caller could nest a component under a part of a DIFFERENT
    vehicle - the FK alone permits it, since it only requires the target to be
    some vehicle_components row.
    """
    result = await session.execute(
        select(func.count())
        .select_from(VehicleComponent)
        .where(VehicleComponent.id == component_id, VehicleComponent.vehicle_id == vehicle_id)
    )
    if int(result.scalar_one()) == 0:
        raise BadRequestError("parent_id must reference a component of the same vehicle")


async def get_vehicle_for_mission(
    session: AsyncSession, *, mission_id: uuid.UUID, user_id: uuid.UUID
) -> Vehicle:
    """The 1:1 lookup behind `GET /missions/{mid}/vehicle`.

    Ownership is re-checked through the mission rather than trusted from the
    caller, and a mission with no vehicle 404s exactly like a mission that
    isn't yours - the caller learns nothing either way.
    """
    await get_owned_mission(session, mission_id=mission_id, user_id=user_id)
    result = await session.execute(
        select(Vehicle)
        .options(selectinload(Vehicle.components))
        .where(Vehicle.mission_id == mission_id)
    )
    vehicle = result.scalar_one_or_none()
    if vehicle is None:
        raise NotFoundError("This mission has no vehicle")
    return vehicle
