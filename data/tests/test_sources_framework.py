"""The adapter framework: HTTP layer, rate limits, errors, registry, mocks."""

import logging

import httpx
import pytest
from pydantic import ValidationError

from data.sources import (
    Capability,
    HttpClient,
    ProviderConfig,
    RateLimitConfig,
    RateLimiter,
    RateLimitExceededError,
    RetryConfig,
    SourceAuthError,
    SourceNotFoundError,
    SourceQuery,
    SourceResponseError,
    SourceTimeoutError,
    SourceUnavailableError,
    UnsupportedOperationError,
    all_source_info,
    build_source,
    get_source_class,
    preferred_source_for,
    redact_mapping,
    redact_url,
    sources_with_capability,
)
from data.sources.registry import SOURCE_CLASSES
from data.tests.mocks import FakeClock, FakeSleeper, MockEndpoint, MockProvider, health_mock


def make_config(**overrides) -> ProviderConfig:
    payload = dict(
        name="test_source",
        base_url="https://example.test",
        timeout_seconds=5.0,
        retry=RetryConfig(max_attempts=3, backoff_factor=0.1, jitter=0.0),
        rate_limit=RateLimitConfig(max_concurrent=2),
    )
    payload.update(overrides)
    return ProviderConfig(**payload)


class TestRedaction:
    def test_api_key_removed_from_url(self):
        url = "https://api.nasa.gov/planetary/apod?api_key=SECRET123&date=2026-08-18"
        redacted = redact_url(url)
        assert "SECRET123" not in redacted
        assert "date=2026-08-18" in redacted
        assert "api_key=***REDACTED***" in redacted

    def test_multiple_secret_params_removed(self):
        url = "https://x.test/a?token=abc&key=def&safe=1"
        redacted = redact_url(url)
        assert "abc" not in redacted and "def" not in redacted
        assert "safe=1" in redacted

    def test_case_insensitive(self):
        assert "SECRET" not in redact_url("https://x.test/a?API_KEY=SECRET")

    def test_headers_redacted(self):
        safe = redact_mapping({"Authorization": "Bearer abc", "Accept": "application/json"})
        assert safe["Authorization"] == "***REDACTED***"
        assert safe["Accept"] == "application/json"

    def test_credential_header_rejected_in_static_headers(self):
        with pytest.raises(ValidationError, match="must be configured via api_key"):
            make_config(headers={"Authorization": "Bearer abc"})


class TestProviderConfig:
    def test_relative_base_url_rejected(self):
        with pytest.raises(ValidationError, match="must be absolute"):
            make_config(base_url="/api")

    def test_api_key_without_transport_rejected(self):
        with pytest.raises(ValidationError, match="api_key_param or api_key_header"):
            make_config(api_key="abc")

    def test_env_overrides_applied(self, monkeypatch):
        monkeypatch.setenv("LIS_TEST_SOURCE_REQUESTS_PER_HOUR", "50")
        monkeypatch.setenv("LIS_TEST_SOURCE_TIMEOUT_SECONDS", "3")
        monkeypatch.setenv("LIS_TEST_SOURCE_MAX_ATTEMPTS", "5")
        resolved = make_config().resolve_from_env()
        assert resolved.rate_limit.requests_per_hour == 50
        assert resolved.timeout_seconds == 3.0
        assert resolved.retry.max_attempts == 5

    def test_env_api_key_resolved_from_documented_variable(self, monkeypatch):
        monkeypatch.setenv("NASA_API_KEY", "from-env")
        source = build_source("nasa_neows")
        assert source.config.api_key == "from-env"
        assert source.config.has_credentials

    def test_invalid_env_values_ignored(self, monkeypatch):
        monkeypatch.setenv("LIS_TEST_SOURCE_REQUESTS_PER_HOUR", "not-a-number")
        assert make_config().resolve_from_env().rate_limit.requests_per_hour is None

    def test_no_universal_rate_limit(self):
        """Each provider carries its own limits; none inherits a shared value."""
        limits = {}
        for name, cls in SOURCE_CLASSES.items():
            limits[name] = cls.default_config().rate_limit
        assert limits["nasa_neows"].requests_per_hour == 1000
        assert limits["jpl_horizons"].requests_per_second == 0.5
        assert limits["celestrak_gp"].requests_per_second == 0.5
        assert limits["nasa_eonet"].requests_per_hour is None
        # Every provider states its policy in words, not just numbers.
        for name, limit in limits.items():
            assert limit.policy_note, "{0} has no documented rate-limit policy".format(name)


