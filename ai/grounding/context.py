"""Context selection.

Turns ranked search results into the `ContextItem`s handed to the model. Four
jobs, in order of how much they matter:

1. **Attribution.** An item that cannot state its source is dropped, not
   included unattributed. This is the invariant the whole grounding design
   rests on: if it reached the model, it can be cited.
2. **Staleness annotation.** Every item is assessed against its source's
   freshness policy, and a stale one carries a note the answer must repeat.
   Silent staleness is how cached data becomes "current".
3. **Quarantine.** Content attempting prompt injection is withheld, and the
   fact is recorded — visibly, not silently.
4. **Budget.** Highest-value items first, within a character budget, so a long
   tail of weak evidence cannot crowd out the strong evidence.
"""

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from contracts._time import utc_now
from contracts.ai import ContextItem
from contracts.provenance import FreshnessClass, SourceReference, SourceType
from contracts.search import SearchResult

from ..safety.sanitize import InjectionFinding, sanitize_context_text

__all__ = ["ContextBudget", "ContextSelection", "ContextBuilder"]


class ContextBudget(BaseModel):
    """Limits on what reaches the model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Total characters of context. A rough proxy for tokens, deliberately
    #: conservative — running out of window mid-answer truncates citations.
    max_characters: int = 6000
    #: Never send more than this many items, however small they are.
    max_items: int = 8
    #: Characters from any single item, so one long document cannot consume
    #: the whole budget.
    max_item_characters: int = 1200
    #: Results below this relevance are not worth the window they occupy.
    min_relevance: float = 0.05


class ContextSelection(BaseModel):
    """The selected context, and everything that was excluded and why."""

    model_config = ConfigDict(extra="forbid")

    items: List[ContextItem] = Field(default_factory=list)
    #: canonical_id -> reason, for every candidate that did not make it.
    excluded: Dict[str, str] = Field(default_factory=dict)
    #: Injection findings across all candidates, including quarantined ones.
    injection_findings: List[InjectionFinding] = Field(default_factory=list)
    #: Items whose content is past its freshness policy.
    stale_items: List[str] = Field(default_factory=list)
    characters_used: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.items

    @property
    def has_stale_content(self) -> bool:
        return bool(self.stale_items)

    @property
    def quarantined(self) -> List[str]:
        return sorted(
            key for key, reason in self.excluded.items() if "injection" in reason
        )

    def by_ref(self) -> Dict[str, ContextItem]:
        return {item.ref: item for item in self.items}

    def source_references(self) -> List[SourceReference]:
        seen: Dict[str, SourceReference] = {}
        for item in self.items:
            seen.setdefault(item.source.source_name, item.source)
        return list(seen.values())

    def weakest_freshness(self) -> Optional[FreshnessClass]:
        """The least-current class among the items actually used.

        An answer is only as current as its least-current load-bearing source,
        so this is what the response reports.
        """
        order = [
            FreshnessClass.REAL_TIME,
            FreshnessClass.NEAR_REAL_TIME,
            FreshnessClass.RECENT,
            FreshnessClass.HISTORICAL,
            FreshnessClass.STATIC,
        ]
        present = [
            item.freshness_class for item in self.items
            if item.freshness_class is not None
        ]
        if not present:
            return None
        return max(present, key=lambda item: order.index(item))


class ContextBuilder:
    """Builds model context from search results."""

    def __init__(
        self,
        budget: Optional[ContextBudget] = None,
        documents: Optional[Any] = None,
        now: Optional[datetime] = None,
    ):
        self.budget = budget or ContextBudget()
        #: Anything with `.get(id) -> SearchDocument`, for fuller text than a
        #: search snippet carries.
        self.documents = documents
        self._now = now

    def build(
        self,
        results: Sequence[SearchResult],
        live_items: Optional[Sequence[ContextItem]] = None,
    ) -> ContextSelection:
        """Select context from ranked results, plus any live items.

        Live items are placed first and are exempt from the relevance floor:
        they were fetched for this question specifically, and their value is
        their currency rather than their retrieval score.
        """
        selection = ContextSelection()
        used = 0
        index = 1

        for item in live_items or []:
            selection.items.append(item)
            used += len(item.content)
            index += 1

        for result in results:
            if len(selection.items) >= self.budget.max_items:
                selection.excluded[result.id] = "budget: item limit reached"
                continue
            if result.score < self.budget.min_relevance:
                selection.excluded[result.id] = (
                    "relevance {0:.3f} below the floor of {1:.3f}".format(
                        result.score, self.budget.min_relevance
                    )
                )
                continue
            if not result.provenance.is_attributed:
                #: The invariant. An unattributed item cannot be cited, so it
                #: must not become something the model can assert.
                selection.excluded[result.id] = (
                    "no source metadata; an item that cannot be cited is not "
                    "given to the model"
                )
                continue

            content = self._content_for(result)
            if not content.strip():
                selection.excluded[result.id] = "no usable text"
                continue

            sanitized = sanitize_context_text(
                content, location=result.id, max_length=self.budget.max_item_characters
            )
            selection.injection_findings.extend(sanitized.findings)

            if sanitized.should_quarantine:
                selection.excluded[result.id] = (
                    "quarantined: prompt injection detected ({0})".format(
                        sanitized.findings[0].description
                    )
                )
                continue

            if used + len(sanitized.text) > self.budget.max_characters:
                selection.excluded[result.id] = "budget: character limit reached"
                continue

            item = self._to_context_item(result, sanitized.text, "S{0}".format(index))
            if item.staleness_note:
                selection.stale_items.append(item.canonical_id)
            selection.items.append(item)
            used += len(sanitized.text)
            index += 1

        selection.characters_used = used
        return selection

    def _content_for(self, result: SearchResult) -> str:
        """Prefer the full indexed text; fall back to the result summary."""
        if self.documents is not None:
            getter = getattr(self.documents, "get", None)
            document = getter(result.id) if getter else None
            if document is not None:
                text = document.plain_text()
                if text.strip():
                    return text
        return result.summary or result.title

    def _to_context_item(
        self, result: SearchResult, content: str, ref: str
    ) -> ContextItem:
        provenance = result.provenance
        source = (
            provenance.sources[0]
            if provenance.sources
            else SourceReference(source_name="unknown", source_type=SourceType.UNKNOWN)
        )
        staleness = self._staleness_note(result)
        return ContextItem(
            ref=ref,
            canonical_id=result.id,
            title=result.title,
            content=content,
            source=source,
            source_type=source.source_type,
            url=result.url or source.source_url,
            timestamp=result.date,
            retrieved_at=provenance.retrieved_at,
            freshness_class=provenance.freshness_class,
            relevance=result.score,
            may_present_as_live=provenance.may_present_as_live,
            staleness_note=staleness,
        )

    def _staleness_note(self, result: SearchResult) -> Optional[str]:
        """A sentence the answer must carry when content is not current."""
        provenance = result.provenance
        freshness = provenance.freshness_class
        if freshness is None:
            return None
        if freshness in (FreshnessClass.HISTORICAL,):
            #: Historical content is not a problem — it is correct about its
            #: own epoch. It only becomes one if presented as current, which
            #: `may_present_as_live` already forbids.
            return None
        if provenance.may_present_as_live:
            return None
        if freshness in (FreshnessClass.REAL_TIME, FreshnessClass.NEAR_REAL_TIME):
            when = provenance.retrieved_at
            return (
                "This is {0} data retrieved at {1}; it is not a live reading and "
                "may have changed.".format(
                    freshness.value.lower().replace("_", "-"),
                    when.isoformat() if when else "an unrecorded time",
                )
            )
        return None
