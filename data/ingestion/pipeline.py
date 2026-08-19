"""The unified multi-source ingestion pipeline.

    Source -> Adapter -> Raw Record -> Parser -> Normalizer -> Validator
           -> Entity Resolution -> Provenance -> Canonical Record -> Index

One `SourcePlan` per source describes how to fetch and how to normalize; the
pipeline runs the shared stages identically for all of them. That is what makes
"add a source" a matter of registering a plan rather than editing the pipeline.

**Failure isolation is the central design property.** Each source runs inside
its own guard. A provider that times out, returns nonsense, or raises anywhere
in its own branch marks *that source* failed and leaves every other source's
records intact. There is no path where one bad provider empties the run.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from contracts._time import utc_now

from ..entity_resolution.resolver import EntityResolver, MergeDecision
from ..provenance.freshness import FreshnessPolicy, apply_freshness, policy_for
from ..provenance.lineage import DataLineage, ProvenanceError, require_provenance
from ..sources.base import SourceRecord, SpaceDataSource
from ..sources.errors import SourceError
from .report import (
    ConflictNote,
    IngestionReport,
    RejectionReason,
    SourceReport,
    SourceStatus,
)

__all__ = ["SourcePlan", "RecordStore", "IngestionPipeline"]

logger = logging.getLogger("data.ingestion")


class RecordStore:
    """In-memory canonical record store.

    Deliberately minimal and swappable. P2 owns the database; until their ORM
    exists, P4 persists here and the pipeline talks to this interface rather
    than to a schema it does not own.
    """

    def __init__(self):
        self._records: Dict[str, Any] = {}
        self._lineage: Dict[str, DataLineage] = {}

    def get(self, canonical_id: str):
        return self._records.get(canonical_id)

    def put(self, record, lineage: Optional[DataLineage] = None) -> bool:
        """Store a record. Returns True when it is new, False when replaced."""
        is_new = record.canonical_id not in self._records
        self._records[record.canonical_id] = record
        if lineage is not None:
            self._lineage[record.canonical_id] = lineage
        return is_new

    def lineage_for(self, canonical_id: str) -> Optional[DataLineage]:
        return self._lineage.get(canonical_id)

    def all(self) -> List[Any]:
        return list(self._records.values())

    def __len__(self) -> int:
        return len(self._records)

    def __contains__(self, canonical_id: str) -> bool:
        return canonical_id in self._records


class SourcePlan(BaseModel):
    """How to run one source through the pipeline."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    source_name: str
    #: Returns the source's raw records. Any exception marks this source failed.
    fetch: Callable[[SpaceDataSource], Awaitable[Sequence[SourceRecord]]]
    #: `SourceRecord -> (record | [records], DataLineage)`. Per-record failures
    #: reject that record only.
    normalize: Callable[[SourceRecord], Any]
    #: Overrides the registered policy. Rarely needed.
    freshness_policy: Optional[FreshnessPolicy] = None
    #: Set False to keep a source registered but not run it.
    enabled: bool = True
    #: Why the source is disabled, shown in the report.
    skip_reason: Optional[str] = None


