"""NASA integration: NeoWs, EONET v3 and NTRS.

All tests run against responses recorded from the live endpoints
(`data/tests/fixtures/`). Live tests are opt-in via `LOSTINTOSPACE_LIVE_TESTS=1`.
"""

import os
from datetime import datetime, timezone

import httpx
import pytest

from data.models import Asteroid, DocumentRecord, NaturalEvent, ObjectType
from data.normalization.nasa import (
    normalize_eonet_event,
    normalize_ntrs_citation,
    normalize_neows_object,
)
from data.provenance import POLICIES, apply_freshness, require_provenance
from data.sources import (
    Capability,
    NasaEonetSource,
    NasaNeoWsSource,
    NasaNtrsSource,
    SourceNotFoundError,
    SourceQuery,
    SourceResponseError,
    build_source,
)
from data.tests.mocks import MockEndpoint, MockProvider, load_fixture

LIVE = os.environ.get("LOSTINTOSPACE_LIVE_TESTS") == "1"
live_only = pytest.mark.skipif(not LIVE, reason="set LOSTINTOSPACE_LIVE_TESTS=1 to run")

EROS = load_fixture("neows_eros.json")
EONET_EVENTS = load_fixture("eonet_events.json")
EONET_CATEGORIES = load_fixture("eonet_categories.json")
NTRS_SEARCH = load_fixture("ntrs_search.json")


def neows(**routes) -> NasaNeoWsSource:
    provider = MockProvider("nasa_neows")
    for path, endpoint in routes.items():
        provider.route(path.replace("__", "/"), endpoint)
    source = build_source("nasa_neows", transport=provider.transport)
    source._mock = provider
    return source


class TestNeoWsFetch:
    async def test_lookup_returns_source_record_with_provenance(self):
        provider = MockProvider("nasa_neows").route(
            "/neo/rest/v1/neo/2000433", MockEndpoint(json=EROS)
        )
        source = build_source("nasa_neows", transport=provider.transport)
        record = await source.fetch_by_id("2000433")
        assert record.source_record_id == "2000433"
        assert record.source_reference.source_name == "nasa_neows"
        assert record.source_reference.source_type.value == "AGENCY_PUBLIC_API"
        assert record.payload["name"].startswith("433 Eros")
        await source.aclose()

    async def test_api_key_is_sent_and_never_persisted(self, monkeypatch):
        monkeypatch.setenv("NASA_API_KEY", "SECRET-KEY-123")
        provider = MockProvider("nasa_neows").route(
            "/neo/rest/v1/neo/2000433", MockEndpoint(json=EROS)
        )
        source = build_source("nasa_neows", transport=provider.transport)
        record = await source.fetch_by_id("2000433")
        assert provider.last_params()["api_key"] == "SECRET-KEY-123"
        assert "SECRET-KEY-123" not in record.source_reference.source_url
        assert "SECRET-KEY-123" not in record.model_dump_json()
        await source.aclose()

    async def test_missing_object_raises_not_found(self):
        provider = MockProvider("nasa_neows").route(
            "/neo/rest/v1/neo/999999", MockEndpoint(status=404, json={"code": 404})
        )
        source = build_source("nasa_neows", transport=provider.transport)
        with pytest.raises(SourceNotFoundError):
            await source.fetch_by_id("999999")
        await source.aclose()

    async def test_empty_identifier_rejected(self):
        source = build_source("nasa_neows")
        with pytest.raises(SourceResponseError, match="needs an identifier"):
            await source.fetch_by_id("   ")
        await source.aclose()

    async def test_unexpected_payload_shape_rejected(self):
        provider = MockProvider("nasa_neows").route(
            "/neo/rest/v1/neo/2000433", MockEndpoint(json={"unexpected": True})
        )
        source = build_source("nasa_neows", transport=provider.transport)
        with pytest.raises(SourceResponseError, match="unexpected payload shape"):
            await source.fetch_by_id("2000433")
        await source.aclose()

    async def test_quota_headers_are_observed(self):
        provider = MockProvider("nasa_neows").route(
            "/neo/rest/v1/neo/2000433",
            MockEndpoint(
                json=EROS,
                headers={"X-RateLimit-Limit": "1000", "X-RateLimit-Remaining": "42"},
            ),
        )
        source = build_source("nasa_neows", transport=provider.transport)
        await source.fetch_by_id("2000433")
        assert source.client.limiter.quota.remaining == 42
        await source.aclose()


