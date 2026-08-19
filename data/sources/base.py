"""The `SpaceDataSource` interface.

Every external provider is reached through this one interface, so ingestion,
search and the AI layer never contain provider-specific branching. Adapters
differ in what they *can* do, which is declared through `Capability` rather than
discovered by calling a method and seeing what happens.

Capabilities:

* `get_source_info` — what this source is, what it holds, how it is limited
* `search`          — find records matching a query
* `fetch`           — retrieve a raw payload for an arbitrary request
* `fetch_by_id`     — retrieve one record by the source's own identifier
* `health_check`    — is the provider reachable and behaving

Adapters implement only what their provider genuinely offers. Anything else
raises `UnsupportedOperationError` rather than returning an empty list, so a
caller asking the wrong provider gets told, not silently misled.
"""

import abc
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts._time import utc_now
from contracts.provenance import SourceReference, SourceType

from ..provenance.freshness import FreshnessPolicy, policy_for
from .config import ProviderConfig
from .errors import UnsupportedOperationError
from .http import HttpClient, RawResponse

__all__ = [
    "Capability",
    "SourceInfo",
    "SourceQuery",
    "SourceRecord",
    "SourceResultPage",
    "HealthStatus",
    "SpaceDataSource",
]


class Capability(str, Enum):
    """What a source can actually provide.

    Declared per adapter and checked before dispatch, so the ingestion layer can
    route a request for orbital elements only to sources that have them.
    """

    SEARCH = "SEARCH"
    FETCH_BY_ID = "FETCH_BY_ID"
    #: Physical parameters of bodies (mass, radius, albedo...).
    PHYSICAL_PARAMETERS = "PHYSICAL_PARAMETERS"
    #: Fitted orbital element sets.
    ORBITAL_ELEMENTS = "ORBITAL_ELEMENTS"
    #: Computed state vectors / ephemerides.
    EPHEMERIS = "EPHEMERIS"
    #: Individual astrometric or radar observations.
    OBSERVATIONS = "OBSERVATIONS"
    #: Exoplanet and host-star catalogue parameters.
    EXOPLANETS = "EXOPLANETS"
    #: Document / literature metadata.
    DOCUMENTS = "DOCUMENTS"
    #: Natural-event records.
    NATURAL_EVENTS = "NATURAL_EVENTS"
    #: Earth-observation product metadata.
    EO_PRODUCTS = "EO_PRODUCTS"
    #: Imagery / media.
    MEDIA = "MEDIA"
    #: Close-approach data for near-earth objects.
    CLOSE_APPROACHES = "CLOSE_APPROACHES"


