"""Shared request/response pieces used across every domain router.

Pagination lives here rather than being re-declared per module so that
`meta` looks identical on every list endpoint - docs/api/API.md publishes one
envelope shape (`{page, per_page, total}`), and P1 should only have to model
it once.
"""

from typing import Annotated, Any, Generic, Literal, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

DataT = TypeVar("DataT")


class PaginationParams(BaseModel):
    """Page/per_page, matching the `meta` block in docs/api/API.md.

    Bounded by MAX_PAGE_SIZE so a client cannot ask for the whole table in one
    request - FastAPI rejects an out-of-range value as 422 before any query runs.
    """

    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def limit(self) -> int:
        return self.per_page


def pagination_params(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> PaginationParams:
    """FastAPI dependency form, so routes can declare `Depends(pagination_params)`
    and get validated query params rather than parsing them by hand."""
    return PaginationParams(page=page, per_page=per_page)


def pagination_meta(pagination: PaginationParams, total: int) -> dict[str, Any]:
    return {"page": pagination.page, "per_page": pagination.per_page, "total": total}


# ---------------------------------------------------------------------------
# Response envelopes as TYPES, not just dict builders.
#
# `core.envelope` builds the dicts at runtime; these models describe the same
# shape to OpenAPI. Without them every response is documented as an untyped
# `object`, so a client generated from the schema gets `any` for every payload
# and the OpenAPI file does not actually describe the contract it's meant to
# freeze. Declared here rather than per-router so the envelope stays identical
# across all 50+ operations.
# ---------------------------------------------------------------------------


class PaginationMeta(BaseModel):
    """The `meta` block published in docs/api/API.md."""

    page: int
    per_page: int
    total: int


class SuccessResponse(BaseModel, Generic[DataT]):
    """`{"status": "success", "data": <T>}` - single-resource responses."""

    status: Literal["success"] = "success"
    data: DataT


class PaginatedResponse(BaseModel, Generic[DataT]):
    """`{"status": "success", "data": [<T>], "meta": {...}}` - list responses."""

    status: Literal["success"] = "success"
    data: list[DataT]
    meta: PaginationMeta


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[Any] | None = None


class ErrorResponse(BaseModel):
    """`{"status": "error", "error": {...}}` - every failure, without exception.

    Registered as the documented response for 401/403/404/409/422 so clients
    can model one error shape instead of guessing per endpoint.
    """

    status: Literal["error"] = "error"
    error: ErrorDetail


# Reusable OpenAPI `responses=` blocks. Applied per-router so the generated
# schema shows what a client should actually expect on failure.
AUTH_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing, invalid, or expired token"},
}
OWNED_RESOURCE_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing, invalid, or expired token"},
    404: {
        "model": ErrorResponse,
        "description": (
            "Not found, or owned by another user. These are deliberately "
            "indistinguishable so resource ids cannot be probed."
        ),
    },
}
PUBLIC_RESOURCE_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not found"},
}


class HealthStatus(BaseModel):
    """`GET /health` payload - liveness only, never touches the database."""

    state: Literal["ok"] = "ok"
    service: str
    version: str


class ReadinessStatus(BaseModel):
    """`GET /health/ready` payload - 200 only when PostgreSQL is reachable."""

    state: Literal["ready"] = "ready"
    database: Literal["reachable"] = "reachable"
