"""Normalization: source-shaped records into canonical models.

Stage three of the pipeline (see docs/PERSON4_DATA_ARCHITECTURE.md §2). Takes a
`SourceRecord` — provider field names, provider units — and produces a canonical
model with SI-convertible `Quantity` values, UTC epochs, explicit frame context
and attached provenance.

Normalizers never fetch. They are pure functions of `(SourceRecord) -> model`,
which is what makes them testable against recorded fixtures.
"""

from .parsing import (
    arcsec_to_degrees,
    clean_text,
    datetime_to_julian_date,
    first_present,
    julian_date_to_datetime,
    make_quantity,
    modified_julian_date_to_datetime,
    parse_bool,
    parse_date,
    parse_datetime,
    parse_float,
    parse_int,
)

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
