"""Document/literature records.

A NASA technical report is a document, not a space object. It gets its own
record type so the RAG layer can cite real literature with real identifiers,
authors and dates, instead of paraphrasing an abstract into a `SpaceObject`
description and losing the citation.
"""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts._time import as_utc

from .base import NamedRecord
from .enums import ObjectType

__all__ = ["DocumentAuthor", "DocumentLink", "DocumentRecord"]


class DocumentAuthor(BaseModel):
    """One author and their affiliation."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    organization: Optional[str] = None
    location: Optional[str] = None
    #: Author order as the source lists it.
    sequence: Optional[int] = None


class DocumentLink(BaseModel):
    """A retrievable rendition of the document."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1)
    mime_type: Optional[str] = None
    label: Optional[str] = None
    #: Whether this project may legally index the full content behind the link.
    #: Defaults to False: metadata is always citable, full text is not.
    full_text_permitted: bool = False


class DocumentRecord(NamedRecord):
    """Bibliographic metadata for a technical or scientific document.

    `name` holds the title (inherited from `NamedRecord`), so documents and
    objects share one search path.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    record_type: str = "document"
    object_type: ObjectType = ObjectType.DOCUMENT

    abstract: Optional[str] = None
    authors: List[DocumentAuthor] = Field(default_factory=list)
    #: Publishing organization or NASA centre.
    publisher: Optional[str] = None
    publication_date: Optional[date] = None
    #: Document type as the source classifies it, e.g. "CONTRACTOR_REPORT".
    document_type: Optional[str] = None
    document_type_label: Optional[str] = None
    #: Report numbers, accession numbers, DOIs.
    identifiers: List[str] = Field(default_factory=list)
    subject_categories: List[str] = Field(default_factory=list)
    #: Distribution/access statement as published, e.g. "PUBLIC".
    distribution: Optional[str] = None
    #: The source's copyright determination. Gates whether full text may be used.
    copyright_determination: Optional[str] = None
    links: List[DocumentLink] = Field(default_factory=list)
    #: True when the source flags this as a lessons-learned document — directly
    #: useful for the failure-analysis material.
    is_lessons_learned: bool = False

    #: When the source record itself was created and last modified.
    source_created_at: Optional[datetime] = None

    @field_validator("source_created_at")
    @classmethod
    def _utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return as_utc(value)

    @model_validator(mode="after")
    def _check(self) -> "DocumentRecord":
        if self.publication_date is not None:
            if not (1800 <= self.publication_date.year <= 2200):
                raise ValueError(
                    "publication_date {0} is outside a plausible range".format(
                        self.publication_date.isoformat()
                    )
                )
        return self

    def temporal_anchor(self) -> Optional[datetime]:
        """A document's content is anchored to when it was published."""
        if self.publication_date is not None:
            return as_utc(
                datetime(
                    self.publication_date.year,
                    self.publication_date.month,
                    self.publication_date.day,
                )
            )
        return self.source_created_at or self.valid_at

    @property
    def author_names(self) -> List[str]:
        ordered = sorted(
            self.authors,
            key=lambda author: (author.sequence if author.sequence is not None else 9999),
        )
        return [author.name for author in ordered]

    def citation_text(self) -> str:
        """A plain citation line for the AI layer to reproduce verbatim."""
        parts = []
        if self.author_names:
            leading = self.author_names[0]
            if len(self.author_names) > 1:
                leading += " et al."
            parts.append(leading)
        parts.append('"{0}"'.format(self.name))
        if self.publisher:
            parts.append(self.publisher)
        if self.publication_date:
            parts.append(str(self.publication_date.year))
        if self.identifiers:
            parts.append(self.identifiers[0])
        return ". ".join(parts)

    @property
    def may_index_full_text(self) -> bool:
        """Whether any link permits full-text indexing.

        Defaults to False everywhere. Abstract-and-metadata indexing is always
        allowed and is what the embedding layer uses unless this says otherwise.
        """
        return any(link.full_text_permitted for link in self.links)