class TestNeoWsSearch:
    async def test_browse_when_no_date_window(self):
        provider = MockProvider("nasa_neows").route(
            "/neo/rest/v1/neo/browse",
            MockEndpoint(
                json={
                    "near_earth_objects": [EROS],
                    "page": {"total_elements": 35000, "size": 20, "number": 0},
                }
            ),
        )
        source = build_source("nasa_neows", transport=provider.transport)
        page = await source.search(SourceQuery(object_type="asteroid", limit=20))
        assert len(page.records) == 1
        assert page.total_available == 35000
        assert "object_type" in " ".join(page.unsupported_filters)
        await source.aclose()

    async def test_feed_used_when_a_date_window_is_given(self):
        provider = MockProvider("nasa_neows").route(
            "/neo/rest/v1/feed",
            MockEndpoint(json={"element_count": 2, "near_earth_objects": {"2026-08-18": [EROS]}}),
        )
        source = build_source("nasa_neows", transport=provider.transport)
        page = await source.search(
            SourceQuery(
                start_time=datetime(2026, 8, 18, tzinfo=timezone.utc),
                end_time=datetime(2026, 8, 20, tzinfo=timezone.utc),
            )
        )
        assert provider.last_params()["start_date"] == "2026-08-18"
        assert provider.last_params()["end_date"] == "2026-08-20"
        assert len(page.records) == 1
        await source.aclose()

    async def test_window_longer_than_seven_days_rejected(self):
        """NASA caps the feed at seven days; failing loudly beats a silent truncation."""
        source = build_source("nasa_neows")
        with pytest.raises(SourceResponseError, match="at most a 7-day range"):
            await source.search(
                SourceQuery(
                    start_time=datetime(2026, 8, 1, tzinfo=timezone.utc),
                    end_time=datetime(2026, 9, 1, tzinfo=timezone.utc),
                )
            )
        await source.aclose()

    async def test_text_search_is_reported_as_unsupported(self):
        provider = MockProvider("nasa_neows").route(
            "/neo/rest/v1/neo/browse",
            MockEndpoint(json={"near_earth_objects": [], "page": {"total_elements": 0}}),
        )
        source = build_source("nasa_neows", transport=provider.transport)
        page = await source.search(SourceQuery(text="eros"))
        assert any("text" in item for item in page.unsupported_filters)
        await source.aclose()


