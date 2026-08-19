"""Semantic search, and the measured retrieval quality it must hold.

The quality thresholds here are set just below numbers actually measured on the
labelled set, so they catch a regression without failing on noise. The measured
values at the time of writing are recorded next to each assertion.
"""

import pytest

from contracts.search import MatchType, SearchQuery, SearchStatus
from search.embeddings import EmbeddingService, HashedLexicalProvider
from search.evaluation import (
    EVALUATION_QUERIES,
    answerable,
    average_precision,
    evaluate,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    unanswerable,
)
from search.indexing import extract_document
from search.keyword import KeywordIndex
from search.retrieval import SemanticSearch
from search.vector_store import InMemoryVectorStore


@pytest.fixture(scope="module")
def embeddings():
    return EmbeddingService(HashedLexicalProvider())


@pytest.fixture(scope="module")
def keyword(corpus):
    index = KeywordIndex()
    index.add_records(corpus)
    return index


@pytest.fixture(scope="module")
def store(corpus, embeddings):
    engine = InMemoryVectorStore()
    documents = [extract_document(record) for record in corpus]
    engine.upsert(embeddings.embed_documents(documents).records)
    return engine


@pytest.fixture(scope="module")
def semantic(store, embeddings, keyword):
    """The production configuration: hybrid, with the lexical index attached."""
    return SemanticSearch(store, embeddings, keyword_index=keyword)


@pytest.fixture(scope="module")
def vector_only(store, embeddings, keyword):
    """Vector retrieval alone, for isolating the embedding layer."""
    return SemanticSearch(store, embeddings, documents=keyword)


def ask(retriever, question, **kwargs):
    return retriever.search(SearchQuery(text=question, **kwargs))


class TestNamedQuestions:
    """The five questions named in the task."""

    def test_staging(self, semantic):
        response = ask(semantic, "How does staging improve rocket performance?")
        assert response.status is SearchStatus.OK
        assert response.top().id == "concept:staging"

    def test_max_q(self, semantic):
        response = ask(semantic, "What causes Max-Q?")
        assert response.status is SearchStatus.OK
        assert response.top().id == "concept:max-q"

    def test_jupiter_spacecraft(self, semantic):
        response = ask(semantic, "Which spacecraft explored Jupiter?")
        assert response.status is SearchStatus.OK
        ids = {result.id for result in response.results}
        assert ids & {"mission:galileo", "mission:juno", "mission:voyager-2"}

    def test_orbital_decay(self, semantic):
        response = ask(semantic, "What causes orbital decay?")
        assert response.status is SearchStatus.OK
        assert response.top().id == "concept:orbital-decay"

    def test_gravity_assist(self, semantic):
        response = ask(semantic, "How does a gravity assist work?")
        assert response.status is SearchStatus.OK
        ids = {result.id for result in response.results}
        assert ids & {
            "concept:gravity-assist", "mission:cassini", "mission:voyager-2",
        }


class TestPipeline:
    def test_results_are_marked_semantic(self, semantic):
        response = ask(semantic, "What causes Max-Q?")
        assert response.top().match_type is MatchType.SEMANTIC

    def test_chunks_collapse_to_one_result_per_record(self, semantic):
        response = ask(semantic, "What causes Max-Q?", limit=10)
        ids = [result.id for result in response.results]
        assert len(ids) == len(set(ids))

    def test_best_chunk_is_reported(self, semantic):
        response = ask(semantic, "What causes Max-Q?")
        assert response.top().metadata["best_chunk"].startswith("concept:max-q#")

    def test_snippet_comes_from_the_matching_chunk(self, semantic):
        response = ask(semantic, "What causes Max-Q?")
        assert response.top().summary

    def test_retrieval_ranks_are_exposed(self, semantic):
        response = ask(semantic, "What causes orbital decay?")
        metadata = response.top().metadata
        assert metadata["vector_rank"] is not None or metadata["keyword_rank"]

    def test_found_by_is_reported(self, semantic):
        response = ask(semantic, "What causes Max-Q?")
        assert set(response.top().matched_fields) <= {"vector", "keyword"}

    def test_score_is_the_similarity_not_the_fused_rank(self, semantic):
        """The fused score is an internal ordering device, not a user number."""
        response = ask(semantic, "What causes Max-Q?")
        assert 0.0 <= response.top().score <= 1.0

    def test_took_ms_is_recorded(self, semantic):
        assert ask(semantic, "Apollo 11").took_ms is not None

    def test_paging(self, semantic):
        first = ask(semantic, "orbital mechanics", limit=2)
        second = ask(semantic, "orbital mechanics", limit=2, offset=2)
        assert len(first.results) <= 2
        if second.results:
            assert {r.id for r in first.results}.isdisjoint(
                {r.id for r in second.results}
            )


