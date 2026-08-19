"""Search contracts — shared between backend, frontend and the AI layer.

`SearchQuery`, `SearchResult` and `SearchResponse` are the interface the
`/search` endpoints expose and the frontend renders. They are defined here, in
`packages/contracts/`, because three teams consume them.

One rule is baked into the shape rather than left to convention: **every
scientific result carries its source metadata**. `SearchResult.sources` is
required for any result derived from an external archive, so a result cannot
reach a user without saying where it came from.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._time import as_utc
from .provenance import FreshnessClass, SourceReference, SourceType

__all__ = [
    "SearchEntityType",
    "MatchType",
    "SearchStatus",
    "SortOrder",
    "SearchQuery",
    "ResultProvenance",
    "SearchResult",
    "SearchFacet",
    "SearchResponse",
]


class SearchEntityType(str, Enum):
    """What kind of thing a result is.

    Callers filter on this; the UI uses it to choose how to render a result.
    """

    SPACE_OBJECT = "SPACE_OBJECT"
    MISSION = "MISSION"
    LESSON = "LESSON"
    CONCEPT = "CONCEPT"
    DOCUMENT = "DOCUMENT"
    EVENT = "EVENT"
    EO_PRODUCT = "EO_PRODUCT"
    REFERENCE = "REFERENCE"
    UNKNOWN = "UNKNOWN"


class MatchType(str, Enum):
    """How a result matched. Ordered from strongest to weakest evidence."""

    #: The query equals the title or an identifier.
    EXACT = "EXACT"
    #: The query matched an alternative name.
    ALIAS = "ALIAS"
    #: A title token starts with a query token.
    PREFIX = "PREFIX"
    #: Query tokens appear in the body.
    PARTIAL = "PARTIAL"
    #: Matched by embedding similarity rather than by tokens.
    SEMANTIC = "SEMANTIC"


class SearchStatus(str, Enum):
    """Outcome of a search.

    `NO_RELIABLE_MATCH` is distinct from `EMPTY`: the first says the index has
    candidates but none is trustworthy enough to present, the second says there
    was nothing at all. Collapsing them would let weak matches masquerade as
    answers.
    """

    OK = "OK"
    EMPTY = "EMPTY"
    NO_RELIABLE_MATCH = "NO_RELIABLE_MATCH"


class SortOrder(str, Enum):
    RELEVANCE = "RELEVANCE"
    NEWEST = "NEWEST"
    OLDEST = "OLDEST"
    TITLE = "TITLE"


class SearchQuery(BaseModel):
    """A search request.

    Every filter is optional; `text` alone is the common case. Filters are
    combined with AND, and multiple values within one filter with OR.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = ""
    #: Restrict to these kinds of entity.
    entity_types: List[SearchEntityType] = Field(default_factory=list)
    #: Restrict to records from these sources (`SourceReference.source_name`).
    sources: List[str] = Field(default_factory=list)
    #: Restrict by authority class, e.g. only primary scientific archives.
    source_types: List[SourceType] = Field(default_factory=list)
    #: Canonical `ObjectType` values, for space objects.
    object_types: List[str] = Field(default_factory=list)
    #: Mission canonical ids or names.
    missions: List[str] = Field(default_factory=list)
    #: Topic tags, e.g. "propulsion", "lunar".
    topics: List[str] = Field(default_factory=list)

    #: Inclusive window on each record's own temporal anchor.
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    sort: SortOrder = SortOrder.RELEVANCE
    #: Results scoring below this are withheld rather than shown weakly.
    min_score: float = Field(default=0.0, ge=0.0)
    #: When False, records whose freshness policy marks them stale are excluded.
    include_stale: bool = True
    #: Ask the backend to compute facet counts.
    include_facets: bool = False

    @field_validator("text")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return " ".join(str(value or "").split())

    @field_validator("start_date", "end_date")
    @classmethod
    def _utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return as_utc(value)

    @model_validator(mode="after")
    def _check(self) -> "SearchQuery":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date is after end_date")
        if not self.text and not any(
            (
                self.entity_types, self.sources, self.source_types,
                self.object_types, self.missions, self.topics,
                self.start_date, self.end_date,
            )
        ):
            raise ValueError("a search needs query text or at least one filter")
        return self

    @property
    def is_browse(self) -> bool:
        """True when the query is filters only, with no text to score against."""
        return not self.text


