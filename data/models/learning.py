"""Learning content: lessons and engineering concepts.

This is the one record type in the canonical model that is *written* rather than
ingested, so its provenance is `SourceType.EDITORIAL` and it is never presented
with the authority of an archive. It exists because the search and AI layers
need something to explain concepts with — "what causes Max-Q?" has no answer in
JPL's database.

Contract note: the `lessons` table in `docs/architecture/DATABASE.md` is P2's,
and holds the user-facing lesson content for the `/learn` pages. This model is
P4's *indexable* view of the same material plus engineering concepts, so search
and RAG can retrieve it. Coordinate before the two are merged.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import NamedRecord

__all__ = ["ContentKind", "DifficultyLevel", "Equation", "LearningContent"]


class ContentKind(str, Enum):
    """What kind of written material a record is."""

    #: A taught unit with a narrative and a learning objective.
    LESSON = "LESSON"
    #: A single engineering or physics idea, explained.
    CONCEPT = "CONCEPT"
    #: A worked explanation of something that went wrong.
    CASE_STUDY = "CASE_STUDY"
    #: A short definition, for glossary lookups.
    DEFINITION = "DEFINITION"


class DifficultyLevel(str, Enum):
    INTRODUCTORY = "INTRODUCTORY"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


class Equation(BaseModel):
    """One equation, with its symbols spelled out.

    Symbols are required: an equation whose terms are undefined cannot be used
    by the AI layer to explain anything, and cannot be checked by a reader.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    #: LaTeX-free plain form, e.g. "q = 0.5 * rho * v^2".
    expression: str = Field(min_length=1)
    #: symbol -> meaning, e.g. {"q": "dynamic pressure (Pa)"}.
    symbols: Dict[str, str] = Field(default_factory=dict)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _check(self) -> "Equation":
        if not self.symbols:
            raise ValueError(
                "equation {0!r} must define its symbols to be usable".format(self.name)
            )
        return self


class LearningContent(NamedRecord):
    """A lesson, concept, case study or definition."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    record_type: str = "learning_content"

    kind: ContentKind = ContentKind.CONCEPT
    #: URL-friendly identifier, unique within the content set.
    slug: str = Field(min_length=1)
    #: One or two sentences. Used as the search snippet and the RAG summary.
    summary: str = Field(min_length=1)
    #: Full explanation, markdown.
    body: str = ""
    difficulty: DifficultyLevel = DifficultyLevel.INTRODUCTORY

    #: Broad category, e.g. "propulsion", "orbital mechanics", "structures".
    category: Optional[str] = None
    #: Free tags used for search faceting.
    topics: List[str] = Field(default_factory=list)
    #: Terms a reader might search for that are not in the title.
    keywords: List[str] = Field(default_factory=list)

    equations: List[Equation] = Field(default_factory=list)
    #: Canonical ids of related objects, missions and other content.
    related_object_ids: List[str] = Field(default_factory=list)
    related_mission_ids: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)

    #: External references supporting the explanation. Editorial content still
    #: cites its sources; it just is not itself an archive.
    reference_urls: List[str] = Field(default_factory=list)
    #: Canonical ids of `DocumentRecord`s that support this content.
    supporting_document_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "LearningContent":
        if self.kind is ContentKind.LESSON and not self.body:
            raise ValueError("a LESSON needs body content, not just a summary")
        return self

    def searchable_text(self) -> str:
        """Everything a keyword index should see for this record."""
        parts = [self.name, self.summary, self.body or ""]
        parts.extend(self.aliases)
        parts.extend(self.keywords)
        parts.extend(self.topics)
        if self.category:
            parts.append(self.category)
        for equation in self.equations:
            parts.append(equation.name)
            parts.extend(equation.symbols.values())
        return "\n".join(part for part in parts if part)
