"""JPL SBDB and Horizons integration, against recorded responses."""

import os

import pytest

from data.models import Asteroid, Comet, ElementTheory, OriginType, ReferenceFrame, TimeScale
from data.normalization.jpl import HorizonsHeader, normalize_sbdb_object, parse_horizons_vectors
from data.provenance import require_provenance
from data.sources import (
    JplHorizonsSource,
    JplSbdbSource,
    SourceNotFoundError,
    SourceQuery,
    SourceResponseError,
    build_source,
)
from data.sources.base import SourceRecord
from data.sources.jpl import HorizonsRequest
from data.tests.mocks import MockEndpoint, MockProvider, load_fixture

LIVE = os.environ.get("LOSTINTOSPACE_LIVE_TESTS") == "1"
live_only = pytest.mark.skipif(not LIVE, reason="set LOSTINTOSPACE_LIVE_TESTS=1 to run")

CERES = load_fixture("sbdb_ceres.json")
BENNU = load_fixture("sbdb_bennu.json")
HORIZONS_MARS = load_fixture("horizons_mars_vectors.json")


def sbdb_record(payload=CERES) -> SourceRecord:
    source = build_source("jpl_sbdb")
    return SourceRecord(
        source_name="jpl_sbdb",
        source_record_id=(payload.get("object") or {}).get("spkid"),
        payload=payload,
        source_reference=source.build_source_reference(
            record_id=(payload.get("object") or {}).get("spkid"), version="1.3"
        ),
    )


class TestSbdbAdapter:
    async def test_lookup_requests_full_precision_and_covariance(self):
        provider = MockProvider("jpl_sbdb").route("/sbdb.api", MockEndpoint(json=CERES))
        source = build_source("jpl_sbdb", transport=provider.transport)
        record = await source.fetch_by_id("Ceres")
        params = provider.last_params()
        assert params["sstr"] == "Ceres"
        assert params["full-prec"] == "1"
        assert params["cov"] == "mat"
        assert params["phys-par"] == "1"
        assert record.source_record_id == "20000001"
        assert record.source_reference.source_version == "1.3"
        await source.aclose()

    async def test_unmatched_designation_raises_not_found(self):
        """SBDB answers a miss with 200 and a message, so 404 must be synthesized."""
        provider = MockProvider("jpl_sbdb").route(
            "/sbdb.api", MockEndpoint(json={"message": "specified object was not found"})
        )
        source = build_source("jpl_sbdb", transport=provider.transport)
        with pytest.raises(SourceNotFoundError, match="no object matching"):
            await source.fetch_by_id("Nonexistent999")
        await source.aclose()

    async def test_ambiguous_designation_reported_separately(self):
        provider = MockProvider("jpl_sbdb").route(
            "/sbdb.api", MockEndpoint(json={"count": 3, "list": [{"pdes": "1"}]})
        )
        source = build_source("jpl_sbdb", transport=provider.transport)
        with pytest.raises(SourceResponseError, match="ambiguous designation"):
            await source.fetch_by_id("smith")
        await source.aclose()

    async def test_blank_identifier_rejected(self):
        source = build_source("jpl_sbdb")
        with pytest.raises(SourceResponseError, match="needs a designation"):
            await source.fetch_by_id("  ")
        await source.aclose()

    async def test_search_returns_empty_page_for_a_miss(self):
        provider = MockProvider("jpl_sbdb").route(
            "/sbdb.api", MockEndpoint(json={"message": "not found"})
        )
        source = build_source("jpl_sbdb", transport=provider.transport)
        page = await source.search(SourceQuery(text="Nonexistent999"))
        assert page.records == []
        assert page.total_available == 0
        await source.aclose()


