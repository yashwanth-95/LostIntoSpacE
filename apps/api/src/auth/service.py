"""Auth business logic: registration, login, and refresh-token lifecycle.

Ownership/authorization principle (DATABASE_CONTRACT.md §5): the backend
derives identity from the database, never trusts a client-supplied id. Every
function here that needs "the current user" gets it by decoding a token and
looking the row up - nothing here accepts a caller-asserted user id.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from src.core.security import (
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from src.models.user import RefreshToken, User

logger = logging.getLogger("auth")

# Returned for every refresh-token failure - not found, expired, or reused -
# so the response never tells a caller *which* check failed. See
# rotate_refresh_token for why reuse specifically must not be distinguishable.
_INVALID_REFRESH_TOKEN_MESSAGE = "Invalid or expired refresh token"
_INVALID_REFRESH_TOKEN_CODE = "INVALID_REFRESH_TOKEN"


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID | str) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    username: str,
    password: str,
    display_name: str | None,
) -> User:
    """Registration reveals *which* field conflicts (email vs. username) -
    unlike login, this is standard and intentional: the entire point of a
    register form is telling the user whether they already have an account."""
    if await get_user_by_email(session, email) is not None:
        raise ConflictError(
            "An account with this email already exists", code="EMAIL_ALREADY_EXISTS"
        )
    if await get_user_by_username(session, username) is not None:
        raise ConflictError("This username is already taken", code="USERNAME_ALREADY_EXISTS")

    user = User(
        email=email,
        username=username,
        password_hash=hash_password(password),
        display_name=display_name,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def authenticate_user(session: AsyncSession, *, email: str, password: str) -> User:
    """Raises the SAME UnauthorizedError for wrong email, wrong password, and
    an inactive account, so a caller can never learn which one it was -
    unlike registration, login must not reveal account existence."""
    user = await get_user_by_email(session, email)
    if user is None or not verify_password(password, user.password_hash) or not user.is_active:
        raise UnauthorizedError("Invalid email or password", code="INVALID_CREDENTIALS")
    return user


async def issue_refresh_token(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    settings: Settings,
    user_agent: str | None = None,
    ip_address: str | None = None,
    replaces: RefreshToken | None = None,
) -> tuple[str, RefreshToken]:
    """Creates a new refresh_tokens row. Returns (raw_token, row) - the raw
    token is returned to the caller exactly once and never stored; only its
    hash is persisted.

    If `replaces` is given (rotation), that row's `revoked_at`/`replaced_by`
    are set as part of the same flush - caller's transaction covers both.
    """
    raw_token = generate_refresh_token()
    now = datetime.now(UTC)
    row = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=now + timedelta(days=settings.jwt_refresh_token_expire_days),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    session.add(row)
    await session.flush()

    if replaces is not None:
        replaces.revoked_at = now
        replaces.replaced_by = row.id

    return raw_token, row


async def revoke_all_active_refresh_tokens(session: AsyncSession, *, user_id: uuid.UUID) -> None:
    """Defensive lockout triggered by refresh-token reuse detection - see
    rotate_refresh_token. Not part of the normal logout path."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def _find_refresh_token_by_raw(session: AsyncSession, raw_token: str) -> RefreshToken | None:
    token_hash = hash_refresh_token(raw_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    return result.scalar_one_or_none()


async def rotate_refresh_token(
    session: AsyncSession,
    *,
    raw_token: str,
    settings: Settings,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[User, str, RefreshToken]:
    """Validates and rotates a refresh token. Returns (user, new_raw_token, new_row).

    Reuse detection: a refresh token that has already been revoked - by a
    prior rotation or by logout - being presented again is treated as a
    possible theft replay. ALL of that user's currently-active refresh tokens
    are revoked defensively, and the SAME generic error is raised as for any
    other invalid token, so an attacker gets no signal that reuse specifically
    was what triggered the lockout.
    """
    row = await _find_refresh_token_by_raw(session, raw_token)

    if row is None:
        raise UnauthorizedError(_INVALID_REFRESH_TOKEN_MESSAGE, code=_INVALID_REFRESH_TOKEN_CODE)

    if row.revoked_at is not None:
        logger.warning("refresh token reuse detected for user_id=%s", row.user_id)
        await revoke_all_active_refresh_tokens(session, user_id=row.user_id)
        raise UnauthorizedError(_INVALID_REFRESH_TOKEN_MESSAGE, code=_INVALID_REFRESH_TOKEN_CODE)

    if row.expires_at <= datetime.now(UTC):
        raise UnauthorizedError(_INVALID_REFRESH_TOKEN_MESSAGE, code=_INVALID_REFRESH_TOKEN_CODE)

    user = await get_user_by_id(session, row.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError(_INVALID_REFRESH_TOKEN_MESSAGE, code=_INVALID_REFRESH_TOKEN_CODE)

    new_raw_token, new_row = await issue_refresh_token(
        session,
        user_id=user.id,
        settings=settings,
        user_agent=user_agent,
        ip_address=ip_address,
        replaces=row,
    )
    return user, new_raw_token, new_row


async def revoke_refresh_token(
    session: AsyncSession, *, user_id: uuid.UUID, raw_token: str
) -> None:
    """Used by logout. Idempotent - revoking an already-revoked token is not
    an error, so a double-submitted logout click doesn't surface as a
    failure. Unlike rotate_refresh_token, presenting an already-revoked token
    HERE is not treated as a reuse/theft signal: logout isn't the
    token-issuance path an attacker would be racing to exploit.
    """
    row = await _find_refresh_token_by_raw(session, raw_token)
    if row is None or row.user_id != user_id:
        raise NotFoundError("Refresh token not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
