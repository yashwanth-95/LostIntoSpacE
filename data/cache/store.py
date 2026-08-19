"""Caching, driven by each source's freshness policy.

The central idea: **a cache hit is not automatically an answer.** An entry that
has outlived its source's freshness policy is still *available*, but it is no
longer *current*, and those are different things. `CacheLookup` reports which,
so a caller can choose between using stale data with a caveat and going back to
the source.

That distinction is why this is not a plain dict with a TTL. Three outcomes,
not two:

* `FRESH` — within policy. Safe to serve, labelled `CACHED`.
* `STALE` — present but past policy. Serve only with a caveat, or refetch.
* `MISS` — absent.

The TTL comes from `data/provenance/freshness.py`, so the cache and the answer
layer cannot disagree about what "current" means for a given source.
"""

import threading
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, Generic, Optional, Tuple, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from contracts._time import utc_now
from contracts.provenance import FreshnessClass

from ..provenance.freshness import POLICIES, FreshnessPolicy, policy_for

__all__ = [
    "CacheState",
    "CacheEntry",
    "CacheLookup",
    "CacheStats",
    "FreshnessAwareCache",
]


class CacheState(str, Enum):
    """Outcome of a cache lookup."""

    FRESH = "FRESH"
    #: Present, but past its source's freshness policy.
    STALE = "STALE"
    MISS = "MISS"


class CacheEntry(BaseModel):
    """One cached value with the metadata needed to judge it."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    key: str
    value: Any
    source_name: str
    stored_at: datetime = Field(default_factory=utc_now)
    #: When the value stops being current. `None` means it never expires,
    #: which is only valid for genuinely static content.
    expires_at: Optional[datetime] = None
    #: What kind of source this came from. Stored rather than the freshness
    #: *class*, because the class is a function of age: an entry that was
    #: REAL_TIME when written is not REAL_TIME an hour later, and a stored
    #: class would silently become a lie.
    source_category: Optional[str] = None
    #: How many times this entry has been served.
    hits: int = 0

    def age(self, now: Optional[datetime] = None) -> timedelta:
        return (now or utc_now()) - self.stored_at

    def freshness_class(
        self, now: Optional[datetime] = None,
        policy: Optional[FreshnessPolicy] = None,
    ) -> FreshnessClass:
        """Classify this entry *by its current age*, not by its age at write.

        Uses the same assessment the ingestion and answer layers use, so a
        cached record and a freshly fetched one are described identically.
        """
        from ..provenance.freshness import assess_freshness

        resolved = policy or policy_for(self.source_name)
        assessment = assess_freshness(
            policy=resolved,
            retrieved_at=self.stored_at,
            valid_at=self.stored_at,
            now=now,
        )
        return assessment.freshness_class

    def is_fresh(self, now: Optional[datetime] = None) -> bool:
        if self.expires_at is None:
            return True
        return (now or utc_now()) < self.expires_at

    def describe_age(self, now: Optional[datetime] = None) -> str:
        seconds = int(self.age(now).total_seconds())
        if seconds < 90:
            return "{0} second(s) ago".format(seconds)
        if seconds < 5400:
            return "{0} minute(s) ago".format(seconds // 60)
        if seconds < 172800:
            return "{0} hour(s) ago".format(seconds // 3600)
        return "{0} day(s) ago".format(seconds // 86400)


class CacheLookup(BaseModel):
    """The result of a lookup — value plus how much it can be trusted."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    state: CacheState
    value: Any = None
    entry: Optional[CacheEntry] = None

    @property
    def hit(self) -> bool:
        """A usable hit. Stale entries are deliberately not hits."""
        return self.state is CacheState.FRESH

    @property
    def has_value(self) -> bool:
        """Whether a value is available at all, fresh or not."""
        return self.state in (CacheState.FRESH, CacheState.STALE)

    def caveat(self, now: Optional[datetime] = None) -> Optional[str]:
        """The sentence a caller must show if it serves a stale value."""
        if self.state is not CacheState.STALE or self.entry is None:
            return None
        return (
            "This is cached data from {0} that is past its freshness window; "
            "it may no longer be current.".format(self.entry.describe_age(now))
        )


class CacheStats(BaseModel):
    """Counters, so cache behaviour is measurable rather than assumed."""

    model_config = ConfigDict(extra="forbid")

    hits: int = 0
    stale_hits: int = 0
    misses: int = 0
    stores: int = 0
    evictions: int = 0

    @property
    def lookups(self) -> int:
        return self.hits + self.stale_hits + self.misses

    @property
    def hit_rate(self) -> float:
        return self.hits / float(self.lookups) if self.lookups else 0.0

    def summary(self) -> str:
        return (
            "{0} lookup(s): {1} fresh, {2} stale, {3} miss; hit rate "
            "{4:.2f}".format(
                self.lookups, self.hits, self.stale_hits, self.misses,
                self.hit_rate,
            )
        )


