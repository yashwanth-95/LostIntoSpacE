"""A scriptable in-process provider.

Two uses:

* **Tests.** Every failure mode a real provider can produce — timeout, outage,
  rate limit, auth rejection, malformed output — is scriptable here, so the
  layers above are tested against all of them without a network.
* **Offline operation.** With no API key configured, the system still runs:
  retrieval, grounding and citation validation all work, and the answer is
  assembled from retrieved context rather than generated. That degrades
  honestly instead of failing, and it is why the RAG layer's behaviour can be
  measured with no vendor account at all.
"""

import asyncio
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Sequence, Union

from contracts._time import utc_now

from ..safety.sanitize import CONTEXT_FENCE_OPEN
from .base import (
    AICompletion,
    AIMessage,
    AIProvider,
    AIProviderError,
    AIProviderTimeout,
    AIRequest,
    MalformedProviderOutput,
    ProviderInfo,
    Role,
    StreamChunk,
)

__all__ = ["MockAIProvider", "ExtractiveProvider"]


class MockAIProvider(AIProvider):
    """Returns scripted responses, or raises scripted errors."""

    name = "mock"

    def __init__(
        self,
        responses: Optional[Sequence[Union[str, Exception]]] = None,
        model_id: str = "mock-model-v1",
        latency_seconds: float = 0.0,
        chunk_size: int = 24,
        default_response: str = "Mock response.",
        responder: Optional[Callable[[AIRequest], str]] = None,
    ):
        #: Consumed in order; the last one repeats once exhausted. An
        #: `Exception` in the list is raised instead of returned.
        self.responses: List[Union[str, Exception]] = list(responses or [])
        self.model_id = model_id
        self.latency_seconds = latency_seconds
        self.chunk_size = max(1, chunk_size)
        self.default_response = default_response
        #: Callable alternative to a fixed script, for prompt-dependent replies.
        self.responder = responder

        #: Every request received, for assertions about what was actually sent.
        self.requests: List[AIRequest] = []
        self.call_count = 0
        self.closed = False

    # -- scripting ---------------------------------------------------------
    def queue(self, *responses: Union[str, Exception]) -> "MockAIProvider":
        self.responses.extend(responses)
        return self

    def _next_response(self, request: AIRequest) -> str:
        if self.responder is not None:
            return self.responder(request)
        if not self.responses:
            return self.default_response
        #: Keep the last entry so a test that makes more calls than it scripted
        #: gets a predictable answer rather than an IndexError.
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item

    # -- interface ---------------------------------------------------------
    async def generate(self, request: AIRequest) -> AICompletion:
        self.requests.append(request)
        self.call_count += 1
        if self.latency_seconds:
            await asyncio.sleep(self.latency_seconds)
        text = self._next_response(request)
        return AICompletion(
            text=text,
            model_id=self.model_id,
            provider=self.name,
            finish_reason="stop",
            input_tokens=len(request.prompt_text().split()),
            output_tokens=len(text.split()),
            latency_ms=self.latency_seconds * 1000.0,
        )

    async def _stream(self, request: AIRequest) -> AsyncIterator[StreamChunk]:
        self.requests.append(request)
        self.call_count += 1
        if self.latency_seconds:
            await asyncio.sleep(self.latency_seconds)
        text = self._next_response(request)
        for start in range(0, len(text), self.chunk_size):
            yield StreamChunk(text=text[start:start + self.chunk_size])
        yield StreamChunk(
            text="",
            is_final=True,
            finish_reason="stop",
            output_tokens=len(text.split()),
        )

    def stream(self, request: AIRequest) -> AsyncIterator[StreamChunk]:
        return self._stream(request)

    async def health_check(self) -> Dict[str, Any]:
        try:
            await self.generate(
                AIRequest(messages=[AIMessage(role=Role.USER, content="ping")])
            )
        except Exception as exc:  # noqa: BLE001 - health checks report
            return {"healthy": False, "provider": self.name, "detail": str(exc)}
        return {"healthy": True, "provider": self.name, "model_id": self.model_id}

    def get_info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            model_id=self.model_id,
            supports_streaming=True,
            requires_api_key=False,
            api_key_env=None,
            is_offline=True,
        )

    async def aclose(self) -> None:
        self.closed = True


class ExtractiveProvider(AIProvider):
    """Answers by quoting retrieved context, never by generating prose.

    The offline fallback. It cannot hallucinate, because it emits only text
    that appeared in the context it was given, with the citation labels already
    attached. The answers read like extracts rather than explanations — which
    is the honest trade: without a language model the system can still ground,
    cite and refuse, it just cannot phrase.

    Used when no API key is configured, so the product degrades to "correct but
    terse" rather than to "unavailable".
    """

    name = "extractive"

    #: The fence the RAG layer wraps context in. Imported rather than
    #: redeclared: two copies of a delimiter drift apart, and when they do this
    #: provider silently finds no context and answers nothing — which is
    #: exactly the bug this constant previously caused.
    CONTEXT_MARKER = CONTEXT_FENCE_OPEN

    def __init__(self, max_sentences: int = 4, context_marker: Optional[str] = None):
        self.max_sentences = max(1, max_sentences)
        self.context_marker = context_marker or self.CONTEXT_MARKER
        self.call_count = 0

    def _extract(self, request: AIRequest) -> str:
        blocks = []
        for message in request.messages:
            if self.context_marker in message.content:
                blocks.append(message.content.split(self.context_marker, 1)[1])
        if not blocks:
            return (
                "No context was supplied, so no grounded answer can be given."
            )

        lines: List[str] = []
        for block in blocks:
            for raw in block.splitlines():
                line = raw.strip()
                #: Context items arrive as "[S1] title — text".
                if line.startswith("[") and "]" in line:
                    lines.append(line)
                if len(lines) >= self.max_sentences:
                    break
        if not lines:
            return "The supplied context does not contain a usable answer."
        return "\n".join(lines)

    async def generate(self, request: AIRequest) -> AICompletion:
        self.call_count += 1
        text = self._extract(request)
        return AICompletion(
            text=text,
            model_id="extractive-v1",
            provider=self.name,
            finish_reason="stop",
            output_tokens=len(text.split()),
        )

    async def _stream(self, request: AIRequest) -> AsyncIterator[StreamChunk]:
        completion = await self.generate(request)
        yield StreamChunk(text=completion.text)
        yield StreamChunk(text="", is_final=True, finish_reason="stop")

    def stream(self, request: AIRequest) -> AsyncIterator[StreamChunk]:
        return self._stream(request)

    async def health_check(self) -> Dict[str, Any]:
        return {"healthy": True, "provider": self.name, "model_id": "extractive-v1"}

    def get_info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            model_id="extractive-v1",
            supports_streaming=True,
            requires_api_key=False,
            is_offline=True,
        )