class TestNeoWsNormalization:
    def _normalize(self):
        provider = MockProvider("nasa_neows")
        source = build_source("nasa_neows", transport=provider.transport)
        reference = source.build_source_reference(record_id="2000433")
        from data.sources.base import SourceRecord

        record = SourceRecord(
            source_name="nasa_neows",
            source_record_id="2000433",
            payload=EROS,
            source_reference=reference,
        )
        return normalize_neows_object(record)

    def test_produces_an_asteroid_not_a_generic_object(self):
        asteroid, _ = self._normalize()
        assert isinstance(asteroid, Asteroid)
        assert asteroid.object_type is ObjectType.ASTEROID
        assert asteroid.canonical_id == "asteroid:433"
        assert asteroid.name == "433 Eros (A898 PA)"

    def test_diameter_range_becomes_midpoint_with_uncertainty(self):
        asteroid, _ = self._normalize()
        diameter = asteroid.physical.diameter
        assert diameter.unit == "km"
        # Fixture range is 22.108 - 49.436 km.
        assert diameter.value == pytest.approx(35.77, abs=0.05)
        assert diameter.uncertainty == pytest.approx(13.66, abs=0.05)

    def test_absolute_magnitude_uses_magnitude_dimension(self):
        asteroid, _ = self._normalize()
        assert asteroid.physical.absolute_magnitude.unit == "mag"
        assert asteroid.physical.absolute_magnitude.value == pytest.approx(10.4)

    def test_orbit_records_frame_and_theory_explicitly(self):
        asteroid, _ = self._normalize()
        orbit = asteroid.orbits[0]
        assert orbit.frame.origin_type.value == "HELIOCENTRIC"
        assert orbit.frame.center_body == "sun"
        assert orbit.frame.time_scale.value == "TDB"
        assert orbit.element_theory.value == "OSCULATING_KEPLERIAN"
        assert orbit.elements.eccentricity.value == pytest.approx(0.2229, abs=1e-3)

    def test_orbit_epoch_converted_from_julian_date(self):
        asteroid, _ = self._normalize()
        orbit = asteroid.orbits[0]
        assert orbit.epoch.tzinfo is not None
        assert 2000 < orbit.epoch.year < 2100

    def test_orbit_fit_metadata_preserved(self):
        asteroid, _ = self._normalize()
        fit = asteroid.orbits[0].fit
        assert fit.observations_used > 0
        assert fit.first_observation < fit.last_observation

    def test_every_quantity_carries_its_source(self):
        asteroid, _ = self._normalize()
        assert asteroid.physical.diameter.source.source_name == "nasa_neows"
        assert asteroid.orbits[0].elements.inclination.source.source_name == "nasa_neows"

    def test_lineage_records_the_conversions(self):
        _, lineage = self._normalize()
        assert lineage.has_origin()
        assert "physical.diameter" in [
            step.output for step in lineage.steps if step.output
        ]
        explanation = lineage.explain_field("orbits[0].epoch")
        assert "JD -> UTC" in explanation

    def test_provenance_requirement_satisfied(self):
        asteroid, lineage = self._normalize()
        require_provenance(asteroid, lineage)

    def test_neows_is_not_the_orbital_authority(self):
        """NeoWs republishes JPL, so it must not outrank SBDB later."""
        asteroid, _ = self._normalize()
        assert asteroid.orbits[0].primary_source.source_type.value == "AGENCY_PUBLIC_API"


