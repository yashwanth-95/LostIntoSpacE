"""ISRO / Bhoonidhi adapter.

Bhoonidhi is NRSC/ISRO's Earth-observation data hub. It publishes an official
API specification at `https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/`, served from
`https://bhoonidhi-api.nrsc.gov.in`, with a STAC-style search surface. NISAR
S-band products are among the collections distributed through it.

Three rules this adapter exists to hold:

1. **No scraping.** An official API exists, so it is used. Nothing here parses
   Bhoonidhi's web pages, and there is no HTML fallback path.
2. **No invented public access.** Access is authorization-gated: a JWT is
   obtained from `/auth/token`, and API access is granted on request to NRSC.
   Without credentials the adapter reports `credentials_missing`, which is a
   distinct state from "no data found".
3. **Documented limits are respected.** The specification states 20
   authentication requests per hour per IP and 3 search requests per second per
   IP. Both are configured here rather than guessed, and the token is cached so
   a run does not re-authenticate per request — the specification asks
   explicitly that callers not fetch a new token for each request.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from contracts._time import utc_now
from contracts.provenance import SourceType

from ..normalization.parsing import clean_text, parse_datetime
from .base import (
    Capability,
    HealthStatus,
    SourceInfo,
    SourceQuery,
    SourceRecord,
    SourceResultPage,
    SpaceDataSource,
)
from .config import ProviderConfig, RateLimitConfig, RetryConfig
from .errors import SourceAuthError, SourceNotFoundError, SourceResponseError

__all__ = [
    "BhoonidhiSource",
    "BHOONIDHI_TOKEN_ENV",
    "BHOONIDHI_USERNAME_ENV",
    "BHOONIDHI_PASSWORD_ENV",
    "BHOONIDHI_ACCESS_CONTACT",
]

#: A pre-issued access token, when one has been obtained out of band.
BHOONIDHI_TOKEN_ENV = (
    "BHOONIDHI_ACCESS_TOKEN",
    "ISRO_BHOONIDHI_TOKEN",
    "LIS_ISRO_BHOONIDHI_API_KEY",
)
BHOONIDHI_USERNAME_ENV = "BHOONIDHI_USERNAME"
BHOONIDHI_PASSWORD_ENV = "BHOONIDHI_PASSWORD"

#: How API access is requested. Stated in errors so a user is told what to do
#: rather than left with an empty result.
BHOONIDHI_ACCESS_CONTACT = "bhoonidhi@nrsc.gov.in"


class BhoonidhiSource(SpaceDataSource):
    """ISRO Bhoonidhi Earth-observation data hub."""

    TOKEN_PATH = "/auth/token"
    LOGOUT_PATH = "/auth/logout"
    COLLECTIONS_PATH = "/data/collections"
    SEARCH_PATH = "/data/search"

    #: Refresh a little before nominal expiry so a long page-through does not
    #: fail mid-run on a token that expired between requests.
    TOKEN_REFRESH_MARGIN = timedelta(minutes=2)

    def __init__(self, *args, **kwargs):
        super(BhoonidhiSource, self).__init__(*args, **kwargs)
        self._access_token: Optional[str] = self.config.api_key
        self._refresh_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._last_response = None

    @classmethod
    def default_config(cls) -> ProviderConfig:
        return ProviderConfig(
            name="isro_bhoonidhi",
            #: The API is served from its own host, not the portal.
            base_url="https://bhoonidhi-api.nrsc.gov.in",
            timeout_seconds=45.0,
            retry=RetryConfig(max_attempts=2, backoff_factor=2.0),
            rate_limit=RateLimitConfig(
                #: The specification documents 3 search requests per second per
                #: IP; a margin is left so a burst cannot trip the limit.
                requests_per_second=2.0,
                max_concurrent=2,
                policy_note=(
                    "Bhoonidhi's API specification documents 20 authentication "
                    "requests per hour per IP, 3 search requests per second per IP, "
                    "and 3 concurrent downloads per user. Tokens are cached so a run "
                    "does not re-authenticate per request, as the specification asks."
                ),
            ),
            requires_auth=True,
            api_key_env=BHOONIDHI_TOKEN_ENV,
            api_key_header="Authorization",
            docs_url="https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/",
        )

    def get_source_info(self) -> SourceInfo:
        return SourceInfo(
            name="isro_bhoonidhi",
            display_name="ISRO Bhoonidhi (NRSC)",
            source_type=SourceType.EO_CATALOGUE,
            authority_note=(
                "Indian Earth-observation data hub. Authoritative for ISRO product "
                "metadata, including NISAR S-band products. Access is granted on "
                "request; it is not an open public API."
            ),
            provider_organization="ISRO / National Remote Sensing Centre",
            base_url=self.config.base_url,
            docs_url="https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/",
            capabilities=[Capability.SEARCH, Capability.FETCH_BY_ID, Capability.EO_PRODUCTS],
            provides=[
                "Earth-observation product metadata for authorized collections",
                "NISAR S-band SAR product metadata",
                "mission, satellite and instrument",
                "acquisition time and processing level",
                "product identifier, geometry and access URL",
            ],
            does_not_provide=[
                "public unauthenticated access",
                "space objects or orbital data",
                "any collection the account is not entitled to",
            ],
            license="ISRO/NRSC data policy; see the Bhoonidhi terms of use",
            attribution="ISRO / NRSC Bhoonidhi",
            requires_auth=True,
            rate_limit_note=self.config.rate_limit.policy_note,
            implemented=True,
        )

    # -- authorization -----------------------------------------------------
    @property
    def is_authorized(self) -> bool:
        """Whether a usable token is configured or has been obtained.

        Not proof the token is still valid — only the API can say that.
        """
        if not self._access_token:
            return False
        if self._token_expires_at is None:
            return True
        return utc_now() + self.TOKEN_REFRESH_MARGIN < self._token_expires_at

    @property
    def has_login_credentials(self) -> bool:
        import os

        return bool(
            os.environ.get(BHOONIDHI_USERNAME_ENV)
            and os.environ.get(BHOONIDHI_PASSWORD_ENV)
        )

    def require_authorization(self) -> None:
        """Raise a clear, actionable error when no credentials are configured."""
        if self.is_authorized or self.has_login_credentials:
            return
        raise SourceAuthError(
            "Bhoonidhi access is authorization-gated. Provide a token via one of "
            "{0}, or a username and password via {1}/{2}. API access is requested "
            "from {3}. This project does not scrape Bhoonidhi pages and provides no "
            "unauthenticated fallback.".format(
                ", ".join(BHOONIDHI_TOKEN_ENV),
                BHOONIDHI_USERNAME_ENV,
                BHOONIDHI_PASSWORD_ENV,
                BHOONIDHI_ACCESS_CONTACT,
            ),
            source_name=self.name,
        )

    async def authenticate(self) -> str:
        """Obtain a JWT access token, reusing a cached one while it is valid.

        The specification asks callers not to fetch a new token per request, and
        limits authentication to 20 requests per hour per IP — so caching here
        is a requirement, not an optimization.
        """
        if self.is_authorized:
            return self._access_token

        import os

        username = os.environ.get(BHOONIDHI_USERNAME_ENV)
        password = os.environ.get(BHOONIDHI_PASSWORD_ENV)
        if not (username and password):
            self.require_authorization()
            return self._access_token

        response = await self._client.post(
            self.TOKEN_PATH,
            json_body={"username": username, "password": password},
        )
        payload = response.json()
        token = clean_text(
            payload.get("access_token") or payload.get("accessToken")
        )
        if not token:
            raise SourceAuthError(
                "Bhoonidhi did not return an access token; check the credentials "
                "and that the account has API access ({0})".format(
                    BHOONIDHI_ACCESS_CONTACT
                ),
                source_name=self.name,
                url=response.url,
            )

        self._access_token = token
        self._refresh_token = clean_text(
            payload.get("refresh_token") or payload.get("refreshToken")
        )
        expires_in = payload.get("expires_in") or payload.get("expiresIn")
        if expires_in:
            try:
                self._token_expires_at = utc_now() + timedelta(seconds=float(expires_in))
            except (TypeError, ValueError):
                self._token_expires_at = None
        return token

    def _auth_headers(self) -> Dict[str, str]:
        if not self._access_token:
            self.require_authorization()
        return {"Authorization": "Bearer {0}".format(self._access_token)}

    # -- operations --------------------------------------------------------
    async def collections(self) -> List[Dict[str, Any]]:
        """List the collections this account may query."""
        await self.authenticate()
        response = await self._client.get(
            self.COLLECTIONS_PATH, headers=self._auth_headers()
        )
        payload = response.json()
        if isinstance(payload, dict):
            return payload.get("collections") or []
        return payload if isinstance(payload, list) else []

    async def search(self, query: SourceQuery) -> SourceResultPage:
        """Search product metadata.

        Uses the documented STAC-style parameters. Values are typed and built
        here; no caller-supplied filter string is passed through.
        """
        self.require_capability(Capability.SEARCH)
        await self.authenticate()

        params: Dict[str, Any] = {"limit": min(query.limit, 500)}

        collections = query.extra.get("collections") or query.extra.get("collection")
        if collections:
            if isinstance(collections, (list, tuple)):
                params["collections"] = ",".join(str(item) for item in collections)
            else:
                params["collections"] = str(collections)

        if query.start_time or query.end_time:
            #: RFC 3339 interval; an open end is expressed with "..".
            start = _rfc3339(query.start_time) if query.start_time else ".."
            end = _rfc3339(query.end_time) if query.end_time else ".."
            params["datetime"] = "{0}/{1}".format(start, end)

        if query.identifier:
            params["ids"] = clean_text(query.identifier)
        if query.extra.get("bbox"):
            params["bbox"] = _validate_bbox(query.extra["bbox"])
        if query.extra.get("token"):
            params["token"] = str(query.extra["token"])

        if not any(key in params for key in ("collections", "datetime", "ids", "bbox")):
            raise SourceResponseError(
                "a Bhoonidhi search needs a collection, time window, id or bounding "
                "box; unfiltered catalogue scans are refused",
                source_name=self.name,
            )

        response = await self._client.get(
            self.SEARCH_PATH, params=params, headers=self._auth_headers()
        )
        payload = response.json()
        features = payload.get("features")
        if features is None:
            raise SourceResponseError(
                "Bhoonidhi search response has no 'features' array",
                source_name=self.name,
                url=response.url,
            )
        self._last_response = response

        context = payload.get("context") or {}
        records = [
            SourceRecord(
                source_name=self.name,
                source_record_id=clean_text(feature.get("id")),
                payload=feature,
                source_reference=self.build_source_reference(
                    response,
                    record_id=clean_text(feature.get("id")),
                    source_timestamp=parse_datetime(
                        (feature.get("properties") or {}).get("datetime")
                    ),
                ),
                retrieved_at=response.retrieved_at,
            )
            for feature in features
        ]
        return SourceResultPage(
            source_name=self.name,
            records=records,
            total_available=context.get("returned"),
            offset=query.offset,
            next_cursor=_next_token(payload),
            unsupported_filters=self._unsupported(
                query,
                ["identifier", "start_time", "end_time", "collections", "collection",
                 "bbox", "token"],
            ),
            query_echo={key: value for key, value in params.items()},
            retrieved_at=response.retrieved_at,
        )

    async def fetch_by_id(
        self, identifier: str, collection: Optional[str] = None, **kwargs
    ) -> Optional[SourceRecord]:
        """Fetch one product by its item id, within a collection when known."""
        self.require_capability(Capability.FETCH_BY_ID)
        item_id = clean_text(identifier)
        if not item_id:
            raise SourceResponseError(
                "a product lookup needs an item id", source_name=self.name
            )
        await self.authenticate()

        if collection:
            path = "{0}/{1}/items/{2}".format(
                self.COLLECTIONS_PATH, clean_text(collection), item_id
            )
            response = await self._client.get(path, headers=self._auth_headers())
            feature = response.json()
            if not isinstance(feature, dict) or "id" not in feature:
                raise SourceNotFoundError(
                    "no Bhoonidhi item {0!r} in collection {1!r}".format(
                        item_id, collection
                    ),
                    source_name=self.name,
                    url=response.url,
                )
            return SourceRecord(
                source_name=self.name,
                source_record_id=clean_text(feature.get("id")),
                payload=feature,
                source_reference=self.build_source_reference(
                    response, record_id=clean_text(feature.get("id"))
                ),
                retrieved_at=response.retrieved_at,
            )

        page = await self.search(SourceQuery(identifier=item_id, limit=1))
        return page.records[0] if page.records else None

    async def health_check(self) -> HealthStatus:
        """Report missing credentials as a configuration state, not a failure."""
        if not (self.is_authorized or self.has_login_credentials):
            return HealthStatus(
                source_name=self.name,
                healthy=False,
                credentials_missing=True,
                detail=(
                    "no Bhoonidhi credentials configured. Set a token via one of {0}, "
                    "or {1}/{2}. Request API access from {3}. Absence of credentials "
                    "is not absence of data.".format(
                        ", ".join(BHOONIDHI_TOKEN_ENV),
                        BHOONIDHI_USERNAME_ENV,
                        BHOONIDHI_PASSWORD_ENV,
                        BHOONIDHI_ACCESS_CONTACT,
                    )
                ),
            )
        try:
            await self.authenticate()
            response = await self._client.get(
                self.COLLECTIONS_PATH, headers=self._auth_headers()
            )
        except Exception as exc:  # noqa: BLE001 - health checks report, never raise
            return HealthStatus(
                source_name=self.name,
                healthy=False,
                credentials_missing=isinstance(exc, SourceAuthError)
                and not self._access_token,
                detail="{0}: {1}".format(exc.__class__.__name__, exc),
            )
        return HealthStatus(
            source_name=self.name,
            healthy=True,
            status_code=response.status_code,
            latency_seconds=response.elapsed_seconds,
            detail="reachable and authorized",
        )

    def health_probe(self):
        return (self.COLLECTIONS_PATH, None)


def _rfc3339(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_token(payload) -> Optional[str]:
    """Read the pagination token from a STAC `links` array."""
    for link in payload.get("links") or []:
        if str(link.get("rel", "")).lower() == "next":
            body = link.get("body") or {}
            token = body.get("token") or link.get("token")
            if token:
                return str(token)
            href = clean_text(link.get("href"))
            if href:
                return href
    return None


def _validate_bbox(value) -> str:
    """Accept a four- or six-number bounding box and render it as CSV."""
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
    else:
        parts = [str(part) for part in value]
    if len(parts) not in (4, 6):
        raise SourceResponseError(
            "a bounding box needs 4 or 6 numbers, got {0}".format(len(parts)),
            source_name="isro_bhoonidhi",
        )
    numbers = []
    for part in parts:
        try:
            numbers.append(float(part))
        except (TypeError, ValueError):
            raise SourceResponseError(
                "bounding-box values must be numeric, got {0!r}".format(part),
                source_name="isro_bhoonidhi",
            )
    return ",".join(repr(number) for number in numbers)
