"""Request/response schemas for the auth endpoints.

`User`, `RegisterRequest`, `LoginRequest`, `AuthResponse` match the shapes
already published in docs/backend/API_CONTRACT.md. `RefreshRequest`,
`LogoutRequest`, and `LogoutResponse` are new - that document only scoped the
minimum surface needed before Phase 2 and didn't cover these two endpoints;
they follow the same token semantics already documented in docs/api/API.md's
"Token semantics" note (refresh token travels in the body, not a Bearer
header, since it isn't a JWT the Bearer scheme could parse).
"""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# Not specified in any existing contract - an app-level choice, documented
# here rather than left implicit. Revisit if product wants different rules.
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

# Mirrors core.security.MAX_PASSWORD_BYTES - kept independent (not imported)
# so a schema-only test suite doesn't need the security module's dependencies.
MAX_PASSWORD_BYTES = 72


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=200)

    @field_validator("username")
    @classmethod
    def _username_charset(cls, value: str) -> str:
        if not USERNAME_PATTERN.match(value):
            raise ValueError("username may only contain letters, digits, underscore, hyphen")
        return value

    @field_validator("password")
    @classmethod
    def _password_byte_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    display_name: str | None
    avatar_url: str | None
    role: str
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class LogoutResponse(BaseModel):
    revoked: bool
