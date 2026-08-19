"""Contract-freeze tests over the generated OpenAPI schema.

These exist because the OpenAPI file IS the artifact P1/P3/P4 build against.
A route that drifts from the published contract - loses its auth marking,
returns an undocumented shape, or moves off /api/v1 - breaks another team
silently, and only a schema-level assertion catches that.

None of these need a database: the schema is generated from the app object.
"""

import pytest

from src.main import app

SPEC = app.openapi()
PATHS = SPEC["paths"]

# Public per docs/api/API.md's Auth column, plus health infrastructure.
# `auth/refresh` is public in the Bearer sense: it authenticates with a refresh
# token in the body, which is not a JWT the Bearer scheme could validate.
EXPECTED_PUBLIC = {
    ("get", "/api/v1/health"),
    ("get", "/api/v1/health/ready"),
    ("post", "/api/v1/auth/register"),
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/refresh"),
    ("get", "/api/v1/lessons"),
    ("get", "/api/v1/lessons/categories"),
    ("get", "/api/v1/lessons/{identifier}"),
    ("get", "/api/v1/space-objects"),
    ("get", "/api/v1/space-objects/categories"),
    ("get", "/api/v1/space-objects/{object_id}"),
}


def all_operations():
    for path, ops in PATHS.items():
        for method, op in ops.items():
            yield method, path, op


# ---------- versioning ----------


def test_every_route_is_under_api_v1() -> None:
    for path in PATHS:
        assert path.startswith("/api/v1/"), f"{path} escapes the versioned prefix"


# ---------- authentication ----------


def test_exactly_the_expected_endpoints_are_public() -> None:
    """The security-critical assertion: a protected route silently losing its
    auth dependency shows up here as a new public endpoint."""
    actual_public = {
        (method, path) for method, path, op in all_operations() if "security" not in op
    }
    assert actual_public == EXPECTED_PUBLIC, (
        f"unexpectedly public: {sorted(actual_public - EXPECTED_PUBLIC)}; "
        f"unexpectedly protected: {sorted(EXPECTED_PUBLIC - actual_public)}"
    )


def test_protected_operations_use_bearer_scheme() -> None:
    for method, path, op in all_operations():
        if (method, path) in EXPECTED_PUBLIC:
            continue
        assert op["security"] == [{"HTTPBearer": []}], f"{method.upper()} {path}"


def test_bearer_security_scheme_is_declared() -> None:
    schemes = SPEC["components"]["securitySchemes"]
    assert schemes["HTTPBearer"] == {"type": "http", "scheme": "bearer"}


# ---------- response contract ----------


def test_no_operation_returns_an_untyped_object() -> None:
    """Without this, responses document as `{}` and a generated client gets
    `any` for every payload - the schema stops being a contract."""
    untyped = []
    for method, path, op in all_operations():
        for code, response in op.get("responses", {}).items():
            if not code.startswith("2"):
                continue
            content = response.get("content")
            if content is None:
                continue  # 204 No Content is legitimately bodyless
            schema = content.get("application/json", {}).get("schema", {})
            if schema.get("type") == "object" and "additionalProperties" in schema:
                untyped.append(f"{method.upper()} {path}")
    assert not untyped, f"untyped 2xx responses: {untyped}"


def test_success_envelopes_declare_status_and_data() -> None:
    """Every 2xx body is `{status, data}` (+ `meta` when paginated), matching
    docs/api/API.md's Standard Response Envelope."""
    schemas = SPEC["components"]["schemas"]
    envelopes = [n for n in schemas if n.startswith(("SuccessResponse", "PaginatedResponse"))]
    assert envelopes, "no envelope schemas generated"
    for name in envelopes:
        props = schemas[name]["properties"]
        assert "status" in props and "data" in props, name
        if name.startswith("PaginatedResponse"):
            assert "meta" in props, f"{name} is paginated but has no meta"


def test_paginated_meta_matches_documented_shape() -> None:
    meta = SPEC["components"]["schemas"]["PaginationMeta"]["properties"]
    assert set(meta) == {"page", "per_page", "total"}


def test_error_envelope_shape_is_documented() -> None:
    error = SPEC["components"]["schemas"]["ErrorResponse"]["properties"]
    assert set(error) == {"status", "error"}
    detail = SPEC["components"]["schemas"]["ErrorDetail"]["properties"]
    assert {"code", "message"} <= set(detail)


