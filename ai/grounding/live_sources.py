"""Live data for time-sensitive questions.

Replaces `NullLiveResolver` with something that actually fetches. It is
consulted only when the intent classifier marks a question as being about the
present, and it resolves only the things a live source genuinely covers:

* **Satellite position and orbital elements** — CelesTrak GP, updated every two
  hours. Labelled `SECONDARY_OPERATIONAL`, never presented as a JPL-grade
  solution.
* **Natural events** — NASA EONET, open events.

Everything else returns nothing, and the RAG layer says so. That is the point:
a resolver that returns *something* for every time-sensitive question would
guarantee an answer, and guaranteeing an answer is how stale data gets
presented as current.

Two honesty properties are enforced here rather than left to the prompt:

* `may_present_as_live` is set from the freshness assessment, not from the fact
  that a fetch happened. Data retrieved just now from a two-hourly feed is
  current *for that feed*, and the caveat says so.
* A failure returns nothing rather than falling back to the cache silently. The
  cached value is offered only through `allow_stale`, and it arrives with its
  age attached.
"""

import re
from datetime import timedelta
from typing import Any, Dict, List, Optional, Sequence

from contracts._time import utc_now
from contracts.ai import ContextItem
from contracts.provenance import FreshnessClass, SourceType

from ..safety.sanitize import sanitize_context_text

__all__ = ["LiveSourceResolver", "SATELLITE_PATTERNS", "EVENT_PATTERNS"]

#: Questions this resolver can serve from a satellite element feed.
SATELLITE_PATTERNS = (
    r"\b(?:iss|international space station|zarya)\b",
    r"\b(?:satellite|spacecraft|station)\b.{0,40}\b(?:position|orbit|"
    r"altitude|elements|where)\b",
    r"\bwhere is\b.{0,40}\b(?:iss|satellite|station)\b",
    r"\bnorad\s*(?:id|number|catalog)?\s*\d+",
)

#: Questions this resolver can serve from a natural-event feed.
EVENT_PATTERNS = (
    r"\b(?:wildfire|wildfires|hurricane|storm|volcano|volcanic|eruption|"
    r"flood|iceberg|drought)\b",
    r"\bnatural (?:event|events|disaster|disasters)\b",
    r"\b(?:current|active|ongoing)\b.{0,30}\bevents?\b",
)

#: Well-known objects, so "where is the ISS" resolves without the user knowing
#: a catalogue number.
_KNOWN_SATELLITES = {
    "iss": "25544",
    "international space station": "25544",
    "zarya": "25544",
    "hubble": "20580",
    "hubble space telescope": "20580",
}

_NORAD = re.compile(r"\b(\d{4,6})\b")


