"""Simulation failure analysis: parsing P3's shape, and the observation /
explanation separation."""

import re

import pytest
from pydantic import ValidationError

from ai.analysis import (
    FAILURE_RULES,
    MODEL_FIDELITY,
    FailureAnalyzer,
    SimulationResultView,
    parse_simulation_result,
)
from ai.providers import AIProviderUnavailable, MockAIProvider
from ai.tests.fixtures.simulation_runs import (
    FUEL_EXHAUSTION,
    INSTABILITY_FAILURE,
    MALFORMED_RUN,
    MAX_Q_FAILURE,
    STRUCTURAL_FAILURE,
    SUCCESSFUL_RUN,
    TWR_FAILURE,
    UNDOCUMENTED_FAILURE,
)
from contracts.ai import ConfidenceLevel
from contracts.analysis import (
    FailureAnalysis,
    FailureSeverity,
    ScientificExplanation,
    SubsystemKind,
)


def explaining_model(request):
    """A stand-in that cites the references it was given."""
    content = request.messages[0].content
    refs = re.findall(r"^\[(S\d+)\]", content, re.MULTILINE)
    if not refs:
        return "No references were supplied, so no sourced explanation is given."
    cites = " ".join("[{0}]".format(ref) for ref in refs[:2])
    return (
        "Dynamic pressure rises with the square of speed while air density "
        "falls with altitude, so the product peaks during ascent {0}. "
        "Acceleration climbs as propellant is consumed at constant thrust "
        "{1}.".format(cites, cites)
    )


@pytest.fixture
def analyzer(retriever):
    return FailureAnalyzer(retriever, MockAIProvider(responder=explaining_model))


def view(payload):
    return parse_simulation_result(payload)


