"""Provider abstraction. All vendor SDK code lives in this package.

`generate`, `stream`, `health_check` — the three operations everything above
depends on. Credentials are read from environment variables here and nowhere
else.
"""

from .base import (
    AICompletion,
    AIMessage,
    AIProvider,
    AIProviderAuthError,
    AIProviderError,
    AIProviderRateLimited,
    AIProviderTimeout,
    AIProviderUnavailable,
    AIRequest,
    MalformedProviderOutput,
    ProviderInfo,
    Role,
    StreamChunk,
)
from .mock import ExtractiveProvider, MockAIProvider
from .registry import (
    AI_PROVIDER_ENV,
    available_providers,
    build_provider,
    describe_configuration,
    resolve_provider_name,
)

__all__ = [
    "AIProvider",
    "AIRequest",
    "AIMessage",
    "AICompletion",
    "StreamChunk",
    "ProviderInfo",
    "Role",
    "AIProviderError",
    "AIProviderTimeout",
    "AIProviderUnavailable",
    "AIProviderAuthError",
    "AIProviderRateLimited",
    "MalformedProviderOutput",
    "MockAIProvider",
    "ExtractiveProvider",
    "build_provider",
    "available_providers",
    "resolve_provider_name",
    "describe_configuration",
    "AI_PROVIDER_ENV",
]
