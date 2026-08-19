"""Centralized HTTP layer for every external source.

One place owns timeout, retry, backoff, rate-limit handling, headers, response
validation and safe logging. Adapters describe *what* to request; they never
implement *how* to request it. That keeps retry semantics consistent and makes
credential redaction impossible to forget.

Testing: pass an `httpx.MockTransport` as `transport`. No network is touched and
no extra dependency is needed.
"""

import json
import logging
import random
import re
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Tuple

import httpx
from pydantic import BaseModel, ConfigDict, Field

from contracts._time import utc_now
from contracts.provenance import REDACTION_MARKER

from .config import ProviderConfig
from .errors import (
    RateLimitExceededError,
    SourceAuthError,
    SourceNotFoundError,
    SourceResponseError,
    SourceTimeoutError,
    SourceUnavailableError,
)
from .ratelimit import RateLimiter

__all__ = ["RawResponse", "HttpClient", "redact_url", "redact_mapping"]

logger = logging.getLogger("data.sources.http")

#: Query parameters whose values must never appear in logs, errors or stored
#: provenance. Matched case-insensitively.
_SECRET_PARAMS = ("api_key", "apikey", "key", "token", "access_token", "password", "secret")

_SECRET_HEADERS = ("authorization", "x-api-key", "api-key", "cookie", "set-cookie",
                   "proxy-authorization")

_REDACTED = REDACTION_MARKER

_PARAM_PATTERN = re.compile(
    r"(?i)\b(" + "|".join(re.escape(name) for name in _SECRET_PARAMS) + r")=([^&\s]*)"
)


def redact_url(url: Any) -> str:
    """Remove credential query-parameter values from a URL.

    NASA endpoints take the API key as a query parameter, so an unredacted URL
    would leak the key into logs, error messages and stored `SourceReference`s.
    """
    text = str(url)
    return _PARAM_PATTERN.sub(lambda match: "{0}={1}".format(match.group(1), _REDACTED), text)