class TestRetryConfig:
    def test_backoff_is_exponential_and_capped(self):
        retry = RetryConfig(backoff_factor=1.0, max_backoff_seconds=4.0)
        assert retry.backoff_for(1) == 1.0
        assert retry.backoff_for(2) == 2.0
        assert retry.backoff_for(3) == 4.0
        assert retry.backoff_for(9) == 4.0

    def test_attempt_is_one_based(self):
        with pytest.raises(ValueError, match="1-based"):
            RetryConfig().backoff_for(0)


class TestRateLimiter:
    async def test_min_interval_enforced(self):
        clock, sleeper = FakeClock(), FakeSleeper()
        limiter = RateLimiter(
            RateLimitConfig(requests_per_second=2.0), clock=clock, sleeper=sleeper
        )
        assert await limiter.acquire() == 0.0
        delay = await limiter.acquire()
        assert delay == pytest.approx(0.5)
        assert limiter.throttled_count == 1

    async def test_advancing_the_clock_removes_the_delay(self):
        clock, sleeper = FakeClock(), FakeSleeper()
        limiter = RateLimiter(
            RateLimitConfig(requests_per_second=2.0), clock=clock, sleeper=sleeper
        )
        await limiter.acquire()
        clock.advance(1.0)
        assert await limiter.acquire() == 0.0

    async def test_hourly_bucket_drains_and_refills(self):
        clock, sleeper = FakeClock(), FakeSleeper()
        limiter = RateLimiter(
            RateLimitConfig(requests_per_hour=2), clock=clock, sleeper=sleeper
        )
        await limiter.acquire()
        clock.advance(3600.0)
        await limiter.acquire()
        clock.advance(3600.0)
        assert await limiter.acquire() == 0.0

    def test_quota_headers_observed(self):
        limiter = RateLimiter(
            RateLimitConfig(
                requests_per_hour=1000,
                limit_header="X-RateLimit-Limit",
                remaining_header="X-RateLimit-Remaining",
            )
        )
        limiter.observe_headers(
            httpx.Headers({"X-RateLimit-Limit": "1000", "X-RateLimit-Remaining": "12"})
        )
        assert limiter.quota.limit == 1000
        assert limiter.quota.remaining == 12

    def test_provider_reported_exhaustion_refuses_further_requests(self):
        limiter = RateLimiter(
            RateLimitConfig(
                requests_per_hour=1000,
                remaining_header="X-RateLimit-Remaining",
                low_quota_threshold=5,
            )
        )
        limiter.observe_headers(httpx.Headers({"X-RateLimit-Remaining": "3"}))
        with pytest.raises(RateLimitExceededError, match="3 requests remaining"):
            limiter.check_quota(source_name="nasa_neows")

    def test_healthy_quota_passes(self):
        limiter = RateLimiter(
            RateLimitConfig(remaining_header="X-RateLimit-Remaining", low_quota_threshold=5)
        )
        limiter.observe_headers(httpx.Headers({"X-RateLimit-Remaining": "900"}))
        limiter.check_quota()

    def test_unparseable_quota_header_ignored(self):
        limiter = RateLimiter(RateLimitConfig(remaining_header="X-RateLimit-Remaining"))
        limiter.observe_headers(httpx.Headers({"X-RateLimit-Remaining": "unknown"}))
        assert limiter.quota.remaining is None


