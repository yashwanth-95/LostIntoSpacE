"""ISRO / Bhoonidhi integration.

The default suite is fully mocked. An integration path against the real API is
provided for environments that hold credentials, and is skipped everywhere else.

The Bhoonidhi search fixture is hand-built from the published API specification
(STAC FeatureCollection with `context`, `features` and paginating `links`)
rather than recorded, because obtaining a real response requires an authorized
account this project does not have. It is marked as such so nobody mistakes it
for a recording.
"""

import os

import pytest

from data.models import AccessStatus, EOProduct, ObjectType
from data.normalization.isro import normalize_bhoonidhi_item
from data.provenance import require_provenance
from data.sources import (
    BhoonidhiSource,
    SourceAuthError,
    SourceQuery,
    SourceResponseError,
    build_source,
)
from data.sources.base import SourceRecord
from data.sources.isro import (
    BHOONIDHI_ACCESS_CONTACT,
    BHOONIDHI_PASSWORD_ENV,
    BHOONIDHI_TOKEN_ENV,
    BHOONIDHI_USERNAME_ENV,
)
from data.tests.mocks import MockEndpoint, MockProvider, load_fixture

LIVE = os.environ.get("LOSTINTOSPACE_LIVE_TESTS") == "1"
HAS_CREDENTIALS = bool(
    os.environ.get("BHOONIDHI_ACCESS_TOKEN")
    or (os.environ.get(BHOONIDHI_USERNAME_ENV) and os.environ.get(BHOONIDHI_PASSWORD_ENV))
)
authorized_only = pytest.mark.skipif(
    not (LIVE and HAS_CREDENTIALS),
    reason="needs LOSTINTOSPACE_LIVE_TESTS=1 and Bhoonidhi credentials",
)

SEARCH = load_fixture("bhoonidhi_search.json")
NISAR = SEARCH["features"][0]
RESOURCESAT = SEARCH["features"][1]

TOKEN_RESPONSE = {
    "access_token": "test-access-token",
    "refresh_token": "test-refresh-token",
    "expires_in": 3600,
}


@pytest.fixture(autouse=True)
def _clear_credentials(monkeypatch):
    """Every test states its own credential situation explicitly."""
    for variable in BHOONIDHI_TOKEN_ENV + (BHOONIDHI_USERNAME_ENV, BHOONIDHI_PASSWORD_ENV):
        monkeypatch.delenv(variable, raising=False)


def item_record(feature=NISAR) -> SourceRecord:
    source = build_source("isro_bhoonidhi")
    return SourceRecord(
        source_name="isro_bhoonidhi",
        source_record_id=feature["id"],
        payload=feature,
        source_reference=source.build_source_reference(record_id=feature["id"]),
    )


def authorized_provider() -> MockProvider:
    return (
        MockProvider("isro_bhoonidhi")
        .route("/auth/token", MockEndpoint(json=TOKEN_RESPONSE))
        .route("/data/search", MockEndpoint(json=SEARCH))
        .route("/data/collections", MockEndpoint(json={"collections": [
            {"id": "NISAR-S-RSLC", "title": "NISAR S-band RSLC"},
            {"id": "RESOURCESAT-2", "title": "Resourcesat-2"},
        ]}))
    )


