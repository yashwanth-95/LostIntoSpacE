"""Per-provider HTTP configuration.

There is deliberately **no universal rate limit**. Every provider publishes its
own limits and its own headers, and a single global number would either throttle
fast providers needlessly or get us blocked by slow ones. Each provider ships a
`ProviderConfig` with its own values, and every value is overridable from the
environment so limits can be corrected in production without a code change.

Environment override pattern, for a provider named `nasa`:

    LIS_NASA_BASE_URL
    LIS_NASA_TIMEOUT_SECONDS
    LIS_NASA_REQUESTS_PER_HOUR
    LIS_NASA_REQUESTS_PER_SECOND
    LIS_NASA_MAX_ATTEMPTS
    LIS_NASA_API_KEY          (or the provider's documented variable, e.g. NASA_API_KEY)
"""

import os
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "RetryConfig",
    "RateLimitConfig",
    "ProviderConfig",
    "env_override",
]

#: Prefix for this project's environment overrides.
ENV_PREFIX = "LIS_"


def env_override(provider: str, suffix: str) -> Optional[str]:
    """Read `LIS_<PROVIDER>_<SUFFIX>` from the environment."""
    key = "{0}{1}_{2}".format(ENV_PREFIX, provider.upper().replace("-", "_"), suffix)
    value = os.environ.get(key)
    return value if value not in (None, "") else None


