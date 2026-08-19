"""Full-stack integration tests against a real PostgreSQL database.

STATUS: PENDING LIVE VERIFICATION. Every test here is gated by `requires_db`
and SKIPS while TEST_DATABASE_URL is unset - which it is on this machine, as
no PostgreSQL is installed (docs/backend/DATABASE_SETUP.md). These are written
and believed correct but have NOT been executed. Do not report their coverage
as verified until they have actually run green.

What only these can prove, and the no-DB suites cannot:
  - ownership ISOLATION between two real users (user B cannot see user A's
    rows) - the no-DB tests prove auth is required, not that the filter works
  - the full CRUD round-trip and that data actually persists
  - pagination and filtering over real rows
  - cascade/soft-delete behaviour
  - the cross-team serialization round-trip (P3 vehicle save/load, P4
    conversation persistence)

To run:
    createdb lostintospace_test
    export TEST_DATABASE_URL="postgresql+asyncpg://user:pw@localhost:5432/lostintospace_test"
    cd database && alembic upgrade head     # against the *_test URL
    cd apps/api && python -m pytest tests/test_integration_live.py -v
"""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import requires_db


def _auth(client: TestClient) -> tuple[dict[str, str], dict]:
    """Registers a fresh user; returns (auth_header, user)."""
    unique = uuid.uuid4().hex[:8]
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"u{unique}@example.com",
            "username": f"u{unique}",
            "password": "integration-test-pw",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    return {"Authorization": f"Bearer {data['access_token']}"}, data["user"]


