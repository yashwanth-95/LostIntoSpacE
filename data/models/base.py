"""Base record types shared by every canonical model.

`CanonicalRecord` carries the fields that make a record auditable: a stable
identity, where it came from, when it was retrieved, and how much we trust it.
Everything else in `data/models/` builds on it.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from contracts._time import as_utc, utc_now
from contracts.provenance import FreshnessClass, SourceReference, SourceType

from .enums import DataStatus
from .units import Dimension, Quantity, UnitError

__all__ = [
    "CanonicalRecord",
    "NamedRecord",
    "CANONICAL_ID_PATTERN",
    "make_canonical_id",
    "slugify",
    "require_dimensions",
]

CANONICAL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:+/-]*$")

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase, hyphen-separated slug suitable for a canonical id segment.

    ``"2000 SG344"`` -> ``"2000-sg344"``, ``"C/2019 Y4 (ATLAS)"`` -> ``"c-2019-y4-atlas"``.
    """
    slug = _SLUG_STRIP.sub("-", str(text).strip().lower()).strip("-")
    if not slug:
        raise ValueError("cannot slugify {0!r}: no alphanumeric content".format(text))
    return slug


def make_canonical_id(namespace: str, identifier: str) -> str:
    """Build a ``namespace:slug`` canonical id.

    The namespace names the *kind* of thing, not the source that supplied it —
    two archives describing Ceres must produce the same canonical id, which is
    what lets entity resolution merge them.
    """
    return "{0}:{1}".format(slugify(namespace), slugify(identifier))


def require_dimensions(model: BaseModel, expected: Dict[str, Dimension]) -> None:
    """Validate that named `Quantity` fields carry the expected dimension.

    This is the check that turns "radius in kilograms" from a plausible-looking
    record into a hard validation failure at ingestion time.
    """
    problems = []
    for field_name, dimension in expected.items():
        value = getattr(model, field_name, None)
        if value is None:
            continue
        quantities: Sequence[Quantity]
        if isinstance(value, Quantity):
            quantities = (value,)
        elif isinstance(value, (list, tuple)):
            quantities = [item for item in value if isinstance(item, Quantity)]
        else:
            continue
        for quantity in quantities:
            try:
                actual = quantity.dimension
            except UnitError as exc:  # pragma: no cover - unit validated on construction
                problems.append("{0}: {1}".format(field_name, exc))
                continue
            if actual is not dimension:
                problems.append(
                    "{0} must be {1}, got {2} (unit {3!r})".format(
                        field_name, dimension.value, actual.value, quantity.unit
                    )
                )
    if problems:
        raise ValueError("; ".join(problems))


