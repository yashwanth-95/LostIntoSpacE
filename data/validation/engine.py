"""The scientific data-quality engine.

Two kinds of check:

* **Per-record** — units, ranges, dates, provenance, freshness, internal
  consistency. Everything answerable from one record alone.
* **Cross-source** — duplicate identifiers, inconsistent object types and
  naming, and conflicting values between archives describing the same thing.

Conflict resolution uses the configurable `AuthorityPolicy`, per field. Two
values that differ by less than their combined published uncertainties are
recorded as agreement-within-uncertainty, not as a conflict: archives quote
different precisions for the same measurement, and calling that a disagreement
would bury the real ones.
"""

import math
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from pydantic import BaseModel

from contracts._time import utc_now

from ..models.orbit import FrameContext, OrbitRecord
from ..models.units import Quantity, UnitError
from ..provenance.freshness import assess_freshness, policy_for
from .authority import AuthorityPolicy
from .issues import (
    DataQualityReport,
    IssueCode,
    QualityIssue,
    RecommendedAction,
    Severity,
    ValueConflict,
)
from .ranges import range_for

__all__ = ["DataQualityEngine", "QUALITY_WEIGHTS"]

#: How much each severity costs the confidence score.
QUALITY_WEIGHTS = {
    Severity.ERROR: 0.35,
    Severity.WARNING: 0.10,
    Severity.INFO: 0.0,
}

#: Earliest plausible date for any record in this domain. Ceres was discovered
#: on 1801-01-01, and the MPC holds observations from that year.
_EARLIEST_PLAUSIBLE = datetime(1700, 1, 1)

#: How far into the future a timestamp may sit before it is impossible.
#: Ephemerides are legitimately predictive, so this is generous.
_FUTURE_TOLERANCE = timedelta(days=365 * 200)


