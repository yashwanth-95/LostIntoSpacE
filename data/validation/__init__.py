"""Scientific data validation and cross-source quality checking.

Two tiers:

* **Structural** validation is the models' own job — pydantic rejects a mass in
  metres or an orbit without a frame at construction time.
* **Scientific** validation lives here: plausible ranges, impossible dates,
  duplicate identifiers, inconsistent typing and naming, staleness, and
  conflicts between archives describing the same thing.

Authority is configurable per field (`AuthorityPolicy`). There is no single
source that wins for every kind of data.
"""

from .authority import DEFAULT_AUTHORITY, FIELD_AUTHORITY, AuthorityPolicy
from .engine import DataQualityEngine
from .issues import (
    DataQualityReport,
    IssueCode,
    QualityIssue,
    RecommendedAction,
    Severity,
    ValueConflict,
)
from .ranges import OBJECT_TYPE_RANGES, SI_RANGES, RangeRule, range_for

__all__ = [
    "DataQualityEngine",
    "DataQualityReport",
    "QualityIssue",
    "ValueConflict",
    "IssueCode",
    "Severity",
    "RecommendedAction",
    "AuthorityPolicy",
    "FIELD_AUTHORITY",
    "DEFAULT_AUTHORITY",
    "RangeRule",
    "SI_RANGES",
    "OBJECT_TYPE_RANGES",
    "range_for",
]
