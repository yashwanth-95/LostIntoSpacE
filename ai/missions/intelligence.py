"""Mission intelligence.

Assembles a `MissionSummary` from whatever sources actually hold the mission:
curated reference records, NTRS document metadata, and any agency data that has
been ingested.

The design follows the same split that failure analysis uses, for the same
reason. **Structured fields are read from records; only the narrative summary is
generated.** Timeline entries, objectives, spacecraft, destinations and outcomes
come from canonical `Mission` records — so "do not invent mission events" is not
a request to the model, it is a property of where the data comes from. The model
never sees an empty field it might feel obliged to fill.

Two consequences are visible in the output:

* `unknown_fields` lists what the sources did not cover. An empty timeline is
  reported as an empty timeline, never padded.
* `conflicts` lists disagreements between sources, with both values and both
  source names. Nothing silently picks a winner — the data-quality engine owns
  that decision, and duplicating it here would eventually contradict it.
"""

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from contracts.ai import Citation, ConfidenceLevel, ContextItem
from contracts.analysis import (
    MissionSummary,
    MissionTimelineEntry,
    SourceConflict,
)
from contracts.provenance import SourceReference, SourceType
from contracts.search import SearchEntityType, SearchQuery, SearchStatus

from ..grounding.citations import CitationValidator
from ..grounding.context import ContextBuilder
from ..providers.base import AIMessage, AIProvider, AIProviderError, AIRequest, Role

__all__ = ["MissionIntelligence", "MISSION_SYSTEM_PROMPT"]


MISSION_SYSTEM_PROMPT = """\
You write short, factual summaries of space missions from supplied records.

Use only what the records contain. Do not add events, dates, instruments, \
findings or outcomes that are not in them — not even ones you are confident \
about. A missing detail is reported as missing, never filled in.

Cite a reference [S1], [S2] for every factual statement.

Where two records disagree, say that they disagree and give both values with \
their sources. Do not choose between them.

Where a record is uncertain or a value is approximate, keep that uncertainty in \
your wording. Do not sharpen an approximate figure into a precise one.

Write two to four sentences. Prefer the records' own terminology.\
"""

#: Fields a complete mission summary would carry. Anything absent after
#: assembly is listed in `unknown_fields` rather than left silently blank.
_EXPECTED_FIELDS = (
    "agency", "scientific_objectives", "timeline", "spacecraft",
    "launch_vehicle", "destinations", "major_events", "outcome",
    "scientific_findings",
)


