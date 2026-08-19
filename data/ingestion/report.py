"""Ingestion counters and reports.

A run that says only "done" is useless. Every run reports, per source: what it
saw, what it created, what it updated, what it rejected and why, what conflicted,
what was stale, and what errored — plus whether the source succeeded at all.

The distinction that matters: **a source failing is not the run failing.** The
report holds per-source outcomes so one provider's outage cannot be mistaken for
a global failure, or hide the other providers' results.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from contracts._time import utc_now
from contracts.provenance import FreshnessClass

__all__ = [
    "SourceStatus",
    "RejectionReason",
    "RejectedRecord",
    "ConflictNote",
    "SourceReport",
    "IngestionReport",
]


class SourceStatus(str, Enum):
    """How one source's branch of the run ended."""

    #: All records processed without a source-level failure.
    OK = "OK"
    #: Some records failed, but the source itself responded.
    PARTIAL = "PARTIAL"
    #: The source could not be reached or refused the request.
    FAILED = "FAILED"
    #: Deliberately not run — no credentials, or disabled by configuration.
    SKIPPED = "SKIPPED"


class RejectionReason(str, Enum):
    """Why a record did not reach the index."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    NORMALIZATION_ERROR = "NORMALIZATION_ERROR"
    ENTITY_CONFLICT = "ENTITY_CONFLICT"
    QUALITY_FAILURE = "QUALITY_FAILURE"
    DUPLICATE = "DUPLICATE"


class RejectedRecord(BaseModel):
    """One record that was refused, with enough detail to diagnose it.

    Rejection is recorded, never silent: a run that quietly drops records is
    indistinguishable from a source that has none.
    """

    model_config = ConfigDict(extra="forbid")

    source_name: str
    source_record_id: Optional[str] = None
    reason: RejectionReason
    detail: str
    #: Trimmed payload excerpt, for diagnosis without storing the whole record.
    payload_excerpt: Optional[str] = None


class ConflictNote(BaseModel):
    """Two sources disagreeing about the same entity or value."""

    model_config = ConfigDict(extra="forbid")

    canonical_id: str
    field: Optional[str] = None
    sources: List[str] = Field(default_factory=list)
    detail: str
    #: Set when the conflict was resolved rather than merely recorded.
    resolved_to: Optional[str] = None


class SourceReport(BaseModel):
    """Counters and outcomes for one source within a run."""

    model_config = ConfigDict(extra="forbid")

    source_name: str
    status: SourceStatus = SourceStatus.OK
    #: The source's own timestamp for the data, when it publishes one.
    source_timestamp: Optional[datetime] = None
    retrieved_at: Optional[datetime] = None

    records_seen: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: List[RejectedRecord] = Field(default_factory=list)
    conflicts: List[ConflictNote] = Field(default_factory=list)
    #: Records whose content is older than their source's freshness policy.
    stale_records: int = 0
    #: Freshness class histogram, so a run can show what it actually served.
    freshness_counts: Dict[str, int] = Field(default_factory=dict)
    #: Source-level errors: an outage, an auth failure, a malformed response.
    errors: List[str] = Field(default_factory=list)
    duration_seconds: Optional[float] = None

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)

    @property
    def succeeded(self) -> bool:
        return self.status in (SourceStatus.OK, SourceStatus.PARTIAL)

    def record_freshness(self, freshness_class: Optional[FreshnessClass]) -> None:
        if freshness_class is None:
            return
        key = freshness_class.value
        self.freshness_counts[key] = self.freshness_counts.get(key, 0) + 1

    def reject(self, reason: RejectionReason, detail: str,
               source_record_id: Optional[str] = None,
               payload_excerpt: Optional[str] = None) -> None:
        self.rejected.append(
            RejectedRecord(
                source_name=self.source_name,
                source_record_id=source_record_id,
                reason=reason,
                detail=detail,
                payload_excerpt=payload_excerpt,
            )
        )

    def fail(self, error: str) -> None:
        """Mark this source failed. Other sources are unaffected."""
        self.status = SourceStatus.FAILED
        self.errors.append(error)

    def summary(self) -> str:
        return (
            "{0}: {1} — seen {2}, created {3}, updated {4}, rejected {5}, "
            "conflicts {6}, stale {7}".format(
                self.source_name,
                self.status.value,
                self.records_seen,
                self.created,
                self.updated,
                self.rejected_count,
                len(self.conflicts),
                self.stale_records,
            )
        )


class IngestionReport(BaseModel):
    """The whole run: one `SourceReport` per source, plus totals."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: Optional[datetime] = None
    sources: Dict[str, SourceReport] = Field(default_factory=dict)

    def source(self, name: str) -> SourceReport:
        """Get or create the report for one source."""
        if name not in self.sources:
            self.sources[name] = SourceReport(source_name=name)
        return self.sources[name]

    # -- totals ------------------------------------------------------------
    def _total(self, attribute: str) -> int:
        return sum(getattr(report, attribute) for report in self.sources.values())

    @property
    def records_seen(self) -> int:
        return self._total("records_seen")

    @property
    def created(self) -> int:
        return self._total("created")

    @property
    def updated(self) -> int:
        return self._total("updated")

    @property
    def rejected(self) -> int:
        return sum(report.rejected_count for report in self.sources.values())

    @property
    def stale_records(self) -> int:
        return self._total("stale_records")

    @property
    def conflicts(self) -> List[ConflictNote]:
        notes: List[ConflictNote] = []
        for report in self.sources.values():
            notes.extend(report.conflicts)
        return notes

    @property
    def failed_sources(self) -> List[str]:
        return sorted(
            name
            for name, report in self.sources.items()
            if report.status is SourceStatus.FAILED
        )

    @property
    def succeeded_sources(self) -> List[str]:
        return sorted(
            name for name, report in self.sources.items() if report.succeeded
        )

    @property
    def all_failed(self) -> bool:
        """True only when every attempted source failed.

        A run with one failed provider out of five is a successful run with a
        recorded failure, not a failed run.
        """
        attempted = [
            report
            for report in self.sources.values()
            if report.status is not SourceStatus.SKIPPED
        ]
        return bool(attempted) and all(
            report.status is SourceStatus.FAILED for report in attempted
        )

    def finish(self) -> "IngestionReport":
        self.finished_at = utc_now()
        return self

    def summary(self) -> str:
        lines = [
            "Ingestion run {0}: {1} source(s), {2} record(s) seen, {3} created, "
            "{4} updated, {5} rejected, {6} conflict(s), {7} stale".format(
                self.run_id,
                len(self.sources),
                self.records_seen,
                self.created,
                self.updated,
                self.rejected,
                len(self.conflicts),
                self.stale_records,
            )
        ]
        for name in sorted(self.sources):
            lines.append("  " + self.sources[name].summary())
        if self.failed_sources:
            lines.append("  failed sources: {0}".format(", ".join(self.failed_sources)))
        return "\n".join(lines)