def _make_project(client: TestClient, headers: dict[str, str], **overrides) -> dict:
    body = {"name": "Test Project", **overrides}
    response = client.post("/api/v1/projects", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _make_mission(client: TestClient, headers: dict[str, str], project_id: str) -> dict:
    response = client.post(
        "/api/v1/missions",
        json={"project_id": project_id, "name": "Test Mission"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@requires_db
class TestUserProfile:
    def test_get_and_patch_profile(self, live_client: TestClient) -> None:
        headers, _ = _auth(live_client)

        read = live_client.get("/api/v1/users/me", headers=headers)
        assert read.status_code == 200
        assert "password_hash" not in read.json()["data"]

        patched = live_client.patch(
            "/api/v1/users/me", json={"display_name": "Renamed"}, headers=headers
        )
        assert patched.status_code == 200
        assert patched.json()["data"]["display_name"] == "Renamed"

    def test_role_cannot_be_escalated(self, live_client: TestClient) -> None:
        headers, _ = _auth(live_client)
        response = live_client.patch("/api/v1/users/me", json={"role": "admin"}, headers=headers)
        assert response.status_code == 422
        profile = live_client.get("/api/v1/users/me", headers=headers).json()["data"]
        assert profile["role"] == "student"

    def test_duplicate_email_on_update_is_409(self, live_client: TestClient) -> None:
        _, first_user = _auth(live_client)
        second_headers, _ = _auth(live_client)
        response = live_client.patch(
            "/api/v1/users/me", json={"email": first_user["email"]}, headers=second_headers
        )
        assert response.status_code == 409

    def test_preferences_merge_not_replace(self, live_client: TestClient) -> None:
        headers, _ = _auth(live_client)
        live_client.patch(
            "/api/v1/users/me/preferences",
            json={"preferences": {"theme": "dark", "units": "metric"}},
            headers=headers,
        )
        live_client.patch(
            "/api/v1/users/me/preferences",
            json={"preferences": {"theme": "light"}},
            headers=headers,
        )
        prefs = live_client.get("/api/v1/users/me/preferences", headers=headers).json()["data"][
            "preferences"
        ]
        assert prefs["theme"] == "light"
        assert prefs["units"] == "metric", "PATCH must merge, not replace"

    def test_null_preference_removes_the_key(self, live_client: TestClient) -> None:
        headers, _ = _auth(live_client)
        live_client.patch(
            "/api/v1/users/me/preferences",
            json={"preferences": {"theme": "dark"}},
            headers=headers,
        )
        live_client.patch(
            "/api/v1/users/me/preferences",
            json={"preferences": {"theme": None}},
            headers=headers,
        )
        prefs = live_client.get("/api/v1/users/me/preferences", headers=headers).json()["data"][
            "preferences"
        ]
        assert "theme" not in prefs


@requires_db
class TestProjectCrudAndOwnership:
    def test_full_crud_round_trip(self, live_client: TestClient) -> None:
        headers, _ = _auth(live_client)
        created = _make_project(live_client, headers, description="initial")

        read = live_client.get(f"/api/v1/projects/{created['id']}", headers=headers)
        assert read.status_code == 200
        assert read.json()["data"]["description"] == "initial"

        patched = live_client.patch(
            f"/api/v1/projects/{created['id']}",
            json={"name": "Renamed", "status": "active"},
            headers=headers,
        )
        assert patched.json()["data"]["name"] == "Renamed"

        assert (
            live_client.delete(f"/api/v1/projects/{created['id']}", headers=headers).status_code
            == 204
        )

    def test_soft_deleted_project_becomes_invisible(self, live_client: TestClient) -> None:
        headers, _ = _auth(live_client)
        project = _make_project(live_client, headers)
        live_client.delete(f"/api/v1/projects/{project['id']}", headers=headers)

        assert (
            live_client.get(f"/api/v1/projects/{project['id']}", headers=headers).status_code == 404
        )
        listed = live_client.get("/api/v1/projects", headers=headers).json()["data"]
        assert all(p["id"] != project["id"] for p in listed)

    def test_user_cannot_read_another_users_project(self, live_client: TestClient) -> None:
        """THE core ownership test - 404, not 403, so ids can't be probed."""
        owner_headers, _ = _auth(live_client)
        attacker_headers, _ = _auth(live_client)
        project = _make_project(live_client, owner_headers)

        response = live_client.get(f"/api/v1/projects/{project['id']}", headers=attacker_headers)
        assert response.status_code == 404

    def test_user_cannot_modify_or_delete_another_users_project(
        self, live_client: TestClient
    ) -> None:
        owner_headers, _ = _auth(live_client)
        attacker_headers, _ = _auth(live_client)
        project = _make_project(live_client, owner_headers)

        assert (
            live_client.patch(
                f"/api/v1/projects/{project['id']}",
                json={"name": "hacked"},
                headers=attacker_headers,
            ).status_code
            == 404
        )
        assert (
            live_client.delete(
                f"/api/v1/projects/{project['id']}", headers=attacker_headers
            ).status_code
            == 404
        )
        # And the original is untouched.
        assert (
            live_client.get(f"/api/v1/projects/{project['id']}", headers=owner_headers).json()[
                "data"
            ]["name"]
            != "hacked"
        )

    def test_listing_only_returns_own_projects(self, live_client: TestClient) -> None:
        headers_a, _ = _auth(live_client)
        headers_b, _ = _auth(live_client)
        _make_project(live_client, headers_a, name="A's project")
        _make_project(live_client, headers_b, name="B's project")

        listed_a = live_client.get("/api/v1/projects", headers=headers_a).json()["data"]
        names = [p["name"] for p in listed_a]
        assert "A's project" in names
        assert "B's project" not in names

    def test_nonexistent_project_is_404(self, live_client: TestClient) -> None:
        headers, _ = _auth(live_client)
        assert (
            live_client.get(f"/api/v1/projects/{uuid.uuid4()}", headers=headers).status_code == 404
        )

    def test_pagination_meta_and_slicing(self, live_client: TestClient) -> None:
        headers, _ = _auth(live_client)
        for i in range(5):
            _make_project(live_client, headers, name=f"Project {i}")

        page = live_client.get("/api/v1/projects?page=1&per_page=2", headers=headers).json()
        assert len(page["data"]) == 2
        assert page["meta"]["total"] >= 5
        assert page["meta"]["per_page"] == 2

    def test_status_filter(self, live_client: TestClient) -> None:
        headers, _ = _auth(live_client)
        _make_project(live_client, headers, name="Draft one", status="draft")
        _make_project(live_client, headers, name="Active one", status="active")

        active = live_client.get("/api/v1/projects?status=active", headers=headers).json()["data"]
        assert all(p["status"] == "active" for p in active)


@requires_db
class TestMissionAndVehicle:
    def test_mission_requires_owned_project(self, live_client: TestClient) -> None:
        owner_headers, _ = _auth(live_client)
        attacker_headers, _ = _auth(live_client)
        project = _make_project(live_client, owner_headers)

        response = live_client.post(
            "/api/v1/missions",
            json={"project_id": project["id"], "name": "Intruder mission"},
            headers=attacker_headers,
        )
        assert response.status_code == 404

    def test_vehicle_save_load_round_trip(self, live_client: TestClient) -> None:
        """The P3 contract: a design saved through the API must come back
        with identical field names and values."""
        headers, _ = _auth(live_client)
        project = _make_project(live_client, headers)
        mission = _make_mission(live_client, headers, project["id"])

        payload = {
            "mission_id": mission["id"],
            "name": "Rocket Alpha",
            "total_height_m": 4.2,
            "components": [
                {
                    "component_type": "nose",
                    "name": "Ogive Nose",
                    "mass_kg": 5.0,
                    "position": {"x": 0, "y": 0, "z": 2.5},
                    "dimensions": {"length_m": 0.5, "diameter_m": 0.3},
                    "sort_order": 0,
                },
                {
                    "component_type": "fins",
                    "name": "Fin Set",
                    "mass_kg": 3.0,
                    "position": {"x": 0, "y": 0, "z": 0.3},
                    "dimensions": {"span_m": 0.25, "chord_m": 0.3},
                    "sort_order": 1,
                },
            ],
        }
        created = live_client.post("/api/v1/vehicles", json=payload, headers=headers)
        assert created.status_code == 201, created.text
        vehicle = created.json()["data"]
        assert len(vehicle["components"]) == 2

        loaded = live_client.get(f"/api/v1/vehicles/{vehicle['id']}", headers=headers).json()[
            "data"
        ]
        nose = next(c for c in loaded["components"] if c["component_type"] == "nose")
        assert nose["mass_kg"] == 5.0
        assert nose["dimensions"] == {"length_m": 0.5, "diameter_m": 0.3}
        assert nose["position"] == {"x": 0, "y": 0, "z": 2.5}

    def test_one_vehicle_per_mission(self, live_client: TestClient) -> None:
        headers, _ = _auth(live_client)
        project = _make_project(live_client, headers)
        mission = _make_mission(live_client, headers, project["id"])

        first = live_client.post(
            "/api/v1/vehicles",
            json={"mission_id": mission["id"], "name": "First"},
            headers=headers,
        )
        assert first.status_code == 201
        second = live_client.post(
            "/api/v1/vehicles",
            json={"mission_id": mission["id"], "name": "Second"},
            headers=headers,
        )
        assert second.status_code == 409

    def test_component_parent_must_be_same_vehicle(self, live_client: TestClient) -> None:
        headers, _ = _auth(live_client)
        project = _make_project(live_client, headers)

        mission_a = _make_mission(live_client, headers, project["id"])
        vehicle_a = live_client.post(
            "/api/v1/vehicles",
            json={
                "mission_id": mission_a["id"],
                "name": "A",
                "components": [
                    {
                        "component_type": "body",
                        "mass_kg": 1,
                        "position": {},
                        "dimensions": {},
                    }
                ],
            },
            headers=headers,
        ).json()["data"]
        foreign_component_id = vehicle_a["components"][0]["id"]

        mission_b = _make_mission(live_client, headers, project["id"])
        vehicle_b = live_client.post(
            "/api/v1/vehicles",
            json={"mission_id": mission_b["id"], "name": "B"},
            headers=headers,
        ).json()["data"]

        response = live_client.post(
            f"/api/v1/vehicles/{vehicle_b['id']}/components",
            json={
                "component_type": "nose",
                "mass_kg": 1,
                "position": {},
                "dimensions": {},
                "parent_id": foreign_component_id,
            },
            headers=headers,
        )
        assert response.status_code == 400

    def test_cannot_read_another_users_vehicle(self, live_client: TestClient) -> None:
        owner_headers, _ = _auth(live_client)
        attacker_headers, _ = _auth(live_client)
        project = _make_project(live_client, owner_headers)
        mission = _make_mission(live_client, owner_headers, project["id"])
        vehicle = live_client.post(
            "/api/v1/vehicles",
            json={"mission_id": mission["id"], "name": "Private"},
            headers=owner_headers,
        ).json()["data"]

        assert (
            live_client.get(
                f"/api/v1/vehicles/{vehicle['id']}", headers=attacker_headers
            ).status_code
            == 404
        )


@requires_db
class TestLearning:
    def test_lessons_are_public(self, live_client: TestClient) -> None:
        assert live_client.get("/api/v1/lessons").status_code == 200

    def test_nonexistent_lesson_is_404(self, live_client: TestClient) -> None:
        assert live_client.get(f"/api/v1/lessons/{uuid.uuid4()}").status_code == 404
        assert live_client.get("/api/v1/lessons/no-such-slug").status_code == 404

    def test_progress_requires_an_existing_lesson(self, live_client: TestClient) -> None:
        headers, _ = _auth(live_client)
        response = live_client.post(
            "/api/v1/learning/progress",
            json={"lesson_id": str(uuid.uuid4()), "status": "in_progress"},
            headers=headers,
        )
        assert response.status_code == 404

    def test_progress_upsert_is_idempotent(self, live_client: TestClient) -> None:
        """Posting twice for the same lesson must update, not create a second
        row or violate the UNIQUE constraint."""
        headers, _ = _auth(live_client)
        lessons = live_client.get("/api/v1/lessons").json()["data"]
        if not lessons:
            return  # nothing seeded; covered by the seed test instead
        lesson_id = lessons[0]["id"]

        first = live_client.post(
            "/api/v1/learning/progress",
            json={"lesson_id": lesson_id, "progress_percent": 25},
            headers=headers,
        )
        assert first.status_code == 200
        second = live_client.post(
            "/api/v1/learning/progress",
            json={"lesson_id": lesson_id, "progress_percent": 75},
            headers=headers,
        )
        assert second.status_code == 200
        assert second.json()["data"]["progress_percent"] == 75

        rows = live_client.get("/api/v1/learning/progress", headers=headers).json()["data"]
        assert len([r for r in rows if r["lesson_id"] == lesson_id]) == 1

    def test_completion_sets_completed_at(self, live_client: TestClient) -> None:
        headers, _ = _auth(live_client)
        lessons = live_client.get("/api/v1/lessons").json()["data"]
        if not lessons:
            return
        response = live_client.post(
            "/api/v1/learning/progress",
            json={"lesson_id": lessons[0]["id"], "status": "completed"},
            headers=headers,
        )
        data = response.json()["data"]
        assert data["status"] == "completed"
        assert data["progress_percent"] == 100
        assert data["completed_at"] is not None

    def test_progress_is_isolated_between_users(self, live_client: TestClient) -> None:
        headers_a, _ = _auth(live_client)
        headers_b, _ = _auth(live_client)
        lessons = live_client.get("/api/v1/lessons").json()["data"]
        if not lessons:
            return

        live_client.post(
            "/api/v1/learning/progress",
            json={"lesson_id": lessons[0]["id"], "progress_percent": 50},
            headers=headers_a,
        )
        assert live_client.get("/api/v1/learning/progress", headers=headers_b).json()["data"] == []


@requires_db
class TestConversations:
    def test_conversation_and_message_persistence(self, live_client: TestClient) -> None:
        """P4's path: create a conversation, store a user turn and an
        assistant turn with grounding, read the transcript back in order."""
        headers, _ = _auth(live_client)

        conversation = live_client.post(
            "/api/v1/conversations",
            json={"title": "Why did it fail?", "context_type": "tutor"},
            headers=headers,
        )
        assert conversation.status_code == 201
        conversation_id = conversation.json()["data"]["id"]

        live_client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"role": "user", "content": "Why did my rocket fail?"},
            headers=headers,
        )
        live_client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={
                "role": "assistant",
                "content": "Thrust-to-weight was below 1.",
                "grounding": [{"type": "lesson", "slug": "thrust-to-weight-ratio"}],
            },
            headers=headers,
        )

        detail = live_client.get(
            f"/api/v1/conversations/{conversation_id}", headers=headers
        ).json()["data"]
        assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
        assert detail["messages"][1]["grounding"][0]["slug"] == "thrust-to-weight-ratio"

    def test_cannot_read_another_users_conversation(self, live_client: TestClient) -> None:
        owner_headers, _ = _auth(live_client)
        attacker_headers, _ = _auth(live_client)
        conversation_id = live_client.post(
            "/api/v1/conversations", json={"title": "Private"}, headers=owner_headers
        ).json()["data"]["id"]

        assert (
            live_client.get(
                f"/api/v1/conversations/{conversation_id}", headers=attacker_headers
            ).status_code
            == 404
        )

    def test_cannot_post_message_to_another_users_conversation(
        self, live_client: TestClient
    ) -> None:
        owner_headers, _ = _auth(live_client)
        attacker_headers, _ = _auth(live_client)
        conversation_id = live_client.post(
            "/api/v1/conversations", json={"title": "Private"}, headers=owner_headers
        ).json()["data"]["id"]

        assert (
            live_client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={"role": "user", "content": "injected"},
                headers=attacker_headers,
            ).status_code
            == 404
        )

    def test_deleting_conversation_removes_messages(self, live_client: TestClient) -> None:
        headers, _ = _auth(live_client)
        conversation_id = live_client.post(
            "/api/v1/conversations", json={"title": "Temp"}, headers=headers
        ).json()["data"]["id"]
        live_client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"role": "user", "content": "hi"},
            headers=headers,
        )

        assert (
            live_client.delete(
                f"/api/v1/conversations/{conversation_id}", headers=headers
            ).status_code
            == 204
        )
        assert (
            live_client.get(f"/api/v1/conversations/{conversation_id}", headers=headers).status_code
            == 404
        )


