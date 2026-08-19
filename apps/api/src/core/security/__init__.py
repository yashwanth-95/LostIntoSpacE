"""Password hashing and JWT access-token utilities.

Password hashing uses `bcrypt` directly, NOT `passlib[bcrypt]` as originally
listed in ARCHITECTURE.md's tech stack table. passlib (last released 2020,
unmaintained) probes `bcrypt.__about__` to detect the backend version; that
module was removed in bcrypt 4.1+. Verified directly in this environment
(bcrypt 5.0.0 installed via the documented dependency): passlib raises
`AttributeError: module 'bcrypt' has no attribute '__about__'` on first hash
call. This is a real, current break, not a hypothetical one - see
DECISION_LOG #30. JWT still uses python-jose[cryptography], per
ARCHITECTURE.md; only the password-hashing half of that line changed.

Refresh tokens are NOT JWTs. They are opaque random strings (DECISION_LOG #16:
only refresh tokens are persisted, so their validity is decided by the
database row, not by anything encoded in the token itself). Making them JWTs
would add a self-describing payload that still has to be ignored in favour of
the DB check - purely redundant complexity.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from src.core.config import Settings

ACCESS_TOKEN_TYPE = "access"

# bcrypt silently truncates input beyond 72 BYTES (not characters - a
# multi-byte UTF-8 password can exceed this well under 72 characters).
# Enforced explicitly so a too-long password fails with a clear error at the
# call site instead of a cryptic ValueError surfacing from inside bcrypt, or
# (with some bindings) a silent truncation that hashes less password than the
# user thinks they set.
MAX_PASSWORD_BYTES = 72


class TokenError(Exception):
    """Any invalid/expired/malformed/wrong-type access token.

    Kept distinct from `jose.JWTError` so callers (auth/dependencies.py) don't
    need to import jose just to catch token failures.
    """


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password exceeds {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed hash in storage (should never happen if only
        # hash_password() ever wrote it) - treat as "does not match" rather
        # than crashing the login flow over corrupted data.
        return False


def create_access_token(*, user_id: str, settings: Settings) -> tuple[str, int]:
    """Returns (token, expires_in_seconds)."""
    now = datetime.now(UTC)
    expires_in = settings.jwt_access_token_expire_minutes * 60
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str, *, settings: Settings) -> str:
    """Returns the user id (the `sub` claim). Raises TokenError on any problem:
    bad signature, expiry, malformed token, or wrong `type` claim."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise TokenError("Invalid or expired access token") from exc

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise TokenError("Wrong token type")

    sub = payload.get("sub")
    if not sub:
        raise TokenError("Token missing subject")
    return str(sub)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits of randomness


def hash_refresh_token(token: str) -> str:
    # Plain SHA-256, not HMAC, and not bcrypt: the token already carries 256
    # bits of cryptographic randomness, so - unlike a password - there is no
    # offline-guessing attack for a secret key or slow hash to defend against.
    # SHA-256's preimage resistance is what matters: a leaked token_hash
    # cannot be reversed to recover the token that produced it.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
