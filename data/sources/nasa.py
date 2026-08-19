"""NASA source adapters.

Four separate sources, because they are four separate APIs with different hosts,
different limits and — critically — different *kinds* of data:

* `NasaApodSource`  — Astronomy Picture of the Day. Media, not science records.
* `NasaNeoWsSource` — near-Earth object summaries and close approaches.
* `NasaEonetSource` — Earth natural-event metadata (EONET v3).
* `NasaNtrsSource`  — technical/scientific document metadata.

Each declares what it does *not* provide, because the most common integration
error with NASA's platform is forcing an unrelated product into `SpaceObject`.
APOD returns a picture and a caption; that is not a space object, and this
adapter will not pretend otherwise.

Rate limits are configuration, not assumptions. NASA's documented default for a
registered key is 1,000 requests per hour, with substantially lower limits for
`DEMO_KEY`; both are overridable via `LIS_NASA_*_REQUESTS_PER_HOUR`, and the
`X-RateLimit-Remaining` header the platform returns is honoured at runtime.
"""

from typing import Any, Dict, List, Optional

from contracts.provenance import SourceType

from ..normalization.parsing import clean_text, parse_datetime
from .base import (
    Capability,
    SourceInfo,
    SourceQuery,
    SourceRecord,
    SourceResultPage,
    SpaceDataSource,
)
from .config import ProviderConfig, RateLimitConfig, RetryConfig
from .errors import SourceResponseError

__all__ = [
    "NASA_API_KEY_ENV",
    "DEMO_KEY",
    "NasaApodSource",
    "NasaNeoWsSource",
    "NasaEonetSource",
    "NasaNtrsSource",
]

#: Environment variables checked for the api.nasa.gov key, in order. The first
#: matches the name already present in the project's `.env.example`.
NASA_API_KEY_ENV = ("NASA_API_KEY", "LIS_NASA_API_KEY")

#: NASA's shared demo key. Heavily rate limited; usable for a smoke test only.
DEMO_KEY = "DEMO_KEY"

#: Quota headers api.nasa.gov returns on every response.
_NASA_QUOTA_HEADERS = {
    "limit_header": "X-RateLimit-Limit",
    "remaining_header": "X-RateLimit-Remaining",
}

_NASA_ATTRIBUTION = "NASA Open APIs (api.nasa.gov)"


def _nasa_rate_limit(default_per_hour: int = 1000) -> RateLimitConfig:
    """Rate limits for an api.nasa.gov endpoint.

    The default reflects NASA's documented hourly limit for a registered key.
    Deployments using `DEMO_KEY` must lower it via
    `LIS_<PROVIDER>_REQUESTS_PER_HOUR`; nothing here assumes which key is in use.
    """
    return RateLimitConfig(
        requests_per_hour=default_per_hour,
        requests_per_second=4.0,
        max_concurrent=4,
        low_quota_threshold=5,
        policy_note=(
            "api.nasa.gov documents an hourly quota per API key (1,000/hour for a "
            "registered key, much lower for DEMO_KEY) and reports remaining quota in "
            "X-RateLimit-Remaining. Both the configured limit and the reported "
            "remaining quota are honoured."
        ),
        **_NASA_QUOTA_HEADERS
    )


class _NasaApiSource(SpaceDataSource):
    """Shared behaviour for endpoints hosted on api.nasa.gov."""

    provider_name = "nasa"
    base_url = "https://api.nasa.gov"

    @classmethod
    def _config(cls, name: str, per_hour: int = 1000, timeout: float = 20.0) -> ProviderConfig:
        return ProviderConfig(
            name=name,
            base_url=cls.base_url,
            timeout_seconds=timeout,
            retry=RetryConfig(max_attempts=3, backoff_factor=0.5),
            rate_limit=_nasa_rate_limit(per_hour),
            api_key_env=NASA_API_KEY_ENV,
            api_key=DEMO_KEY,
            api_key_param="api_key",
            docs_url="https://api.nasa.gov/",
        )

    @property
    def using_demo_key(self) -> bool:
        """True when running on NASA's shared demo key.

        Worth surfacing: the demo key's limits are low enough that an ingestion
        run will be throttled, and the resulting gaps must not be mistaken for
        the objects not existing.
        """
        return self.config.api_key == DEMO_KEY


