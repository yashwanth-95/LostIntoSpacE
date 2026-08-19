"""Mock HTTP transports for every provider.

Built on `httpx.MockTransport`, so the adapter under test runs its real request
path — rate limiting, retry, redaction, validation — against a scripted
response. No network, no extra dependency, and a fixture is literally a recorded
response body.

Usage:

    provider = MockProvider("jpl_sbdb")
    provider.route("/sbdb.api", MockEndpoint(json=CERES_SBDB))
    source = JplSbdbSource(transport=provider.transport)
"""

import json as jsonlib
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

import httpx

__all__ = ["MockEndpoint", "MockProvider", "FakeSleeper", "fixture_path", "load_fixture"]

import pathlib

_FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"


def fixture_path(name: str) -> pathlib.Path:
    """Absolute path to a recorded response fixture."""
    return _FIXTURE_DIR / name


def load_fixture(name: str) -> Any:
    """Load a recorded JSON response fixture."""
    with open(str(fixture_path(name)), "r", encoding="utf-8") as handle:
        return jsonlib.load(handle)


class MockEndpoint:
    """One scripted response, or one scripted failure."""

    def __init__(
        self,
        status: int = 200,
        json: Optional[Any] = None,
        text: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        raises: Optional[Exception] = None,
    ):
        if json is not None and text is not None:
            raise ValueError("give MockEndpoint either json or text, not both")
        self.status = status
        self.json = json
        self.text = text
        self.headers = dict(headers or {})
        #: An exception instance to raise instead of responding — used to
        #: simulate timeouts and connection failures.
        self.raises = raises

    def to_response(self, request: httpx.Request) -> httpx.Response:
        if self.raises is not None:
            raise self.raises
        headers = dict(self.headers)
        if self.json is not None:
            headers.setdefault("Content-Type", "application/json")
            return httpx.Response(
                self.status, json=self.json, headers=headers, request=request
            )
        return httpx.Response(
            self.status, text=self.text or "", headers=headers, request=request
        )


Responder = Union[MockEndpoint, Callable[[httpx.Request], httpx.Response]]


class MockProvider:
    """A scripted stand-in for one provider's HTTP surface."""

    def __init__(self, name: str, default: Optional[MockEndpoint] = None):
        self.name = name
        self._routes: Dict[str, List[Responder]] = {}
        self._default = default or MockEndpoint(
            status=404, json={"error": "no mock route registered"}
        )
        #: Every request the adapter made, in order. Assert against these to
        #: check that query parameters were built correctly.
        self.requests: List[httpx.Request] = []

    def route(self, path: str, *responders: Responder) -> "MockProvider":
        """Register responses for `path`.

        Several responders are returned in order and the last one repeats, which
        is how retry behaviour is scripted: `route(p, fail, fail, success)`.
        """
        if not responders:
            raise ValueError("route needs at least one responder")
        self._routes.setdefault(path, []).extend(responders)
        return self

    def _match(self, request: httpx.Request) -> Optional[str]:
        path = request.url.path
        if path in self._routes:
            return path
        # Fall back to a suffix match so callers can register "/sbdb.api"
        # without repeating the whole base path.
        for candidate in self._routes:
            if path.endswith(candidate):
                return candidate
        return None

    def _handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = self._match(request)
        if key is None:
            return self._default.to_response(request)
        queue = self._routes[key]
        responder = queue[0] if len(queue) == 1 else queue.pop(0)
        if callable(responder) and not isinstance(responder, MockEndpoint):
            return responder(request)
        return responder.to_response(request)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handler)

    # -- assertions helpers ------------------------------------------------
    @property
    def call_count(self) -> int:
        return len(self.requests)

    def last_request(self) -> httpx.Request:
        if not self.requests:
            raise AssertionError("no requests were made to {0}".format(self.name))
        return self.requests[-1]

    def last_params(self) -> Dict[str, str]:
        return dict(self.last_request().url.params)

    def paths(self) -> List[str]:
        return [request.url.path for request in self.requests]


class FakeSleeper:
    """Async sleep replacement that records delays instead of waiting.

    Retry and rate-limit tests assert on the delays that *would* have been
    applied, so the suite stays fast and deterministic.
    """

    def __init__(self):
        self.delays: List[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)

    @property
    def total(self) -> float:
        return sum(self.delays)

    @property
    def count(self) -> int:
        return len(self.delays)


class FakeClock:
    """Monotonic clock a test can advance by hand."""

    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --------------------------------------------------------------------------
# Ready-made minimal mocks, one per registered provider.
#
# These are shape-accurate stubs sufficient to exercise the framework — health
# checks, capability gating, error mapping. Task-specific tests use recorded
# fixtures from `data/tests/fixtures/` for real parsing.
# --------------------------------------------------------------------------

PROVIDER_HEALTH_MOCKS: Dict[str, Sequence] = {
    "nasa_apod": ("/planetary/apod", MockEndpoint(json={"title": "A Galaxy", "date": "2026-08-18"})),
    "nasa_neows": (
        "/neo/rest/v1/stats",
        MockEndpoint(
            json={"near_earth_object_count": 35000},
            headers={"X-RateLimit-Limit": "1000", "X-RateLimit-Remaining": "998"},
        ),
    ),
    "nasa_eonet": ("/categories", MockEndpoint(json={"categories": [{"id": "wildfires"}]})),
    "nasa_ntrs": ("/openapi", MockEndpoint(json={"openapi": "3.0.0"})),
    "jpl_sbdb": ("/sbdb.api", MockEndpoint(json={"object": {"fullname": "1 Ceres"}})),
    "jpl_horizons": ("/api/horizons.api", MockEndpoint(json={"result": "API VERSION: 1.2"})),
    "mpc_orbits": ("/api/get-orb", MockEndpoint(json=[{"designation": "Ceres"}])),
    "mpc_observations": ("/api/get-obs", MockEndpoint(json=[{"designation": "Ceres"}])),
    "nasa_exoplanet_archive": ("/TAP/sync", MockEndpoint(json=[{"count(*)": 5800}])),
    "celestrak_gp": (
        "/NORAD/elements/gp.php",
        MockEndpoint(json=[{"OBJECT_NAME": "ISS (ZARYA)", "NORAD_CAT_ID": 25544}]),
    ),
    "esa_copernicus": ("/odata/v1/Products", MockEndpoint(json={"value": []})),
    "isro_bhoonidhi": (
        "/data/collections",
        MockEndpoint(json={"collections": [{"id": "NISAR-S-RSLC"}]}),
    ),
}


def health_mock(source_name: str) -> MockProvider:
    """A `MockProvider` scripted to answer that source's health probe."""
    path, endpoint = PROVIDER_HEALTH_MOCKS[source_name]
    return MockProvider(source_name).route(path, endpoint)