class TestHttpClient:
    async def test_successful_get_returns_raw_response(self):
        provider = MockProvider("t").route("/thing", MockEndpoint(json={"ok": True}))
        client = HttpClient(make_config(), transport=provider.transport)
        response = await client.get("/thing")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert response.attempts == 1
        assert "example.test" in response.url
        await client.aclose()

    async def test_api_key_is_sent_but_never_stored(self):
        provider = MockProvider("t").route("/thing", MockEndpoint(json={}))
        config = make_config(api_key="SECRET123", api_key_param="api_key")
        client = HttpClient(config, transport=provider.transport)
        response = await client.get("/thing")
        # Sent to the provider...
        assert provider.last_params()["api_key"] == "SECRET123"
        # ...but absent from everything we keep.
        assert "SECRET123" not in response.url
        assert response.request_params["api_key"] == "***REDACTED***"
        assert "SECRET123" not in response.model_dump_json()
        await client.aclose()

    async def test_retries_then_succeeds(self):
        sleeper = FakeSleeper()
        provider = MockProvider("t").route(
            "/thing",
            MockEndpoint(status=503, text="down"),
            MockEndpoint(status=503, text="down"),
            MockEndpoint(json={"ok": True}),
        )
        client = HttpClient(make_config(), transport=provider.transport, sleeper=sleeper)
        response = await client.get("/thing")
        assert response.attempts == 3
        assert provider.call_count == 3
        assert sleeper.count == 2
        assert client.stats["retries"] == 2
        await client.aclose()

    async def test_gives_up_after_max_attempts(self):
        sleeper = FakeSleeper()
        provider = MockProvider("t").route("/thing", MockEndpoint(status=503, text="down"))
        client = HttpClient(make_config(), transport=provider.transport, sleeper=sleeper)
        with pytest.raises(SourceUnavailableError, match="provider returned 503"):
            await client.get("/thing")
        assert provider.call_count == 3
        assert client.stats["failures"] == 1
        await client.aclose()

    async def test_backoff_is_exponential(self):
        sleeper = FakeSleeper()
        provider = MockProvider("t").route("/thing", MockEndpoint(status=500))
        config = make_config(
            retry=RetryConfig(max_attempts=4, backoff_factor=1.0, jitter=0.0)
        )
        client = HttpClient(config, transport=provider.transport, sleeper=sleeper)
        with pytest.raises(SourceUnavailableError):
            await client.get("/thing")
        assert sleeper.delays == [1.0, 2.0, 4.0]
        await client.aclose()

    async def test_retry_after_header_is_honoured(self):
        sleeper = FakeSleeper()
        provider = MockProvider("t").route(
            "/thing",
            MockEndpoint(status=429, headers={"Retry-After": "7"}),
            MockEndpoint(json={"ok": True}),
        )
        client = HttpClient(make_config(), transport=provider.transport, sleeper=sleeper)
        await client.get("/thing")
        assert sleeper.delays == [7.0]
        await client.aclose()

    async def test_absurd_retry_after_is_capped(self):
        sleeper = FakeSleeper()
        provider = MockProvider("t").route(
            "/thing",
            MockEndpoint(status=429, headers={"Retry-After": "99999"}),
            MockEndpoint(json={"ok": True}),
        )
        config = make_config(
            retry=RetryConfig(max_attempts=2, jitter=0.0, max_retry_after_seconds=60.0)
        )
        client = HttpClient(config, transport=provider.transport, sleeper=sleeper)
        await client.get("/thing")
        assert sleeper.delays == [60.0]
        await client.aclose()

    async def test_404_is_not_retried(self):
        provider = MockProvider("t").route("/thing", MockEndpoint(status=404, text="nope"))
        client = HttpClient(make_config(), transport=provider.transport)
        with pytest.raises(SourceNotFoundError):
            await client.get("/thing")
        assert provider.call_count == 1
        await client.aclose()

    async def test_401_maps_to_auth_error_and_is_not_retried(self):
        provider = MockProvider("t").route("/thing", MockEndpoint(status=401))
        client = HttpClient(make_config(), transport=provider.transport)
        with pytest.raises(SourceAuthError, match="authorization failed"):
            await client.get("/thing")
        assert provider.call_count == 1
        await client.aclose()

    async def test_unexpected_status_maps_to_response_error(self):
        provider = MockProvider("t").route("/thing", MockEndpoint(status=418, text="teapot"))
        client = HttpClient(make_config(), transport=provider.transport)
        with pytest.raises(SourceResponseError, match="unexpected status 418"):
            await client.get("/thing")
        await client.aclose()

    async def test_timeout_maps_to_timeout_error(self):
        sleeper = FakeSleeper()
        provider = MockProvider("t").route(
            "/thing", MockEndpoint(raises=httpx.ReadTimeout("too slow"))
        )
        client = HttpClient(make_config(), transport=provider.transport, sleeper=sleeper)
        with pytest.raises(SourceTimeoutError, match="timed out"):
            await client.get("/thing")
        await client.aclose()

    async def test_connection_error_maps_to_unavailable(self):
        sleeper = FakeSleeper()
        provider = MockProvider("t").route(
            "/thing", MockEndpoint(raises=httpx.ConnectError("refused"))
        )
        client = HttpClient(make_config(), transport=provider.transport, sleeper=sleeper)
        with pytest.raises(SourceUnavailableError, match="transport error"):
            await client.get("/thing")
        await client.aclose()

    async def test_malformed_json_body_raises_response_error(self):
        provider = MockProvider("t").route("/thing", MockEndpoint(text="<html>nope</html>"))
        client = HttpClient(make_config(), transport=provider.transport)
        response = await client.get("/thing")
        with pytest.raises(SourceResponseError, match="not valid JSON"):
            response.json()
        await client.aclose()

    async def test_errors_carry_source_name_and_redacted_url(self):
        provider = MockProvider("t").route("/thing", MockEndpoint(status=404))
        config = make_config(api_key="SECRET123", api_key_param="api_key")
        client = HttpClient(config, transport=provider.transport)
        with pytest.raises(SourceNotFoundError) as excinfo:
            await client.get("/thing")
        assert excinfo.value.source_name == "test_source"
        assert "SECRET123" not in str(excinfo.value)
        assert "SECRET123" not in (excinfo.value.url or "")
        await client.aclose()

    async def test_logging_never_emits_the_key(self, caplog):
        provider = MockProvider("t").route("/thing", MockEndpoint(json={}))
        config = make_config(api_key="SECRET123", api_key_param="api_key")
        client = HttpClient(config, transport=provider.transport)
        with caplog.at_level(logging.DEBUG, logger="data.sources.http"):
            await client.get("/thing")
        assert caplog.records
        assert "SECRET123" not in caplog.text
        await client.aclose()

    async def test_user_agent_identifies_the_project(self):
        provider = MockProvider("t").route("/thing", MockEndpoint(json={}))
        client = HttpClient(make_config(), transport=provider.transport)
        await client.get("/thing")
        assert "LostIntoSpacE" in provider.last_request().headers["User-Agent"]
        await client.aclose()