class TestEonet:
    async def test_search_returns_events(self):
        provider = MockProvider("nasa_eonet").route(
            "/events", MockEndpoint(json=EONET_EVENTS)
        )
        source = build_source("nasa_eonet", transport=provider.transport)
        page = await source.search(SourceQuery(text=None, extra={"status": "open"}, limit=2))
        assert len(page.records) == 2
        assert page.records[0].source_record_id.startswith("EONET_")
        assert provider.last_params()["status"] == "open"
        await source.aclose()

    async def test_text_filter_applied_client_side_and_declared(self):
        provider = MockProvider("nasa_eonet").route(
            "/events", MockEndpoint(json=EONET_EVENTS)
        )
        source = build_source("nasa_eonet", transport=provider.transport)
        page = await source.search(SourceQuery(text="Chaves"))
        assert len(page.records) == 1
        assert any("client-side" in item for item in page.unsupported_filters)
        await source.aclose()

    async def test_missing_events_array_raises(self):
        provider = MockProvider("nasa_eonet").route("/events", MockEndpoint(json={"x": 1}))
        source = build_source("nasa_eonet", transport=provider.transport)
        with pytest.raises(SourceResponseError, match="no 'events' array"):
            await source.search(SourceQuery(text="fire"))
        await source.aclose()

    async def test_categories_endpoint(self):
        provider = MockProvider("nasa_eonet").route(
            "/categories", MockEndpoint(json=EONET_CATEGORIES)
        )
        source = build_source("nasa_eonet", transport=provider.transport)
        categories = await source.categories()
        assert {"wildfires", "volcanoes", "severeStorms"} <= {c["id"] for c in categories}
        await source.aclose()

    async def test_source_timestamp_is_the_latest_observation(self):
        provider = MockProvider("nasa_eonet").route(
            "/events", MockEndpoint(json=EONET_EVENTS)
        )
        source = build_source("nasa_eonet", transport=provider.transport)
        page = await source.search(SourceQuery(extra={"status": "open"}))
        assert page.records[0].source_reference.source_timestamp is not None
        await source.aclose()

    def _normalize_first(self):
        from data.sources.base import SourceRecord

        source = build_source("nasa_eonet")
        payload = EONET_EVENTS["events"][0]
        record = SourceRecord(
            source_name="nasa_eonet",
            source_record_id=payload["id"],
            payload=payload,
            source_reference=source.build_source_reference(record_id=payload["id"]),
        )
        return normalize_eonet_event(record)

    def test_event_becomes_a_natural_event_not_a_space_object(self):
        event, _ = self._normalize_first()
        assert isinstance(event, NaturalEvent)
        assert event.object_type is ObjectType.NATURAL_EVENT
        assert not hasattr(event, "physical")

    def test_geometry_and_magnitude_preserved(self):
        event, _ = self._normalize_first()
        geometry = event.geometries[0]
        assert geometry.geometry_type == "Point"
        assert geometry.latitude == pytest.approx(43.00919)
        assert geometry.longitude == pytest.approx(-120.774487)
        assert geometry.magnitude.value == pytest.approx(1625.0)
        assert geometry.magnitude_unit_label == "acres"

    def test_reporting_agency_credited_alongside_eonet(self):
        event, _ = self._normalize_first()
        assert event.event_sources[0].id == "IRWIN"
        assert event.source_references[0].source_name == "nasa_eonet"

    def test_open_event_has_no_close_date(self):
        event, _ = self._normalize_first()
        assert event.is_open
        assert event.closed_at is None

    def test_freshness_uses_the_observation_time_not_the_fetch_time(self):
        """An old event served by a live feed is still an old event."""
        event, _ = self._normalize_first()
        event.retrieved_at = datetime(2030, 1, 1, tzinfo=timezone.utc)
        assessment = apply_freshness(
            event, POLICIES["nasa_eonet"], now=datetime(2030, 1, 1, tzinfo=timezone.utc)
        )
        assert assessment.freshness_class.value == "HISTORICAL"
        assert assessment.may_present_as_live is False


