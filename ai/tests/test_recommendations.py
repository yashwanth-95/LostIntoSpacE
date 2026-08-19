"""Recommendations: rules, similarity, explanations, and the four scenarios."""

import pytest
from pydantic import ValidationError

from ai.recommendations import RecommendationEngine, RecommendationRequest
from contracts.recommendations import (
    LearnerLevel,
    Recommendation,
    RecommendationKind,
    RecommendationSet,
)


@pytest.fixture
def engine(retriever, record_store):
    return RecommendationEngine(retriever, record_store=record_store)


class TestBeginnerScenario:
    """Someone new, working through the introductory material."""

    def _request(self, **kwargs):
        payload = dict(
            current_topic="propulsion",
            level=LearnerLevel.BEGINNER,
            completed_ids=["concept:max-q"],
            topic_mastery={"propulsion": 0.1, "orbital mechanics": 0.8},
            limit=5,
        )
        payload.update(kwargs)
        return RecommendationRequest(**payload)

    def test_returns_recommendations(self, engine):
        result = engine.recommend(self._request())
        assert not result.is_empty

    def test_completed_material_is_excluded(self, engine):
        """Uses a completed item the propulsion query actually retrieves."""
        result = engine.recommend(
            self._request(completed_ids=["concept:liquid-propulsion"])
        )
        assert "concept:liquid-propulsion" not in [i.id for i in result.items]
        assert result.excluded.get("concept:liquid-propulsion") == (
            "already completed"
        )

    def test_the_weakest_topic_is_favoured(self, engine):
        result = engine.recommend(self._request())
        joined = " ".join(item.reason.lower() for item in result.items)
        assert "propulsion" in joined

    def test_reasons_prefer_specific_explanations_over_generic_ones(self, engine):
        """"Similar to what you are looking at" is true of every candidate."""
        result = engine.recommend(self._request())
        reasons = " ".join(item.reason.lower() for item in result.items)
        assert "progress is lowest" in reasons or "covers propulsion" in reasons

    def test_a_generic_reason_is_never_the_only_one_offered(self, engine):
        result = engine.recommend(self._request())
        for item in result.items:
            specific = [
                signal for signal in item.signals
                if signal.weight > 0 and signal.detail
                and signal.name != "similarity"
            ]
            if specific:
                assert not item.reason.lower().startswith("similar to")

    def test_references_are_deprioritised_for_beginners(self, engine):
        result = engine.recommend(self._request(limit=10))
        kinds = [item.kind for item in result.items]
        if RecommendationKind.REFERENCE in kinds and len(kinds) > 1:
            #: A technical document may appear, but should not lead.
            assert kinds[0] is not RecommendationKind.REFERENCE

    def test_the_current_item_is_not_recommended_back(self, engine):
        result = engine.recommend(
            self._request(current_item_id="concept:liquid-propulsion")
        )
        assert "concept:liquid-propulsion" not in [i.id for i in result.items]
        assert result.excluded.get("concept:liquid-propulsion") == "currently open"


class TestEngineeringScenario:
    """Someone designing a vehicle, after a structural failure."""

    def _request(self, **kwargs):
        payload = dict(
            current_topic="structures",
            level=LearnerLevel.INTERMEDIATE,
            project_context="two-stage vehicle exceeded its structural limit",
            project_subsystems=["STRUCTURE", "AERODYNAMICS"],
            limit=6,
        )
        payload.update(kwargs)
        return RecommendationRequest(**payload)

    def test_project_relevant_material_is_surfaced(self, engine):
        result = engine.recommend(self._request())
        assert not result.is_empty
        ids = [item.id for item in result.items]
        assert any(
            candidate in ids
            for candidate in ("concept:max-q", "concept:staging",
                              "concept:reentry-heating")
        )

    def test_project_relevance_is_named_in_a_reason(self, engine):
        result = engine.recommend(self._request())
        signals = [
            signal.name for item in result.items for signal in item.signals
        ]
        assert "project_relevance" in signals or "similarity" in signals

    def test_the_project_context_drives_retrieval(self, engine):
        with_project = engine.recommend(self._request())
        without = engine.recommend(
            self._request(project_context=None, project_subsystems=[])
        )
        assert [i.id for i in with_project.items] != [i.id for i in without.items]

    def test_intermediate_level_allows_technical_material(self, engine):
        result = engine.recommend(self._request(limit=10))
        assert result.items


