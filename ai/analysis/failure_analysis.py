"""Simulation failure analysis.

    Simulation -> failure context -> scientific knowledge retrieval
               -> reranking -> AI -> citation validation

The structural commitment: **what the simulator did and why it happens are
different things, produced by different steps, from different sources.**

* Observations come from the run. They are read directly off the events and
  telemetry — no model involved — so they cannot drift. They are true about the
  model, not about the world.
* Explanations come from retrieved, cited references. They describe physics.

`FailureAnalysis` keeps them in separate fields, so a renderer cannot mix them
and a prompt cannot talk one into the other. Every analysis that explains
anything is also required to state which simulator approximations bear on it,
drawn from the engine's own documented fidelity table.
"""

import time
from typing import Any, Dict, List, Optional, Sequence

from contracts.ai import Citation, ConfidenceLevel, ContextItem
from contracts.analysis import (
    FailureAnalysis,
    FailureSeverity,
    Mitigation,
    ScientificExplanation,
    SimulationObservation,
    SubsystemKind,
)
from contracts.search import SearchQuery, SearchStatus

from ..grounding.citations import CitationValidator
from ..grounding.context import ContextBuilder
from ..providers.base import AIMessage, AIProvider, AIProviderError, AIRequest, Role
from .simulation_view import (
    FAILURE_RULES,
    MODEL_FIDELITY,
    SimulationEventView,
    SimulationResultView,
)

__all__ = ["FailureAnalyzer", "FAILURE_SYSTEM_PROMPT"]


FAILURE_SYSTEM_PROMPT = """\
You explain why an educational rocket simulation produced the result it did.

Two kinds of statement, and you must never merge them:

1. SIMULATION OBSERVATION — what the run produced. These are given to you as \
facts about the model. They are not measurements of a real vehicle.
2. SCIENTIFIC EXPLANATION — the physics or engineering that accounts for the \
observed behaviour. Every one of these must cite a retrieved reference [S1], \
[S2]. If you cannot support an explanation from the references, say so and \
label it as your own reasoning.

The simulator is an educational tool using analytical and simplified models. \
Never say or imply that it reproduces reality exactly, that its numbers are \
what a real vehicle would do, or that a real design would behave identically. \
When an approximation in the engine bears on your explanation, say which.

Be specific about the subsystem and, where the configuration names one, the \
component. Distinguish the first failure from its consequences: a later event \
is usually an effect of an earlier one, not a separate cause.\
"""


