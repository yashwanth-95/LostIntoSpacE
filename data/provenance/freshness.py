"""Freshness policy and assessment.

Two separate ideas, deliberately not conflated:

* **`SourceCategory`** describes a *source*: how often the publisher updates it.
  CelesTrak GP is `NEAR_REAL_TIME` because it refreshes every two hours.
* **`FreshnessClass`** describes a *record*: how old this particular record's
  content is right now. A `NEAR_REAL_TIME` source routinely yields `HISTORICAL`
  records — an element set whose epoch is three days old is three days old no
  matter how modern the feed that served it.

The two project rules this module enforces:

1. Never call a historical orbital element "current".
2. Never call cached data "live" unless its freshness policy allows it.

Both are expressed as `FreshnessAssessment.may_present_as_live`, which callers
must consult before using words like "current", "live" or "now" about a record.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts._time import as_utc, utc_now
from contracts.provenance import FreshnessClass

__all__ = [
    "SourceCategory",
    "FreshnessPolicy",
    "FreshnessAssessment",
    "assess_freshness",
    "apply_freshness",
    "POLICIES",
    "policy_for",
]


class SourceCategory(str, Enum):
    """How often a *source* publishes new data."""

    REAL_TIME = "REAL_TIME"
    NEAR_REAL_TIME = "NEAR_REAL_TIME"
    DAILY = "DAILY"
    PERIODIC = "PERIODIC"
    STATIC_REFERENCE = "STATIC_REFERENCE"


class FreshnessPolicy(BaseModel):
    """Per-source rules for caching, staleness and what may be called live."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_category: SourceCategory

    #: Publisher's own update cadence, when documented. CelesTrak GP is 2 hours.
    update_interval: Optional[timedelta] = None
    #: How old a record's content may be before it is stale. `None` means the
    #: content does not go stale (static reference values).
    max_age: Optional[timedelta] = None

    cacheable: bool = True
    #: How long a fetched response may be reused. Should not exceed
    #: `update_interval` — re-fetching sooner than the publisher updates wastes
    #: their bandwidth and ours.
    cache_ttl: Optional[timedelta] = None

    #: Whether a record from this source may ever be described as live/current.
    #: False for archives: a JPL orbit solution is authoritative but not "live".
    allows_live_presentation: bool = False

    # -- record classification thresholds ---------------------------------
    real_time_within: timedelta = timedelta(minutes=5)
    near_real_time_within: timedelta = timedelta(hours=6)
    recent_within: timedelta = timedelta(days=30)

    #: Human-readable note shown in docs and API responses.
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _check(self) -> "FreshnessPolicy":
        if not self.cacheable and self.cache_ttl is not None:
            raise ValueError("cache_ttl is meaningless when cacheable is False")
        if self.cache_ttl is not None and self.cache_ttl.total_seconds() < 0:
            raise ValueError("cache_ttl must not be negative")
        if self.source_category is SourceCategory.STATIC_REFERENCE:
            if self.allows_live_presentation:
                raise ValueError(
                    "a STATIC_REFERENCE source can never be presented as live data"
                )
        ordered = (self.real_time_within, self.near_real_time_within, self.recent_within)
        if not (ordered[0] <= ordered[1] <= ordered[2]):
            raise ValueError(
                "freshness thresholds must satisfy real_time <= near_real_time <= recent"
            )
        return self

    def expiry_for(self, retrieved_at: Optional[datetime]) -> Optional[datetime]:
        """When a response fetched at `retrieved_at` stops being reusable."""
        anchor = as_utc(retrieved_at)
        if anchor is None or self.cache_ttl is None or not self.cacheable:
            return None
        return anchor + self.cache_ttl