def test_protected_operations_document_401() -> None:
    """P1 must be able to see, from the schema alone, that a call can 401."""
    missing = [
        f"{method.upper()} {path}"
        for method, path, op in all_operations()
        if (method, path) not in EXPECTED_PUBLIC and "401" not in op.get("responses", {})
    ]
    assert not missing, f"protected but no documented 401: {missing}"


def test_owned_resource_operations_document_404() -> None:
    """The 404-not-403 ownership rule must be visible in the contract, not
    just in the code."""
    owned_markers = (
        "{project_id}",
        "{mission_id}",
        "{vehicle_id}",
        "{component_id}",
        "{conversation_id}",
        "{lesson_id}",
    )
    missing = []
    for method, path, op in all_operations():
        if (method, path) in EXPECTED_PUBLIC:
            continue
        if any(marker in path for marker in owned_markers):
            if "404" not in op.get("responses", {}):
                missing.append(f"{method.upper()} {path}")
    assert not missing, f"owned-resource ops without documented 404: {missing}"


# ---------- documented contract paths exist ----------

# Paths docs/api/API.md publishes that P1/P3 build against. Deliberately does
# NOT include simulation/telemetry/stages/rkt/reports/search - those are
# blocked or deferred and must stay absent (see test below).
CONTRACT_PATHS = [
    ("post", "/api/v1/auth/register"),
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/logout"),
    ("post", "/api/v1/auth/refresh"),
    ("get", "/api/v1/auth/me"),
    ("get", "/api/v1/projects"),
    ("post", "/api/v1/projects"),
    ("get", "/api/v1/projects/{project_id}"),
    ("patch", "/api/v1/projects/{project_id}"),
    ("delete", "/api/v1/projects/{project_id}"),
    ("get", "/api/v1/projects/{project_id}/missions"),
    ("post", "/api/v1/projects/{project_id}/missions"),
    ("get", "/api/v1/missions/{mission_id}"),
    ("patch", "/api/v1/missions/{mission_id}"),
    ("get", "/api/v1/missions/{mission_id}/vehicle"),
    ("post", "/api/v1/missions/{mission_id}/vehicle"),
    ("patch", "/api/v1/vehicles/{vehicle_id}"),
    ("get", "/api/v1/vehicles/{vehicle_id}/components"),
    ("post", "/api/v1/vehicles/{vehicle_id}/components"),
    ("patch", "/api/v1/components/{component_id}"),
    ("delete", "/api/v1/components/{component_id}"),
    ("get", "/api/v1/space-objects"),
    ("get", "/api/v1/space-objects/{object_id}"),
    ("get", "/api/v1/space-objects/categories"),
    ("get", "/api/v1/lessons"),
    ("get", "/api/v1/lessons/categories"),
    ("post", "/api/v1/learning/progress"),
]


@pytest.mark.parametrize(("method", "path"), CONTRACT_PATHS)
def test_documented_contract_path_is_implemented(method: str, path: str) -> None:
    assert path in PATHS, f"{path} is published in API.md but not implemented"
    assert method in PATHS[path], f"{method.upper()} {path} is published but not implemented"


# ---------- blocked/deferred features must stay absent ----------

MUST_NOT_EXIST = [
    "/api/v1/vehicles/{vehicle_id}/stages",  # vehicle_stages blocked on P3
    "/api/v1/stages/{stage_id}",
    "/api/v1/simulations/run",  # P3 owns; telemetry contract open
    "/api/v1/simulations/{simulation_id}/telemetry",
    "/api/v1/rockets",  # rejected - vehicle is canonical
    "/api/v1/mission-events",  # rejected - simulation_events canonical
    "/api/v1/favorites",  # deferred (SD-3)
    "/api/v1/quizzes",  # deferred (SD-3)
    "/api/v1/courses",  # deferred (SD-3)
    "/api/v1/learning-paths",  # deferred (SD-3)
]


@pytest.mark.parametrize("path", MUST_NOT_EXIST)
def test_blocked_or_deferred_feature_is_not_exposed(path: str) -> None:
    """Guards the finalized decisions. If one of these ever appears, either a
    P3 blocker was resolved (and the contract docs need updating) or a
    deferred entity crept back in."""
    assert path not in PATHS, f"{path} exists but should be blocked/deferred"


def test_no_rocket_terminology_in_any_path() -> None:
    """DECISION_LOG #20: `vehicle` is canonical in the API; only the UI says
    'rocket'."""
    offenders = [p for p in PATHS if "rocket" in p.lower()]
    assert not offenders, f"paths using rejected 'rocket' terminology: {offenders}"
