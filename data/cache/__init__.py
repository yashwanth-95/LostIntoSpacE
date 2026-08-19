"""Freshness-aware caching.

A cache hit is not automatically an answer: an entry past its source's
freshness policy is available but not current, and `CacheLookup` reports which.
"""

from .store import (
    CacheEntry,
    CacheLookup,
    CacheState,
    CacheStats,
    FreshnessAwareCache,
)

__all__ = [
    "FreshnessAwareCache",
    "CacheEntry",
    "CacheLookup",
    "CacheState",
    "CacheStats",
]