class ResultProvenance(BaseModel):
    """Source metadata carried on every scientific result.

    Required, not optional: a result that cannot say where it came from must
    not be rendered as a scientific fact.
    """

    model_config = ConfigDict(extra="forbid")

    sources: List[SourceReference] = Field(default_factory=list)
    #: Credit lines to display beside the result.
    attribution: List[str] = Field(default_factory=list)
    freshness_class: Optional[FreshnessClass] = None
    #: Whether this result may be described as current. Consult before using
    #: words like "now" or "live" about it.
    may_present_as_live: bool = False
    #: Sentence to show when the data is not current.
    caveat: Optional[str] = None
    retrieved_at: Optional[datetime] = None

    @property
    def source_names(self) -> List[str]:
        seen: List[str] = []
        for reference in self.sources:
            if reference.source_name not in seen:
                seen.append(reference.source_name)
        return seen

    @property
    def is_attributed(self) -> bool:
        return bool(self.sources)


class SearchResult(BaseModel):
    """One hit."""

    model_config = ConfigDict(extra="forbid")

    #: Canonical id of the underlying record.
    id: str
    entity_type: SearchEntityType
    title: str
    #: Short human-readable description or matched excerpt.
    summary: Optional[str] = None
    #: 0..1 relevance.
    score: float = Field(ge=0.0)
    match_type: MatchType = MatchType.PARTIAL
    #: Which fields the query matched, for explainability.
    matched_fields: List[str] = Field(default_factory=list)

    #: Where the underlying data came from. See `ResultProvenance`.
    provenance: ResultProvenance = Field(default_factory=ResultProvenance)

    object_type: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    mission_ids: List[str] = Field(default_factory=list)
    #: The record's own temporal anchor, for date sorting and display.
    date: Optional[datetime] = None
    url: Optional[str] = None
    #: Extra fields a renderer may use. Never a substitute for provenance.
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("date")
    @classmethod
    def _utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return as_utc(value)

    @model_validator(mode="after")
    def _check(self) -> "SearchResult":
        scientific = self.entity_type in (
            SearchEntityType.SPACE_OBJECT,
            SearchEntityType.EVENT,
            SearchEntityType.EO_PRODUCT,
            SearchEntityType.DOCUMENT,
        )
        if scientific and not self.provenance.is_attributed:
            raise ValueError(
                "a {0} result must carry source metadata; results derived from "
                "external archives cannot be shown unattributed".format(
                    self.entity_type.value
                )
            )
        return self


class SearchFacet(BaseModel):
    """Counts for one filterable dimension."""

    model_config = ConfigDict(extra="forbid")

    name: str
    #: value -> number of matching results.
    counts: Dict[str, int] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """A page of results, plus what the caller needs to page and to trust it."""

    model_config = ConfigDict(extra="forbid")

    query: SearchQuery
    status: SearchStatus = SearchStatus.OK
    results: List[SearchResult] = Field(default_factory=list)
    #: Total matches before paging.
    total: int = 0
    offset: int = 0
    limit: int = 20
    took_ms: Optional[float] = None
    facets: List[SearchFacet] = Field(default_factory=list)
    #: Why the status is what it is — shown when nothing reliable was found.
    explanation: Optional[str] = None
    #: Alternative phrasings, when the backend can suggest any.
    suggestions: List[str] = Field(default_factory=list)

    @property
    def has_more(self) -> bool:
        return (self.offset + len(self.results)) < self.total

    @property
    def is_reliable(self) -> bool:
        return self.status is SearchStatus.OK

    def top(self) -> Optional[SearchResult]:
        return self.results[0] if self.results else None

    def source_names(self) -> List[str]:
        """Every source contributing to this page, for a combined credit line."""
        seen: List[str] = []
        for result in self.results:
            for name in result.provenance.source_names:
                if name not in seen:
                    seen.append(name)
        return seen
