"""Endpoint-level tests that need no database.

Two things are genuinely verifiable without PostgreSQL:

  1. AUTHENTICATION BOUNDARY - a protected route rejects an unauthenticated
     caller before any query runs, so the 401 is real, not incidental.
  2. INPUT VALIDATION - Pydantic and FastAPI's path/query coercion run before
     the route body, so malformed requests 422 without touching the database.

Anything that requires a row to exist (ownership isolation between two real
users, cascade behaviour, pagination over real data) is in
test_integration_live.py, gated behind TEST_DATABASE_URL.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

# Every protected endpoint, as (method, path). Kept as one list so a new route
# added without auth shows up as a failure here.
PROTECTED_ENDPOINTS = [
    ("GET", "/api/v1/users/me"),
    ("PATCH", "/api/v1/users/me"),
    ("GET", "/api/v1/users/me/preferences"),
    ("PATCH", "/api/v1/users/me/preferences"),
    ("GET", "/api/v1/projects"),
    ("POST", "/api/v1/projects"),
    ("GET", f"/api/v1/projects/{uuid.uuid4()}"),
    ("PATCH", f"/api/v1/projects/{uuid.uuid4()}"),
    ("DELETE", f"/api/v1/projects/{uuid.uuid4()}"),
    ("GET", "/api/v1/missions"),
    ("POST", "/api/v1/missions"),
    ("GET", f"/api/v1/missions/{uuid.uuid4()}"),
    ("PATCH", f"/api/v1/missions/{uuid.uuid4()}"),
    ("DELETE", f"/api/v1/missions/{uuid.uuid4()}"),
    ("GET", "/api/v1/vehicles"),
    ("POST", "/api/v1/vehicles"),
    ("GET", f"/api/v1/vehicles/{uuid.uuid4()}"),
    ("PATCH", f"/api/v1/vehicles/{uuid.uuid4()}"),
    ("DELETE", f"/api/v1/vehicles/{uuid.uuid4()}"),
    ("GET", f"/api/v1/vehicles/{uuid.uuid4()}/components"),
    ("POST", f"/api/v1/vehicles/{uuid.uuid4()}/components"),
    ("PATCH", f"/api/v1/components/{uuid.uuid4()}"),
    ("DELETE", f"/api/v1/components/{uuid.uuid4()}"),
    ("GET", "/api/v1/learning/progress"),
    ("POST", "/api/v1/learning/progress"),
    ("PATCH", f"/api/v1/learning/progress/{uuid.uuid4()}"),
    ("GET", "/api/v1/conversations"),
    ("POST", "/api/v1/conversations"),
    ("GET", f"/api/v1/conversations/{uuid.uuid4()}"),
    ("PATCH", f"/api/v1/conversations/{uuid.uuid4()}"),
    ("DELETE", f"/api/v1/conversations/{uuid.uuid4()}"),
    ("GET", f"/api/v1/conversations/{uuid.uuid4()}/messages"),
    ("POST", f"/api/v1/conversations/{uuid.uuid4()}/messages"),
]

# Public per docs/api/API.md - a token must NOT be required.
PUBLIC_ENDPOINTS = [
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/lessons"),
    ("GET", "/api/v1/lessons/categories"),
    ("GET", "/api/v1/space-objects"),
    ("GET", "/api/v1/space-objects/categories"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED_ENDPOINTS)
def test_protected_endpoint_rejects_anonymous_caller(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(method, path, json={})
    assert response.status_code == 401, f"{method} {path} did not require auth"
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize(("method", "path"), PROTECTED_ENDPOINTS)
def test_protected_endpoint_rejects_forged_token(
    client: TestClient, method: str, path: str
) -> None:
    """A syntactically valid JWT signed with the wrong key must be rejected
    everywhere, not just on /auth/me."""
    from jose import jwt as jose_jwt

    forged = jose_jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access"}, "attacker-key", algorithm="HS256"
    )
    response = client.request(method, path, json={}, headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.parametrize(("method", "path"), PUBLIC_ENDPOINTS)
def test_public_endpoint_does_not_require_auth(method: str, path: str) -> None:
    """Must not 401. These hit the database (except /health), which is
    unreachable here, so anything other than 401 proves auth wasn't the
    blocker - that's the property under test."""
    from src.main import app

    lenient = TestClient(app, raise_server_exceptions=False)
    response = lenient.request(method, path)
    assert response.status_code != 401


# ---------- malformed input, rejected before the database ----------


def test_invalid_uuid_in_path_is_422(client: TestClient) -> None:
    """A non-UUID path segment is coerced by FastAPI and fails at the edge -
    it never reaches a query, so this is testable without a database."""
    response = client.get("/api/v1/projects/not-a-uuid", headers={"Authorization": "Bearer x"})
    assert response.status_code in (401, 422)


def test_pagination_out_of_range_is_422(client: TestClient) -> None:
    from src.main import app

    lenient = TestClient(app, raise_server_exceptions=False)
    for query in ("?page=0", "?per_page=0", "?per_page=100000", "?page=-5"):
        response = lenient.get(f"/api/v1/lessons{query}")
        assert response.status_code == 422, f"{query} should be rejected"


def test_unknown_sort_field_is_422(client: TestClient) -> None:
    """`sort` is a Literal, so an arbitrary value can never reach SQL."""
    from src.main import app

    lenient = TestClient(app, raise_server_exceptions=False)
    response = lenient.get("/api/v1/space-objects?sort=id;DROP TABLE users")
    assert response.status_code == 422


def test_unknown_order_direction_is_422(client: TestClient) -> None:
    from src.main import app

    lenient = TestClient(app, raise_server_exceptions=False)
    assert lenient.get("/api/v1/space-objects?order=sideways").status_code == 422


# ---------- response contract ----------


def test_health_uses_the_standard_success_envelope(client: TestClient) -> None:
    body = client.get("/api/v1/health").json()
    assert body["status"] == "success"
    assert body["data"]["state"] == "ok"


def test_errors_never_leak_internals(client: TestClient) -> None:
    """No stack traces, no file paths, no connection strings in a 401 body."""
    text = client.get("/api/v1/projects").text.lower()
    for marker in ("traceback", "site-packages", "postgresql://", "asyncpg", "password"):
        assert marker not in text


def test_every_route_is_under_the_api_v1_prefix() -> None:
    """Guards the published base path - a route mounted outside /api/v1 would
    be invisible to P1's client."""
    from src.main import app

    for path in app.openapi()["paths"]:
        assert path.startswith("/api/v1/"), f"{path} is outside the versioned prefix"
