"""Google Gemini, behind the provider interface.

Talks to the Generative Language API over plain HTTP rather than through the
`google-generativeai` SDK. That is deliberate: the repository has no AI
dependency, the request shape needed here is three fields, and an SDK would
pull a transitive tree in for a JSON POST this file does in forty lines.

Everything vendor-shaped is normalised before it leaves: Gemini's `candidates`
become an :class:`AICompletion`, its HTTP statuses become the error taxonomy in
`base.py`, and its `finishReason` becomes the neutral values the RAG layer
checks for truncation. Nothing above `ai/providers/` learns that Gemini exists.

## Credentials

Read from the environment at construction, never accepted as an argument, and
sent in the ``x-goog-api-key`` header rather than in the query string — a key
in a URL ends up in access logs, proxy logs and browser history.

## Safety settings

The API's own content filters are left at their defaults. This assistant answers
questions about orbital mechanics and rocket propulsion, and a filter that
occasionally objects to the word "explosive" in a question about solid motors is
a smaller problem than one that has been turned off wholesale.

## Thinking

Current Gemini flash models reason before answering, and those thinking tokens
come out of the same output budget as the answer. Left alone, a 300-token
request spent 286 tokens thinking and 10 on the reply, then stopped at
`MAX_TOKENS` mid-word. Thinking is therefore disabled by default: the questions
here are short and the answer is already grounded in retrieved evidence, so
there is nothing for extended reasoning to add. Set `GEMINI_THINKING_BUDGET` to
a token count to turn it back on.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from .base import (
    AICompletion,
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

__all__ = [
    "GeminiProvider",
    "GEMINI_KEY_ENV",
    "GEMINI_MODEL_ENV",
    "DEFAULT_MODEL",
    "DEFAULT_MODELS",
]

#: Environment variables that may carry the key, in order of preference.
GEMINI_KEY_ENV = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "AI_API_KEY")

#: Overrides the model. Useful when a deployment is pinned to an older one.
GEMINI_MODEL_ENV = "GEMINI_MODEL"

#: Thinking tokens to allow. 0 disables it, which is the default here — see the
#: module docstring for why.
GEMINI_THINKING_ENV = "GEMINI_THINKING_BUDGET"

#: Models to try, in order. Fast ones first: this assistant answers short
#: grounded questions, and a two-second reply is worth more than a marginally
#: better one that takes twenty.
#:
#: A list rather than a single id because the Generative Language API returns
#: 503 for individual overloaded models fairly often — during development
#: `gemini-flash-latest` failed three attempts in a row while `gemini-3.5-flash`
#: answered in 1.3 s. Falling through to the next model turns that from an
#: outage into a slightly slower answer.
#:
#: `-latest` aliases are included as a hedge against pinned ids being retired,
#: which is how this provider failed on its very first run.
DEFAULT_MODELS = ("gemini-3.5-flash", "gemini-flash-latest", "gemini-3.7-flash")

#: The first choice, for callers that want one name.
DEFAULT_MODEL = DEFAULT_MODELS[0]

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

#: Statuses worth retrying. Overload, not failure.
_TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})

#: How many extra attempts a transient status buys.
_TRANSIENT_RETRIES = 2

#: Base backoff between attempts. Unit: seconds.
_RETRY_BACKOFF_S = 0.6


def _int_env(name: str, default: int) -> int:
    """Read an integer from the environment, falling back on anything unparseable."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default

#: Gemini's finish reasons mapped onto the neutral vocabulary. `MAX_TOKENS`
#: must survive as a truncation signal: the RAG layer drops answers that ended
#: mid-citation, and losing that would let a claim keep its text but lose its
#: evidence.
_FINISH_REASONS = {
    "STOP": "stop",
    "MAX_TOKENS": "max_tokens",
    "SAFETY": "content_filter",
    "RECITATION": "content_filter",
    "OTHER": "error",
}


