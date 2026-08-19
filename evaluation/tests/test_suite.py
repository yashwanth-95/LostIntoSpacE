"""The evaluation suite itself: dataset integrity and baseline thresholds.

Two jobs. First, keep the datasets honest — unique ids, labels pointing at
records that exist, minimum counts. A label referencing a missing record
measures nothing, and that failure is silent.

Second, pin the baseline. The thresholds sit just below measured values, so a
regression fails here rather than being noticed later.
"""

import pytest

from evaluation.datasets import (
    ENGINEERING_QUESTIONS,
    FAILURE_SCENARIOS,
    MISSION_QUESTIONS,
    OBJECT_QUESTIONS,
    RAG_QUESTIONS,
    RECOMMENDATION_SCENARIOS,
)
from evaluation.runners import build_stack, render_report, run_all
from search.evaluation import EVALUATION_QUERIES


@pytest.fixture(scope="module")
def stack():
    return build_stack()


class TestDatasetSizes:
    """The minimum counts the task requires."""

    def test_thirty_search_queries(self):
        assert len(EVALUATION_QUERIES) >= 30

    def test_thirty_rag_questions(self):
        assert len(RAG_QUESTIONS) >= 30

    def test_twenty_mission_questions(self):
        assert len(MISSION_QUESTIONS) >= 20

    def test_twenty_engineering_questions(self):
        assert len(ENGINEERING_QUESTIONS) >= 20

    def test_twenty_object_questions(self):
        assert len(OBJECT_QUESTIONS) >= 20

    def test_ten_failure_scenarios(self):
        assert len(FAILURE_SCENARIOS) >= 10

    def test_ten_recommendation_scenarios(self):
        assert len(RECOMMENDATION_SCENARIOS) >= 10


class TestDatasetIntegrity:
    ALL_QUESTIONS = (
        RAG_QUESTIONS + MISSION_QUESTIONS + ENGINEERING_QUESTIONS
        + OBJECT_QUESTIONS
    )

    def test_question_ids_are_unique_within_each_set(self):
        for name, items in (
            ("rag", RAG_QUESTIONS), ("mission", MISSION_QUESTIONS),
            ("engineering", ENGINEERING_QUESTIONS), ("object", OBJECT_QUESTIONS),
        ):
            ids = [item.id for item in items]
            assert len(ids) == len(set(ids)), name

    def test_question_ids_are_unique_across_sets(self):
        ids = [item.id for item in self.ALL_QUESTIONS]
        assert len(ids) == len(set(ids))

    def test_every_question_has_a_rationale(self):
        for question in self.ALL_QUESTIONS:
            assert question.rationale, question.id

    def test_expected_sources_exist_in_the_corpus(self, stack):
        """A label pointing at a missing record measures nothing, silently."""
        keyword = stack["keyword"]
        missing = []
        for question in self.ALL_QUESTIONS:
            for canonical_id in question.expected_sources:
                if keyword.get(canonical_id) is None:
                    missing.append("{0} -> {1}".format(question.id, canonical_id))
        assert missing == []

    def test_unanswerable_questions_name_no_sources(self):
        for question in self.ALL_QUESTIONS:
            if question.should_decline:
                assert question.expected_sources == [], question.id

    def test_every_set_includes_something_that_must_be_declined(self):
        for name, items in (
            ("rag", RAG_QUESTIONS), ("mission", MISSION_QUESTIONS),
            ("engineering", ENGINEERING_QUESTIONS), ("object", OBJECT_QUESTIONS),
        ):
            assert any(item.should_decline for item in items), name

    def test_failure_scenario_ids_are_unique(self):
        ids = [item.id for item in FAILURE_SCENARIOS]
        assert len(ids) == len(set(ids))

    def test_failure_scenarios_reference_real_runs(self):
        from ai.tests.fixtures.simulation_runs import ALL_RUNS

        for scenario in FAILURE_SCENARIOS:
            assert scenario.run in ALL_RUNS, scenario.id

    def test_recommendation_scenario_ids_are_unique(self):
        ids = [item.id for item in RECOMMENDATION_SCENARIOS]
        assert len(ids) == len(set(ids))

    def test_recommendation_expectations_exist_in_the_corpus(self, stack):
        keyword = stack["keyword"]
        missing = []
        for scenario in RECOMMENDATION_SCENARIOS:
            for canonical_id in scenario.expected_any + scenario.forbidden:
                if keyword.get(canonical_id) is None:
                    missing.append("{0} -> {1}".format(scenario.id, canonical_id))
        assert missing == []