class TestSbdbNormalization:
    def test_ceres_becomes_an_asteroid(self):
        body, _ = normalize_sbdb_object(sbdb_record())
        assert isinstance(body, Asteroid)
        assert body.canonical_id == "asteroid:1"
        assert body.name == "1 Ceres"
        assert body.number == 1
        assert body.spk_id == "20000001"
        assert body.orbit_class == "MBA"
        assert body.is_near_earth_object is False

    def test_physical_parameters_keep_units_and_sigmas(self):
        body, _ = normalize_sbdb_object(sbdb_record())
        physical = body.physical
        assert physical.diameter.value == pytest.approx(939.4)
        assert physical.diameter.unit == "km"
        assert physical.diameter.uncertainty == pytest.approx(0.2)
        assert physical.gm.unit == "km3/s2"
        assert physical.gm.value == pytest.approx(62.6284)
        assert physical.density.unit == "g/cm3"
        assert physical.density.si_value() == pytest.approx(2162.0)
        assert physical.absolute_magnitude.unit == "mag"
        assert physical.geometric_albedo.value == pytest.approx(0.090)

    def test_rotation_and_pole_split_correctly(self):
        body, _ = normalize_sbdb_object(sbdb_record())
        rotation = body.physical.rotation
        assert rotation.sidereal_rotation_period.unit == "h"
        assert rotation.sidereal_rotation_period.value == pytest.approx(9.074170)
        assert rotation.pole_right_ascension.value == pytest.approx(291.421)
        assert rotation.pole_declination.value == pytest.approx(66.758)
        assert rotation.pole_declination.uncertainty == pytest.approx(0.002)

    def test_unmapped_physical_parameters_are_preserved_not_dropped(self):
        body, _ = normalize_sbdb_object(sbdb_record())
        extras = body.source_specific["sbdb_extras"]
        assert "extent" in extras
        assert extras["extent"]["value"] == "964.4 x 964.2 x 891.8"
        assert extras["references"]["diameter"].startswith("Nature")

    def test_spectral_type_captured(self):
        body, _ = normalize_sbdb_object(sbdb_record())
        assert body.spectral_type == "G"

    def test_orbit_elements_keep_published_precision_and_sigma(self):
        body, _ = normalize_sbdb_object(sbdb_record())
        orbit = body.orbits[0]
        assert orbit.elements.semi_major_axis.value == pytest.approx(2.765552595034094, rel=1e-15)
        assert orbit.elements.semi_major_axis.unit == "au"
        assert orbit.elements.semi_major_axis.uncertainty == pytest.approx(1.0134e-11)
        assert orbit.elements.eccentricity.uncertainty == pytest.approx(4.7755e-12)
        assert orbit.elements.mean_motion.unit == "deg/d"

    def test_frame_context_is_explicit(self):
        body, _ = normalize_sbdb_object(sbdb_record())
        frame = body.orbits[0].frame
        assert frame.origin_type is OriginType.HELIOCENTRIC
        assert frame.center_body == "sun"
        assert frame.reference_frame is ReferenceFrame.ECLIPJ2000
        assert frame.time_scale is TimeScale.TDB
        assert body.orbits[0].element_theory is ElementTheory.OSCULATING_KEPLERIAN

    def test_epoch_converted_from_julian_date(self):
        body, _ = normalize_sbdb_object(sbdb_record())
        # JD 2461200.5 = 20613 days after the Unix epoch = 2026-06-09 00:00.
        # A JD ending in .5 lands on midnight, which is why SBDB epochs do.
        epoch = body.orbits[0].epoch
        assert (epoch.year, epoch.month, epoch.day) == (2026, 6, 9)
        assert (epoch.hour, epoch.minute) == (0, 0)

    def test_covariance_preserved_with_its_own_epoch(self):
        body, _ = normalize_sbdb_object(sbdb_record())
        covariance = body.orbits[0].covariance
        assert covariance is not None
        assert covariance.labels == ["e", "q", "tp", "node", "peri", "i"]
        assert len(covariance.matrix) == 6
        # SBDB gives the covariance a different epoch from the orbit.
        assert covariance.epoch is not None
        assert covariance.epoch != body.orbits[0].epoch
        assert covariance.sigma("e") > 0

    def test_orbit_fit_quality_captured(self):
        body, _ = normalize_sbdb_object(sbdb_record())
        fit = body.orbits[0].fit
        assert fit.observations_used == 1075
        assert fit.condition_code == "0"
        assert fit.rms_residual_arcsec == pytest.approx(0.43153)
        assert fit.data_arc_days == pytest.approx(9520.0)

    def test_validity_window_recorded_when_published(self):
        body, _ = normalize_sbdb_object(sbdb_record())
        orbit = body.orbits[0]
        # not_valid_before/after may be null for a well-determined main-belt orbit.
        if orbit.valid_from and orbit.valid_until:
            assert orbit.valid_from < orbit.valid_until

    def test_discovery_information_mapped(self):
        body, _ = normalize_sbdb_object(sbdb_record())
        assert body.discovery.discovered_by == "Piazzi, G."
        assert body.discovery.discovery_year == 1801
        assert body.discovery.discovery_facility == "Palermo"

    def test_bennu_is_a_near_earth_asteroid(self):
        body, _ = normalize_sbdb_object(sbdb_record(BENNU))
        assert isinstance(body, Asteroid)
        assert body.is_near_earth_object is True
        assert body.earth_moid is not None
        assert body.earth_moid.unit == "au"

    def test_lineage_explains_the_epoch_conversion(self):
        _, lineage = normalize_sbdb_object(sbdb_record())
        explanation = lineage.explain_field("orbits[0].epoch")
        assert "JD" in explanation and "TDB" in explanation

    def test_lineage_records_the_frame_annotation(self):
        _, lineage = normalize_sbdb_object(sbdb_record())
        assert "heliocentric ecliptic" in lineage.explain_field("orbits[0].frame")

    def test_provenance_complete(self):
        body, lineage = normalize_sbdb_object(sbdb_record())
        require_provenance(body, lineage)
        assert body.orbits[0].elements.inclination.source.source_name == "jpl_sbdb"

    def test_roundtrips_through_json(self):
        body, _ = normalize_sbdb_object(sbdb_record())
        restored = Asteroid.model_validate_json(body.model_dump_json())
        assert restored == body