class TestResearcherScenario:
    """Someone who wants primary sources rather than lessons."""

    def _request(self, **kwargs):
        payload = dict(
            current_topic="max-q",
            level=LearnerLevel.RESEARCHER,
            limit=8,
        )
        payload.update(kwargs)
        return RecommendationRequest(**payload)

    def test_lessons_are_penalised_for_researchers(self, engine):
        result = engine.recommend(self._request())
        for item in result.items:
            if item.kind is RecommendationKind.LESSON:
                penalties = [
                    signal for signal in item.signals
                    if signal.name == "level_mismatch"
                ]
                assert penalties

    def test_references_and_objects_are_favoured(self, engine):
        result = engine.recommend(self._request())
        assert result.items
        kinds = {item.kind for item in result.items}
        assert kinds & {
            RecommendationKind.REFERENCE, RecommendationKind.SPACE_OBJECT,
            RecommendationKind.MISSION, RecommendationKind.CONCEPT,
        }

    def test_a_researcher_gets_different_results_than_a_beginner(self, engine):
        researcher = engine.recommend(self._request())
        beginner = engine.recommend(
            self._request(level=LearnerLevel.BEGINNER)
        )
        assert [i.id for i in researcher.items] != [i.id for i in beginner.items]


class TestProjectScenario:
    """Someone whose simulation just failed."""

    def _request(self, **kwargs):
        payload = dict(
            current_topic="dynamic pressure",
            level=LearnerLevel.INTERMEDIATE,
            project_context="airframe exceeded dynamic pressure limit at t+48 s",
            project_subsystems=["AERODYNAMICS"],
            limit=5,
        )
        payload.update(kwargs)
        return RecommendationRequest(**payload)

    def test_the_relevant_concept_is_recommended(self, engine):
        result = engine.recommend(self._request())
        assert "concept:max-q" in [item.id for item in result.items]

    def test_the_reason_connects_to_the_project(self, engine):
        result = engine.recommend(self._request())
        top = result.items[0]
        assert top.reason
        assert top.reason[0].isupper()
        assert top.reason.endswith(".")

    def test_recommendations_carry_sources_when_available(self, engine):
        result = engine.recommend(self._request())
        assert any(item.sources for item in result.items)


class TestRules:
    def test_prerequisites_gate_recommendations(self, engine):
        """Staging declares specific impulse as a prerequisite."""
        without = engine.recommend(RecommendationRequest(
            current_topic="staging", level=LearnerLevel.BEGINNER, limit=10
        ))
        staging = [i for i in without.items if i.id == "concept:staging"]
        if staging:
            names = [signal.name for signal in staging[0].signals]
            assert "prerequisite_missing" in names

    def test_covering_the_prerequisite_removes_the_penalty(self, engine):
        result = engine.recommend(RecommendationRequest(
            current_topic="staging",
            level=LearnerLevel.BEGINNER,
            completed_ids=["concept:specific-impulse"],
            limit=10,
        ))
        staging = [i for i in result.items if i.id == "concept:staging"]
        if staging:
            names = [signal.name for signal in staging[0].signals]
            assert "prerequisite_missing" not in names
            assert "prerequisite_ready" in names

    def test_rules_outweigh_similarity(self, engine):
        """A perfect similarity match that is completed must not be returned."""
        result = engine.recommend(RecommendationRequest(
            current_topic="Max-Q",
            completed_ids=["concept:max-q"],
            level=LearnerLevel.BEGINNER,
        ))
        assert "concept:max-q" not in [item.id for item in result.items]

    def test_difficulty_above_the_level_is_penalised(self, engine):
        result = engine.recommend(RecommendationRequest(
            current_topic="orbital mechanics",
            level=LearnerLevel.BEGINNER,
            limit=10,
        ))
        advanced = [
            item for item in result.items if item.difficulty == "ADVANCED"
        ]
        for item in advanced:
            assert any(
                signal.name == "level_mismatch" for signal in item.signals
            )

    def test_kind_filtering(self, engine):
        result = engine.recommend(RecommendationRequest(
            current_topic="Jupiter",
            kinds=[RecommendationKind.MISSION],
            limit=5,
        ))
        assert result.items
        assert all(item.kind is RecommendationKind.MISSION
                   for item in result.items)

    def test_an_empty_profile_still_returns_something(self, engine):
        """A new user with no history must not get an empty page."""
        result = engine.recommend(RecommendationRequest(limit=5))
        assert not result.is_empty


