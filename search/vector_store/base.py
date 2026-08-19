"""The `VectorStore` interface.

Deliberately narrow: upsert, delete, get, search, health check. Everything
retrieval needs and nothing that ties it to one backend.

**On infrastructure.** The project already runs PostgreSQL (P2's database).
When the pgvector-versus-hosted decision in `DECISION_LOG.md` closes in favour
of pgvector, the vectors live in *that* Postgres as another table — not in a
second database. `InMemoryVectorStore` exists so retrieval, RAG and evaluation
can be built and measured before that decision lands; swapping it out changes
one constructor call, because callers only ever see this interface.
"""

import abc
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts._time import utc_now
from contracts.provenance import SourceReference
from contracts.search import SearchEntityType

from ..embeddings.vectors import TRUST_ORDER, EmbeddingRecord, TrustLevel, VectorMetadata

__all__ = [
    "VectorFilter",
    "VectorMatch",
    "VectorStoreHealth",
    "VectorStore",
]


class VectorFilter(BaseModel):
    """Metadata constraints applied alongside similarity.

    Filters are applied *before* ranking, so a `top_k` of 5 returns the five
    best matches that satisfy the filter rather than five candidates that may
    all be discarded afterwards.
    """

    model_config = ConfigDict(extra="forbid")

    canonical_ids: List[str] = Field(default_factory=list)
    entity_types: List[SearchEntityType] = Field(default_factory=list)
    object_types: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    source_types: List[str] = Field(default_factory=list)
    missions: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    #: Inclusive window on the record's own temporal anchor.
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    #: Exclude anything less trustworthy than this.
    min_trust: Optional[TrustLevel] = None
    #: Drop vectors whose record was assessed as historical or stale.
    exclude_historical: bool = False

    @model_validator(mode="after")
    def _check(self) -> "VectorFilter":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date is after end_date")
        return self

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.canonical_ids, self.entity_types, self.object_types,
                self.sources, self.source_types, self.missions, self.topics,
                self.start_date, self.end_date, self.min_trust,
                self.exclude_historical,
            )
        )

    def matches(self, metadata: VectorMetadata) -> bool:
        """Whether a vector's metadata satisfies every constraint."""
        if self.canonical_ids and metadata.canonical_id not in self.canonical_ids:
            return False
        if self.entity_types and metadata.entity_type not in self.entity_types:
            return False
        if self.object_types and metadata.object_type not in self.object_types:
            return False
        if self.sources and not set(self.sources) & set(metadata.source_names):
            return False
        if self.source_types and not set(self.source_types) & set(metadata.source_types):
            return False
        if self.missions and not set(self.missions) & set(metadata.mission_ids):
            return False
        if self.topics:
            wanted = {topic.lower() for topic in self.topics}
            present = {topic.lower() for topic in metadata.topics}
            if not wanted & present:
                return False
        if self.start_date:
            if metadata.timestamp is None or metadata.timestamp < self.start_date:
                return False
        if self.end_date:
            if metadata.timestamp is None or metadata.timestamp > self.end_date:
                return False
        if self.min_trust and not metadata.meets_trust(self.min_trust):
            return False
        if self.exclude_historical and metadata.freshness_class is not None:
            if metadata.freshness_class.value in ("HISTORICAL",):
                return False
        return True


class VectorMatch(BaseModel):
    """One retrieved vector, with everything needed to rank and cite it."""

    model_config = ConfigDict(extra="forbid")

    #: Chunk id, `<canonical_id>#<chunk_index>`.
    id: str
    #: The record the chunk belongs to.
    canonical_id: str
    #: Cosine similarity in -1..1. Higher is closer.
    similarity: float
    metadata: VectorMetadata
    #: Provenance for the underlying record, when the caller supplied it.
    sources: List[SourceReference] = Field(default_factory=list)

    @property
    def title(self) -> str:
        return self.metadata.title

    @property
    def snippet(self) -> Optional[str]:
        return self.metadata.snippet

    @property
    def source_names(self) -> List[str]:
        return self.metadata.source_names

    @property
    def trust_level(self) -> TrustLevel:
        return self.metadata.trust_level

    def describe(self) -> str:
        return "{0} ({1:.3f}) via {2}".format(
            self.metadata.title or self.canonical_id,
            self.similarity,
            ", ".join(self.metadata.source_names) or "unattributed",
        )


class VectorStoreHealth(BaseModel):
    """Result of probing a vector store."""

    model_config = ConfigDict(extra="forbid")

    healthy: bool
    backend: str
    vector_count: int = 0
    dimensions: Optional[int] = None
    #: Set when the store holds vectors from more than one model — a corruption
    #: that makes similarity meaningless and must be surfaced loudly.
    mixed_models: List[str] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=utc_now)
    detail: Optional[str] = None


class VectorStore(abc.ABC):
    """Storage and nearest-neighbour search over embedding vectors."""

    backend = "abstract"

    @abc.abstractmethod
    def upsert(self, records: Iterable[EmbeddingRecord]) -> int:
        """Insert or replace vectors. Returns how many were written."""

    @abc.abstractmethod
    def delete(self, ids: Iterable[str]) -> int:
        """Delete by chunk id. Returns how many were removed."""

    @abc.abstractmethod
    def delete_by_canonical_id(self, canonical_id: str) -> int:
        """Delete every chunk belonging to one record."""

    @abc.abstractmethod
    def get(self, vector_id: str) -> Optional[EmbeddingRecord]:
        """Fetch one vector by chunk id."""

    @abc.abstractmethod
    def search(
        self,
        vector: Sequence[float],
        top_k: int = 10,
        filters: Optional[VectorFilter] = None,
        min_similarity: float = 0.0,
    ) -> List[VectorMatch]:
        """Nearest neighbours, filtered by metadata."""

    @abc.abstractmethod
    def health_check(self) -> VectorStoreHealth:
        """Probe the store. Reports rather than raising."""

    def count(self) -> int:
        raise NotImplementedError

    def __len__(self) -> int:
        return self.count()