class TestAuthorizationGate:
    async def test_no_credentials_reports_missing_not_empty(self):
        source = build_source("isro_bhoonidhi")
        status = await source.health_check()
        assert status.healthy is False
        assert status.credentials_missing is True
        assert "not absence of data" in status.detail
        await source.aclose()

    async def test_health_detail_says_how_to_get_access(self):
        source = build_source("isro_bhoonidhi")
        status = await source.health_check()
        assert BHOONIDHI_ACCESS_CONTACT in status.detail
        assert BHOONIDHI_USERNAME_ENV in status.detail
        await source.aclose()

    async def test_search_without_credentials_raises_auth_error(self):
        provider = MockProvider("isro_bhoonidhi")
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        with pytest.raises(SourceAuthError, match="authorization-gated"):
            await source.search(SourceQuery(extra={"collections": "NISAR-S-RSLC"}))
        # No request is made at all, so no data is silently reported as absent.
        assert provider.call_count == 0
        await source.aclose()

    async def test_auth_error_names_the_environment_variables(self):
        source = build_source("isro_bhoonidhi")
        with pytest.raises(SourceAuthError) as excinfo:
            source.require_authorization()
        message = str(excinfo.value)
        assert BHOONIDHI_USERNAME_ENV in message
        assert BHOONIDHI_PASSWORD_ENV in message
        assert BHOONIDHI_ACCESS_CONTACT in message
        await source.aclose()

    async def test_no_scraping_fallback_exists(self):
        """There is no HTML path: the official API is the only route."""
        source = build_source("isro_bhoonidhi")
        assert not hasattr(source, "scrape")
        assert source.config.base_url == "https://bhoonidhi-api.nrsc.gov.in"
        await source.aclose()

    async def test_pre_issued_token_is_accepted(self, monkeypatch):
        monkeypatch.setenv("BHOONIDHI_ACCESS_TOKEN", "preissued-token")
        provider = authorized_provider()
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        assert source.is_authorized is True
        await source.search(SourceQuery(extra={"collections": "NISAR-S-RSLC"}))
        # No token exchange needed when a token was supplied.
        assert "/auth/token" not in provider.paths()
        assert provider.last_request().headers["Authorization"] == "Bearer preissued-token"
        await source.aclose()

    async def test_username_and_password_exchange_for_a_token(self, monkeypatch):
        monkeypatch.setenv(BHOONIDHI_USERNAME_ENV, "user")
        monkeypatch.setenv(BHOONIDHI_PASSWORD_ENV, "secret-password")
        provider = authorized_provider()
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        await source.search(SourceQuery(extra={"collections": "NISAR-S-RSLC"}))
        assert "/auth/token" in provider.paths()
        assert provider.last_request().headers["Authorization"] == (
            "Bearer test-access-token"
        )
        await source.aclose()

    async def test_token_is_cached_across_requests(self, monkeypatch):
        """The specification asks callers not to re-authenticate per request."""
        monkeypatch.setenv(BHOONIDHI_USERNAME_ENV, "user")
        monkeypatch.setenv(BHOONIDHI_PASSWORD_ENV, "secret-password")
        provider = authorized_provider()
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        for _ in range(3):
            await source.search(SourceQuery(extra={"collections": "NISAR-S-RSLC"}))
        assert provider.paths().count("/auth/token") == 1
        await source.aclose()

    async def test_password_never_appears_in_a_stored_record(self, monkeypatch):
        monkeypatch.setenv(BHOONIDHI_USERNAME_ENV, "user")
        monkeypatch.setenv(BHOONIDHI_PASSWORD_ENV, "secret-password")
        provider = authorized_provider()
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        page = await source.search(SourceQuery(extra={"collections": "NISAR-S-RSLC"}))
        serialized = page.model_dump_json()
        assert "secret-password" not in serialized
        assert "test-access-token" not in serialized
        await source.aclose()

    async def test_missing_token_in_auth_response_is_an_auth_error(self, monkeypatch):
        monkeypatch.setenv(BHOONIDHI_USERNAME_ENV, "user")
        monkeypatch.setenv(BHOONIDHI_PASSWORD_ENV, "secret-password")
        provider = MockProvider("isro_bhoonidhi").route(
            "/auth/token", MockEndpoint(json={"detail": "no api access"})
        )
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        with pytest.raises(SourceAuthError, match="did not return an access token"):
            await source.authenticate()
        await source.aclose()


