"""Mission intelligence: source-backed fields, no invented events, visible
conflicts."""

import re
from datetime import date

import pytest

from ai.missions import MISSION_SYSTEM_PROMPT, MissionIntelligence
from ai.providers import AIProviderUnavailable, MockAIProvider
from contracts.ai import ConfidenceLevel
from contracts.analysis import MissionSummary
from contracts.provenance import SourceReference, SourceType


def citing_model(request):
    content = request.messages[0].content
    refs = re.findall(r"^\[(S\d+)\]", content, re.MULTILINE)
    cites = " ".join("[{0}]".format(ref) for ref in refs[:2]) or ""
    return "A short factual summary of the mission {0}.".format(cites)


@pytest.fixture
def intelligence(retriever, record_store):
    return MissionIntelligence(
        retriever, MockAIProvider(responder=citing_model),
        record_store=record_store,
    )


class TestKnownMissions:
    async def test_apollo_11(self, intelligence):
        summary = await intelligence.summarize("Apollo 11")
        assert summary is not None
        assert summary.name == "Apollo 11"
        assert summary.agency == "NASA"
        assert summary.sources

    async def test_apollo_11_objectives_come_from_the_record(self, intelligence):
        summary = await intelligence.summarize("Apollo 11")
        assert summary.scientific_objectives
        assert any("lunar landing" in item.lower()
                   for item in summary.scientific_objectives)

    async def test_apollo_11_timeline_uses_recorded_dates(self, intelligence):
        summary = await intelligence.summarize("Apollo 11")
        labels = {entry.label for entry in summary.timeline}
        assert "Launch" in labels
        launch = [e for e in summary.timeline if e.label == "Launch"][0]
        assert "1969-07-16" in launch.when

    async def test_apollo_13_outcome_and_anomalies(self, intelligence):
        summary = await intelligence.summarize("Apollo 13")
        assert summary.outcome
        assert any("oxygen tank" in item.lower() for item in summary.major_events)

    async def test_voyager_2_destinations(self, intelligence):
        summary = await intelligence.summarize("Voyager 2")
        assert summary.destinations
        joined = " ".join(summary.destinations).lower()
        assert "uranus" in joined and "neptune" in joined

    async def test_chandrayaan_3_agency(self, intelligence):
        summary = await intelligence.summarize("Chandrayaan-3")
        assert summary.agency == "ISRO"

    async def test_galileo_findings(self, intelligence):
        summary = await intelligence.summarize("Galileo")
        assert summary.scientific_findings

    async def test_launch_vehicle_is_readable(self, intelligence):
        summary = await intelligence.summarize("Apollo 11")
        assert summary.launch_vehicle == "Saturn V"

    async def test_curiosity_matches_by_alias(self, intelligence):
        summary = await intelligence.summarize("Curiosity")
        assert summary is not None
        assert "Curiosity" in summary.name


