"""Runners for failure-analysis and recommendation scenarios.

Both score *properties of the output* rather than its wording: which failure
rule was identified, which subsystem, whether the simulator caveats are present,
whether a forbidden recommendation appeared. Those are the things that must
hold; the phrasing is the model's business.
"""

from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from ..datasets.domain_questions import (
    FAILURE_SCENARIOS,
    RECOMMENDATION_SCENARIOS,
    FailureScenario,
    RecommendationScenario,
)

__all__ = [
    "FailureOutcome",
    "FailureSummary",
    "run_failure_evaluation",
    "RecommendationOutcome",
    "RecommendationSummary",
    "run_recommendation_evaluation",
]


# ----------------------------------------------------------------------
class FailureOutcome(BaseModel):
    """How one failure-analysis scenario scored."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    run: str
    identified_cause: bool = False
    correct_subsystem: bool = False
    retrieved_expected_reference: bool = False
    #: Every analysis that explains anything must state its limitations.
    states_limitations: bool = False
    #: Observations must be present and separate from explanation.
    separates_observation_from_explanation: bool = False
    #: True when mitigation behaviour matched the expectation.
    offered_mitigations: bool = False
    #: An explanation that cited a source not supplied.
    hallucinated_citation: bool = False
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        return (
            self.error is None
            and self.states_limitations
            and self.separates_observation_from_explanation
            and not self.hallucinated_citation
        )


class FailureSummary(BaseModel):
    """Aggregate over the failure-analysis set."""

    model_config = ConfigDict(extra="forbid")

    total: int = 0
    cause_accuracy: float = 0.0
    subsystem_accuracy: float = 0.0
    reference_recall: float = 0.0
    limitation_disclosure: float = 0.0
    separation_rate: float = 0.0
    mitigation_rate: float = 0.0
    hallucination_rate: float = 0.0
    errors: int = 0
    outcomes: List[FailureOutcome] = Field(default_factory=list)

    def describe(self) -> str:
        return "\n".join([
            "Failure analysis over {0} scenario(s)".format(self.total),
            "  cause identified      {0:.3f}".format(self.cause_accuracy),
            "  subsystem correct     {0:.3f}".format(self.subsystem_accuracy),
            "  reference recall      {0:.3f}".format(self.reference_recall),
            "  limitations disclosed {0:.3f}".format(self.limitation_disclosure),
            "  obs/explanation split {0:.3f}".format(self.separation_rate),
            "  mitigation behaviour  {0:.3f}".format(self.mitigation_rate),
            "  hallucination rate    {0:.3f}".format(self.hallucination_rate),
            "  errors                {0}".format(self.errors),
        ])

    def failures(self) -> List[FailureOutcome]:
        return [outcome for outcome in self.outcomes if not outcome.passed]


async def run_failure_evaluation(
    analyzer: Any,
    runs: Dict[str, Any],
    scenarios: Optional[Sequence[FailureScenario]] = None,
) -> FailureSummary:
    """Run every failure scenario through the analyzer."""
    from ai.analysis import parse_simulation_result

    items = list(scenarios if scenarios is not None else FAILURE_SCENARIOS)
    outcomes: List[FailureOutcome] = []

    for scenario in items:
        outcome = FailureOutcome(scenario_id=scenario.id, run=scenario.run)
        try:
            view = parse_simulation_result(runs[scenario.run])
            analysis = await analyzer.analyze(view)
        except Exception as exc:  # noqa: BLE001 - a crash is a result
            outcome.error = "{0}: {1}".format(exc.__class__.__name__, exc)
            outcomes.append(outcome)
            continue

        if scenario.expects_cause:
            outcome.identified_cause = bool(
                analysis.likely_cause
                and "cannot be attributed" not in analysis.likely_cause
            )
        else:
            #: Two correct outcomes here, and they look different. A successful
            #: run has no cause at all. An *undocumented* failure has a cause
            #: field that explicitly declines to attribute one. Both are right;
            #: inventing a cause is the failure.
            outcome.identified_cause = (
                analysis.likely_cause is None
                or "cannot be attributed" in analysis.likely_cause
            )

        if scenario.expected_subsystem:
            outcome.correct_subsystem = any(
                subsystem.value == scenario.expected_subsystem
                for subsystem in analysis.affected_subsystems
            )
        else:
            outcome.correct_subsystem = True

        if scenario.expected_references:
            retrieved = {item.canonical_id for item in analysis.context_items}
            outcome.retrieved_expected_reference = bool(
                retrieved & set(scenario.expected_references)
            )
        else:
            outcome.retrieved_expected_reference = True

        outcome.states_limitations = bool(analysis.simulation_limitations)
        outcome.separates_observation_from_explanation = bool(
            analysis.observations
        )
        #: Scored against the expectation, not as a raw count. A successful
        #: run offering no mitigations is correct, and averaging the raw
        #: boolean would mark it a failure.
        outcome.offered_mitigations = (
            bool(analysis.mitigations) == scenario.expects_mitigations
        )
        outcome.hallucinated_citation = any(
            "were not supplied" in note for note in analysis.uncertainty
        )
        outcomes.append(outcome)

    return _summarize_failures(outcomes)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / float(len(values)) if values else 0.0


def _summarize_failures(outcomes: Sequence[FailureOutcome]) -> FailureSummary:
    scored = [outcome for outcome in outcomes if outcome.error is None]
    return FailureSummary(
        total=len(outcomes),
        cause_accuracy=_mean([1.0 if o.identified_cause else 0.0 for o in scored]),
        subsystem_accuracy=_mean(
            [1.0 if o.correct_subsystem else 0.0 for o in scored]
        ),
        reference_recall=_mean(
            [1.0 if o.retrieved_expected_reference else 0.0 for o in scored]
        ),
        limitation_disclosure=_mean(
            [1.0 if o.states_limitations else 0.0 for o in scored]
        ),
        separation_rate=_mean(
            [1.0 if o.separates_observation_from_explanation else 0.0
             for o in scored]
        ),
        mitigation_rate=_mean(
            [1.0 if o.offered_mitigations else 0.0 for o in scored]
        ),
        hallucination_rate=_mean(
            [1.0 if o.hallucinated_citation else 0.0 for o in scored]
        ),
        errors=len(outcomes) - len(scored),
        outcomes=list(outcomes),
    )


# ----------------------------------------------------------------------
class RecommendationOutcome(BaseModel):
    """How one recommendation scenario scored."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    returned_items: int = 0
    found_expected: bool = False
    avoided_forbidden: bool = True
    all_explained: bool = False
    all_scored: bool = False
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        return (
            self.error is None
            and self.returned_items > 0
            and self.found_expected
            and self.avoided_forbidden
            and self.all_explained
        )


