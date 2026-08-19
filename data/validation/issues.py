"""Quality issues and the report they roll up into.

An issue is a *finding about a record*, not an exception. The engine's job is to
describe what is wrong and how confident we are, then recommend an action —
never to silently discard data or silently accept it.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from contracts._time import utc_now

__all__ = [
    "Severity",
    "IssueCode",
    "RecommendedAction",
    "QualityIssue",
    "ValueConflict",
    "DataQualityReport",
]


class Severity(str, Enum):
    """How bad a finding is.

    `ERROR` means the record should not be served as-is. `WARNING` means serve
    it but say something. `INFO` is context for a human reviewing the data.
    """

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class IssueCode(str, Enum):
    """What kind of problem was found. One code per check."""

    # -- structural ------------------------------------------------------
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    #: A value whose unit is not the dimension its field requires.
    UNIT_DIMENSION_MISMATCH = "UNIT_DIMENSION_MISMATCH"
    #: A value in a valid unit but an implausible magnitude for that unit —
    #: usually a metre/kilometre or gram/kilogram slip upstream.
    SUSPECT_UNIT_SCALE = "SUSPECT_UNIT_SCALE"

    # -- scientific ------------------------------------------------------
    VALUE_OUT_OF_RANGE = "VALUE_OUT_OF_RANGE"
    IMPOSSIBLE_DATE = "IMPOSSIBLE_DATE"
    INCONSISTENT_DERIVED_VALUE = "INCONSISTENT_DERIVED_VALUE"
    MISSING_UNCERTAINTY = "MISSING_UNCERTAINTY"

    # -- identity --------------------------------------------------------
    DUPLICATE_IDENTIFIER = "DUPLICATE_IDENTIFIER"
    INCONSISTENT_OBJECT_TYPE = "INCONSISTENT_OBJECT_TYPE"
    INCONSISTENT_NAMING = "INCONSISTENT_NAMING"

    # -- freshness -------------------------------------------------------
    STALE_RECORD = "STALE_RECORD"
    NO_TEMPORAL_ANCHOR = "NO_TEMPORAL_ANCHOR"

    # -- cross-source ----------------------------------------------------
    CONFLICTING_VALUE = "CONFLICTING_VALUE"
    #: Two sources disagree, but within their published uncertainties.
    DISAGREEMENT_WITHIN_UNCERTAINTY = "DISAGREEMENT_WITHIN_UNCERTAINTY"
    #: Values compared across incompatible reference frames.
    INCOMPARABLE_FRAMES = "INCOMPARABLE_FRAMES"
    #: Element sets from different dynamical theories compared or merged.
    INCOMPATIBLE_ELEMENT_THEORY = "INCOMPATIBLE_ELEMENT_THEORY"


class RecommendedAction(str, Enum):
    """What a caller should do with the record."""

    ACCEPT = "ACCEPT"
    #: Serve it, but show the caveat the report carries.
    ACCEPT_WITH_CAVEAT = "ACCEPT_WITH_CAVEAT"
    #: Re-fetch from the source before relying on it.
    REFRESH = "REFRESH"
    #: Needs a person to decide. Do not auto-merge or auto-discard.
    REVIEW = "REVIEW"
    #: Do not serve.
    REJECT = "REJECT"


class QualityIssue(BaseModel):
    """One finding about one record."""

    model_config = ConfigDict(extra="forbid")

    code: IssueCode
    severity: Severity
    message: str
    #: Canonical record the issue belongs to.
    canonical_id: Optional[str] = None
    #: Dotted path of the offending field, when there is one.
    field: Optional[str] = None
    #: Sources involved. More than one means a cross-source finding.
    sources: List[str] = Field(default_factory=list)
    #: Structured detail for a UI or a downstream rule.
    detail: Dict[str, Any] = Field(default_factory=dict)

    def __str__(self) -> str:
        location = " [{0}]".format(self.field) if self.field else ""
        return "{0} {1}{2}: {3}".format(
            self.severity.value, self.code.value, location, self.message
        )


class ValueConflict(BaseModel):
    """Two sources publishing different values for the same field."""

    model_config = ConfigDict(extra="forbid")

    canonical_id: str
    field: str
    #: source name -> value rendered in SI, for comparability.
    values: Dict[str, float] = Field(default_factory=dict)
    #: source name -> the unit each published.
    units: Dict[str, str] = Field(default_factory=dict)
    #: Relative difference between the extremes.
    relative_difference: Optional[float] = None
    #: True when the difference is covered by the published uncertainties.
    within_uncertainty: bool = False
    #: The source the authority policy prefers for this field.
    preferred_source: Optional[str] = None
    #: The value that should be served, in SI.
    preferred_value: Optional[float] = None
    reason: str = ""


class DataQualityReport(BaseModel):
    """Everything the engine found, for one record or a whole dataset."""

    model_config = ConfigDict(extra="forbid")

    #: Set when the report covers a single record.
    canonical_id: Optional[str] = None
    generated_at: datetime = Field(default_factory=utc_now)
    issues: List[QualityIssue] = Field(default_factory=list)
    conflicts: List[ValueConflict] = Field(default_factory=list)
    #: Canonical ids whose content is older than their source's policy allows.
    stale_records: List[str] = Field(default_factory=list)
    #: 0..1. Starts at 1.0 and is reduced by findings.
    confidence: float = 1.0
    recommended_action: RecommendedAction = RecommendedAction.ACCEPT
    #: Number of records examined, when the report covers a dataset.
    records_checked: int = 0

    # -- accessors ---------------------------------------------------------
    @property
    def errors(self) -> List[QualityIssue]:
        return [issue for issue in self.issues if issue.severity is Severity.ERROR]

    @property
    def warnings(self) -> List[QualityIssue]:
        return [issue for issue in self.issues if issue.severity is Severity.WARNING]

    @property
    def infos(self) -> List[QualityIssue]:
        return [issue for issue in self.issues if issue.severity is Severity.INFO]

    @property
    def is_acceptable(self) -> bool:
        return self.recommended_action in (
            RecommendedAction.ACCEPT,
            RecommendedAction.ACCEPT_WITH_CAVEAT,
        )

    def codes(self) -> List[str]:
        return sorted({issue.code.value for issue in self.issues})

    def has(self, code: IssueCode) -> bool:
        return any(issue.code is code for issue in self.issues)

    def issues_for(self, field: str) -> List[QualityIssue]:
        return [issue for issue in self.issues if issue.field == field]

    # -- building ----------------------------------------------------------
    def add(self, issue: QualityIssue) -> "DataQualityReport":
        self.issues.append(issue)
        return self

    def extend(self, report: "DataQualityReport") -> "DataQualityReport":
        """Fold another report into this one."""
        self.issues.extend(report.issues)
        self.conflicts.extend(report.conflicts)
        for canonical_id in report.stale_records:
            if canonical_id not in self.stale_records:
                self.stale_records.append(canonical_id)
        self.records_checked += report.records_checked
        return self

    def summary(self) -> str:
        return (
            "{0}: {1} error(s), {2} warning(s), {3} conflict(s), {4} stale; "
            "confidence {5:.2f}; action {6}".format(
                self.canonical_id or "dataset",
                len(self.errors),
                len(self.warnings),
                len(self.conflicts),
                len(self.stale_records),
                self.confidence,
                self.recommended_action.value,
            )
        )

    def describe(self) -> str:
        """Full human-readable rendering, for logs and review."""
        lines = [self.summary()]
        for issue in self.issues:
            lines.append("  " + str(issue))
        for conflict in self.conflicts:
            lines.append(
                "  CONFLICT [{0}]: {1} -> preferring {2} ({3})".format(
                    conflict.field,
                    conflict.values,
                    conflict.preferred_source,
                    conflict.reason,
                )
            )
        return "\n".join(lines)
