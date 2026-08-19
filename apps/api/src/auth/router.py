"""POST /auth/register, /login, /refresh, /logout; GET /auth/me.

Auth type per docs/api/API.md:
    register, login   - Public
    me, logout         - Bearer (access token)
    refresh            - Refresh token, carried in the request body (it is not
                         a JWT, so there's nothing for the Bearer scheme to
                         validate structurally - see docs/api/API.md's
                         "Token semantics" note).
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.service import (
    authenticate_user,
    issue_refresh_token,
    register_user,
    revoke_refresh_token,
    rotate_refresh_token,
)
from src.core.config import Settings, get_settings
from src.core.database import get_db
from src.core.envelope import success_envelope
from src.core.security import create_access_token
from src.models.user import User
from src.schemas.auth import (
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
    RegisterRequest,
    UserResponse,
)
from src.schemas.common import AUTH_ERROR_RESPONSES, ErrorResponse, SuccessResponse

router = APIRouter()


def _client_info(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return user_agent, ip_address


async def _issue_auth_response(
    session: AsyncSession, user: User, settings: Settings, request: Request
) -> AuthResponse:
    access_token, expires_in = create_access_token(user_id=str(user.id), settings=settings)
    user_agent, ip_address = _client_info(request)
    raw_refresh_token, _ = await issue_refresh_token(
        session,
        user_id=user.id,
        settings=settings,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    return AuthResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/register",
    status_code=201,
    response_model=SuccessResponse[AuthResponse],
    responses={409: {"model": ErrorResponse, "description": "Email or username already exists"}},
)
async def register(
    body: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Auto-logs in on success: returns the same AuthResponse shape as
    /auth/login rather than requiring a second round trip, and to keep one
    response type across register/login/refresh for the frontend to model."""
    user = await register_user(
        session,
        email=body.email,
        username=body.username,
        password=body.password,
        display_name=body.display_name,
    )
    result = await _issue_auth_response(session, user, settings, request)
    return success_envelope(result.model_dump(mode="json"))


@router.post(
    "/login",
    response_model=SuccessResponse[AuthResponse],
    responses={401: {"model": ErrorResponse, "description": "Invalid email or password"}},
)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    user = await authenticate_user(session, email=body.email, password=body.password)
    result = await _issue_auth_response(session, user, settings, request)
    return success_envelope(result.model_dump(mode="json"))


@router.get("/me", response_model=SuccessResponse[UserResponse], responses=AUTH_ERROR_RESPONSES)
async def me(current_user: User = Depends(get_current_user)) -> dict:
    return success_envelope(UserResponse.model_validate(current_user).model_dump(mode="json"))


@router.post(
    "/refresh",
    response_model=SuccessResponse[AuthResponse],
    responses={
        401: {"model": ErrorResponse, "description": "Invalid, expired, or reused refresh token"}
    },
)
async def refresh(
    body: RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    user_agent, ip_address = _client_info(request)
    user, new_raw_token, _ = await rotate_refresh_token(
        session,
        raw_token=body.refresh_token,
        settings=settings,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    access_token, expires_in = create_access_token(user_id=str(user.id), settings=settings)
    result = AuthResponse(
        access_token=access_token,
        refresh_token=new_raw_token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )
    return success_envelope(result.model_dump(mode="json"))


@router.post(
    "/logout", response_model=SuccessResponse[LogoutResponse], responses=AUTH_ERROR_RESPONSES
)
async def logout(
    body: LogoutRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    await revoke_refresh_token(session, user_id=current_user.id, raw_token=body.refresh_token)
    return success_envelope(LogoutResponse(revoked=True).model_dump())
