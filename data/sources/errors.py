"""Error taxonomy for external data sources.

Every failure mode is a distinct type so callers can react correctly: an
ingestion run should retry a `SourceUnavailableError`, back off on a
`RateLimitExceededError`, skip a `SourceNotFoundError`, and stop entirely on a
`SourceConfigurationError`. Collapsing these into one exception is what makes a
pipeline either retry forever or give up too early.

Every error carries the source name so a multi-source run can report which
provider failed without unwrapping the traceback.
"""

from typing import Optional

__all__ = [
    "SourceError",
    "SourceConfigurationError",
    "SourceUnavailableError",
    "SourceTimeoutError",
    "RateLimitExceededError",
    "SourceAuthError",
    "SourceNotFoundError",
    "SourceResponseError",
    "UnsupportedOperationError",
]


class SourceError(Exception):
    """Base class for anything that goes wrong talking to an external source."""

    #: Whether retrying the same request could plausibly succeed.
    retryable = False

    def __init__(
        self,
        message: str,
        source_name: Optional[str] = None,
        status_code: Optional[int] = None,
        url: Optional[str] = None,
    ):
        self.source_name = source_name
        self.status_code = status_code
        #: Always a redacted URL — see `data.sources.http.redact_url`.
        self.url = url
        prefix = "[{0}] ".format(source_name) if source_name else ""
        super().__init__("{0}{1}".format(prefix, message))


class SourceConfigurationError(SourceError):
    """The adapter cannot run as configured — missing key, bad base URL.

    Not retryable: retrying a misconfiguration just wastes the provider's quota.
    """


class SourceUnavailableError(SourceError):
    """Network failure or a 5xx from the provider."""

    retryable = True


class SourceTimeoutError(SourceUnavailableError):
    """The request exceeded the configured timeout."""

    retryable = True


class RateLimitExceededError(SourceError):
    """The provider refused the request because we are over quota.

    `retry_after` is populated from the `Retry-After` header when the provider
    sends one; honouring it is a condition of continued access.
    """

    retryable = True

    def __init__(self, message: str, retry_after: Optional[float] = None, **kwargs):
        self.retry_after = retry_after
        super().__init__(message, **kwargs)


class SourceAuthError(SourceError):
    """401/403 — the credentials are missing, wrong, or lack authorization.

    Not retryable. For authorization-gated sources such as ISRO Bhoonidhi this
    is the expected outcome without credentials, and must be reported as such
    rather than presented as "no data".
    """


class SourceNotFoundError(SourceError):
    """The requested record does not exist at this source.

    A legitimate answer, not a malfunction: not every archive holds every object.
    """


class SourceResponseError(SourceError):
    """The response arrived but could not be parsed or failed validation."""


class UnsupportedOperationError(SourceError):
    """The adapter does not implement this capability.

    Raised deliberately rather than returning empty results, so a caller asking
    an exoplanet archive for satellite element sets gets an error instead of a
    silently empty list.
    """