class TestSourceQuery:
    def test_empty_query_rejected(self):
        with pytest.raises(ValidationError, match="at least one criterion"):
            SourceQuery()

    def test_reversed_window_rejected(self):
        from datetime import datetime, timezone

        with pytest.raises(ValidationError, match="after end_time"):
            SourceQuery(
                text="mars",
                start_time=datetime(2026, 8, 2, tzinfo=timezone.utc),
                end_time=datetime(2026, 8, 1, tzinfo=timezone.utc),
            )

    def test_limit_bounded(self):
        with pytest.raises(ValidationError):
            SourceQuery(text="mars", limit=100_000)


class TestRegistry:
    def test_every_provider_is_registered(self):
        expected = {
            "nasa_apod", "nasa_neows", "nasa_eonet", "nasa_ntrs",
            "jpl_sbdb", "jpl_horizons",
            "mpc_orbits", "mpc_observations",
            "nasa_exoplanet_archive", "celestrak_gp",
            "esa_copernicus", "isro_bhoonidhi",
        }
        assert set(SOURCE_CLASSES) == expected

    def test_source_info_name_matches_registry_key(self):
        for name, cls in SOURCE_CLASSES.items():
            assert cls().get_source_info().name == name

    def test_source_info_matches_config_name(self):
        for name, cls in SOURCE_CLASSES.items():
            assert cls.default_config().name == name

    def test_unknown_source_raises_with_a_helpful_message(self):
        with pytest.raises(KeyError, match="registered sources are"):
            get_source_class("nasa_hubble")

    def test_authority_is_per_capability_not_global(self):
        assert preferred_source_for(Capability.EPHEMERIS) == "jpl_horizons"
        assert preferred_source_for(Capability.OBSERVATIONS) == "mpc_observations"
        assert preferred_source_for(Capability.EXOPLANETS) == "nasa_exoplanet_archive"
        assert preferred_source_for(Capability.NATURAL_EVENTS) == "nasa_eonet"

    def test_celestrak_is_not_preferred_for_orbital_elements(self):
        """It is an operational feed, so scientific archives outrank it."""
        ranked = sources_with_capability(Capability.ORBITAL_ELEMENTS)
        assert ranked[0] == "jpl_sbdb"
        assert ranked.index("celestrak_gp") > ranked.index("mpc_orbits")

    def test_every_source_declares_what_it_does_not_provide(self):
        for info in all_source_info():
            assert info.does_not_provide, "{0} does not state its limits".format(info.name)
            assert info.provides
            assert info.attribution

    def test_celestrak_declares_secondary_authority(self):
        info = build_source("celestrak_gp").get_source_info()
        assert info.source_type.value == "SECONDARY_OPERATIONAL"
        assert "NOT equivalent to a primary scientific source" in info.authority_note

    def test_every_source_has_a_freshness_policy(self):
        for name, cls in SOURCE_CLASSES.items():
            assert cls().freshness_policy is not None