class TestSearch:
    async def test_search_returns_stac_features(self, monkeypatch):
        monkeypatch.setenv("BHOONIDHI_ACCESS_TOKEN", "t")
        provider = authorized_provider()
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        page = await source.search(
            SourceQuery(extra={"collections": ["NISAR-S-RSLC", "RESOURCESAT-2"]}, limit=2)
        )
        assert len(page.records) == 2
        assert provider.last_params()["collections"] == "NISAR-S-RSLC,RESOURCESAT-2"
        assert provider.last_params()["limit"] == "2"
        await source.aclose()

    async def test_limit_capped_at_the_documented_maximum(self, monkeypatch):
        monkeypatch.setenv("BHOONIDHI_ACCESS_TOKEN", "t")
        provider = authorized_provider()
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        await source.search(
            SourceQuery(extra={"collections": "NISAR-S-RSLC"}, limit=1000)
        )
        assert int(provider.last_params()["limit"]) == 500
        await source.aclose()

    async def test_datetime_interval_is_rfc3339(self, monkeypatch):
        from datetime import datetime, timezone

        monkeypatch.setenv("BHOONIDHI_ACCESS_TOKEN", "t")
        provider = authorized_provider()
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        await source.search(
            SourceQuery(
                start_time=datetime(2026, 7, 1, tzinfo=timezone.utc),
                end_time=datetime(2026, 7, 31, tzinfo=timezone.utc),
            )
        )
        assert provider.last_params()["datetime"] == (
            "2026-07-01T00:00:00Z/2026-07-31T00:00:00Z"
        )
        await source.aclose()

    async def test_open_ended_interval(self, monkeypatch):
        from datetime import datetime, timezone

        monkeypatch.setenv("BHOONIDHI_ACCESS_TOKEN", "t")
        provider = authorized_provider()
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        await source.search(SourceQuery(start_time=datetime(2026, 7, 1, tzinfo=timezone.utc)))
        assert provider.last_params()["datetime"].endswith("/..")
        await source.aclose()

    async def test_unfiltered_scan_refused(self, monkeypatch):
        monkeypatch.setenv("BHOONIDHI_ACCESS_TOKEN", "t")
        provider = authorized_provider()
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        with pytest.raises(SourceResponseError, match="unfiltered catalogue scans"):
            await source.search(SourceQuery(text="anything"))
        await source.aclose()

    async def test_bounding_box_validated(self, monkeypatch):
        monkeypatch.setenv("BHOONIDHI_ACCESS_TOKEN", "t")
        provider = authorized_provider()
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        with pytest.raises(SourceResponseError, match="4 or 6 numbers"):
            await source.search(SourceQuery(extra={"bbox": [1, 2, 3]}))
        with pytest.raises(SourceResponseError, match="must be numeric"):
            await source.search(SourceQuery(extra={"bbox": ["a", "b", "c", "d"]}))
        await source.aclose()

    async def test_pagination_token_surfaced(self, monkeypatch):
        monkeypatch.setenv("BHOONIDHI_ACCESS_TOKEN", "t")
        provider = authorized_provider()
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        page = await source.search(SourceQuery(extra={"collections": "NISAR-S-RSLC"}))
        assert page.next_cursor == "next:eyJvZmZzZXQiOjJ9"
        await source.aclose()

    async def test_malformed_response_rejected(self, monkeypatch):
        monkeypatch.setenv("BHOONIDHI_ACCESS_TOKEN", "t")
        provider = MockProvider("isro_bhoonidhi").route(
            "/data/search", MockEndpoint(json={"unexpected": True})
        )
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        with pytest.raises(SourceResponseError, match="no 'features' array"):
            await source.search(SourceQuery(extra={"collections": "NISAR-S-RSLC"}))
        await source.aclose()

    async def test_collections_listed(self, monkeypatch):
        monkeypatch.setenv("BHOONIDHI_ACCESS_TOKEN", "t")
        provider = authorized_provider()
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        collections = await source.collections()
        assert {"NISAR-S-RSLC", "RESOURCESAT-2"} == {c["id"] for c in collections}
        await source.aclose()

    async def test_fetch_by_id_within_a_collection(self, monkeypatch):
        monkeypatch.setenv("BHOONIDHI_ACCESS_TOKEN", "t")
        provider = MockProvider("isro_bhoonidhi").route(
            "/data/collections/NISAR-S-RSLC/items/{0}".format(NISAR["id"]),
            MockEndpoint(json=NISAR),
        )
        source = build_source("isro_bhoonidhi", transport=provider.transport)
        record = await source.fetch_by_id(NISAR["id"], collection="NISAR-S-RSLC")
        assert record.source_record_id == NISAR["id"]
        await source.aclose()

    async def test_blank_identifier_rejected(self, monkeypatch):
        monkeypatch.setenv("BHOONIDHI_ACCESS_TOKEN", "t")
        source = build_source("isro_bhoonidhi")
        with pytest.raises(SourceResponseError, match="needs an item id"):
            await source.fetch_by_id("  ")
        await source.aclose()


