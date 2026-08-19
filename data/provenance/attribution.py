"""Attribution and citation rendering.

Every scientific value shown to a user carries a credit line, and every AI
answer carries citations. Both are built here so the wording is consistent
wherever it appears.
"""

from typing import Dict, Iterable, List, Optional

from pydantic import BaseModel

from contracts.provenance import SourceReference

from .freshness import FreshnessAssessment

__all__ = [
    "Citation",
    "build_citation",
    "collect_citations",
    "attribution_block",
    "freshness_caveat",
]


class Citation:
    """A renderable reference to one source, optionally with a freshness caveat."""

    def __init__(
        self,
        source: SourceReference,
        assessment: Optional[FreshnessAssessment] = None,
        field_path: Optional[str] = None,
    ):
        self.source = source
        self.assessment = assessment
        self.field_path = field_path

    def to_text(self) -> str:
        parts = [self.source.display_credit()]
        if self.source.source_record_id:
            parts.append("record {0}".format(self.source.source_record_id))
        if self.source.source_version:
            parts.append("version {0}".format(self.source.source_version))
        parts.append("retrieved {0}".format(self.source.retrieved_at.strftime("%Y-%m-%d")))
        text = ", ".join(parts)
        caveat = freshness_caveat(self.assessment)
        if caveat:
            text = "{0} — {1}".format(text, caveat)
        return text

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "source_name": self.source.source_name,
            "source_type": self.source.source_type.value,
            "source_url": self.source.source_url,
            "source_record_id": self.source.source_record_id,
            "retrieved_at": self.source.retrieved_at.isoformat(),
            "attribution": self.source.display_credit(),
        }
        if self.field_path:
            payload["field"] = self.field_path
        if self.assessment is not None:
            payload["freshness_class"] = self.assessment.freshness_class.value
            payload["may_present_as_live"] = self.assessment.may_present_as_live
            payload["is_stale"] = self.assessment.is_stale
        return payload

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "Citation({0!r})".format(self.to_text())


def freshness_caveat(assessment: Optional[FreshnessAssessment]) -> Optional[str]:
    """The sentence that must accompany data that is not current.

    Returns `None` only when the data genuinely may be described as live.
    """
    if assessment is None:
        return None
    if assessment.may_present_as_live:
        return None
    if assessment.is_stale:
        return "this data is stale and should be refreshed before it is relied on"
    label = assessment.freshness_class.value.replace("_", " ").lower()
    return "{0} data, not a current measurement".format(label)


def build_citation(
    source: SourceReference,
    assessment: Optional[FreshnessAssessment] = None,
    field_path: Optional[str] = None,
) -> Citation:
    return Citation(source=source, assessment=assessment, field_path=field_path)


def collect_citations(record, assessment: Optional[FreshnessAssessment] = None) -> List[Citation]:
    """Citations for a record: its own sources plus per-value sources.

    A record assembled from three archives cites all three, and a single value
    sourced differently from its parent record gets its own citation.
    """
    citations: List[Citation] = []
    seen = set()

    for ref in getattr(record, "source_references", []) or []:
        key = (ref.source_name, ref.source_record_id, None)
        if key not in seen:
            seen.add(key)
            citations.append(Citation(ref, assessment))

    for field_path, quantity_source in _walk_quantity_sources(record):
        key = (quantity_source.source_name, quantity_source.source_record_id, field_path)
        record_level = (quantity_source.source_name, quantity_source.source_record_id, None)
        if key in seen or record_level in seen:
            continue
        seen.add(key)
        citations.append(Citation(quantity_source, assessment, field_path))

    return citations


def _walk_quantity_sources(model, prefix: str = "") -> Iterable:
    """Yield `(field_path, SourceReference)` for every attributed Quantity."""
    from data.models.units import Quantity

    # `model_fields` must be read from the class: reading it from an instance is
    # deprecated in pydantic 2.11 and removed in v3.
    fields = getattr(type(model), "model_fields", None)
    if not fields:
        return
    for name in fields:
        value = getattr(model, name, None)
        path = "{0}.{1}".format(prefix, name) if prefix else name
        if isinstance(value, Quantity):
            if value.source is not None:
                yield (path, value.source)
        elif isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, Quantity) and item.source is not None:
                    yield ("{0}.{1}".format(path, key), item.source)
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                if isinstance(item, Quantity) and item.source is not None:
                    yield ("{0}[{1}]".format(path, index), item.source)
                elif isinstance(item, BaseModel):
                    for nested in _walk_quantity_sources(item, "{0}[{1}]".format(path, index)):
                        yield nested
        elif isinstance(value, BaseModel):
            for nested in _walk_quantity_sources(value, path):
                yield nested


def attribution_block(record, assessment: Optional[FreshnessAssessment] = None) -> str:
    """Multi-line credit block suitable for display beneath a record."""
    citations = collect_citations(record, assessment)
    if not citations:
        return "No source attribution available for this record."
    lines = ["Sources:"]
    for citation in citations:
        prefix = "  - "
        if citation.field_path:
            prefix = "  - {0}: ".format(citation.field_path)
        lines.append("{0}{1}".format(prefix, citation.to_text()))
    return "\n".join(lines)
