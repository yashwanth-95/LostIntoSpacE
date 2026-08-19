"""Query intent classification.

Intent changes what a good result *is*, so ranking cannot be intent-blind:

* "Ceres" wants one specific record, ranked by exact identity.
* "How does staging work?" wants an explanation, so editorial concepts outrank
  archive records that merely mention the word.
* "Where is the ISS right now?" wants current data, so a six-week-old element
  set is the wrong answer no matter how well it matches the words.

Deliberately rule-based. The signals are strong and few, the rules are
inspectable, and a misclassification is traceable to the phrase that caused it —
none of which is true of a learned classifier at this scale.
"""

import re
from enum import Enum
from typing import List, Optional, Sequence, Set

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "QueryIntent",
    "IntentAssessment",
    "classify_intent",
    "TEMPORAL_MARKERS",
]


class QueryIntent(str, Enum):
    """What the user is trying to do."""

    #: Find one specific named entity. "Ceres", "Apollo 11", "25544".
    LOOKUP = "LOOKUP"
    #: Understand a mechanism. "How does a gravity assist work?"
    CONCEPTUAL = "CONCEPTUAL"
    #: Wants the present state of something that changes.
    #: "Where is the ISS now?", "latest mission status".
    CURRENT_STATE = "CURRENT_STATE"
    #: Weigh two or more things against each other.
    COMPARISON = "COMPARISON"
    #: Browse a category. "Mars missions", "Jupiter spacecraft".
    EXPLORATORY = "EXPLORATORY"
    UNKNOWN = "UNKNOWN"


#: Words that make a question about *now*. Their presence is the single most
#: consequential signal here: it decides whether cached embeddings may answer at
#: all, or whether a live source must be consulted.
TEMPORAL_MARKERS: Set[str] = {
    "now", "current", "currently", "today", "tonight", "latest", "live",
    "recent", "recently", "present", "at the moment", "right now", "up to date",
    "up-to-date", "this week", "this month", "as of today", "still",
}

#: Phrases asking for a mechanism or a cause.
_CONCEPTUAL_PATTERNS = (
    r"\bhow (?:does|do|did|can|is|are|would)\b",
    r"\bwhat (?:causes|caused|is|are|does)\b",
    r"\bwhy (?:do|does|did|is|are|would)\b",
    r"\bexplain\b",
    r"\bwhat happens\b",
    r"\bhow to\b",
    r"\bmeaning of\b",
    r"\bdefine\b",
)

#: "What is the <attribute> of <entity>?" asks for a stored value, not a
#: mechanism. Checked before the conceptual patterns, because a bare "what is"
#: matches both and the factual reading is the more specific one.
_ATTRIBUTE_LOOKUP_PATTERNS = (
    r"\bwhat (?:is|are|was|were) the\b.+\bof\b",
    r"\bhow (?:big|large|massive|far|old|heavy|hot|cold) is\b",
    r"\bwhat (?:is|are) .{0,30}\b(?:mass|radius|diameter|temperature|period|"
    r"distance|altitude|eccentricity|inclination|magnitude|density)\b",
)

_COMPARISON_PATTERNS = (
    r"\bcompare\b",
    r"\b(?:vs|versus)\b",
    r"\bdifference between\b",
    r"\bbetter than\b",
    r"\bwhich is (?:better|faster|heavier|larger)\b",
)

_EXPLORATORY_PATTERNS = (
    r"\blist\b",
    r"\bshow me\b",
    r"\ball\b",
    r"\bwhich (?:missions|spacecraft|planets|objects|rockets)\b",
    r"\bkinds? of\b",
    r"\btypes? of\b",
)

#: Plural category nouns. Their presence turns a short phrase from a name into
#: a browse: "Mars missions" wants a list, "Apollo 11" wants one record.
_CATEGORY_PLURALS: Set[str] = {
    "missions", "spacecraft", "planets", "moons", "rockets", "asteroids",
    "comets", "satellites", "stars", "exoplanets", "probes", "rovers",
    "landers", "orbiters", "launchers", "engines", "concepts", "lessons",
    "objects", "events", "observations", "telescopes",
}

#: A four-digit year mentioned in the question.
_YEAR = re.compile(r"\b(2[0-9]{3})\b")

#: How far ahead a question may reach before stored data cannot support it.
#: Generous: published ephemerides genuinely cover decades, and JPL solutions
#: are valid well beyond a single year. Beyond this, an answer derived from a
#: current element set would be a fabrication dressed as a calculation.
FAR_FUTURE_HORIZON_YEARS = 50

#: A bare catalogue number, designation or international designator.
_IDENTIFIER = re.compile(
    r"^\s*(?:\d{1,6}|[12]\d{3}\s?[a-z]{2}\d*|\d{4}-\d{3}[a-z])\s*$", re.IGNORECASE
)


