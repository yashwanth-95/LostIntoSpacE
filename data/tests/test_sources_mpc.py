"""Minor Planet Center integration, against recorded responses.

Example objects: 1 Ceres (numbered, long arc) for orbits, and 2024 YR4 (a
recently-discovered NEO with a dense observation set) for observations.
"""

import os

import pytest

from data.models import (
    CoordinateSystem,
    ElementTheory,
    Observation,
    ObservationType,
    OrbitRecord,
    OriginType,
    ReferenceFrame,
    TimeScale,
)
from data.normalization.mpc import normalize_mpc_observations, normalize_mpc_orbit
from data.provenance import require_provenance
from data.sources import (
    MpcObservationsSource,
    MpcOrbitsSource,
    SourceNotFoundError,
    SourceQuery,
    SourceResponseError,
    build_source,
)
from data.sources.base import SourceRecord
from data.tests.mocks import MockEndpoint, MockProvider, load_fixture

LIVE = os.environ.get("LOSTINTOSPACE_LIVE_TESTS") == "1"
live_only = pytest.mark.skipif(not LIVE, reason="set LOSTINTOSPACE_LIVE_TESTS=1 to run")

CERES_ORB = load_fixture("mpc_orb_ceres.json")
YR4_OBS = load_fixture("mpc_obs_2024yr4.json")


def orbit_record() -> SourceRecord:
    source = build_source("mpc_orbits")
    payload = CERES_ORB[0]["mpc_orb"][0]
    return SourceRecord(
        source_name="mpc_orbits",
        source_record_id="1",
        payload=payload,
        source_reference=source.build_source_reference(record_id="1", version="0.4"),
    )


def observation_record(rows=None) -> SourceRecord:
    source = build_source("mpc_observations")
    return SourceRecord(
        source_name="mpc_observations",
        source_record_id="2024 YR4",
        payload={
            "format": "ADES_DF",
            "designation": "2024 YR4",
            "rows": YR4_OBS[0]["ADES_DF"] if rows is None else rows,
        },
        source_reference=source.build_source_reference(record_id="2024 YR4"),
    )


class TestMpcOrbitsAdapter:
    async def test_lookup_sends_a_json_body_on_get(self):
        """The MPC data APIs answer a plain GET with a content-type error."""
        provider = MockProvider("mpc_orbits").route("/api/get-orb", MockEndpoint(json=CERES_ORB))
        source = build_source("mpc_orbits", transport=provider.transport)
        record = await source.fetch_by_id("Ceres")
        request = provider.last_request()
        assert request.method == "GET"
        assert request.headers["Content-Type"] == "application/json"
        assert b"Ceres" in request.content
        assert record.source_record_id == "1"
        await source.aclose()

    async def test_unknown_designation_raises_not_found(self):
        provider = MockProvider("mpc_orbits").route(
            "/api/get-orb", MockEndpoint(json=[{"mpc_orb": []}])
        )
        source = build_source("mpc_orbits", transport=provider.transport)
        with pytest.raises(SourceNotFoundError, match="no orbit solution"):
            await source.fetch_by_id("Nonexistent999")
        await source.aclose()

    async def test_blank_designation_rejected(self):
        source = build_source("mpc_orbits")
        with pytest.raises(SourceResponseError, match="needs a designation"):
            await source.fetch_by_id("")
        await source.aclose()

    async def test_search_returns_empty_page_on_a_miss(self):
        provider = MockProvider("mpc_orbits").route(
            "/api/get-orb", MockEndpoint(json=[{"mpc_orb": []}])
        )
        source = build_source("mpc_orbits", transport=provider.transport)
        page = await source.search(SourceQuery(identifier="Nonexistent999"))
        assert page.records == []
        await source.aclose()

    async def test_health_check_uses_the_json_body_form(self):
        provider = MockProvider("mpc_orbits").route("/api/get-orb", MockEndpoint(json=CERES_ORB))
        source = build_source("mpc_orbits", transport=provider.transport)
        status = await source.health_check()
        assert status.healthy is True
        assert provider.last_request().content
        await source.aclose()

    async def test_version_captured_from_mpcorb_version(self):
        provider = MockProvider("mpc_orbits").route("/api/get-orb", MockEndpoint(json=CERES_ORB))
        source = build_source("mpc_orbits", transport=provider.transport)
        record = await source.fetch_by_id("Ceres")
        assert record.source_reference.source_version == "0.4"
        await source.aclose()


