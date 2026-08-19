"""Project request/response schemas.

Field mapping note: the ORM attribute is `project_metadata` because
`metadata` is reserved on SQLAlchemy's DeclarativeBase, but the COLUMN and the
JSON field are both `metadata` - `docs/backend/API_CONTRACT.md` publishes
`metadata`, so that is what crosses the wire. The alias keeps the Python-side
rename from leaking into P1's contract.

Notes on fields the Phase 7 brief lists that are NOT columns here:
  - mission relationship        -> `missions` are a child resource
                                   (`GET /projects/{pid}/missions`, per
                                   docs/api/API.md); a project response
                                   carries `mission_count`, not embedded rows.
  - vehicle / simulation refs   -> reachable through missions
                                   (project -> mission -> vehicle), never
                                   duplicated onto the project. A second path
                                   to the same answer eventually disagrees
                                   with the first (DATABASE_CONTRACT.md §3).
  - payload/config metadata,
    project notes               -> `metadata` JSONB. The finalized schema has
                                   exactly one flexible bag on `projects`;
                                   adding `notes`/`payload` columns would be a
                                   schema change the contract didn't approve.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Mirrors the CHECK constraint on projects.status (DATABASE_CONTRACT.md §6).
# Declared as a Literal so a bad value fails as a 422 at the edge rather than
# as an opaque IntegrityError 500 from the database. The DB CHECK remains the
# real guarantee; this is the friendly path.
ProjectStatus = Literal["draft", "active", "completed", "archived"]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: ProjectStatus = "draft"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    """PATCH - only supplied fields change.

    `user_id` is absent by design and rejected by extra="forbid": ownership is
    derived from the token, never from the body, so a project can never be
    reassigned to another user through this endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: ProjectStatus | None = None
    metadata: dict[str, Any] | None = None

    def changed_fields(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    user_id: UUID
    name: str
    description: str | None
    status: str
    # serialization_alias keeps the wire name `metadata` despite the ORM
    # attribute being `project_metadata`.
    metadata: dict[str, Any] = Field(validation_alias="project_metadata", default_factory=dict)
    created_at: datetime
    updated_at: datetime