class IntentAssessment(BaseModel):
    """A classification, with the evidence that produced it."""

    model_config = ConfigDict(extra="forbid")

    intent: QueryIntent = QueryIntent.UNKNOWN
    #: 0..1. Low confidence means ranking should not lean on the intent.
    confidence: float = 0.0
    #: Phrases that triggered the classification, for explainability.
    signals: List[str] = Field(default_factory=list)
    #: True when the question is about the present state of something.
    #: Read by the RAG layer to decide whether live data is required.
    is_time_sensitive: bool = False
    #: A year far beyond any stored data's validity, when the question names
    #: one. Orbital elements and ephemerides are only valid near their epoch,
    #: so a question about a distant future date cannot be answered from them
    #: however good the retrieval is.
    far_future_year: Optional[int] = None

    @property
    def asks_beyond_data_validity(self) -> bool:
        return self.far_future_year is not None

    @property
    def wants_explanation(self) -> bool:
        return self.intent in (QueryIntent.CONCEPTUAL, QueryIntent.COMPARISON)

    @property
    def wants_specific_record(self) -> bool:
        return self.intent is QueryIntent.LOOKUP


def _matches(text: str, patterns: Sequence[str]) -> List[str]:
    found = []
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            found.append(match.group(0))
    return found


def classify_intent(text: str) -> IntentAssessment:
    """Classify a query. Never raises; unknown is a valid answer."""
    lowered = " ".join(str(text or "").lower().split())
    if not lowered:
        return IntentAssessment()

    signals: List[str] = []

    #: Temporal markers are checked first and recorded independently of the
    #: chosen intent — "how does orbital decay affect the ISS right now?" is
    #: both conceptual and time-sensitive, and losing the second would let a
    #: stale answer through.
    temporal = [marker for marker in TEMPORAL_MARKERS if marker in lowered]
    is_time_sensitive = bool(temporal)
    signals.extend(temporal)

    far_future = _far_future_year(lowered)
    if far_future is not None:
        signals.append("year {0}".format(far_future))

    attribute_lookup = _matches(lowered, _ATTRIBUTE_LOOKUP_PATTERNS)
    conceptual = _matches(lowered, _CONCEPTUAL_PATTERNS)
    comparison = _matches(lowered, _COMPARISON_PATTERNS)
    exploratory = _matches(lowered, _EXPLORATORY_PATTERNS)

    #: An attribute question outranks the conceptual reading. "What is the mass
    #: of Ceres?" wants a value from an archive, not an explanation, and
    #: routing it to editorial content would answer the wrong question.
    if attribute_lookup and not is_time_sensitive:
        return IntentAssessment(
            intent=QueryIntent.LOOKUP,
            confidence=0.75,
            signals=signals + attribute_lookup,
            is_time_sensitive=False,
            far_future_year=far_future,
        )

    if comparison:
        return IntentAssessment(
            intent=QueryIntent.COMPARISON,
            confidence=0.8,
            signals=signals + comparison,
            is_time_sensitive=is_time_sensitive,
            far_future_year=far_future,
        )

    #: A time-sensitive question about a specific thing outranks the
    #: conceptual reading, because serving it from cache would be wrong.
    if is_time_sensitive and not conceptual:
        return IntentAssessment(
            intent=QueryIntent.CURRENT_STATE,
            confidence=0.85,
            signals=signals,
            is_time_sensitive=True,
            far_future_year=far_future,
        )

    if conceptual:
        return IntentAssessment(
            intent=QueryIntent.CONCEPTUAL,
            confidence=0.8,
            signals=signals + conceptual,
            is_time_sensitive=is_time_sensitive,
            far_future_year=far_future,
        )

    if exploratory:
        return IntentAssessment(
            intent=QueryIntent.EXPLORATORY,
            confidence=0.7,
            signals=signals + exploratory,
            is_time_sensitive=is_time_sensitive,
            far_future_year=far_future,
        )

    words = lowered.split()
    if _IDENTIFIER.match(lowered):
        return IntentAssessment(
            intent=QueryIntent.LOOKUP,
            confidence=0.95,
            signals=signals + ["bare identifier"],
            is_time_sensitive=is_time_sensitive,
            far_future_year=far_future,
        )

    #: A short phrase ending in a plural category noun is a browse, not a name.
    #: "Mars missions" wants several results; "Apollo 11" wants one.
    category = [word for word in words if word in _CATEGORY_PLURALS]
    if category:
        return IntentAssessment(
            intent=QueryIntent.EXPLORATORY,
            confidence=0.7,
            signals=signals + category,
            is_time_sensitive=is_time_sensitive,
            far_future_year=far_future,
        )

    #: A short phrase with no question words reads as a name.
    if len(words) <= 4:
        return IntentAssessment(
            intent=QueryIntent.LOOKUP,
            confidence=0.6,
            signals=signals + ["short noun phrase"],
            is_time_sensitive=is_time_sensitive,
            far_future_year=far_future,
        )

    return IntentAssessment(
        intent=QueryIntent.UNKNOWN,
        confidence=0.2,
        signals=signals,
        is_time_sensitive=is_time_sensitive,
        far_future_year=far_future,
    )


def _far_future_year(lowered):
    """A year in the question lying beyond stored data's validity.

    Returns None for a past or near-future year: those are ordinary historical
    or planning questions the corpus may well be able to answer.
    """
    from datetime import datetime

    current = datetime.utcnow().year
    for match in _YEAR.finditer(lowered):
        year = int(match.group(1))
        if year - current > FAR_FUTURE_HORIZON_YEARS:
            return year
    return None