class TestCapabilityGating:
    def test_unsupported_capability_raises_rather_than_returning_empty(self):
        source = build_source("nasa_apod")
        with pytest.raises(UnsupportedOperationError, match="does not provide EPHEMERIS"):
            source.require_capability(Capability.EPHEMERIS)

    def test_error_lists_what_the_source_does_provide(self):
        source = build_source("nasa_eonet")
        with pytest.raises(UnsupportedOperationError, match="NATURAL_EVENTS"):
            source.require_capability(Capability.ORBITAL_ELEMENTS)

    async def test_declared_but_unimplemented_operation_says_so(self):
        """A capability that is declared but not yet wired must say so.

        Checked across every not-yet-implemented adapter rather than naming one,
        so the test stays meaningful as adapters are completed.
        """
        pending = [
            name
            for name, cls in SOURCE_CLASSES.items()
            if not cls().get_source_info().implemented
            and cls().supports(Capability.SEARCH)
        ]
        if not pending:
            pytest.skip("every adapter declaring SEARCH is now implemented")
        for name in pending:
            source = build_source(name)
            with pytest.raises(UnsupportedOperationError, match="does not implement it yet"):
                await source.search(SourceQuery(text="anything"))
            await source.aclose()

    def test_supports_reflects_declared_capabilities(self):
        assert build_source("mpc_observations").supports(Capability.OBSERVATIONS)
        assert not build_source("mpc_observations").supports(Capability.EPHEMERIS)


class TestHealthChecks:
    @pytest.mark.parametrize("name", sorted(SOURCE_CLASSES))
    async def test_every_provider_has_a_working_mock_health_check(self, name):
        if name == "isro_bhoonidhi":
            pytest.skip("covered separately: credentials are required")
        provider = health_mock(name)
        source = build_source(name, transport=provider.transport)
        status = await source.health_check()
        assert status.healthy, status.detail
        assert status.source_name == name
        await source.aclose()

    async def test_health_check_reports_failure_without_raising(self):
        provider = MockProvider("t").route(
            "/sbdb.api", MockEndpoint(raises=httpx.ConnectError("refused"))
        )
        source = build_source("jpl_sbdb", transport=provider.transport)
        status = await source.health_check()
        assert status.healthy is False
        assert "SourceUnavailableError" in status.detail
        await source.aclose()

    async def test_health_check_surfaces_reported_quota(self):
        provider = health_mock("nasa_neows")
        source = build_source("nasa_neows", transport=provider.transport)
        status = await source.health_check()
        assert status.quota["limit"] == 1000
        assert status.quota["remaining"] == 998
        await source.aclose()

    async def test_authorization_gated_source_reports_missing_credentials(self, monkeypatch):
        for variable in ("BHOONIDHI_ACCESS_TOKEN", "ISRO_BHOONIDHI_TOKEN",
                         "LIS_ISRO_BHOONIDHI_API_KEY"):
            monkeypatch.delenv(variable, raising=False)
        source = build_source("isro_bhoonidhi")
        status = await source.health_check()
        assert status.healthy is False
        assert status.credentials_missing is True
        assert "not absence of data" in status.detail
        await source.aclose()

    async def test_authorized_bhoonidhi_probes_normally(self, monkeypatch):
        monkeypatch.setenv("BHOONIDHI_ACCESS_TOKEN", "token-abc")
        provider = health_mock("isro_bhoonidhi")
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        status = await source.health_check()
        assert status.healthy is True
        assert status.credentials_missing is False
        await source.aclose()


class TestSourceReferenceConstruction:
    async def test_reference_built_from_response_is_redacted(self):
        provider = MockProvider("t").route("/planetary/apod", MockEndpoint(json={}))
        monkey_config = build_source("nasa_apod", transport=provider.transport)
        object.__setattr__(
            monkey_config, "config", monkey_config.config.model_copy(
                update={"api_key": "SECRET123"}
            )
        )
        response = await monkey_config.fetch("/planetary/apod")
        reference = monkey_config.build_source_reference(response, record_id="2026-08-18")
        assert "SECRET123" not in (reference.source_url or "")
        assert reference.source_name == "nasa_apod"
        assert reference.source_record_id == "2026-08-18"
        assert reference.attribution
        await monkey_config.aclose()

    def test_reference_without_a_response_uses_the_base_url(self):
        source = build_source("jpl_sbdb")
        reference = source.build_source_reference(record_id="2000001")
        assert reference.source_url == "https://ssd-api.jpl.nasa.gov"
        assert reference.source_type.value == "PRIMARY_SCIENTIFIC"