class TestBaseline:
    """Thresholds sit just below measured values.

    Measured at the time of writing:

    | Area | Key numbers |
    |---|---|
    | Retrieval (hybrid) | MRR 0.969, P@1 0.938, R@5 0.974, 1 false answer |
    | Grounded answering | groundedness 1.000, hallucination 0.000, missed 0.000 |
    | Failure analysis | every measure 1.000, hallucination 0.000 |
    | Recommendations | every measure 1.000 |
    """

    @pytest.fixture(scope="class")
    async def results(self, stack):
        return await run_all(stack)

    async def test_retrieval_holds(self, stack):
        results = await run_all(stack)
        search = results["search"]
        assert search.mean_reciprocal_rank >= 0.92, search.describe()
        assert search.precision_at_k[1] >= 0.88, search.describe()
        assert search.recall_at_k[5] >= 0.94, search.describe()

    async def test_grounded_answering_holds(self, stack):
        results = await run_all(stack)
        for key in ("rag", "missions", "engineering", "objects"):
            summary = results[key]
            assert summary.groundedness == 1.0, (key, summary.describe())
            assert summary.hallucination_rate == 0.0, (key, summary.describe())
            assert summary.citation_correctness >= 0.9, (key, summary.describe())
            assert summary.freshness_correctness == 1.0, (key, summary.describe())

    async def test_nothing_answerable_is_refused(self, stack):
        results = await run_all(stack)
        for key in ("rag", "missions", "engineering", "objects"):
            assert results[key].missed_answer_rate == 0.0, key

    async def test_abstention_holds(self, stack):
        """One known false answer, documented in the baseline report."""
        results = await run_all(stack)
        assert results["rag"].abstention_precision == 1.0
        assert results["missions"].abstention_precision == 1.0
        assert results["engineering"].abstention_precision == 1.0
        #: The object set contains the documented "dwarf planet" weakness.
        assert results["objects"].abstention_precision >= 0.6

    async def test_failure_analysis_holds(self, stack):
        results = await run_all(stack)
        failures = results["failures"]
        assert failures.errors == 0, failures.describe()
        assert failures.limitation_disclosure == 1.0, failures.describe()
        assert failures.separation_rate == 1.0, failures.describe()
        assert failures.hallucination_rate == 0.0, failures.describe()
        assert failures.cause_accuracy >= 0.9, failures.describe()

    async def test_recommendations_hold(self, stack):
        results = await run_all(stack)
        recommendations = results["recommendations"]
        assert recommendations.errors == 0
        assert recommendations.coverage == 1.0, recommendations.describe()
        assert recommendations.explanation_rate == 1.0, recommendations.describe()
        assert recommendations.forbidden_avoidance == 1.0, (
            recommendations.describe()
        )

    async def test_hybrid_beats_keyword_only_on_abstention(self, stack):
        """The reason hybrid ships despite a comparable MRR."""
        results = await run_all(stack)
        assert results["search"].false_answers < (
            results["search_keyword_only"].false_answers
        )


class TestReport:
    async def test_the_report_renders(self, stack):
        results = await run_all(stack)
        report = render_report(results)
        assert "# Person 4 Evaluation Baseline" in report
        assert "## 1. Retrieval" in report
        assert "## 3. Failure analysis" in report

    async def test_the_report_states_its_limitations(self, stack):
        """A report without caveats invites its numbers being over-read."""
        report = render_report(await run_all(stack))
        assert "Self-authored labels" in report
        assert "Small corpus" in report
        assert "Known residual weakness" in report

    def test_a_checked_in_baseline_exists(self):
        import pathlib

        path = (
            pathlib.Path(__file__).resolve().parents[1] / "reports" / "BASELINE.md"
        )
        assert path.exists(), "run `python -m evaluation.runners.baseline`"
        assert "Person 4 Evaluation Baseline" in path.read_text(encoding="utf-8")

    async def test_the_suite_is_deterministic(self, stack):
        """Two runs must agree, or a regression cannot be attributed."""
        first = await run_all(stack)
        second = await run_all(stack)
        assert (
            first["search"].mean_reciprocal_rank
            == second["search"].mean_reciprocal_rank
        )
        assert first["rag"].groundedness == second["rag"].groundedness

    def test_the_suite_needs_no_network_or_vendor_account(self):
        """CI must not depend on an archive's availability or an API key."""
        from ai.providers import MockAIProvider
        from search.embeddings import HashedLexicalProvider

        assert MockAIProvider().get_info().is_offline
        assert HashedLexicalProvider().health_check()["healthy"]
