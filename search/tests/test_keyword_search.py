"""Keyword search over the real corpus, with the queries users actually type."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from contracts.search import (
    MatchType,
    SearchEntityType,
    SearchQuery,
    SearchResult,
    SearchStatus,
    SortOrder,
)
from data.models import LearningContent
from data.seeds import build_concepts
from search.indexing import extract_document
from search.keyword import KeywordIndex, normalize, tokenize


def run(index, text, **kwargs):
    return index.search(SearchQuery(text=text, **kwargs))


class TestTokenizer:
    def test_hyphenated_terms_keep_both_forms(self):
        tokens = tokenize("Max-Q")
        assert "max" in tokens
        assert "q" in tokens
        assert "maxq" in tokens

    def test_designations_get_a_joined_form(self):
        tokens = tokenize("2024 YR4")
        assert "2024" in tokens and "yr4" in tokens
        assert "2024yr4" in tokens

    def test_international_designator(self):
        assert "1998067a" in tokenize("1998-067A")

    def test_case_and_spacing_normalized(self):
        assert normalize("  Max   Q  ") == "max q"

    def test_short_stop_words_dropped_but_meaningful_ones_kept(self):
        tokens = tokenize("the causes of orbital decay")
        assert "the" not in tokens
        assert "orbital" in tokens and "decay" in tokens

    def test_empty_input(self):
        assert tokenize("") == []
        assert tokenize(None) == []


class TestRealisticQueries:
    """The query set named in the task, run against the real corpus."""

    def test_mars(self, index):
        response = run(index, "Mars")
        assert response.status is SearchStatus.OK
        titles = [result.title for result in response.results]
        assert any("Mars" in title or "Curiosity" in title or "Perseverance" in title
                   for title in titles)

    def test_mars_missions(self, index):
        response = run(index, "Mars missions")
        assert response.status is SearchStatus.OK
        missions = [
            result for result in response.results
            if result.entity_type is SearchEntityType.MISSION
        ]
        assert missions
        assert any("Curiosity" in result.title or "Perseverance" in result.title
                   for result in missions)

    def test_jupiter_spacecraft(self, index):
        response = run(index, "Jupiter spacecraft")
        assert response.status is SearchStatus.OK
        titles = " ".join(result.title for result in response.results)
        assert "Galileo" in titles or "Juno" in titles or "Voyager" in titles

    def test_apollo(self, index):
        response = run(index, "Apollo")
        assert response.status is SearchStatus.OK
        titles = [result.title for result in response.results]
        assert any("Apollo 11" in title for title in titles)
        assert any("Apollo 13" in title for title in titles)

    def test_apollo_11_is_an_exact_match(self, index):
        response = run(index, "Apollo 11")
        top = response.top()
        assert top.title == "Apollo 11"
        assert top.match_type is MatchType.EXACT
        assert top.score > 0.5

    def test_artemis(self, index):
        response = run(index, "Artemis")
        assert response.status is SearchStatus.OK
        assert any("Artemis" in result.title for result in response.results)

    def test_max_q(self, index):
        response = run(index, "Max-Q")
        assert response.status is SearchStatus.OK
        top = response.top()
        assert "Max-Q" in top.title
        assert top.entity_type is SearchEntityType.CONCEPT

    def test_max_q_written_without_the_hyphen(self, index):
        """Users type it three different ways; all must work."""
        for spelling in ("max q", "maxq", "Max Q"):
            response = run(index, spelling)
            assert response.status is SearchStatus.OK, spelling
            assert "Max-Q" in response.top().title, spelling

    def test_orbital_mechanics(self, index):
        response = run(index, "orbital mechanics")
        assert response.status is SearchStatus.OK
        assert "Orbital mechanics" in response.top().title

    def test_liquid_propulsion(self, index):
        response = run(index, "liquid propulsion")
        assert response.status is SearchStatus.OK
        assert "Liquid propulsion" in response.top().title

    def test_exoplanets(self, index):
        response = run(index, "exoplanets")
        assert response.status is SearchStatus.OK
        assert response.results

    def test_kepler_22b_by_name(self, index):
        response = run(index, "Kepler-22 b")
        assert response.status is SearchStatus.OK
        assert response.top().title == "Kepler-22 b"

    def test_staging_question_phrasing(self, index):
        response = run(index, "staging rocket performance")
        assert response.status is SearchStatus.OK
        assert any("staging" in result.title.lower() for result in response.results)

    def test_gravity_assist(self, index):
        response = run(index, "gravity assist")
        assert "Gravity assist" in response.top().title

    def test_orbital_decay(self, index):
        response = run(index, "orbital decay")
        assert "Orbital decay" in response.top().title


class TestMatchModes:
    def test_exact_title(self, index):
        assert run(index, "Juno").top().title == "Juno"

    def test_alias_match(self, index):
        """The ISS is catalogued as "ISS (ZARYA)" but users type "ISS"."""
        response = run(index, "International Space Station")
        assert any("ISS" in result.title for result in response.results)

    def test_prefix_match(self, index):
        response = run(index, "propuls")
        assert response.status is SearchStatus.OK
        assert response.results

    def test_partial_body_match(self, index):
        response = run(index, "turbopump")
        assert response.status is SearchStatus.OK
        assert "Liquid propulsion" in response.top().title

    def test_identifier_paste_in(self, index):
        response = run(index, "25544")
        assert response.status is SearchStatus.OK
        assert response.top().metadata["record_type"] == "space_station"

    def test_matched_fields_are_reported(self, index):
        response = run(index, "Max-Q")
        assert response.top().matched_fields

    def test_score_is_bounded(self, index):
        for result in run(index, "Apollo").results:
            assert 0.0 <= result.score <= 1.0


class TestNoReliableMatch:
    def test_nonsense_query_returns_empty(self, index):
        response = run(index, "zzzqqqxxwv")
        assert response.status is SearchStatus.EMPTY
        assert response.results == []
        assert "no indexed record matched" in response.explanation

    def test_weak_match_is_withheld_rather_than_presented(self):
        """A single weak body token must not become an answer."""
        index = KeywordIndex(reliability_floor=0.9)
        index.add_records(build_concepts())
        response = index.search(SearchQuery(text="the"))
        assert response.status in (SearchStatus.EMPTY, SearchStatus.NO_RELIABLE_MATCH)
        assert response.results == []

    def test_no_reliable_match_explains_itself(self):
        index = KeywordIndex(reliability_floor=0.99)
        index.add_records(build_concepts())
        response = index.search(SearchQuery(text="pressure"))
        if response.status is SearchStatus.NO_RELIABLE_MATCH:
            assert "reliability threshold" in response.explanation
            assert response.results == []

    def test_reliable_result_is_not_withheld(self, index):
        response = run(index, "Max-Q")
        assert response.status is SearchStatus.OK
        assert response.is_reliable


class TestFilters:
    def test_filter_by_entity_type(self, index):
        response = run(index, "Mars", entity_types=[SearchEntityType.MISSION])
        assert response.results
        assert all(
            result.entity_type is SearchEntityType.MISSION
            for result in response.results
        )

    def test_filter_by_source(self, index):
        response = run(index, "Ceres", sources=["jpl_sbdb"])
        assert response.results
        for result in response.results:
            assert "jpl_sbdb" in result.provenance.source_names

    def test_filter_by_source_type(self, index):
        from contracts.provenance import SourceType

        response = index.search(
            SearchQuery(text="", source_types=[SourceType.SECONDARY_OPERATIONAL])
        )
        assert response.results
        for result in response.results:
            assert any(
                reference.source_type is SourceType.SECONDARY_OPERATIONAL
                for reference in result.provenance.sources
            )

    def test_filter_by_object_type(self, index):
        response = index.search(SearchQuery(text="", object_types=["ASTEROID"]))
        assert response.results
        assert all(result.object_type == "ASTEROID" for result in response.results)

    def test_filter_by_topic(self, index):
        response = index.search(SearchQuery(text="", topics=["propulsion"]))
        assert response.results
        for result in response.results:
            assert any(topic.lower() == "propulsion" for topic in result.topics)

    def test_filter_by_mission(self, index):
        response = index.search(SearchQuery(text="", missions=["mission:apollo-11"]))
        assert response.results
        assert response.results[0].id == "mission:apollo-11"

    def test_filter_by_date_range(self, index):
        response = index.search(
            SearchQuery(
                text="",
                entity_types=[SearchEntityType.MISSION],
                start_date=datetime(1960, 1, 1, tzinfo=timezone.utc),
                end_date=datetime(1975, 1, 1, tzinfo=timezone.utc),
            )
        )
        titles = [result.title for result in response.results]
        assert "Apollo 11" in titles
        assert "Artemis I" not in titles

    def test_filters_combine_with_and(self, index):
        response = run(
            index, "Mars",
            entity_types=[SearchEntityType.MISSION],
            topics=["rover"],
        )
        for result in response.results:
            assert result.entity_type is SearchEntityType.MISSION
            assert any(topic.lower() == "rover" for topic in result.topics)

    def test_browse_query_needs_no_text(self, index):
        response = index.search(SearchQuery(text="", entity_types=[SearchEntityType.CONCEPT]))
        assert response.results
        assert response.status is SearchStatus.OK

    def test_empty_query_with_no_filters_is_rejected(self):
        with pytest.raises(ValidationError, match="needs query text or at least one"):
            SearchQuery(text="")


class TestSortingAndPaging:
    def test_relevance_is_the_default_order(self, index):
        response = run(index, "Apollo")
        scores = [result.score for result in response.results]
        assert scores == sorted(scores, reverse=True)

    def test_sort_by_newest(self, index):
        response = index.search(
            SearchQuery(text="", entity_types=[SearchEntityType.MISSION],
                        sort=SortOrder.NEWEST, limit=5)
        )
        dates = [result.date for result in response.results if result.date]
        assert dates == sorted(dates, reverse=True)

    def test_sort_by_title(self, index):
        response = index.search(
            SearchQuery(text="", entity_types=[SearchEntityType.CONCEPT],
                        sort=SortOrder.TITLE, limit=20)
        )
        titles = [result.title.lower() for result in response.results]
        assert titles == sorted(titles)

    def test_paging(self, index):
        first = index.search(
            SearchQuery(text="", entity_types=[SearchEntityType.CONCEPT], limit=3)
        )
        second = index.search(
            SearchQuery(text="", entity_types=[SearchEntityType.CONCEPT],
                        limit=3, offset=3)
        )
        assert len(first.results) == 3
        assert first.total == second.total
        assert {r.id for r in first.results}.isdisjoint({r.id for r in second.results})

    def test_has_more_flag(self, index):
        response = index.search(
            SearchQuery(text="", entity_types=[SearchEntityType.CONCEPT], limit=2)
        )
        assert response.has_more


class TestSourceDisplay:
    def test_every_scientific_result_exposes_its_source(self, index):
        response = index.search(
            SearchQuery(text="", entity_types=[SearchEntityType.SPACE_OBJECT], limit=50)
        )
        assert response.results
        for result in response.results:
            assert result.provenance.is_attributed
            assert result.provenance.source_names
            assert result.provenance.attribution

    def test_a_scientific_result_cannot_be_built_unattributed(self):
        """Enforced by the contract, not by convention."""
        with pytest.raises(ValidationError, match="must carry source metadata"):
            SearchResult(
                id="asteroid:1",
                entity_type=SearchEntityType.SPACE_OBJECT,
                title="1 Ceres",
                score=0.9,
            )

    def test_editorial_content_may_be_unattributed_in_the_contract(self):
        """A concept is written by us, so the archive rule does not apply."""
        result = SearchResult(
            id="concept:max-q",
            entity_type=SearchEntityType.CONCEPT,
            title="Max-Q",
            score=0.9,
        )
        assert result.entity_type is SearchEntityType.CONCEPT

    def test_seed_content_still_carries_editorial_provenance(self, index):
        response = run(index, "Max-Q")
        provenance = response.top().provenance
        assert provenance.is_attributed
        assert provenance.sources[0].source_type.value == "EDITORIAL"

    def test_response_lists_contributing_sources(self, index):
        response = run(index, "Ceres")
        assert "jpl_sbdb" in response.source_names()

    def test_freshness_is_carried_through_to_results(self, index):
        response = run(index, "ISS")
        result = [r for r in response.results if "ISS" in r.title][0]
        assert result.provenance.freshness_class is not None

    def test_index_does_not_declare_records_live_on_its_own(self, index):
        response = index.search(
            SearchQuery(
                text="",
                entity_types=[
                    SearchEntityType.SPACE_OBJECT,
                    SearchEntityType.MISSION,
                    SearchEntityType.CONCEPT,
                    SearchEntityType.DOCUMENT,
                    SearchEntityType.EVENT,
                ],
                limit=100,
            )
        )
        assert all(
            result.provenance.may_present_as_live is False
            for result in response.results
        )


class TestLiveIndexing:
    def test_a_newly_ingested_record_is_searchable_without_code_changes(self):
        """The Task 15 'live data' requirement, exercised directly."""
        index = KeywordIndex()
        index.add_records(build_concepts())
        assert index.search(SearchQuery(text="Hohmann")).results

        from contracts.provenance import SourceReference, SourceType
        from data.models import Asteroid

        newcomer = Asteroid(
            canonical_id="asteroid:99999",
            name="99999 Testbody",
            aliases=["Testbody"],
            designation="99999",
            source_references=[
                SourceReference(source_name="jpl_sbdb",
                                source_type=SourceType.PRIMARY_SCIENTIFIC)
            ],
        )
        index.add_record(newcomer)
        response = index.search(SearchQuery(text="Testbody"))
        assert response.top().id == "asteroid:99999"

    def test_an_unknown_record_type_is_still_indexed(self):
        """A record type the extractor has never seen must not be dropped."""
        from contracts.provenance import SourceReference, SourceType
        from data.models import CanonicalRecord, NamedRecord

        class FutureRecord(NamedRecord):
            record_type: str = "future_thing"
            gadget: str = ""

        index = KeywordIndex()
        index.add_record(
            FutureRecord(
                canonical_id="future:1",
                name="Quantum Sail Demonstrator",
                gadget="lightsail propulsion testbed",
                source_references=[
                    SourceReference(source_name="bundled_reference",
                                    source_type=SourceType.BUNDLED_REFERENCE)
                ],
            )
        )
        response = index.search(SearchQuery(text="lightsail"))
        assert response.results
        assert response.top().id == "future:1"
        assert response.top().entity_type is SearchEntityType.UNKNOWN

    def test_reindexing_replaces_rather_than_duplicates(self, corpus):
        index = KeywordIndex()
        index.add_records(corpus)
        size = len(index)
        index.add_records(corpus)
        assert len(index) == size

    def test_removal(self):
        index = KeywordIndex()
        index.add_records(build_concepts())
        assert index.remove("concept:max-q") is True
        assert index.search(SearchQuery(text="Max-Q")).status is not SearchStatus.OK
        assert index.remove("concept:max-q") is False


class TestSuggestions:
    def test_prefix_suggestions(self, index):
        assert any("Apollo" in item for item in index.suggest("apo"))

    def test_suggestions_include_aliases(self, index):
        suggestions = index.suggest("max")
        assert any("Max" in item for item in suggestions)

    def test_empty_prefix_returns_nothing(self, index):
        assert index.suggest("") == []


class TestFacets:
    def test_facets_are_computed_on_request(self, index):
        response = index.search(SearchQuery(text="Mars", include_facets=True))
        names = {facet.name for facet in response.facets}
        assert {"entity_type", "source", "topic"} == names

    def test_facets_absent_by_default(self, index):
        assert run(index, "Mars").facets == []


class TestDocumentExtraction:
    def test_concept_extraction_captures_keywords_and_equations(self):
        concept = [c for c in build_concepts() if c.slug == "max-q"][0]
        document = extract_document(concept)
        assert document.entity_type is SearchEntityType.CONCEPT
        assert "dynamic pressure" in document.fields["keywords"]
        assert "rho" in document.fields["body"]

    def test_document_text_is_usable_for_embedding(self):
        concept = [c for c in build_concepts() if c.slug == "staging"][0]
        text = extract_document(concept).text()
        assert "rocket equation" in text.lower()
        assert len(text) > 200

    def test_extraction_never_loses_provenance(self, corpus):
        for record in corpus:
            document = extract_document(record)
            assert document.provenance.sources, record.canonical_id
