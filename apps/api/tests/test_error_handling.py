from fastapi.testclient import TestClient


def test_unknown_route_returns_structured_404(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "HTTP_404"
    assert "message" in body["error"]


def test_wrong_method_returns_structured_405(client: TestClient) -> None:
    response = client.post("/api/v1/health")

    assert response.status_code == 405
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "HTTP_405"


def test_error_response_still_has_cors_headers(client: TestClient) -> None:
    response = client.get(
        "/api/v1/does-not-exist",
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