class SourceInfo(BaseModel):
    """Static description of a source. Never requires a network call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Matches `SourceReference.source_name`, so provenance and adapters agree.
    name: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    source_type: SourceType
    #: Authority statement. `SECONDARY_OPERATIONAL` sources say so here, in the
    #: words that will be shown to users.
    authority_note: Optional[str] = None
    provider_organization: Optional[str] = None
    base_url: str
    docs_url: Optional[str] = None
    capabilities: List[Capability] = Field(default_factory=list)
    #: What this source is authoritative for, in plain language.
    provides: List[str] = Field(default_factory=list)
    #: What this source must NOT be used for. Prevents forcing unrelated
    #: products into the wrong canonical model.
    does_not_provide: List[str] = Field(default_factory=list)
    license: Optional[str] = None
    attribution: Optional[str] = None
    requires_auth: bool = False
    #: Free-text summary of the provider's published rate-limit policy.
    rate_limit_note: Optional[str] = None
    #: Whether this adapter is wired to a live endpoint yet.
    implemented: bool = False

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities


class SourceQuery(BaseModel):
    """A provider-independent search request.

    Adapters translate the fields they support and ignore the rest; anything an
    adapter cannot honour is reported in `SourceResultPage.unsupported_filters`
    so a caller is never silently given broader results than it asked for.
    """

    model_config = ConfigDict(extra="forbid")

    text: Optional[str] = None
    #: Source-specific identifier, when searching for a known record.
    identifier: Optional[str] = None
    object_type: Optional[str] = None
    #: Inclusive time window on the record's own timestamp.
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(default=25, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    #: Escape hatch for genuinely provider-specific parameters. Values are
    #: validated by the adapter, never passed through blindly.
    extra: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> "SourceQuery":
        if self.start_time and self.end_time and self.start_time > self.end_time:
            raise ValueError("start_time is after end_time")
        if not any((self.text, self.identifier, self.object_type, self.start_time,
                    self.end_time, self.extra)):
            raise ValueError("a SourceQuery needs at least one criterion")
        return self


class SourceRecord(BaseModel):
    """One parsed-but-not-yet-canonical record from a source.

    Sits between the raw response and the canonical model: field names are the
    provider's, values are still in the provider's units. Normalization happens
    downstream, and this stage is what lineage records as `PARSE`.
    """

    model_config = ConfigDict(extra="forbid")

    source_name: str
    #: The provider's own identifier for this record.
    source_record_id: Optional[str] = None
    #: Provider-shaped payload, untouched.
    payload: Dict[str, Any] = Field(default_factory=dict)
    #: Provenance for this specific record.
    source_reference: SourceReference
    retrieved_at: datetime = Field(default_factory=utc_now)


class SourceResultPage(BaseModel):
    """A page of results plus everything needed to page and to audit."""

    model_config = ConfigDict(extra="forbid")

    source_name: str
    records: List[SourceRecord] = Field(default_factory=list)
    #: Total matches the provider reports, when it reports one.
    total_available: Optional[int] = None
    offset: int = 0
    #: Opaque continuation token for providers that use cursors instead.
    next_cursor: Optional[str] = None
    #: Filters the caller asked for that this provider cannot apply. Callers
    #: must post-filter these themselves or narrow their claim about the result.
    unsupported_filters: List[str] = Field(default_factory=list)
    query_echo: Dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime = Field(default_factory=utc_now)

    @property
    def has_more(self) -> bool:
        if self.next_cursor:
            return True
        if self.total_available is None:
            return False
        return (self.offset + len(self.records)) < self.total_available


class HealthStatus(BaseModel):
    """Result of probing a provider."""

    model_config = ConfigDict(extra="forbid")

    source_name: str
    healthy: bool
    #: HTTP status of the probe, when one was made.
    status_code: Optional[int] = None
    latency_seconds: Optional[float] = None
    checked_at: datetime = Field(default_factory=utc_now)
    detail: Optional[str] = None
    #: Quota the provider reported during the probe.
    quota: Dict[str, Any] = Field(default_factory=dict)
    #: True when the check could not run because credentials are absent. This is
    #: distinct from unhealthy: an authorization-gated source without a key is
    #: correctly configured and simply unavailable to us.
    credentials_missing: bool = False


class SpaceDataSource(abc.ABC):
    """Base class for every external space-data adapter.

    Subclasses must implement `get_source_info`. The remaining operations
    default to raising `UnsupportedOperationError`, so an adapter only overrides
    what its provider genuinely supports.
    """

    def __init__(
        self,
        config: Optional[ProviderConfig] = None,
        client: Optional[HttpClient] = None,
        transport=None,
    ):
        self.config = (config or self.default_config()).resolve_from_env()
        self._client = client or HttpClient(self.config, transport=transport)

    # -- configuration -----------------------------------------------------
    @classmethod
    @abc.abstractmethod
    def default_config(cls) -> ProviderConfig:
        """The provider's documented endpoint, limits and retry policy."""

    @abc.abstractmethod
    def get_source_info(self) -> SourceInfo:
        """Static description of this source. Must not make a network call."""

    @property
    def client(self) -> HttpClient:
        return self._client

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def freshness_policy(self) -> FreshnessPolicy:
        """The freshness rules governing records from this source."""
        return policy_for(self.name)

    def supports(self, capability: Capability) -> bool:
        return self.get_source_info().supports(capability)

    def require_capability(self, capability: Capability) -> None:
        """Raise unless this source declares `capability`."""
        if not self.supports(capability):
            info = self.get_source_info()
            raise UnsupportedOperationError(
                "{0} does not provide {1}. It provides: {2}".format(
                    info.display_name,
                    capability.value,
                    ", ".join(c.value for c in info.capabilities) or "nothing yet",
                ),
                source_name=self.name,
            )

    # -- provenance --------------------------------------------------------
    def build_source_reference(
        self,
        response: Optional[RawResponse] = None,
        record_id: Optional[str] = None,
        source_timestamp: Optional[datetime] = None,
        version: Optional[str] = None,
    ) -> SourceReference:
        """Provenance for a record from this source.

        `RawResponse.url` is already redacted, so the reference can never carry
        a credential.
        """
        info = self.get_source_info()
        return SourceReference(
            source_name=info.name,
            source_type=info.source_type,
            source_url=response.url if response is not None else info.base_url,
            source_record_id=record_id,
            retrieved_at=response.retrieved_at if response is not None else utc_now(),
            source_timestamp=source_timestamp,
            source_version=version,
            license=info.license,
            attribution=info.attribution,
        )

    # -- operations --------------------------------------------------------
    async def search(self, query: SourceQuery) -> SourceResultPage:
        """Find records matching `query`."""
        self.require_capability(Capability.SEARCH)
        raise UnsupportedOperationError(
            "{0} declares SEARCH but does not implement it yet".format(self.name),
            source_name=self.name,
        )

    async def fetch(
        self, path: str, params: Optional[Dict[str, Any]] = None, **kwargs
    ) -> RawResponse:
        """Retrieve a raw payload. The escape hatch for provider-specific calls.

        Returns the unparsed response so callers can record it as a fixture and
        so parsing failures stay diagnosable.
        """
        return await self._client.get(path, params=params, **kwargs)

    async def fetch_by_id(self, identifier: str, **kwargs) -> Optional[SourceRecord]:
        """Retrieve one record by the provider's own identifier."""
        self.require_capability(Capability.FETCH_BY_ID)
        raise UnsupportedOperationError(
            "{0} declares FETCH_BY_ID but does not implement it yet".format(self.name),
            source_name=self.name,
        )

    async def health_check(self) -> HealthStatus:
        """Probe the provider.

        The default probe is a cheap GET against the health path the adapter
        declares. Adapters override when their provider needs something else.
        """
        info = self.get_source_info()
        if self.config.requires_auth and not self.config.has_credentials:
            return HealthStatus(
                source_name=self.name,
                healthy=False,
                credentials_missing=True,
                detail=(
                    "{0} requires authorization and no credentials are configured; "
                    "set one of {1}".format(
                        info.display_name,
                        ", ".join(self.config.api_key_env) or "the provider's key variable",
                    )
                ),
            )
        path, params = self.health_probe()
        try:
            response = await self._client.get(path, params=params)
        except Exception as exc:  # noqa: BLE001 - health checks report, never raise
            return HealthStatus(
                source_name=self.name,
                healthy=False,
                detail="{0}: {1}".format(exc.__class__.__name__, exc),
                quota=self._client.limiter.quota.as_dict(),
            )
        return HealthStatus(
            source_name=self.name,
            healthy=True,
            status_code=response.status_code,
            latency_seconds=response.elapsed_seconds,
            detail="reachable",
            quota=self._client.limiter.quota.as_dict(),
        )

    def health_probe(self):
        """`(path, params)` for the cheapest request that proves reachability."""
        return ("", None)

    # -- helpers for subclasses -------------------------------------------
    def _unsupported(self, query: SourceQuery, supported: Sequence[str]) -> List[str]:
        """Names of query fields this adapter cannot honour."""
        requested = []
        for field in ("text", "identifier", "object_type", "start_time", "end_time"):
            if getattr(query, field, None) is not None and field not in supported:
                requested.append(field)
        for key in query.extra:
            if key not in supported:
                requested.append("extra.{0}".format(key))
        return requested

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        await self.aclose()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "{0}(name={1!r})".format(type(self).__name__, self.name)
