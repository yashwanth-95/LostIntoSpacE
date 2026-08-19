"""Provenance contracts — shared across backend, search, AI and frontend.

This is the single definition of `SourceReference` for the whole project.
`data/models/` and `ai/` import it from here rather than redeclaring it, per the
`packages/contracts/` single-source-of-truth rule.

Architecture principle #4 (Data Provenance): every data point traces to its
source. A canonical record with no `SourceReference` is a validation error, not
a warning.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._time import as_utc, utc_now

__all__ = [
    "SourceType",
    "FreshnessClass",
    "SourceReference",
    "REDACTION_MARKER",
]

#: Placeholder a redacted credential value is replaced with. Shared with
#: `data.sources.http` so redaction and validation cannot disagree.
REDACTION_MARKER = "***REDACTED***"


class SourceType(str, Enum):
    """What kind of authority a source is.

    This drives conflict resolution in the data-quality engine: a
    `PRIMARY_SCIENTIFIC` value outranks a `SECONDARY_OPERATIONAL` one for the
    same field, and `DERIVED`/`CALCULATED` values never outrank measurements.
    """

    #: Authoritative scientific archive (JPL, MPC, NASA Exoplanet Archive).
    PRIMARY_SCIENTIFIC = "PRIMARY_SCIENTIFIC"
    #: Operational feed useful for "current" state but not a science archive.
    #: CelesTrak GP/OMM element sets are exactly this.
    SECONDARY_OPERATIONAL = "SECONDARY_OPERATIONAL"
    #: Agency public/outreach API (APOD, rover photos, EONET events).
    AGENCY_PUBLIC_API = "AGENCY_PUBLIC_API"
    #: Document/literature metadata (NASA NTRS).
    LITERATURE = "LITERATURE"
    #: Earth-observation product catalogue (Copernicus, Bhoonidhi).
    EO_CATALOGUE = "EO_CATALOGUE"
    #: Curated reference values shipped with the app (offline demo tier).
    BUNDLED_REFERENCE = "BUNDLED_REFERENCE"
    #: Computed by this project from other records. Never authoritative.
    CALCULATED = "CALCULATED"
    #: Output of the educational simulator (P3's engine).
    #:
    #: Its own type rather than a flavour of `CALCULATED`, because the two need
    #: different treatment: a calculated value is a real quantity derived from
    #: measurements, while a simulator result is a statement about a model. It
    #: must never be presented as a real-world observation, and the AI layer
    #: labels every claim resting on it as `ClaimType.SIMULATION`.
    SIMULATION = "SIMULATION"
    #: Human-authored educational content.
    EDITORIAL = "EDITORIAL"
    #: Data supplied by the user — project notes, configurations, uploads.
    #: Untrusted input: never an authority, and always sanitized before it
    #: reaches a model.
    USER_PROVIDED = "USER_PROVIDED"
    #: Provenance known to be incomplete. Flagged by the quality engine.
    UNKNOWN = "UNKNOWN"


class FreshnessClass(str, Enum):
    """How current a *record* is — not how current its source could be.

    A `NEAR_REAL_TIME` source can still yield a `HISTORICAL` record when the
    record's own epoch is old. This distinction is what stops a three-day-old
    element set from being presented as "current".
    """

    REAL_TIME = "REAL_TIME"
    NEAR_REAL_TIME = "NEAR_REAL_TIME"
    RECENT = "RECENT"
    HISTORICAL = "HISTORICAL"
    STATIC = "STATIC"


class SourceReference(BaseModel):
    """Where a single value or record came from.

    Attached to canonical records (`source_references`) and to individual
    physical values (`Quantity.source`) so that a record assembled from three
    archives can still say which archive each number came from.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Stable machine key for the source, e.g. "jpl_sbdb", "mpc_orbits".
    source_name: str = Field(min_length=1)
    source_type: SourceType = SourceType.UNKNOWN
    #: Endpoint or landing page the record came from. Never contains credentials.
    source_url: Optional[str] = None
    #: The source's own identifier for the record (SPK-ID, NORAD ID, DOI...).
    source_record_id: Optional[str] = None
    #: When *we* fetched it.
    retrieved_at: datetime = Field(default_factory=utc_now)
    #: The timestamp the source itself attaches to the record, if any.
    source_timestamp: Optional[datetime] = None
    #: Dataset/API version or release tag when the source publishes one.
    source_version: Optional[str] = None
    license: Optional[str] = None
    #: Human-readable credit string to display alongside the data.
    attribution: Optional[str] = None

    @field_validator("retrieved_at", "source_timestamp")
    @classmethod
    def _normalize_time(cls, value: Optional[datetime]) -> Optional[datetime]:
        return as_utc(value)

    @field_validator("source_url")
    @classmethod
    def _no_credentials_in_url(cls, value: Optional[str]) -> Optional[str]:
        """Guard against leaking an API key into stored provenance.

        Keys arrive as query parameters on several NASA endpoints, so a naive
        `str(request.url)` would persist the secret into the database and into
        API responses. Callers must redact before constructing the reference.
        """
        if value is None:
            return None
        lowered = value.lower()
        for marker in ("api_key=", "apikey=", "token=", "password=", "&key=", "?key="):
            index = lowered.find(marker)
            if index == -1:
                continue
            # An already-redacted URL keeps the parameter name so readers can
            # see a credential was sent; only an actual value is a leak.
            tail = value[index + len(marker):]
            if tail.startswith(REDACTION_MARKER):
                continue
            raise ValueError(
                "source_url appears to contain a credential; redact it before "
                "building a SourceReference"
            )
        return value

    @property
    def age(self) -> timedelta:
        """How long ago this reference was retrieved."""
        return utc_now() - self.retrieved_at

    def display_credit(self) -> str:
        """Best available human-readable credit line."""
        if self.attribution:
            return self.attribution
        if self.license:
            return "{0} ({1})".format(self.source_name, self.license)
        return self.source_name