class IngestionPipeline:
    """Runs many sources into one canonical store, isolating their failures."""

    def __init__(
        self,
        store: Optional[RecordStore] = None,
        resolver: Optional[EntityResolver] = None,
        now: Optional[Any] = None,
    ):
        self.store = store or RecordStore()
        self.resolver = resolver or EntityResolver()
        #: Injectable clock, so freshness assertions are deterministic in tests.
        self._now = now

    async def run(
        self,
        plans: Iterable[SourcePlan],
        sources: Dict[str, SpaceDataSource],
        run_id: Optional[str] = None,
        concurrent: bool = True,
    ) -> IngestionReport:
        """Run every plan and return one report covering all of them."""
        report = IngestionReport(
            run_id=run_id or "run-{0}".format(utc_now().strftime("%Y%m%dT%H%M%S"))
        )
        plans = list(plans)

        if concurrent:
            #: `return_exceptions=True` is what stops one source's failure from
            #: cancelling the others. Each branch also guards itself, so this is
            #: belt and braces rather than the only protection.
            await asyncio.gather(
                *[self._run_plan(plan, sources, report) for plan in plans],
                return_exceptions=True,
            )
        else:
            for plan in plans:
                await self._run_plan(plan, sources, report)

        return report.finish()

    async def _run_plan(
        self,
        plan: SourcePlan,
        sources: Dict[str, SpaceDataSource],
        report: IngestionReport,
    ) -> None:
        """Run one source. Never raises: failures are recorded, not propagated."""
        source_report = report.source(plan.source_name)
        started = utc_now()

        if not plan.enabled:
            source_report.status = SourceStatus.SKIPPED
            if plan.skip_reason:
                source_report.errors.append(plan.skip_reason)
            return

        source = sources.get(plan.source_name)
        if source is None:
            source_report.status = SourceStatus.SKIPPED
            source_report.errors.append(
                "no adapter supplied for {0}".format(plan.source_name)
            )
            return

        try:
            raw_records = await plan.fetch(source)
        except SourceError as exc:
            source_report.fail("{0}: {1}".format(exc.__class__.__name__, exc))
            logger.warning("source %s failed: %s", plan.source_name, exc)
            return
        except Exception as exc:  # noqa: BLE001 - one source must not fail the run
            source_report.fail(
                "unexpected {0}: {1}".format(exc.__class__.__name__, exc)
            )
            logger.exception("source %s raised unexpectedly", plan.source_name)
            return

        policy = plan.freshness_policy or policy_for(plan.source_name)

        for raw in raw_records or []:
            source_report.records_seen += 1
            if source_report.retrieved_at is None:
                source_report.retrieved_at = raw.retrieved_at
            if raw.source_reference.source_timestamp is not None:
                source_report.source_timestamp = raw.source_reference.source_timestamp
            self._process_record(raw, plan, policy, source_report)

        if source_report.rejected and source_report.status is SourceStatus.OK:
            source_report.status = SourceStatus.PARTIAL
        source_report.duration_seconds = (utc_now() - started).total_seconds()

    def _process_record(
        self,
        raw: SourceRecord,
        plan: SourcePlan,
        policy: FreshnessPolicy,
        source_report: SourceReport,
    ) -> None:
        """Normalize, validate, resolve and store one record.

        A failure here rejects this record only; the source keeps going.
        """
        try:
            normalized = plan.normalize(raw)
        except Exception as exc:  # noqa: BLE001 - one record must not stop a source
            source_report.reject(
                RejectionReason.NORMALIZATION_ERROR,
                "{0}: {1}".format(exc.__class__.__name__, exc),
                source_record_id=raw.source_record_id,
                payload_excerpt=str(raw.payload)[:200],
            )
            return

        for record, lineage in _iter_normalized(normalized):
            self._store_record(record, lineage, raw, policy, source_report)

    def _store_record(self, record, lineage, raw, policy, source_report) -> None:
        # -- provenance ---------------------------------------------------
        try:
            require_provenance(record, lineage)
        except ProvenanceError as exc:
            source_report.reject(
                RejectionReason.MISSING_PROVENANCE,
                str(exc),
                source_record_id=raw.source_record_id,
            )
            return

        # -- freshness ----------------------------------------------------
        assessment = apply_freshness(record, policy, now=self._now)
        source_report.record_freshness(record.freshness_class)
        if assessment.is_stale:
            source_report.stale_records += 1

        # -- entity resolution --------------------------------------------
        outcome = self.resolver.resolve(
            record,
            source_name=raw.source_name,
            source_record_id=raw.source_record_id,
        )

        if outcome.decision is MergeDecision.CONFLICT:
            source_report.conflicts.append(
                ConflictNote(
                    canonical_id=record.canonical_id,
                    sources=[raw.source_name],
                    detail=outcome.reason,
                )
            )
            source_report.reject(
                RejectionReason.ENTITY_CONFLICT,
                outcome.reason,
                source_record_id=raw.source_record_id,
            )
            return

        if outcome.decision is MergeDecision.CANDIDATE:
            #: A name-only match is recorded but does not block the record: it
            #: is stored under its own id, and a human decides later.
            source_report.conflicts.append(
                ConflictNote(
                    canonical_id=record.canonical_id,
                    sources=[raw.source_name] + outcome.conflicting_ids,
                    detail=outcome.reason,
                )
            )

        if outcome.decision is MergeDecision.MERGED:
            existing = self.store.get(outcome.merged_into)
            if existing is not None and existing.canonical_id != record.canonical_id:
                #: The incoming record describes an entity already known under a
                #: different canonical id. Keep the established id so links from
                #: other records stay valid.
                record = record.model_copy(
                    update={"canonical_id": outcome.merged_into}
                )

        # -- store --------------------------------------------------------
        try:
            is_new = self.store.put(record, lineage)
        except Exception as exc:  # noqa: BLE001 - storage must not kill the run
            source_report.reject(
                RejectionReason.VALIDATION_ERROR,
                "store rejected the record: {0}".format(exc),
                source_record_id=raw.source_record_id,
            )
            return

        self.resolver.register(
            record,
            outcome,
            source_name=raw.source_name,
            source_record_id=raw.source_record_id,
        )

        if is_new:
            source_report.created += 1
        else:
            source_report.updated += 1


def _iter_normalized(result):
    """Yield `(record, lineage)` pairs from whatever a normalizer returned.

    Normalizers return one record, a list of records, or a record plus an
    optional companion (the exoplanet normalizer returns a planet and its host
    star). Normalizing that shape here keeps the pipeline uniform.
    """
    if result is None:
        return

    if isinstance(result, tuple):
        *records, lineage = result
        if not isinstance(lineage, DataLineage):
            #: No lineage in the tuple — treat every element as a record.
            records = list(result)
            lineage = None
        for record in records:
            if record is None:
                continue
            if isinstance(record, (list, tuple)):
                for item in record:
                    if item is not None:
                        yield (item, lineage)
            else:
                yield (record, lineage)
        return

    if isinstance(result, list):
        for record in result:
            yield (record, None)
        return

    yield (result, None)
