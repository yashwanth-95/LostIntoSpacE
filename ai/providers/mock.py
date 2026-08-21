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
import re
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Sequence, Union

from contracts._time import utc_now

from ..safety.sanitize import CONTEXT_FENCE_CLOSE, CONTEXT_FENCE_OPEN
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

    #: Words too common to indicate relevance. Kept short deliberately: a long
    #: stop list starts discarding domain terms like "mass" and "burn".
    _STOPWORDS = frozenset(
        """a an and are as at be by did do does for from has have how in is it its
        my of on or that the this to was were what when where which why will with
        your you""".split()
    )

    def __init__(self, max_sentences: int = 4, context_marker: Optional[str] = None):
        self.max_sentences = max(1, max_sentences)
        self.context_marker = context_marker or self.CONTEXT_MARKER
        self.call_count = 0

    @staticmethod
    def _question_of(request: AIRequest) -> str:
        """The user's last message, which is the question being asked."""
        for message in reversed(request.messages):
            if getattr(message.role, "value", message.role) == "user":
                text = message.content
                # Strip the fenced context so the question's own words are not
                # swamped by the evidence quoted beneath it.
                return text.split(CONTEXT_FENCE_OPEN, 1)[0]
        return ""

    #: Suffixes stripped when matching, longest first. Crude, and enough: it is
    #: what makes "why did my rocket fail" match a context line about a
    #: "failure", which is the single most common question this product is
    #: asked. A real stemmer would be a dependency bought for one rule.
    _SUFFIXES = ("ures", "ing", "ure", "ed", "es", "s")

    def _stem(self, word: str) -> str:
        for suffix in self._SUFFIXES:
            if len(word) > len(suffix) + 2 and word.endswith(suffix):
                return word[: -len(suffix)]
        return word

    #: Question words mapped onto the vocabulary the context is written in.
    #: A user asks "how high did it go"; the telemetry says "Maximum altitude".
    #: Without this the two never meet, and the offline answer falls back to
    #: listing section titles.
    _SYNONYMS = {
        "high": ("altitude", "apogee"),
        "height": ("altitude",),
        "apoge": ("altitude", "apoapsi"),
        "fast": ("speed", "velocity"),
        "quick": ("speed", "velocity"),
        "heavy": ("mass",),
        "weight": ("mass", "twr"),
        "unstable": ("stability", "margin", "caliber"),
        "stabl": ("stability", "margin", "caliber"),
        "tumbl": ("stability", "margin"),
        "wind": ("crosswind", "gust", "lateral"),
        "explod": ("failure", "structural"),
        "crash": ("failure", "impact"),
        "thrust": ("twr", "propulsion"),
        "engine": ("thrust", "propulsion", "isp"),
        "fuel": ("propellant",),
    }

    def _terms(self, text: str) -> set:
        words = re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text.lower())
        terms = {self._stem(word) for word in words if word not in self._STOPWORDS}
        for term in tuple(terms):
            terms.update(self._stem(alias) for alias in self._SYNONYMS.get(term, ()))
        return terms

    def _extract(self, request: AIRequest) -> str:
        """Quote the lines of context that actually bear on the question.

        The original implementation kept only lines beginning ``[Sn]`` — the
        item *headers*. That was fine when every context item was a single line
        of prose, and useless once items became structured records, because the
        header of "Current rocket design" says nothing about the rocket. Asked
        why their vehicle failed, a user got a list of section titles.

        So: lines are scored on term overlap with the question, headers are
        carried down as attribution for the lines beneath them, and the best few
        are quoted with their citation label. Still incapable of inventing
        anything — every line emitted appeared verbatim in the context — but now
        the lines chosen are the ones asked about.
        """
        blocks = []
        for message in request.messages:
            if self.context_marker in message.content:
                blocks.append(message.content.split(self.context_marker, 1)[1])
        if not blocks:
            return "No context was supplied, so no grounded answer can be given."

        question_terms = self._terms(self._question_of(request))

        #: (score, order, label, line)
        scored: List[tuple] = []
        order = 0
        for block in blocks:
            label = ""
            for raw in block.splitlines():
                line = raw.strip()
                # Everything past the closing fence is prompt scaffolding, not
                # evidence. Reading on quotes the model's own instructions back
                # at the user, which is both wrong and faintly absurd.
                if line.startswith(CONTEXT_FENCE_CLOSE):
                    break
                if not line:
                    continue

                is_header = line.startswith("[") and "]" in line
                if is_header:
                    label = line[: line.index("]") + 1]
                    candidate = line
                else:
                    candidate = "{0} {1}".format(label, line).strip() if label else line

                overlap = len(question_terms & self._terms(line))
                # Lines the context itself flagged as significant win ties: they
                # are the ones stating a threshold was crossed.
                emphasis = 1 if line.startswith(("NOTE:", "Validation", "  - ")) else 0
                # A header names the evidence; it does not contain any. Ranking
                # it on term overlap puts "Current rocket design" above the
                # rocket's actual numbers for any question containing the word
                # "rocket", which is most of them.
                if is_header:
                    overlap = 0
                    emphasis = -1
                scored.append((overlap, emphasis, -order, label, candidate))
                order += 1

        if not scored:
            return "The supplied context does not contain a usable answer."

        best = sorted(scored, key=lambda item: item[:3], reverse=True)[: self.max_sentences]
        if not any(item[0] for item in best):
            # Nothing in the context bears on the question. Listing the headers
            # is the honest answer: it says what evidence was available without
            # pretending any of it was relevant.
            headers = [
                candidate
                for overlap, emphasis, _, _, candidate in sorted(scored, key=lambda i: -i[2])
                if emphasis < 0
            ]
            return "\n".join(headers[: self.max_sentences]) or best[0][4]

        # Restore reading order among the selected lines.
        best = sorted(best, key=lambda item: -item[2])
        return "\n".join(candidate for _, _, _, _, candidate in best)

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
