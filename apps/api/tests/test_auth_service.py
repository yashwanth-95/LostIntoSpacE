"""Service-layer decision-logic tests using a mocked AsyncSession.

These are genuinely runnable without PostgreSQL - no network call happens,
`session.execute()` is a plain Python mock returning canned rows. What they
prove: given a certain database STATE (a row exists / doesn't / is revoked /
is expired), the service function makes the correct DECISION (raise which
error, revoke what, rotate how).

What they do NOT prove: that the actual SQL executes correctly against real
PostgreSQL, that the UNIQUE/CHECK constraints behave as designed under
concurrent writes, or that a real transaction rollback behaves as expected.
That is exactly what tests/test_auth_live.py covers instead, gated behind
TEST_DATABASE_URL.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.auth.service import (
    authenticate_user,
    register_user,
    revoke_refresh_token,
    rotate_refresh_token,
)
from src.core.config import Settings
from src.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from src.core.security import hash_password, hash_refresh_token
from src.models.user import RefreshToken, User


def make_session(execute_results: list) -> AsyncMock:
    """A fake AsyncSession whose .execute() returns each of `execute_results`
    in order (wrapped so .scalar_one_or_none() works), and whose .add/.flush/
    .refresh/.execute (for non-select statements) are no-ops."""
    session = AsyncMock()

    wrapped = []
    for value in execute_results:
        result = MagicMock()
        result.scalar_one_or_none.return_value = value
        wrapped.append(result)
    session.execute.side_effect = wrapped

    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def make_user(
    *, email: str = "a@example.com", password: str = "correct-password", **kwargs
) -> User:
    user = User(
        email=email,
        username=kwargs.pop("username", "someuser"),
        password_hash=hash_password(password),
        display_name=kwargs.pop("display_name", None),
        is_active=kwargs.pop("is_active", True),
    )
    user.id = kwargs.pop("id", uuid.uuid4())
    user.created_at = datetime.now(UTC)
    return user


def make_refresh_token_row(
    *,
    raw_token: str,
    user_id: uuid.UUID,
    revoked: bool = False,
    expired: bool = False,
) -> RefreshToken:
    now = datetime.now(UTC)
    row = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=now - timedelta(days=1) if expired else now + timedelta(days=7),
    )
    row.id = uuid.uuid4()
    row.revoked_at = now - timedelta(hours=1) if revoked else None
    return row


@pytest.fixture
def settings() -> Settings:
    return Settings(jwt_refresh_token_expire_days=7)


# ---------- register_user: duplicate detection ----------


@pytest.mark.asyncio
async def test_register_user_rejects_duplicate_email() -> None:
    session = make_session(execute_results=[make_user(email="taken@example.com")])
    with pytest.raises(ConflictError) as exc_info:
        await register_user(
            session,
            email="taken@example.com",
            username="newuser",
            password="longenough123",
            display_name=None,
        )
    assert exc_info.value.code == "EMAIL_ALREADY_EXISTS"
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_register_user_rejects_duplicate_username() -> None:
    # First execute() call (email lookup) -> None (available);
    # second call (username lookup) -> an existing user (taken).
    session = make_session(execute_results=[None, make_user(username="taken")])
    with pytest.raises(ConflictError) as exc_info:
        await register_user(
            session,
            email="new@example.com",
            username="taken",
            password="longenough123",
            display_name=None,
        )
    assert exc_info.value.code == "USERNAME_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_register_user_hashes_the_password_not_stores_it_raw() -> None:
    session = make_session(execute_results=[None, None])
    user = await register_user(
        session,
        email="new@example.com",
        username="newuser",
        password="my-plaintext-password",
        display_name="New User",
    )
    assert user.password_hash != "my-plaintext-password"
    assert "my-plaintext-password" not in user.password_hash


@pytest.mark.asyncio
async def test_register_user_succeeds_when_neither_email_nor_username_taken() -> None:
    session = make_session(execute_results=[None, None])
    user = await register_user(
        session,
        email="new@example.com",
        username="newuser",
        password="longenough123",
        display_name=None,
    )
    assert user.email == "new@example.com"
    session.add.assert_called_once()


# ---------- authenticate_user: login success/failure ----------


@pytest.mark.asyncio
async def test_authenticate_user_succeeds_with_correct_password() -> None:
    existing = make_user(email="a@example.com", password="right-password")
    session = make_session(execute_results=[existing])
    user = await authenticate_user(session, email="a@example.com", password="right-password")
    assert user is existing


@pytest.mark.asyncio
async def test_authenticate_user_fails_with_wrong_password() -> None:
    session = make_session(execute_results=[make_user(email="a@example.com", password="right")])
    with pytest.raises(UnauthorizedError) as exc_info:
        await authenticate_user(session, email="a@example.com", password="wrong")
    assert exc_info.value.code == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_authenticate_user_fails_when_user_does_not_exist() -> None:
    session = make_session(execute_results=[None])
    with pytest.raises(UnauthorizedError) as exc_info:
        await authenticate_user(session, email="nobody@example.com", password="whatever")
    assert exc_info.value.code == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_authenticate_user_fails_for_inactive_account() -> None:
    inactive = make_user(email="a@example.com", password="right", is_active=False)
    session = make_session(execute_results=[inactive])
    with pytest.raises(UnauthorizedError) as exc_info:
        await authenticate_user(session, email="a@example.com", password="right")
    assert exc_info.value.code == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_authenticate_user_error_message_does_not_reveal_which_check_failed() -> None:
    """Wrong-password and user-not-found must be indistinguishable to the
    caller - checked here by asserting both raise the identical message."""
    session_a = make_session(execute_results=[None])
    session_b = make_session(execute_results=[make_user(password="right")])

    with pytest.raises(UnauthorizedError) as exc_a:
        await authenticate_user(session_a, email="nobody@example.com", password="x")
    with pytest.raises(UnauthorizedError) as exc_b:
        await authenticate_user(session_b, email="a@example.com", password="wrong")

    assert exc_a.value.message == exc_b.value.message
    assert exc_a.value.code == exc_b.value.code


# ---------- rotate_refresh_token: rotation and reuse detection ----------


@pytest.mark.asyncio
async def test_rotate_refresh_token_rejects_unknown_token(settings: Settings) -> None:
    session = make_session(execute_results=[None])
    with pytest.raises(UnauthorizedError) as exc_info:
        await rotate_refresh_token(session, raw_token="does-not-exist", settings=settings)
    assert exc_info.value.code == "INVALID_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_rotate_refresh_token_rejects_expired_token(settings: Settings) -> None:
    user_id = uuid.uuid4()
    row = make_refresh_token_row(raw_token="tok", user_id=user_id, expired=True)
    session = make_session(execute_results=[row])
    with pytest.raises(UnauthorizedError) as exc_info:
        await rotate_refresh_token(session, raw_token="tok", settings=settings)
    assert exc_info.value.code == "INVALID_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_rotate_refresh_token_rejects_and_locks_out_on_reuse(settings: Settings) -> None:
    """The core security property: presenting an already-revoked (rotated
    away) token must both fail AND revoke all of that user's other active
    tokens, since it's a signal of possible theft."""
    user_id = uuid.uuid4()
    revoked_row = make_refresh_token_row(raw_token="stolen-tok", user_id=user_id, revoked=True)
    # Second entry: the lockout UPDATE issued by revoke_all_active_refresh_tokens.
    # Its result is unused by the code (an UPDATE row count, not scalar_one_or_none),
    # so any value satisfies the mock's second call.
    session = make_session(execute_results=[revoked_row, None])

    with pytest.raises(UnauthorizedError) as exc_info:
        await rotate_refresh_token(session, raw_token="stolen-tok", settings=settings)

    assert exc_info.value.code == "INVALID_REFRESH_TOKEN"
    # revoke_all_active_refresh_tokens issues an UPDATE via session.execute -
    # confirm the lockout statement was actually issued, not skipped.
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_rotate_refresh_token_reuse_error_matches_normal_invalid_token_error(
    settings: Settings,
) -> None:
    """An attacker must not be able to distinguish 'reuse detected, you're
    locked out' from 'this token never existed' - both produce the identical
    error, or the lockout itself becomes an information leak."""
    user_id = uuid.uuid4()

    session_unknown = make_session(execute_results=[None])
    session_reused = make_session(
        execute_results=[
            make_refresh_token_row(raw_token="t", user_id=user_id, revoked=True),
            None,  # the lockout UPDATE's result - see comment above
        ]
    )

    with pytest.raises(UnauthorizedError) as exc_unknown:
        await rotate_refresh_token(session_unknown, raw_token="t", settings=settings)
    with pytest.raises(UnauthorizedError) as exc_reused:
        await rotate_refresh_token(session_reused, raw_token="t", settings=settings)

    assert exc_unknown.value.message == exc_reused.value.message
    assert exc_unknown.value.code == exc_reused.value.code