class TestNoInvention:
    async def test_an_unknown_mission_returns_nothing(self, intelligence):
        """An empty summary would render as a real page with nothing in it."""
        assert await intelligence.summarize("Beagle 2") is None

    async def test_structured_fields_do_not_come_from_the_model(
        self, retriever, record_store
    ):
        """A model producing nonsense must not change any structured field."""
        good = MissionIntelligence(
            retriever, MockAIProvider(responder=citing_model),
            record_store=record_store,
        )
        bad = MissionIntelligence(
            retriever,
            MockAIProvider(responses=[
                "Apollo 11 launched in 1492 and landed on Neptune."
            ]),
            record_store=record_store,
        )
        first = await good.summarize("Apollo 11")
        second = await bad.summarize("Apollo 11")

        assert first.timeline[0].when == second.timeline[0].when
        assert first.destinations == second.destinations
        assert first.agency == second.agency

    async def test_missing_fields_are_reported_not_filled(self, intelligence):
        summary = await intelligence.summarize("Juno")
        assert isinstance(summary.unknown_fields, list)
        for field in summary.unknown_fields:
            assert not getattr(summary, field)

    async def test_an_empty_timeline_stays_empty(self, retriever, record_store):
        """A mission record with no dates must not acquire any."""
        from data.models import Mission

        record = Mission(
            canonical_id="mission:dateless",
            name="Dateless Mission",
            source_references=[
                SourceReference(source_name="bundled_reference",
                                source_type=SourceType.BUNDLED_REFERENCE)
            ],
        )
        record_store.put(record)
        engine = MissionIntelligence(
            retriever, MockAIProvider(responses=["Summary [S1]."]),
            record_store=record_store,
        )
        summary = await engine.summarize("Dateless Mission",
                                         canonical_id="mission:dateless")
        if summary is not None:
            assert summary.timeline == []
            assert "timeline" in summary.unknown_fields

    def test_the_prompt_forbids_adding_facts(self):
        assert "Do not add events" in MISSION_SYSTEM_PROMPT
        assert "never filled in" in MISSION_SYSTEM_PROMPT

    async def test_a_similar_mission_is_not_merged_in(self, intelligence):
        """Apollo 11 and Apollo 13 must not become one mission history."""
        summary = await intelligence.summarize("Apollo 11")
        joined = " ".join(summary.major_events).lower()
        assert "oxygen tank" not in joined


class TestSourceConflicts:
    def _conflicting_records(self, record_store):
        from data.models import Mission, MissionOutcome
        from data.models.enums import MissionStatus

        first = Mission(
            canonical_id="mission:disputed",
            name="Disputed Mission",
            agency="NASA",
            launch_date=date(1999, 1, 1),
            source_references=[
                SourceReference(source_name="bundled_reference",
                                source_type=SourceType.BUNDLED_REFERENCE)
            ],
        )
        second = Mission(
            canonical_id="mission:disputed-alt",
            name="Disputed Mission",
            agency="ESA",
            launch_date=date(2000, 6, 1),
            source_references=[
                SourceReference(source_name="nasa_ntrs",
                                source_type=SourceType.LITERATURE)
            ],
        )
        record_store.put(first)
        record_store.put(second)
        return first, second

    async def test_disagreeing_sources_are_reported(
        self, retriever, record_store
    ):
        first, second = self._conflicting_records(record_store)
        engine = MissionIntelligence(
            retriever, MockAIProvider(responder=citing_model),
            record_store=record_store,
        )
        summary = MissionSummary(name="Disputed Mission")
        engine._detect_conflicts(summary, [first, second])

        assert summary.has_conflicts
        fields = {conflict.field for conflict in summary.conflicts}
        assert "agency" in fields

    async def test_both_values_are_shown(self, retriever, record_store):
        first, second = self._conflicting_records(record_store)
        engine = MissionIntelligence(retriever, MockAIProvider(),
                                     record_store=record_store)
        summary = MissionSummary(name="Disputed Mission")
        engine._detect_conflicts(summary, [first, second])

        agency = [c for c in summary.conflicts if c.field == "agency"][0]
        assert set(agency.values.values()) == {"NASA", "ESA"}

    async def test_neither_value_is_selected(self, retriever, record_store):
        first, second = self._conflicting_records(record_store)
        engine = MissionIntelligence(retriever, MockAIProvider(),
                                     record_store=record_store)
        summary = MissionSummary(name="Disputed Mission")
        engine._detect_conflicts(summary, [first, second])
        assert "neither has been selected" in summary.conflicts[0].note

    async def test_a_conflict_lowers_confidence(self, retriever, record_store):
        first, second = self._conflicting_records(record_store)
        engine = MissionIntelligence(retriever, MockAIProvider(),
                                     record_store=record_store)
        summary = MissionSummary(name="Disputed Mission")
        engine._detect_conflicts(summary, [first, second])
        assert engine._confidence(summary, [first, second]) is (
            ConfidenceLevel.MEDIUM
        )

    async def test_the_conflict_reaches_the_prompt(self, retriever, record_store):
        first, second = self._conflicting_records(record_store)
        provider = MockAIProvider(responder=citing_model)
        engine = MissionIntelligence(retriever, provider,
                                     record_store=record_store)
        summary = MissionSummary(name="Disputed Mission")
        engine._detect_conflicts(summary, [first, second])
        references = engine._retrieve_references("Apollo 11", [first])
        if references:
            await engine._generate(summary, references)
            prompt = provider.requests[0].messages[0].content
            assert "SOURCE CONFLICTS" in prompt
            assert "choose neither" in prompt

    async def test_agreeing_records_produce_no_conflict(self, intelligence):
        summary = await intelligence.summarize("Apollo 11")
        assert not summary.has_conflicts

    def test_the_prompt_forbids_choosing_between_sources(self):
        assert "Do not choose between them" in MISSION_SYSTEM_PROMPT