class FreshnessAwareCache:
    """In-memory cache whose TTLs come from source freshness policies.

    Thread-safe, bounded, and LRU-evicting. In-memory is right for now: the
    process is single-node, and introducing Redis before there is a second
    node would add an operational dependency for no benefit. The interface is
    what matters — a Redis backing swaps in behind these five methods.
    """

    def __init__(self, max_entries: int = 2000, now: Optional[Callable] = None):
        self.max_entries = max(1, max_entries)
        self._entries: Dict[str, CacheEntry] = {}
        #: Insertion/most-recent-use order, for eviction.
        self._order: list = []
        self._lock = threading.RLock()
        self._now = now or utc_now
        self.stats = CacheStats()

    # -- keys --------------------------------------------------------------
    @staticmethod
    def make_key(source_name: str, operation: str, **parameters) -> str:
        """A stable key. Parameter order must not produce two entries."""
        parts = ["{0}={1}".format(name, parameters[name])
                 for name in sorted(parameters)]
        return "{0}:{1}:{2}".format(source_name, operation, "|".join(parts))

    # -- reads -------------------------------------------------------------
    def get(self, key: str) -> CacheLookup:
        """Look up `key`, reporting freshness rather than just presence."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self.stats.misses += 1
                return CacheLookup(state=CacheState.MISS)

            self._touch(key)
            if entry.is_fresh(self._now()):
                entry.hits += 1
                self.stats.hits += 1
                return CacheLookup(
                    state=CacheState.FRESH, value=entry.value, entry=entry
                )

            self.stats.stale_hits += 1
            return CacheLookup(
                state=CacheState.STALE, value=entry.value, entry=entry
            )

    # -- writes ------------------------------------------------------------
    def put(
        self,
        key: str,
        value: Any,
        source_name: str,
        policy: Optional[FreshnessPolicy] = None,
        ttl: Optional[timedelta] = None,
    ) -> CacheEntry:
        """Store a value, deriving its TTL from the source's policy.

        An explicit `ttl` overrides the policy — used where a provider states
        its own cadence, such as CelesTrak's two-hourly GP updates.
        """
        resolved = policy or policy_for(source_name)
        now = self._now()

        if ttl is not None:
            expires_at = now + ttl
        elif resolved.cache_ttl is not None:
            expires_at = now + resolved.cache_ttl
        else:
            #: No TTL in the policy means static content. It does not expire,
            #: but it is still labelled STATIC rather than passed off as live.
            expires_at = None

        entry = CacheEntry(
            key=key,
            value=value,
            source_name=source_name,
            stored_at=now,
            expires_at=expires_at,
            source_category=resolved.source_category.value,
        )

        with self._lock:
            self._entries[key] = entry
            self._touch(key)
            self.stats.stores += 1
            self._evict_if_needed()
        return entry

    def invalidate(self, key: str) -> bool:
        with self._lock:
            existed = self._entries.pop(key, None) is not None
            if key in self._order:
                self._order.remove(key)
            return existed

    def invalidate_source(self, source_name: str) -> int:
        """Drop every entry from one source. Used when a source is refetched."""
        with self._lock:
            keys = [
                key for key, entry in self._entries.items()
                if entry.source_name == source_name
            ]
            for key in keys:
                self._entries.pop(key, None)
                if key in self._order:
                    self._order.remove(key)
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._order = []

    # -- maintenance -------------------------------------------------------
    def _touch(self, key: str) -> None:
        if key in self._order:
            self._order.remove(key)
        self._order.append(key)

    def _evict_if_needed(self) -> None:
        while len(self._entries) > self.max_entries:
            oldest = self._order.pop(0)
            self._entries.pop(oldest, None)
            self.stats.evictions += 1

    def purge_expired(self) -> int:
        """Remove entries past their TTL. Returns how many went."""
        now = self._now()
        with self._lock:
            keys = [
                key for key, entry in self._entries.items()
                if not entry.is_fresh(now)
            ]
            for key in keys:
                self._entries.pop(key, None)
                if key in self._order:
                    self._order.remove(key)
            return len(keys)

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    # -- convenience -------------------------------------------------------
    async def get_or_fetch(
        self,
        key: str,
        source_name: str,
        fetch: Callable,
        policy: Optional[FreshnessPolicy] = None,
        ttl: Optional[timedelta] = None,
        allow_stale_on_error: bool = True,
    ) -> Tuple[Any, CacheState]:
        """Serve from cache, or fetch and store.

        On a fetch failure with a stale entry present, the stale value is
        returned with `CacheState.STALE` rather than raising — degraded but
        labelled beats unavailable. The caller must show the caveat.
        """
        lookup = self.get(key)
        if lookup.hit:
            return (lookup.value, CacheState.FRESH)

        try:
            value = await fetch()
        except Exception:
            if allow_stale_on_error and lookup.has_value:
                return (lookup.value, CacheState.STALE)
            raise

        self.put(key, value, source_name, policy=policy, ttl=ttl)
        return (value, CacheState.MISS)
