from fastapi.testclient import TestClient


def test_health_returns_ok_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["state"] == "ok"
    assert body["data"]["service"] == "lostintospace-api"


def test_health_includes_request_id_header(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) == 32  # uuid4().hex
