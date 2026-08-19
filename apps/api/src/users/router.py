"""GET/PATCH /users/me and /users/me/preferences.

All four routes are `/me`-scoped: there is deliberately no
`GET /users/{id}` endpoint. The current contract has no feature that needs one
(no sharing, no public profiles - `DATABASE_CONTRACT.md` O-3 is still open),
and adding a by-id lookup would create a user-enumeration surface for nothing.

`GET /users/me` overlaps `GET /auth/me` by design: /auth/me is part of the
auth handshake P1 calls right after login, /users/me is the profile resource
that PATCH acts on. Both are in docs/api/API.md's shape; they return the same
data through different schemas (UserResponse vs UserProfileResponse, the
latter adding `updated_at`).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.core.database import get_db
from src.core.envelope import success_envelope
from src.models.user import User
from src.schemas.common import (
    AUTH_ERROR_RESPONSES,
    SuccessResponse,
)
from src.schemas.user import (
    PreferencesResponse,
    PreferencesUpdate,
    UserProfileResponse,
    UserProfileUpdate,
)
from src.users.service import merge_preferences, update_profile

router = APIRouter()


@router.get(
    "/me", response_model=SuccessResponse[UserProfileResponse], responses=AUTH_ERROR_RESPONSES
)
async def read_me(current_user: User = Depends(get_current_user)) -> dict:
    return success_envelope(
        UserProfileResponse.model_validate(current_user).model_dump(mode="json")
    )


@router.patch(
    "/me", response_model=SuccessResponse[UserProfileResponse], responses=AUTH_ERROR_RESPONSES
)
async def update_me(
    body: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    updated = await update_profile(session, user=current_user, changes=body.changed_fields())
    return success_envelope(UserProfileResponse.model_validate(updated).model_dump(mode="json"))


@router.get(
    "/me/preferences",
    response_model=SuccessResponse[PreferencesResponse],
    responses=AUTH_ERROR_RESPONSES,
)
async def read_my_preferences(current_user: User = Depends(get_current_user)) -> dict:
    return success_envelope(
        PreferencesResponse(preferences=current_user.preferences or {}).model_dump(mode="json")
    )


@router.patch(
    "/me/preferences",
    response_model=SuccessResponse[PreferencesResponse],
    responses=AUTH_ERROR_RESPONSES,
)
async def update_my_preferences(
    body: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    merged = await merge_preferences(session, user=current_user, incoming=body.preferences)
    return success_envelope(PreferencesResponse(preferences=merged).model_dump(mode="json"))
