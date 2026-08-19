"""Ownership resolution for user-owned resources.

Implements the rules in docs/backend/DATABASE_CONTRACT.md §5:

  1. Ownership is derived from the DATABASE by walking foreign keys to
     `users.id`. A client-supplied owner id is never trusted, and no function
     here accepts one.
  2. **404, not 403**, when a row exists but belongs to someone else -
     otherwise the API confirms the existence of other users' data, which is
     an enumeration oracle.
  3. Soft-deleted projects are invisible, and so is everything reachable
     through them: every ownership join filters `projects.deleted_at IS NULL`.

Deep paths stay joins rather than denormalized owner columns (§5 rule 1). If
the 2-3 hops ever become a measured bottleneck the fix is a denormalized
`user_id` on `simulation_runs` - never a weaker check.
"""

import uuid
from typing import TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.models.conversation import Conversation
from src.models.project import Mission, Project
from src.models.vehicle import Vehicle

T = TypeVar("T")


async def count_query(session: AsyncSession, statement: Select) -> int:
    """Total row count for a filtered query, for pagination `meta.total`."""
    subquery = statement.order_by(None).subquery()
    result = await session.execute(select(func.count()).select_from(subquery))
    return int(result.scalar_one())


def owned_projects(user_id: uuid.UUID) -> Select:
    """Base SELECT for a user's live projects. Every project-scoped query
    starts here so the soft-delete filter can never be forgotten."""
    return select(Project).where(Project.user_id == user_id, Project.deleted_at.is_(None))


async def get_owned_project(
    session: AsyncSession, *, project_id: uuid.UUID, user_id: uuid.UUID
) -> Project:
    result = await session.execute(owned_projects(user_id).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        # Covers all three cases identically: no such project, someone else's
        # project, and soft-deleted project.
        raise NotFoundError("Project not found")
    return project


async def get_owned_mission(
    session: AsyncSession, *, mission_id: uuid.UUID, user_id: uuid.UUID
) -> Mission:
    """mission -> project -> user (1 join)."""
    result = await session.execute(
        select(Mission)
        .join(Project, Mission.project_id == Project.id)
        .where(
            Mission.id == mission_id,
            Project.user_id == user_id,
            Project.deleted_at.is_(None),
        )
    )
    mission = result.scalar_one_or_none()
    if mission is None:
        raise NotFoundError("Mission not found")
    return mission


async def get_owned_vehicle(
    session: AsyncSession, *, vehicle_id: uuid.UUID, user_id: uuid.UUID
) -> Vehicle:
    """vehicle -> mission -> project -> user (2 joins)."""
    result = await session.execute(
        select(Vehicle)
        .join(Mission, Vehicle.mission_id == Mission.id)
        .join(Project, Mission.project_id == Project.id)
        .where(
            Vehicle.id == vehicle_id,
            Project.user_id == user_id,
            Project.deleted_at.is_(None),
        )
    )
    vehicle = result.scalar_one_or_none()
    if vehicle is None:
        raise NotFoundError("Vehicle not found")
    return vehicle


async def get_owned_conversation(
    session: AsyncSession, *, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> Conversation:
    """Conversations are owned directly - no join needed."""
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise NotFoundError("Conversation not found")
    return conversation
