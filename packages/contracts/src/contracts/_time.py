"""Shared time helpers for contract types.

Rule: every timestamp crossing a contract boundary is timezone-aware UTC.
External APIs frequently emit naive ISO strings; those are interpreted as UTC
rather than rejected, because rejecting them would discard otherwise-good
scientific records. The assumption is documented so it is auditable.
"""

from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Coerce a datetime to timezone-aware UTC.

    Naive datetimes are assumed to already be UTC.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