class TestHorizonsRequest:
    def test_parameters_are_quoted_as_horizons_requires(self):
        params = HorizonsRequest(
            command="499", start_time="2026-08-18", stop_time="2026-08-20", step_size="1 d"
        ).to_params()
        assert params["COMMAND"] == "'499'"
        assert params["STEP_SIZE"] == "'1 d'"
        assert params["CENTER"] == "'500@0'"
        assert params["format"] == "json"

    def test_quotes_in_input_are_normalized(self):
        assert HorizonsRequest(
            command="'499'", start_time="2026-08-18", stop_time="2026-08-20"
        ).command == "499"

    def test_unknown_units_rejected(self):
        with pytest.raises(ValueError, match="unsupported out_units"):
            HorizonsRequest(
                command="499", start_time="a", stop_time="b", out_units="FURLONGS"
            )

    def test_unknown_ephem_type_rejected(self):
        with pytest.raises(ValueError, match="unsupported ephem_type"):
            HorizonsRequest(
                command="499", start_time="a", stop_time="b", ephem_type="MAGIC"
            )


class TestHorizonsAdapter:
    async def test_vectors_fetch_records_the_request(self):
        provider = MockProvider("jpl_horizons").route(
            "/api/horizons.api", MockEndpoint(json=HORIZONS_MARS)
        )
        source = build_source("jpl_horizons", transport=provider.transport)
        record = await source.fetch_vectors(
            HorizonsRequest(command="499", start_time="2026-08-18", stop_time="2026-08-20")
        )
        assert record.payload["request"]["COMMAND"] == "'499'"
        assert "$$SOE" in record.payload["result"]
        await source.aclose()

    async def test_horizons_error_block_is_surfaced(self):
        provider = MockProvider("jpl_horizons").route(
            "/api/horizons.api",
            MockEndpoint(json={"error": "INPUT ERROR in VLADD; STEP_SIZE=1 D"}),
        )
        source = build_source("jpl_horizons", transport=provider.transport)
        with pytest.raises(SourceResponseError, match="Horizons rejected the request"):
            await source.fetch_vectors(
                HorizonsRequest(command="499", start_time="a", stop_time="b")
            )
        await source.aclose()

    async def test_missing_ephemeris_block_is_an_error(self):
        provider = MockProvider("jpl_horizons").route(
            "/api/horizons.api", MockEndpoint(json={"result": "API VERSION: 1.2\nno data"})
        )
        source = build_source("jpl_horizons", transport=provider.transport)
        with pytest.raises(SourceResponseError, match=r"no ephemeris block"):
            await source.fetch_vectors(
                HorizonsRequest(command="499", start_time="a", stop_time="b")
            )
        await source.aclose()


