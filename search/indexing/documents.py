"""Turning canonical records into indexable documents.

Extraction is **generic by default**. A record type this module has never seen
still produces a usable document, because the extractor falls back to walking
the record's own fields rather than consulting a hard-coded map. That is what
lets newly ingested record types become searchable without a code change.

Specific extractors exist only where a record has structure worth boosting — a
concept's keywords, a mission's objectives, a document's abstract.
"""

from datetime import datetime
from typing import Any, ClassVar, Dict, Iterable, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from contracts.provenance import FreshnessClass, SourceReference
from contracts.search import ResultProvenance, SearchEntityType

__all__ = [
    "FieldWeights",
    "SearchDocument",
    "extract_document",
    "ENTITY_TYPE_BY_RECORD",
]

#: `record_type` -> the entity type search should report.
#: A record type absent from this map falls back to `UNKNOWN`, which is still
#: indexable and still filterable — it simply has no specialised rendering.
ENTITY_TYPE_BY_RECORD: Dict[str, SearchEntityType] = {
    "space_object": SearchEntityType.SPACE_OBJECT,
    "planet": SearchEntityType.SPACE_OBJECT,
    "dwarf_planet": SearchEntityType.SPACE_OBJECT,
    "moon": SearchEntityType.SPACE_OBJECT,
    "star": SearchEntityType.SPACE_OBJECT,
    "asteroid": SearchEntityType.SPACE_OBJECT,
    "comet": SearchEntityType.SPACE_OBJECT,
    "satellite": SearchEntityType.SPACE_OBJECT,
    "space_station": SearchEntityType.SPACE_OBJECT,
    "spacecraft": SearchEntityType.SPACE_OBJECT,
    "launch_vehicle": SearchEntityType.SPACE_OBJECT,
    "mission_target": SearchEntityType.SPACE_OBJECT,
    "mission": SearchEntityType.MISSION,
    "learning_content": SearchEntityType.CONCEPT,
    "document": SearchEntityType.DOCUMENT,
    "natural_event": SearchEntityType.EVENT,
    "eo_product": SearchEntityType.EO_PRODUCT,
}


class FieldWeights(BaseModel):
    """How much each field contributes to a match score."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: float = 6.0
    aliases: float = 4.0
    keywords: float = 3.0
    topics: float = 2.5
    summary: float = 2.0
    body: float = 1.0
    identifiers: float = 5.0

    def weight(self, field: str) -> float:
        return getattr(self, field, 1.0)


DEFAULT_WEIGHTS = FieldWeights()


class SearchDocument(BaseModel):
    """One indexable view of a canonical record.

    Holds the searchable text split by field (so matches can be weighted and
    explained), the filterable attributes, and the provenance every result must
    carry.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    entity_type: SearchEntityType
    title: str
    #: Field name -> text. Weighted separately at scoring time.
    fields: Dict[str, str] = Field(default_factory=dict)
    #: Alternative names, matched exactly rather than tokenised away.
    aliases: List[str] = Field(default_factory=list)
    #: Strong identifiers a user might paste in verbatim.
    identifiers: List[str] = Field(default_factory=list)

    # -- filterable attributes -------------------------------------------
    object_type: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    mission_ids: List[str] = Field(default_factory=list)
    source_names: List[str] = Field(default_factory=list)
    source_types: List[str] = Field(default_factory=list)
    date: Optional[datetime] = None
    freshness_class: Optional[FreshnessClass] = None
    is_stale: bool = False

    # -- display ----------------------------------------------------------
    summary: Optional[str] = None
    url: Optional[str] = None
    provenance: ResultProvenance = Field(default_factory=ResultProvenance)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    #: Stable hash of the indexed content, so unchanged documents can be
    #: skipped when re-embedding (see `search/embeddings`).
    content_hash: Optional[str] = None

    #: How many times each field is repeated in the embedded text. Repetition
    #: is how a bag-of-features embedder is told that a title matters more than
    #: a sentence buried in the body — there is no other channel for it.
    EMBEDDING_REPEATS: ClassVar[Dict[str, int]] = {
        "title": 3,
        "aliases": 2,
        "keywords": 2,
        "topics": 2,
        "summary": 2,
        "identifiers": 1,
        "body": 1,
    }

    def text(self) -> str:
        """The text that gets embedded, with high-value fields weighted.

        Also the input to the content hash, so the hash changes exactly when
        the embedded content does.
        """
        parts: List[str] = []
        for name in sorted(self.fields):
            value = self.fields.get(name)
            if not value:
                continue
            repeats = self.EMBEDDING_REPEATS.get(name, 1)
            parts.extend([value] * repeats)
        if not parts:
            parts = [self.title]
        return "\n".join(parts)

    def plain_text(self) -> str:
        """Unweighted text, for display and for anything that must not see
        the artificial repetition."""
        parts = [self.title]
        parts.extend(self.aliases)
        parts.extend(self.fields.get(name, "") for name in sorted(self.fields))
        return "\n".join(part for part in parts if part)


