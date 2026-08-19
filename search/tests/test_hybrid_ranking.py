"""Hybrid search: fusion, normalization, reranking, and the measured gain."""

from datetime import datetime, timezone

import pytest

from contracts.provenance import FreshnessClass
from contracts.search import SearchEntityType, SearchQuery, SearchStatus
from search.embeddings import EmbeddingService, HashedLexicalProvider, TrustLevel
from search.evaluation import evaluate
from search.indexing import extract_document
from search.keyword import KeywordIndex
from search.ranking import (
    HeuristicReranker,
    HybridSearch,
    IntentAssessment,
    NormalizationMethod,
    NoOpReranker,
    QueryIntent,
    RerankCandidate,
    Reranker,
    RerankWeights,
    RetrieverResult,
    classify_intent,
    normalize_scores,
    reciprocal_rank_fusion,
    weighted_score_fusion,
)
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
def semantic(corpus, embeddings, keyword):
    store = InMemoryVectorStore()
    store.upsert(
        embeddings.embed_documents([extract_document(r) for r in corpus]).records
    )
    return SemanticSearch(store, embeddings, keyword_index=keyword)


@pytest.fixture(scope="module")
def hybrid(keyword, semantic):
    return HybridSearch(keyword, semantic)


def candidate(id="x", relevance=0.5, **kwargs):
    return RerankCandidate(id=id, relevance=relevance, **kwargs)


class TestNormalization:
    def test_min_max_maps_to_unit_range(self):
        assert normalize_scores([2.0, 4.0, 6.0]) == [0.0, 0.5, 1.0]

    def test_min_max_of_identical_scores_is_neutral(self):
        """All-equal scores expressed no preference; 1.0 would assert one."""
        assert normalize_scores([3.0, 3.0, 3.0]) == [0.5, 0.5, 0.5]

    def test_z_score_is_bounded(self):
        values = normalize_scores(
            [1.0, 2.0, 3.0, 100.0], NormalizationMethod.Z_SCORE
        )
        assert all(0.0 <= value <= 1.0 for value in values)

    def test_z_score_preserves_order(self):
        values = normalize_scores([1.0, 5.0, 3.0], NormalizationMethod.Z_SCORE)
        assert values[1] > values[2] > values[0]

    def test_none_leaves_scores_alone(self):
        assert normalize_scores([0.3, 7.0], NormalizationMethod.NONE) == [0.3, 7.0]

    def test_empty_input(self):
        assert normalize_scores([]) == []


class TestFusion:
    def test_rrf_combines_ranks_not_scores(self):
        """A wildly-scaled score must not dominate; only rank matters."""
        results = [
            RetrieverResult(retriever="a", ids=["x", "y"], scores=[0.9, 0.8]),
            RetrieverResult(retriever="b", ids=["y", "x"], scores=[1000.0, 1.0]),
        ]
        fused = reciprocal_rank_fusion(results)
        #: Both appear at rank 1 and 2 once each, so they tie despite b's scale.
        assert fused[0].fused_score == pytest.approx(fused[1].fused_score)

    def test_rrf_rewards_agreement(self):
        results = [
            RetrieverResult(retriever="a", ids=["x", "y", "z"], scores=[1, 1, 1]),
            RetrieverResult(retriever="b", ids=["x", "z", "y"], scores=[1, 1, 1]),
        ]
        fused = reciprocal_rank_fusion(results)
        assert fused[0].id == "x"
        assert fused[0].retriever_count == 2

    def test_absence_contributes_nothing_rather_than_zero(self):
        """Not retrieved is not the same as scored zero."""
        results = [
            RetrieverResult(retriever="a", ids=["x"], scores=[0.9]),
            RetrieverResult(retriever="b", ids=["y"], scores=[0.9]),
        ]
        fused = reciprocal_rank_fusion(results)
        assert {item.id for item in fused} == {"x", "y"}
        assert all(item.retriever_count == 1 for item in fused)

    def test_weights_shift_the_fusion(self):
        results = [
            RetrieverResult(retriever="a", ids=["x", "y"], scores=[1, 1], weight=5.0),
            RetrieverResult(retriever="b", ids=["y", "x"], scores=[1, 1], weight=1.0),
        ]
        assert reciprocal_rank_fusion(results)[0].id == "x"

    def test_weighted_fusion_normalizes_first(self):
        """The whole point: incompatible scales are reconciled before summing."""
        results = [
            RetrieverResult(retriever="a", ids=["x", "y"], scores=[0.9, 0.1]),
            RetrieverResult(retriever="b", ids=["y", "x"], scores=[9000.0, 1000.0]),
        ]
        fused = weighted_score_fusion(results)
        for item in fused:
            for value in item.normalized_scores.values():
                assert 0.0 <= value <= 1.0

    def test_raw_scores_are_retained_unmodified(self):
        results = [RetrieverResult(retriever="a", ids=["x"], scores=[0.77])]
        fused = weighted_score_fusion(results)
        assert fused[0].raw_scores["a"] == 0.77

    def test_fused_candidate_explains_itself(self):
        results = [
            RetrieverResult(retriever="keyword", ids=["x"], scores=[0.5]),
            RetrieverResult(retriever="vector", ids=["x"], scores=[0.3]),
        ]
        text = reciprocal_rank_fusion(results)[0].explain()
        assert "keyword#1" in text and "vector#1" in text

    def test_found_by_lists_the_retrievers(self):
        results = [
            RetrieverResult(retriever="keyword", ids=["x"], scores=[0.5]),
            RetrieverResult(retriever="vector", ids=["x"], scores=[0.3]),
        ]
        assert reciprocal_rank_fusion(results)[0].found_by == ["keyword", "vector"]

    def test_empty_input_fuses_to_nothing(self):
        assert reciprocal_rank_fusion([]) == []