def redact_mapping(mapping: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Copy a header/param mapping with credential values replaced."""
    if not mapping:
        return {}
    safe: Dict[str, Any] = {}
    for key, value in mapping.items():
        lowered = str(key).lower()
        if lowered in _SECRET_HEADERS or lowered in _SECRET_PARAMS:
            safe[key] = _REDACTED
        else:
            safe[key] = value
    return safe


class RawResponse(BaseModel):
    """An immutable record of one external response.

    Kept before parsing so that a fixture is literally a recorded response, and
    so a parsing bug can be diagnosed without re-hitting the provider.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    source_name: str
    #: Already redacted. There is no un-redacted variant on purpose.
    url: str
    method: str = "GET"
    status_code: int
    #: Redacted request parameters.
    request_params: Dict[str, Any] = Field(default_factory=dict)
    #: Redacted response headers.
    headers: Dict[str, str] = Field(default_factory=dict)
    text: str = ""
    retrieved_at: datetime = Field(default_factory=utc_now)
    elapsed_seconds: Optional[float] = None
    #: How many attempts it took, including the successful one.
    attempts: int = 1

    def json(self) -> Any:
        """Parse the body as JSON, or raise `SourceResponseError`."""
        try:
            return json.loads(self.text)
        except ValueError as exc:
            raise SourceResponseError(
                "response body is not valid JSON: {0}".format(exc),
                source_name=self.source_name,
                status_code=self.status_code,
                url=self.url,
            )

    @property
    def content_type(self) -> str:
        for key, value in self.headers.items():
            if key.lower() == "content-type":
                return value
        return ""

    def summary(self) -> str:
        """Safe one-line description for logs."""
        return "{0} {1} -> {2} ({3} bytes, {4} attempt(s))".format(
            self.method, self.url, self.status_code, len(self.text), self.attempts
        )


class HttpClient:
    """Async HTTP client bound to one provider's configuration."""

    def __init__(
        self,
        config: ProviderConfig,
        transport: Optional[httpx.BaseTransport] = None,
        limiter: Optional[RateLimiter] = None,
        sleeper=None,
    ):
        self.config = config
        self.limiter = limiter or RateLimiter(config.rate_limit, sleeper=sleeper)
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None
        self._sleep = sleeper
        #: Simple counters, surfaced by health checks and ingestion reports.
        self.stats = {"requests": 0, "retries": 0, "failures": 0}

    # -- lifecycle ---------------------------------------------------------
    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = dict(self.config.headers)
            headers.setdefault("User-Agent", self.config.user_agent)
            headers.setdefault("Accept", "application/json")
            if self.config.api_key and self.config.api_key_header:
                headers[self.config.api_key_header] = self.config.api_key
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout_seconds,
                headers=headers,
                transport=self._transport,
                verify=self.config.verify_ssl,
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "HttpClient":
        await self._ensure_client()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    # -- request path ------------------------------------------------------
    async def request(
        self,
        method: str,
        path: str,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Optional[Any] = None,
        headers: Optional[Mapping[str, str]] = None,
        expected_status: Tuple[int, ...] = (200,),
    ) -> RawResponse:
        """Send a request, applying rate limiting, retry and validation."""
        client = await self._ensure_client()
        retry = self.config.retry
        source = self.config.name

        send_params: Dict[str, Any] = dict(params or {})
        if self.config.api_key and self.config.api_key_param:
            send_params[self.config.api_key_param] = self.config.api_key
        safe_params = redact_mapping(send_params)

        last_error: Optional[Exception] = None
        started = utc_now()

        for attempt in range(1, retry.max_attempts + 1):
            self.limiter.check_quota(source_name=source)
            await self.limiter.acquire()

            async with self.limiter.concurrency_slot():
                self.stats["requests"] += 1
                try:
                    response = await client.request(
                        method,
                        path,
                        params=send_params or None,
                        json=json_body,
                        headers=dict(headers or {}),
                    )
                except httpx.TimeoutException as exc:
                    last_error = SourceTimeoutError(
                        "request timed out after {0}s".format(self.config.timeout_seconds),
                        source_name=source,
                        url=redact_url(path),
                    )
                    logger.warning(
                        "%s timeout on attempt %s/%s: %s",
                        source, attempt, retry.max_attempts, exc.__class__.__name__,
                    )
                except httpx.HTTPError as exc:
                    last_error = SourceUnavailableError(
                        "transport error: {0}".format(exc.__class__.__name__),
                        source_name=source,
                        url=redact_url(path),
                    )
                    logger.warning(
                        "%s transport error on attempt %s/%s: %s",
                        source, attempt, retry.max_attempts, exc.__class__.__name__,
                    )
                else:
                    self.limiter.observe_headers(response.headers)
                    raw = self._build_raw(
                        response, safe_params, attempt, started, method
                    )
                    logger.debug("%s %s", source, raw.summary())

                    if response.status_code in expected_status:
                        return raw

                    error = self._classify(response, raw)
                    if not self._should_retry(response.status_code, attempt):
                        self.stats["failures"] += 1
                        raise error
                    last_error = error

            if attempt < retry.max_attempts:
                self.stats["retries"] += 1
                await self._backoff(attempt, last_error)

        self.stats["failures"] += 1
        raise last_error or SourceUnavailableError(
            "request failed after {0} attempts".format(retry.max_attempts),
            source_name=source,
            url=redact_url(path),
        )

    async def get(self, path: str, **kwargs) -> RawResponse:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> RawResponse:
        return await self.request("POST", path, **kwargs)

    # -- helpers -----------------------------------------------------------
    def _build_raw(self, response, safe_params, attempt, started, method) -> RawResponse:
        return RawResponse(
            source_name=self.config.name,
            url=redact_url(response.request.url),
            method=method.upper(),
            status_code=response.status_code,
            request_params=safe_params,
            headers=redact_mapping(dict(response.headers)),
            text=response.text,
            retrieved_at=utc_now(),
            elapsed_seconds=(utc_now() - started).total_seconds(),
            attempts=attempt,
        )

    def _classify(self, response, raw: RawResponse):
        """Map an unexpected status onto the right error type."""
        source = self.config.name
        status = response.status_code
        url = raw.url
        body_hint = raw.text[:200] if raw.text else ""

        if status == 429:
            return RateLimitExceededError(
                "rate limit exceeded: {0}".format(body_hint or "no detail"),
                retry_after=self._retry_after(response),
                source_name=source,
                status_code=status,
                url=url,
            )
        if status in (401, 403):
            return SourceAuthError(
                "authentication or authorization failed; check credentials and access "
                "entitlement for this dataset",
                source_name=source,
                status_code=status,
                url=url,
            )
        if status == 404:
            return SourceNotFoundError(
                "record not found at this source",
                source_name=source,
                status_code=status,
                url=url,
            )
        if 500 <= status < 600:
            return SourceUnavailableError(
                "provider returned {0}".format(status),
                source_name=source,
                status_code=status,
                url=url,
            )
        return SourceResponseError(
            "unexpected status {0}: {1}".format(status, body_hint or "no body"),
            source_name=source,
            status_code=status,
            url=url,
        )

    def _retry_after(self, response) -> Optional[float]:
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            # HTTP-date form is legal but rare; computed backoff covers it.
            return None

    def _should_retry(self, status_code: int, attempt: int) -> bool:
        retry = self.config.retry
        if attempt >= retry.max_attempts:
            return False
        return status_code in retry.retry_on_status

    async def _backoff(self, attempt: int, error: Optional[Exception]) -> None:
        retry = self.config.retry
        delay = retry.backoff_for(attempt)

        retry_after = getattr(error, "retry_after", None)
        if retry.respect_retry_after and retry_after:
            delay = min(float(retry_after), retry.max_retry_after_seconds)

        if retry.jitter:
            delay += delay * retry.jitter * random.random()

        logger.info(
            "%s backing off %.2fs before attempt %s", self.config.name, delay, attempt + 1
        )
        if self._sleep is not None:
            await self._sleep(delay)
        else:
            import asyncio

            await asyncio.sleep(delay)