class TestNisarNormalization:
    def test_becomes_an_eo_product(self):
        product, _ = normalize_bhoonidhi_item(item_record())
        assert isinstance(product, EOProduct)
        assert product.object_type is ObjectType.EO_PRODUCT

    def test_mission_satellite_and_instrument_captured(self):
        product, _ = normalize_bhoonidhi_item(item_record())
        assert product.mission == "NISAR"
        assert product.platform == "NISAR"
        assert product.instrument == "S-SAR"

    def test_product_and_processing_level_captured(self):
        product, _ = normalize_bhoonidhi_item(item_record())
        assert product.product_type == "RSLC"
        assert product.processing_level == "L1"
        assert product.operational_mode == "SHNA"

    def test_acquisition_window_captured(self):
        product, _ = normalize_bhoonidhi_item(item_record())
        assert product.acquisition_start.isoformat().startswith("2026-07-14T05:32:12")
        assert product.acquisition_end > product.acquisition_start

    def test_product_identifier_and_access_url(self):
        product, _ = normalize_bhoonidhi_item(item_record())
        assert product.product_id == NISAR["id"]
        assert product.access_url.startswith("https://bhoonidhi-api.nrsc.gov.in")

    def test_access_url_never_carries_a_token(self):
        product, _ = normalize_bhoonidhi_item(item_record())
        for marker in ("token=", "api_key=", "password="):
            assert marker not in product.access_url.lower()

    def test_authorization_status_recorded(self):
        product, _ = normalize_bhoonidhi_item(item_record(), has_credentials=True)
        assert product.access_status is AccessStatus.AUTHORIZED
        assert product.is_retrievable is True

    def test_unauthorized_status_is_explained_not_hidden(self):
        product, _ = normalize_bhoonidhi_item(item_record(), has_credentials=False)
        assert product.access_status is AccessStatus.CREDENTIALS_REQUIRED
        assert "requires an account" in product.access_explanation()

    def test_authorization_note_travels_with_the_record(self):
        product, _ = normalize_bhoonidhi_item(item_record())
        assert BHOONIDHI_ACCESS_CONTACT in product.source_specific["authorization_note"]

    def test_geometry_preserved(self):
        product, _ = normalize_bhoonidhi_item(item_record())
        assert product.footprint.geojson["type"] == "Polygon"
        assert product.footprint.srid == 4326

    def test_orbit_metadata_mapped(self):
        product, _ = normalize_bhoonidhi_item(item_record())
        assert product.absolute_orbit_number == 1101
        assert product.relative_orbit_number == 14
        assert product.orbit_direction == "ascending"

    def test_assets_recorded(self):
        product, _ = normalize_bhoonidhi_item(item_record())
        assert product.source_specific["assets"] == ["data", "metadata"]
        assert product.source_specific["collection"] == "NISAR-S-RSLC"

    def test_provenance_complete(self):
        product, lineage = normalize_bhoonidhi_item(item_record())
        require_provenance(product, lineage)

    def test_lineage_records_the_access_decision(self):
        _, lineage = normalize_bhoonidhi_item(item_record())
        assert "authorized account" in lineage.explain_field("access_status")

    def test_roundtrips_through_json(self):
        product, _ = normalize_bhoonidhi_item(item_record())
        assert EOProduct.model_validate_json(product.model_dump_json()) == product

    def test_item_without_id_rejected(self):
        record = item_record()
        record.payload = {"type": "Feature", "properties": {}}
        with pytest.raises(ValueError, match="no id"):
            normalize_bhoonidhi_item(record)


class TestResourcesatNormalization:
    def test_alternate_property_spellings_are_handled(self):
        product, _ = normalize_bhoonidhi_item(item_record(RESOURCESAT))
        assert product.mission == "RESOURCESAT-2"
        assert product.platform == "RESOURCESAT-2"
        assert product.instrument == "LISS-III"
        assert product.product_type == "GEOTIFF"
        assert product.processing_level == "L2"

    def test_cloud_cover_mapped(self):
        product, _ = normalize_bhoonidhi_item(item_record(RESOURCESAT))
        assert product.cloud_cover.unit == "percent"
        assert product.cloud_cover.value == pytest.approx(18.5)

    def test_single_datetime_gives_equal_start_and_end(self):
        product, _ = normalize_bhoonidhi_item(item_record(RESOURCESAT))
        assert product.acquisition_start == product.acquisition_end


class TestSourceDeclaration:
    def test_requires_auth_is_declared(self):
        info = build_source("isro_bhoonidhi").get_source_info()
        assert info.requires_auth is True
        assert "public unauthenticated access" in info.does_not_provide

    def test_documented_rate_limits_are_configured(self):
        config = BhoonidhiSource.default_config()
        assert config.rate_limit.requests_per_second == 2.0
        assert "3 search requests per second" in config.rate_limit.policy_note
        assert "20 authentication requests per hour" in config.rate_limit.policy_note

    def test_docs_url_points_at_the_official_specification(self):
        info = build_source("isro_bhoonidhi").get_source_info()
        assert info.docs_url == "https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/"


@authorized_only
class TestBhoonidhiLive:
    """Runs only where real Bhoonidhi credentials are configured."""

    async def test_collections_live(self):
        async with BhoonidhiSource() as source:
            collections = await source.collections()
            assert isinstance(collections, list)

    async def test_search_live(self):
        async with BhoonidhiSource() as source:
            page = await source.search(SourceQuery(extra={"collections": "NISAR-S-RSLC"},
                                                   limit=2))
            if page.records:
                product, _ = normalize_bhoonidhi_item(page.records[0])
                assert product.product_id
