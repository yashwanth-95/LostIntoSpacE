"""Small constructors shared by the catalog content modules.

These exist to keep the content files readable. A catalog entry should look
like a record of facts, not like Pydantic boilerplate, because the facts are
the part that has to be checked.
"""

from datetime import datetime, timezone
from typing import Optional

from contracts.provenance import SourceReference, SourceType

from .models import Property

__all__ = ["NASA_FACTSHEET", "JPL_SSD", "BUNDLED", "prop", "text_prop"]

_RETRIEVED = datetime(2026, 8, 20, tzinfo=timezone.utc)

#: NASA's planetary fact sheets — the standard reference for bulk parameters.
NASA_FACTSHEET = SourceReference(
    source_name="NASA Planetary Fact Sheet",
    source_type=SourceType.BUNDLED_REFERENCE,
    source_url="https://nssdc.gsfc.nasa.gov/planetary/factsheet/",
    retrieved_at=_RETRIEVED,
    attribution="NASA Goddard Space Flight Center, National Space Science Data Center",
)

#: JPL Solar System Dynamics — orbital elements and small-body parameters.
JPL_SSD = SourceReference(
    source_name="JPL Solar System Dynamics",
    source_type=SourceType.BUNDLED_REFERENCE,
    source_url="https://ssd.jpl.nasa.gov/",
    retrieved_at=_RETRIEVED,
    attribution="NASA Jet Propulsion Laboratory, California Institute of Technology",
)

#: Curated editorial content written for this platform.
BUNDLED = SourceReference(
    source_name="bundled_reference",
    source_type=SourceType.BUNDLED_REFERENCE,
    retrieved_at=_RETRIEVED,
    attribution="Curated reference data bundled with LostIntoSpacE",
)


def prop(
    label: str,
    value: float,
    unit: Optional[str] = None,
    precision: Optional[int] = None,
    note: Optional[str] = None,
    earth_ratio: Optional[float] = None,
) -> Property:
    """A numeric property."""
    return Property(
        label=label,
        value=value,
        unit=unit,
        precision=precision,
        note=note,
        earth_ratio=earth_ratio,
    )


def text_prop(label: str, display: str, note: Optional[str] = None) -> Property:
    """A property whose value is genuinely not one number."""
    return Property(label=label, display=display, note=note)