class CanonicalRecord(BaseModel):
    """Common identity, provenance and freshness fields.

    Subclasses add domain content. No subclass may redeclare these fields.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    #: Stable project-wide identifier, ``namespace:slug`` (see `make_canonical_id`).
    canonical_id: str
    #: Discriminator matching the concrete class, so serialized records round-trip.
    record_type: str = "canonical_record"

    #: Every source that contributed to this record. Empty means missing
    #: provenance, which the quality engine reports as an error.
    source_references: List[SourceReference] = Field(default_factory=list)

    #: 0..1 aggregate trust in this record. `None` means "not assessed" and is
    #: deliberately distinct from 0.0 ("assessed as untrustworthy").
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    #: Short human-readable justification for `confidence`.
    confidence_basis: Optional[str] = None

    data_status: DataStatus = DataStatus.UNKNOWN

    #: When this project fetched the underlying data.
    retrieved_at: Optional[datetime] = None
    #: When the source last changed the data, if the source reports it.
    source_updated_at: Optional[datetime] = None
    #: When this project last confirmed the record still matches the source.
    last_verified_at: Optional[datetime] = None

    #: The instant the record's *content* describes — an orbit epoch, an
    #: observation time, an event onset. Distinct from `retrieved_at`: a record
    #: fetched a second ago can describe a state from three days ago.
    #: Subclasses with a domain-specific anchor override `temporal_anchor()`.
    valid_at: Optional[datetime] = None
    #: When this record should no longer be served without re-fetching.
    #: Set from the source's `FreshnessPolicy`; `None` means "does not expire".
    expires_at: Optional[datetime] = None
    #: How current this record is. Assigned by `data.provenance.freshness`, not
    #: by adapters — an adapter knows its source's cadence, not the record's age.
    freshness_class: Optional[FreshnessClass] = None

    #: Source-specific fields worth keeping but not part of the canonical shape.
    #: Preserved verbatim so nothing scientifically meaningful is discarded.
    source_specific: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("canonical_id")
    @classmethod
    def _validate_canonical_id(cls, value: str) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError("canonical_id must not be empty")
        if not CANONICAL_ID_PATTERN.match(text):
            raise ValueError(
                "canonical_id {0!r} must be lowercase and contain no whitespace "
                "(expected form 'namespace:slug')".format(value)
            )
        return text

    @field_validator(
        "retrieved_at", "source_updated_at", "last_verified_at", "valid_at", "expires_at"
    )
    @classmethod
    def _normalize_times(cls, value: Optional[datetime]) -> Optional[datetime]:
        return as_utc(value)

    def temporal_anchor(self) -> Optional[datetime]:
        """The instant this record's content describes.

        Overridden by record types that carry a domain-specific anchor
        (`OrbitRecord.epoch`, `Observation.observed_at`). Freshness is assessed
        against this, never against `retrieved_at` alone.
        """
        return self.valid_at

    # -- provenance helpers ------------------------------------------------
    @property
    def has_provenance(self) -> bool:
        return len(self.source_references) > 0

    @property
    def primary_source(self) -> Optional[SourceReference]:
        """The highest-authority source reference, or `None`.

        Ordering favours scientific archives over operational feeds and
        anything published over anything we calculated ourselves.
        """
        if not self.source_references:
            return None
        rank = {
            SourceType.PRIMARY_SCIENTIFIC: 0,
            SourceType.LITERATURE: 1,
            SourceType.AGENCY_PUBLIC_API: 2,
            SourceType.EO_CATALOGUE: 3,
            SourceType.SECONDARY_OPERATIONAL: 4,
            SourceType.BUNDLED_REFERENCE: 5,
            SourceType.EDITORIAL: 6,
            SourceType.CALCULATED: 7,
            SourceType.UNKNOWN: 8,
        }
        return sorted(
            self.source_references,
            key=lambda ref: (rank.get(ref.source_type, 9), -ref.retrieved_at.timestamp()),
        )[0]

    def add_source(self, reference: SourceReference) -> None:
        """Append a source reference, ignoring exact duplicates."""
        if reference not in self.source_references:
            self.source_references = list(self.source_references) + [reference]

    def source_names(self) -> List[str]:
        seen = []
        for ref in self.source_references:
            if ref.source_name not in seen:
                seen.append(ref.source_name)
        return seen

    def attribution_lines(self) -> List[str]:
        """Credit strings to display wherever this record is shown."""
        lines = []
        for ref in self.source_references:
            credit = ref.display_credit()
            if credit not in lines:
                lines.append(credit)
        return lines

    def mark_verified(self, when: Optional[datetime] = None) -> None:
        self.last_verified_at = as_utc(when) or utc_now()


class NamedRecord(CanonicalRecord):
    """A canonical record that has a human-facing name and aliases."""

    name: str = Field(min_length=1)
    #: Alternative names and designations. Search matches these, and entity
    #: resolution uses them to link records across archives.
    aliases: List[str] = Field(default_factory=list)
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        text = " ".join(str(value).split())
        if not text:
            raise ValueError("name must not be blank")
        return text

    @field_validator("aliases")
    @classmethod
    def _clean_aliases(cls, value: List[str]) -> List[str]:
        cleaned: List[str] = []
        seen = set()
        for alias in value or []:
            text = " ".join(str(alias).split())
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
        return cleaned

    def all_names(self) -> List[str]:
        """Name plus aliases, de-duplicated case-insensitively."""
        names = [self.name]
        lowered = {self.name.lower()}
        for alias in self.aliases:
            if alias.lower() not in lowered:
                lowered.add(alias.lower())
                names.append(alias)
        return names
