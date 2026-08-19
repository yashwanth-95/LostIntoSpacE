"""NASA Exoplanet Archive integration and ADQL query safety."""

import os

import httpx
import pytest
from pydantic import ValidationError

from data.models import DataStatus, ObjectType, Planet, Star
from data.normalization.exoplanet import (
    map_disposition,
    normalize_exoplanet_row,
    strip_reference_markup,
)
from data.provenance import require_provenance
from data.sources import ExoplanetArchiveSource, SourceQuery, SourceResponseError, build_source
from data.sources.adql import AdqlError, AdqlQuery, Comparison, Predicate, quote_literal
from data.sources.base import SourceRecord
from data.sources.exoplanet_archive import (
    PS_COLUMNS,
    PS_TABLE,
    PSCOMPPARS_TABLE,
    TABLE_COLUMNS,
)
from data.tests.mocks import FakeSleeper, MockEndpoint, MockProvider, load_fixture

LIVE = os.environ.get("LOSTINTOSPACE_LIVE_TESTS") == "1"
live_only = pytest.mark.skipif(not LIVE, reason="set LOSTINTOSPACE_LIVE_TESTS=1 to run")

PS_ROWS = load_fixture("exoplanet_kepler22b.json")
COMP_ROWS = load_fixture("exoplanet_pscomppars_kepler22b.json")
EMPTY = load_fixture("exoplanet_empty.json")

VOTABLE_ERROR = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">\n'
    '<RESOURCE type="results">\n'
    '<INFO name="QUERY_STATUS" value="ERROR">\n'
    "ORA-00904: 'NONEXISTENT_COL': invalid identifier\n"
    "</INFO>\n</RESOURCE>\n</VOTABLE>\n"
)


def archive_record(row, table=PSCOMPPARS_TABLE) -> SourceRecord:
    source = build_source("nasa_exoplanet_archive")
    payload = dict(row, _table=table)
    return SourceRecord(
        source_name="nasa_exoplanet_archive",
        source_record_id=row.get("pl_name"),
        payload=payload,
        source_reference=source.build_source_reference(record_id=row.get("pl_name")),
    )


#: `AdqlError` subclasses `ValueError`, so pydantic wraps it in a
#: `ValidationError` when it is raised inside a field/model validator. Either
#: type means the unsafe input was refused; the message is preserved in both.
REFUSED = (AdqlError, ValidationError)


class TestAdqlSafety:
    def test_basic_query_renders(self):
        query = AdqlQuery(
            table="ps",
            columns=["pl_name", "hostname"],
            predicates=[Predicate(column="pl_name", value="Kepler-22 b")],
            limit=5,
            order_by="pl_name",
        )
        assert query.render() == (
            "select top 5 pl_name, hostname from ps where pl_name = 'Kepler-22 b' "
            "order by pl_name asc"
        )

    def test_string_literals_escape_embedded_quotes(self):
        assert quote_literal("O'Brien") == "'O''Brien'"

    def test_injection_attempt_is_escaped_not_executed(self):
        predicate = Predicate(column="pl_name", value="x'; drop table ps; --")
        rendered = predicate.render()
        assert rendered == "pl_name = 'x''; drop table ps; --'"
        # The payload survives as data; it never terminates the statement.
        assert rendered.count("'") % 2 == 0

    def test_injection_in_a_column_name_is_rejected(self):
        with pytest.raises(REFUSED, match="not a valid ADQL identifier"):
            Predicate(column="pl_name; drop table ps", value="x")

    def test_injection_in_a_table_name_is_rejected(self):
        with pytest.raises(REFUSED, match="not a valid ADQL identifier"):
            AdqlQuery(table="ps; drop table x", columns=["pl_name"])

    def test_comment_marker_in_column_rejected(self):
        with pytest.raises(REFUSED, match="not a valid ADQL identifier"):
            AdqlQuery(table="ps", columns=["pl_name --"])

    def test_control_characters_in_literals_rejected(self):
        with pytest.raises(AdqlError, match="control characters"):
            quote_literal("abc\ndef")

    def test_numeric_values_are_not_quoted(self):
        assert Predicate(column="disc_year", value=2011).render() == "disc_year = 2011"

    def test_in_requires_a_list(self):
        with pytest.raises(REFUSED, match="IN requires a list"):
            Predicate(column="pl_name", operator=Comparison.IN, value="Kepler-22 b")

    def test_in_renders_each_value(self):
        rendered = Predicate(
            column="pl_name", operator=Comparison.IN, value=["a", "b"]
        ).render()
        assert rendered == "pl_name in ('a', 'b')"

    def test_null_operators_take_no_value(self):
        with pytest.raises(REFUSED, match="takes no value"):
            Predicate(column="pl_rade", operator=Comparison.IS_NULL, value=1)
        assert (
            Predicate(column="pl_rade", operator=Comparison.IS_NULL).render()
            == "pl_rade is null"
        )

    def test_unknown_column_rejected_against_allow_list(self):
        query = AdqlQuery(table="ps", columns=["pl_name", "secret_column"])
        with pytest.raises(AdqlError, match="not in the allow-list"):
            query.validate_against(PS_COLUMNS)

    def test_allow_list_covers_the_columns_we_request(self):
        for table, columns in TABLE_COLUMNS.items():
            query = AdqlQuery(table=table, columns=list(columns))
            query.validate_against(columns)

    def test_limit_is_bounded(self):
        with pytest.raises(Exception):
            AdqlQuery(table="ps", columns=["pl_name"], limit=999_999)


