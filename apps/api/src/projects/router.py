"""Project CRUD routes - POST/GET/PATCH/DELETE /projects, per docs/api/API.md."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.core.database import get_db
from src.core.envelope import success_envelope
from src.missions.service import create_mission, list_missions
from src.models.user import User
from src.projects.service import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)
from src.schemas.common import (
    AUTH_ERROR_RESPONSES,
    OWNED_RESOURCE_RESPONSES,
    PaginatedResponse,
    PaginationParams,
    SuccessResponse,
    pagination_meta,
    pagination_params,
)
from src.schemas.mission import MissionCreateNested, MissionResponse
from src.schemas.project import ProjectCreate, ProjectResponse, ProjectStatus, ProjectUpdate

router = APIRouter()


@router.post(
    "",
    status_code=201,
    response_model=SuccessResponse[ProjectResponse],
    responses=AUTH_ERROR_RESPONSES,
)
async def create(
    body: ProjectCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    project = await create_project(
        session,
        user_id=current_user.id,  # from the token, never from the body
        name=body.name,
        description=body.description,
        status=body.status,
        metadata=body.metadata,
    )
    return success_envelope(ProjectResponse.model_validate(project).model_dump(mode="json"))


@router.get("", response_model=PaginatedResponse[ProjectResponse], responses=AUTH_ERROR_RESPONSES)
async def list_(
    status: ProjectStatus | None = Query(default=None),
    pagination: PaginationParams = Depends(pagination_params),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    projects, total = await list_projects(
        session, user_id=current_user.id, pagination=pagination, status=status
    )
    return success_envelope(
        [ProjectResponse.model_validate(p).model_dump(mode="json") for p in projects],
        meta=pagination_meta(pagination, total),
    )


@router.get(
    "/{project_id}",
    response_model=SuccessResponse[ProjectResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def read(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    # A non-UUID path segment is rejected by FastAPI as 422 before this runs;
    # a well-formed UUID belonging to someone else 404s inside get_project.
    project = await get_project(session, project_id=project_id, user_id=current_user.id)
    return success_envelope(ProjectResponse.model_validate(project).model_dump(mode="json"))


@router.patch(
    "/{project_id}",
    response_model=SuccessResponse[ProjectResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def update(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    project = await update_project(
        session,
        project_id=project_id,
        user_id=current_user.id,
        changes=body.changed_fields(),
    )
    return success_envelope(ProjectResponse.model_validate(project).model_dump(mode="json"))


@router.delete("/{project_id}", status_code=204, responses=OWNED_RESOURCE_RESPONSES)
async def delete(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await delete_project(session, project_id=project_id, user_id=current_user.id)


# ---------------------------------------------------------------------------
# Nested mission routes.
#
# docs/api/API.md publishes `GET/POST /projects/{pid}/missions`, and P1 builds
# against that contract. These are thin aliases over the same mission service
# the flat `/missions` collection uses - no duplicated logic, no second code
# path, and the flat form (with ?project_id=) keeps working unchanged.
# ---------------------------------------------------------------------------


@router.get(
    "/{project_id}/missions",
    response_model=PaginatedResponse[MissionResponse],
    responses=OWNED_RESOURCE_RESPONSES,
    tags=["missions"],
)
async def list_project_missions(
    project_id: uuid.UUID,
    pagination: PaginationParams = Depends(pagination_params),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    # Resolve the project first so an unowned/nonexistent id 404s here rather
    # than silently returning an empty list, which would imply it exists.
    await get_project(session, project_id=project_id, user_id=current_user.id)
    missions, total = await list_missions(
        session, user_id=current_user.id, pagination=pagination, project_id=project_id
    )
    return success_envelope(
        [MissionResponse.model_validate(m).model_dump(mode="json") for m in missions],
        meta=pagination_meta(pagination, total),
    )


@router.post(
    "/{project_id}/missions",
    status_code=201,
    response_model=SuccessResponse[MissionResponse],
    responses=OWNED_RESOURCE_RESPONSES,
    tags=["missions"],
)
async def create_project_mission(
    project_id: uuid.UUID,
    body: MissionCreateNested,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """`project_id` comes from the PATH, not the body - there is no way to
    create a mission in a different project than the one addressed."""
    mission = await create_mission(
        session, user_id=current_user.id, project_id=project_id, payload=body.model_dump()
    )
    return success_envelope(MissionResponse.model_validate(mission).model_dump(mode="json"))
