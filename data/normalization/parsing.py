"""Shared parsing helpers for source adapters.

Every adapter needs the same handful of defensive conversions: a number that
might be a string or might be absent, a date in one of a dozen formats, a
Julian date, a value that should become a `Quantity` only if it is actually
present. Doing this once means a single source's odd formatting cannot produce a
subtly different result from another's.

All of these return `None` rather than raising on absent input. Absent data must
stay absent — coercing it to zero is how a missing mass becomes a massless body.
"""

import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from contracts.provenance import SourceReference

from ..models.units import Quantity

__all__ = [
    "parse_float",
    "parse_int",
    "parse_bool",
    "parse_datetime",
    "parse_date",
    "julian_date_to_datetime",
    "datetime_to_julian_date",
    "modified_julian_date_to_datetime",
    "arcsec_to_degrees",
    "make_quantity",
    "first_present",
    "clean_text",
]

#: Values several archives use to mean "no value". Treated as absent.
_NULL_TOKENS = {"", "n/a", "na", "null", "none", "nan", "-", "--", "unknown", "?"}

_ISO_LIKE = (
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y-%b-%d %H:%M:%S.%f",
    "%Y-%b-%d %H:%M:%S",
    "%Y-%b-%d %H:%M",
    "%Y-%b-%d",
    "%Y/%m/%d",
    "%Y",
)

#: Unix epoch as a Julian Date, for JD <-> datetime conversion.
_JD_UNIX_EPOCH = 2440587.5


def clean_text(value: Any) -> Optional[str]:
    """Collapse whitespace and map null-ish tokens to `None`."""
    if value is None:
        return None
    text = " ".join(str(value).split())
    if text.lower() in _NULL_TOKENS:
        return None
    return text or None


def parse_float(value: Any) -> Optional[float]:
    """Parse a float that may arrive as a string, or be absent.

    Non-finite results are treated as absent: an archive that emits `NaN` is
    saying it has no value, and a `Quantity` would reject it anyway.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = clean_text(value)
        if text is None:
            return None
        # Some archives use Fortran-style exponents ("1.5D-3").
        text = text.replace("D", "E").replace("d", "e")
        try:
            number = float(text)
        except ValueError:
            return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def parse_int(value: Any) -> Optional[int]:
    number = parse_float(value)
    return None if number is None else int(number)


def parse_bool(value: Any) -> Optional[bool]:
    """Parse a boolean that may arrive as a string, `Y`/`N`, or `0`/`1`."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = clean_text(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in ("true", "yes", "y", "1"):
        return True
    if lowered in ("false", "no", "n", "0"):
        return False
    return None


def parse_datetime(value: Any) -> Optional[datetime]:
    """Parse a timestamp into timezone-aware UTC.

    Handles ISO-8601 with and without a zone, `Z` suffixes, sub-second
    precision beyond microseconds (NTRS emits 7 digits), and `YYYY-Mon-DD`
    forms used by JPL.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        # Epoch milliseconds are common in NASA JSON payloads.
        seconds = float(value)
        if abs(seconds) > 1e11:
            seconds /= 1000.0
        return datetime.fromtimestamp(seconds, tz=timezone.utc)

    text = clean_text(value)
    if text is None:
        return None
    text = text.replace("Z", "+00:00")
    # Trim sub-second precision to microseconds; %f accepts at most 6 digits.
    text = re.sub(r"(\.\d{6})\d+", r"\1", text)
    # Normalize "+00:00" to "+0000" for %z on Python 3.9's stricter parsers.
    normalized = re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", text)

    for candidate in (normalized, text):
        for pattern in _ISO_LIKE:
            try:
                parsed = datetime.strptime(candidate, pattern)
            except ValueError:
                continue
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_date(value: Any) -> Optional[date]:
    parsed = parse_datetime(value)
    return None if parsed is None else parsed.date()


def julian_date_to_datetime(jd: Any) -> Optional[datetime]:
    """Convert a Julian Date to a UTC datetime.

    Note the time scale is *not* converted: a JD in TDB stays a TDB instant,
    rendered as a datetime. The record's `TimeScale` field records which it is.
    """
    value = parse_float(jd)
    if value is None:
        return None
    seconds = (value - _JD_UNIX_EPOCH) * 86400.0
    try:
        return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    except (OverflowError, OSError, ValueError):
        return None


def datetime_to_julian_date(moment: Optional[datetime]) -> Optional[float]:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    delta = moment.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return _JD_UNIX_EPOCH + delta.total_seconds() / 86400.0


#: MJD = JD - 2400000.5, the offset the MPC uses for its epochs.
_MJD_OFFSET = 2400000.5


def modified_julian_date_to_datetime(mjd: Any) -> Optional[datetime]:
    """Convert a Modified Julian Date to a datetime.

    As with `julian_date_to_datetime`, the *time scale* is not converted. An
    MPC epoch in TDT stays a TDT instant; the record's `TimeScale` says so.
    """
    value = parse_float(mjd)
    if value is None:
        return None
    return julian_date_to_datetime(value + _MJD_OFFSET)


def arcsec_to_degrees(value: Any) -> Optional[float]:
    """Convert an arcsecond figure to degrees.

    Astrometric uncertainties are published in arcseconds while the positions
    themselves are in degrees; a `Quantity`'s uncertainty must share the unit of
    its value, so the conversion has to happen at parse time.
    """
    number = parse_float(value)
    return None if number is None else number / 3600.0


def make_quantity(
    value: Any,
    unit: str,
    uncertainty: Any = None,
    uncertainty_lower: Any = None,
    uncertainty_upper: Any = None,
    source: Optional[SourceReference] = None,
) -> Optional[Quantity]:
    """Build a `Quantity`, or `None` when the value is absent.

    Uncertainties are attached only when they parse; a source that publishes a
    value without an error bar produces a quantity without one, never a
    fabricated zero.
    """
    number = parse_float(value)
    if number is None:
        return None
    sigma = parse_float(uncertainty)
    lower = parse_float(uncertainty_lower)
    upper = parse_float(uncertainty_upper)

    # Archives publish asymmetric bars with a sign on the lower bound.
    if lower is not None:
        lower = abs(lower)
    if upper is not None:
        upper = abs(upper)
    if sigma is not None:
        sigma = abs(sigma)
        lower = upper = None

    return Quantity(
        value=number,
        unit=unit,
        uncertainty=sigma,
        uncertainty_lower=lower,
        uncertainty_upper=upper,
        source=source,
    )


def first_present(payload: dict, *keys: str) -> Any:
    """Return the first key present and non-null in `payload`.

    Archives rename fields between releases; listing the aliases in one call
    keeps the parser readable and makes the rename history visible.
    """
    for key in keys:
        if key in payload:
            value = payload[key]
            if value is not None and clean_text(value) is not None:
                return value
    return None