class DataQualityEngine:
    """Checks canonical records, alone and against each other."""

    def __init__(
        self,
        authority: Optional[AuthorityPolicy] = None,
        now: Optional[datetime] = None,
    ):
        self.authority = authority or AuthorityPolicy()
        self._now = now

    # ------------------------------------------------------------------
    # Per-record checks
    # ------------------------------------------------------------------
    def check_record(self, record) -> DataQualityReport:
        """Every check that needs only this record."""
        report = DataQualityReport(canonical_id=record.canonical_id, records_checked=1)
        object_type = getattr(record, "object_type", None)
        type_value = object_type.value if object_type is not None else None

        self._check_provenance(record, report)
        self._check_quantities(record, report, type_value)
        self._check_dates(record, report)
        self._check_internal_consistency(record, report)
        self._check_freshness(record, report)

        self._finalize(report)
        return report

    def _check_provenance(self, record, report) -> None:
        if not getattr(record, "source_references", None):
            report.add(
                QualityIssue(
                    code=IssueCode.MISSING_PROVENANCE,
                    severity=Severity.ERROR,
                    message="record has no source references and cannot be cited",
                    canonical_id=record.canonical_id,
                )
            )
            return

        unknown = [
            reference.source_name
            for reference in record.source_references
            if reference.source_type.value == "UNKNOWN"
        ]
        if unknown:
            report.add(
                QualityIssue(
                    code=IssueCode.MISSING_PROVENANCE,
                    severity=Severity.WARNING,
                    message="source(s) {0} have an unknown authority class".format(
                        ", ".join(unknown)
                    ),
                    canonical_id=record.canonical_id,
                    sources=unknown,
                )
            )

    def _check_quantities(self, record, report, object_type) -> None:
        """Range and unit checks over every `Quantity` on the record."""
        for field, quantity in _walk_quantities(record):
            try:
                si_value = quantity.si_value()
            except UnitError as exc:
                report.add(
                    QualityIssue(
                        code=IssueCode.UNIT_DIMENSION_MISMATCH,
                        severity=Severity.ERROR,
                        message=str(exc),
                        canonical_id=record.canonical_id,
                        field=field,
                    )
                )
                continue

            if math.isnan(si_value) or math.isinf(si_value):
                report.add(
                    QualityIssue(
                        code=IssueCode.VALUE_OUT_OF_RANGE,
                        severity=Severity.ERROR,
                        message="value is not finite",
                        canonical_id=record.canonical_id,
                        field=field,
                    )
                )
                continue

            rule = range_for(field, object_type)
            if rule is None:
                continue
            verdict = rule.classify(si_value)
            if verdict is None:
                continue

            severity = Severity.ERROR if verdict == "error" else Severity.WARNING
            #: A value out by a clean power of 1000 is almost always a unit slip
            #: rather than a wrong measurement, and saying so makes it fixable.
            code = IssueCode.VALUE_OUT_OF_RANGE
            hint = ""
            scale = _suspect_scale(si_value, rule)
            if scale is not None:
                code = IssueCode.SUSPECT_UNIT_SCALE
                hint = " (out by a factor of about {0:g} — check the unit)".format(scale)

            report.add(
                QualityIssue(
                    code=code,
                    severity=severity,
                    message="{0} = {1:g} {2} ({3:g} SI) is outside the plausible "
                    "range: {4}{5}".format(
                        field, quantity.value, quantity.unit, si_value,
                        rule.describe(), hint,
                    ),
                    canonical_id=record.canonical_id,
                    field=field,
                    detail={"si_value": si_value, "unit": quantity.unit},
                )
            )

    def _check_dates(self, record, report) -> None:
        horizon = (self._now or utc_now()) + _FUTURE_TOLERANCE
        for field, moment in _walk_datetimes(record):
            naive = moment.replace(tzinfo=None)
            if naive < _EARLIEST_PLAUSIBLE:
                report.add(
                    QualityIssue(
                        code=IssueCode.IMPOSSIBLE_DATE,
                        severity=Severity.ERROR,
                        message="{0} = {1} predates any plausible record".format(
                            field, moment.isoformat()
                        ),
                        canonical_id=record.canonical_id,
                        field=field,
                    )
                )
            elif moment > horizon:
                report.add(
                    QualityIssue(
                        code=IssueCode.IMPOSSIBLE_DATE,
                        severity=Severity.ERROR,
                        message="{0} = {1} is implausibly far in the future".format(
                            field, moment.isoformat()
                        ),
                        canonical_id=record.canonical_id,
                        field=field,
                    )
                )

        retrieved = getattr(record, "retrieved_at", None)
        if retrieved is not None and retrieved > (self._now or utc_now()) + timedelta(
            minutes=5
        ):
            report.add(
                QualityIssue(
                    code=IssueCode.IMPOSSIBLE_DATE,
                    severity=Severity.WARNING,
                    message="retrieved_at is in the future; check the system clock",
                    canonical_id=record.canonical_id,
                    field="retrieved_at",
                )
            )

    def _check_internal_consistency(self, record, report) -> None:
        """Cross-field checks the models cannot express on their own."""
        physical = getattr(record, "physical", None)
        if physical is not None:
            self._check_density_consistency(record, physical, report)

        #: An `OrbitRecord` is a canonical record in its own right and is
        #: checked directly; other records carry theirs in `orbits`.
        if isinstance(record, OrbitRecord):
            self._check_orbit(record, record, None, report)
        for index, orbit in enumerate(getattr(record, "orbits", []) or []):
            self._check_orbit(record, orbit, index, report)

    def _check_density_consistency(self, record, physical, report) -> None:
        """Density implied by mass and radius, against the published density.

        A mismatch means one of the three is wrong — usually a unit. This is the
        single most informative consistency check available for a body.
        """
        mass = physical.mass
        radius = physical.effective_radius()
        density = physical.density
        if not (mass and radius and density):
            return
        radius_m = radius.si_value()
        if radius_m <= 0:
            return
        volume = (4.0 / 3.0) * math.pi * radius_m ** 3
        implied = mass.si_value() / volume
        published = density.si_value()
        if published <= 0:
            return
        ratio = implied / published
        if 0.5 <= ratio <= 2.0:
            return
        report.add(
            QualityIssue(
                code=IssueCode.INCONSISTENT_DERIVED_VALUE,
                severity=Severity.WARNING if 0.2 <= ratio <= 5.0 else Severity.ERROR,
                message=(
                    "density implied by mass and radius ({0:.3g} kg/m3) disagrees "
                    "with the published density ({1:.3g} kg/m3) by a factor of "
                    "{2:.3g}".format(implied, published, ratio)
                ),
                canonical_id=record.canonical_id,
                field="physical.density",
                detail={"implied": implied, "published": published, "ratio": ratio},
            )
        )

    def _check_orbit(self, record, orbit, index, report) -> None:
        #: `index` is None when the orbit *is* the record being checked.
        prefix = "orbit" if index is None else "orbits[{0}]".format(index)
        elements = orbit.elements

        if orbit.frame.origin_type.value == "UNKNOWN":
            report.add(
                QualityIssue(
                    code=IssueCode.MISSING_REQUIRED_FIELD,
                    severity=Severity.WARNING,
                    message="orbit has an UNKNOWN origin type; its elements cannot "
                    "be compared with any other solution",
                    canonical_id=record.canonical_id,
                    field="{0}.frame.origin_type".format(prefix),
                )
            )

        if orbit.element_theory.value == "UNKNOWN":
            report.add(
                QualityIssue(
                    code=IssueCode.MISSING_REQUIRED_FIELD,
                    severity=Severity.WARNING,
                    message="orbit does not state which dynamical theory its "
                    "elements belong to",
                    canonical_id=record.canonical_id,
                    field="{0}.element_theory".format(prefix),
                )
            )

        #: An unbound orbit for a catalogued body is usually a parse error, but
        #: is genuinely possible for interstellar objects, so it warns.
        if elements.eccentricity is not None:
            eccentricity = elements.eccentricity.to("1").value
            if eccentricity >= 1.0:
                report.add(
                    QualityIssue(
                        code=IssueCode.VALUE_OUT_OF_RANGE,
                        severity=Severity.WARNING,
                        message="eccentricity {0:g} describes an unbound orbit".format(
                            eccentricity
                        ),
                        canonical_id=record.canonical_id,
                        field="{0}.elements.eccentricity".format(prefix),
                    )
                )

        #: Uncertainty is what makes an element set scientifically usable.
        if elements.semi_major_axis is not None and not (
            elements.semi_major_axis.has_uncertainty
        ):
            report.add(
                QualityIssue(
                    code=IssueCode.MISSING_UNCERTAINTY,
                    severity=Severity.INFO,
                    message="semi-major axis has no published uncertainty",
                    canonical_id=record.canonical_id,
                    field="{0}.elements.semi_major_axis".format(prefix),
                )
            )

    def _check_freshness(self, record, report) -> None:
        source = record.primary_source
        if source is None:
            return
        policy = policy_for(source.source_name)
        assessment = assess_freshness(
            policy=policy,
            retrieved_at=getattr(record, "retrieved_at", None),
            valid_at=record.temporal_anchor(),
            now=self._now,
        )
        if assessment.is_stale:
            report.stale_records.append(record.canonical_id)
            report.add(
                QualityIssue(
                    code=IssueCode.STALE_RECORD,
                    severity=Severity.WARNING,
                    message="content is stale for a {0} source: {1}".format(
                        policy.source_category.value, assessment.reason
                    ),
                    canonical_id=record.canonical_id,
                    sources=[source.source_name],
                    detail={
                        "freshness_class": assessment.freshness_class.value,
                        "may_present_as_live": assessment.may_present_as_live,
                    },
                )
            )
        if record.temporal_anchor() is None and policy.max_age is not None:
            report.add(
                QualityIssue(
                    code=IssueCode.NO_TEMPORAL_ANCHOR,
                    severity=Severity.WARNING,
                    message="record has no epoch, so its currency cannot be "
                    "established",
                    canonical_id=record.canonical_id,
                )
            )

    # ------------------------------------------------------------------
    # Cross-record checks
    # ------------------------------------------------------------------
    def check_dataset(self, records: Sequence[Any]) -> DataQualityReport:
        """Per-record checks plus identity and naming checks across the set."""
        report = DataQualityReport()
        for record in records:
            report.extend(self.check_record(record))

        self._check_duplicate_identifiers(records, report)
        self._check_type_and_name_consistency(records, report)

        self._finalize(report)
        return report

    def _check_duplicate_identifiers(self, records, report) -> None:
        seen_ids: Dict[str, List[str]] = {}
        strong: Dict[Tuple[str, str], List[str]] = {}

        for record in records:
            seen_ids.setdefault(record.canonical_id, []).append(
                record.primary_source.source_name if record.primary_source else "?"
            )
            for field in ("spk_id", "norad_cat_id", "product_id"):
                value = getattr(record, field, None)
                if value not in (None, ""):
                    strong.setdefault((field, str(value)), []).append(
                        record.canonical_id
                    )

        for canonical_id, sources in seen_ids.items():
            if len(sources) > 1:
                report.add(
                    QualityIssue(
                        code=IssueCode.DUPLICATE_IDENTIFIER,
                        severity=Severity.ERROR,
                        message="canonical id appears {0} times in the dataset".format(
                            len(sources)
                        ),
                        canonical_id=canonical_id,
                        sources=sorted(set(sources)),
                    )
                )

        for (field, value), canonical_ids in strong.items():
            distinct = sorted(set(canonical_ids))
            if len(distinct) > 1:
                report.add(
                    QualityIssue(
                        code=IssueCode.DUPLICATE_IDENTIFIER,
                        severity=Severity.ERROR,
                        message="{0}={1} is claimed by {2} different entities: "
                        "{3}".format(field, value, len(distinct), distinct),
                        field=field,
                        detail={"identifier": value, "canonical_ids": distinct},
                    )
                )

    def _check_type_and_name_consistency(self, records, report) -> None:
        by_id: Dict[str, List[Any]] = {}
        for record in records:
            by_id.setdefault(record.canonical_id, []).append(record)

        for canonical_id, group in by_id.items():
            types = {
                getattr(record, "object_type", None) for record in group
            }
            types.discard(None)
            if len(types) > 1:
                report.add(
                    QualityIssue(
                        code=IssueCode.INCONSISTENT_OBJECT_TYPE,
                        severity=Severity.ERROR,
                        message="the same entity is typed as {0}".format(
                            sorted(item.value for item in types)
                        ),
                        canonical_id=canonical_id,
                    )
                )

            names = {
                getattr(record, "name", None)
                for record in group
                if getattr(record, "name", None)
            }
            if len(names) > 1:
                normalized = {name.strip().lower() for name in names}
                if len(normalized) > 1:
                    report.add(
                        QualityIssue(
                            code=IssueCode.INCONSISTENT_NAMING,
                            severity=Severity.WARNING,
                            message="the same entity is named {0}".format(
                                sorted(names)
                            ),
                            canonical_id=canonical_id,
                            detail={"names": sorted(names)},
                        )
                    )

    # ------------------------------------------------------------------
    # Conflict detection between sources
    # ------------------------------------------------------------------
    def compare_records(self, first, second) -> DataQualityReport:
        """Compare two records describing the same entity, field by field."""
        report = DataQualityReport(canonical_id=first.canonical_id, records_checked=2)

        first_source = _source_name(first)
        second_source = _source_name(second)

        first_values = dict(_walk_quantities(first))
        second_values = dict(_walk_quantities(second))

        for field in sorted(set(first_values) & set(second_values)):
            conflict = self._compare_quantity(
                first.canonical_id,
                field,
                first_values[field],
                second_values[field],
                first_source,
                second_source,
            )
            if conflict is None:
                continue
            report.conflicts.append(conflict)
            if conflict.within_uncertainty:
                report.add(
                    QualityIssue(
                        code=IssueCode.DISAGREEMENT_WITHIN_UNCERTAINTY,
                        severity=Severity.INFO,
                        message="{0}: {1} and {2} differ by {3:.3g} relative, within "
                        "their published uncertainties".format(
                            field, first_source, second_source,
                            conflict.relative_difference or 0.0,
                        ),
                        canonical_id=first.canonical_id,
                        field=field,
                        sources=[first_source, second_source],
                    )
                )
            else:
                report.add(
                    QualityIssue(
                        code=IssueCode.CONFLICTING_VALUE,
                        severity=Severity.WARNING,
                        message="{0}: {1} and {2} disagree by {3:.3g} relative; "
                        "{4}".format(
                            field, first_source, second_source,
                            conflict.relative_difference or 0.0, conflict.reason,
                        ),
                        canonical_id=first.canonical_id,
                        field=field,
                        sources=[first_source, second_source],
                    )
                )

        self._check_frame_compatibility(first, second, report)
        self._finalize(report)
        return report

    def _compare_quantity(
        self, canonical_id, field, first, second, first_source, second_source
    ) -> Optional[ValueConflict]:
        if first.dimension is not second.dimension:
            return ValueConflict(
                canonical_id=canonical_id,
                field=field,
                values={first_source: first.value, second_source: second.value},
                units={first_source: first.unit, second_source: second.unit},
                preferred_source=self.authority.preferred(
                    [first_source, second_source], field
                ),
                reason="the two sources publish different dimensions for this field",
            )

        a = first.si_value()
        b = second.si_value()
        scale = max(abs(a), abs(b))
        if scale == 0.0:
            return None
        difference = abs(a - b)
        relative = difference / scale
        if relative < 1e-9:
            return None

        tolerance = _combined_uncertainty(first, second)
        within = tolerance is not None and difference <= tolerance

        preferred_source = self.authority.preferred([first_source, second_source], field)
        preferred_value = a if preferred_source == first_source else b

        return ValueConflict(
            canonical_id=canonical_id,
            field=field,
            values={first_source: a, second_source: b},
            units={first_source: first.unit, second_source: second.unit},
            relative_difference=relative,
            within_uncertainty=within,
            preferred_source=preferred_source,
            preferred_value=preferred_value,
            reason=self.authority.explain([first_source, second_source], field),
        )

    def _check_frame_compatibility(self, first, second, report) -> None:
        """Refuse to treat orbits in different frames as comparable."""
        first_orbits = getattr(first, "orbits", None) or []
        second_orbits = getattr(second, "orbits", None) or []
        if not (first_orbits and second_orbits):
            return
        a, b = first_orbits[0], second_orbits[0]

        if not a.frame.is_comparable_to(b.frame):
            report.add(
                QualityIssue(
                    code=IssueCode.INCOMPARABLE_FRAMES,
                    severity=Severity.WARNING,
                    message=(
                        "orbits are in different frames and must not be compared "
                        "numerically: {0!r} vs {1!r}".format(
                            a.frame.describe(), b.frame.describe()
                        )
                    ),
                    canonical_id=first.canonical_id,
                    field="orbits[0].frame",
                    sources=[_source_name(first), _source_name(second)],
                )
            )

        if a.element_theory is not b.element_theory:
            report.add(
                QualityIssue(
                    code=IssueCode.INCOMPATIBLE_ELEMENT_THEORY,
                    severity=Severity.ERROR,
                    message=(
                        "element sets belong to different dynamical theories "
                        "({0} vs {1}); they share field names but are not "
                        "interchangeable".format(
                            a.element_theory.value, b.element_theory.value
                        )
                    ),
                    canonical_id=first.canonical_id,
                    field="orbits[0].element_theory",
                    sources=[_source_name(first), _source_name(second)],
                )
            )

    # ------------------------------------------------------------------
    def _finalize(self, report: DataQualityReport) -> None:
        """Score confidence and choose a recommended action."""
        confidence = 1.0
        for issue in report.issues:
            confidence -= QUALITY_WEIGHTS.get(issue.severity, 0.0)
        #: Unresolved conflicts reduce confidence even when each value is
        #: individually plausible — that is what a conflict means.
        confidence -= 0.15 * len(
            [item for item in report.conflicts if not item.within_uncertainty]
        )
        report.confidence = max(0.0, min(1.0, confidence))

        errors = report.errors
        blocking = [
            issue
            for issue in errors
            if issue.code
            in (
                IssueCode.MISSING_PROVENANCE,
                IssueCode.DUPLICATE_IDENTIFIER,
                IssueCode.INCONSISTENT_OBJECT_TYPE,
                IssueCode.INCOMPATIBLE_ELEMENT_THEORY,
            )
        ]

        if blocking:
            report.recommended_action = RecommendedAction.REVIEW
        elif errors:
            report.recommended_action = RecommendedAction.REJECT
        elif any(not item.within_uncertainty for item in report.conflicts):
            report.recommended_action = RecommendedAction.REVIEW
        elif report.stale_records:
            report.recommended_action = RecommendedAction.REFRESH
        elif report.warnings:
            report.recommended_action = RecommendedAction.ACCEPT_WITH_CAVEAT
        else:
            report.recommended_action = RecommendedAction.ACCEPT