class TestIntent:
    def test_bare_identifier_is_a_lookup(self):
        assessment = classify_intent("25544")
        assert assessment.intent is QueryIntent.LOOKUP
        assert assessment.confidence > 0.9

    def test_short_name_is_a_lookup(self):
        assert classify_intent("Ceres").intent is QueryIntent.LOOKUP

    def test_how_question_is_conceptual(self):
        assert classify_intent(
            "How does staging improve rocket performance?"
        ).intent is QueryIntent.CONCEPTUAL

    def test_what_causes_is_conceptual(self):
        assert classify_intent("What causes Max-Q?").intent is QueryIntent.CONCEPTUAL

    def test_plural_category_is_exploratory(self):
        assert classify_intent("Mars missions").intent is QueryIntent.EXPLORATORY

    def test_comparison(self):
        assert classify_intent(
            "compare Falcon 9 and Saturn V"
        ).intent is QueryIntent.COMPARISON

    def test_temporal_marker_makes_it_current_state(self):
        assessment = classify_intent("Where is the ISS right now?")
        assert assessment.intent is QueryIntent.CURRENT_STATE
        assert assessment.is_time_sensitive

    def test_latest_is_time_sensitive(self):
        assert classify_intent("latest mission status").is_time_sensitive

    def test_time_sensitivity_survives_a_conceptual_reading(self):
        """Both facts matter; losing the second would let stale data through."""
        assessment = classify_intent(
            "How does orbital decay affect the ISS right now?"
        )
        assert assessment.intent is QueryIntent.CONCEPTUAL
        assert assessment.is_time_sensitive is True

    def test_ordinary_question_is_not_time_sensitive(self):
        assert not classify_intent("What causes orbital decay?").is_time_sensitive

    def test_signals_are_recorded(self):
        assert classify_intent("Where is the ISS now?").signals

    def test_empty_query(self):
        assert classify_intent("").intent is QueryIntent.UNKNOWN