class TestArchiveAdapter:
    async def test_search_builds_a_validated_query(self):
        provider = MockProvider("nasa_exoplanet_archive").route(
            "/TAP/sync", MockEndpoint(json=COMP_ROWS)
        )
        source = build_source("nasa_exoplanet_archive", transport=provider.transport)
        page = await source.search(SourceQuery(identifier="Kepler-22 b"))
        assert len(page.records) == 1
        sent = provider.last_params()["query"]
        assert sent.startswith("select top")
        assert "from pscomppars" in sent
        assert "pl_name = 'Kepler-22 b'" in sent
        await source.aclose()

    async def test_ps_table_selected_explicitly(self):
        provider = MockProvider("nasa_exoplanet_archive").route(
            "/TAP/sync", MockEndpoint(json=PS_ROWS)
        )
        source = build_source("nasa_exoplanet_archive", transport=provider.transport)
        page = await source.search(
            SourceQuery(identifier="Kepler-22 b", extra={"table": PS_TABLE})
        )
        assert "from ps " in provider.last_params()["query"]
        assert len(page.records) == len(PS_ROWS)
        await source.aclose()

    async def test_unknown_table_refused_before_the_request(self):
        provider = MockProvider("nasa_exoplanet_archive")
        source = build_source("nasa_exoplanet_archive", transport=provider.transport)
        with pytest.raises(AdqlError, match="not in the allow-list"):
            await source.search(SourceQuery(text="x", extra={"table": "users"}))
        assert provider.call_count == 0
        await source.aclose()

    async def test_unfiltered_scan_refused(self):
        source = build_source("nasa_exoplanet_archive")
        with pytest.raises(SourceResponseError, match="unfiltered table scans are refused"):
            await source.search(SourceQuery(extra={"table": PSCOMPPARS_TABLE, "x": 1}))
        await source.aclose()

    async def test_empty_result_is_not_an_error(self):
        provider = MockProvider("nasa_exoplanet_archive").route(
            "/TAP/sync", MockEndpoint(json=EMPTY)
        )
        source = build_source("nasa_exoplanet_archive", transport=provider.transport)
        page = await source.search(SourceQuery(identifier="Nonexistent Planet zz"))
        assert page.records == []
        assert page.total_available == 0
        await source.aclose()

    async def test_votable_error_is_surfaced_as_a_message(self):
        provider = MockProvider("nasa_exoplanet_archive").route(
            "/TAP/sync", MockEndpoint(status=400, text=VOTABLE_ERROR)
        )
        source = build_source("nasa_exoplanet_archive", transport=provider.transport)
        with pytest.raises(SourceResponseError, match="ORA-00904"):
            await source.search(SourceQuery(identifier="Kepler-22 b"))
        await source.aclose()

    async def test_network_failure_surfaces_as_unavailable(self):
        from data.sources import SourceUnavailableError

        provider = MockProvider("nasa_exoplanet_archive").route(
            "/TAP/sync", MockEndpoint(raises=httpx.ConnectError("refused"))
        )
        source = build_source("nasa_exoplanet_archive", transport=provider.transport)
        source.client._sleep = FakeSleeper()
        with pytest.raises(SourceUnavailableError):
            await source.search(SourceQuery(identifier="Kepler-22 b"))
        await source.aclose()

    async def test_fetch_by_id_returns_one_record(self):
        provider = MockProvider("nasa_exoplanet_archive").route(
            "/TAP/sync", MockEndpoint(json=COMP_ROWS)
        )
        source = build_source("nasa_exoplanet_archive", transport=provider.transport)
        record = await source.fetch_by_id("Kepler-22 b")
        assert record.source_record_id == "Kepler-22 b"
        await source.aclose()

    async def test_fetch_by_id_returns_none_when_absent(self):
        provider = MockProvider("nasa_exoplanet_archive").route(
            "/TAP/sync", MockEndpoint(json=EMPTY)
        )
        source = build_source("nasa_exoplanet_archive", transport=provider.transport)
        assert await source.fetch_by_id("Nonexistent Planet zz") is None
        await source.aclose()

    async def test_host_star_filter_is_parameterized(self):
        provider = MockProvider("nasa_exoplanet_archive").route(
            "/TAP/sync", MockEndpoint(json=COMP_ROWS)
        )
        source = build_source("nasa_exoplanet_archive", transport=provider.transport)
        await source.search(SourceQuery(text="b", extra={"hostname": "Kepler-22"}))
        assert "hostname = 'Kepler-22'" in provider.last_params()["query"]
        await source.aclose()