# ----------------------------------------------------------------------
# Traversal helpers
# ----------------------------------------------------------------------
def _source_name(record) -> str:
    source = getattr(record, "primary_source", None)
    return source.source_name if source is not None else "unknown"


def _combined_uncertainty(first: Quantity, second: Quantity) -> Optional[float]:
    """Combined 1-sigma tolerance in SI, or `None` when neither publishes one."""
    def widest(quantity: Quantity) -> Optional[float]:
        candidates = [
            quantity.uncertainty,
            quantity.uncertainty_lower,
            quantity.uncertainty_upper,
        ]
        present = [value for value in candidates if value is not None]
        if not present:
            return None
        widest_value = max(present)
        #: Convert the uncertainty to SI by scaling with the value's own factor.
        if quantity.value == 0:
            return widest_value
        return abs(quantity.si_value() / quantity.value) * widest_value

    a = widest(first)
    b = widest(second)
    if a is None and b is None:
        return None
    #: Sum in quadrature, then allow 3 sigma before calling it a conflict.
    total = math.sqrt((a or 0.0) ** 2 + (b or 0.0) ** 2)
    return 3.0 * total


def _suspect_scale(value: float, rule) -> Optional[float]:
    """Detect an out-of-range value that is a clean power of 1000 off."""
    if value == 0:
        return None
    for bound in (rule.error_min, rule.error_max):
        if bound in (None, 0):
            continue
        ratio = abs(value / bound)
        for factor in (1e3, 1e6, 1e9, 1e-3, 1e-6, 1e-9):
            if abs(math.log10(ratio) - math.log10(abs(factor))) < 0.35:
                return factor
    return None


