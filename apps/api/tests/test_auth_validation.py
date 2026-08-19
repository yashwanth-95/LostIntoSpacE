"""Input-validation and protected-route tests that never touch a database.

Two paths make this possible with no PostgreSQL running:
  - Pydantic validates the request body BEFORE the route function runs, so a
    malformed body never reaches a database query.
  - get_current_user raises before its `session` parameter is ever queried
    when there's no (or an invalid) token - see auth/dependencies.py's
    docstring for why entering the AsyncSession context is itself safe with
    no server running.
"""

from fastapi.testclient import TestClient

# ---------- registration: invalid input ----------


def test_register_rejects_invalid_email(client: TestClient) -> None:
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "username": "validuser", "password": "longenough123"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(e["loc"] == ["body", "email"] for e in body["error"]["details"])


def test_register_rejects_short_password(client: TestClient) -> None:
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "a@example.com", "username": "validuser", "password": "short"},
    )
    assert r.status_code == 422
    assert any(e["loc"] == ["body", "password"] for e in r.json()["error"]["details"])


def test_register_rejects_password_over_72_bytes(client: TestClient) -> None:
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "a@example.com", "username": "validuser", "password": "a" * 73},
    )
    assert r.status_code == 422
    assert any(e["loc"] == ["body", "password"] for e in r.json()["error"]["details"])


def test_register_rejects_short_username(client: TestClient) -> None:
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "a@example.com", "username": "ab", "password": "longenough123"},
    )
    assert r.status_code == 422
    assert any(e["loc"] == ["body", "username"] for e in r.json()["error"]["details"])


def test_register_rejects_username_with_invalid_characters(client: TestClient) -> None:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "a@example.com",
            "username": "not a valid username!",
            "password": "longenough123",
        },
    )
    assert r.status_code == 422
    assert any(e["loc"] == ["body", "username"] for e in r.json()["error"]["details"])


def test_register_rejects_missing_fields(client: TestClient) -> None:
    r = client.post("/api/v1/auth/register", json={"email": "a@example.com"})
    assert r.status_code == 422
    missing_fields = {tuple(e["loc"]) for e in r.json()["error"]["details"]}
    assert ("body", "username") in missing_fields
    assert ("body", "password") in missing_fields


def test_register_accepts_username_hyphen_and_underscore() -> None:
    """Confirms the charset validator isn't over-restrictive - this should
    pass validation and only fail later trying to reach the (unreachable, in
    this environment) database, never as a 422. Needs its own client with
    raise_server_exceptions=False: the default TestClient re-raises the
    connection error into the test process instead of returning a response,
    which is correct default behaviour for catching real bugs but means the
    default `client` fixture can't be used to observe "did this become a 500
    instead of a 422" here."""
    from src.main import app

    lenient_client = TestClient(app, raise_server_exceptions=False)
    r = lenient_client.post(
        "/api/v1/auth/register",
        json={"email": "a@example.com", "username": "valid_user-99", "password": "longenough123"},
    )
    assert r.status_code != 422


# ---------- login: invalid input ----------


def test_login_rejects_invalid_email(client: TestClient) -> None:
    r = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "whatever"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_login_rejects_missing_password(client: TestClient) -> None:
    r = client.post("/api/v1/auth/login", json={"email": "a@example.com"})
    assert r.status_code == 422


# ---------- refresh/logout: invalid input ----------


def test_refresh_rejects_empty_body(client: TestClient) -> None:
    r = client.post("/api/v1/auth/refresh", json={})
    assert r.status_code == 422


def test_refresh_rejects_empty_string_token(client: TestClient) -> None:
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": ""})
    assert r.status_code == 422


def test_logout_without_auth_header_is_401_not_422(client: TestClient) -> None:
    """Auth is checked before the body would even matter for this route."""
    r = client.post("/api/v1/auth/logout", json={"refresh_token": "whatever"})
    assert r.status_code == 401


# ---------- protected routes: get_current_user ----------


def test_me_without_authorization_header_is_401(client: TestClient) -> None:
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    body = r.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_me_with_malformed_bearer_token_is_401_not_500(client: TestClient) -> None:
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_TOKEN"


def test_me_with_empty_bearer_token_is_401(client: TestClient) -> None:
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer "})
    assert r.status_code == 401


def test_me_with_non_bearer_scheme_is_401(client: TestClient) -> None:
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert r.status_code == 401


def test_me_with_token_signed_by_a_different_secret_is_401(client: TestClient) -> None:
    """A token that is syntactically a valid JWT but signed with the wrong key
    must be rejected the same way a garbage string is - not crash, not 200."""
    from jose import jwt as jose_jwt

    forged = jose_jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000000", "type": "access"},
        "attacker-controlled-secret",
        algorithm="HS256",
    )
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_TOKEN"


# ---------- sensitive-data leakage ----------


def test_register_validation_error_never_echoes_the_password(client: TestClient) -> None:
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "username": "ab", "password": "my-secret-password-value"},
    )
    assert "my-secret-password-value" not in r.text


def test_401_responses_never_contain_a_stack_trace(client: TestClient) -> None:
    r = client.get("/api/v1/auth/me")
    text_lower = r.text.lower()
    for marker in ("traceback", "site-packages", "raise ", '.py"', "line "):
        assert marker not in text_lower


def test_unauthorized_error_body_shape_matches_the_standard_envelope(client: TestClient) -> None:
    r = client.get("/api/v1/auth/me")
    body = r.json()
    assert set(body.keys()) == {"status", "error"}
    assert set(body["error"].keys()) <= {"code", "message", "details"}
