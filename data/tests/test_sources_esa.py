"""Copernicus OData integration: discovery, filtering, pagination, failures."""

import os
from datetime import datetime, timezone

import httpx
import pytest

from data.models import AccessStatus, EOProduct, ObjectType
from data.normalization.esa import extract_attributes, normalize_copernicus_product
from data.provenance import require_provenance
from data.sources import (
    CopernicusSource,
    SourceQuery,
    SourceResponseError,
    SourceTimeoutError,
    SourceUnavailableError,
    build_source,
)
from data.sources.base import SourceRecord
from data.sources.esa import COLLECTIONS, odata_literal
from data.tests.mocks import FakeSleeper, MockEndpoint, MockProvider, load_fixture

LIVE = os.environ.get("LOSTINTOSPACE_LIVE_TESTS") == "1"
live_only = pytest.mark.skipif(not LIVE, reason="set LOSTINTOSPACE_LIVE_TESTS=1 to run")

PAGE = load_fixture("copernicus_sentinel2.json")
PRODUCT = PAGE["value"][0]


def product_record(payload=None) -> SourceRecord:
    source = build_source("esa_copernicus")
    payload = PRODUCT if payload is None else payload
    return SourceRecord(
        source_name="esa_copernicus",
        source_record_id=payload.get("Id"),
        payload=payload,
        source_reference=source.build_source_reference(record_id=payload.get("Id")),
    )


class TestOdataFilterSafety:
    def test_literal_escapes_quotes(self):
        assert odata_literal("O'Brien") == "'O''Brien'"

    def test_literal_rejects_control_characters(self):
        with pytest.raises(SourceResponseError, match="control characters"):
            odata_literal("a\nb")

    async def test_collection_allow_list_enforced(self):
        provider = MockProvider("esa_copernicus")
        source = build_source("esa_copernicus", transport=provider.transport)
        with pytest.raises(SourceResponseError, match="not in the allow-list"):
            await source.search(SourceQuery(extra={"collection": "SECRET-9"}))
        assert provider.call_count == 0
        await source.aclose()

    async def test_unfiltered_scan_refused(self):
        source = build_source("esa_copernicus")
        with pytest.raises(SourceResponseError, match="unfiltered catalogue scans"):
            await source.search(SourceQuery(extra={"unrelated": 1}))
        await source.aclose()

    async def test_injection_in_a_name_is_escaped(self):
        provider = MockProvider("esa_copernicus").route(
            "/odata/v1/Products", MockEndpoint(json=PAGE)
        )
        source = build_source("esa_copernicus", transport=provider.transport)
        await source.search(SourceQuery(identifier="x' or Name ne '"))
        sent = provider.last_params()["$filter"]
        assert "Name eq 'x'' or Name ne '''" in sent
        await source.aclose()

    async def test_cloud_cover_bounds_validated(self):
        source = build_source("esa_copernicus")
        with pytest.raises(SourceResponseError, match=r"\[0, 100\]"):
            await source.search(
                SourceQuery(extra={"collection": "SENTINEL-2", "max_cloud_cover": 250})
            )
        await source.aclose()

    async def test_wkt_geometry_validated(self):
        source = build_source("esa_copernicus")
        with pytest.raises(SourceResponseError, match="unsupported WKT geometry"):
            await source.search(SourceQuery(extra={"intersects_wkt": "DROP TABLE x"}))
        await source.aclose()

    async def test_wkt_with_quotes_refused(self):
        source = build_source("esa_copernicus")
        with pytest.raises(SourceResponseError, match="must not contain quotes"):
            await source.search(
                SourceQuery(extra={"intersects_wkt": "POLYGON ((0 0)) '; --"})
            )
        await source.aclose()