class GeminiProvider(AIProvider):
    """Generation via Google's Generative Language API."""

    name = "gemini"

    def __init__(
        self,
        model: Optional[str] = None,
        timeout_seconds: float = 45.0,
        thinking_budget: Optional[int] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        # Raises AIProviderAuthError when no key is present, which the registry
        # turns into a fallback to the extractive provider rather than a 500.
        self._api_key = self.read_api_key(GEMINI_KEY_ENV, provider=self.name, required=True)
        # An explicitly configured model is used alone: an operator who pinned a
        # model wants that model, and silently answering from a different one
        # would make the choice meaningless.
        configured = model or os.environ.get(GEMINI_MODEL_ENV, "").strip()
        self.models = (configured,) if configured else DEFAULT_MODELS
        self.model = self.models[0]
        self.timeout_seconds = timeout_seconds
        self.thinking_budget = (
            thinking_budget
            if thinking_budget is not None
            else _int_env(GEMINI_THINKING_ENV, 0)
        )
        self._client = client
        self._owns_client = client is None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # -- request shaping ---------------------------------------------------

    def _payload(self, request: AIRequest) -> Dict[str, Any]:
        """Translate a neutral request into Gemini's schema.

        Gemini has no `assistant` role — it calls the same thing `model` — and
        it takes the system instruction as a separate top-level field rather
        than as a message.
        """
        contents: List[Dict[str, Any]] = []
        for message in request.messages:
            if message.role is Role.SYSTEM:
                # Folded into systemInstruction below; a system message left in
                # `contents` is rejected.
                continue
            role = "model" if message.role is Role.ASSISTANT else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})

        if not contents:
            contents = [{"role": "user", "parts": [{"text": request.prompt_text()}]}]

        system_parts = [m.content for m in request.messages if m.role is Role.SYSTEM]
        if request.system:
            system_parts.insert(0, request.system)

        generation: Dict[str, Any] = {
            "temperature": request.temperature,
            "maxOutputTokens": request.max_tokens,
        }
        # Thinking tokens are drawn from maxOutputTokens, so leaving this
        # unset lets the model reason its way past the budget and truncate the
        # answer it was about to give.
        if self.thinking_budget <= 0:
            generation["thinkingConfig"] = {"thinkingBudget": 0}
        else:
            generation["thinkingConfig"] = {"thinkingBudget": self.thinking_budget}

        payload: Dict[str, Any] = {"contents": contents, "generationConfig": generation}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        if request.stop_sequences:
            payload["generationConfig"]["stopSequences"] = request.stop_sequences[:5]
        return payload

    def _headers(self) -> Dict[str, str]:
        return {
            "x-goog-api-key": self._api_key or "",
            "Content-Type": "application/json",
        }

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Normalise an HTTP failure into this project's error taxonomy.

        The response body is never included. Google echoes request metadata in
        error payloads, and an error message that ends up in a log should not be
        able to carry any of it.
        """
        status = response.status_code
        if status < 400:
            return
        if status in (401, 403):
            raise AIProviderAuthError(
                "Gemini rejected the API key ({0}).".format(status), provider=self.name
            )
        if status == 404:
            # Almost always a model name this key cannot reach, not a routing
            # fault. Say which model, because the fix is to change it.
            raise AIProviderUnavailable(
                "Gemini has no model {0!r} available to this key. Set {1} to one "
                "the key can reach.".format(self.model, GEMINI_MODEL_ENV),
                provider=self.name,
            )
        if status == 429:
            raise AIProviderRateLimited("Gemini rate limit reached.", provider=self.name)
        if status in (500, 502, 503, 504):
            raise AIProviderUnavailable(
                "Gemini is unavailable ({0}).".format(status), provider=self.name
            )
        raise AIProviderError(
            "Gemini returned {0}.".format(status), provider=self.name
        )

    @staticmethod
    def _text_of(payload: Dict[str, Any]) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            return ""
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(part.get("text", "") for part in parts)

    # -- interface ---------------------------------------------------------

    async def _post(self, model: str, payload: Dict[str, Any], timeout: float):
        """One model, with retries for transient overload.

        Returns the response, or `None` when every attempt hit a transient
        status — which tells the caller to try the next model rather than to
        give up.
        """
        client = await self._http()
        url = "{0}/models/{1}:generateContent".format(_BASE_URL, model)

        for attempt in range(_TRANSIENT_RETRIES + 1):
            try:
                response = await client.post(
                    url, json=payload, headers=self._headers(), timeout=timeout
                )
            except httpx.TimeoutException:
                if attempt < _TRANSIENT_RETRIES:
                    await asyncio.sleep(_RETRY_BACKOFF_S * (attempt + 1))
                    continue
                return None
            except httpx.HTTPError as exc:
                # A transport failure is not model-specific, so trying another
                # model would just wait longer for the same outcome.
                raise AIProviderUnavailable(
                    "Gemini is unreachable.", provider=self.name
                ) from exc

            if response.status_code in _TRANSIENT_STATUSES and attempt < _TRANSIENT_RETRIES:
                await asyncio.sleep(_RETRY_BACKOFF_S * (attempt + 1))
                continue
            return response

        return None

    async def generate(self, request: AIRequest) -> AICompletion:
        started = time.perf_counter()
        payload = self._payload(request)
        timeout = request.timeout_seconds or self.timeout_seconds

        response = None
        model_used = self.models[0]
        for model in self.models:
            model_used = model
            response = await self._post(model, payload, timeout)
            if response is None:
                # Every attempt on this model hit a transient status. Another
                # model is very often fine — Google overloads them individually.
                continue
            if response.status_code == 404 and len(self.models) > 1:
                # This key cannot reach that model. Try the next rather than
                # failing, since the fallback list exists for exactly this.
                continue
            break

        if response is None:
            raise AIProviderUnavailable(
                "Gemini is overloaded; every configured model ({0}) failed to "
                "respond.".format(", ".join(self.models)),
                provider=self.name,
            )

        # Report against whichever model actually answered.
        self.model = model_used
        self._raise_for_status(response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise MalformedProviderOutput(
                "Gemini returned a body that is not JSON.", provider=self.name
            ) from exc

        text = self._text_of(payload)
        candidates = payload.get("candidates") or []
        finish = (candidates[0].get("finishReason") if candidates else None) or "STOP"
        usage = payload.get("usageMetadata") or {}

        if not text and _FINISH_REASONS.get(finish) == "content_filter":
            # An empty body with a filter reason is a refusal, not a fault. The
            # grounding layer treats an empty answer as "could not answer",
            # which is the correct outcome — but say why.
            text = (
                "The model declined to answer this question. Try rephrasing it, "
                "or ask about the underlying engineering directly."
            )

        return AICompletion(
            text=text,
            model_id=model_used,
            provider=self.name,
            finish_reason=_FINISH_REASONS.get(finish, "stop"),
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            raw_metadata={"finish_reason_raw": finish},
        )

    async def _stream(self, request: AIRequest) -> AsyncIterator[StreamChunk]:
        """Stream by chunking a completed generation.

        Gemini's streaming endpoint returns a JSON array delivered
        incrementally, which needs a partial-JSON parser to consume properly.
        Nothing in this product streams yet — the assistant renders a finished
        answer with its citations attached, and a half-rendered citation is
        worse than a short wait. When streaming is wanted, this is the one
        method to replace.
        """
        completion = await self.generate(request)
        yield StreamChunk(text=completion.text)
        yield StreamChunk(
            text="",
            is_final=True,
            finish_reason=completion.finish_reason,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
        )

    def stream(self, request: AIRequest) -> AsyncIterator[StreamChunk]:
        return self._stream(request)

    async def health_check(self) -> Dict[str, Any]:
        """Probe with the cheapest possible generation. Reports, never raises."""
        try:
            completion = await self.generate(
                AIRequest(
                    messages=[{"role": Role.USER, "content": "Reply with the word: ok"}],
                    max_tokens=8,
                    temperature=0.0,
                    timeout_seconds=10.0,
                )
            )
        except AIProviderError as exc:
            return {
                "healthy": False,
                "provider": self.name,
                "model_id": self.model,
                # `str(exc)` here is this project's own message, not Google's.
                "reason": str(exc),
            }
        return {
            "healthy": bool(completion.text),
            "provider": self.name,
            "model_id": self.model,
            "latency_ms": completion.latency_ms,
        }

    def get_info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            model_id=self.models[0],
            supports_streaming=True,
            requires_api_key=True,
            is_offline=False,
        )