class TestMpcOrbitNormalization:
    def test_produces_an_orbit_record(self):
        orbit, _ = normalize_mpc_orbit(orbit_record())
        assert isinstance(orbit, OrbitRecord)
        assert orbit.object_canonical_id == "asteroid:1"
        assert orbit.source_designation == "1"

    def test_epoch_converted_from_mjd_with_time_scale_preserved(self):
        orbit, _ = normalize_mpc_orbit(orbit_record())
        # MJD 61000.0 = JD 2461000.5 = 2025-11-21.
        assert (orbit.epoch.year, orbit.epoch.month, orbit.epoch.day) == (2025, 11, 21)
        # The MPC calls it TDT; the canonical vocabulary calls it TT.
        assert orbit.frame.time_scale is TimeScale.TT

    def test_frame_is_heliocentric_ecliptic(self):
        orbit, _ = normalize_mpc_orbit(orbit_record())
        assert orbit.frame.origin_type is OriginType.HELIOCENTRIC
        assert orbit.frame.center_body == "sun"
        assert orbit.frame.reference_frame is ReferenceFrame.ECLIPJ2000
        assert orbit.frame.coordinate_system is CoordinateSystem.KEPLERIAN
        assert orbit.element_theory is ElementTheory.OSCULATING_KEPLERIAN

    def test_cometary_elements_mapped_with_uncertainties(self):
        orbit, _ = normalize_mpc_orbit(orbit_record())
        elements = orbit.elements
        assert elements.periapsis_distance.unit == "au"
        assert elements.periapsis_distance.value == pytest.approx(2.54553801175322, rel=1e-14)
        assert elements.periapsis_distance.uncertainty == pytest.approx(8.08234e-07)
        assert elements.eccentricity.value == pytest.approx(0.079576366193319, rel=1e-14)
        assert elements.eccentricity.uncertainty == pytest.approx(2.92222e-07)
        assert elements.inclination.unit == "deg"
        assert elements.ascending_node_longitude.value == pytest.approx(80.249637228685)

    def test_perihelion_time_converted_from_mjd(self):
        orbit, _ = normalize_mpc_orbit(orbit_record())
        assert orbit.elements.periapsis_time is not None
        assert orbit.elements.periapsis_time.tzinfo is not None

    def test_covariance_rebuilt_and_symmetric(self):
        orbit, _ = normalize_mpc_orbit(orbit_record())
        covariance = orbit.covariance
        assert covariance is not None
        assert covariance.labels == ["q", "e", "i", "node", "argperi", "peri_time"]
        assert len(covariance.matrix) == 6
        # Validator enforces symmetry, so reaching here proves the mirror worked.
        assert covariance.matrix[0][1] == covariance.matrix[1][0]
        assert covariance.sigma("q") > 0

    def test_covariance_units_match_labels(self):
        orbit, _ = normalize_mpc_orbit(orbit_record())
        covariance = orbit.covariance
        assert covariance.units == ["au", "1", "deg", "deg", "deg", "d"]

    def test_fit_statistics_captured(self):
        orbit, _ = normalize_mpc_orbit(orbit_record())
        assert orbit.fit.observations_used == 7297
        assert orbit.fit.condition_code == "0"
        assert orbit.fit.solution_date is not None

    def test_cartesian_element_set_preserved_not_discarded(self):
        orbit, _ = normalize_mpc_orbit(orbit_record())
        cartesian = orbit.source_specific["cartesian_element_set"]
        assert cartesian["coefficient_names"] == ["x", "y", "z", "vx", "vy", "vz"]
        assert len(cartesian["coefficient_values"]) == 6

    def test_secondary_designations_preserved(self):
        orbit, _ = normalize_mpc_orbit(orbit_record())
        secondary = orbit.source_specific["unpacked_secondary_provisional_designations"]
        assert "1943 XB" in secondary
        assert "A899 OF" in secondary

    def test_moids_and_magnitude_block_preserved(self):
        orbit, _ = normalize_mpc_orbit(orbit_record())
        assert "Earth" in orbit.source_specific["moid_data"]
        assert orbit.source_specific["magnitude_data"]["H"] == pytest.approx(3.341)

    def test_orbit_class_from_categorization(self):
        orbit, _ = normalize_mpc_orbit(orbit_record())
        assert orbit.orbit_class == "Main Belt"

    def test_lineage_explains_the_epoch_and_covariance(self):
        _, lineage = normalize_mpc_orbit(orbit_record())
        assert "MJD" in lineage.explain_field("epoch")
        assert "mirroring the upper" in lineage.explain_field("covariance")

    def test_provenance_complete(self):
        orbit, lineage = normalize_mpc_orbit(orbit_record())
        require_provenance(orbit, lineage)

    def test_roundtrips_through_json(self):
        orbit, _ = normalize_mpc_orbit(orbit_record())
        assert OrbitRecord.model_validate_json(orbit.model_dump_json()) == orbit

    def test_missing_epoch_is_an_error_not_a_guess(self):
        record = orbit_record()
        record.payload = dict(record.payload)
        record.payload["epoch_data"] = {}
        with pytest.raises(ValueError, match="no usable epoch"):
            normalize_mpc_orbit(record)