class TestReranker:
    def test_implements_the_interface(self):
        assert isinstance(HeuristicReranker(), Reranker)
        assert isinstance(NoOpReranker(), Reranker)

    def test_no_op_preserves_order(self):
        candidates = [candidate("a", 0.1), candidate("b", 0.9)]
        ranked = NoOpReranker().rerank("q", candidates, top_k=2)
        assert [item.id for item in ranked] == ["a", "b"]

    def test_relevance_dominates(self):
        """An authoritative irrelevant record must not outrank a relevant one."""
        ranked = HeuristicReranker().rerank(
            "q",
            [
                candidate("relevant", 1.0, trust_level=TrustLevel.LOW),
                candidate("authoritative", 0.0,
                          trust_level=TrustLevel.AUTHORITATIVE),
            ],
            top_k=2,
        )
        assert ranked[0].id == "relevant"

    def test_authority_breaks_a_relevance_tie(self):
        ranked = HeuristicReranker().rerank(
            "q",
            [
                candidate("low", 0.5, trust_level=TrustLevel.LOW),
                candidate("high", 0.5, trust_level=TrustLevel.AUTHORITATIVE),
            ],
            top_k=2,
        )
        assert ranked[0].id == "high"

    def test_stale_record_is_penalised_for_a_current_question(self):
        """Equal relevance, so the freshness signal is what decides."""
        intent = IntentAssessment(
            intent=QueryIntent.CURRENT_STATE, confidence=0.9, is_time_sensitive=True
        )
        ranked = HeuristicReranker().rerank(
            "where is it now",
            [
                candidate("stale", 0.5, is_stale=True,
                          source_names=["celestrak_gp"]),
                candidate("fresh", 0.5,
                          freshness_class=FreshnessClass.NEAR_REAL_TIME,
                          source_names=["celestrak_gp"]),
            ],
            top_k=2,
            intent=intent,
        )
        assert ranked[0].id == "fresh"

    def test_freshness_cannot_override_a_clear_relevance_gap(self):
        """Deliberate: a stale record that is actually about the question beats
        a fresh one that is not. Freshness is a correction, not a veto."""
        intent = IntentAssessment(
            intent=QueryIntent.CURRENT_STATE, confidence=0.9, is_time_sensitive=True
        )
        ranked = HeuristicReranker().rerank(
            "where is it now",
            [
                candidate("stale-but-relevant", 0.9, is_stale=True,
                          source_names=["celestrak_gp"]),
                candidate("fresh-but-not", 0.1,
                          freshness_class=FreshnessClass.NEAR_REAL_TIME,
                          source_names=["celestrak_gp"]),
            ],
            top_k=2,
            intent=intent,
        )
        assert ranked[0].id == "stale-but-relevant"

    def test_historical_record_is_not_penalised_for_an_ordinary_question(self):
        """A 1969 mission is not worse for being old."""
        intent = IntentAssessment(intent=QueryIntent.LOOKUP, confidence=0.9)
        reranker = HeuristicReranker()
        old = reranker.score(
            candidate("old", 0.5, freshness_class=FreshnessClass.HISTORICAL), intent
        )
        new = reranker.score(
            candidate("new", 0.5, freshness_class=FreshnessClass.RECENT), intent
        )
        assert old["freshness"] >= new["freshness"] * 0.8

    def test_conceptual_intent_prefers_written_explanation(self):
        intent = IntentAssessment(intent=QueryIntent.CONCEPTUAL, confidence=0.9)
        ranked = HeuristicReranker().rerank(
            "how does it work",
            [
                candidate("object", 0.5, entity_type=SearchEntityType.SPACE_OBJECT),
                candidate("concept", 0.5, entity_type=SearchEntityType.CONCEPT),
            ],
            top_k=2,
            intent=intent,
        )
        assert ranked[0].id == "concept"

    def test_current_state_intent_prefers_an_operational_feed(self):
        intent = IntentAssessment(
            intent=QueryIntent.CURRENT_STATE, confidence=0.9, is_time_sensitive=True
        )
        ranked = HeuristicReranker().rerank(
            "where is it now",
            [
                candidate("archive", 0.5, source_names=["jpl_sbdb"],
                          entity_type=SearchEntityType.SPACE_OBJECT),
                candidate("feed", 0.5, source_names=["celestrak_gp"],
                          entity_type=SearchEntityType.SPACE_OBJECT),
            ],
            top_k=2,
            intent=intent,
        )
        assert ranked[0].id == "feed"

    def test_score_breakdown_is_returned(self):
        ranked = HeuristicReranker().rerank("q", [candidate("a", 0.5)], top_k=1)
        assert set(ranked[0].components) >= {
            "relevance", "authority", "freshness", "type_match", "intent_match"
        }
        assert ranked[0].explanation

    def test_movement_is_reported(self):
        ranked = HeuristicReranker().rerank(
            "q", [candidate("a", 0.1), candidate("b", 0.9)], top_k=2
        )
        moved = {item.id: item.moved for item in ranked}
        assert moved["b"] == 1
        assert moved["a"] == -1

    def test_top_k_limits_the_output(self):
        candidates = [candidate(str(i), i / 10.0) for i in range(10)]
        assert len(HeuristicReranker().rerank("q", candidates, top_k=3)) == 3

    def test_weights_are_configurable(self):
        heavy = HeuristicReranker(
            weights=RerankWeights(relevance=0.0, authority=10.0)
        )
        ranked = heavy.rerank(
            "q",
            [
                candidate("relevant", 1.0, trust_level=TrustLevel.LOW),
                candidate("authoritative", 0.0,
                          trust_level=TrustLevel.AUTHORITATIVE),
            ],
            top_k=2,
        )
        assert ranked[0].id == "authoritative"

    def test_health_check(self):
        assert HeuristicReranker().health_check()["healthy"] is True
        assert NoOpReranker().health_check()["healthy"] is True

    def test_a_broken_reranker_reports_rather_than_raises(self):
        class Broken(Reranker):
            name = "broken"

            def rerank(self, query, candidates, top_k=10, intent=None):
                raise RuntimeError("model unavailable")

        status = Broken().health_check()
        assert status["healthy"] is False
        assert "model unavailable" in status["detail"]