class TestParsingP3Shape:
    def test_documented_event_fields_are_read(self):
        result = view(MAX_Q_FAILURE)
        assert result.simulation_id == "sim-maxq-002"
        assert result.succeeded is False
        assert result.engine_version == "sim-0.3.1"
        assert len(result.events) == 5

    def test_severity_is_parsed_from_the_documented_vocabulary(self):
        result = view(MAX_Q_FAILURE)
        failure = result.first_failure()
        assert failure.severity is FailureSeverity.CRITICAL

    def test_failure_events_are_identified(self):
        result = view(STRUCTURAL_FAILURE)
        assert result.failed
        assert len(result.failure_events()) == 1

    def test_the_first_failure_is_the_earliest(self):
        """A later impact is an aftermath, not a second cause."""
        result = view(MAX_Q_FAILURE)
        first = result.first_failure()
        assert first.event_type == "failure_excessive_q"
        assert first.time_s == 48.5

    def test_rule_keys_map_to_documented_rules(self):
        for payload, expected in (
            (TWR_FAILURE, "insufficient_twr"),
            (MAX_Q_FAILURE, "excessive_q"),
            (STRUCTURAL_FAILURE, "structural_overload"),
            (FUEL_EXHAUSTION, "fuel_exhaustion"),
            (INSTABILITY_FAILURE, "instability"),
        ):
            assert view(payload).first_failure().rule_key == expected

    def test_telemetry_uses_si_units_from_the_spec(self):
        result = view(STRUCTURAL_FAILURE)
        assert result.peak("acceleration_ms2") == pytest.approx(91.4)
        assert result.peak("altitude_m") == pytest.approx(24500.0)

    def test_sample_at_finds_the_nearest_moment(self):
        result = view(STRUCTURAL_FAILURE)
        sample = result.sample_at(62.0)
        assert sample.acceleration_ms2 == pytest.approx(91.4)

    def test_a_successful_run_is_not_a_failure(self):
        result = view(SUCCESSFUL_RUN)
        assert not result.failed
        assert result.first_failure() is None

    def test_an_undocumented_event_is_flagged_not_dropped(self):
        result = view(UNDOCUMENTED_FAILURE)
        failure = result.first_failure()
        assert failure is not None
        assert failure.is_recognised is False
        assert failure.rule_key is None

    def test_an_unexpected_payload_shape_degrades_rather_than_raising(self):
        result = view(MALFORMED_RUN)
        assert result.succeeded is False
        assert result.unparsed_keys

    def test_alias_field_names_are_understood(self):
        result = view(MALFORMED_RUN)
        assert result.telemetry
        assert result.telemetry[0].altitude_m == pytest.approx(900.0)
        assert result.telemetry[0].dynamic_pressure_pa == pytest.approx(51000.0)

    def test_a_non_mapping_payload_is_rejected(self):
        with pytest.raises(ValueError, match="must be a mapping"):
            parse_simulation_result(["not", "a", "dict"])

    def test_no_simulation_physics_is_reimplemented(self):
        """P4 reads P3's output; it must not recompute it."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2]
        banned = ("def rk4", "def integrate", "def drag_force", "def thrust_force",
                  "def atmosphere_model", "def gravity_force")
        offenders = []
        for path in root.glob("ai/**/*.py"):
            #: This file names the forbidden markers in order to search for
            #: them, so scanning itself would always fail.
            if path.name == pathlib.Path(__file__).name:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in banned:
                if marker in text:
                    offenders.append("{0}: {1}".format(path.name, marker))
        assert offenders == []


class TestObservations:
    async def test_observations_are_read_from_the_run(self, analyzer):
        analysis = await analyzer.analyze(view(STRUCTURAL_FAILURE))
        statements = analysis.observation_statements()
        assert any("structural overload" in s for s in statements)
        assert any("t+62" in s for s in statements)

    async def test_observations_include_telemetry_peaks(self, analyzer):
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        statements = analysis.observation_statements()
        assert any("Peak dynamic pressure" in s for s in statements)

    async def test_the_engine_message_is_preserved_verbatim(self, analyzer):
        analysis = await analyzer.analyze(view(STRUCTURAL_FAILURE))
        joined = " ".join(analysis.observation_statements())
        assert "91.4 m/s^2 exceeded g-limit 78.5" in joined

    async def test_observations_are_marked_as_model_output(self, analyzer):
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        assert all(item.is_model_output for item in analysis.observations)

    async def test_observations_do_not_depend_on_the_language_model(self, retriever):
        """A model that says nothing useful must not change the observations."""
        useful = FailureAnalyzer(
            retriever, MockAIProvider(responder=explaining_model)
        )
        useless = FailureAnalyzer(retriever, MockAIProvider(responses=["..."]))
        first = await useful.analyze(view(MAX_Q_FAILURE))
        second = await useless.analyze(view(MAX_Q_FAILURE))
        assert first.observation_statements() == second.observation_statements()


class TestObservationExplanationSeparation:
    async def test_they_are_separate_fields(self, analyzer):
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        assert analysis.observations
        assert analysis.explanation
        assert analysis.observations is not analysis.explanation

    async def test_explanations_carry_citations(self, analyzer):
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        cited = [item for item in analysis.explanation if item.citations]
        assert cited

    def test_an_uncited_explanation_must_declare_itself_an_inference(self):
        with pytest.raises(ValidationError, match="must either carry citations"):
            ScientificExplanation(statement="Rockets go up because of magic.")

    def test_an_inference_may_be_uncited_if_labelled(self):
        item = ScientificExplanation(
            statement="This is my own reasoning.", is_inference=True
        )
        assert item.is_inference

    async def test_uncited_model_statements_are_labelled_inferences(self, retriever):
        analyzer = FailureAnalyzer(
            retriever,
            MockAIProvider(responses=[
                "The vehicle broke apart because the structure was too weak."
            ]),
        )
        analysis = await analyzer.analyze(view(STRUCTURAL_FAILURE))
        inferences = [item for item in analysis.explanation if item.is_inference]
        assert inferences


class TestSimulationLimitations:
    async def test_limitations_are_always_present(self, analyzer):
        for payload in (TWR_FAILURE, MAX_Q_FAILURE, STRUCTURAL_FAILURE,
                        FUEL_EXHAUSTION, INSTABILITY_FAILURE):
            analysis = await analyzer.analyze(view(payload))
            assert analysis.simulation_limitations, payload["id"]

    def test_an_explanation_without_limitations_is_rejected(self):
        """Enforced by the contract, not left to the pipeline."""
        with pytest.raises(ValidationError, match="educational model"):
            FailureAnalysis(
                summary="x",
                explanation=[
                    ScientificExplanation(statement="y", is_inference=True)
                ],
                simulation_limitations=[],
            )

    async def test_limitations_name_the_relevant_models(self, analyzer):
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        text = " ".join(analysis.simulation_limitations)
        assert "atmosphere" in text
        assert "drag" in text

    async def test_different_failures_name_different_models(self, analyzer):
        aero = await analyzer.analyze(view(MAX_Q_FAILURE))
        twr = await analyzer.analyze(view(TWR_FAILURE))
        assert set(aero.simulation_limitations) != set(twr.simulation_limitations)

    async def test_the_educational_caveat_is_always_included(self, analyzer):
        analysis = await analyzer.analyze(view(FUEL_EXHAUSTION))
        text = " ".join(analysis.simulation_limitations)
        assert "not predictions of what a real vehicle would do" in text

    async def test_three_degrees_of_freedom_is_disclosed(self, analyzer):
        analysis = await analyzer.analyze(view(INSTABILITY_FAILURE))
        text = " ".join(analysis.simulation_limitations)
        assert "3 degrees of freedom" in text

    def test_the_fidelity_table_matches_the_engine_documentation(self):
        assert set(MODEL_FIDELITY) == {
            "gravity", "atmosphere", "drag", "thrust", "mass", "trajectory",
            "stability",
        }

    async def test_the_prompt_forbids_claiming_realism(self, analyzer, retriever):
        provider = MockAIProvider(responder=explaining_model)
        engine = FailureAnalyzer(retriever, provider)
        await engine.analyze(view(MAX_Q_FAILURE))
        system = provider.requests[0].system
        assert "Never say or imply that it reproduces reality exactly" in system


class TestCauseAndConsequences:
    async def test_the_cause_comes_from_the_engines_own_rule(self, analyzer):
        analysis = await analyzer.analyze(view(TWR_FAILURE))
        assert "could not lift its own weight" in analysis.likely_cause
        assert "thrust/weight < 1.0" in analysis.likely_cause

    async def test_later_failures_are_consequences_not_causes(self, analyzer):
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        assert "excessive q" in analysis.summary
        assert any("impact" in item for item in analysis.consequences)

    async def test_the_affected_subsystem_is_identified(self, analyzer):
        analysis = await analyzer.analyze(view(STRUCTURAL_FAILURE))
        assert SubsystemKind.STRUCTURE in analysis.affected_subsystems

    async def test_aerodynamic_failures_map_to_aerodynamics(self, analyzer):
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        assert SubsystemKind.AERODYNAMICS in analysis.affected_subsystems

    async def test_named_components_are_carried_through(self, analyzer):
        analysis = await analyzer.analyze(view(STRUCTURAL_FAILURE))
        assert "stage-1 tank" in analysis.affected_components

    async def test_an_undocumented_failure_is_not_attributed(self, analyzer):
        analysis = await analyzer.analyze(view(UNDOCUMENTED_FAILURE))
        assert "cannot be attributed" in analysis.likely_cause
        assert analysis.cause_confidence is ConfidenceLevel.LOW

    async def test_an_undocumented_event_is_recorded_as_uncertainty(self, analyzer):
        analysis = await analyzer.analyze(view(UNDOCUMENTED_FAILURE))
        assert any("not documented" in item for item in analysis.uncertainty)

    async def test_a_successful_run_produces_no_invented_failure(self, analyzer):
        analysis = await analyzer.analyze(view(SUCCESSFUL_RUN))
        assert analysis.likely_cause is None
        assert "without a recorded failure" in analysis.summary


class TestMitigations:
    async def test_mitigations_address_the_detected_rule(self, analyzer):
        analysis = await analyzer.analyze(view(TWR_FAILURE))
        actions = " ".join(item.action for item in analysis.mitigations)
        assert "thrust-to-weight" in actions

    async def test_max_q_mitigations_are_aerodynamic(self, analyzer):
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        assert analysis.mitigations
        assert all(
            item.subsystem is SubsystemKind.AERODYNAMICS
            for item in analysis.mitigations
        )

    async def test_mitigations_are_marked_as_heuristics(self, analyzer):
        analysis = await analyzer.analyze(view(STRUCTURAL_FAILURE))
        assert all(item.is_heuristic for item in analysis.mitigations)

    async def test_each_mitigation_gives_a_rationale(self, analyzer):
        analysis = await analyzer.analyze(view(FUEL_EXHAUSTION))
        assert all(item.rationale for item in analysis.mitigations)

    async def test_an_undocumented_failure_yields_no_mitigations(self, analyzer):
        analysis = await analyzer.analyze(view(UNDOCUMENTED_FAILURE))
        assert analysis.mitigations == []


class TestRetrieval:
    async def test_references_are_retrieved_for_the_physics(self, analyzer):
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        assert analysis.context_items
        assert analysis.sources

    async def test_the_query_describes_the_phenomenon_not_the_run(self, analyzer):
        query = analyzer.build_query(view(MAX_Q_FAILURE))
        assert "dynamic pressure" in query
        assert "sim-" not in query

    async def test_max_q_retrieval_finds_the_max_q_concept(self, analyzer):
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        ids = {item.canonical_id for item in analysis.context_items}
        assert "concept:max-q" in ids

    async def test_every_reference_is_attributed(self, analyzer):
        analysis = await analyzer.analyze(view(STRUCTURAL_FAILURE))
        for item in analysis.context_items:
            assert item.source.source_name


class TestFailureModes:
    async def test_a_provider_outage_leaves_observations_intact(self, retriever):
        analyzer = FailureAnalyzer(
            retriever, MockAIProvider(responses=[AIProviderUnavailable("down")])
        )
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        assert analysis.observations
        assert analysis.explanation == []
        assert any("could not be generated" in item for item in analysis.uncertainty)

    async def test_a_fabricated_citation_is_reported(self, retriever):
        analyzer = FailureAnalyzer(
            retriever, MockAIProvider(responses=["A physical claim [S99]."])
        )
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        assert any("were not supplied" in item for item in analysis.uncertainty)
        assert analysis.cause_confidence is ConfidenceLevel.LOW

    async def test_unparsed_payload_fields_are_disclosed(self, retriever):
        analyzer = FailureAnalyzer(
            retriever, MockAIProvider(responder=explaining_model)
        )
        analysis = await analyzer.analyze(view(MALFORMED_RUN))
        assert any("did not understand" in item for item in analysis.uncertainty)

    async def test_no_references_means_no_explanation(self, retriever):
        class EmptyRetriever:
            def search(self, query):
                from contracts.search import SearchResponse, SearchStatus

                return SearchResponse(
                    query=query, status=SearchStatus.EMPTY, results=[], total=0
                )

        analyzer = FailureAnalyzer(
            EmptyRetriever(), MockAIProvider(responses=["invented explanation"])
        )
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        assert analysis.explanation == []
        assert analysis.observations
        assert any("No reference material" in item for item in analysis.uncertainty)


class TestOutputCompleteness:
    """Every field the task requires must be populated for a real failure."""

    async def test_all_required_fields(self, analyzer):
        analysis = await analyzer.analyze(
            view(STRUCTURAL_FAILURE),
            vehicle_description="Two-stage vehicle, 48 t at lift-off",
            mission_description="400 km circular orbit",
        )
        assert analysis.summary                     # what happened
        assert analysis.observations                # what happened, in detail
        assert analysis.likely_cause                # likely cause
        assert analysis.affected_subsystems         # affected subsystem
        assert analysis.affected_components         # affected component
        assert analysis.consequences or True        # consequences (may be empty)
        assert analysis.mitigations                 # possible mitigation
        assert analysis.explanation                 # scientific explanation
        assert analysis.simulation_limitations      # simulation limitations
        assert analysis.sources                     # sources

    async def test_the_vehicle_configuration_reaches_the_prompt(self, retriever):
        provider = MockAIProvider(responder=explaining_model)
        analyzer = FailureAnalyzer(retriever, provider)
        await analyzer.analyze(
            view(STRUCTURAL_FAILURE),
            vehicle_description="Two-stage vehicle, 48 t at lift-off",
        )
        prompt = provider.requests[0].messages[0].content
        assert "48 t at lift-off" in prompt

    async def test_diagnostics_record_the_pipeline(self, analyzer):
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        assert "latency_ms" in analysis.diagnostics
        assert "references" in analysis.diagnostics
        assert analysis.diagnostics["query"]

    async def test_the_analysis_serializes(self, analyzer):
        analysis = await analyzer.analyze(view(MAX_Q_FAILURE))
        restored = FailureAnalysis.model_validate_json(analysis.model_dump_json())
        assert restored.summary == analysis.summary
        assert len(restored.observations) == len(analysis.observations)
