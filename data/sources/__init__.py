"""External space-data source adapters.

Every provider is reached through the single `SpaceDataSource` interface, and
every HTTP concern — timeout, retry, backoff, rate limiting, header handling,
response validation and credential redaction — lives in `http.py` rather than in
individual adapters.

Adapters return raw and parsed source records. They never write to a database
and never build canonical models directly; normalization is a separate stage
(see docs/PERSON4_DATA_ARCHITECTURE.md §2).
"""

from .base import (
    Capability,
    HealthStatus,
    SourceInfo,
    SourceQuery,
    SourceRecord,
    SourceResultPage,
    SpaceDataSource,
)
from .celestrak import PROVENANCE_LABEL, CelestrakSource
from .config import ProviderConfig, RateLimitConfig, RetryConfig
from .errors import (
    RateLimitExceededError,
    SourceAuthError,
    SourceConfigurationError,
    SourceError,
    SourceNotFoundError,
    SourceResponseError,
    SourceTimeoutError,
    SourceUnavailableError,
    UnsupportedOperationError,
)
from .esa import CopernicusSource
from .exoplanet_archive import ExoplanetArchiveSource
from .http import HttpClient, RawResponse, redact_mapping, redact_url
from .isro import BhoonidhiSource
from .jpl import JplHorizonsSource, JplSbdbSource
from .mpc import MpcObservationsSource, MpcOrbitsSource
from .nasa import NasaApodSource, NasaEonetSource, NasaNeoWsSource, NasaNtrsSource
from .ratelimit import RateLimiter
from .registry import (
    AUTHORITY_BY_CAPABILITY,
    SOURCE_CLASSES,
    all_source_info,
    build_source,
    get_source_class,
    preferred_source_for,
    sources_with_capability,
)

__all__ = [
    # interface
    "SpaceDataSource",
    "SourceInfo",
    "SourceQuery",
    "SourceRecord",
    "SourceResultPage",
    "HealthStatus",
    "Capability",
    # http / config
    "HttpClient",
    "RawResponse",
    "redact_url",
    "redact_mapping",
    "ProviderConfig",
    "RateLimitConfig",
    "RetryConfig",
    "RateLimiter",
    # errors
    "SourceError",
    "SourceConfigurationError",
    "SourceUnavailableError",
    "SourceTimeoutError",
    "RateLimitExceededError",
    "SourceAuthError",
    "SourceNotFoundError",
    "SourceResponseError",
    "UnsupportedOperationError",
    # adapters
    "NasaApodSource",
    "NasaNeoWsSource",
    "NasaEonetSource",
    "NasaNtrsSource",
    "JplSbdbSource",
    "JplHorizonsSource",
    "MpcOrbitsSource",
    "MpcObservationsSource",
    "ExoplanetArchiveSource",
    "CelestrakSource",
    "CopernicusSource",
    "BhoonidhiSource",
    "PROVENANCE_LABEL",
    # registry
    "SOURCE_CLASSES",
    "AUTHORITY_BY_CAPABILITY",
    "get_source_class",
    "build_source",
    "all_source_info",
    "sources_with_capability",
    "preferred_source_for",
]