class TestDiversity:
    def _same_source(self, count):
        return [
            candidate("p{0}".format(i), 0.9 - i * 0.001,
                      source_names=["esa_copernicus"],
                      entity_type=SearchEntityType.EO_PRODUCT)
            for i in range(count)
        ] + [
            candidate("other", 0.85, source_names=["jpl_sbdb"],
                      entity_type=SearchEntityType.SPACE_OBJECT)
        ]

    def test_diversity_applies_to_exploratory_queries(self):
        intent = IntentAssessment(intent=QueryIntent.EXPLORATORY, confidence=0.8)
        ranked = HeuristicReranker().rerank(
            "sentinel products", self._same_source(5), top_k=3, intent=intent
        )
        assert "other" in [item.id for item in ranked]

    def test_diversity_does_not_apply_to_lookups(self):
        """One right answer must not be displaced to make the page varied."""
        intent = IntentAssessment(intent=QueryIntent.LOOKUP, confidence=0.9)
        ranked = HeuristicReranker().rerank(
            "sentinel", self._same_source(5), top_k=3, intent=intent
        )
        assert [item.id for item in ranked[:3]] == ["p0", "p1", "p2"]

    def test_diversity_can_be_disabled(self):
        """No penalty is applied, so no candidate carries the component."""
        intent = IntentAssessment(intent=QueryIntent.EXPLORATORY, confidence=0.8)
        ranked = HeuristicReranker(diversity_penalty=0.0).rerank(
            "x", self._same_source(5), top_k=4, intent=intent
        )
        assert not any("diversity_penalty" in item.components for item in ranked)

    def test_penalty_is_recorded_when_applied(self):
        intent = IntentAssessment(intent=QueryIntent.EXPLORATORY, confidence=0.8)
        ranked = HeuristicReranker().rerank(
            "x", self._same_source(5), top_k=4, intent=intent
        )
        assert any("diversity_penalty" in item.components for item in ranked)


