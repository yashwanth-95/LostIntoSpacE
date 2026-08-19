"""Mission schemas.

A mission belongs to exactly one project and is never shared between them
(DATABASE_CONTRACT.md §2.4). `project_id` is required on create and absent
from update - reparenting a mission is not an operation any contract asks for,
and allowing it would let a caller move a mission into a project they own from
one they don't.

The three JSONB blobs (`target_orbit`, `launch_site`, `environment`) are
passed through verbatim: their shape varies by mission type and they are
consumed wholesale by P3's simulation engine, so the backend deliberately does
not model their interiors. Validating them here would fossilize P3's config
structure into P2's schema.

MISSION EVENTS ARE NOT HERE (DECISION_LOG #21). Events belong to a simulation
run - one mission has many runs, each with its own event timeline. There is no
`mission_events` and this schema does not invent one.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MissionStatus = Literal["planning", "ready", "simulated", "analyzed"]


class MissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    name: str = Field(min_length=1, max_length=200)
    objective: str | None = Field(default=None, max_length=10_000)
    target_orbit: dict[str, Any] | None = None
    launch_site: dict[str, Any] | None = None
    environment: dict[str, Any] | None = None
    status: MissionStatus = "planning"


class MissionCreateNested(BaseModel):
    """Body for `POST /projects/{project_id}/missions`.

    Identical to MissionCreate except `project_id` is absent: it comes from
    the URL path. Including it in the body too would create two sources of
    truth for the same value and an obvious mismatch case to handle.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    objective: str | None = Field(default=None, max_length=10_000)
    target_orbit: dict[str, Any] | None = None
    launch_site: dict[str, Any] | None = None
    environment: dict[str, Any] | None = None
    status: MissionStatus = "planning"


class MissionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    objective: str | None = Field(default=None, max_length=10_000)
    target_orbit: dict[str, Any] | None = None
    launch_site: dict[str, Any] | None = None
    environment: dict[str, Any] | None = None
    status: MissionStatus | None = None

    def changed_fields(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class MissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    objective: str | None
    target_orbit: dict[str, Any] | None
    launch_site: dict[str, Any] | None
    environment: dict[str, Any] | None
    status: str
    created_at: datetime
    updated_at: datetime