class TestSourcing:
    async def test_every_summary_carries_sources(self, intelligence):
        for name in ("Apollo 11", "Voyager 2", "Juno"):
            summary = await intelligence.summarize(name)
            assert summary.sources, name

    async def test_citations_resolve_to_supplied_references(self, intelligence):
        summary = await intelligence.summarize("Apollo 11")
        for citation in summary.citations:
            assert citation.verified

    async def test_ntrs_documents_are_pulled_in_when_available(
        self, retriever, record_store
    ):
        engine = MissionIntelligence(
            retriever, MockAIProvider(responder=citing_model),
            record_store=record_store,
        )
        references = engine._retrieve_references("Apollo", [])
        assert references

    async def test_a_provider_outage_keeps_the_structured_fields(
        self, retriever, record_store
    ):
        engine = MissionIntelligence(
            retriever, MockAIProvider(responses=[AIProviderUnavailable("down")]),
            record_store=record_store,
        )
        summary = await engine.summarize("Apollo 11")
        assert summary is not None
        assert summary.agency == "NASA"
        assert summary.timeline
        #: The fallback prose is assembled from the record, not generated.
        assert "Apollo 11" in summary.summary

    async def test_the_fallback_summary_only_uses_populated_fields(
        self, retriever, record_store
    ):
        engine = MissionIntelligence(
            retriever, MockAIProvider(responses=[AIProviderUnavailable("down")]),
            record_store=record_store,
        )
        summary = await engine.summarize("Chandrayaan-3")
        assert "ISRO" in summary.summary

    async def test_a_fabricated_citation_lowers_confidence(
        self, retriever, record_store
    ):
        engine = MissionIntelligence(
            retriever, MockAIProvider(responses=["Summary [S99]."]),
            record_store=record_store,
        )
        summary = await engine.summarize("Apollo 11")
        assert summary.confidence is ConfidenceLevel.LOW
        assert "[S99]" not in summary.summary


class TestCompleteness:
    """Every field the task names must be supported."""

    async def test_all_supported_fields(self, intelligence):
        summary = await intelligence.summarize("Apollo 11")
        assert summary.summary                  # mission summary
        assert summary.scientific_objectives    # scientific objective
        assert summary.timeline                 # timeline
        assert summary.spacecraft               # spacecraft
        assert summary.launch_vehicle           # launch vehicle
        assert summary.destinations             # destination
        assert summary.outcome                  # mission outcome
        assert summary.scientific_findings      # scientific findings
        #: major_events may legitimately be empty for a mission with no
        #: recorded anomalies; Apollo 13 covers the populated case.

    async def test_major_events_are_populated_where_recorded(self, intelligence):
        summary = await intelligence.summarize("Apollo 13")
        assert summary.major_events

    async def test_the_summary_serializes(self, intelligence):
        summary = await intelligence.summarize("Apollo 11")
        restored = MissionSummary.model_validate_json(summary.model_dump_json())
        assert restored.name == summary.name
        assert len(restored.timeline) == len(summary.timeline)