class TestFiltering:
    def test_entity_type_filter_applies(self, semantic):
        from contracts.search import SearchEntityType

        response = semantic.search(
            SearchQuery(
                text="Which spacecraft explored Jupiter?",
                entity_types=[SearchEntityType.MISSION],
            )
        )
        assert response.results
        assert all(
            result.entity_type is SearchEntityType.MISSION
            for result in response.results
        )

    def test_topic_filter_applies(self, semantic):
        response = semantic.search(
            SearchQuery(text="how do engines work", topics=["propulsion"])
        )
        for result in response.results:
            assert any(topic.lower() == "propulsion" for topic in result.topics)

    def test_source_filter_applies(self, semantic):
        response = semantic.search(
            SearchQuery(text="Ceres", sources=["jpl_sbdb"])
        )
        for result in response.results:
            assert "jpl_sbdb" in result.provenance.source_names

    def test_impossible_filter_yields_no_results(self, semantic):
        response = semantic.search(
            SearchQuery(text="What causes Max-Q?", sources=["no_such_source"])
        )
        assert response.results == []
        assert response.status is not SearchStatus.OK


class TestLowConfidence:
    """Weak evidence must be reported, never dressed up as an answer."""

    def test_out_of_domain_question_abstains(self, semantic):
        response = ask(semantic, "How do I file my tax return?")
        assert response.status is not SearchStatus.OK
        assert response.results == []

    def test_gibberish_abstains(self, semantic):
        response = ask(semantic, "zzqqxx wvvbb kkjjhh")
        assert response.status in (
            SearchStatus.EMPTY, SearchStatus.NO_RELIABLE_MATCH
        )
        assert response.results == []

    def test_abstention_explains_itself(self, semantic):
        response = ask(semantic, "What is the best pizza topping?")
        assert response.explanation

    def test_unknown_named_subject_abstains(self, semantic):
        """A question about a mission the corpus lacks must not be answered.

        This is the case similarity alone gets wrong: the question overlaps
        heavily with every Mars mission on its generic words.
        """
        response = ask(semantic, "What did the Beagle 2 lander discover on Mars?")
        assert response.status is SearchStatus.NO_RELIABLE_MATCH
        assert response.results == []
        assert "Beagle" in response.explanation

    def test_unknown_subject_check_does_not_block_known_ones(self, semantic):
        for question in (
            "Which ISRO mission landed near the lunar south pole?",
            "What was the first Artemis flight?",
            "Which mission visited Uranus and Neptune?",
            "What is a Hohmann transfer orbit?",
        ):
            response = ask(semantic, question)
            assert response.status is SearchStatus.OK, question

    def test_a_strong_match_survives_an_unknown_word(self, store, embeddings, keyword):
        """Strong evidence outweighs an unrecognised name."""
        retriever = SemanticSearch(
            store, embeddings, keyword_index=keyword, confident_similarity=0.0
        )
        response = retriever.search(
            SearchQuery(text="What causes Max-Q according to Zzyzx?")
        )
        assert response.status is SearchStatus.OK

    def test_similarity_threshold_is_configurable(self, store, embeddings, keyword):
        """Raising the floor withholds matches that no longer clear it."""
        strict = SemanticSearch(
            store, embeddings, documents=keyword, min_similarity=0.95
        )
        response = strict.search(SearchQuery(text="what is dynamic pressure"))
        assert response.status is SearchStatus.NO_RELIABLE_MATCH
        assert "below the confidence threshold" in response.explanation

    def test_an_exact_lexical_hit_outranks_the_similarity_floor(
        self, store, embeddings, keyword
    ):
        """A user who typed an exact title has given unambiguous intent.

        Similarity is a proxy for intent; an exact match is intent itself, so
        the floor must not suppress it.
        """
        strict = SemanticSearch(
            store, embeddings, keyword_index=keyword, min_similarity=0.95
        )
        response = strict.search(SearchQuery(text="Apollo 11"))
        assert response.status is SearchStatus.OK
        assert response.top().id == "mission:apollo-11"

    def test_margin_rule_can_require_a_clear_winner(self, store, embeddings):
        ambiguous = SemanticSearch(store, embeddings, margin=0.99)
        response = ambiguous.search(SearchQuery(text="orbital mechanics"))
        assert response.status is SearchStatus.NO_RELIABLE_MATCH
        assert "clearly the answer" in response.explanation

    def test_no_result_is_ever_returned_unattributed(self, semantic):
        for query in EVALUATION_QUERIES:
            response = ask(semantic, query.text)
            for result in response.results:
                assert result.provenance.is_attributed, query.text


class TestUnknownSubjectDetection:
    def test_finds_an_absent_proper_noun(self, keyword):
        assert keyword.unknown_proper_nouns(
            "What did the Beagle 2 lander discover on Mars?"
        ) == ["Beagle"]

    def test_known_proper_nouns_are_not_flagged(self, keyword):
        assert keyword.unknown_proper_nouns("Tell me about Apollo and Artemis") == []

    def test_sentence_initial_capital_is_ignored(self, keyword):
        """The first word is capitalized by grammar, not because it names one."""
        assert "Zzyzx" not in keyword.unknown_proper_nouns("Zzyzx is a place")

    def test_punctuation_is_stripped(self, keyword):
        assert keyword.unknown_proper_nouns("a mission called Beagle.") == ["Beagle"]

    def test_knows_reports_indexed_vocabulary(self, keyword):
        assert keyword.knows("Apollo")
        assert keyword.knows("turbopump")
        assert not keyword.knows("zzyzxqq")