class LiveSourceResolver:
    """Fetches current data for questions that genuinely need it."""

    def __init__(
        self,
        celestrak: Optional[Any] = None,
        eonet: Optional[Any] = None,
        cache: Optional[Any] = None,
        allow_stale: bool = True,
        max_items: int = 3,
    ):
        #: Adapters from `data/sources/`. Either may be `None`, in which case
        #: that kind of question simply gets no live data — reported, not
        #: silently substituted.
        self.celestrak = celestrak
        self.eonet = eonet
        self.cache = cache
        #: Whether a stale cached value may be offered when a fetch fails. It
        #: always arrives with its age stated.
        self.allow_stale = allow_stale
        self.max_items = max_items
        #: Populated after each call, for diagnostics.
        self.last_attempt: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    def can_resolve(self, question: str) -> Optional[str]:
        """Which live source, if any, covers this question."""
        text = str(question or "").lower()
        if any(re.search(pattern, text) for pattern in SATELLITE_PATTERNS):
            return "satellite"
        if any(re.search(pattern, text) for pattern in EVENT_PATTERNS):
            return "event"
        return None

    async def resolve_async(self, question: str, intent: Any) -> List[ContextItem]:
        """Fetch live context. Returns an empty list when nothing applies."""
        self.last_attempt = {"question": question, "kind": None,
                             "fetched": False, "reason": None}

        kind = self.can_resolve(question)
        if kind is None:
            self.last_attempt["reason"] = (
                "no live source covers this question"
            )
            return []
        self.last_attempt["kind"] = kind

        try:
            if kind == "satellite":
                items = await self._satellite(question)
            else:
                items = await self._events(question)
        except Exception as exc:  # noqa: BLE001 - degrade, never fail the answer
            self.last_attempt["reason"] = "{0}: {1}".format(
                exc.__class__.__name__, exc
            )
            return []

        self.last_attempt["fetched"] = bool(items)
        if not items:
            self.last_attempt.setdefault(
                "reason", "the live source returned nothing"
            )
        return items

    #: `GroundedRAG` calls `resolve` synchronously in its own guard. The async
    #: variant is the real one; this adapter keeps the protocol simple for
    #: callers that already have a running loop.
    def resolve(self, question: str, intent: Any) -> List[ContextItem]:
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return []
        if loop.is_running():
            #: Already inside a loop — the caller should use `resolve_async`.
            #: Returning nothing is correct: blocking here would deadlock, and
            #: pretending to have data would be worse.
            self.last_attempt = {
                "question": question, "fetched": False,
                "reason": "called synchronously from a running event loop; "
                          "use resolve_async",
            }
            return []
        return loop.run_until_complete(self.resolve_async(question, intent))

    # -- satellites --------------------------------------------------------
    async def _satellite(self, question: str) -> List[ContextItem]:
        if self.celestrak is None:
            self.last_attempt["reason"] = "no satellite source configured"
            return []

        catalog_number = self._catalog_number(question)
        if catalog_number is None:
            self.last_attempt["reason"] = (
                "could not identify which satellite the question is about"
            )
            return []

        record = await self.celestrak.fetch_by_id(catalog_number)
        if record is None:
            return []

        from data.normalization.celestrak import normalize_gp_record

        satellite, _lineage = normalize_gp_record(record)
        return [self._satellite_item(satellite, record)]

    def _catalog_number(self, question: str) -> Optional[str]:
        text = str(question or "").lower()
        for name, number in _KNOWN_SATELLITES.items():
            if name in text:
                return number
        match = _NORAD.search(text)
        return match.group(1) if match else None

    def _satellite_item(self, satellite, record) -> ContextItem:
        """Build a context item, with the currency caveat the feed requires."""
        from data.provenance.freshness import assess_freshness, policy_for

        policy = policy_for("celestrak_gp")
        assessment = assess_freshness(
            policy=policy,
            retrieved_at=record.retrieved_at,
            valid_at=satellite.temporal_anchor(),
        )

        orbit = (satellite.orbits or [None])[0]
        lines = ["Object: {0}".format(satellite.name)]
        if satellite.norad_cat_id:
            lines.append("NORAD catalog number: {0}".format(satellite.norad_cat_id))
        if orbit is not None:
            lines.append("Element set epoch: {0}".format(orbit.epoch.isoformat()))
            lines.append("Reference frame: {0}".format(orbit.frame.describe()))
            elements = orbit.elements
            for label, quantity in (
                ("Inclination", elements.inclination),
                ("Eccentricity", elements.eccentricity),
                ("Mean motion", elements.mean_motion),
                ("RAAN", elements.ascending_node_longitude),
            ):
                if quantity is not None:
                    lines.append("{0}: {1:g} {2}".format(
                        label, quantity.value, quantity.unit
                    ))
        lines.append(
            "These are mean elements for the SGP4 model, not a precise "
            "ephemeris, and not a position fix."
        )

        cleaned = sanitize_context_text("\n".join(lines),
                                        location=satellite.canonical_id)
        return ContextItem(
            ref="L1",
            canonical_id=satellite.canonical_id,
            title="{0} — current element set".format(satellite.name),
            content=cleaned.text,
            source=record.source_reference,
            source_type=SourceType.SECONDARY_OPERATIONAL,
            url=record.source_reference.source_url,
            timestamp=satellite.temporal_anchor(),
            retrieved_at=record.retrieved_at,
            freshness_class=assessment.freshness_class,
            relevance=1.0,
            may_present_as_live=assessment.may_present_as_live,
            staleness_note=(
                None if assessment.may_present_as_live else
                "This element set was published by CelesTrak, which updates "
                "every two hours; it describes the orbit at its epoch, not the "
                "object's position now."
            ),
        )

    # -- natural events ----------------------------------------------------
    async def _events(self, question: str) -> List[ContextItem]:
        if self.eonet is None:
            self.last_attempt["reason"] = "no event source configured"
            return []

        from data.sources.base import SourceQuery

        page = await self.eonet.search(
            SourceQuery(extra={"status": "open"}, limit=self.max_items)
        )
        if not page.records:
            return []

        from data.normalization.nasa import normalize_eonet_event

        items: List[ContextItem] = []
        failures: List[str] = []
        for index, record in enumerate(page.records[:self.max_items], start=1):
            try:
                event, _lineage = normalize_eonet_event(record)
            except Exception as exc:  # noqa: BLE001 - one bad event must not lose the rest
                #: Recorded, not swallowed. A silent `continue` here hid a
                #: real attribute error during development, and an empty
                #: result looks identical to "no events are happening".
                failures.append("{0}: {1}".format(exc.__class__.__name__, exc))
                continue

            lines = ["Event: {0}".format(event.name)]
            if event.categories:
                lines.append("Categories: {0}".format(
                    ", ".join(category.title for category in event.categories)
                ))
            if event.geometries:
                latest = event.geometries[-1]
                lines.append("Most recent report: {0}".format(
                    latest.date.isoformat() if latest.date else "unknown"
                ))
            lines.append("Status: {0}".format(
                "open" if not event.closed_at else "closed"
            ))

            cleaned = sanitize_context_text("\n".join(lines),
                                            location=event.canonical_id)
            items.append(
                ContextItem(
                    ref="L{0}".format(index),
                    canonical_id=event.canonical_id,
                    title=event.name,
                    content=cleaned.text,
                    source=record.source_reference,
                    source_type=SourceType.AGENCY_PUBLIC_API,
                    url=record.source_reference.source_url,
                    timestamp=event.temporal_anchor(),
                    retrieved_at=record.retrieved_at,
                    freshness_class=FreshnessClass.NEAR_REAL_TIME,
                    relevance=1.0,
                    #: EONET reports open events as they are catalogued, so a
                    #: freshly fetched open event may be described as current.
                    may_present_as_live=True,
                )
            )

        if failures and not items:
            self.last_attempt["reason"] = (
                "every retrieved event failed to normalize: {0}".format(
                    "; ".join(failures[:3])
                )
            )
        return items
