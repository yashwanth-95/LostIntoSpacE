from fastapi.testclient import TestClient

from src.core.config import get_settings


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
    """An error must not lose its CORS headers, or the browser reports a CORS
    failure and the real error is invisible to the client.

    The origin comes from the configured allow-list rather than being hardcoded.
    This previously asserted `http://localhost:5173` — Vite's default port —
    while the app and `apps/web/vite.config.ts` both use 3000, so it tested the
    configuration rather than the behaviour and failed on any correctly
    configured install.
    """
    allowed_origin = get_settings().cors_origins_list[0]

    response = client.get("/api/v1/does-not-exist", headers={"Origin": allowed_origin})

    assert response.headers.get("access-control-allow-origin") == allowed_origin