class TestMpcObservationsAdapter:
    async def test_fetch_requests_structured_ades(self):
        provider = MockProvider("mpc_observations").route(
            "/api/get-obs", MockEndpoint(json=YR4_OBS)
        )
        source = build_source("mpc_observations", transport=provider.transport)
        record = await source.fetch_by_id("2024 YR4")
        assert b"ADES_DF" in provider.last_request().content
        assert record.payload["format"] == "ADES_DF"
        assert len(record.payload["rows"]) == 3
        await source.aclose()

    async def test_unsupported_format_rejected_before_the_request(self):
        provider = MockProvider("mpc_observations")
        source = build_source("mpc_observations", transport=provider.transport)
        with pytest.raises(SourceResponseError, match="unsupported observation format"):
            await source.fetch_by_id("Ceres", output_format="CSV")
        assert provider.call_count == 0
        await source.aclose()

    async def test_no_observations_raises_not_found(self):
        provider = MockProvider("mpc_observations").route(
            "/api/get-obs", MockEndpoint(json=[{"ADES_DF": None}])
        )
        source = build_source("mpc_observations", transport=provider.transport)
        with pytest.raises(SourceNotFoundError, match="no observations"):
            await source.fetch_by_id("Nonexistent999")
        await source.aclose()

    async def test_search_reports_row_count(self):
        provider = MockProvider("mpc_observations").route(
            "/api/get-obs", MockEndpoint(json=YR4_OBS)
        )
        source = build_source("mpc_observations", transport=provider.transport)
        page = await source.search(SourceQuery(identifier="2024 YR4"))
        assert page.total_available == 3
        await source.aclose()


