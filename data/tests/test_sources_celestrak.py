"""CelesTrak GP/OMM integration: the ISS and a sample constellation."""

import os
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from data.models import (
    CoordinateSystem,
    ElementTheory,
    ObjectType,
    OrbitRecord,
    OrbitRegime,
    OriginType,
    ReferenceFrame,
    Satellite,
    SpaceStation,
    TimeScale,
)
from data.normalization.celestrak import classify_regime, normalize_gp_record
from data.provenance import POLICIES, apply_freshness, require_provenance
from data.sources import (
    CelestrakSource,
    SourceNotFoundError,
    SourceQuery,
    SourceResponseError,
    build_source,
)
from data.sources.base import SourceRecord
from data.sources.celestrak import PROVENANCE_LABEL
from data.tests.mocks import MockEndpoint, MockProvider, load_fixture

LIVE = os.environ.get("LOSTINTOSPACE_LIVE_TESTS") == "1"
live_only = pytest.mark.skipif(not LIVE, reason="set LOSTINTOSPACE_LIVE_TESTS=1 to run")

ISS = load_fixture("celestrak_iss.json")
GPS = load_fixture("celestrak_gps_ops.json")


def gp_record(row) -> SourceRecord:
    source = build_source("celestrak_gp")
    return SourceRecord(
        source_name="celestrak_gp",
        source_record_id=str(row["NORAD_CAT_ID"]),
        payload=row,
        source_reference=source.build_source_reference(
            record_id=str(row["NORAD_CAT_ID"])
        ),
    )


class TestCelestrakAdapter:
    async def test_iss_lookup_by_catalog_number(self):
        provider = MockProvider("celestrak_gp").route(
            "/NORAD/elements/gp.php", MockEndpoint(json=ISS)
        )
        source = build_source("celestrak_gp", transport=provider.transport)
        record = await source.fetch_by_id("25544")
        assert provider.last_params()["CATNR"] == "25544"
        assert provider.last_params()["FORMAT"] == "JSON"
        assert record.payload["OBJECT_NAME"] == "ISS (ZARYA)"
        await source.aclose()

    async def test_non_numeric_catalog_number_rejected(self):
        source = build_source("celestrak_gp")
        with pytest.raises(SourceResponseError, match="numeric NORAD catalog number"):
            await source.fetch_by_id("ISS")
        await source.aclose()

    async def test_no_gp_data_notice_becomes_not_found(self):
        """CelesTrak answers a miss with plain text and a 200."""
        provider = MockProvider("celestrak_gp").route(
            "/NORAD/elements/gp.php", MockEndpoint(text="No GP data found")
        )
        source = build_source("celestrak_gp", transport=provider.transport)
        with pytest.raises(SourceNotFoundError, match="no GP data"):
            await source.fetch_by_id("99999999")
        await source.aclose()

    async def test_constellation_group_fetch(self):
        provider = MockProvider("celestrak_gp").route(
            "/NORAD/elements/gp.php", MockEndpoint(json=GPS)
        )
        source = build_source("celestrak_gp", transport=provider.transport)
        page = await source.fetch_group("gps-ops")
        assert provider.last_params()["GROUP"] == "gps-ops"
        assert len(page.records) == 3
        assert all("GPS" in r.payload["OBJECT_NAME"] for r in page.records)
        await source.aclose()

    async def test_whole_catalogue_pull_is_refused(self):
        """CelesTrak asks users to retrieve only what they need."""
        source = build_source("celestrak_gp")
        with pytest.raises(SourceResponseError, match="whole-catalogue pulls are refused"):
            await source.search(SourceQuery(extra={"unrelated": 1}))
        await source.aclose()

    async def test_search_by_name(self):
        provider = MockProvider("celestrak_gp").route(
            "/NORAD/elements/gp.php", MockEndpoint(json=ISS)
        )
        source = build_source("celestrak_gp", transport=provider.transport)
        page = await source.search(SourceQuery(text="ISS"))
        assert provider.last_params()["NAME"] == "ISS"
        assert len(page.records) == 1
        await source.aclose()

    async def test_search_by_international_designator(self):
        provider = MockProvider("celestrak_gp").route(
            "/NORAD/elements/gp.php", MockEndpoint(json=ISS)
        )
        source = build_source("celestrak_gp", transport=provider.transport)
        await source.search(SourceQuery(identifier="1998-067A"))
        assert provider.last_params()["INTDES"] == "1998-067A"
        await source.aclose()

    async def test_source_timestamp_is_the_element_set_epoch(self):
        provider = MockProvider("celestrak_gp").route(
            "/NORAD/elements/gp.php", MockEndpoint(json=ISS)
        )
        source = build_source("celestrak_gp", transport=provider.transport)
        record = await source.fetch_by_id("25544")
        timestamp = record.source_reference.source_timestamp
        assert timestamp is not None
        assert timestamp.year == 2026
        await source.aclose()

    async def test_only_one_request_per_lookup(self):
        """The update policy is honoured by not fanning out requests."""
        provider = MockProvider("celestrak_gp").route(
            "/NORAD/elements/gp.php", MockEndpoint(json=ISS)
        )
        source = build_source("celestrak_gp", transport=provider.transport)
        await source.fetch_by_id("25544")
        assert provider.call_count == 1
        await source.aclose()