class NasaApodSource(_NasaApiSource):
    """Astronomy Picture of the Day.

    Media and editorial captions. Deliberately not mapped into `SpaceObject`:
    an APOD entry is an image with a title and an explanation, and treating it
    as a scientific record about a body would invent structure that is not there.
    """

    @classmethod
    def default_config(cls) -> ProviderConfig:
        return cls._config("nasa_apod")

    def get_source_info(self) -> SourceInfo:
        return SourceInfo(
            name="nasa_apod",
            display_name="NASA Astronomy Picture of the Day",
            source_type=SourceType.AGENCY_PUBLIC_API,
            provider_organization="NASA",
            base_url=self.config.base_url,
            docs_url="https://api.nasa.gov/",
            capabilities=[Capability.MEDIA, Capability.FETCH_BY_ID],
            provides=["daily astronomy image", "title", "editorial explanation", "credit"],
            does_not_provide=[
                "physical parameters",
                "orbital elements",
                "any structured record about a specific body",
            ],
            attribution=_NASA_ATTRIBUTION,
            rate_limit_note=self.config.rate_limit.policy_note,
            implemented=False,
        )

    def health_probe(self):
        return ("/planetary/apod", None)


class NasaNeoWsSource(_NasaApiSource):
    """Near Earth Object Web Service.

    Useful for close-approach summaries and a browsable NEO list. Its orbital
    and physical values originate from JPL's small-body data, so it is treated
    as a convenience layer, never as an authority: where NeoWs and JPL SBDB
    disagree, SBDB wins.
    """

    @classmethod
    def default_config(cls) -> ProviderConfig:
        return cls._config("nasa_neows")

    def get_source_info(self) -> SourceInfo:
        return SourceInfo(
            name="nasa_neows",
            display_name="NASA Near Earth Object Web Service",
            source_type=SourceType.AGENCY_PUBLIC_API,
            authority_note=(
                "Derived from JPL small-body data. Use JPL SBDB as the authority for "
                "orbital elements and physical parameters."
            ),
            provider_organization="NASA / JPL",
            base_url=self.config.base_url,
            docs_url="https://api.nasa.gov/",
            capabilities=[
                Capability.SEARCH,
                Capability.FETCH_BY_ID,
                Capability.CLOSE_APPROACHES,
                Capability.PHYSICAL_PARAMETERS,
            ],
            provides=[
                "near-earth object list by close-approach date",
                "estimated diameter range",
                "close-approach distance and relative velocity",
                "potentially-hazardous flag",
            ],
            does_not_provide=[
                "covariance",
                "individual astrometric observations",
                "precise ephemerides",
                "main-belt asteroids that never approach Earth",
            ],
            attribution=_NASA_ATTRIBUTION,
            rate_limit_note=self.config.rate_limit.policy_note,
            implemented=True,
        )

    def health_probe(self):
        return ("/neo/rest/v1/stats", None)

    async def fetch_by_id(self, identifier: str, **kwargs) -> Optional[SourceRecord]:
        """Look up one NEO by its NeoWs/SPK reference id.

        Example: `2000433` is 433 Eros.
        """
        self.require_capability(Capability.FETCH_BY_ID)
        identifier = str(identifier).strip()
        if not identifier:
            raise SourceResponseError("a NEO lookup needs an identifier", source_name=self.name)

        response = await self._client.get("/neo/rest/v1/neo/{0}".format(identifier))
        payload = response.json()
        if not isinstance(payload, dict) or "id" not in payload:
            raise SourceResponseError(
                "NeoWs lookup returned an unexpected payload shape",
                source_name=self.name,
                url=response.url,
            )
        return SourceRecord(
            source_name=self.name,
            source_record_id=str(payload.get("id")),
            payload=payload,
            source_reference=self.build_source_reference(
                response, record_id=str(payload.get("id"))
            ),
            retrieved_at=response.retrieved_at,
        )

    async def search(self, query: SourceQuery) -> SourceResultPage:
        """Browse the NEO catalogue, or list objects by close-approach date.

        NeoWs offers two very different query shapes and no free-text search.
        A `text` filter is therefore reported as unsupported rather than being
        silently ignored — the caller must post-filter or narrow its claim.
        """
        self.require_capability(Capability.SEARCH)

        supported = ["start_time", "end_time", "offset", "limit"]
        unsupported = self._unsupported(query, supported)

        if query.start_time is not None:
            # The feed endpoint is limited to a seven-day span by NASA.
            if query.end_time is not None:
                span_days = (query.end_time - query.start_time).days
                if span_days > 7:
                    raise SourceResponseError(
                        "the NeoWs feed endpoint accepts at most a 7-day range; "
                        "{0} days were requested".format(span_days),
                        source_name=self.name,
                    )
            params: Dict[str, Any] = {"start_date": query.start_time.strftime("%Y-%m-%d")}
            if query.end_time is not None:
                params["end_date"] = query.end_time.strftime("%Y-%m-%d")
            response = await self._client.get("/neo/rest/v1/feed", params=params)
            payload = response.json()
            objects: List[Dict[str, Any]] = []
            for daily in (payload.get("near_earth_objects") or {}).values():
                objects.extend(daily)
            total = payload.get("element_count")
        else:
            params = {
                "page": query.offset // query.limit if query.limit else 0,
                "size": query.limit,
            }
            response = await self._client.get("/neo/rest/v1/neo/browse", params=params)
            payload = response.json()
            objects = payload.get("near_earth_objects") or []
            total = (payload.get("page") or {}).get("total_elements")

        records = [
            SourceRecord(
                source_name=self.name,
                source_record_id=str(item.get("id")),
                payload=item,
                source_reference=self.build_source_reference(
                    response, record_id=str(item.get("id"))
                ),
                retrieved_at=response.retrieved_at,
            )
            for item in objects
        ]
        return SourceResultPage(
            source_name=self.name,
            records=records,
            total_available=total,
            offset=query.offset,
            unsupported_filters=unsupported,
            query_echo=dict(response.request_params),
            retrieved_at=response.retrieved_at,
        )