class TestMpcObservationNormalization:
    def test_rows_become_observations(self):
        observations, _ = normalize_mpc_observations(observation_record())
        assert len(observations) == 3
        assert all(isinstance(item, Observation) for item in observations)

    def test_an_observation_is_never_an_orbital_solution(self):
        """The rule this integration exists to hold."""
        observations, _ = normalize_mpc_observations(observation_record())
        for observation in observations:
            assert observation.is_orbital_solution is False
        assert "elements" not in Observation.model_fields
        assert "semi_major_axis" not in Observation.model_fields

    def test_astrometry_mapped_with_converted_uncertainties(self):
        observations, _ = normalize_mpc_observations(observation_record())
        first = observations[0]
        assert first.right_ascension.unit == "deg"
        assert first.right_ascension.value == pytest.approx(190.949838)
        # rmsra is 1.6 arcsec in the fixture -> degrees.
        assert first.right_ascension.uncertainty == pytest.approx(1.6 / 3600.0)
        assert first.declination.uncertainty == pytest.approx(0.7 / 3600.0)

    def test_observatory_code_required_and_present(self):
        observations, _ = normalize_mpc_observations(observation_record())
        assert observations[0].frame.observatory_code == "W68"
        assert observations[0].frame.origin_type is OriginType.TOPOCENTRIC

    def test_magnitude_kept_only_with_its_band(self):
        observations, _ = normalize_mpc_observations(observation_record())
        first = observations[0]
        assert first.magnitude.value == pytest.approx(17.3)
        assert first.magnitude_band == "G"

    def test_magnitude_without_band_is_dropped_not_invented(self):
        rows = [dict(YR4_OBS[0]["ADES_DF"][0])]
        rows[0]["band"] = None
        observations, _ = normalize_mpc_observations(observation_record(rows))
        assert observations[0].magnitude is None
        assert observations[0].magnitude_band is None
        # The astrometry survives; only the uncomparable magnitude is dropped.
        assert observations[0].right_ascension is not None

    def test_observation_type_detected_from_mode(self):
        observations, _ = normalize_mpc_observations(observation_record())
        assert observations[0].observation_type is ObservationType.OPTICAL_ASTROMETRY

    def test_observation_metadata_preserved(self):
        observations, _ = normalize_mpc_observations(observation_record())
        extras = observations[0].source_specific
        assert extras["obsid"]
        assert extras["exposure_seconds"] == pytest.approx(30.0)
        assert extras["seeing_arcsec"] == pytest.approx(3.9)
        assert observations[0].catalog_code == "Gaia3"

    def test_rows_without_a_time_are_skipped(self):
        rows = [dict(YR4_OBS[0]["ADES_DF"][0]), {"obstime": None, "ra": "1", "dec": "1"}]
        observations, _ = normalize_mpc_observations(observation_record(rows))
        assert len(observations) == 1

    def test_unstructured_format_refused(self):
        record = observation_record()
        record.payload = dict(record.payload)
        record.payload["format"] = "OBS80"
        with pytest.raises(ValueError, match="only the structured ADES_DF"):
            normalize_mpc_observations(record)

    def test_lineage_notes_the_arcsec_conversion(self):
        _, lineage = normalize_mpc_observations(observation_record())
        assert "arcsec -> degrees" in lineage.describe()

    def test_lineage_asserts_none_are_solutions(self):
        _, lineage = normalize_mpc_observations(observation_record())
        assert "none is an orbital" in lineage.describe()

    def test_provenance_complete(self):
        observations, lineage = normalize_mpc_observations(observation_record())
        for observation in observations:
            require_provenance(observation, lineage)

    def test_roundtrips_through_json(self):
        observations, _ = normalize_mpc_observations(observation_record())
        first = observations[0]
        assert Observation.model_validate_json(first.model_dump_json()) == first


class TestMpcVersusJplAuthority:
    def test_mpc_and_jpl_orbits_stay_separate_records(self):
        """Two archives, two solutions, kept side by side rather than merged."""
        from data.normalization.jpl import normalize_sbdb_object
        from data.tests.test_sources_jpl import sbdb_record

        mpc_orbit, _ = normalize_mpc_orbit(orbit_record())
        jpl_body, _ = normalize_sbdb_object(sbdb_record())
        jpl_orbit = jpl_body.orbits[0]

        assert mpc_orbit.object_canonical_id == jpl_orbit.object_canonical_id
        assert mpc_orbit.canonical_id != jpl_orbit.canonical_id
        assert mpc_orbit.epoch != jpl_orbit.epoch
        # Same physical object, different published solutions and time scales.
        assert mpc_orbit.frame.time_scale is TimeScale.TT
        assert jpl_orbit.frame.time_scale is TimeScale.TDB


@live_only
class TestMpcLive:
    async def test_orbit_live(self):
        async with MpcOrbitsSource() as source:
            record = await source.fetch_by_id("Ceres")
            orbit, _ = normalize_mpc_orbit(record)
            assert orbit.covariance is not None

    async def test_observations_live(self):
        async with MpcObservationsSource() as source:
            record = await source.fetch_by_id("Ceres")
            observations, _ = normalize_mpc_observations(record)
            assert observations
