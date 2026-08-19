"""User profile and preferences schemas.

SECURITY - the update schemas use `extra="forbid"` deliberately.

Pydantic's default is to silently DROP unknown fields. For an update endpoint
that is the dangerous default: a request containing `{"role": "admin"}` or
`{"is_active": true}` would return 200 and look to the caller as though it had
worked. `forbid` turns those into an explicit 422, so a privilege-escalation
attempt fails loudly instead of quietly. `password_hash` is covered by the
same rule.

Fields a user may change about themselves are therefore an ALLOW-LIST, not a
deny-list: anything not named here is rejected.
"""

import json
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.schemas.auth import USERNAME_PATTERN

# Bounds on the free-form preferences blob. Key *semantics* are P1's to define
# (see models/user.py); the backend's job is only to stop it becoming an
# unbounded document store.
MAX_PREFERENCE_KEYS = 64
MAX_PREFERENCES_BYTES = 16_384
MAX_PREFERENCE_KEY_LENGTH = 64
PREFERENCE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class UserProfileResponse(BaseModel):
    """What a user may see about themselves.

    Explicitly excludes `password_hash` (never leaves the database layer) and
    `is_active` (an account-state flag the user cannot act on). `role` IS shown
    - a user may know their own role, they just may not change it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    display_name: str | None
    avatar_url: str | None
    role: str
    created_at: datetime
    updated_at: datetime


class UserProfileUpdate(BaseModel):
    """Every field optional - PATCH semantics, only what's sent is changed.

    NOT updatable here, by omission (and enforced by extra="forbid"):
      role        - privilege escalation
      is_active   - account state, not a profile field
      password    - belongs behind a dedicated change-password flow that
                    re-verifies the current password; a profile PATCH is the
                    wrong place for it
      id, created_at, updated_at - server-owned
    """

    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=3, max_length=50)
    display_name: str | None = Field(default=None, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=2048)

    @field_validator("username")
    @classmethod
    def _username_charset(cls, value: str | None) -> str | None:
        if value is not None and not USERNAME_PATTERN.match(value):
            raise ValueError("username may only contain letters, digits, underscore, hyphen")
        return value

    def changed_fields(self) -> dict[str, Any]:
        """Only the keys actually present in the request body.

        `exclude_unset` matters: it distinguishes "field omitted" from "field
        explicitly set to null". Sending `{"display_name": null}` clears the
        display name; omitting it leaves the existing value alone.
        """
        return self.model_dump(exclude_unset=True)


class PreferencesResponse(BaseModel):
    preferences: dict[str, Any]


class PreferencesUpdate(BaseModel):
    """Shallow-merged into the stored object - see users/service.py.

    Validated for size and shape but not for meaning: the backend does not
    know or care what `theme` or `units` should contain, and hardcoding a key
    list here would mean a backend change every time P1 adds a toggle.
    """

    model_config = ConfigDict(extra="forbid")

    preferences: dict[str, Any]

    @field_validator("preferences")
    @classmethod
    def _bounded_and_flat(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > MAX_PREFERENCE_KEYS:
            raise ValueError(f"at most {MAX_PREFERENCE_KEYS} preference keys are allowed")

        for key, item in value.items():
            if len(key) > MAX_PREFERENCE_KEY_LENGTH:
                raise ValueError(f"preference key '{key[:20]}...' is too long")
            if not PREFERENCE_KEY_PATTERN.match(key):
                raise ValueError(
                    f"preference key '{key}' may only contain letters, digits, '_', '.', '-'"
                )
            # One level of nesting is plenty for UI settings. Rejecting deeper
            # structures keeps this from turning into an unbounded document
            # store that nothing validates.
            if isinstance(item, dict | list) and _depth(item) > 1:
                raise ValueError(f"preference '{key}' is nested too deeply (max 1 level)")

        # Guard total size after per-key checks, so an attacker can't get past
        # the key count with a few enormous values.
        if len(json.dumps(value).encode("utf-8")) > MAX_PREFERENCES_BYTES:
            raise ValueError(f"preferences must serialize to under {MAX_PREFERENCES_BYTES} bytes")
        return value


def _depth(value: Any) -> int:
    if isinstance(value, dict):
        return 1 + max((_depth(v) for v in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(v) for v in value), default=0)
    return 0