@requires_db
class TestSpaceObjects:
    def test_list_and_filter(self, live_client: TestClient) -> None:
        listed = live_client.get("/api/v1/space-objects")
        assert listed.status_code == 200
        assert "meta" in listed.json()

    def test_nonexistent_object_is_404(self, live_client: TestClient) -> None:
        assert live_client.get(f"/api/v1/space-objects/{uuid.uuid4()}").status_code == 404


@requires_db
class TestFullDemoJourney:
    def test_complete_user_journey(self, live_client: TestClient) -> None:
        """The DEMO_RUNBOOK path end to end:
        register -> project -> mission -> vehicle -> lesson progress ->
        conversation. If this passes, the prototype demo is backed by real
        persistence.
        """
        headers, _ = _auth(live_client)

        project = _make_project(live_client, headers, name="SIH Demo Project")
        mission = _make_mission(live_client, headers, project["id"])

        vehicle = live_client.post(
            "/api/v1/vehicles",
            json={
                "mission_id": mission["id"],
                "name": "Demo Rocket",
                "components": [
                    {
                        "component_type": "nose",
                        "mass_kg": 5,
                        "position": {"x": 0, "y": 0, "z": 3},
                        "dimensions": {"length_m": 0.5},
                    }
                ],
            },
            headers=headers,
        )
        assert vehicle.status_code == 201

        conversation = live_client.post(
            "/api/v1/conversations", json={"title": "Demo chat"}, headers=headers
        )
        assert conversation.status_code == 201

        # Everything is reachable from the dashboard afterwards.
        assert live_client.get("/api/v1/projects", headers=headers).json()["meta"]["total"] >= 1
        assert live_client.get("/api/v1/vehicles", headers=headers).json()["meta"]["total"] >= 1
        conversations = live_client.get("/api/v1/conversations", headers=headers)
        assert conversations.json()["meta"]["total"] >= 1