class TestDisposition:
    def test_confirmed_and_candidate_are_distinguished(self):
        assert map_disposition("Published Confirmed") is DataStatus.CONFIRMED
        assert map_disposition("Published Candidate") is DataStatus.CANDIDATE
        assert map_disposition("TESS Project Candidate") is DataStatus.CANDIDATE

    def test_false_positive_is_deprecated(self):
        assert map_disposition("False Positive") is DataStatus.DEPRECATED
        assert map_disposition("Refuted") is DataStatus.DEPRECATED

    def test_unrecognised_disposition_is_never_confirmed(self):
        assert map_disposition("Something New") is DataStatus.UNKNOWN

    def test_missing_soltype_defaults_to_unknown_except_for_pscomppars(self):
        assert map_disposition(None) is DataStatus.UNKNOWN
        assert map_disposition(None, "ps") is DataStatus.UNKNOWN
        assert map_disposition(None, "pscomppars") is DataStatus.CONFIRMED


class TestExoplanetNormalization:
    def _default_row(self):
        return [row for row in PS_ROWS if row.get("default_flag") == 1][0]

    def test_produces_a_planet_marked_as_an_exoplanet(self):
        planet, _, _ = normalize_exoplanet_row(archive_record(COMP_ROWS[0]))
        assert isinstance(planet, Planet)
        assert planet.is_exoplanet is True
        assert planet.object_type is ObjectType.EXOPLANET
        assert planet.canonical_id == "exoplanet:kepler-22-b"
        assert planet.host_star_name == "Kepler-22"

    def test_radius_and_mass_use_astronomical_units(self):
        planet, _, _ = normalize_exoplanet_row(archive_record(COMP_ROWS[0]))
        radius = planet.physical.radius_mean
        assert radius.unit == "R_earth"
        assert radius.value == pytest.approx(2.10)
        assert planet.physical.mass.unit == "M_earth"
        assert planet.physical.mass.value == pytest.approx(9.10)

    def test_asymmetric_error_bars_preserved(self):
        planet, _, _ = normalize_exoplanet_row(archive_record(COMP_ROWS[0]))
        radius = planet.physical.radius_mean
        assert radius.uncertainty is None
        assert radius.uncertainty_upper == pytest.approx(0.12)
        # err2 is published negative; magnitude is what matters.
        assert radius.uncertainty_lower == pytest.approx(0.12)

    def test_orbital_parameters_are_not_passed_off_as_an_orbit_record(self):
        """The archive gives no epoch or frame, so an OrbitRecord would be a lie."""
        planet, _, _ = normalize_exoplanet_row(archive_record(COMP_ROWS[0]))
        assert planet.orbits == []
        parameters = planet.source_specific["orbital_parameters"]
        assert parameters["orbital_period"]["value"] == pytest.approx(289.863876)
        assert parameters["orbital_period"]["unit"] == "d"
        assert parameters["semi_major_axis"]["unit"] == "au"

    def test_discovery_information_mapped(self):
        planet, _, _ = normalize_exoplanet_row(archive_record(COMP_ROWS[0]))
        assert planet.discovery.discovery_year == 2011
        assert planet.discovery.discovery_method == "Transit"
        assert planet.discovery.discovery_facility == "Kepler"

    def test_reference_markup_stripped_to_a_citation(self):
        planet, _, _ = normalize_exoplanet_row(archive_record(self._default_row(), PS_TABLE))
        citation = planet.source_specific["planet_reference"]
        assert "<" not in citation
        assert "Bonomo" in citation

    def test_strip_markup_handles_plain_text(self):
        assert strip_reference_markup("Bonomo et al. 2023") == "Bonomo et al. 2023"
        assert strip_reference_markup(None) is None

    def test_ps_row_carries_its_disposition(self):
        planet, _, _ = normalize_exoplanet_row(archive_record(self._default_row(), PS_TABLE))
        assert planet.data_status is DataStatus.CONFIRMED
        assert planet.source_specific["soltype"] == "Published Confirmed"
        assert planet.source_specific["default_flag"] == 1

    def test_candidate_row_is_not_promoted(self):
        row = dict(COMP_ROWS[0])
        row["soltype"] = "Published Candidate"
        planet, _, _ = normalize_exoplanet_row(archive_record(row, PS_TABLE))
        assert planet.data_status is DataStatus.CANDIDATE
        assert planet.data_status is not DataStatus.CONFIRMED

    def test_host_star_built_from_stellar_columns(self):
        _, star, _ = normalize_exoplanet_row(archive_record(COMP_ROWS[0]))
        assert isinstance(star, Star)
        assert star.canonical_id == "star:kepler-22"
        assert star.is_host_star is True
        assert star.spectral_type == "G5 V"
        assert star.physical.effective_temperature.value == pytest.approx(5596.0)
        assert star.physical.radius_mean.unit == "R_sun"
        assert star.physical.mass.unit == "M_sun"

    def test_star_metallicity_keeps_its_ratio(self):
        _, star, _ = normalize_exoplanet_row(archive_record(COMP_ROWS[0]))
        assert star.metallicity.value == pytest.approx(-0.2550)
        assert star.metallicity_ratio == "[Fe/H]"

    def test_star_metallicity_dropped_when_ratio_absent(self):
        row = dict(COMP_ROWS[0])
        row["st_metratio"] = None
        _, star, _ = normalize_exoplanet_row(archive_record(row))
        assert star.metallicity is None
        # The rest of the star survives.
        assert star.physical.effective_temperature is not None

    def test_no_star_when_row_has_no_stellar_columns(self):
        row = {"pl_name": "X b", "hostname": "X", "_table": "pscomppars"}
        _, star, _ = normalize_exoplanet_row(archive_record(row))
        assert star is None

    def test_row_without_a_name_is_rejected(self):
        with pytest.raises(ValueError, match="no pl_name"):
            normalize_exoplanet_row(archive_record({"hostname": "X"}))

    def test_distance_requires_context(self):
        planet, _, _ = normalize_exoplanet_row(archive_record(COMP_ROWS[0]))
        assert planet.distance.unit == "pc"
        assert planet.distance_context

    def test_lineage_records_the_disposition_decision(self):
        _, _, lineage = normalize_exoplanet_row(archive_record(COMP_ROWS[0]))
        assert "data_status" in lineage.explain_field("data_status")

    def test_provenance_complete(self):
        planet, star, lineage = normalize_exoplanet_row(archive_record(COMP_ROWS[0]))
        require_provenance(planet, lineage)
        require_provenance(star, lineage)

    def test_roundtrips_through_json(self):
        planet, star, _ = normalize_exoplanet_row(archive_record(COMP_ROWS[0]))
        assert Planet.model_validate_json(planet.model_dump_json()) == planet
        assert Star.model_validate_json(star.model_dump_json()) == star

    def test_multiple_ps_rows_are_separate_published_solutions(self):
        """`ps` holds one row per reference; they are not merged silently."""
        planets = [normalize_exoplanet_row(archive_record(row, PS_TABLE))[0]
                   for row in PS_ROWS]
        assert len(planets) > 1
        radii = {
            planet.physical.radius_mean.value
            for planet in planets
            if planet.physical.radius_mean is not None
        }
        assert len(radii) > 1


@live_only
class TestExoplanetLive:
    async def test_known_planet_live(self):
        async with ExoplanetArchiveSource() as source:
            record = await source.fetch_by_id("Kepler-22 b")
            planet, star, _ = normalize_exoplanet_row(record)
            assert planet.name == "Kepler-22 b"
            assert star is not None

    async def test_empty_result_live(self):
        async with ExoplanetArchiveSource() as source:
            assert await source.fetch_by_id("Nonexistent Planet zz") is None
