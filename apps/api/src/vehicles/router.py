"""Vehicle + component routes.

Paths follow docs/api/API.md: `/vehicles/{id}/components` for the collection,
`/components/{id}` for a single component (mounted at the API root, not under
/vehicles, exactly as the contract publishes it).
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.core.database import get_db
from src.core.envelope import success_envelope
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
from src.schemas.vehicle import (
    VehicleComponentCreate,
    VehicleComponentResponse,
    VehicleComponentUpdate,
    VehicleCreate,
    VehicleDetailResponse,
    VehicleResponse,
    VehicleUpdate,
)
from src.vehicles.service import (
    add_component,
    create_vehicle,
    delete_component,
    delete_vehicle,
    get_vehicle_detail,
    list_components,
    list_vehicles,
    update_component,
    update_vehicle,
)

router = APIRouter()
component_router = APIRouter()


@router.post(
    "",
    status_code=201,
    response_model=SuccessResponse[VehicleDetailResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def create(
    body: VehicleCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    vehicle = await create_vehicle(
        session,
        user_id=current_user.id,
        mission_id=body.mission_id,
        name=body.name,
        total_height_m=body.total_height_m,
        components=[c.model_dump() for c in body.components],
    )
    return success_envelope(VehicleDetailResponse.model_validate(vehicle).model_dump(mode="json"))


@router.get("", response_model=PaginatedResponse[VehicleResponse], responses=AUTH_ERROR_RESPONSES)
async def list_(
    mission_id: uuid.UUID | None = Query(default=None),
    pagination: PaginationParams = Depends(pagination_params),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    vehicles, total = await list_vehicles(
        session, user_id=current_user.id, pagination=pagination, mission_id=mission_id
    )
    return success_envelope(
        [VehicleResponse.model_validate(v).model_dump(mode="json") for v in vehicles],
        meta=pagination_meta(pagination, total),
    )


@router.get(
    "/{vehicle_id}",
    response_model=SuccessResponse[VehicleDetailResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def read(
    vehicle_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    vehicle = await get_vehicle_detail(session, vehicle_id=vehicle_id, user_id=current_user.id)
    return success_envelope(VehicleDetailResponse.model_validate(vehicle).model_dump(mode="json"))


@router.patch(
    "/{vehicle_id}",
    response_model=SuccessResponse[VehicleDetailResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def update(
    vehicle_id: uuid.UUID,
    body: VehicleUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    vehicle = await update_vehicle(
        session, vehicle_id=vehicle_id, user_id=current_user.id, changes=body.changed_fields()
    )
    return success_envelope(VehicleDetailResponse.model_validate(vehicle).model_dump(mode="json"))


@router.delete("/{vehicle_id}", status_code=204, responses=OWNED_RESOURCE_RESPONSES)
async def delete(
    vehicle_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await delete_vehicle(session, vehicle_id=vehicle_id, user_id=current_user.id)


@router.get(
    "/{vehicle_id}/components",
    response_model=SuccessResponse[list[VehicleComponentResponse]],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def list_vehicle_components(
    vehicle_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    components = await list_components(session, vehicle_id=vehicle_id, user_id=current_user.id)
    return success_envelope(
        [VehicleComponentResponse.model_validate(c).model_dump(mode="json") for c in components]
    )


@router.post(
    "/{vehicle_id}/components",
    status_code=201,
    response_model=SuccessResponse[VehicleComponentResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def create_vehicle_component(
    vehicle_id: uuid.UUID,
    body: VehicleComponentCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    component = await add_component(
        session, vehicle_id=vehicle_id, user_id=current_user.id, payload=body.model_dump()
    )
    return success_envelope(
        VehicleComponentResponse.model_validate(component).model_dump(mode="json")
    )


@component_router.patch(
    "/{component_id}",
    response_model=SuccessResponse[VehicleComponentResponse],
    responses=OWNED_RESOURCE_RESPONSES,
)
async def update_single_component(
    component_id: uuid.UUID,
    body: VehicleComponentUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    component = await update_component(
        session,
        component_id=component_id,
        user_id=current_user.id,
        changes=body.changed_fields(),
    )
    return success_envelope(
        VehicleComponentResponse.model_validate(component).model_dump(mode="json")
    )


@component_router.delete("/{component_id}", status_code=204, responses=OWNED_RESOURCE_RESPONSES)
async def delete_single_component(
    component_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await delete_component(session, component_id=component_id, user_id=current_user.id)