class MissionIntelligence:
    """Builds source-backed mission summaries."""

    def __init__(
        self,
        retriever: Any,
        provider: AIProvider,
        record_store: Optional[Any] = None,
        context_builder: Optional[ContextBuilder] = None,
        validator: Optional[CitationValidator] = None,
        max_references: int = 6,
    ):
        self.retriever = retriever
        self.provider = provider
        #: Anything with `.get(canonical_id)` returning a canonical record —
        #: the keyword index satisfies it via its documents.
        self.record_store = record_store
        self.context = context_builder or ContextBuilder()
        self.validator = validator or CitationValidator()
        self.max_references = max_references

    # ------------------------------------------------------------------
    async def summarize(
        self, mission_name: str, canonical_id: Optional[str] = None
    ) -> Optional[MissionSummary]:
        """Assemble a summary, or `None` when no mission matches.

        Returning `None` rather than an empty summary is deliberate: a summary
        object for a mission the corpus does not hold would render as a real
        page with nothing in it.
        """
        started = time.time()
        records = self._find_mission_records(mission_name, canonical_id)
        if not records:
            return None

        primary = records[0]
        summary = MissionSummary(
            canonical_id=getattr(primary, "canonical_id", None),
            name=getattr(primary, "name", mission_name) or mission_name,
        )

        self._fill_structured_fields(summary, primary)
        self._detect_conflicts(summary, records)

        references = self._retrieve_references(summary.name, records)
        summary.sources = _dedupe_sources(references)

        fabricated = False
        if references:
            try:
                completion = await self._generate(summary, references)
                validation = self.validator.validate(completion.text, references)
                summary.summary = validation.cleaned_answer
                summary.citations = validation.citations
                fabricated = bool(validation.fabricated_refs)
            except AIProviderError:
                #: The structured fields are already complete and sourced. A
                #: provider outage costs the prose, not the content.
                summary.summary = self._fallback_summary(summary)
        else:
            summary.summary = self._fallback_summary(summary)

        summary.unknown_fields = self._unknown_fields(summary)
        summary.confidence = self._confidence(summary, records, fabricated)
        return summary

    # -- record lookup -----------------------------------------------------
    def _find_mission_records(
        self, mission_name: str, canonical_id: Optional[str]
    ) -> List[Any]:
        """Every canonical record describing this mission.

        More than one is the interesting case: two records for the same mission
        from different sources is exactly what produces a conflict worth
        showing.
        """
        found: List[Any] = []

        if canonical_id and self.record_store is not None:
            record = self._record(canonical_id)
            if record is not None:
                found.append(record)

        response = self.retriever.search(
            SearchQuery(
                text=mission_name,
                entity_types=[SearchEntityType.MISSION],
                limit=5,
            )
        )
        if response.status is SearchStatus.OK:
            for result in response.results:
                record = self._record(result.id)
                if record is None:
                    continue
                if any(
                    getattr(item, "canonical_id", None) == result.id
                    for item in found
                ):
                    continue
                #: Only records whose name actually matches. A search for
                #: "Apollo 11" that also returns Apollo 13 must not merge them.
                if _names_match(mission_name, getattr(record, "name", "")):
                    found.append(record)
        return found

    def _record(self, canonical_id: str):
        if self.record_store is None:
            return None
        getter = getattr(self.record_store, "get_record", None) or getattr(
            self.record_store, "get", None
        )
        return getter(canonical_id) if getter else None

    # -- structured assembly -----------------------------------------------
    def _fill_structured_fields(self, summary: MissionSummary, record) -> None:
        """Read every structured field off the canonical record.

        No model involved, so nothing here can be invented.
        """
        summary.agency = getattr(record, "agency", None)
        summary.scientific_objectives = list(
            getattr(record, "objectives", []) or []
        )
        summary.spacecraft = [
            name for name in [getattr(record, "name", None)] if name
        ]
        summary.launch_vehicle = _readable_id(
            getattr(record, "launch_vehicle_canonical_id", None)
        )
        summary.destinations = [
            _readable_id(item)
            for item in (getattr(record, "target_canonical_ids", []) or [])
        ]

        outcome = getattr(record, "outcome", None)
        if outcome is not None:
            status = getattr(outcome, "status", None)
            summary.outcome = status.value if status is not None else None
            summary.scientific_findings = list(
                getattr(outcome, "achievements", []) or []
            )
            summary.major_events = (
                list(getattr(outcome, "anomalies", []) or [])
                + list(getattr(outcome, "published_lessons", []) or [])
            )

        summary.timeline = self._timeline(record)

    def _timeline(self, record) -> List[MissionTimelineEntry]:
        """Timeline entries, built only from dates the record carries."""
        entries: List[MissionTimelineEntry] = []
        launch = getattr(record, "launch_date", None)
        end = getattr(record, "end_date", None)

        if launch is not None:
            entries.append(
                MissionTimelineEntry(
                    label="Launch",
                    when=str(launch),
                    description="Mission launched",
                )
            )
        if end is not None:
            entries.append(
                MissionTimelineEntry(
                    label="End of mission",
                    when=str(end),
                    description="Mission concluded",
                )
            )
        return entries

    # -- conflicts ---------------------------------------------------------
    def _detect_conflicts(
        self, summary: MissionSummary, records: Sequence[Any]
    ) -> None:
        """Report disagreement between records describing the same mission."""
        if len(records) < 2:
            return

        for field in ("agency", "launch_date", "end_date"):
            values: Dict[str, str] = {}
            for record in records:
                value = getattr(record, field, None)
                if value in (None, ""):
                    continue
                source = _source_name(record)
                values[source] = str(value)
            if len(set(values.values())) > 1:
                summary.conflicts.append(
                    SourceConflict(
                        field=field,
                        values=values,
                        note=(
                            "Sources disagree on {0}. Both values are shown; "
                            "neither has been selected.".format(field)
                        ),
                    )
                )

    # -- references and generation -----------------------------------------
    def _retrieve_references(
        self, mission_name: str, records: Sequence[Any]
    ) -> List[ContextItem]:
        """Retrieve supporting material, preferring authoritative sources."""
        response = self.retriever.search(
            SearchQuery(text=mission_name, limit=self.max_references)
        )
        results = (
            response.results if response.status is SearchStatus.OK else []
        )
        #: NTRS technical documents are the strongest support available for a
        #: mission claim, so they are pulled in explicitly when the general
        #: query did not surface one.
        if not any(
            result.entity_type is SearchEntityType.DOCUMENT for result in results
        ):
            documents = self.retriever.search(
                SearchQuery(
                    text=mission_name,
                    entity_types=[SearchEntityType.DOCUMENT],
                    limit=2,
                )
            )
            if documents.status is SearchStatus.OK:
                results = list(results) + list(documents.results)

        return self.context.build(results).items

    async def _generate(self, summary: MissionSummary, references):
        from ..prompts.scientific import build_context_block

        facts = ["MISSION RECORD:", "  name: {0}".format(summary.name)]
        for field in ("agency", "launch_vehicle", "outcome"):
            value = getattr(summary, field, None)
            if value:
                facts.append("  {0}: {1}".format(field, value))
        for field in ("scientific_objectives", "destinations",
                      "scientific_findings", "major_events"):
            values = getattr(summary, field, None) or []
            if values:
                facts.append("  {0}: {1}".format(field, "; ".join(values)))
        for entry in summary.timeline:
            facts.append("  timeline: {0} — {1}".format(entry.label, entry.when))
        if summary.conflicts:
            facts.append("  SOURCE CONFLICTS (report both, choose neither):")
            for conflict in summary.conflicts:
                facts.append("    {0}: {1}".format(conflict.field, conflict.values))

        content = "\n".join(
            facts
            + ["", "REFERENCES:", build_context_block(references), "",
               "Write a short factual summary of this mission, citing the "
               "references. Add nothing the records do not contain."]
        )
        return await self.provider.generate(
            AIRequest(
                system=MISSION_SYSTEM_PROMPT,
                messages=[AIMessage(role=Role.USER, content=content)],
                max_tokens=512,
                temperature=0.1,
            )
        )

    def _fallback_summary(self, summary: MissionSummary) -> str:
        """A summary assembled from the record alone, with no model.

        Terse, but every clause traces to a field that was actually populated.
        """
        parts = [summary.name]
        if summary.agency:
            parts.append("an {0} mission".format(summary.agency))
        if summary.destinations:
            parts.append("to {0}".format(", ".join(summary.destinations)))
        launch = next(
            (entry.when for entry in summary.timeline if entry.label == "Launch"),
            None,
        )
        if launch:
            parts.append("launched {0}".format(launch))
        text = " ".join(parts).strip()
        if summary.outcome:
            text += ". Outcome: {0}".format(summary.outcome)
        return text + "." if text and not text.endswith(".") else text

    # -- completeness ------------------------------------------------------
    def _unknown_fields(self, summary: MissionSummary) -> List[str]:
        """Which expected fields the sources did not cover."""
        missing = []
        for field in _EXPECTED_FIELDS:
            value = getattr(summary, field, None)
            if value in (None, "", [], {}):
                missing.append(field)
        return missing

    def _confidence(
        self, summary: MissionSummary, records, fabricated: bool = False
    ) -> ConfidenceLevel:
        if fabricated:
            #: Checked first. A summary whose prose cited a source that does
            #: not exist is untrustworthy however complete its fields are.
            return ConfidenceLevel.LOW
        if summary.conflicts:
            #: A disagreement is not a reason to hide the summary, but it is a
            #: reason not to present it as settled.
            return ConfidenceLevel.MEDIUM
        authoritative = any(
            source.source_type in (
                SourceType.PRIMARY_SCIENTIFIC, SourceType.LITERATURE,
                SourceType.AGENCY_PUBLIC_API,
            )
            for source in summary.sources
        )
        if len(summary.unknown_fields) > 5:
            return ConfidenceLevel.LOW
        if authoritative and summary.citations:
            return ConfidenceLevel.HIGH
        return ConfidenceLevel.MEDIUM


# ----------------------------------------------------------------------
def _dedupe_sources(items: Sequence[ContextItem]) -> List[SourceReference]:
    seen: Dict[str, SourceReference] = {}
    for item in items:
        seen.setdefault(item.source.source_name, item.source)
    return list(seen.values())


def _source_name(record) -> str:
    source = getattr(record, "primary_source", None)
    return source.source_name if source is not None else "unknown"


def _readable_id(canonical_id: Optional[str]) -> Optional[str]:
    """Turn `planet:jupiter` into `Jupiter` for display."""
    if not canonical_id:
        return None
    tail = str(canonical_id).split(":", 1)[-1]
    return tail.replace("-", " ").title()


def _names_match(query: str, name: str) -> bool:
    """Whether a record's name is plausibly the mission that was asked for.

    Deliberately strict: merging two records that are not the same mission
    would fabricate a mission history, which is the exact failure this module
    is built to avoid.
    """
    left = str(query or "").strip().lower()
    right = str(name or "").strip().lower()
    if not left or not right:
        return False
    if left == right:
        return True
    #: Substring either way covers "Apollo 11" against "Apollo 11 (AS-506)"
    #: and "Curiosity" against "Mars Science Laboratory (Curiosity)".
    return left in right or right in left