@pytest.mark.asyncio
async def test_rotate_refresh_token_succeeds_and_revokes_the_old_row(settings: Settings) -> None:
    user_id = uuid.uuid4()
    old_row = make_refresh_token_row(raw_token="valid-tok", user_id=user_id)
    active_user = make_user(id=user_id, is_active=True)
    session = make_session(execute_results=[old_row, active_user])

    user, new_raw_token, new_row = await rotate_refresh_token(
        session, raw_token="valid-tok", settings=settings
    )

    assert user.id == user_id
    assert new_raw_token != "valid-tok"
    assert old_row.revoked_at is not None
    assert old_row.replaced_by == new_row.id


@pytest.mark.asyncio
async def test_rotate_refresh_token_rejects_when_owning_user_is_inactive(
    settings: Settings,
) -> None:
    user_id = uuid.uuid4()
    row = make_refresh_token_row(raw_token="tok", user_id=user_id)
    inactive_user = make_user(id=user_id, is_active=False)
    session = make_session(execute_results=[row, inactive_user])

    with pytest.raises(UnauthorizedError) as exc_info:
        await rotate_refresh_token(session, raw_token="tok", settings=settings)
    assert exc_info.value.code == "INVALID_REFRESH_TOKEN"


# ---------- revoke_refresh_token: logout ----------