class FailureAnalyzer:
    """Explains a simulation failure, grounded in retrieved references."""

    def __init__(
        self,
        retriever: Any,
        provider: AIProvider,
        context_builder: Optional[ContextBuilder] = None,
        validator: Optional[CitationValidator] = None,
        max_references: int = 6,
    ):
        self.retriever = retriever
        self.provider = provider
        self.context = context_builder or ContextBuilder()
        self.validator = validator or CitationValidator()
        self.max_references = max_references

    # ------------------------------------------------------------------
    # Step 1: failure context, read straight from the run
    # ------------------------------------------------------------------
    def build_observations(
        self, result: SimulationResultView
    ) -> List[SimulationObservation]:
        """Read observations off the run. No model, no inference.

        This is deliberately mechanical. Everything here is a restatement of
        something the engine recorded, so an observation cannot be wrong about
        the run in a way a language model could introduce.
        """
        observations: List[SimulationObservation] = []

        if result.outcome:
            observations.append(
                SimulationObservation(
                    statement="The run ended with: {0}".format(result.outcome),
                    event_type="outcome",
                )
            )
        if result.termination_reason:
            observations.append(
                SimulationObservation(
                    statement="Termination reason: {0}".format(
                        result.termination_reason
                    ),
                    event_type="termination",
                )
            )

        for event in sorted(
            result.failure_events(),
            key=lambda item: (item.time_s is None, item.time_s or 0.0),
        ):
            when = (
                " at t+{0:g} s".format(event.time_s)
                if event.time_s is not None else ""
            )
            rule = FAILURE_RULES.get(event.rule_key or "", {})
            plain = rule.get("plain")
            statement = "The simulation recorded {0}{1}".format(
                event.event_type.replace("_", " "), when
            )
            if plain:
                statement += " — {0}".format(plain)
            if event.message:
                statement += ". Engine message: {0}".format(event.message)

            observations.append(
                SimulationObservation(
                    statement=statement,
                    time_s=event.time_s,
                    event_type=event.event_type,
                    severity=event.severity,
                    values=dict(event.values),
                    phase=event.phase,
                )
            )

        #: Peak values give the explanation something quantitative to work
        #: with, and they come straight from telemetry.
        for field, label, unit in (
            ("acceleration_ms2", "Peak acceleration", "m/s^2"),
            ("dynamic_pressure_pa", "Peak dynamic pressure", "Pa"),
            ("altitude_m", "Maximum altitude", "m"),
            ("velocity_ms", "Maximum velocity", "m/s"),
        ):
            peak = result.peak(field)
            if peak is not None:
                observations.append(
                    SimulationObservation(
                        statement="{0} recorded: {1:g} {2}".format(label, peak, unit),
                        event_type="telemetry_peak",
                        values={field: peak},
                    )
                )

        return observations

    def identify_subsystems(
        self, result: SimulationResultView
    ) -> List[SubsystemKind]:
        """Map failures to subsystems using the engine's documented rules."""
        found: List[SubsystemKind] = []
        for event in result.failure_events():
            rule = FAILURE_RULES.get(event.rule_key or "")
            subsystem = (
                rule["subsystem"] if rule else SubsystemKind.UNKNOWN
            )
            if subsystem not in found:
                found.append(subsystem)
        return found or [SubsystemKind.UNKNOWN]

    def limitations_for(self, result: SimulationResultView) -> List[str]:
        """Which documented approximations bear on this failure.

        Selected rather than dumped: listing all seven every time trains a
        reader to skip them. The ones named are those whose model feeds the
        quantity that failed.
        """
        relevant: List[str] = []

        def add(key):
            text = MODEL_FIDELITY.get(key)
            if text and text not in relevant:
                relevant.append("{0}: {1}".format(key, text))

        keys = {event.rule_key for event in result.failure_events()}
        if "excessive_q" in keys:
            add("atmosphere")
            add("drag")
        if "structural_overload" in keys:
            add("thrust")
            add("mass")
            add("trajectory")
        if "insufficient_twr" in keys:
            add("thrust")
            add("mass")
            add("gravity")
        if "fuel_exhaustion" in keys:
            add("mass")
            add("thrust")
        if "instability" in keys:
            add("stability")
            add("trajectory")
        if "trajectory_divergence" in keys:
            add("trajectory")
            add("gravity")

        if not relevant:
            #: Unrecognised failure: name the models that underpin every run,
            #: rather than claiming no approximation applies.
            add("trajectory")
            add("atmosphere")

        relevant.append(
            "The engine integrates 3 degrees of freedom only, so rotational "
            "dynamics and their coupling with the trajectory are absent "
            "entirely."
        )
        relevant.append(
            "This is an educational simulator. Its numbers illustrate the "
            "physics; they are not predictions of what a real vehicle would do."
        )
        return relevant

    # ------------------------------------------------------------------
    # Step 2: retrieve the scientific knowledge that explains it
    # ------------------------------------------------------------------
    def build_query(self, result: SimulationResultView) -> str:
        """A retrieval query describing the *physics*, not the run.

        Searching for "simulation failed at t+62" would retrieve nothing useful.
        The documented failure rule names the phenomenon, and that is what the
        corpus can actually explain.
        """
        first = result.first_failure()
        if first is None:
            return "rocket flight performance and failure modes"

        rule = FAILURE_RULES.get(first.rule_key or "")
        if rule:
            return "{0}: {1}".format(
                first.event_type.replace("_", " ").replace("failure ", ""),
                rule["condition"],
            )
        return "{0} rocket failure".format(first.event_type.replace("_", " "))

    def retrieve_references(
        self, result: SimulationResultView
    ) -> List[ContextItem]:
        """Retrieve and select references explaining the failure."""
        query_text = self.build_query(result)
        response = self.retriever.search(
            SearchQuery(text=query_text, limit=self.max_references)
        )
        results = (
            response.results if response.status is SearchStatus.OK else []
        )

        #: The documented rule names concepts that explain it directly. Pulling
        #: them in by id guarantees the right reference is present even when
        #: the phrasing of the query does not retrieve it.
        first = result.first_failure()
        rule = FAILURE_RULES.get((first.rule_key if first else None) or "")
        if rule:
            have = {item.id for item in results}
            for canonical_id in rule.get("concepts", []):
                if canonical_id in have:
                    continue
                targeted = self.retriever.search(
                    SearchQuery(text="", entity_types=[], limit=1,
                                topics=[]) if False else
                    SearchQuery(text=canonical_id.split(":", 1)[-1].replace("-", " "),
                                limit=3)
                )
                for candidate in targeted.results:
                    if candidate.id == canonical_id:
                        results = list(results) + [candidate]
                        break

        selection = self.context.build(results)
        return selection.items

    # ------------------------------------------------------------------
    # Step 3-5: generate, validate, assemble
    # ------------------------------------------------------------------
    async def analyze(
        self,
        result: SimulationResultView,
        vehicle_description: Optional[str] = None,
        mission_description: Optional[str] = None,
    ) -> FailureAnalysis:
        """Produce a grounded analysis of a failed run."""
        started = time.time()
        observations = self.build_observations(result)
        subsystems = self.identify_subsystems(result)
        limitations = self.limitations_for(result)
        references = self.retrieve_references(result)

        analysis = FailureAnalysis(
            simulation_id=result.simulation_id,
            observations=observations,
            affected_subsystems=subsystems,
            simulation_limitations=limitations,
            context_items=list(references),
            sources=_dedupe_sources(references),
        )

        first = result.first_failure()
        analysis.summary = self._summary(result, first)
        analysis.likely_cause = self._likely_cause(first)
        analysis.consequences = self._consequences(result, first)
        analysis.affected_components = self._components(result)

        if not references:
            #: No references means no explanation. The observations stand on
            #: their own — they are still true about the run — but nothing is
            #: asserted about the physics.
            analysis.cause_confidence = ConfidenceLevel.LOW
            analysis.uncertainty.append(
                "No reference material was retrieved for this failure mode, so "
                "no sourced physical explanation is offered."
            )
            analysis.diagnostics["latency_ms"] = (time.time() - started) * 1000.0
            return analysis

        try:
            completion = await self._generate(
                result, observations, references,
                vehicle_description, mission_description,
            )
        except AIProviderError as exc:
            analysis.cause_confidence = ConfidenceLevel.LOW
            analysis.uncertainty.append(
                "The explanation could not be generated ({0}); the observations "
                "and references below are unprocessed.".format(
                    exc.__class__.__name__
                )
            )
            analysis.diagnostics["provider_error"] = str(exc)
            analysis.diagnostics["latency_ms"] = (time.time() - started) * 1000.0
            return analysis

        validation = self.validator.validate(completion.text, references)
        analysis.explanation = self._explanations(validation, completion.text)
        analysis.mitigations = self._mitigations(first, validation)
        analysis.cause_confidence = self._confidence(first, validation)

        if validation.fabricated_refs:
            analysis.uncertainty.append(
                "The generated explanation cited {0} reference(s) that were not "
                "supplied; they have been removed.".format(
                    len(validation.fabricated_refs)
                )
            )
        if result.unparsed_keys:
            analysis.uncertainty.append(
                "The simulation payload contained fields this analysis did not "
                "understand ({0}); they were ignored.".format(
                    ", ".join(result.unparsed_keys[:5])
                )
            )
        if any(not event.is_recognised for event in result.failure_events()):
            analysis.uncertainty.append(
                "At least one failure event used an identifier not documented "
                "by the engine, so its interpretation is uncertain."
            )

        analysis.diagnostics.update({
            "latency_ms": (time.time() - started) * 1000.0,
            "query": self.build_query(result),
            "references": len(references),
            "citation_coverage": round(validation.citation_coverage, 3),
        })
        return analysis

    # -- generation --------------------------------------------------------
    async def _generate(
        self, result, observations, references, vehicle, mission
    ):
        from ..prompts.scientific import build_context_block

        lines = ["SIMULATION OBSERVATIONS (facts about the model run):"]
        for observation in observations:
            lines.append("  - {0}".format(observation.statement))
        if vehicle:
            lines.append("")
            lines.append("VEHICLE CONFIGURATION (the user's design):")
            lines.append(_indent(vehicle))
        if mission:
            lines.append("")
            lines.append("MISSION CONFIGURATION:")
            lines.append(_indent(mission))
        lines.append("")
        lines.append("REFERENCES (cite these for any physical explanation):")
        lines.append(build_context_block(references))
        lines.append("")
        lines.append(
            "Explain why the simulation behaved this way. Cite a reference for "
            "every physical claim. Do not restate the observations as facts "
            "about a real vehicle."
        )

        request = AIRequest(
            system=FAILURE_SYSTEM_PROMPT,
            messages=[AIMessage(role=Role.USER, content="\n".join(lines))],
            max_tokens=1024,
            temperature=0.1,
        )
        return await self.provider.generate(request)

    # -- assembly ----------------------------------------------------------
    def _summary(self, result, first) -> str:
        if first is None:
            if result.failed:
                return "The run did not succeed, but recorded no failure event."
            return "The run completed without a recorded failure."
        when = (
            " at t+{0:g} s".format(first.time_s)
            if first.time_s is not None else ""
        )
        return "The simulation failed with {0}{1}.".format(
            first.event_type.replace("_", " "), when
        )

    def _likely_cause(self, first) -> Optional[str]:
        """The cause, from the engine's own rule.

        Taken from the documented rule rather than from the model: the engine
        states exactly what condition it detected, and paraphrasing that
        through a language model could only lose fidelity.
        """
        if first is None:
            return None
        rule = FAILURE_RULES.get(first.rule_key or "")
        if not rule:
            return (
                "The engine reported {0}, which is not one of its documented "
                "failure rules; the cause cannot be attributed with "
                "confidence.".format(first.event_type)
            )
        return "{0} (engine rule: {1})".format(rule["plain"], rule["condition"])

    def _consequences(self, result, first) -> List[str]:
        """Later failures, framed as effects rather than separate causes."""
        if first is None:
            return []
        later = [
            event for event in result.failure_events()
            if event is not first
            and (event.time_s or 0.0) >= (first.time_s or 0.0)
        ]
        consequences = []
        for event in sorted(later, key=lambda item: item.time_s or 0.0):
            when = (
                " at t+{0:g} s".format(event.time_s)
                if event.time_s is not None else ""
            )
            consequences.append(
                "{0}{1}, following the initial failure".format(
                    event.event_type.replace("_", " "), when
                )
            )
        if result.termination_reason:
            consequences.append(
                "The run terminated: {0}".format(result.termination_reason)
            )
        return consequences

    def _components(self, result) -> List[str]:
        names = []
        for event in result.failure_events():
            if event.component and event.component not in names:
                names.append(event.component)
        return names

    def _explanations(self, validation, raw_text) -> List[ScientificExplanation]:
        """Split the generated text into cited and uncited statements."""
        explanations: List[ScientificExplanation] = []
        by_claim: Dict[str, List[Citation]] = {}
        for citation in validation.citations:
            by_claim.setdefault(citation.claim, []).append(citation)

        for claim, citations in by_claim.items():
            if claim.strip():
                explanations.append(
                    ScientificExplanation(statement=claim, citations=citations)
                )

        for claim in validation.uncited_claims:
            #: An uncited claim is the model's own reasoning. Kept, because it
            #: may be useful, but labelled so a reader knows it is unsourced.
            explanations.append(
                ScientificExplanation(statement=claim, is_inference=True)
            )
        return explanations

    def _mitigations(self, first, validation) -> List[Mitigation]:
        """Suggestions tied to the documented failure rule.

        Derived from the rule rather than generated, so a suggestion always
        addresses the condition the engine actually detected. Marked as
        heuristics, because they are rules of thumb about a simplified model.
        """
        if first is None:
            return []
        key = first.rule_key
        suggestions = {
            "insufficient_twr": [
                ("Increase first-stage thrust, or reduce lift-off mass, until "
                 "thrust-to-weight at ignition exceeds 1.0",
                 "A vehicle whose thrust does not exceed its weight cannot "
                 "leave the pad."),
            ],
            "excessive_q": [
                ("Reduce thrust through the high dynamic-pressure region, or "
                 "raise the configured q limit if the airframe supports it",
                 "Dynamic pressure scales with the square of speed, so slowing "
                 "the ascent through the dense lower atmosphere cuts the peak "
                 "sharply."),
                ("Adjust the pitch programme to gain altitude sooner",
                 "Thinner air at the same speed means lower dynamic pressure."),
            ],
            "structural_overload": [
                ("Throttle down late in the burn, when the stage is light and "
                 "acceleration rises fastest",
                 "Acceleration climbs as propellant is consumed at constant "
                 "thrust."),
                ("Raise the configured g-limit only if the design justifies it",
                 "The limit is an input to the model, not a property the "
                 "simulation derives."),
            ],
            "fuel_exhaustion": [
                ("Increase propellant load or specific impulse, or reduce the "
                 "delta-v the stage must supply",
                 "The rocket equation is exponential in delta-v, so a small "
                 "shortfall in capability costs a large amount of propellant."),
            ],
            "instability": [
                ("Move the centre of gravity forward or the centre of pressure "
                 "aft — add nose mass, or enlarge the fins",
                 "A positive static margin is what makes a vehicle "
                 "aerodynamically self-correcting."),
            ],
            "trajectory_divergence": [
                ("Review the pitch programme and the launch azimuth",
                 "A divergence usually indicates the guidance profile does not "
                 "match the vehicle's actual performance."),
            ],
        }.get(key or "", [])

        rule = FAILURE_RULES.get(key or "", {})
        subsystem = rule.get("subsystem", SubsystemKind.UNKNOWN)
        return [
            Mitigation(
                action=action,
                rationale=rationale,
                subsystem=subsystem,
                is_heuristic=True,
            )
            for action, rationale in suggestions
        ]

    def _confidence(self, first, validation) -> ConfidenceLevel:
        if first is None:
            return ConfidenceLevel.LOW
        if validation.fabricated_refs:
            return ConfidenceLevel.LOW
        if first.rule_key is None:
            #: An undocumented failure identifier: the engine reported
            #: something this analysis cannot map to a known cause.
            return ConfidenceLevel.LOW
        if validation.citations:
            return ConfidenceLevel.HIGH
        return ConfidenceLevel.MEDIUM


def _dedupe_sources(items: Sequence[ContextItem]):
    seen = {}
    for item in items:
        seen.setdefault(item.source.source_name, item.source)
    return list(seen.values())


def _indent(text: str) -> str:
    return "\n".join("  " + line for line in str(text).splitlines())