class TestHorizonsHeaderParsing:
    def _header(self) -> HorizonsHeader:
        return HorizonsHeader(HORIZONS_MARS["result"])

    def test_target_and_center_read_from_the_report(self):
        header = self._header()
        assert header.target.startswith("Mars")
        assert "Solar System Barycenter" in header.center

    def test_units_read_not_assumed(self):
        assert self._header().units == ("km", "km/s")

    def test_unrecognised_units_refuse_to_guess(self):
        header = HorizonsHeader("Output units    : PARSECS-FORTNIGHT\n")
        with pytest.raises(ValueError, match="refusing to guess"):
            header.units

    def test_reference_frame_detected(self):
        assert self._header().reference_frame is ReferenceFrame.ECLIPJ2000

    def test_origin_type_detected_as_barycentric(self):
        """The centre was 500@0 — barycentric, not heliocentric."""
        origin_type, body = self._header().origin
        assert origin_type is OriginType.BARYCENTRIC
        assert body == "ssb"

    def test_time_scale_detected(self):
        assert self._header().time_scale is TimeScale.TDB

    def test_geocentric_centre_detected(self):
        header = HorizonsHeader(
            "Center body name: Earth (399)\nStart time      : A.D. 2026-Aug-18 00:00:00 TDB\n"
        )
        assert header.origin == (OriginType.GEOCENTRIC, "earth")