class TestIssNormalization:
    def _iss(self):
        return normalize_gp_record(gp_record(ISS[0]))

    def test_iss_becomes_a_space_station(self):
        station, _ = self._iss()
        assert isinstance(station, SpaceStation)
        assert isinstance(station, Satellite)
        assert station.object_type is ObjectType.SPACE_STATION
        assert station.canonical_id == "space-station:25544"

    def test_identifiers_mapped(self):
        station, _ = self._iss()
        assert station.norad_cat_id == 25544
        assert station.international_designator == "1998-067A"
        assert station.name == "ISS (ZARYA)"

    def test_elements_keep_their_published_units(self):
        station, _ = self._iss()
        elements = station.orbits[0].elements
        assert elements.mean_motion.unit == "rev/d"
        assert elements.mean_motion.value == pytest.approx(15.49488657)
        assert elements.inclination.unit == "deg"
        assert elements.inclination.value == pytest.approx(51.6333)
        assert elements.eccentricity.value == pytest.approx(0.00076081)
        assert elements.ascending_node_longitude.value == pytest.approx(351.68)
        assert elements.argument_of_periapsis.value == pytest.approx(59.6839)
        assert elements.mean_anomaly.value == pytest.approx(300.4901)

    def test_drag_terms_preserved_with_units(self):
        station, _ = self._iss()
        elements = station.orbits[0].elements
        assert elements.bstar.unit == "1/R_earth"
        assert elements.bstar.value == pytest.approx(0.00014375343)
        assert elements.mean_motion_dot == pytest.approx(7.616e-5)
        assert elements.mean_motion_ddot == pytest.approx(0.0)
        assert elements.revolution_number_at_epoch == 58141

    def test_element_theory_is_sgp4_not_keplerian(self):
        """The distinction that stops these being averaged with JPL elements."""
        station, _ = self._iss()
        orbit = station.orbits[0]
        assert orbit.element_theory is ElementTheory.SGP4_MEAN
        assert orbit.element_theory is not ElementTheory.OSCULATING_KEPLERIAN

    def test_frame_is_geocentric_teme(self):
        station, _ = self._iss()
        frame = station.orbits[0].frame
        assert frame.origin_type is OriginType.GEOCENTRIC
        assert frame.center_body == "earth"
        assert frame.reference_frame is ReferenceFrame.TEME
        assert frame.time_scale is TimeScale.UTC

    def test_provenance_labelled_secondary_operational(self):
        station, _ = self._iss()
        assert station.source_specific["provenance_label"] == PROVENANCE_LABEL
        assert station.orbits[0].source_specific["provenance_label"] == PROVENANCE_LABEL
        assert station.primary_source.source_type.value == "SECONDARY_OPERATIONAL"

    def test_record_says_it_is_not_an_ephemeris(self):
        station, _ = self._iss()
        assert "not a precise ephemeris" in station.orbits[0].source_specific["note"]

    def test_regime_classified_as_leo(self):
        station, _ = self._iss()
        assert station.orbit_regime is OrbitRegime.LEO

    def test_regime_is_recorded_as_derived_in_lineage(self):
        _, lineage = self._iss()
        assert lineage.is_derived("orbit_regime")

    def test_lineage_warns_about_element_theory(self):
        _, lineage = self._iss()
        assert "not osculating Keplerian" in lineage.explain_field("orbits[0].frame")

    def test_provenance_complete(self):
        station, lineage = self._iss()
        require_provenance(station, lineage)

    def test_roundtrips_through_json(self):
        station, _ = self._iss()
        assert SpaceStation.model_validate_json(station.model_dump_json()) == station

    def test_missing_epoch_is_an_error(self):
        row = dict(ISS[0])
        row["EPOCH"] = None
        with pytest.raises(ValueError, match="no EPOCH"):
            normalize_gp_record(gp_record(row))

    def test_missing_catalog_number_is_an_error(self):
        row = dict(ISS[0])
        row["NORAD_CAT_ID"] = None
        with pytest.raises(ValueError, match="no NORAD_CAT_ID"):
            normalize_gp_record(gp_record(row))


