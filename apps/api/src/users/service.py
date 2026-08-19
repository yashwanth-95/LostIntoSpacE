"""Profile and preference updates for the authenticated user.

Every function takes the already-authenticated `User` object resolved by
`get_current_user` from the token - never a user id from the request body.
There is no code path here that can act on a user the caller didn't
authenticate as.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.service import get_user_by_email, get_user_by_username
from src.core.exceptions import ConflictError
from src.models.user import User


async def update_profile(session: AsyncSession, *, user: User, changes: dict[str, Any]) -> User:
    """Applies an allow-listed partial update.

    Uniqueness is re-checked here rather than relying solely on the database's
    UNIQUE constraints: a constraint violation surfaces as an opaque
    IntegrityError (a 500 through the generic handler), whereas this produces
    the same structured 409 that registration returns. The DB constraints
    remain the real guarantee against a concurrent duplicate - this is the
    friendly path, not the safety net.
    """
    new_email = changes.get("email")
    if new_email is not None and new_email != user.email:
        existing = await get_user_by_email(session, new_email)
        if existing is not None:
            raise ConflictError(
                "An account with this email already exists", code="EMAIL_ALREADY_EXISTS"
            )

    new_username = changes.get("username")
    if new_username is not None and new_username != user.username:
        existing_username = await get_user_by_username(session, new_username)
        if existing_username is not None:
            raise ConflictError("This username is already taken", code="USERNAME_ALREADY_EXISTS")

    for field, value in changes.items():
        setattr(user, field, value)

    await session.flush()
    await session.refresh(user)
    return user


async def merge_preferences(
    session: AsyncSession, *, user: User, incoming: dict[str, Any]
) -> dict[str, Any]:
    """Shallow-merges incoming keys over the stored ones.

    PATCH semantics: sending `{"theme": "dark"}` changes only `theme` and
    leaves every other preference intact. Setting a key to null REMOVES it,
    which is how a client clears a preference without having to send the whole
    object back.
    """
    merged = dict(user.preferences or {})
    for key, value in incoming.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value

    # Reassign rather than mutate in place: SQLAlchemy tracks JSONB changes by
    # identity, so mutating the existing dict would not mark the column dirty
    # and the UPDATE would silently never happen.
    user.preferences = merged
    await session.flush()
    await session.refresh(user)
    return user.preferences