def _walk_quantities(model, prefix: str = "") -> Iterable[Tuple[str, Quantity]]:
    """Yield `(field_path, Quantity)` for every quantity on a record."""
    fields = getattr(type(model), "model_fields", None)
    if not fields:
        return
    for name in fields:
        value = getattr(model, name, None)
        path = "{0}.{1}".format(prefix, name) if prefix else name
        if isinstance(value, Quantity):
            yield (path, value)
        elif isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, Quantity):
                    yield ("{0}.{1}".format(path, key), item)
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                if isinstance(item, Quantity):
                    yield ("{0}[{1}]".format(path, index), item)
                elif isinstance(item, BaseModel):
                    #: Index-free path so range rules match regardless of which
                    #: orbit in the list a quantity came from.
                    for nested in _walk_quantities(item, path):
                        yield nested
        elif isinstance(value, BaseModel):
            for nested in _walk_quantities(value, path):
                yield nested


def _walk_datetimes(model, prefix: str = "") -> Iterable[Tuple[str, datetime]]:
    """Yield `(field_path, datetime)` for every timestamp on a record."""
    fields = getattr(type(model), "model_fields", None)
    if not fields:
        return
    for name in fields:
        value = getattr(model, name, None)
        path = "{0}.{1}".format(prefix, name) if prefix else name
        if isinstance(value, datetime):
            yield (path, value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, BaseModel):
                    for nested in _walk_datetimes(item, path):
                        yield nested
        elif isinstance(value, BaseModel):
            for nested in _walk_datetimes(value, path):
                yield nested
