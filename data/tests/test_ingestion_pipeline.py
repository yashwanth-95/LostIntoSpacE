"""Unified ingestion: a full multi-provider mock run, and failure isolation."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from data.entity_resolution import EntityResolver, MergeDecision, normalize_designation
from data.ingestion import (
    IngestionPipeline,
    IngestionReport,
    RecordStore,
    RejectionReason,
    SourcePlan,
    SourceStatus,
    build_plans,
)
from data.models import Asteroid, DocumentRecord, EOProduct, NaturalEvent, Planet, SpaceStation
from data.normalization.celestrak import normalize_gp_record
from data.normalization.esa import normalize_copernicus_product
from data.normalization.exoplanet import normalize_exoplanet_row
from data.normalization.jpl import normalize_sbdb_object
from data.normalization.mpc import normalize_mpc_orbit
from data.normalization.nasa import normalize_eonet_event, normalize_ntrs_citation
from data.sources import SourceQuery, build_source
from data.tests.mocks import MockEndpoint, MockProvider, load_fixture

CERES_SBDB = load_fixture("sbdb_ceres.json")
BENNU_SBDB = load_fixture("sbdb_bennu.json")
CERES_MPC = load_fixture("mpc_orb_ceres.json")
ISS = load_fixture("celestrak_iss.json")
EONET = load_fixture("eonet_events.json")
NTRS = load_fixture("ntrs_search.json")
EXOPLANET = load_fixture("exoplanet_pscomppars_kepler22b.json")
COPERNICUS = load_fixture("copernicus_sentinel2.json")

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def make_sources(**overrides):
    """Build every adapter against a scripted transport."""
    providers = {
        "jpl_sbdb": MockProvider("jpl_sbdb").route("/sbdb.api", MockEndpoint(json=CERES_SBDB)),
        "mpc_orbits": MockProvider("mpc_orbits").route(
            "/api/get-orb", MockEndpoint(json=CERES_MPC)
        ),
        "celestrak_gp": MockProvider("celestrak_gp").route(
            "/NORAD/elements/gp.php", MockEndpoint(json=ISS)
        ),
        "nasa_eonet": MockProvider("nasa_eonet").route("/events", MockEndpoint(json=EONET)),
        "nasa_ntrs": MockProvider("nasa_ntrs").route(
            "/citations/search", MockEndpoint(json=NTRS)
        ),
        "nasa_exoplanet_archive": MockProvider("nasa_exoplanet_archive").route(
            "/TAP/sync", MockEndpoint(json=EXOPLANET)
        ),
        "esa_copernicus": MockProvider("esa_copernicus").route(
            "/odata/v1/Products", MockEndpoint(json=COPERNICUS)
        ),
    }
    providers.update(overrides)
    sources = {
        name: build_source(name, transport=provider.transport)
        for name, provider in providers.items()
    }
    return sources, providers


def plans_for(names):
    return build_plans(small_bodies=["Ceres"], satellites=["25544"], enabled=names)


async def close_all(sources):
    for source in sources.values():
        await source.aclose()


class TestFullMockRun:
    async def test_multi_provider_run_produces_records_from_every_source(self):
        names = [
            "jpl_sbdb", "mpc_orbits", "celestrak_gp", "nasa_eonet",
            "nasa_ntrs", "nasa_exoplanet_archive", "esa_copernicus",
        ]
        sources, _ = make_sources()
        pipeline = IngestionPipeline(now=NOW)
        report = await pipeline.run(plans_for(names), sources, run_id="test-run")

        assert set(report.sources) == set(names)
        assert report.failed_sources == []
        assert report.records_seen >= 7
        assert report.created >= 7
        assert len(pipeline.store) >= 7
        await close_all(sources)

    async def test_records_of_every_expected_type_are_stored(self):
        names = [
            "jpl_sbdb", "celestrak_gp", "nasa_eonet", "nasa_ntrs",
            "nasa_exoplanet_archive", "esa_copernicus",
        ]
        sources, _ = make_sources()
        pipeline = IngestionPipeline(now=NOW)
        await pipeline.run(plans_for(names), sources)

        kinds = {type(record).__name__ for record in pipeline.store.all()}
        assert {"Asteroid", "SpaceStation", "NaturalEvent", "DocumentRecord",
                "Planet", "Star", "EOProduct"} <= kinds
        await close_all(sources)

    async def test_report_counts_per_source(self):
        sources, _ = make_sources()
        pipeline = IngestionPipeline(now=NOW)
        report = await pipeline.run(plans_for(["jpl_sbdb", "celestrak_gp"]), sources)

        assert report.sources["jpl_sbdb"].records_seen == 1
        assert report.sources["jpl_sbdb"].created == 1
        assert report.sources["celestrak_gp"].records_seen == 1
        assert report.sources["celestrak_gp"].status is SourceStatus.OK
        await close_all(sources)

    async def test_report_records_source_timestamps_and_retrieval(self):
        sources, _ = make_sources()
        pipeline = IngestionPipeline(now=NOW)
        report = await pipeline.run(plans_for(["celestrak_gp"]), sources)
        source_report = report.sources["celestrak_gp"]
        assert source_report.retrieved_at is not None
        assert source_report.source_timestamp is not None
        await close_all(sources)

    async def test_freshness_is_applied_and_counted(self):
        sources, _ = make_sources()
        pipeline = IngestionPipeline(now=NOW)
        report = await pipeline.run(plans_for(["celestrak_gp", "nasa_ntrs"]), sources)

        celestrak = report.sources["celestrak_gp"]
        assert celestrak.freshness_counts
        # The ISS fixture epoch is from 2026-08-18; at NOW it is a day old.
        assert sum(celestrak.freshness_counts.values()) == celestrak.records_seen
        await close_all(sources)

    async def test_static_sources_are_not_marked_live(self):
        sources, _ = make_sources()
        pipeline = IngestionPipeline(now=NOW)
        await pipeline.run(plans_for(["nasa_ntrs"]), sources)
        documents = [r for r in pipeline.store.all() if isinstance(r, DocumentRecord)]
        assert documents
        for document in documents:
            # A 1977 report is historical no matter when it was fetched.
            assert document.freshness_class.value == "HISTORICAL"
        await close_all(sources)

    async def test_every_stored_record_has_provenance(self):
        sources, _ = make_sources()
        pipeline = IngestionPipeline(now=NOW)
        await pipeline.run(
            plans_for(["jpl_sbdb", "celestrak_gp", "nasa_eonet"]), sources
        )
        for record in pipeline.store.all():
            assert record.has_provenance
            assert record.source_references
        await close_all(sources)

    async def test_lineage_is_retained_per_record(self):
        sources, _ = make_sources()
        pipeline = IngestionPipeline(now=NOW)
        await pipeline.run(plans_for(["jpl_sbdb"]), sources)
        asteroid = [r for r in pipeline.store.all() if isinstance(r, Asteroid)][0]
        lineage = pipeline.store.lineage_for(asteroid.canonical_id)
        assert lineage is not None
        assert lineage.has_origin()
        await close_all(sources)

    async def test_report_summary_is_readable(self):
        sources, _ = make_sources()
        pipeline = IngestionPipeline(now=NOW)
        report = await pipeline.run(plans_for(["jpl_sbdb", "celestrak_gp"]), sources)
        summary = report.summary()
        assert "jpl_sbdb" in summary
        assert "created" in summary
        await close_all(sources)

    async def test_sequential_run_matches_concurrent_run(self):
        names = ["jpl_sbdb", "celestrak_gp", "nasa_eonet"]
        sources_a, _ = make_sources()
        sources_b, _ = make_sources()
        concurrent = await IngestionPipeline(now=NOW).run(plans_for(names), sources_a)
        sequential = await IngestionPipeline(now=NOW).run(
            plans_for(names), sources_b, concurrent=False
        )
        assert concurrent.created == sequential.created
        assert concurrent.records_seen == sequential.records_seen
        await close_all(sources_a)
        await close_all(sources_b)


class TestFailureIsolation:
    async def test_one_failing_provider_does_not_break_the_others(self):
        broken = MockProvider("nasa_eonet").route(
            "/events", MockEndpoint(raises=httpx.ConnectError("refused"))
        )
        sources, _ = make_sources(nasa_eonet=broken)
        sources["nasa_eonet"].client._sleep = _no_sleep
        pipeline = IngestionPipeline(now=NOW)
        report = await pipeline.run(
            plans_for(["jpl_sbdb", "nasa_eonet", "celestrak_gp"]), sources
        )

        assert report.failed_sources == ["nasa_eonet"]
        assert report.sources["jpl_sbdb"].status is SourceStatus.OK
        assert report.sources["celestrak_gp"].status is SourceStatus.OK
        assert report.created >= 2
        assert not report.all_failed
        await close_all(sources)

    async def test_failed_source_records_the_error(self):
        broken = MockProvider("nasa_eonet").route("/events", MockEndpoint(status=503))
        sources, _ = make_sources(nasa_eonet=broken)
        sources["nasa_eonet"].client._sleep = _no_sleep
        pipeline = IngestionPipeline(now=NOW)
        report = await pipeline.run(plans_for(["nasa_eonet", "jpl_sbdb"]), sources)

        assert report.sources["nasa_eonet"].errors
        assert "503" in report.sources["nasa_eonet"].errors[0]
        await close_all(sources)

    async def test_auth_failure_is_isolated_too(self):
        broken = MockProvider("nasa_ntrs").route(
            "/citations/search", MockEndpoint(status=401)
        )
        sources, _ = make_sources(nasa_ntrs=broken)
        pipeline = IngestionPipeline(now=NOW)
        report = await pipeline.run(plans_for(["nasa_ntrs", "jpl_sbdb"]), sources)
        assert report.sources["nasa_ntrs"].status is SourceStatus.FAILED
        assert report.sources["jpl_sbdb"].created == 1
        await close_all(sources)

    async def test_every_provider_failing_is_reported_as_such(self):
        providers = {
            name: MockProvider(name).route("/", MockEndpoint(status=500))
            for name in ("jpl_sbdb", "celestrak_gp")
        }
        sources = {
            name: build_source(name, transport=provider.transport)
            for name, provider in providers.items()
        }
        for source in sources.values():
            source.client._sleep = _no_sleep
        report = await IngestionPipeline(now=NOW).run(
            plans_for(["jpl_sbdb", "celestrak_gp"]), sources
        )
        assert report.all_failed
        assert sorted(report.failed_sources) == ["celestrak_gp", "jpl_sbdb"]
        await close_all(sources)

    async def test_a_bad_record_rejects_only_that_record(self):
        def normalize(raw):
            if raw.source_record_id == "bad":
                raise ValueError("this record is unusable")
            return normalize_gp_record(raw)

        rows = [dict(ISS[0]), dict(ISS[0], NORAD_CAT_ID=99999, OBJECT_NAME="OTHER")]
        provider = MockProvider("celestrak_gp").route(
            "/NORAD/elements/gp.php", MockEndpoint(json=rows)
        )
        source = build_source("celestrak_gp", transport=provider.transport)

        async def fetch(src):
            page = await src.search(SourceQuery(text="ISS"))
            records = list(page.records)
            records[0].source_record_id = "bad"
            return records

        plan = SourcePlan(source_name="celestrak_gp", fetch=fetch, normalize=normalize)
        pipeline = IngestionPipeline(now=NOW)
        report = await pipeline.run([plan], {"celestrak_gp": source})

        source_report = report.sources["celestrak_gp"]
        assert source_report.records_seen == 2
        assert source_report.created == 1
        assert source_report.rejected_count == 1
        assert source_report.rejected[0].reason is RejectionReason.NORMALIZATION_ERROR
        assert source_report.status is SourceStatus.PARTIAL
        await source.aclose()

    async def test_rejection_records_the_reason_and_excerpt(self):
        def normalize(raw):
            raise ValueError("boom")

        provider = MockProvider("celestrak_gp").route(
            "/NORAD/elements/gp.php", MockEndpoint(json=ISS)
        )
        source = build_source("celestrak_gp", transport=provider.transport)

        async def fetch(src):
            return [await src.fetch_by_id("25544")]

        report = await IngestionPipeline(now=NOW).run(
            [SourcePlan(source_name="celestrak_gp", fetch=fetch, normalize=normalize)],
            {"celestrak_gp": source},
        )
        rejected = report.sources["celestrak_gp"].rejected[0]
        assert "boom" in rejected.detail
        assert rejected.payload_excerpt
        await source.aclose()

    async def test_record_without_provenance_is_rejected(self):
        def normalize(raw):
            asteroid, lineage = normalize_sbdb_object(raw)
            asteroid.source_references = []
            return asteroid, lineage

        provider = MockProvider("jpl_sbdb").route("/sbdb.api", MockEndpoint(json=CERES_SBDB))
        source = build_source("jpl_sbdb", transport=provider.transport)

        async def fetch(src):
            return [await src.fetch_by_id("Ceres")]

        report = await IngestionPipeline(now=NOW).run(
            [SourcePlan(source_name="jpl_sbdb", fetch=fetch, normalize=normalize)],
            {"jpl_sbdb": source},
        )
        rejected = report.sources["jpl_sbdb"].rejected[0]
        assert rejected.reason is RejectionReason.MISSING_PROVENANCE
        await source.aclose()

    async def test_missing_adapter_is_skipped_not_failed(self):
        report = await IngestionPipeline(now=NOW).run(plans_for(["jpl_sbdb"]), {})
        assert report.sources["jpl_sbdb"].status is SourceStatus.SKIPPED
        assert "no adapter supplied" in report.sources["jpl_sbdb"].errors[0]

    async def test_disabled_source_is_skipped_with_a_reason(self):
        plans = build_plans(enabled=["isro_bhoonidhi"], bhoonidhi_authorized=False)
        report = await IngestionPipeline(now=NOW).run(plans, {})
        source_report = report.sources["isro_bhoonidhi"]
        assert source_report.status is SourceStatus.SKIPPED
        assert "bhoonidhi@nrsc.gov.in" in source_report.errors[0]
        assert not report.all_failed


class TestEntityResolution:
    def test_designation_normalization(self):
        assert normalize_designation("2024 YR4") == "2024yr4"
        assert normalize_designation("2024YR4") == "2024yr4"
        assert normalize_designation("  A801 AA ") == "a801aa"
        assert normalize_designation(None) is None

    def test_new_entity_when_nothing_matches(self):
        resolver = EntityResolver()
        asteroid = Asteroid(canonical_id="asteroid:1", name="1 Ceres", spk_id="20000001")
        outcome = resolver.resolve(asteroid)
        assert outcome.decision is MergeDecision.NEW

    def test_strong_identifier_merges_across_sources(self):
        resolver = EntityResolver()
        first = Asteroid(canonical_id="asteroid:1", name="1 Ceres", spk_id="20000001")
        resolver.register(first, resolver.resolve(first))

        # Same object, different canonical id, same SPK-ID.
        second = Asteroid(canonical_id="asteroid:ceres", name="Ceres", spk_id="20000001")
        outcome = resolver.resolve(second)
        assert outcome.decision is MergeDecision.MERGED
        assert outcome.merged_into == "asteroid:1"

    def test_name_only_match_is_a_candidate_not_a_merge(self):
        """Two different objects can share a name; merging on it is unsafe."""
        resolver = EntityResolver()
        moon = Asteroid(canonical_id="asteroid:52", name="Europa", spk_id="20000052")
        resolver.register(moon, resolver.resolve(moon))

        other = Asteroid(canonical_id="moon:europa", name="Europa", spk_id="502")
        outcome = resolver.resolve(other)
        assert outcome.decision is MergeDecision.CANDIDATE
        assert "asteroid:52" in outcome.conflicting_ids

    def test_conflicting_strong_identifiers_are_refused(self):
        resolver = EntityResolver()
        first = Asteroid(canonical_id="asteroid:a", name="A", spk_id="1")
        second = Asteroid(canonical_id="asteroid:b", name="B", packed_designation="X1")
        resolver.register(first, resolver.resolve(first))
        resolver.register(second, resolver.resolve(second))

        # A record asserting both identifiers points at two known entities.
        merged = Asteroid(
            canonical_id="asteroid:c", name="C", spk_id="1", packed_designation="X1"
        )
        outcome = resolver.resolve(merged)
        assert outcome.decision is MergeDecision.CONFLICT
        assert sorted(outcome.conflicting_ids) == ["asteroid:a", "asteroid:b"]

    def test_norad_and_asteroid_numbers_do_not_collide(self):
        resolver = EntityResolver()
        station = SpaceStation(
            canonical_id="space-station:25544", name="ISS", norad_cat_id=25544
        )
        resolver.register(station, resolver.resolve(station))
        asteroid = Asteroid(
            canonical_id="asteroid:25544", name="25544 Test", designation="25544"
        )
        assert resolver.resolve(asteroid).decision is MergeDecision.NEW

    def test_source_record_mapping_is_recorded(self):
        resolver = EntityResolver()
        asteroid = Asteroid(canonical_id="asteroid:1", name="1 Ceres", spk_id="20000001")
        resolver.register(
            asteroid, resolver.resolve(asteroid),
            source_name="jpl_sbdb", source_record_id="20000001",
        )
        assert resolver.canonical_id_for("jpl_sbdb", "20000001") == "asteroid:1"
        assert resolver.canonical_id_for("mpc_orbits", "1") is None

    async def test_conflict_is_reported_and_the_record_rejected(self):
        """Ceres' SPK-ID and its designation already point at different entities.

        A registry in this state is inconsistent, and the incoming record is the
        thing that reveals it. Refusing to pick one is the correct response.
        """
        resolver = EntityResolver()
        first = Asteroid(canonical_id="asteroid:x", name="X", spk_id="20000001")
        second = Asteroid(canonical_id="asteroid:y", name="Y", designation="1")
        resolver.register(first, resolver.resolve(first))
        resolver.register(second, resolver.resolve(second))

        sources, _ = make_sources()
        pipeline = IngestionPipeline(resolver=resolver, now=NOW)
        report = await pipeline.run(plans_for(["jpl_sbdb"]), sources)

        source_report = report.sources["jpl_sbdb"]
        assert source_report.conflicts
        assert source_report.rejected[0].reason is RejectionReason.ENTITY_CONFLICT
        await close_all(sources)

    async def test_same_object_from_two_sources_resolves_to_one_entity(self):
        """JPL and the MPC both describe Ceres; the run keeps one entity."""
        sources, _ = make_sources()
        pipeline = IngestionPipeline(now=NOW)
        report = await pipeline.run(plans_for(["jpl_sbdb", "mpc_orbits"]), sources)

        assert report.failed_sources == []
        asteroids = [r for r in pipeline.store.all() if isinstance(r, Asteroid)]
        assert len(asteroids) == 1
        assert pipeline.resolver.entity_count >= 1
        await close_all(sources)


class TestStore:
    def test_put_reports_new_then_replaced(self):
        store = RecordStore()
        asteroid = Asteroid(canonical_id="asteroid:1", name="Ceres")
        assert store.put(asteroid) is True
        assert store.put(asteroid) is False
        assert len(store) == 1
        assert "asteroid:1" in store

    def test_get_returns_none_for_unknown(self):
        assert RecordStore().get("asteroid:none") is None


async def _no_sleep(seconds):
    """Skip retry backoff in tests."""
    return None