class RecommendationSummary(BaseModel):
    """Aggregate over the recommendation set."""

    model_config = ConfigDict(extra="forbid")

    total: int = 0
    coverage: float = 0.0
    expectation_accuracy: float = 0.0
    forbidden_avoidance: float = 0.0
    explanation_rate: float = 0.0
    errors: int = 0
    outcomes: List[RecommendationOutcome] = Field(default_factory=list)

    def describe(self) -> str:
        return "\n".join([
            "Recommendations over {0} scenario(s)".format(self.total),
            "  returned something    {0:.3f}".format(self.coverage),
            "  expected item found   {0:.3f}".format(self.expectation_accuracy),
            "  forbidden avoided     {0:.3f}".format(self.forbidden_avoidance),
            "  all explained         {0:.3f}".format(self.explanation_rate),
            "  errors                {0}".format(self.errors),
        ])

    def failures(self) -> List[RecommendationOutcome]:
        return [outcome for outcome in self.outcomes if not outcome.passed]


def run_recommendation_evaluation(
    engine: Any,
    scenarios: Optional[Sequence[RecommendationScenario]] = None,
) -> RecommendationSummary:
    """Run every recommendation scenario through the engine."""
    from ai.recommendations import RecommendationRequest
    from contracts.recommendations import LearnerLevel

    items = list(
        scenarios if scenarios is not None else RECOMMENDATION_SCENARIOS
    )
    outcomes: List[RecommendationOutcome] = []

    for scenario in items:
        outcome = RecommendationOutcome(scenario_id=scenario.id)
        try:
            result = engine.recommend(RecommendationRequest(
                current_topic=scenario.current_topic or None,
                level=LearnerLevel(scenario.level),
                completed_ids=list(scenario.completed_ids),
                topic_mastery=dict(scenario.topic_mastery),
                project_context=scenario.project_context or None,
                project_subsystems=list(scenario.project_subsystems),
                limit=8,
            ))
        except Exception as exc:  # noqa: BLE001 - a crash is a result
            outcome.error = "{0}: {1}".format(exc.__class__.__name__, exc)
            outcomes.append(outcome)
            continue

        ids = [item.id for item in result.items]
        outcome.returned_items = len(ids)
        outcome.found_expected = (
            bool(set(ids) & set(scenario.expected_any))
            if scenario.expected_any else True
        )
        outcome.avoided_forbidden = not (set(ids) & set(scenario.forbidden))
        outcome.all_explained = all(
            item.reason and item.reason.strip() for item in result.items
        )
        outcome.all_scored = all(
            0.0 <= item.score <= 1.0 for item in result.items
        )
        outcomes.append(outcome)

    scored = [outcome for outcome in outcomes if outcome.error is None]
    return RecommendationSummary(
        total=len(outcomes),
        coverage=_mean([1.0 if o.returned_items else 0.0 for o in scored]),
        expectation_accuracy=_mean(
            [1.0 if o.found_expected else 0.0 for o in scored]
        ),
        forbidden_avoidance=_mean(
            [1.0 if o.avoided_forbidden else 0.0 for o in scored]
        ),
        explanation_rate=_mean([1.0 if o.all_explained else 0.0 for o in scored]),
        errors=len(outcomes) - len(scored),
        outcomes=list(outcomes),
    )