class TestMetrics:
    def test_precision_at_k(self):
        assert precision_at_k(["a", "b", "c"], {"a", "c"}, 3) == pytest.approx(2 / 3)

    def test_precision_divides_by_k_not_by_results_returned(self):
        """Two results, both relevant, is not Precision@5 of 1.0."""
        assert precision_at_k(["a", "b"], {"a", "b"}, 5) == pytest.approx(0.4)

    def test_recall_at_k(self):
        assert recall_at_k(["a", "x"], {"a", "b"}, 2) == pytest.approx(0.5)

    def test_recall_is_capped_by_k(self):
        assert recall_at_k(["a", "b"], {"a", "b"}, 1) == pytest.approx(0.5)

    def test_reciprocal_rank(self):
        assert reciprocal_rank(["x", "a"], {"a"}) == pytest.approx(0.5)

    def test_reciprocal_rank_is_zero_when_nothing_is_relevant(self):
        assert reciprocal_rank(["x", "y"], {"a"}) == 0.0

    def test_average_precision(self):
        assert average_precision(["a", "x", "b"], {"a", "b"}) == pytest.approx(
            (1.0 + 2.0 / 3.0) / 2.0
        )

    def test_empty_relevant_set_scores_zero(self):
        assert precision_at_k(["a"], set(), 1) == 0.0
        assert recall_at_k(["a"], set(), 1) == 0.0

    def test_invalid_k_rejected(self):
        with pytest.raises(ValueError, match="k must be positive"):
            precision_at_k(["a"], {"a"}, 0)


class TestEvaluationSet:
    def test_at_least_thirty_queries(self):
        assert len(EVALUATION_QUERIES) >= 30

    def test_query_ids_are_unique(self):
        ids = [query.id for query in EVALUATION_QUERIES]
        assert len(ids) == len(set(ids))

    def test_answerable_queries_name_their_relevant_records(self):
        for query in answerable():
            assert query.relevant, query.id

    def test_unanswerable_queries_name_none(self):
        for query in unanswerable():
            assert query.relevant == [], query.id

    def test_the_set_includes_abstention_cases(self):
        assert len(unanswerable()) >= 3

    def test_every_relevant_id_exists_in_the_corpus(self, keyword):
        """A label pointing at a record that is not indexed measures nothing."""
        for query in answerable():
            for canonical_id in query.relevant:
                assert keyword.get(canonical_id) is not None, (
                    "{0} references missing record {1}".format(query.id, canonical_id)
                )

    def test_every_query_has_a_rationale(self):
        for query in EVALUATION_QUERIES:
            assert query.rationale, query.id


class TestMeasuredQuality:
    """Thresholds sit just below measured values, to catch regressions.

    Measured for the hybrid retriever at the time of writing:
    MRR 0.938, MAP 0.920, P@1 0.906, R@1 0.833, R@5 0.953, R@10 0.984,
    abstention precision 1.000, 0 false answers, 0 missed answers.
    """

    @pytest.fixture(scope="class")
    def summary(self, semantic):
        return evaluate(semantic)

    def test_mrr(self, summary):
        assert summary.mean_reciprocal_rank >= 0.85, summary.describe()

    def test_mean_average_precision(self, summary):
        assert summary.mean_average_precision >= 0.82, summary.describe()

    def test_precision_at_1(self, summary):
        assert summary.precision_at_k[1] >= 0.82, summary.describe()

    def test_recall_at_5(self, summary):
        assert summary.recall_at_k[5] >= 0.88, summary.describe()

    def test_recall_at_10(self, summary):
        assert summary.recall_at_k[10] >= 0.92, summary.describe()

    def test_never_answers_an_unanswerable_question(self, summary):
        """The failure that matters most for a RAG layer."""
        assert summary.false_answers == 0, summary.describe()

    def test_does_not_abstain_on_answerable_questions(self, summary):
        assert summary.missed_answers == 0, summary.describe()

    def test_abstention_precision(self, summary):
        assert summary.abstention_precision >= 0.8, summary.describe()

    def test_every_query_was_scored(self, summary):
        assert summary.queries == len(EVALUATION_QUERIES)
        assert summary.answerable_queries == len(answerable())

    def test_report_is_readable(self, summary):
        text = summary.describe()
        assert "MRR" in text and "P@1" in text and "abstentions" in text

    def test_hybrid_beats_vector_alone_on_abstention(self, semantic, vector_only):
        """Fusing lexical evidence is what makes abstention reliable."""
        hybrid = evaluate(semantic)
        vector = evaluate(vector_only)
        assert hybrid.false_answers <= vector.false_answers
        assert hybrid.mean_reciprocal_rank >= vector.mean_reciprocal_rank

    def test_keyword_alone_is_also_measurable(self, keyword):
        """The same harness scores any retriever, so they compare on equal terms."""
        summary = evaluate(keyword)
        assert summary.queries == len(EVALUATION_QUERIES)
        assert summary.mean_reciprocal_rank > 0.5