class NasaEonetSource(SpaceDataSource):
    """Earth Observatory Natural Event Tracker, v3.

    v3 is the current stable version. Events are curated natural-event records
    with geometry and categories — they are Earth events, not space objects, and
    are modelled as their own record type.
    """

    @classmethod
    def default_config(cls) -> ProviderConfig:
        return ProviderConfig(
            name="nasa_eonet",
            base_url="https://eonet.gsfc.nasa.gov/api/v3",
            timeout_seconds=20.0,
            retry=RetryConfig(max_attempts=3, backoff_factor=0.5),
            rate_limit=RateLimitConfig(
                requests_per_second=2.0,
                max_concurrent=2,
                policy_note=(
                    "EONET publishes no documented hard quota; a conservative "
                    "self-imposed limit is applied to stay a good citizen."
                ),
            ),
            docs_url="https://eonet.gsfc.nasa.gov/docs/v3",
        )

    def get_source_info(self) -> SourceInfo:
        return SourceInfo(
            name="nasa_eonet",
            display_name="NASA EONET v3",
            source_type=SourceType.AGENCY_PUBLIC_API,
            provider_organization="NASA Earth Observatory",
            base_url=self.config.base_url,
            docs_url="https://eonet.gsfc.nasa.gov/docs/v3",
            capabilities=[Capability.SEARCH, Capability.FETCH_BY_ID,
                          Capability.NATURAL_EVENTS],
            provides=[
                "open and closed natural events",
                "event categories (wildfires, storms, volcanoes, ...)",
                "event geometry and dates",
                "links to source agencies",
            ],
            does_not_provide=[
                "space objects",
                "orbital data",
                "satellite imagery products",
            ],
            attribution="NASA Earth Observatory Natural Event Tracker (EONET)",
            rate_limit_note=self.config.rate_limit.policy_note,
            implemented=True,
        )

    def health_probe(self):
        return ("/categories", None)

    async def search(self, query: SourceQuery) -> SourceResultPage:
        """List natural events.

        EONET filters server-side by status, category, date window and count. It
        has no free-text search, so a `text` query is applied client-side over
        event titles and reported as a filter EONET itself did not apply.
        """
        self.require_capability(Capability.SEARCH)

        params: Dict[str, Any] = {"limit": query.limit}
        #: EONET defaults to open events only; "all" is needed for history.
        params["status"] = str(query.extra.get("status", "all"))
        if query.object_type:
            params["category"] = query.object_type
        if query.extra.get("category"):
            params["category"] = str(query.extra["category"])
        if query.extra.get("source"):
            params["source"] = str(query.extra["source"])
        if query.extra.get("bbox"):
            params["bbox"] = str(query.extra["bbox"])
        if query.start_time is not None:
            params["start"] = query.start_time.strftime("%Y-%m-%d")
        if query.end_time is not None:
            params["end"] = query.end_time.strftime("%Y-%m-%d")

        response = await self._client.get("/events", params=params)
        payload = response.json()
        events = payload.get("events")
        if events is None:
            raise SourceResponseError(
                "EONET response has no 'events' array",
                source_name=self.name,
                url=response.url,
            )

        unsupported: List[str] = []
        if query.text:
            # Applied here, not by EONET. Recorded so the caller knows.
            needle = query.text.lower()
            events = [
                event
                for event in events
                if needle in str(event.get("title", "")).lower()
                or needle in str(event.get("description") or "").lower()
            ]
            unsupported.append("text (filtered client-side; EONET has no text search)")

        records = [
            SourceRecord(
                source_name=self.name,
                source_record_id=str(event.get("id")),
                payload=event,
                source_reference=self.build_source_reference(
                    response,
                    record_id=str(event.get("id")),
                    source_timestamp=self._latest_geometry_date(event),
                ),
                retrieved_at=response.retrieved_at,
            )
            for event in events
        ]
        return SourceResultPage(
            source_name=self.name,
            records=records,
            offset=query.offset,
            unsupported_filters=unsupported,
            query_echo=dict(response.request_params),
            retrieved_at=response.retrieved_at,
        )

    async def fetch_by_id(self, identifier: str, **kwargs) -> Optional[SourceRecord]:
        """Fetch one event by its EONET id, e.g. `EONET_22798`."""
        self.require_capability(Capability.FETCH_BY_ID)
        identifier = clean_text(identifier)
        if not identifier:
            raise SourceResponseError("an event lookup needs an id", source_name=self.name)

        response = await self._client.get("/events/{0}".format(identifier))
        payload = response.json()
        if not isinstance(payload, dict) or "id" not in payload:
            raise SourceResponseError(
                "EONET event lookup returned an unexpected payload shape",
                source_name=self.name,
                url=response.url,
            )
        return SourceRecord(
            source_name=self.name,
            source_record_id=str(payload["id"]),
            payload=payload,
            source_reference=self.build_source_reference(
                response,
                record_id=str(payload["id"]),
                source_timestamp=self._latest_geometry_date(payload),
            ),
            retrieved_at=response.retrieved_at,
        )

    async def categories(self) -> List[Dict[str, Any]]:
        """The category vocabulary EONET filters by."""
        response = await self._client.get("/categories")
        return (response.json() or {}).get("categories", [])

    @staticmethod
    def _latest_geometry_date(event: Dict[str, Any]):
        """Most recent observation time in an event, for provenance.

        This becomes the record's `source_timestamp`, and drives freshness: a
        storm last seen four days ago is historical, however live the feed is.
        """
        dates = [
            parse_datetime(geometry.get("date"))
            for geometry in (event.get("geometry") or [])
        ]
        present = [value for value in dates if value is not None]
        return max(present) if present else None