@pytest.mark.asyncio
async def test_revoke_refresh_token_marks_the_row_revoked() -> None:
    user_id = uuid.uuid4()
    row = make_refresh_token_row(raw_token="tok", user_id=user_id)
    session = make_session(execute_results=[row])

    await revoke_refresh_token(session, user_id=user_id, raw_token="tok")
    assert row.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_refresh_token_is_idempotent_on_already_revoked_token() -> None:
    user_id = uuid.uuid4()
    row = make_refresh_token_row(raw_token="tok", user_id=user_id, revoked=True)
    original_revoked_at = row.revoked_at
    session = make_session(execute_results=[row])

    await revoke_refresh_token(session, user_id=user_id, raw_token="tok")  # must not raise
    assert row.revoked_at == original_revoked_at  # untouched, not re-stamped


@pytest.mark.asyncio
async def test_revoke_refresh_token_rejects_unknown_token() -> None:
    session = make_session(execute_results=[None])
    with pytest.raises(NotFoundError):
        await revoke_refresh_token(session, user_id=uuid.uuid4(), raw_token="does-not-exist")


@pytest.mark.asyncio
async def test_revoke_refresh_token_rejects_token_owned_by_a_different_user() -> None:
    """A caller must not be able to revoke someone else's refresh token just
    by knowing/guessing the raw value together with their own access token."""
    owner_id = uuid.uuid4()
    attacker_id = uuid.uuid4()
    row = make_refresh_token_row(raw_token="victim-tok", user_id=owner_id)
    session = make_session(execute_results=[row])

    with pytest.raises(NotFoundError):
        await revoke_refresh_token(session, user_id=attacker_id, raw_token="victim-tok")
