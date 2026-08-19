"""The `AIProvider` interface.

Three operations: `generate`, `stream`, `health_check`.

**Provider SDK code stays behind this boundary.** Nothing above `ai/providers/`
imports a vendor SDK, references a vendor model id, or knows a vendor's error
taxonomy. Everything vendor-shaped is normalized here into the errors and value
objects declared in this module, so swapping providers touches one directory.

**Keys never leave the server.** Credentials are read from environment
variables at construction, are never accepted as function arguments, are never
placed in a URL, and are redacted from every error and log line. No provider
field carrying a key is serialized.
"""

import abc
import os
from enum import Enum
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from contracts._time import utc_now

__all__ = [
    "Role",
    "AIMessage",
    "AIRequest",
    "AICompletion",
    "StreamChunk",
    "ProviderInfo",
    "AIProviderError",
    "AIProviderTimeout",
    "AIProviderUnavailable",
    "AIProviderAuthError",
    "AIProviderRateLimited",
    "MalformedProviderOutput",
    "AIProvider",
]


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class AIMessage(BaseModel):
    """One message in a conversation."""

    model_config = ConfigDict(extra="forbid")

    role: Role = Role.USER
    content: str = ""

    @field_validator("content")
    @classmethod
    def _not_none(cls, value: Optional[str]) -> str:
        return value or ""


class AIRequest(BaseModel):
    """A generation request, in provider-neutral terms."""

    model_config = ConfigDict(extra="forbid")

    messages: List[AIMessage] = Field(default_factory=list)
    #: Kept separate from `messages` so a provider that has a dedicated system
    #: parameter can use it, and one that does not can prepend it.
    system: Optional[str] = None
    max_tokens: int = Field(default=1024, ge=1, le=100_000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    stop_sequences: List[str] = Field(default_factory=list)
    #: Per-request override; falls back to the provider's configured timeout.
    timeout_seconds: Optional[float] = None
    #: Opaque provider-specific options. Deliberately not typed: anything the
    #: layers above need should become a first-class field instead of leaking
    #: a vendor's parameter names upward.
    provider_options: Dict[str, Any] = Field(default_factory=dict)

    def prompt_text(self) -> str:
        """Flattened text, for providers with no chat surface and for hashing."""
        parts = []
        if self.system:
            parts.append("[system] {0}".format(self.system))
        for message in self.messages:
            parts.append("[{0}] {1}".format(message.role.value, message.content))
        return "\n".join(parts)


class AICompletion(BaseModel):
    """A finished generation."""

    model_config = ConfigDict(extra="forbid")

    text: str
    model_id: str = ""
    provider: str = ""
    #: Why generation ended: "stop", "max_tokens", "stop_sequence", …
    finish_reason: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms: Optional[float] = None
    #: Non-authoritative provider detail. Never contains credentials.
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def was_truncated(self) -> bool:
        """True when output stopped at the token cap rather than completing.

        Load-bearing: a truncated answer can end mid-citation, and treating it
        as complete would drop the evidence for a claim already written.
        """
        return self.finish_reason in ("max_tokens", "length")


class StreamChunk(BaseModel):
    """One incremental piece of a streamed generation."""

    model_config = ConfigDict(extra="forbid")

    text: str = ""
    #: True for the terminal chunk. Carries the finish reason and usage.
    is_final: bool = False
    finish_reason: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class ProviderInfo(BaseModel):
    """What a provider is and what it can do."""

    model_config = ConfigDict(extra="forbid")

    name: str
    model_id: str
    supports_streaming: bool = True
    max_context_tokens: Optional[int] = None
    #: Which environment variable supplies the key. The value is never read
    #: into this object.
    api_key_env: Optional[str] = None
    requires_api_key: bool = True
    #: True when the provider makes no network call — the mock and any local
    #: implementation. Callers use this to decide whether a test is offline.
    is_offline: bool = False


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------
class AIProviderError(Exception):
    """Base class. Every vendor failure is normalized into one of these."""

    def __init__(self, message: str, provider: str = "", retryable: bool = False):
        super(AIProviderError, self).__init__(message)
        self.provider = provider
        #: Whether retrying the identical request could plausibly succeed.
        self.retryable = retryable

    def __str__(self) -> str:
        base = super(AIProviderError, self).__str__()
        return "[{0}] {1}".format(self.provider, base) if self.provider else base


class AIProviderTimeout(AIProviderError):
    """The provider did not respond within the deadline."""

    def __init__(self, message: str, provider: str = ""):
        super(AIProviderTimeout, self).__init__(message, provider, retryable=True)


class AIProviderUnavailable(AIProviderError):
    """The provider is down, overloaded, or returned a server error."""

    def __init__(self, message: str, provider: str = ""):
        super(AIProviderUnavailable, self).__init__(message, provider, retryable=True)


class AIProviderRateLimited(AIProviderError):
    """The provider refused the request for rate reasons."""

    def __init__(self, message: str, provider: str = "",
                 retry_after_seconds: Optional[float] = None):
        super(AIProviderRateLimited, self).__init__(message, provider, retryable=True)
        self.retry_after_seconds = retry_after_seconds


class AIProviderAuthError(AIProviderError):
    """The credential is missing, malformed or rejected.

    Never retryable, and its message never contains the credential.
    """

    def __init__(self, message: str, provider: str = ""):
        super(AIProviderAuthError, self).__init__(message, provider, retryable=False)


class MalformedProviderOutput(AIProviderError):
    """The provider responded, but not in a shape that can be used.

    Its own class because it is not a transport failure: retrying may well
    produce the same garbage, and the caller usually wants to fall back rather
    than retry.
    """

    def __init__(self, message: str, provider: str = "", payload_excerpt: str = ""):
        super(MalformedProviderOutput, self).__init__(message, provider,
                                                      retryable=False)
        #: Trimmed excerpt for diagnosis. Truncated so a huge body cannot be
        #: dumped into a log.
        self.payload_excerpt = (payload_excerpt or "")[:500]


# ----------------------------------------------------------------------
# Interface
# ----------------------------------------------------------------------
class AIProvider(abc.ABC):
    """Interface every AI provider implements."""

    name = "abstract"

    @abc.abstractmethod
    async def generate(self, request: AIRequest) -> AICompletion:
        """Produce a complete generation."""

    @abc.abstractmethod
    def stream(self, request: AIRequest) -> AsyncIterator[StreamChunk]:
        """Yield incremental chunks.

        Returns an async iterator rather than being an `async def` generator so
        that implementations may choose either form.
        """

    @abc.abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Probe the provider. Reports rather than raising."""

    @abc.abstractmethod
    def get_info(self) -> ProviderInfo:
        """Describe this provider."""

    # -- credential handling ----------------------------------------------
    @staticmethod
    def read_api_key(
        env_names: Sequence[str], provider: str = "", required: bool = True
    ) -> Optional[str]:
        """Read a credential from the environment, and only from there.

        There is deliberately no parameter to pass a key in directly. A key
        that can be passed as an argument ends up in a config file, a log line,
        or a request body sooner or later.
        """
        for name in env_names:
            value = os.environ.get(name)
            if value and value.strip():
                return value.strip()
        if required:
            raise AIProviderAuthError(
                "no API key found; set one of {0}. Keys are read from the "
                "environment only and are never accepted as arguments.".format(
                    ", ".join(env_names)
                ),
                provider=provider,
            )
        return None

    async def aclose(self) -> None:
        """Release resources. Safe to call more than once."""
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()