class NasaNtrsSource(SpaceDataSource):
    """NASA Technical Reports Server.

    Document *metadata* — titles, abstracts, authors, dates, identifiers — which
    is what the RAG layer cites. Full-text retrieval is deliberately out of scope
    at this stage: availability and licensing vary per document, and citing
    metadata is both sufficient and unambiguously permitted.
    """

    @classmethod
    def default_config(cls) -> ProviderConfig:
        return ProviderConfig(
            name="nasa_ntrs",
            base_url="https://ntrs.nasa.gov/api",
            timeout_seconds=30.0,
            retry=RetryConfig(max_attempts=3, backoff_factor=1.0),
            rate_limit=RateLimitConfig(
                requests_per_second=1.0,
                max_concurrent=2,
                policy_note=(
                    "NTRS publishes an OpenAPI interface without a documented public "
                    "quota; requests are self-limited to one per second."
                ),
            ),
            docs_url="https://ntrs.nasa.gov/api/openapi",
        )

    def get_source_info(self) -> SourceInfo:
        return SourceInfo(
            name="nasa_ntrs",
            display_name="NASA Technical Reports Server",
            source_type=SourceType.LITERATURE,
            provider_organization="NASA STI Program",
            base_url=self.config.base_url,
            docs_url="https://ntrs.nasa.gov/api/openapi",
            capabilities=[Capability.SEARCH, Capability.FETCH_BY_ID, Capability.DOCUMENTS],
            provides=[
                "technical report metadata",
                "titles, abstracts and authors",
                "publication dates and identifiers",
                "subject categories",
            ],
            does_not_provide=[
                "physical or orbital parameters",
                "guaranteed full text",
                "any structured scientific record",
            ],
            attribution="NASA Technical Reports Server (NTRS)",
            rate_limit_note=self.config.rate_limit.policy_note,
            implemented=True,
        )

    def health_probe(self):
        return ("/openapi", None)

    #: NTRS pages with `page.size` / `page.from`, not `limit` / `offset`.
    SEARCH_PATH = "/citations/search"

    async def search(self, query: SourceQuery) -> SourceResultPage:
        """Full-text search over NTRS citation metadata."""
        self.require_capability(Capability.SEARCH)

        text = clean_text(query.text)
        if not text:
            raise SourceResponseError(
                "an NTRS search needs query text", source_name=self.name
            )

        params: Dict[str, Any] = {"q": text, "page.size": query.limit}
        if query.offset:
            params["page.from"] = query.offset
        if query.start_time is not None:
            params["published.gte"] = query.start_time.strftime("%Y-%m-%d")
        if query.end_time is not None:
            params["published.lte"] = query.end_time.strftime("%Y-%m-%d")
        for key in ("center", "stiType", "subjectCategory", "sort"):
            if query.extra.get(key) is not None:
                params[key] = str(query.extra[key])

        response = await self._client.get(self.SEARCH_PATH, params=params)
        payload = response.json()
        results = payload.get("results")
        if results is None:
            raise SourceResponseError(
                "NTRS response has no 'results' array",
                source_name=self.name,
                url=response.url,
            )

        stats = payload.get("stats") or {}
        records = [
            SourceRecord(
                source_name=self.name,
                source_record_id=str(item.get("id")),
                payload=item,
                source_reference=self.build_source_reference(
                    response,
                    record_id=str(item.get("id")),
                    source_timestamp=parse_datetime(item.get("modified")),
                ),
                retrieved_at=response.retrieved_at,
            )
            for item in results
        ]
        return SourceResultPage(
            source_name=self.name,
            records=records,
            total_available=stats.get("total"),
            offset=query.offset,
            unsupported_filters=self._unsupported(
                query,
                ["text", "start_time", "end_time", "center", "stiType",
                 "subjectCategory", "sort"],
            ),
            query_echo=dict(response.request_params),
            retrieved_at=response.retrieved_at,
        )

    async def fetch_by_id(self, identifier: str, **kwargs) -> Optional[SourceRecord]:
        """Fetch one citation by its NTRS numeric id."""
        self.require_capability(Capability.FETCH_BY_ID)
        identifier = clean_text(identifier)
        if not identifier:
            raise SourceResponseError("a citation lookup needs an id", source_name=self.name)

        response = await self._client.get("/citations/{0}".format(identifier))
        payload = response.json()
        if not isinstance(payload, dict) or "id" not in payload:
            raise SourceResponseError(
                "NTRS citation lookup returned an unexpected payload shape",
                source_name=self.name,
                url=response.url,
            )
        return SourceRecord(
            source_name=self.name,
            source_record_id=str(payload["id"]),
            payload=payload,
            source_reference=self.build_source_reference(
                response,
                record_id=str(payload["id"]),
                source_timestamp=parse_datetime(payload.get("modified")),
            ),
            retrieved_at=response.retrieved_at,
        )