class TestNtrs:
    async def test_search_returns_citations(self):
        provider = MockProvider("nasa_ntrs").route(
            "/citations/search", MockEndpoint(json=NTRS_SEARCH)
        )
        source = build_source("nasa_ntrs", transport=provider.transport)
        page = await source.search(SourceQuery(text="max-q launch vehicle", limit=1))
        assert len(page.records) == 1
        assert page.total_available == NTRS_SEARCH["stats"]["total"]
        assert provider.last_params()["q"] == "max-q launch vehicle"
        assert provider.last_params()["page.size"] == "1"
        await source.aclose()

    async def test_empty_result_is_not_an_error(self):
        provider = MockProvider("nasa_ntrs").route(
            "/citations/search",
            MockEndpoint(json={"stats": {"total": 0}, "results": [], "aggregations": {}}),
        )
        source = build_source("nasa_ntrs", transport=provider.transport)
        page = await source.search(SourceQuery(text="zzzznonexistent"))
        assert page.records == []
        assert page.total_available == 0
        await source.aclose()

    async def test_search_without_text_rejected(self):
        source = build_source("nasa_ntrs")
        with pytest.raises(SourceResponseError, match="needs query text"):
            await source.search(SourceQuery(identifier="19770021237"))
        await source.aclose()

    async def test_offset_uses_ntrs_paging_parameter(self):
        provider = MockProvider("nasa_ntrs").route(
            "/citations/search", MockEndpoint(json=NTRS_SEARCH)
        )
        source = build_source("nasa_ntrs", transport=provider.transport)
        await source.search(SourceQuery(text="apollo", limit=10, offset=20))
        assert provider.last_params()["page.from"] == "20"
        await source.aclose()

    async def test_timeout_surfaces_as_timeout_error(self):
        from data.sources import SourceTimeoutError
        from data.tests.mocks import FakeSleeper

        provider = MockProvider("nasa_ntrs").route(
            "/citations/search", MockEndpoint(raises=httpx.ReadTimeout("slow"))
        )
        source = build_source("nasa_ntrs", transport=provider.transport)
        source.client._sleep = FakeSleeper()
        with pytest.raises(SourceTimeoutError):
            await source.search(SourceQuery(text="apollo"))
        await source.aclose()

    def _normalize_first(self):
        from data.sources.base import SourceRecord

        source = build_source("nasa_ntrs")
        payload = NTRS_SEARCH["results"][0]
        record = SourceRecord(
            source_name="nasa_ntrs",
            source_record_id=str(payload["id"]),
            payload=payload,
            source_reference=source.build_source_reference(record_id=str(payload["id"])),
        )
        return normalize_ntrs_citation(record)

    def test_citation_becomes_a_document_not_a_space_object(self):
        document, _ = self._normalize_first()
        assert isinstance(document, DocumentRecord)
        assert document.object_type is ObjectType.DOCUMENT

    def test_metadata_fields_mapped(self):
        document, _ = self._normalize_first()
        assert document.name
        assert document.abstract
        assert document.author_names
        assert document.publication_date is not None
        assert document.subject_categories

    def test_identifiers_include_report_numbers(self):
        document, _ = self._normalize_first()
        assert any("NASA-CR" in identifier for identifier in document.identifiers)

    def test_citation_text_is_renderable(self):
        document, _ = self._normalize_first()
        citation = document.citation_text()
        assert document.name in citation
        assert str(document.publication_date.year) in citation

    def test_full_text_permitted_only_when_the_source_says_so(self):
        document, _ = self._normalize_first()
        assert document.copyright_determination == "GOV_PUBLIC_USE_PERMITTED"
        assert document.may_index_full_text is True

    def test_restricted_copyright_blocks_full_text(self):
        from data.sources.base import SourceRecord

        payload = dict(NTRS_SEARCH["results"][0])
        payload["copyright"] = {"determinationType": "COPYRIGHTED"}
        source = build_source("nasa_ntrs")
        record = SourceRecord(
            source_name="nasa_ntrs",
            source_record_id=str(payload["id"]),
            payload=payload,
            source_reference=source.build_source_reference(),
        )
        document, _ = normalize_ntrs_citation(record)
        assert document.may_index_full_text is False

    def test_document_freshness_anchors_on_publication(self):
        document, _ = self._normalize_first()
        assert document.temporal_anchor().year == document.publication_date.year


class TestNasaCapabilityBoundaries:
    def test_apod_is_not_a_space_object_source(self):
        info = build_source("nasa_apod").get_source_info()
        assert Capability.PHYSICAL_PARAMETERS not in info.capabilities
        assert "any structured record about a specific body" in info.does_not_provide

    def test_eonet_does_not_claim_orbital_data(self):
        info = build_source("nasa_eonet").get_source_info()
        assert Capability.ORBITAL_ELEMENTS not in info.capabilities
        assert "orbital data" in info.does_not_provide

    def test_ntrs_does_not_claim_scientific_records(self):
        info = build_source("nasa_ntrs").get_source_info()
        assert Capability.PHYSICAL_PARAMETERS not in info.capabilities

    def test_implemented_sources_are_flagged(self):
        for name in ("nasa_neows", "nasa_eonet", "nasa_ntrs"):
            assert build_source(name).get_source_info().implemented is True


@live_only
class TestNasaLive:
    """Opt-in checks against the real endpoints. Never run in the default suite."""

    async def test_eonet_categories_live(self):
        async with NasaEonetSource() as source:
            categories = await source.categories()
            assert any(item["id"] == "wildfires" for item in categories)

    async def test_ntrs_search_live(self):
        async with NasaNtrsSource() as source:
            page = await source.search(SourceQuery(text="apollo guidance computer", limit=2))
            assert page.records

    async def test_neows_lookup_live(self):
        async with NasaNeoWsSource() as source:
            record = await source.fetch_by_id("2000433")
            assert record.payload["name"].startswith("433 Eros")
