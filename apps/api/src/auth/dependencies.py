"""get_current_user - the dependency every protected route uses.

Declares `session: AsyncSession = Depends(get_db)` unconditionally, including
on the "no Authorization header" path. This is deliberately safe: entering an
AsyncSession's `async with` block does not open a network connection by
itself (verified directly against build_session_factory - SQLAlchemy defers
connecting until the first `execute()`), so a request with no token still
gets a clean 401 with no database running, rather than hanging or 500ing.
"""

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.service import get_user_by_id
from src.core.config import Settings, get_settings
from src.core.database import get_db
from src.core.exceptions import UnauthorizedError
from src.core.security import TokenError, decode_access_token
from src.models.user import User

# auto_error=False: a missing header should reach our own UnauthorizedError
# (structured envelope), not FastAPI/Starlette's default 403 "Not authenticated".
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Authentication required", code="UNAUTHORIZED")

    try:
        subject = decode_access_token(credentials.credentials, settings=settings)
    except TokenError as exc:
        raise UnauthorizedError("Invalid or expired access token", code="INVALID_TOKEN") from exc

    try:
        # `sub` is opaque to decode_access_token (it's a generic JWT claim);
        # this app always puts a user UUID there, so that's validated here,
        # at the point the assumption is actually made. A tampered/garbage
        # claim must fail as 401, not as an unhandled uuid.UUID() ValueError
        # surfacing all the way to a 500 once it hits the query bind param.
        user_id = uuid.UUID(subject)
    except ValueError as exc:
        raise UnauthorizedError("Invalid or expired access token", code="INVALID_TOKEN") from exc

    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        # Same code/message whether the token's subject doesn't exist or the
        # account was deactivated after the token was issued - both cases mean
        # "this token no longer grants access," and neither should let a
        # caller distinguish "deleted" from "banned."
        raise UnauthorizedError("Invalid or expired access token", code="INVALID_TOKEN")

    return user
