"""Pure unit tests for password hashing and JWT access-token logic.

No database, no mocking - these exercise the real bcrypt and jose libraries
end to end. This is the highest-value test file in Phase 5: every other test
either can't run without PostgreSQL, or is testing wiring around these
functions.
"""

from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt as jose_jwt

from src.core.config import Settings
from src.core.security import (
    MAX_PASSWORD_BYTES,
    TokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(secret_key="test-secret-key-not-for-production", jwt_algorithm="HS256")


# ---------- password hashing ----------


def test_hash_password_never_returns_the_plaintext() -> None:
    hashed = hash_password("correct horse battery staple")
    assert "correct horse battery staple" not in hashed


def test_hash_password_is_salted_so_two_hashes_of_the_same_password_differ() -> None:
    h1 = hash_password("same-password")
    h2 = hash_password("same-password")
    assert h1 != h2


def test_verify_password_accepts_correct_password() -> None:
    hashed = hash_password("correct-password")
    assert verify_password("correct-password", hashed) is True


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("correct-password")
    assert verify_password("wrong-password", hashed) is False


def test_verify_password_rejects_empty_string_against_real_hash() -> None:
    hashed = hash_password("correct-password")
    assert verify_password("", hashed) is False


def test_verify_password_does_not_crash_on_malformed_stored_hash() -> None:
    """A corrupted password_hash column must fail closed, not 500 the login route."""
    assert verify_password("anything", "not-a-real-bcrypt-hash") is False


def test_hash_password_rejects_passwords_over_72_bytes() -> None:
    # bcrypt silently truncates beyond 72 bytes; this must fail loudly instead.
    too_long = "a" * (MAX_PASSWORD_BYTES + 1)
    with pytest.raises(ValueError, match="72 bytes"):
        hash_password(too_long)


def test_hash_password_accepts_exactly_72_bytes() -> None:
    exactly_max = "a" * MAX_PASSWORD_BYTES
    hashed = hash_password(exactly_max)
    assert verify_password(exactly_max, hashed) is True


def test_hash_password_byte_length_not_character_length() -> None:
    """A multi-byte UTF-8 password can exceed 72 bytes well under 72 characters."""
    # "é" (e-acute) is 2 bytes in UTF-8.
    too_long_in_bytes = "é" * 40  # 40 chars, 80 bytes
    with pytest.raises(ValueError, match="72 bytes"):
        hash_password(too_long_in_bytes)


# ---------- access tokens ----------


def test_create_and_decode_access_token_round_trips_the_user_id(settings: Settings) -> None:
    token, expires_in = create_access_token(user_id="user-123", settings=settings)
    assert expires_in == settings.jwt_access_token_expire_minutes * 60
    assert decode_access_token(token, settings=settings) == "user-123"


def test_decode_access_token_rejects_tampered_signature(settings: Settings) -> None:
    token, _ = create_access_token(user_id="user-123", settings=settings)
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-4]}zzzz"
    with pytest.raises(TokenError):
        decode_access_token(tampered, settings=settings)


def test_decode_access_token_rejects_wrong_secret(settings: Settings) -> None:
    token, _ = create_access_token(user_id="user-123", settings=settings)
    wrong_settings = Settings(secret_key="a-completely-different-secret", jwt_algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(token, settings=wrong_settings)


def test_decode_access_token_rejects_expired_token(settings: Settings) -> None:
    now = datetime.now(UTC)
    expired_payload = {
        "sub": "user-123",
        "type": "access",
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
    }
    expired_token = jose_jwt.encode(
        expired_payload, settings.secret_key, algorithm=settings.jwt_algorithm
    )
    with pytest.raises(TokenError):
        decode_access_token(expired_token, settings=settings)


def test_decode_access_token_rejects_wrong_type_claim(settings: Settings) -> None:
    """Defense in depth: refresh tokens aren't JWTs in this design, but if
    something ever crafted a JWT with type='refresh', it must not be usable
    as an access token."""
    now = datetime.now(UTC)
    wrong_type_payload = {
        "sub": "user-123",
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(minutes=30),
    }
    token = jose_jwt.encode(
        wrong_type_payload, settings.secret_key, algorithm=settings.jwt_algorithm
    )
    with pytest.raises(TokenError):
        decode_access_token(token, settings=settings)


def test_decode_access_token_rejects_missing_subject(settings: Settings) -> None:
    now = datetime.now(UTC)
    payload = {"type": "access", "iat": now, "exp": now + timedelta(minutes=30)}
    token = jose_jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(TokenError):
        decode_access_token(token, settings=settings)


def test_decode_access_token_rejects_garbage_string(settings: Settings) -> None:
    with pytest.raises(TokenError):
        decode_access_token("not.a.jwt", settings=settings)


def test_access_token_does_not_contain_the_word_password(settings: Settings) -> None:
    """Sanity check against ever accidentally embedding sensitive data in the token."""
    token, _ = create_access_token(user_id="user-123", settings=settings)
    assert "password" not in token.lower()


# ---------- refresh tokens ----------


def test_generate_refresh_token_produces_unique_high_entropy_values() -> None:
    tokens = {generate_refresh_token() for _ in range(20)}
    assert len(tokens) == 20  # no collisions
    assert all(len(t) >= 32 for t in tokens)


def test_hash_refresh_token_is_deterministic() -> None:
    token = generate_refresh_token()
    assert hash_refresh_token(token) == hash_refresh_token(token)


def test_hash_refresh_token_differs_for_different_tokens() -> None:
    a, b = generate_refresh_token(), generate_refresh_token()
    assert hash_refresh_token(a) != hash_refresh_token(b)


def test_hash_refresh_token_does_not_contain_the_raw_token() -> None:
    token = generate_refresh_token()
    assert token not in hash_refresh_token(token)
