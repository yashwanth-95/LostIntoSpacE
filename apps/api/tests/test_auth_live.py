"""Full HTTP-level auth integration tests against a real PostgreSQL database.

STATUS: PENDING LIVE VERIFICATION. Every test in this file is gated by
`requires_db` and SKIPS when `TEST_DATABASE_URL` is unset - which it is on
this machine, since no PostgreSQL server is installed here (see
docs/backend/DATABASE_SETUP.md). These tests are written and believed
correct, but have NOT been executed against a real database. Do not report
this file's coverage as verified until it has actually run green.

To run for real:
    createdb lostintospace_test
    export TEST_DATABASE_URL="postgresql+asyncpg://user:pw@localhost:5432/lostintospace_test"
    cd database && alembic upgrade head   # against the *_test URL
    cd apps/api && python -m pytest tests/test_auth_live.py -v
"""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import requires_db


def _register(client: TestClient, **overrides) -> dict:
    unique = uuid.uuid4().hex[:8]
    body = {
        "email": f"user-{unique}@example.com",
        "username": f"user{unique}",
        "password": "correct-horse-battery",
        **overrides,
    }
    r = client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 201, r.text
    return r.json()["data"]


@requires_db
class TestRegistration:
    def test_register_returns_tokens_and_user(self, live_client: TestClient) -> None:
        data = _register(live_client)
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0
        assert data["user"]["email"]

    def test_register_never_returns_password_hash(self, live_client: TestClient) -> None:
        data = _register(live_client)
        assert "password_hash" not in data["user"]
        assert "password" not in data["user"]

    def test_register_duplicate_email_returns_409(self, live_client: TestClient) -> None:
        first = _register(live_client)
        r = live_client.post(
            "/api/v1/auth/register",
            json={
                "email": first["user"]["email"],
                "username": "differentusername",
                "password": "another-password",
            },
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

    def test_register_duplicate_username_returns_409(self, live_client: TestClient) -> None:
        first = _register(live_client)
        r = live_client.post(
            "/api/v1/auth/register",
            json={
                "email": "totally-different@example.com",
                "username": first["user"]["username"],
                "password": "another-password",
            },
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "USERNAME_ALREADY_EXISTS"


@requires_db
class TestLogin:
    def test_login_succeeds_with_correct_credentials(self, live_client: TestClient) -> None:
        registered = _register(live_client, password="my-real-password")
        r = live_client.post(
            "/api/v1/auth/login",
            json={"email": registered["user"]["email"], "password": "my-real-password"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["access_token"]

    def test_login_fails_with_wrong_password(self, live_client: TestClient) -> None:
        registered = _register(live_client, password="my-real-password")
        r = live_client.post(
            "/api/v1/auth/login",
            json={"email": registered["user"]["email"], "password": "wrong-password"},
        )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"

    def test_login_fails_for_nonexistent_user(self, live_client: TestClient) -> None:
        r = live_client.post(
            "/api/v1/auth/login",
            json={"email": "nobody-registered@example.com", "password": "whatever"},
        )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


@requires_db
class TestMe:
    def test_me_returns_the_authenticated_user(self, live_client: TestClient) -> None:
        registered = _register(live_client)
        r = live_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {registered['access_token']}"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["email"] == registered["user"]["email"]

    def test_me_never_returns_password_hash(self, live_client: TestClient) -> None:
        registered = _register(live_client)
        r = live_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {registered['access_token']}"},
        )
        assert "password_hash" not in r.json()["data"]


@requires_db
class TestRefreshRotation:
    def test_refresh_returns_new_tokens(self, live_client: TestClient) -> None:
        registered = _register(live_client)
        r = live_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": registered["refresh_token"]}
        )
        assert r.status_code == 200
        new_data = r.json()["data"]
        assert new_data["refresh_token"] != registered["refresh_token"]
        assert new_data["access_token"] != registered["access_token"]

    def test_rotated_away_token_cannot_be_reused(self, live_client: TestClient) -> None:
        """The core rotation guarantee: once a refresh token has been
        exchanged, presenting the SAME raw token again must fail."""
        registered = _register(live_client)
        old_token = registered["refresh_token"]

        first = live_client.post("/api/v1/auth/refresh", json={"refresh_token": old_token})
        assert first.status_code == 200

        second = live_client.post("/api/v1/auth/refresh", json={"refresh_token": old_token})
        assert second.status_code == 401
        assert second.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"

    def test_reuse_locks_out_the_rotated_replacement_too(self, live_client: TestClient) -> None:
        """Reuse detection must revoke the ENTIRE chain, not just the reused
        token - the newest (legitimate) token must also stop working."""
        registered = _register(live_client)
        old_token = registered["refresh_token"]

        first = live_client.post("/api/v1/auth/refresh", json={"refresh_token": old_token})
        new_token = first.json()["data"]["refresh_token"]

        # Replay the old (already-rotated) token - triggers the lockout.
        live_client.post("/api/v1/auth/refresh", json={"refresh_token": old_token})

        # The legitimately-issued new_token must now ALSO be rejected.
        r = live_client.post("/api/v1/auth/refresh", json={"refresh_token": new_token})
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"

    def test_refresh_with_garbage_token_returns_401(self, live_client: TestClient) -> None:
        r = live_client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


@requires_db
class TestLogout:
    def test_logout_revokes_the_refresh_token(self, live_client: TestClient) -> None:
        registered = _register(live_client)
        r = live_client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": registered["refresh_token"]},
            headers={"Authorization": f"Bearer {registered['access_token']}"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["revoked"] is True

        # The revoked token must no longer work for refresh.
        r2 = live_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": registered["refresh_token"]}
        )
        assert r2.status_code == 401

    def test_logout_is_idempotent(self, live_client: TestClient) -> None:
        registered = _register(live_client)
        headers = {"Authorization": f"Bearer {registered['access_token']}"}
        body = {"refresh_token": registered["refresh_token"]}

        first = live_client.post("/api/v1/auth/logout", json=body, headers=headers)
        assert first.status_code == 200

        second = live_client.post("/api/v1/auth/logout", json=body, headers=headers)
        assert second.status_code == 200  # not an error to log out twice

    def test_logout_requires_authentication(self, live_client: TestClient) -> None:
        r = live_client.post("/api/v1/auth/logout", json={"refresh_token": "whatever"})
        assert r.status_code == 401

    def test_cannot_logout_another_users_refresh_token(self, live_client: TestClient) -> None:
        victim = _register(live_client)
        attacker = _register(live_client)

        r = live_client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": victim["refresh_token"]},
            headers={"Authorization": f"Bearer {attacker['access_token']}"},
        )
        assert r.status_code == 404  # ownership rule: 404, not 403 or 200


@requires_db
class TestFullFlow:
    def test_register_login_me_refresh_logout(self, live_client: TestClient) -> None:
        """The whole lifecycle end to end, matching the acceptance criteria
        list: registration -> login -> protected route -> rotation -> logout
        -> the logged-out token is dead."""
        registered = _register(live_client, password="the-real-password")
        email = registered["user"]["email"]

        login = live_client.post(
            "/api/v1/auth/login", json={"email": email, "password": "the-real-password"}
        )
        assert login.status_code == 200
        tokens = login.json()["data"]

        me = live_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert me.status_code == 200
        assert me.json()["data"]["email"] == email

        refreshed = live_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refreshed.status_code == 200
        new_tokens = refreshed.json()["data"]

        logout = live_client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": new_tokens["refresh_token"]},
            headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
        )
        assert logout.status_code == 200

        dead = live_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]}
        )
        assert dead.status_code == 401