class TestPipeline:
    def test_returns_results(self, hybrid):
        response = hybrid.search(SearchQuery(text="What causes Max-Q?"))
        assert response.status is SearchStatus.OK
        assert response.top().id == "concept:max-q"

    def test_trace_records_every_stage(self, hybrid):
        hybrid.search(SearchQuery(text="Apollo 11"))
        trace = hybrid.last_trace
        assert trace.keyword_candidates > 0
        assert trace.vector_candidates > 0
        assert trace.fused_candidates > 0
        assert trace.reranked_candidates > 0
        assert set(trace.stage_ms) == {"retrieve", "fuse", "rerank"}

    def test_only_a_small_set_is_reranked(self, keyword, semantic):
        """Reranking is the expensive stage and must not see the whole index."""
        engine = HybridSearch(keyword, semantic, rerank_top_n=5)
        engine.search(SearchQuery(text="mission", limit=20))
        assert engine.last_trace.reranked_candidates <= 5

    def test_intent_is_recorded_in_the_trace(self, hybrid):
        hybrid.search(SearchQuery(text="Where is the ISS right now?"))
        assert hybrid.last_trace.intent.is_time_sensitive is True

    def test_results_carry_the_rerank_breakdown(self, hybrid):
        response = hybrid.search(SearchQuery(text="What causes Max-Q?"))
        metadata = response.top().metadata
        assert "rerank_components" in metadata
        assert "rerank_explanation" in metadata
        assert "found_by" in metadata

    def test_every_result_is_attributed(self, hybrid):
        response = hybrid.search(SearchQuery(text="Ceres"))
        for result in response.results:
            assert result.provenance.is_attributed

    def test_exact_identifier_still_found(self, hybrid):
        """The case pure semantic search loses."""
        response = hybrid.search(SearchQuery(text="25544"))
        assert response.status is SearchStatus.OK
        assert response.top().id == "space-station:25544"

    def test_paraphrase_still_found(self, hybrid):
        """The case pure keyword search loses."""
        response = hybrid.search(
            SearchQuery(text="Why do rockets throttle down during ascent?")
        )
        assert response.status is SearchStatus.OK
        assert "concept:max-q" in [result.id for result in response.results]

    def test_abstains_on_an_unanswerable_question(self, hybrid):
        response = hybrid.search(
            SearchQuery(text="What did the Beagle 2 lander discover on Mars?")
        )
        assert response.status is SearchStatus.NO_RELIABLE_MATCH
        assert response.results == []

    def test_filters_pass_through(self, hybrid):
        response = hybrid.search(
            SearchQuery(text="Mars", entity_types=[SearchEntityType.MISSION])
        )
        assert response.results
        assert all(
            result.entity_type is SearchEntityType.MISSION
            for result in response.results
        )

    def test_weighted_fusion_mode_works(self, keyword, semantic):
        engine = HybridSearch(keyword, semantic, fusion_method="weighted")
        response = engine.search(SearchQuery(text="What causes Max-Q?"))
        assert response.status is SearchStatus.OK
        assert engine.last_trace.fusion_method == "weighted"


class TestMeasuredImprovement:
    """Compared against the baselines the task asks for.

    Measured at the time of writing, over the 37-query labelled set:

    | config                    | MRR   | MAP   | P@1   | R@5   | false | miss |
    |---------------------------|-------|-------|-------|-------|-------|------|
    | keyword only              | 0.961 | 0.941 | 0.938 | 0.969 | 3     | 0    |
    | semantic only             | 0.874 | 0.846 | 0.812 | 0.911 | 2     | 1    |
    | hybrid + no-op rerank     | 0.954 | 0.936 | 0.938 | 0.969 | 0     | 0    |
    | hybrid + heuristic rerank | 0.969 | 0.933 | 0.938 | 0.974 | 0     | 0    |
    """

    @pytest.fixture(scope="class")
    def scores(self, keyword, semantic):
        vector_only = SemanticSearch(
            semantic.store, semantic.embeddings, documents=keyword
        )
        return {
            "keyword": evaluate(keyword),
            "semantic": evaluate(vector_only),
            "no_rerank": evaluate(
                HybridSearch(keyword, semantic, reranker=NoOpReranker())
            ),
            "hybrid": evaluate(HybridSearch(keyword, semantic)),
        }

    def test_hybrid_beats_keyword_only_on_mrr(self, scores):
        assert scores["hybrid"].mean_reciprocal_rank >= (
            scores["keyword"].mean_reciprocal_rank
        )

    def test_hybrid_beats_semantic_only_on_mrr(self, scores):
        assert scores["hybrid"].mean_reciprocal_rank > (
            scores["semantic"].mean_reciprocal_rank
        )

    def test_reranking_improves_on_fusion_alone(self, scores):
        assert scores["hybrid"].mean_reciprocal_rank > (
            scores["no_rerank"].mean_reciprocal_rank
        )

    def test_hybrid_makes_fewer_false_answers_than_either_baseline(self, scores):
        """Fewer, not zero — the residual case is caught by the topic
        classifier above this layer, and is documented in the baseline."""
        assert scores["keyword"].false_answers > scores["hybrid"].false_answers
        assert scores["semantic"].false_answers > scores["hybrid"].false_answers
        assert scores["hybrid"].false_answers <= 1

    def test_hybrid_misses_nothing(self, scores):
        assert scores["hybrid"].missed_answers == 0

    def test_hybrid_recall_at_5(self, scores):
        assert scores["hybrid"].recall_at_k[5] >= 0.94

    def test_absolute_quality_floor(self, scores):
        summary = scores["hybrid"]
        assert summary.mean_reciprocal_rank >= 0.92, summary.describe()
        assert summary.precision_at_k[1] >= 0.88, summary.describe()