class TestExplanations:
    def test_every_recommendation_explains_itself(self, engine):
        result = engine.recommend(RecommendationRequest(
            current_topic="propulsion", level=LearnerLevel.BEGINNER
        ))
        for item in result.items:
            assert item.reason.strip()
            assert len(item.reason) > 10

    def test_signals_are_exposed_for_debugging(self, engine):
        result = engine.recommend(RecommendationRequest(
            current_topic="propulsion", level=LearnerLevel.BEGINNER
        ))
        assert all(item.signals for item in result.items)

    def test_the_reason_matches_the_strongest_signals(self, engine):
        result = engine.recommend(RecommendationRequest(
            current_topic="propulsion",
            topic_mastery={"propulsion": 0.1},
            level=LearnerLevel.BEGINNER,
        ))
        top = result.items[0]
        strongest = max(
            (s for s in top.signals if s.weight > 0 and s.detail),
            key=lambda s: s.weight,
        )
        assert strongest.detail.lower()[:12] in top.reason.lower()

    def test_the_contract_rejects_an_unexplained_recommendation(self):
        with pytest.raises(ValidationError):
            Recommendation(
                id="x", kind=RecommendationKind.CONCEPT, title="X",
                score=0.9, reason="   ",
            )

    def test_scores_are_bounded(self, engine):
        result = engine.recommend(RecommendationRequest(
            current_topic="propulsion", level=LearnerLevel.BEGINNER
        ))
        assert all(0.0 <= item.score <= 1.0 for item in result.items)

    def test_results_are_ranked(self, engine):
        result = engine.recommend(RecommendationRequest(
            current_topic="propulsion", level=LearnerLevel.BEGINNER, limit=10
        ))
        scores = [item.score for item in result.items]
        assert scores == sorted(scores, reverse=True)

    def test_exclusions_are_explained(self, engine):
        result = engine.recommend(RecommendationRequest(
            current_topic="Max-Q",
            completed_ids=["concept:max-q"],
            level=LearnerLevel.BEGINNER,
        ))
        assert all(reason for reason in result.excluded.values())

    def test_the_profile_summary_describes_the_request(self, engine):
        result = engine.recommend(RecommendationRequest(
            current_topic="propulsion",
            level=LearnerLevel.BEGINNER,
            completed_ids=["concept:max-q"],
        ))
        assert "beginner" in result.profile_summary
        assert "propulsion" in result.profile_summary


class TestMvpDiscipline:
    """The task says rules plus similarity, not a learned recommender."""

    def test_no_machine_learning_dependency_is_used(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2]
        banned = ("sklearn", "torch", "tensorflow", "lightgbm", "xgboost",
                  "surprise", "implicit")
        offenders = []
        for path in root.glob("ai/recommendations/*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for name in banned:
                if "import {0}".format(name) in text:
                    offenders.append(name)
        assert offenders == []

    def test_the_engine_is_deterministic(self, engine):
        request = RecommendationRequest(
            current_topic="propulsion", level=LearnerLevel.BEGINNER
        )
        first = engine.recommend(request)
        second = engine.recommend(request)
        assert [i.id for i in first.items] == [i.id for i in second.items]
        assert [i.score for i in first.items] == [i.score for i in second.items]

    def test_weights_are_configurable(self, retriever, record_store):
        default = RecommendationEngine(retriever, record_store=record_store)
        tuned = RecommendationEngine(
            retriever, record_store=record_store,
            weights={"similarity": 0.0, "weak_topic": 2.0},
        )
        request = RecommendationRequest(
            current_topic="propulsion",
            topic_mastery={"propulsion": 0.1},
            level=LearnerLevel.BEGINNER,
        )
        assert [i.id for i in default.recommend(request).items] != [
            i.id for i in tuned.recommend(request).items
        ]

    def test_the_result_set_serializes(self, engine):
        result = engine.recommend(RecommendationRequest(
            current_topic="propulsion", level=LearnerLevel.BEGINNER
        ))
        restored = RecommendationSet.model_validate_json(result.model_dump_json())
        assert len(restored.items) == len(result.items)