class TestProductDiscovery:
    async def test_search_by_collection_and_window(self):
        provider = MockProvider("esa_copernicus").route(
            "/odata/v1/Products", MockEndpoint(json=PAGE)
        )
        source = build_source("esa_copernicus", transport=provider.transport)
        page = await source.search(
            SourceQuery(
                start_time=datetime(2026, 8, 1, tzinfo=timezone.utc),
                end_time=datetime(2026, 8, 18, tzinfo=timezone.utc),
                extra={"collection": "SENTINEL-2"},
                limit=2,
            )
        )
        sent = provider.last_params()["$filter"]
        assert "Collection/Name eq 'SENTINEL-2'" in sent
        assert "ContentDate/Start gt 2026-08-01T00:00:00.000Z" in sent
        assert "ContentDate/Start lt 2026-08-18T00:00:00.000Z" in sent
        assert provider.last_params()["$top"] == "2"
        assert provider.last_params()["$expand"] == "Attributes"
        assert len(page.records) == 2
        await source.aclose()

    async def test_cloud_cover_filter_targets_the_attribute(self):
        provider = MockProvider("esa_copernicus").route(
            "/odata/v1/Products", MockEndpoint(json=PAGE)
        )
        source = build_source("esa_copernicus", transport=provider.transport)
        await source.search(
            SourceQuery(extra={"collection": "SENTINEL-2", "max_cloud_cover": 20})
        )
        sent = provider.last_params()["$filter"]
        assert "att/Name eq 'cloudCover'" in sent
        assert "le 20.0" in sent
        await source.aclose()

    async def test_product_type_filter(self):
        provider = MockProvider("esa_copernicus").route(
            "/odata/v1/Products", MockEndpoint(json=PAGE)
        )
        source = build_source("esa_copernicus", transport=provider.transport)
        await source.search(
            SourceQuery(extra={"collection": "SENTINEL-2", "product_type": "S2MSI2A"})
        )
        assert "'S2MSI2A'" in provider.last_params()["$filter"]
        await source.aclose()

    async def test_pagination_cursor_surfaced(self):
        provider = MockProvider("esa_copernicus").route(
            "/odata/v1/Products", MockEndpoint(json=PAGE)
        )
        source = build_source("esa_copernicus", transport=provider.transport)
        page = await source.search(SourceQuery(extra={"collection": "SENTINEL-2"}))
        assert page.next_cursor
        assert page.has_more
        await source.aclose()

    async def test_continuation_link_followed(self):
        follow = {"value": [PRODUCT], "@odata.nextLink": None}
        provider = MockProvider("esa_copernicus").route(
            "/odata/v1/Products", MockEndpoint(json=follow)
        )
        source = build_source("esa_copernicus", transport=provider.transport)
        page = await source.fetch_page(
            "https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$skip=2"
        )
        assert len(page.records) == 1
        assert page.next_cursor is None
        await source.aclose()

    async def test_foreign_continuation_link_refused(self):
        source = build_source("esa_copernicus")
        with pytest.raises(SourceResponseError, match="must point at"):
            await source.fetch_page("https://evil.test/odata/v1/Products")
        await source.aclose()

    async def test_offset_becomes_skip(self):
        provider = MockProvider("esa_copernicus").route(
            "/odata/v1/Products", MockEndpoint(json=PAGE)
        )
        source = build_source("esa_copernicus", transport=provider.transport)
        await source.search(SourceQuery(extra={"collection": "SENTINEL-2"}, offset=20))
        assert provider.last_params()["$skip"] == "20"
        await source.aclose()


class TestFailureModes:
    async def test_malformed_response_rejected(self):
        provider = MockProvider("esa_copernicus").route(
            "/odata/v1/Products", MockEndpoint(json={"unexpected": True})
        )
        source = build_source("esa_copernicus", transport=provider.transport)
        with pytest.raises(SourceResponseError, match="no 'value' array"):
            await source.search(SourceQuery(extra={"collection": "SENTINEL-2"}))
        await source.aclose()

    async def test_non_json_body_rejected(self):
        provider = MockProvider("esa_copernicus").route(
            "/odata/v1/Products", MockEndpoint(text="<html>gateway</html>")
        )
        source = build_source("esa_copernicus", transport=provider.transport)
        with pytest.raises(SourceResponseError, match="not valid JSON"):
            await source.search(SourceQuery(extra={"collection": "SENTINEL-2"}))
        await source.aclose()

    async def test_timeout_surfaces_as_timeout_error(self):
        provider = MockProvider("esa_copernicus").route(
            "/odata/v1/Products", MockEndpoint(raises=httpx.ReadTimeout("slow"))
        )
        source = build_source("esa_copernicus", transport=provider.transport)
        source.client._sleep = FakeSleeper()
        with pytest.raises(SourceTimeoutError):
            await source.search(SourceQuery(extra={"collection": "SENTINEL-2"}))
        await source.aclose()

    async def test_server_error_is_retried_then_raised(self):
        sleeper = FakeSleeper()
        provider = MockProvider("esa_copernicus").route(
            "/odata/v1/Products", MockEndpoint(status=503)
        )
        source = build_source("esa_copernicus", transport=provider.transport)
        source.client._sleep = sleeper
        with pytest.raises(SourceUnavailableError):
            await source.search(SourceQuery(extra={"collection": "SENTINEL-2"}))
        assert provider.call_count == 3
        await source.aclose()


