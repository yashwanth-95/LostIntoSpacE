"""Data lineage.

Records the path every value took:

    source -> transformation -> normalized value -> derived value -> final record

This exists so that when a user asks "where did 3.72 m/s² come from?", the
answer is a chain of concrete steps ending at a `SourceReference`, not a
plausible-sounding guess. The AI layer cites lineage; it does not reconstruct it.

Lineage is metadata *about* a record, stored alongside it rather than inside it,
so a record stays small when the chain is long.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from contracts._time import as_utc, utc_now
from contracts.provenance import SourceReference, SourceType

__all__ = [
    "TransformationType",
    "LineageStep",
    "DataLineage",
    "LineageBuilder",
    "ProvenanceError",
    "require_provenance",
    "derive_quantity",
]


class ProvenanceError(ValueError):
    """Raised when a record reaches a stage that requires provenance without it."""


class TransformationType(str, Enum):
    """What kind of step was applied."""

    #: Bytes came back from an external API.
    FETCH = "FETCH"
    #: Raw payload turned into typed fields.
    PARSE = "PARSE"
    #: Value converted between units.
    UNIT_CONVERSION = "UNIT_CONVERSION"
    #: Source field name mapped onto a canonical field name.
    FIELD_MAPPING = "FIELD_MAPPING"
    #: Epoch converted between time scales or formats.
    EPOCH_CONVERSION = "EPOCH_CONVERSION"
    #: Frame/origin context attached to otherwise ambiguous numbers.
    FRAME_ANNOTATION = "FRAME_ANNOTATION"
    #: Name/designation canonicalized.
    NAME_NORMALIZATION = "NAME_NORMALIZATION"
    #: New value computed from other values. Output is never authoritative.
    DERIVATION = "DERIVATION"
    #: Two or more source records combined into one canonical record.
    MERGE = "MERGE"
    #: A conflict between sources resolved in favour of one of them.
    CONFLICT_RESOLUTION = "CONFLICT_RESOLUTION"
    #: Structural or scientific validation applied.
    VALIDATION = "VALIDATION"
    #: Credential or PII removed before storage.
    REDACTION = "REDACTION"
    #: Record written to its final canonical form.
    FINALIZATION = "FINALIZATION"


class LineageStep(BaseModel):
    """One transformation in a record's history."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int = Field(ge=0)
    transformation: TransformationType
    description: str = Field(min_length=1)
    #: Dotted module path that performed the step, e.g. "data.normalization.units".
    module: Optional[str] = None
    #: Canonical field paths consumed, e.g. ["physical.mass", "physical.radius_mean"].
    inputs: List[str] = Field(default_factory=list)
    #: Canonical field path produced, e.g. "physical.density".
    output: Optional[str] = None
    #: Small scalar snapshots. Deliberately not the whole payload — lineage is
    #: an audit trail, not a second copy of the data.
    input_value: Optional[Any] = None
    output_value: Optional[Any] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    #: The source this step drew from. Required on FETCH steps.
    source_reference: Optional[SourceReference] = None
    at: datetime = Field(default_factory=utc_now)

    @field_validator("at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return as_utc(value)

    def describe(self) -> str:
        parts = ["{0}. {1}".format(self.sequence, self.description)]
        if self.inputs:
            parts.append("from {0}".format(", ".join(self.inputs)))
        if self.output:
            parts.append("-> {0}".format(self.output))
        if self.source_reference is not None:
            parts.append("[{0}]".format(self.source_reference.source_name))
        return " ".join(parts)


class DataLineage(BaseModel):
    """The full transformation history of one canonical record."""

    model_config = ConfigDict(extra="forbid")

    #: `canonical_id` of the record this lineage belongs to.
    record_id: str
    steps: List[LineageStep] = Field(default_factory=list)

    # -- queries -----------------------------------------------------------
    def source_references(self) -> List[SourceReference]:
        """Every distinct source that contributed, in the order first seen."""
        found: List[SourceReference] = []
        for step in self.steps:
            ref = step.source_reference
            if ref is not None and ref not in found:
                found.append(ref)
        return found

    def origin_sources(self) -> List[SourceReference]:
        """Sources attached to FETCH steps — where the data actually entered."""
        return [
            step.source_reference
            for step in self.steps
            if step.transformation is TransformationType.FETCH
            and step.source_reference is not None
        ]

    def steps_for(self, field_path: str) -> List[LineageStep]:
        """Every step that read or wrote `field_path`."""
        return [
            step
            for step in self.steps
            if step.output == field_path or field_path in step.inputs
        ]

    def derived_fields(self) -> List[str]:
        """Field paths whose value this project computed rather than received."""
        return [
            step.output
            for step in self.steps
            if step.transformation is TransformationType.DERIVATION and step.output
        ]

    def is_derived(self, field_path: str) -> bool:
        return field_path in self.derived_fields()

    def has_origin(self) -> bool:
        """True when at least one FETCH step carries a source reference."""
        return len(self.origin_sources()) > 0

    def describe(self) -> str:
        """Human-readable chain, one step per line."""
        return "\n".join(step.describe() for step in self.steps)

    def explain_field(self, field_path: str) -> str:
        """Answer 'where did this number come from?' for one field."""
        relevant = self.steps_for(field_path)
        if not relevant:
            return "No lineage recorded for {0}.".format(field_path)
        lines = [step.describe() for step in relevant]
        if self.is_derived(field_path):
            lines.append(
                "NOTE: {0} was computed by this project, not published by a "
                "source.".format(field_path)
            )
        return "\n".join(lines)


class LineageBuilder:
    """Convenience wrapper for accumulating steps in pipeline order.

    Sequence numbers are assigned automatically so callers cannot record steps
    out of order by accident.
    """

    def __init__(self, record_id: str):
        self._lineage = DataLineage(record_id=record_id)

    # -- generic ----------------------------------------------------------
    def add(
        self,
        transformation: TransformationType,
        description: str,
        module: Optional[str] = None,
        inputs: Optional[List[str]] = None,
        output: Optional[str] = None,
        input_value: Optional[Any] = None,
        output_value: Optional[Any] = None,
        parameters: Optional[Dict[str, Any]] = None,
        source_reference: Optional[SourceReference] = None,
        at: Optional[datetime] = None,
    ) -> "LineageBuilder":
        step = LineageStep(
            sequence=len(self._lineage.steps),
            transformation=transformation,
            description=description,
            module=module,
            inputs=list(inputs or []),
            output=output,
            input_value=input_value,
            output_value=output_value,
            parameters=dict(parameters or {}),
            source_reference=source_reference,
            at=as_utc(at) or utc_now(),
        )
        self._lineage.steps.append(step)
        return self

    # -- named pipeline stages --------------------------------------------
    def fetched(self, source_reference: SourceReference, description: Optional[str] = None,
                **kwargs) -> "LineageBuilder":
        """Record the FETCH that brought data in. Requires a source reference."""
        if source_reference is None:
            raise ProvenanceError("a FETCH step must carry a SourceReference")
        return self.add(
            TransformationType.FETCH,
            description or "fetched from {0}".format(source_reference.source_name),
            source_reference=source_reference,
            **kwargs
        )

    def parsed(self, description: str, **kwargs) -> "LineageBuilder":
        return self.add(TransformationType.PARSE, description, **kwargs)

    def normalized(
        self,
        transformation: TransformationType,
        description: str,
        **kwargs
    ) -> "LineageBuilder":
        if transformation not in (
            TransformationType.UNIT_CONVERSION,
            TransformationType.FIELD_MAPPING,
            TransformationType.EPOCH_CONVERSION,
            TransformationType.FRAME_ANNOTATION,
            TransformationType.NAME_NORMALIZATION,
        ):
            raise ValueError(
                "{0} is not a normalization transformation".format(transformation.value)
            )
        return self.add(transformation, description, **kwargs)

    def derived(self, description: str, inputs: List[str], output: str,
                **kwargs) -> "LineageBuilder":
        """Record a value this project computed. Inputs are mandatory."""
        if not inputs:
            raise ProvenanceError(
                "a DERIVATION step must name the inputs it was computed from"
            )
        return self.add(
            TransformationType.DERIVATION,
            description,
            inputs=inputs,
            output=output,
            **kwargs
        )

    def merged(self, description: str, **kwargs) -> "LineageBuilder":
        return self.add(TransformationType.MERGE, description, **kwargs)

    def resolved_conflict(self, description: str, **kwargs) -> "LineageBuilder":
        return self.add(TransformationType.CONFLICT_RESOLUTION, description, **kwargs)

    def validated(self, description: str, **kwargs) -> "LineageBuilder":
        return self.add(TransformationType.VALIDATION, description, **kwargs)

    def finalized(self, description: str = "written to canonical form",
                  **kwargs) -> "LineageBuilder":
        return self.add(TransformationType.FINALIZATION, description, **kwargs)

    def build(self) -> DataLineage:
        return self._lineage

    @property
    def lineage(self) -> DataLineage:
        return self._lineage


def require_provenance(record, lineage: Optional[DataLineage] = None) -> None:
    """Assert that a record may proceed to indexing.

    Missing provenance is an error, not a warning: an unattributed record cannot
    be cited, cannot be refreshed, and cannot be checked against its source.
    """
    if not getattr(record, "source_references", None):
        raise ProvenanceError(
            "record {0!r} has no source_references; it cannot be indexed or "
            "cited".format(getattr(record, "canonical_id", "<unknown>"))
        )
    if lineage is not None and not lineage.has_origin():
        raise ProvenanceError(
            "lineage for {0!r} records no FETCH step with a source; the origin of "
            "the data is unknown".format(lineage.record_id)
        )


def derive_quantity(
    value,
    inputs: Dict[str, Any],
    description: str,
    output_field: str,
    builder: Optional[LineageBuilder] = None,
    module: Optional[str] = None,
):
    """Tag a computed `Quantity` as derived and record the derivation.

    The returned quantity's source is `SourceType.CALCULATED`, so the quality
    engine's authority ranking can never let a value this project computed
    outrank one a source published.
    """
    from data.models.units import Quantity  # local import: models must not import provenance

    if not isinstance(value, Quantity):
        raise TypeError("derive_quantity expects a Quantity, got {0}".format(type(value)))
    if not inputs:
        raise ProvenanceError("a derived value must name the inputs it came from")

    contributing = []
    for item in inputs.values():
        if isinstance(item, Quantity) and item.source is not None:
            if item.source.source_name not in contributing:
                contributing.append(item.source.source_name)

    calculated = SourceReference(
        source_name="derived",
        source_type=SourceType.CALCULATED,
        attribution="Computed by LostIntoSpacE from {0}".format(
            ", ".join(contributing) if contributing else "unattributed inputs"
        ),
    )
    tagged = value.with_source(calculated)

    if builder is not None:
        builder.derived(
            description,
            inputs=sorted(inputs.keys()),
            output=output_field,
            module=module,
            output_value=tagged.value,
            parameters={"unit": tagged.unit, "contributing_sources": contributing},
        )
    return tagged
