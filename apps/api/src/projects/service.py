"""Project CRUD.

Ownership is enforced by `core.authz.get_owned_project`, which resolves
project -> user through the database and raises NotFoundError (404, not 403)
for someone else's project, a nonexistent id, and a soft-deleted project
alike. No function here accepts a caller-supplied owner id.
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.authz import count_query, get_owned_project, owned_projects
from src.models.project import Mission, Project
from src.schemas.common import PaginationParams


async def create_project(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    description: str | None,
    status: str,
    metadata: dict[str, Any],
) -> Project:
    project = Project(
        user_id=user_id,
        name=name,
        description=description,
        status=status,
        project_metadata=metadata,
    )
    session.add(project)
    await session.flush()
    await session.refresh(project)
    return project


async def list_projects(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    pagination: PaginationParams,
    status: str | None = None,
) -> tuple[list[Project], int]:
    """Returns (page_of_projects, total_matching). Newest first."""
    statement = owned_projects(user_id)
    if status is not None:
        statement = statement.where(Project.status == status)

    total = await count_query(session, statement)
    result = await session.execute(
        statement.order_by(Project.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    return list(result.scalars().all()), total


async def get_project(
    session: AsyncSession, *, project_id: uuid.UUID, user_id: uuid.UUID
) -> Project:
    return await get_owned_project(session, project_id=project_id, user_id=user_id)


async def update_project(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    changes: dict[str, Any],
) -> Project:
    project = await get_owned_project(session, project_id=project_id, user_id=user_id)
    for field, value in changes.items():
        # The wire field is `metadata`; the ORM attribute is `project_metadata`
        # (SQLAlchemy reserves `metadata`). Translate at this boundary only.
        setattr(project, "project_metadata" if field == "metadata" else field, value)
    await session.flush()
    await session.refresh(project)
    return project


async def delete_project(
    session: AsyncSession, *, project_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """SOFT delete (SD-8): sets `deleted_at` rather than removing the row.

    A hard DELETE would cascade four levels - missions, vehicles, components,
    simulation runs and their telemetry - destroying a student's entire body of
    work irreversibly on one click. After this the project is invisible to
    every query, because they all go through `owned_projects()`.
    """
    project = await get_owned_project(session, project_id=project_id, user_id=user_id)
    project.deleted_at = func.now()
    await session.flush()


async def count_missions(session: AsyncSession, *, project_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(Mission).where(Mission.project_id == project_id)
    )
    return int(result.scalar_one())
