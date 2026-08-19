"""Vector records and the metadata every vector must carry.

A bare vector is useless for this product. Retrieval has to be filterable by
source, mission and topic, and every retrieved passage has to be citable — so
the metadata travels with the vector rather than being looked up afterwards
from a table that might have moved on.
"""

import hashlib
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts._time import utc_now
from contracts.provenance import FreshnessClass, SourceType
from contracts.search import SearchEntityType

__all__ = [
    "TrustLevel",
    "trust_for_source_type",
    "VectorMetadata",
    "EmbeddingRecord",
    "content_hash",
]


class TrustLevel(str, Enum):
    """How much weight a retrieved passage should carry.

    Derived from source type rather than set by hand, so it cannot drift away
    from the provenance it is supposed to summarize.
    """

    #: Primary scientific archives.
    AUTHORITATIVE = "AUTHORITATIVE"
    #: Agency APIs and peer-reviewed literature metadata.
    HIGH = "HIGH"
    #: Operational feeds and product catalogues.
    MODERATE = "MODERATE"
    #: Content this project wrote. Accurate, but not an archive.
    EDITORIAL = "EDITORIAL"
    #: Values this project computed, or provenance we could not establish.
    LOW = "LOW"


_TRUST_BY_SOURCE_TYPE = {
    SourceType.PRIMARY_SCIENTIFIC: TrustLevel.AUTHORITATIVE,
    SourceType.LITERATURE: TrustLevel.HIGH,
    SourceType.AGENCY_PUBLIC_API: TrustLevel.HIGH,
    SourceType.EO_CATALOGUE: TrustLevel.MODERATE,
    SourceType.SECONDARY_OPERATIONAL: TrustLevel.MODERATE,
    SourceType.BUNDLED_REFERENCE: TrustLevel.MODERATE,
    SourceType.EDITORIAL: TrustLevel.EDITORIAL,
    SourceType.CALCULATED: TrustLevel.LOW,
    #: Simulator output is low trust *as a statement about the world*, which is
    #: the only thing trust means here. It may be perfectly accurate about the
    #: model that produced it.
    SourceType.SIMULATION: TrustLevel.LOW,
    SourceType.USER_PROVIDED: TrustLevel.LOW,
    SourceType.UNKNOWN: TrustLevel.LOW,
}

#: Ranking order, most trusted first. Used when filtering by minimum trust.
TRUST_ORDER = (
    TrustLevel.AUTHORITATIVE,
    TrustLevel.HIGH,
    TrustLevel.MODERATE,
    TrustLevel.EDITORIAL,
    TrustLevel.LOW,
)


def trust_for_source_type(source_types: Sequence[Any]) -> TrustLevel:
    """The best trust level among a record's sources.

    "Best" rather than "worst": a record assembled from JPL plus a bundled
    fallback is still anchored on JPL. The individual sources remain listed, so
    nothing is hidden by this summary.
    """
    levels = []
    for item in source_types or []:
        if isinstance(item, str):
            try:
                item = SourceType(item)
            except ValueError:
                continue
        levels.append(_TRUST_BY_SOURCE_TYPE.get(item, TrustLevel.LOW))
    if not levels:
        return TrustLevel.LOW
    return sorted(levels, key=lambda level: TRUST_ORDER.index(level))[0]


def content_hash(*parts: Any) -> str:
    """Stable hash of the content that was embedded.

    Used to decide whether a document needs re-embedding. It covers exactly the
    text and the metadata that affect the vector — nothing else, so a change to
    an unrelated field does not trigger pointless recomputation.
    """
    digest = hashlib.sha256()
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (list, tuple, set)):
            payload = "|".join(sorted(str(item) for item in part))
        else:
            payload = str(part)
        digest.update(payload.encode("utf-8"))
        digest.update(b"\x1f")
    return digest.hexdigest()


class VectorMetadata(BaseModel):
    """Everything retrieval needs to filter, rank and cite a vector."""

    model_config = ConfigDict(extra="forbid")

    canonical_id: str
    entity_type: SearchEntityType = SearchEntityType.UNKNOWN
    title: str = ""
    #: Excerpt shown with a retrieved result, and given to the AI layer.
    snippet: Optional[str] = None

    #: Provenance, carried per vector so a retrieved passage is always citable.
    source_names: List[str] = Field(default_factory=list)
    source_types: List[str] = Field(default_factory=list)
    trust_level: TrustLevel = TrustLevel.LOW

    mission_ids: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    object_type: Optional[str] = None

    #: The record's own temporal anchor — what the content is about.
    timestamp: Optional[datetime] = None
    freshness_class: Optional[FreshnessClass] = None
    #: When this vector was computed.
    indexed_at: datetime = Field(default_factory=utc_now)

    #: Which model produced the vector, and over what content.
    model_id: str = ""
    dimensions: int = 0
    content_hash: str = ""
    #: Index of this chunk when a record was split into several vectors.
    chunk_index: int = 0
    chunk_count: int = 1

    extra: Dict[str, Any] = Field(default_factory=dict)

    @property
    def primary_source(self) -> Optional[str]:
        return self.source_names[0] if self.source_names else None

    def meets_trust(self, minimum: TrustLevel) -> bool:
        return TRUST_ORDER.index(self.trust_level) <= TRUST_ORDER.index(minimum)


class EmbeddingRecord(BaseModel):
    """One vector plus its metadata."""

    model_config = ConfigDict(extra="forbid")

    #: Unique per chunk: `<canonical_id>#<chunk_index>`.
    id: str
    vector: List[float]
    metadata: VectorMetadata

    @field_validator("vector")
    @classmethod
    def _non_empty(cls, value: List[float]) -> List[float]:
        if not value:
            raise ValueError("an embedding vector must not be empty")
        return [float(item) for item in value]

    @model_validator(mode="after")
    def _check(self) -> "EmbeddingRecord":
        if self.metadata.dimensions and len(self.vector) != self.metadata.dimensions:
            raise ValueError(
                "vector has {0} dimensions but its metadata declares {1}".format(
                    len(self.vector), self.metadata.dimensions
                )
            )
        return self

    @property
    def dimensions(self) -> int:
        return len(self.vector)