def _clean(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _joined(values: Optional[Iterable[Any]]) -> str:
    return " ".join(_clean(item) for item in (values or []) if item)


def _provenance_for(record) -> ResultProvenance:
    """Build the provenance block every result carries."""
    references: Sequence[SourceReference] = getattr(record, "source_references", []) or []
    attribution: List[str] = []
    for reference in references:
        credit = reference.display_credit()
        if credit not in attribution:
            attribution.append(credit)
    return ResultProvenance(
        sources=list(references),
        attribution=attribution,
        freshness_class=getattr(record, "freshness_class", None),
        #: Conservative: a document is only marked live when a freshness
        #: assessment has said so. The indexer does not decide this.
        may_present_as_live=False,
        retrieved_at=getattr(record, "retrieved_at", None),
    )


def _generic_fields(record) -> Dict[str, str]:
    """Collect text from any record, without knowing its type.

    Walks the record's own string fields and string lists. This is the reason a
    newly added record type is searchable immediately.
    """
    fields: Dict[str, str] = {}
    body_parts: List[str] = []

    model_fields = getattr(type(record), "model_fields", {}) or {}
    skip = {
        "canonical_id", "record_type", "source_references", "source_specific",
        "confidence_basis", "url", "access_url", "slug",
    }
    for name in model_fields:
        if name in skip:
            continue
        value = getattr(record, name, None)
        if isinstance(value, str) and value:
            if name in ("name", "title"):
                continue
            body_parts.append(value)
        elif isinstance(value, (list, tuple)) and value:
            strings = [item for item in value if isinstance(item, str) and item]
            if strings:
                body_parts.append(" ".join(strings))

    if body_parts:
        fields["body"] = "\n".join(body_parts)
    return fields


def extract_document(record, weights: FieldWeights = DEFAULT_WEIGHTS) -> SearchDocument:
    """Build a `SearchDocument` from any canonical record."""
    record_type = getattr(record, "record_type", "") or ""
    entity_type = ENTITY_TYPE_BY_RECORD.get(record_type, SearchEntityType.UNKNOWN)

    title = _clean(getattr(record, "name", None)) or record.canonical_id
    aliases = [
        _clean(alias)
        for alias in (getattr(record, "aliases", []) or [])
        if _clean(alias)
    ]

    identifiers: List[str] = [record.canonical_id]
    for field in ("designation", "packed_designation", "spk_id", "norad_cat_id",
                  "international_designator", "product_id", "slug"):
        value = getattr(record, field, None)
        if value not in (None, ""):
            identifiers.append(_clean(value))

    fields: Dict[str, str] = {}
    topics: List[str] = list(getattr(record, "topics", []) or [])
    mission_ids: List[str] = []
    summary: Optional[str] = None

    # -- type-specific enrichment -----------------------------------------
    if record_type == "learning_content":
        summary = _clean(getattr(record, "summary", None))
        fields["summary"] = summary
        fields["body"] = _clean(getattr(record, "body", None))
        fields["keywords"] = _joined(getattr(record, "keywords", None))
        category = _clean(getattr(record, "category", None))
        if category:
            topics.append(category)
            fields["topics"] = _joined(topics)
        equations = getattr(record, "equations", []) or []
        if equations:
            fields["body"] += "\n" + "\n".join(
                "{0}: {1} ({2})".format(
                    equation.name, equation.expression,
                    "; ".join(equation.symbols.values()),
                )
                for equation in equations
            )
        mission_ids = list(getattr(record, "related_mission_ids", []) or [])

    elif record_type == "mission":
        summary = _clean(getattr(record, "description", None))
        fields["summary"] = summary
        objectives = _joined(getattr(record, "objectives", None))
        outcome = getattr(record, "outcome", None)
        outcome_text = ""
        if outcome is not None:
            outcome_text = " ".join(
                filter(
                    None,
                    [
                        _clean(outcome.summary),
                        _joined(outcome.achievements),
                        _joined(outcome.anomalies),
                        _joined(outcome.published_lessons),
                    ],
                )
            )
        agency = _clean(getattr(record, "agency", None))
        fields["body"] = "\n".join(
            part for part in (objectives, outcome_text, agency,
                              _joined(getattr(record, "instruments", None)),
                              _joined(getattr(record, "crew", None))) if part
        )
        fields["keywords"] = " ".join(
            filter(None, [
                agency,
                _clean(getattr(record, "mission_type", None)
                       and record.mission_type.value),
            ])
        )
        mission_ids = [record.canonical_id]
        fields["topics"] = _joined(topics)

    elif record_type == "document":
        summary = _clean(getattr(record, "abstract", None))
        fields["summary"] = summary
        fields["keywords"] = _joined(getattr(record, "subject_categories", None))
        fields["body"] = " ".join(
            filter(None, [
                _joined(getattr(record, "author_names", None)),
                _clean(getattr(record, "publisher", None)),
                _joined(getattr(record, "identifiers", None)),
                _clean(getattr(record, "document_type_label", None)),
            ])
        )
        topics.extend(getattr(record, "subject_categories", []) or [])

    elif record_type in ("natural_event",):
        summary = _clean(getattr(record, "description", None))
        fields["summary"] = summary
        categories = [category.id for category in getattr(record, "categories", [])]
        topics.extend(categories)
        fields["topics"] = _joined(topics)
        fields["body"] = _joined(
            [source.id for source in getattr(record, "event_sources", [])]
        )

    elif record_type == "eo_product":
        summary = _clean(getattr(record, "description", None)) or _clean(
            getattr(record, "product_type", None)
        )
        fields["summary"] = summary
        fields["keywords"] = " ".join(
            filter(None, [
                _clean(getattr(record, "mission", None)),
                _clean(getattr(record, "platform", None)),
                _clean(getattr(record, "instrument", None)),
                _clean(getattr(record, "product_type", None)),
                _clean(getattr(record, "processing_level", None)),
            ])
        )
        fields["body"] = _clean(getattr(record, "tile_id", None))

    else:
        summary = _clean(getattr(record, "description", None))
        if summary:
            fields["summary"] = summary
        fields.update(_generic_fields(record))
        object_specific = " ".join(
            filter(None, [
                _clean(getattr(record, "orbit_class", None)),
                _clean(getattr(record, "spectral_type", None)),
                _clean(getattr(record, "agency", None)),
                _clean(getattr(record, "operator", None)),
                _clean(getattr(record, "constellation", None)),
                _clean(getattr(record, "host_star_name", None)),
            ])
        )
        if object_specific:
            fields["keywords"] = object_specific
        mission_ids = list(getattr(record, "mission_canonical_ids", []) or [])

    if topics and "topics" not in fields:
        fields["topics"] = _joined(topics)
    fields["title"] = title
    fields["aliases"] = " ".join(aliases)
    fields["identifiers"] = " ".join(identifiers)

    references = getattr(record, "source_references", []) or []
    object_type = getattr(record, "object_type", None)

    return SearchDocument(
        id=record.canonical_id,
        entity_type=entity_type,
        title=title,
        fields={name: value for name, value in fields.items() if value},
        aliases=aliases,
        identifiers=identifiers,
        object_type=object_type.value if object_type is not None else None,
        topics=sorted({_clean(topic) for topic in topics if _clean(topic)}),
        mission_ids=mission_ids,
        source_names=[reference.source_name for reference in references],
        source_types=[reference.source_type.value for reference in references],
        date=record.temporal_anchor(),
        freshness_class=getattr(record, "freshness_class", None),
        summary=summary,
        url=_clean(getattr(record, "access_url", None)) or None,
        provenance=_provenance_for(record),
        metadata={"record_type": record_type},
    )
