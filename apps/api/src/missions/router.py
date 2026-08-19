"""Mission routes.

docs/api/API.md publishes both `/projects/{pid}/missions` (list/create scoped
to a project) and `/missions/{id}` (read/update/delete). Both are provided:
the nested form is mounted from the projects router prefix, the flat form
here. The Phase 10 brief's `GET/POST /missions` is the flat collection with an
optional `project_id` filter.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.core.database import get_db
from src.core.envelope import success_envelope
from src.missions.service import (
    create_mission,
    delete_mission,
    get_mission,
    list_missions,
    update_mission,
)
from src.models.user import User
from src.schemas.common import (
    AUTH_ERROR_RESPONSES,
    OWNED_RESOURCE_RESPONSES,
    PaginatedResponse,
    PaginationParams,
    SuccessResponse,
    pagination_meta,
    pagination_params,
)
from src.schemas.mission import MissionCreate, MissionResponse, MissionStatus, MissionUpdate
from src.schemas.vehicle import VehicleCreateNested, VehicleDetailResponse
from src.vehicles.service import create_vehicle, get_vehicle_for_mission

router = APIRouter()


@router.post(
    "",
    status_code=201,
    response_model=SuccessResponse[MissionResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def create(
    body: MissionCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    payload = body.model_dump(exclude={"project_id"})
    mission = await create_mission(
        session, user_id=current_user.id, project_id=body.project_id, payload=payload
    )
    return success_envelope(MissionResponse.model_validate(mission).model_dump(mode="json"))


@router.get("", response_model=PaginatedResponse[MissionResponse], responses=AUTH_ERROR_RESPONSES)
async def list_(
    project_id: uuid.UUID | None = Query(default=None),
    status: MissionStatus | None = Query(default=None),
    pagination: PaginationParams = Depends(pagination_params),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    missions, total = await list_missions(
        session,
        user_id=current_user.id,
        pagination=pagination,
        project_id=project_id,
        status=status,
    )
    return success_envelope(
        [MissionResponse.model_validate(m).model_dump(mode="json") for m in missions],
        meta=pagination_meta(pagination, total),
    )


@router.get(
    "/{mission_id}",
    response_model=SuccessResponse[MissionResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def read(
    mission_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    mission = await get_mission(session, mission_id=mission_id, user_id=current_user.id)
    return success_envelope(MissionResponse.model_validate(mission).model_dump(mode="json"))


@router.patch(
    "/{mission_id}",
    response_model=SuccessResponse[MissionResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def update(
    mission_id: uuid.UUID,
    body: MissionUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    mission = await update_mission(
        session, mission_id=mission_id, user_id=current_user.id, changes=body.changed_fields()
    )
    return success_envelope(MissionResponse.model_validate(mission).model_dump(mode="json"))


@router.delete("/{mission_id}", status_code=204, responses=OWNED_RESOURCE_RESPONSES)
async def delete(
    mission_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await delete_mission(session, mission_id=mission_id, user_id=current_user.id)


# ---------------------------------------------------------------------------
# Mission -> vehicle access.
#
# docs/api/API.md publishes `GET/POST /missions/{mid}/vehicle`, and it is the
# path P3's builder naturally uses: "load the vehicle for the mission I am
# simulating." Thin aliases over the vehicle service - the flat `/vehicles`
# collection is unchanged and both stay in sync because there is one
# implementation underneath.
#
# Singular `vehicle`, not `vehicles`: the relationship is 1:1, enforced by the
# UNIQUE on vehicles.mission_id.
# ---------------------------------------------------------------------------


@router.get(
    "/{mission_id}/vehicle",
    response_model=SuccessResponse[VehicleDetailResponse],
    responses=OWNED_RESOURCE_RESPONSES,
    tags=["vehicles"],
)
async def read_mission_vehicle(
    mission_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """404 covers three cases identically: no such mission, not your mission,
    and the mission has no vehicle yet."""
    await get_mission(session, mission_id=mission_id, user_id=current_user.id)
    vehicle = await get_vehicle_for_mission(session, mission_id=mission_id, user_id=current_user.id)
    return success_envelope(VehicleDetailResponse.model_validate(vehicle).model_dump(mode="json"))


@router.post(
    "/{mission_id}/vehicle",
    status_code=201,
    response_model=SuccessResponse[VehicleDetailResponse],
    responses=OWNED_RESOURCE_RESPONSES,
    tags=["vehicles"],
)
async def create_mission_vehicle(
    mission_id: uuid.UUID,
    body: VehicleCreateNested,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """`mission_id` comes from the PATH. Returns 409 if the mission already
    has a vehicle - API.md calls this "create/replace", but silently destroying
    an existing design (and its components) on a POST is not a behaviour worth
    making easy. DELETE then POST, or PATCH the existing one.
    """
    vehicle = await create_vehicle(
        session,
        user_id=current_user.id,
        mission_id=mission_id,
        name=body.name,
        total_height_m=body.total_height_m,
        components=[c.model_dump() for c in body.components],
    )
    return success_envelope(VehicleDetailResponse.model_validate(vehicle).model_dump(mode="json"))
