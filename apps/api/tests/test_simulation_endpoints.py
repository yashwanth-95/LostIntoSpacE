"""Tests for POST /api/v1/simulations/run and its guards.

These cover the seam, not the physics — the engine's own suites
(``simulation/tests/``) own whether the trajectory is right. What is tested
here is that a well-formed request produces a real flight, that a malformed one
is rejected cleanly, and that the cost and safety limits actually bite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.schemas.simulation import MAX_STAGES, MAX_TIME_S

FIXTURES = Path(__file__).resolve().parents[3] / "simulation" / "tests" / "fixtures"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def orbital_config():
    return json.loads((FIXTURES / "orbital.config.json").read_text())


@pytest.fixture(scope="module")
def suborbital_config():
    return json.loads((FIXTURES / "suborbital.config.json").read_text())


@pytest.fixture(scope="module")
def orbital_run(client, orbital_config):
    response = client.post("/api/v1/simulations/run", json={"config": orbital_config})
    assert response.status_code == 200, response.text
    return response.json()


class TestEngineAvailability:
    def test_health_engines_reports_every_engine(self, client):
        body = client.get("/api/v1/health/engines").json()
        assert body["status"] == "success"
        assert set(body["data"]) == {"simulation", "search", "ai"}

    def test_the_simulation_engine_is_reachable(self, client):
        body = client.get("/api/v1/health/engines").json()
        assert body["data"]["simulation"]["available"] is True

    def test_it_answers_without_a_database(self, client):
        """Engine availability is independent of PostgreSQL, and must not 500
        when the database is down — that is exactly when it gets checked."""
        assert client.get("/api/v1/health/engines").status_code == 200


class TestLimitsEndpoint:
    def test_it_publishes_the_caps(self, client):
        data = client.get("/api/v1/simulations/limits").json()["data"]
        assert data["max_time_s"] == MAX_TIME_S
        assert data["max_stages"] == MAX_STAGES

    def test_it_needs_no_token(self, client):
        assert client.get("/api/v1/simulations/limits").status_code == 200


class TestRunningASimulation:
    def test_a_guest_can_run_one(self, client, orbital_config):
        """No Authorization header. Guest mode is a product requirement."""
        response = client.post("/api/v1/simulations/run", json={"config": orbital_config})
        assert response.status_code == 200

    def test_it_returns_the_standard_envelope(self, orbital_run):
        assert orbital_run["status"] == "success"
        assert "data" in orbital_run
        assert "meta" in orbital_run

    def test_the_reference_launcher_reaches_orbit(self, orbital_run):
        data = orbital_run["data"]
        assert data["outcome"] == "success"
        assert data["summary"]["max_altitude_m"] > 150_000
        assert any(point["in_orbit"] for point in data["telemetry"])

    def test_it_returns_telemetry_events_and_a_summary(self, orbital_run):
        data = orbital_run["data"]
        assert len(data["telemetry"]) > 100
        assert len(data["events"]) > 5
        assert data["summary"]["max_speed_ms"] > 1000

    def test_telemetry_samples_carry_the_documented_fields(self, orbital_run):
        point = orbital_run["data"]["telemetry"][10]
        for field in (
            "t",
            "altitude_m",
            "speed_ms",
            "acceleration_ms2",
            "mass_kg",
            "thrust_N",
            "drag_N",
            "g_load_g",
            "dynamic_pressure_Pa",
            "mach",
            "stage",
            "mission_state",
        ):
            assert field in point, f"telemetry is missing {field}"

    def test_events_are_ordered_and_typed(self, orbital_run):
        events = orbital_run["data"]["events"]
        assert [e["t"] for e in events] == sorted(e["t"] for e in events)
        assert all(e["type"] and e["severity"] for e in events)

    def test_the_meta_block_records_provenance(self, orbital_run):
        meta = orbital_run["meta"]
        assert meta["engine"] == "lostintospace-python-simulation"
        assert meta["compute_time_s"] > 0
        assert meta["telemetry_points_generated"] >= meta["telemetry_points_returned"]

    def test_a_suborbital_hop_comes_back_down(self, client, suborbital_config):
        data = client.post(
            "/api/v1/simulations/run", json={"config": suborbital_config}
        ).json()["data"]
        assert data["final_state"] == "SURFACE"


class TestFailuresAreReported:
    def test_an_underpowered_vehicle_returns_a_structured_failure(
        self, client, orbital_config
    ):
        """The failure record is what the AI assistant consumes to explain a
        loss, so it must survive the round trip intact."""
        config = json.loads(json.dumps(orbital_config))
        for stage in config["vehicle"]["stages"]:
            stage["thrust_vacuum_N"] = 1000.0
            stage["thrust_sea_level_N"] = 1000.0

        data = client.post("/api/v1/simulations/run", json={"config": config}).json()["data"]

        assert data["failures"], "an underpowered vehicle should fail"
        failure = data["failures"][0]
        assert failure["mode_id"] == "INSUFFICIENT_THRUST"
        assert failure["severity"] in {"info", "warning", "critical", "fatal"}
        assert failure["educational_explanation"]
        assert failure["recommended_fix"]
        assert failure["measured_value"] < failure["threshold_value"]


class TestRequestValidation:
    def test_an_empty_body_is_rejected(self, client):
        assert client.post("/api/v1/simulations/run", json={}).status_code == 422

    def test_a_config_without_a_vehicle_is_rejected(self, client):
        response = client.post("/api/v1/simulations/run", json={"config": {"mission": {}}})
        assert response.status_code == 422

    def test_a_structurally_invalid_config_returns_400_with_detail(
        self, client, orbital_config
    ):
        config = json.loads(json.dumps(orbital_config))
        del config["vehicle"]["stages"][0]["thrust_vacuum_N"]

        response = client.post("/api/v1/simulations/run", json={"config": config})
        assert response.status_code == 400
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == "BAD_REQUEST"
        assert body["error"]["details"], "the caller should be told which field"

    def test_a_negative_propellant_mass_is_rejected(self, client, orbital_config):
        config = json.loads(json.dumps(orbital_config))
        config["vehicle"]["stages"][0]["propellant_mass_kg"] = -5000.0
        assert client.post("/api/v1/simulations/run", json={"config": config}).status_code == 400


class TestCostLimits:
    """The endpoint takes no token, so these are the only thing bounding it."""

    def test_an_excessive_max_time_is_rejected(self, client, orbital_config):
        config = json.loads(json.dumps(orbital_config))
        config["settings"]["max_time_s"] = MAX_TIME_S * 10
        assert client.post("/api/v1/simulations/run", json={"config": config}).status_code == 422

    def test_a_microscopic_timestep_is_rejected(self, client, orbital_config):
        config = json.loads(json.dumps(orbital_config))
        config["settings"]["dt_powered_s"] = 1e-9
        assert client.post("/api/v1/simulations/run", json={"config": config}).status_code == 422

    def test_an_absurd_step_count_is_rejected(self, client, orbital_config):
        config = json.loads(json.dumps(orbital_config))
        config["settings"]["max_steps"] = 10**12
        assert client.post("/api/v1/simulations/run", json={"config": config}).status_code == 422

    def test_too_many_stages_is_rejected(self, client, orbital_config):
        config = json.loads(json.dumps(orbital_config))
        stage = config["vehicle"]["stages"][0]
        config["vehicle"]["stages"] = [
            {**stage, "stage_number": i} for i in range(MAX_STAGES + 5)
        ]
        assert client.post("/api/v1/simulations/run", json={"config": config}).status_code == 422

    def test_telemetry_is_decimated_rather_than_unbounded(self, client, orbital_config):
        """A fine sample interval must not return a multi-megabyte body."""
        config = json.loads(json.dumps(orbital_config))
        config["settings"]["telemetry_sample_interval_s"] = 0.05

        body = client.post("/api/v1/simulations/run", json={"config": config}).json()
        assert body["meta"]["telemetry_decimated"] is True
        assert len(body["data"]["telemetry"]) <= 5_000
        # The last sample is kept, so the flight does not appear to stop early.
        assert body["data"]["telemetry"][-1]["t"] == pytest.approx(
            body["data"]["summary"]["flight_time_s"], rel=0.05
        )


class TestNoCodeExecution:
    """The configuration is data. There is no path that evaluates it."""

    def test_an_expression_in_a_numeric_field_is_rejected(self, client, orbital_config):
        config = json.loads(json.dumps(orbital_config))
        config["vehicle"]["stages"][0]["thrust_vacuum_N"] = "__import__('os').system('id')"
        assert client.post("/api/v1/simulations/run", json={"config": config}).status_code == 400

    def test_unknown_fields_do_not_reach_the_engine(self, client, orbital_config):
        """Extra keys are ignored, not executed, and not echoed back."""
        config = json.loads(json.dumps(orbital_config))
        config["__class__"] = "evil"
        config["vehicle"]["exec"] = "rm -rf /"

        response = client.post("/api/v1/simulations/run", json={"config": config})
        assert response.status_code == 200
        assert "exec" not in json.dumps(response.json()["data"])
