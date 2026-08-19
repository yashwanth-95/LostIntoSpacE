"""Entity resolution: deciding when two source records describe one thing.

Three archives can describe Ceres as `1`, `A801 AA` and `20000001`. Without
resolution the catalogue holds three objects; with naive resolution it merges
things that only look alike. This module errs toward *not* merging: a merge that
should not have happened is much harder to detect later than a duplicate.
"""

from .resolver import (
    EntityResolver,
    IdentityKey,
    MergeDecision,
    ResolutionOutcome,
    normalize_designation,
)

__all__ = [
    "EntityResolver",
    "IdentityKey",
    "MergeDecision",
    "ResolutionOutcome",
    "normalize_designation",
]
