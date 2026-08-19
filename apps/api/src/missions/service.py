"""Mission CRUD.

Ownership is mission -> project -> user (1 join). Creating a mission requires
owning the target project, which is what stops a caller inserting a mission
into someone else's project by supplying its id.

No physics, no simulation, no event generation - a mission here is a
persisted configuration record. Runs and their events belong to
`simulation_runs` (DECISION_LOG #21).
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.authz import count_query, get_owned_mission, get_owned_project
from src.models.project import Mission, Project
from src.schemas.common import PaginationParams


async def create_mission(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID, payload: dict[str, Any]
) -> Mission:
    # 404s for a project that doesn't exist OR isn't yours - same response
    # either way, so project ids can't be probed.
    await get_owned_project(session, project_id=project_id, user_id=user_id)
    mission = Mission(project_id=project_id, **payload)
    session.add(mission)
    await session.flush()
    await session.refresh(mission)
    return mission


async def list_missions(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    pagination: PaginationParams,
    project_id: uuid.UUID | None = None,
    status: str | None = None,
) -> tuple[list[Mission], int]:
    statement = (
        select(Mission)
        .join(Project, Mission.project_id == Project.id)
        .where(Project.user_id == user_id, Project.deleted_at.is_(None))
    )
    if project_id is not None:
        statement = statement.where(Mission.project_id == project_id)
    if status is not None:
        statement = statement.where(Mission.status == status)

    total = await count_query(session, statement)
    result = await session.execute(
        statement.order_by(Mission.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    return list(result.scalars().all()), total


async def get_mission(
    session: AsyncSession, *, mission_id: uuid.UUID, user_id: uuid.UUID
) -> Mission:
    return await get_owned_mission(session, mission_id=mission_id, user_id=user_id)


async def update_mission(
    session: AsyncSession,
    *,
    mission_id: uuid.UUID,
    user_id: uuid.UUID,
    changes: dict[str, Any],
) -> Mission:
    mission = await get_owned_mission(session, mission_id=mission_id, user_id=user_id)
    for field, value in changes.items():
        setattr(mission, field, value)
    await session.flush()
    await session.refresh(mission)
    return mission


async def delete_mission(
    session: AsyncSession, *, mission_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    mission = await get_owned_mission(session, mission_id=mission_id, user_id=user_id)
    await session.delete(mission)
    await session.flush()