class FreshnessAssessment(BaseModel):
    """The result of judging one record against its source's policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    freshness_class: FreshnessClass
    #: Age of the record's *content* (from `temporal_anchor`).
    content_age: Optional[timedelta] = None
    #: Age of our *copy* (from `retrieved_at`).
    retrieval_age: Optional[timedelta] = None
    #: True when the content is older than the policy's `max_age`.
    is_stale: bool = False
    #: True when our cached copy is past its TTL and should be re-fetched.
    is_cache_expired: bool = False
    expires_at: Optional[datetime] = None
    #: The gate on words like "current", "live" and "now".
    may_present_as_live: bool = False
    #: Why the assessment came out this way. Surfaced to users and to the AI
    #: layer so an explanation can state the caveat rather than hide it.
    reason: str = ""
    assessed_at: datetime = Field(default_factory=utc_now)

    def describe(self) -> str:
        """One-line, user-facing statement of how current this record is."""
        label = self.freshness_class.value.replace("_", " ").lower()
        if self.is_stale:
            return "stale ({0}): {1}".format(label, self.reason)
        return "{0}: {1}".format(label, self.reason)


def _classify(content_age: Optional[timedelta], policy: FreshnessPolicy) -> FreshnessClass:
    if policy.source_category is SourceCategory.STATIC_REFERENCE:
        return FreshnessClass.STATIC
    if content_age is None:
        # No anchor to judge against. Refusing to guess is the safe answer:
        # HISTORICAL prevents anything downstream calling it current.
        return FreshnessClass.HISTORICAL
    if content_age <= policy.real_time_within:
        return FreshnessClass.REAL_TIME
    if content_age <= policy.near_real_time_within:
        return FreshnessClass.NEAR_REAL_TIME
    if content_age <= policy.recent_within:
        return FreshnessClass.RECENT
    return FreshnessClass.HISTORICAL


def assess_freshness(
    policy: FreshnessPolicy,
    retrieved_at: Optional[datetime] = None,
    valid_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> FreshnessAssessment:
    """Judge one record's currency.

    `valid_at` is the record's content anchor (orbit epoch, observation time);
    `retrieved_at` is when we fetched it. Both matter: fresh retrieval of stale
    content is still stale content.
    """
    moment = as_utc(now) or utc_now()
    retrieved = as_utc(retrieved_at)
    anchor = as_utc(valid_at)

    content_age = None if anchor is None else moment - anchor
    retrieval_age = None if retrieved is None else moment - retrieved

    freshness_class = _classify(content_age, policy)

    is_stale = False
    if policy.max_age is not None:
        if content_age is None:
            is_stale = True
        elif content_age > policy.max_age:
            is_stale = True

    expires_at = policy.expiry_for(retrieved)
    is_cache_expired = expires_at is not None and moment > expires_at

    reasons = []
    may_present_as_live = policy.allows_live_presentation

    if not policy.allows_live_presentation:
        reasons.append(
            "source category {0} is not a live feed".format(policy.source_category.value)
        )
    if freshness_class in (FreshnessClass.HISTORICAL, FreshnessClass.STATIC):
        if may_present_as_live:
            reasons.append(
                "record content is {0}, so it is not current".format(
                    freshness_class.value.lower()
                )
            )
        may_present_as_live = False
    if is_stale:
        if may_present_as_live:
            reasons.append("content is older than the policy's maximum age")
        may_present_as_live = False
    if is_cache_expired:
        if may_present_as_live:
            reasons.append("cached copy is past its TTL and needs re-fetching")
        may_present_as_live = False

    if may_present_as_live:
        reasons.append(
            "within the {0} freshness window for a {1} source".format(
                freshness_class.value.lower(), policy.source_category.value
            )
        )
    if content_age is None and anchor is None:
        reasons.append("record has no epoch, so its currency cannot be established")

    return FreshnessAssessment(
        freshness_class=freshness_class,
        content_age=content_age,
        retrieval_age=retrieval_age,
        is_stale=is_stale,
        is_cache_expired=is_cache_expired,
        expires_at=expires_at,
        may_present_as_live=may_present_as_live,
        reason="; ".join(reasons) if reasons else "no constraints applied",
        assessed_at=moment,
    )


def apply_freshness(record, policy: FreshnessPolicy, now: Optional[datetime] = None):
    """Assess `record` and write the result onto it.

    Sets `freshness_class` and `expires_at`, and returns the assessment so the
    caller can act on `may_present_as_live`. Adapters never set these fields
    themselves — an adapter knows its source's cadence, not a record's age.
    """
    assessment = assess_freshness(
        policy=policy,
        retrieved_at=record.retrieved_at,
        valid_at=record.temporal_anchor(),
        now=now,
    )
    record.freshness_class = assessment.freshness_class
    if assessment.expires_at is not None:
        record.expires_at = assessment.expires_at
    return assessment


#: Default policy per source, keyed by `SourceReference.source_name`.
#:
#: Cadences reflect each provider's published guidance; see
#: docs/PERSON4_DATA_ARCHITECTURE.md §4. Adapters may override their own entry,
#: but nothing may present data as live unless its policy says so.
POLICIES = {
    "celestrak_gp": FreshnessPolicy(
        source_category=SourceCategory.NEAR_REAL_TIME,
        update_interval=timedelta(hours=2),
        max_age=timedelta(days=3),
        cache_ttl=timedelta(hours=2),
        allows_live_presentation=True,
        near_real_time_within=timedelta(hours=6),
        recent_within=timedelta(days=3),
        notes=(
            "CelesTrak guidance: GP data updates every two hours; retrieve only what "
            "is needed and only once per update. Operational feed, not a science archive."
        ),
    ),
    "nasa_eonet": FreshnessPolicy(
        source_category=SourceCategory.NEAR_REAL_TIME,
        update_interval=timedelta(hours=1),
        max_age=timedelta(days=30),
        cache_ttl=timedelta(hours=1),
        allows_live_presentation=True,
        notes="Natural-event feed; events remain open for days, so RECENT is normal.",
    ),
    "nasa_neows": FreshnessPolicy(
        source_category=SourceCategory.DAILY,
        update_interval=timedelta(days=1),
        max_age=timedelta(days=7),
        cache_ttl=timedelta(hours=12),
        notes="Close-approach summaries; derived from JPL, not a substitute for it.",
    ),
    "nasa_apod": FreshnessPolicy(
        source_category=SourceCategory.DAILY,
        update_interval=timedelta(days=1),
        cache_ttl=timedelta(hours=12),
        notes="One image per day; yesterday's is not wrong, just not today's.",
    ),
    "jpl_horizons": FreshnessPolicy(
        source_category=SourceCategory.PERIODIC,
        max_age=None,
        cache_ttl=timedelta(days=1),
        notes=(
            "Computed on request from a published ephemeris. The result is exact for "
            "the epoch requested and does not become 'stale', but it is never 'live'."
        ),
    ),
    "jpl_sbdb": FreshnessPolicy(
        source_category=SourceCategory.PERIODIC,
        update_interval=timedelta(days=1),
        max_age=timedelta(days=180),
        cache_ttl=timedelta(days=1),
        notes="Orbit solutions change when new observations arrive.",
    ),
    "mpc_orbits": FreshnessPolicy(
        source_category=SourceCategory.DAILY,
        update_interval=timedelta(days=1),
        max_age=timedelta(days=180),
        cache_ttl=timedelta(days=1),
    ),
    "mpc_observations": FreshnessPolicy(
        source_category=SourceCategory.DAILY,
        update_interval=timedelta(days=1),
        #: An observation never goes stale — it happened at a fixed time.
        max_age=None,
        cache_ttl=timedelta(days=7),
        notes="Observations are historical measurements by nature.",
    ),
    "nasa_exoplanet_archive": FreshnessPolicy(
        source_category=SourceCategory.PERIODIC,
        update_interval=timedelta(days=7),
        max_age=timedelta(days=365),
        cache_ttl=timedelta(days=7),
        notes="Weekly-ish releases; parameters are revised as papers are published.",
    ),
    "nasa_ntrs": FreshnessPolicy(
        source_category=SourceCategory.PERIODIC,
        cache_ttl=timedelta(days=30),
        notes="Document metadata; a 1969 report does not become stale.",
    ),
    "esa_copernicus": FreshnessPolicy(
        source_category=SourceCategory.DAILY,
        update_interval=timedelta(days=1),
        cache_ttl=timedelta(hours=6),
        notes="Product catalogue metadata, not the products themselves.",
    ),
    "isro_bhoonidhi": FreshnessPolicy(
        source_category=SourceCategory.DAILY,
        update_interval=timedelta(days=1),
        cache_ttl=timedelta(hours=6),
        notes="Access is authorization-gated; see docs/PROVENANCE.md.",
    ),
    "bundled_reference": FreshnessPolicy(
        source_category=SourceCategory.STATIC_REFERENCE,
        max_age=None,
        cache_ttl=None,
        allows_live_presentation=False,
        notes="Offline fallback tier. Never presented as live, by definition.",
    ),
}

#: Used when a source has no registered policy. Conservative on purpose: an
#: unregistered source can never be presented as live.
DEFAULT_POLICY = FreshnessPolicy(
    source_category=SourceCategory.PERIODIC,
    cache_ttl=timedelta(hours=1),
    allows_live_presentation=False,
    notes="Fallback policy for a source with no registered freshness rules.",
)


def policy_for(source_name: str) -> FreshnessPolicy:
    """Look up a source's policy, falling back to the conservative default."""
    return POLICIES.get(source_name, DEFAULT_POLICY)
