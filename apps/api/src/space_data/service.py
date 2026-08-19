"""Space-object reads.

Read-only by design: P4 owns ingestion and writes rows through
`database/seeds/` loaders, so there is no create/update/delete here. The API
behaves identically whether the rows came from a live NASA fetch or bundled
fallback data - which is what makes the offline demo mode work.

Search uses PostgreSQL full-text over the `search_vector` GENERATED column
when a query is supplied. That column is maintained by the database itself
(DECISION_LOG #29), so search works on any row P4 inserts without them having
to remember to populate an index.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.authz import count_query
from src.core.exceptions import NotFoundError
from src.models.content import SpaceObject
from src.schemas.common import PaginationParams

SORTABLE_FIELDS = {
    "name": SpaceObject.name,
    "category": SpaceObject.category,
    "created_at": SpaceObject.created_at,
    "last_updated": SpaceObject.last_updated,
}


async def list_space_objects(
    session: AsyncSession,
    *,
    pagination: PaginationParams,
    category: str | None = None,
    source: str | None = None,
    q: str | None = None,
    sort: str = "name",
    order: str = "asc",
) -> tuple[list[SpaceObject], int]:
    statement = select(SpaceObject)

    if category is not None:
        statement = statement.where(SpaceObject.category == category)
    if source is not None:
        statement = statement.where(SpaceObject.source == source)
    if q:
        # plainto_tsquery (not to_tsquery) so arbitrary user input can't be a
        # syntax error - it treats the string as plain words rather than a
        # tsquery expression with operators.
        statement = statement.where(
            SpaceObject.search_vector.op("@@")(func.plainto_tsquery("english", q))
        )

    total = await count_query(session, statement)

    column = SORTABLE_FIELDS.get(sort, SpaceObject.name)
    statement = statement.order_by(column.desc() if order == "desc" else column.asc())

    result = await session.execute(statement.offset(pagination.offset).limit(pagination.limit))
    return list(result.scalars().all()), total


async def get_space_object(session: AsyncSession, *, object_id: uuid.UUID) -> SpaceObject:
    result = await session.execute(select(SpaceObject).where(SpaceObject.id == object_id))
    space_object = result.scalar_one_or_none()
    if space_object is None:
        raise NotFoundError("Space object not found")
    return space_object


async def list_space_object_categories(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(SpaceObject.category).distinct().order_by(SpaceObject.category)
    )
    return list(result.scalars().all())