class TestConstellationNormalization:
    def test_all_gps_satellites_normalize(self):
        satellites = [normalize_gp_record(gp_record(row))[0] for row in GPS]
        assert len(satellites) == 3
        assert all(isinstance(item, Satellite) for item in satellites)
        assert all(not isinstance(item, SpaceStation) for item in satellites)

    def test_gps_classified_as_meo(self):
        satellites = [normalize_gp_record(gp_record(row))[0] for row in GPS]
        assert all(item.orbit_regime is OrbitRegime.MEO for item in satellites)

    def test_each_satellite_has_a_distinct_canonical_id(self):
        ids = {normalize_gp_record(gp_record(row))[0].canonical_id for row in GPS}
        assert len(ids) == 3

    def test_zero_bstar_is_preserved_not_dropped(self):
        satellite, _ = normalize_gp_record(gp_record(GPS[0]))
        assert satellite.orbits[0].elements.bstar is not None
        assert satellite.orbits[0].elements.bstar.value == 0.0


class TestRegimeClassification:
    def test_leo(self):
        assert classify_regime(15.5, 0.0007) is OrbitRegime.LEO

    def test_meo(self):
        assert classify_regime(2.0, 0.01) is OrbitRegime.MEO

    def test_geo(self):
        assert classify_regime(1.0027, 0.0001) is OrbitRegime.GEO

    def test_highly_eccentric(self):
        assert classify_regime(2.0, 0.7) is OrbitRegime.HEO

    def test_unknown_without_mean_motion(self):
        assert classify_regime(None, 0.1) is OrbitRegime.UNKNOWN
        assert classify_regime(0.0, 0.1) is OrbitRegime.UNKNOWN


class TestCelestrakFreshness:
    def test_recent_element_set_may_be_called_current(self):
        station, _ = normalize_gp_record(gp_record(ISS[0]))
        orbit = station.orbits[0]
        now = orbit.epoch + timedelta(hours=1)
        orbit.retrieved_at = now
        assessment = apply_freshness(orbit, POLICIES["celestrak_gp"], now=now)
        assert assessment.may_present_as_live is True

    def test_week_old_element_set_may_not_be_called_current(self):
        station, _ = normalize_gp_record(gp_record(ISS[0]))
        orbit = station.orbits[0]
        now = orbit.epoch + timedelta(days=7)
        orbit.retrieved_at = now
        assessment = apply_freshness(orbit, POLICIES["celestrak_gp"], now=now)
        assert assessment.may_present_as_live is False
        assert assessment.is_stale is True

    def test_cache_ttl_matches_the_two_hour_update_cadence(self):
        policy = POLICIES["celestrak_gp"]
        assert policy.cache_ttl == timedelta(hours=2)
        assert policy.update_interval == timedelta(hours=2)


class TestAuthorityBoundary:
    def test_sgp4_elements_cannot_claim_a_heliocentric_frame(self):
        from data.models import FrameContext, OrbitalElements

        with pytest.raises(ValidationError, match="geocentric by definition"):
            OrbitRecord(
                canonical_id="orbit:bad",
                object_canonical_id="satellite:1",
                epoch=datetime(2026, 8, 18, tzinfo=timezone.utc),
                frame=FrameContext(origin_type=OriginType.HELIOCENTRIC, center_body="sun"),
                element_theory=ElementTheory.SGP4_MEAN,
                elements=OrbitalElements(),
            )

    def test_celestrak_ranks_below_scientific_archives_for_elements(self):
        from data.sources import Capability, sources_with_capability

        ranked = sources_with_capability(Capability.ORBITAL_ELEMENTS)
        assert ranked.index("celestrak_gp") > ranked.index("jpl_sbdb")

    def test_celestrak_is_the_only_source_for_current_satellite_elements(self):
        """No scientific archive publishes these, which is why it is included."""
        from data.sources import all_source_info

        providers = [
            info.name
            for info in all_source_info()
            if any(
                "satellite" in item.lower() and "element" in item.lower()
                for item in info.provides
            )
        ]
        assert providers == ["celestrak_gp"]

    def test_scientific_archives_disclaim_artificial_satellites(self):
        from data.sources import build_source

        for name in ("jpl_sbdb", "mpc_orbits", "nasa_exoplanet_archive"):
            disclaimers = " ".join(build_source(name).get_source_info().does_not_provide)
            assert "satellite" in disclaimers.lower()


@live_only
class TestCelestrakLive:
    async def test_iss_live(self):
        async with CelestrakSource() as source:
            record = await source.fetch_by_id("25544")
            station, _ = normalize_gp_record(record)
            assert station.norad_cat_id == 25544

    async def test_group_live(self):
        async with CelestrakSource() as source:
            page = await source.fetch_group("gps-ops")
            assert len(page.records) > 5