class TestHorizonsNormalization:
    def _ephemeris(self):
        source = build_source("jpl_horizons")
        record = SourceRecord(
            source_name="jpl_horizons",
            source_record_id="499",
            payload={
                "result": HORIZONS_MARS["result"],
                "request": HorizonsRequest(
                    command="499", start_time="2026-08-18", stop_time="2026-08-20"
                ).to_params(),
            },
            source_reference=source.build_source_reference(record_id="499", version="1.2"),
        )
        return parse_horizons_vectors(record)

    def test_all_states_parsed(self):
        ephemeris, _ = self._ephemeris()
        assert len(ephemeris.states) == 3

    def test_positions_keep_full_precision(self):
        ephemeris, _ = self._ephemeris()
        first = ephemeris.states[0]
        assert first.x.unit == "km"
        assert first.x.value == pytest.approx(1.033127417350907e08, rel=1e-15)
        assert first.z.value == pytest.approx(1.653931190076560e06, rel=1e-15)

    def test_velocities_parsed_with_their_own_unit(self):
        ephemeris, _ = self._ephemeris()
        first = ephemeris.states[0]
        assert first.has_velocity
        assert first.vx.unit == "km/s"
        assert first.vx.value == pytest.approx(-2.057152321831161e01, rel=1e-15)
        assert first.velocity_si()[0] == pytest.approx(-20571.52321831161, rel=1e-12)

    def test_epochs_from_julian_dates_are_ordered(self):
        ephemeris, _ = self._ephemeris()
        epochs = [state.epoch for state in ephemeris.states]
        assert epochs == sorted(epochs)
        assert epochs[0].year == 2026 and epochs[0].month == 8 and epochs[0].day == 18

    def test_frame_context_is_barycentric_not_heliocentric(self):
        """The distinction that makes the numbers meaningful."""
        ephemeris, _ = self._ephemeris()
        assert ephemeris.frame.origin_type is OriginType.BARYCENTRIC
        assert ephemeris.frame.center_body == "ssb"
        assert ephemeris.frame.reference_frame is ReferenceFrame.ECLIPJ2000
        assert ephemeris.frame.time_scale is TimeScale.TDB
        assert "barycentric" in ephemeris.frame.describe()

    def test_query_parameters_stored_for_reproducibility(self):
        ephemeris, _ = self._ephemeris()
        assert ephemeris.query_parameters["COMMAND"] == "'499'"
        assert ephemeris.query_parameters["OUT_UNITS"] == "'KM-S'"
        assert ephemeris.query_parameters["REF_PLANE"] == "'ECLIPTIC'"

    def test_step_size_and_window_captured(self):
        ephemeris, _ = self._ephemeris()
        assert ephemeris.step_size == "1440 minutes"
        assert ephemeris.start_time < ephemeris.stop_time

    def test_raw_header_text_preserved(self):
        ephemeris, _ = self._ephemeris()
        assert "Ecliptic" in ephemeris.source_specific["reference_frame_text"]
        assert ephemeris.source_specific["output_units_text"] == "KM-S"

    def test_lineage_states_the_frame_it_read(self):
        _, lineage = self._ephemeris()
        assert "BARYCENTRIC" in lineage.explain_field("frame")

    def test_provenance_complete(self):
        ephemeris, lineage = self._ephemeris()
        require_provenance(ephemeris, lineage)
        assert ephemeris.states[0].x.source.source_name == "jpl_horizons"

    def test_roundtrips_through_json(self):
        ephemeris, _ = self._ephemeris()
        restored = ephemeris.model_validate_json(ephemeris.model_dump_json())
        assert restored == ephemeris


class TestFrameSafety:
    def test_barycentric_and_heliocentric_states_are_not_comparable(self):
        ephemeris, _ = TestHorizonsNormalization()._ephemeris()
        from data.models import CoordinateSystem, FrameContext

        heliocentric = FrameContext(
            origin_type=OriginType.HELIOCENTRIC,
            center_body="sun",
            reference_frame=ReferenceFrame.ECLIPJ2000,
            coordinate_system=CoordinateSystem.CARTESIAN,
        )
        assert not ephemeris.frame.is_comparable_to(heliocentric)

    def test_sbdb_orbit_and_horizons_ephemeris_have_different_origins(self):
        body, _ = normalize_sbdb_object(sbdb_record())
        ephemeris, _ = TestHorizonsNormalization()._ephemeris()
        assert body.orbits[0].frame.origin_type is OriginType.HELIOCENTRIC
        assert ephemeris.frame.origin_type is OriginType.BARYCENTRIC
        assert not body.orbits[0].frame.is_comparable_to(ephemeris.frame)


@live_only
class TestJplLive:
    async def test_sbdb_ceres_live(self):
        async with JplSbdbSource() as source:
            record = await source.fetch_by_id("Ceres")
            body, _ = normalize_sbdb_object(record)
            assert body.name.endswith("Ceres")

    async def test_horizons_mars_live(self):
        async with JplHorizonsSource() as source:
            record = await source.fetch_vectors(
                HorizonsRequest(
                    command="499", start_time="2026-08-18", stop_time="2026-08-19"
                )
            )
            ephemeris, _ = parse_horizons_vectors(record)
            assert ephemeris.states