class TestProductNormalization:
    def test_becomes_an_eo_product_not_a_space_object(self):
        product, _ = normalize_copernicus_product(product_record())
        assert isinstance(product, EOProduct)
        assert product.object_type is ObjectType.EO_PRODUCT

    def test_mission_platform_and_instrument_mapped(self):
        product, _ = normalize_copernicus_product(product_record())
        assert product.mission == "SENTINEL-2"
        assert product.platform == "SENTINEL-2B"
        assert product.instrument == "MSI"

    def test_processing_level_and_product_type(self):
        product, _ = normalize_copernicus_product(product_record())
        assert product.processing_level == "S2MSI2A"
        assert product.product_type == "S2MSI2A"
        assert product.processor_version == "05.12"

    def test_acquisition_time_mapped(self):
        product, _ = normalize_copernicus_product(product_record())
        assert product.acquisition_start is not None
        assert product.acquisition_start.year == 2026
        assert product.acquisition_start.tzinfo is not None
        assert product.published_at is not None

    def test_cloud_cover_is_a_percentage(self):
        product, _ = normalize_copernicus_product(product_record())
        assert product.cloud_cover.unit == "percent"
        assert product.cloud_cover.value == pytest.approx(64.217979)

    def test_impossible_cloud_cover_rejected(self):
        from pydantic import ValidationError

        payload = dict(PRODUCT)
        payload["Attributes"] = [
            {"Name": "cloudCover", "Value": 250.0, "ValueType": "Double"}
        ]
        with pytest.raises(ValidationError, match="outside"):
            normalize_copernicus_product(product_record(payload))

    def test_geometry_preserved(self):
        product, _ = normalize_copernicus_product(product_record())
        assert product.footprint is not None
        assert product.footprint.wkt
        assert product.footprint.srid == 4326

    def test_orbit_and_tile_metadata(self):
        product, _ = normalize_copernicus_product(product_record())
        assert product.absolute_orbit_number == 49331
        assert product.relative_orbit_number == 113
        assert product.tile_id == "10UGV"

    def test_access_url_has_no_credential(self):
        product, _ = normalize_copernicus_product(product_record())
        assert product.access_url.startswith("https://catalogue.dataspace.copernicus.eu")
        assert "api_key" not in product.access_url
        assert "token" not in product.access_url

    def test_access_status_says_credentials_are_needed(self):
        product, _ = normalize_copernicus_product(product_record())
        assert product.access_status is AccessStatus.CREDENTIALS_REQUIRED
        assert product.is_retrievable is False
        assert "requires an account" in product.access_explanation()

    def test_access_status_with_credentials(self):
        product, _ = normalize_copernicus_product(product_record(), has_credentials=True)
        assert product.access_status is AccessStatus.AUTHORIZED
        assert product.is_retrievable is True

    def test_offline_product_reported_as_offline(self):
        payload = dict(PRODUCT)
        payload["Online"] = False
        product, _ = normalize_copernicus_product(product_record(payload),
                                                  has_credentials=True)
        assert product.access_status is AccessStatus.OFFLINE
        assert "long-term storage" in product.access_explanation()

    def test_no_pixel_data_is_fetched(self):
        """Metadata-first: the record describes the product, it does not hold it."""
        product, _ = normalize_copernicus_product(product_record())
        assert product.content_length > 0
        assert "data" not in EOProduct.model_fields
        assert "raster" not in EOProduct.model_fields

    def test_unmapped_attributes_preserved(self):
        product, _ = normalize_copernicus_product(product_record())
        assert "datastripId" in product.attributes or "origin" in product.attributes

    def test_extract_attributes_flattens_the_array(self):
        attributes = extract_attributes(PRODUCT)
        assert attributes["platformShortName"] == "SENTINEL-2"
        assert attributes["cloudCover"] == pytest.approx(64.217979)

    def test_product_without_id_or_name_rejected(self):
        with pytest.raises(ValueError, match="neither Id nor Name"):
            normalize_copernicus_product(product_record({"Attributes": []}))

    def test_provenance_complete(self):
        product, lineage = normalize_copernicus_product(product_record())
        require_provenance(product, lineage)

    def test_lineage_records_the_access_decision(self):
        _, lineage = normalize_copernicus_product(product_record())
        assert "requires a Copernicus Data Space account" in lineage.explain_field(
            "access_status"
        )

    def test_roundtrips_through_json(self):
        product, _ = normalize_copernicus_product(product_record())
        assert EOProduct.model_validate_json(product.model_dump_json()) == product

    def test_freshness_anchors_on_acquisition(self):
        product, _ = normalize_copernicus_product(product_record())
        assert product.temporal_anchor() == product.acquisition_start


class TestCollectionAllowList:
    def test_expected_collections_present(self):
        assert "SENTINEL-1" in COLLECTIONS
        assert "SENTINEL-2" in COLLECTIONS

    def test_source_declares_it_is_not_an_orbital_source(self):
        info = build_source("esa_copernicus").get_source_info()
        assert "space objects or orbital elements" in info.does_not_provide
        assert info.source_type.value == "EO_CATALOGUE"


@live_only
class TestCopernicusLive:
    async def test_discovery_live(self):
        async with CopernicusSource() as source:
            page = await source.search(
                SourceQuery(
                    extra={"collection": "SENTINEL-2"},
                    start_time=datetime(2026, 8, 1, tzinfo=timezone.utc),
                    limit=2,
                )
            )
            assert page.records
            product, _ = normalize_copernicus_product(page.records[0])
            assert product.mission == "SENTINEL-2"