def _as_float(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _as_int(text: Optional[str]) -> Optional[int]:
    value = _as_float(text)
    return None if value is None else int(value)


class RetryConfig(BaseModel):
    """Retry and backoff behaviour for one provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Total attempts including the first. 1 disables retrying.
    max_attempts: int = Field(default=3, ge=1, le=10)
    #: Base for exponential backoff: delay = backoff_factor * 2**(attempt - 1).
    backoff_factor: float = Field(default=0.5, ge=0.0)
    max_backoff_seconds: float = Field(default=30.0, ge=0.0)
    #: Random fraction added to each delay, to avoid synchronised retries when
    #: several ingestion workers hit the same provider.
    jitter: float = Field(default=0.1, ge=0.0, le=1.0)
    #: Status codes worth retrying. 429 is included but is handled by the
    #: rate-limit path first, which honours `Retry-After`.
    retry_on_status: Tuple[int, ...] = (408, 425, 429, 500, 502, 503, 504)
    #: Whether to obey a `Retry-After` header instead of computed backoff.
    respect_retry_after: bool = True
    #: Upper bound on an honoured `Retry-After`, so a hostile or mistaken header
    #: cannot stall an ingestion run indefinitely.
    max_retry_after_seconds: float = Field(default=120.0, ge=0.0)

    def backoff_for(self, attempt: int) -> float:
        """Delay before `attempt` (1-based), before jitter is applied."""
        if attempt < 1:
            raise ValueError("attempt is 1-based")
        delay = self.backoff_factor * (2 ** (attempt - 1))
        return min(delay, self.max_backoff_seconds)


class RateLimitConfig(BaseModel):
    """One provider's rate limits, plus the headers it reports them in.

    Providers express limits differently — NASA documents an hourly quota and
    reports remaining quota in a header, CelesTrak asks for one request per
    two-hour update rather than a rate. Both are expressible here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Hourly quota, when the provider documents one.
    requests_per_hour: Optional[int] = Field(default=None, ge=1)
    #: Short-term ceiling, to avoid bursting even when the hourly quota allows it.
    requests_per_second: Optional[float] = Field(default=None, gt=0.0)
    #: Maximum concurrent in-flight requests to this provider.
    max_concurrent: int = Field(default=4, ge=1)

    #: Response headers the provider uses to report quota, if any.
    limit_header: Optional[str] = None
    remaining_header: Optional[str] = None
    reset_header: Optional[str] = None

    #: Pause further requests when the remaining-quota header drops to or below
    #: this. Leaves headroom for health checks and interactive queries.
    low_quota_threshold: int = Field(default=0, ge=0)

    #: Human-readable statement of the provider's published policy.
    policy_note: Optional[str] = None

    @property
    def min_interval_seconds(self) -> float:
        """Smallest gap between consecutive requests implied by the limits."""
        intervals = [0.0]
        if self.requests_per_second:
            intervals.append(1.0 / self.requests_per_second)
        if self.requests_per_hour:
            intervals.append(3600.0 / float(self.requests_per_hour))
        return max(intervals)


class ProviderConfig(BaseModel):
    """Everything the HTTP layer needs to talk to one provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    timeout_seconds: float = Field(default=20.0, gt=0.0)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)

    #: Static headers sent with every request. Never put credentials here —
    #: use `api_key` so the redaction logic knows what to hide.
    headers: Dict[str, str] = Field(default_factory=dict)
    user_agent: str = "LostIntoSpacE/0.1 (educational space simulation project)"

    #: Environment variable names checked, in order, for this provider's key.
    api_key_env: Tuple[str, ...] = ()
    #: Resolved key. Populated by `from_env`; never logged or serialized out.
    api_key: Optional[str] = Field(default=None, repr=False)
    #: Query parameter the key travels in, when the provider uses one.
    api_key_param: Optional[str] = None
    #: Header the key travels in, when the provider uses one.
    api_key_header: Optional[str] = None
    #: True when the provider cannot be used at all without credentials.
    requires_auth: bool = False

    verify_ssl: bool = True
    #: Link to the provider's own API documentation.
    docs_url: Optional[str] = None

    @model_validator(mode="after")
    def _check(self) -> "ProviderConfig":
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError(
                "base_url must be absolute, got {0!r}".format(self.base_url)
            )
        if self.api_key and not (self.api_key_param or self.api_key_header):
            raise ValueError(
                "an api_key needs api_key_param or api_key_header so the transport "
                "knows how to send it"
            )
        for key in self.headers:
            if key.lower() in ("authorization", "x-api-key", "api-key"):
                raise ValueError(
                    "credential header {0!r} must be configured via api_key/"
                    "api_key_header, not headers, so redaction applies".format(key)
                )
        return self

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key)

    def resolve_from_env(self) -> "ProviderConfig":
        """Return a copy with environment overrides and the API key applied.

        Called at adapter construction so a deployment can correct a limit or
        point at a different endpoint without a code change.
        """
        updates: Dict[str, object] = {}

        base_url = env_override(self.name, "BASE_URL")
        if base_url:
            updates["base_url"] = base_url

        timeout = _as_float(env_override(self.name, "TIMEOUT_SECONDS"))
        if timeout and timeout > 0:
            updates["timeout_seconds"] = timeout

        retry_updates: Dict[str, object] = {}
        attempts = _as_int(env_override(self.name, "MAX_ATTEMPTS"))
        if attempts and 1 <= attempts <= 10:
            retry_updates["max_attempts"] = attempts
        backoff = _as_float(env_override(self.name, "BACKOFF_FACTOR"))
        if backoff is not None and backoff >= 0:
            retry_updates["backoff_factor"] = backoff
        if retry_updates:
            updates["retry"] = self.retry.model_copy(update=retry_updates)

        limit_updates: Dict[str, object] = {}
        per_hour = _as_int(env_override(self.name, "REQUESTS_PER_HOUR"))
        if per_hour and per_hour >= 1:
            limit_updates["requests_per_hour"] = per_hour
        per_second = _as_float(env_override(self.name, "REQUESTS_PER_SECOND"))
        if per_second and per_second > 0:
            limit_updates["requests_per_second"] = per_second
        concurrent = _as_int(env_override(self.name, "MAX_CONCURRENT"))
        if concurrent and concurrent >= 1:
            limit_updates["max_concurrent"] = concurrent
        if limit_updates:
            updates["rate_limit"] = self.rate_limit.model_copy(update=limit_updates)

        key = self._resolve_api_key()
        if key:
            updates["api_key"] = key

        return self.model_copy(update=updates) if updates else self

    def _resolve_api_key(self) -> Optional[str]:
        candidates: List[str] = list(self.api_key_env)
        candidates.append("{0}{1}_API_KEY".format(ENV_PREFIX, self.name.upper()))
        for variable in candidates:
            value = os.environ.get(variable)
            if value:
                return value
        return self.api_key
