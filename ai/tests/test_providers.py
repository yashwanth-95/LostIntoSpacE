"""AI provider interface: success, streaming, failures, and key handling."""

import asyncio
import os

import pytest

from ai.providers import (
    AICompletion,
    AIMessage,
    AIProvider,
    AIProviderAuthError,
    AIProviderError,
    AIProviderRateLimited,
    AIProviderTimeout,
    AIProviderUnavailable,
    AIRequest,
    ExtractiveProvider,
    MalformedProviderOutput,
    MockAIProvider,
    Role,
    StreamChunk,
    available_providers,
    build_provider,
    describe_configuration,
    resolve_provider_name,
)
from ai.providers.gemini import GEMINI_KEY_ENV
from ai.providers.registry import AI_PROVIDER_ENV


def request(text="Why is the sky dark at night?", **kwargs):
    return AIRequest(messages=[AIMessage(role=Role.USER, content=text)], **kwargs)


async def collect(provider, req):
    chunks = []
    async for chunk in provider.stream(req):
        chunks.append(chunk)
    return chunks


class TestInterface:
    def test_mock_implements_the_interface(self):
        assert isinstance(MockAIProvider(), AIProvider)

    def test_extractive_implements_the_interface(self):
        assert isinstance(ExtractiveProvider(), AIProvider)

    def test_required_operations_are_abstract(self):
        for method in ("generate", "stream", "health_check", "get_info"):
            assert getattr(AIProvider, method).__isabstractmethod__, method

    def test_info_describes_the_provider(self):
        info = MockAIProvider(model_id="m1").get_info()
        assert info.name == "mock"
        assert info.model_id == "m1"
        assert info.supports_streaming is True
        assert info.is_offline is True


class TestGenerate:
    async def test_success(self):
        provider = MockAIProvider(responses=["Because the universe is finite."])
        completion = await provider.generate(request())
        assert completion.text == "Because the universe is finite."
        assert completion.provider == "mock"
        assert completion.finish_reason == "stop"

    async def test_records_the_request(self):
        provider = MockAIProvider()
        await provider.generate(request("a question"))
        assert provider.call_count == 1
        assert provider.requests[0].messages[0].content == "a question"

    async def test_scripted_responses_are_consumed_in_order(self):
        provider = MockAIProvider(responses=["first", "second", "third"])
        assert (await provider.generate(request())).text == "first"
        assert (await provider.generate(request())).text == "second"
        assert (await provider.generate(request())).text == "third"

    async def test_last_response_repeats_when_the_script_runs_out(self):
        provider = MockAIProvider(responses=["only"])
        await provider.generate(request())
        assert (await provider.generate(request())).text == "only"

    async def test_responder_can_depend_on_the_prompt(self):
        provider = MockAIProvider(
            responder=lambda req: "echo: {0}".format(req.messages[0].content)
        )
        assert (await provider.generate(request("hi"))).text == "echo: hi"

    async def test_token_counts_are_reported(self):
        completion = await MockAIProvider(responses=["one two three"]).generate(
            request()
        )
        assert completion.output_tokens == 3
        assert completion.input_tokens is not None

    async def test_truncation_is_detectable(self):
        """A truncated answer can end mid-citation and must not read as done."""
        completion = AICompletion(text="partial", finish_reason="max_tokens")
        assert completion.was_truncated is True
        assert AICompletion(text="x", finish_reason="stop").was_truncated is False

    async def test_system_prompt_is_carried_separately(self):
        provider = MockAIProvider()
        await provider.generate(request(system="be terse"))
        assert provider.requests[0].system == "be terse"
        assert "[system] be terse" in provider.requests[0].prompt_text()


class TestStreaming:
    async def test_chunks_reassemble_to_the_full_text(self):
        text = "Staging discards spent structure so the remaining engines "
        text += "no longer accelerate empty tanks."
        provider = MockAIProvider(responses=[text], chunk_size=10)
        chunks = await collect(provider, request())
        assert "".join(chunk.text for chunk in chunks) == text

    async def test_a_final_chunk_terminates_the_stream(self):
        chunks = await collect(MockAIProvider(responses=["abc"]), request())
        assert chunks[-1].is_final is True
        assert chunks[-1].finish_reason == "stop"
        assert sum(1 for chunk in chunks if chunk.is_final) == 1

    async def test_more_than_one_chunk_for_long_output(self):
        provider = MockAIProvider(responses=["x" * 100], chunk_size=10)
        chunks = await collect(provider, request())
        assert len([c for c in chunks if c.text]) == 10

    async def test_streaming_errors_surface_from_the_iterator(self):
        provider = MockAIProvider(
            responses=[AIProviderUnavailable("overloaded", "mock")]
        )
        with pytest.raises(AIProviderUnavailable):
            await collect(provider, request())

    async def test_extractive_provider_streams(self):
        chunks = await collect(ExtractiveProvider(), request())
        assert chunks[-1].is_final


class TestFailureModes:
    async def test_timeout(self):
        provider = MockAIProvider(responses=[AIProviderTimeout("deadline", "mock")])
        with pytest.raises(AIProviderTimeout) as excinfo:
            await provider.generate(request())
        assert excinfo.value.retryable is True

    async def test_provider_unavailable(self):
        provider = MockAIProvider(
            responses=[AIProviderUnavailable("503 from upstream", "mock")]
        )
        with pytest.raises(AIProviderUnavailable) as excinfo:
            await provider.generate(request())
        assert excinfo.value.retryable is True

    async def test_rate_limited_carries_retry_after(self):
        error = AIProviderRateLimited("slow down", "mock", retry_after_seconds=30.0)
        provider = MockAIProvider(responses=[error])
        with pytest.raises(AIProviderRateLimited) as excinfo:
            await provider.generate(request())
        assert excinfo.value.retry_after_seconds == 30.0

    async def test_auth_error_is_not_retryable(self):
        provider = MockAIProvider(responses=[AIProviderAuthError("rejected", "mock")])
        with pytest.raises(AIProviderAuthError) as excinfo:
            await provider.generate(request())
        assert excinfo.value.retryable is False

    async def test_malformed_output(self):
        error = MalformedProviderOutput(
            "response was not JSON", "mock", payload_excerpt="<html>500</html>"
        )
        provider = MockAIProvider(responses=[error])
        with pytest.raises(MalformedProviderOutput) as excinfo:
            await provider.generate(request())
        assert excinfo.value.payload_excerpt == "<html>500</html>"
        assert excinfo.value.retryable is False

    async def test_malformed_excerpt_is_truncated(self):
        error = MalformedProviderOutput("bad", "mock", payload_excerpt="x" * 5000)
        assert len(error.payload_excerpt) == 500

    async def test_every_failure_is_an_ai_provider_error(self):
        for error in (
            AIProviderTimeout("t"), AIProviderUnavailable("u"),
            AIProviderAuthError("a"), AIProviderRateLimited("r"),
            MalformedProviderOutput("m"),
        ):
            assert isinstance(error, AIProviderError)

    async def test_error_message_names_the_provider(self):
        assert "[mock]" in str(AIProviderTimeout("deadline", "mock"))

    async def test_a_real_timeout_can_be_enforced_by_the_caller(self):
        """The interface does not block callers from imposing a deadline."""
        provider = MockAIProvider(responses=["slow"], latency_seconds=0.2)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(provider.generate(request()), timeout=0.01)


class TestHealthCheck:
    async def test_healthy_provider(self):
        status = await MockAIProvider().health_check()
        assert status["healthy"] is True
        assert status["provider"] == "mock"

    async def test_broken_provider_reports_rather_than_raising(self):
        provider = MockAIProvider(responses=[AIProviderUnavailable("down", "mock")])
        status = await provider.health_check()
        assert status["healthy"] is False
        assert "down" in status["detail"]

    async def test_extractive_provider_is_always_healthy(self):
        assert (await ExtractiveProvider().health_check())["healthy"] is True


class TestCredentialSafety:
    def test_keys_are_read_only_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("TEST_AI_KEY", "sk-secret-value")
        assert AIProvider.read_api_key(["TEST_AI_KEY"]) == "sk-secret-value"

    def test_missing_key_raises_without_naming_a_value(self, monkeypatch):
        monkeypatch.delenv("TEST_AI_KEY", raising=False)
        with pytest.raises(AIProviderAuthError) as excinfo:
            AIProvider.read_api_key(["TEST_AI_KEY"], provider="x")
        message = str(excinfo.value)
        assert "TEST_AI_KEY" in message
        assert "never accepted as arguments" in message

    def test_optional_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("TEST_AI_KEY", raising=False)
        assert AIProvider.read_api_key(["TEST_AI_KEY"], required=False) is None

    def test_blank_key_counts_as_missing(self, monkeypatch):
        monkeypatch.setenv("TEST_AI_KEY", "   ")
        assert AIProvider.read_api_key(["TEST_AI_KEY"], required=False) is None

    def test_first_configured_variable_wins(self, monkeypatch):
        monkeypatch.delenv("FIRST_KEY", raising=False)
        monkeypatch.setenv("SECOND_KEY", "second")
        assert AIProvider.read_api_key(["FIRST_KEY", "SECOND_KEY"]) == "second"

    def test_no_interface_method_accepts_a_key(self):
        """A key that can be passed as an argument ends up in a log."""
        import inspect

        for name in ("generate", "stream", "health_check"):
            signature = inspect.signature(getattr(AIProvider, name))
            for parameter in signature.parameters:
                assert "key" not in parameter.lower()
                assert "token" not in parameter.lower()

    def test_configuration_report_never_exposes_a_value(self, monkeypatch):
        monkeypatch.setenv("LIS_TEST_SECRET", "sk-do-not-leak")
        report = describe_configuration()
        serialized = repr(report)
        assert "sk-do-not-leak" not in serialized

    def test_configuration_report_says_whether_a_key_is_present(self):
        report = describe_configuration()
        assert "selected_provider" in report
        assert "keys" in report
        for entry in report["keys"].values():
            assert isinstance(entry["configured"], bool)

    def test_completion_metadata_carries_no_credential(self):
        completion = AICompletion(text="x", raw_metadata={"model": "m"})
        assert "key" not in repr(completion.raw_metadata).lower()


class TestRegistry:
    def test_available_providers(self):
        assert "mock" in available_providers()
        assert "extractive" in available_providers()

    def test_default_is_the_offline_fallback(self, monkeypatch):
        """No key configured must degrade honestly, not fail."""
        monkeypatch.delenv(AI_PROVIDER_ENV, raising=False)
        for env in GEMINI_KEY_ENV:
            monkeypatch.delenv(env, raising=False)
        assert resolve_provider_name() == "extractive"

    def test_a_configured_key_is_selected_without_being_named(self, monkeypatch):
        """A deployment that sets a key should not also have to set a provider."""
        monkeypatch.delenv(AI_PROVIDER_ENV, raising=False)
        for env in GEMINI_KEY_ENV:
            monkeypatch.delenv(env, raising=False)
        monkeypatch.setenv(GEMINI_KEY_ENV[0], "test-key-not-used-for-a-request")
        assert resolve_provider_name() == "gemini"

    def test_an_explicit_provider_still_wins_over_a_present_key(self, monkeypatch):
        """Auto-selection is a convenience, not an override."""
        monkeypatch.setenv(GEMINI_KEY_ENV[0], "test-key-not-used-for-a-request")
        monkeypatch.setenv(AI_PROVIDER_ENV, "extractive")
        assert resolve_provider_name() == "extractive"

    def test_a_blank_key_does_not_count_as_configured(self, monkeypatch):
        """An empty variable is how a key gets 'unset' in a .env file."""
        monkeypatch.delenv(AI_PROVIDER_ENV, raising=False)
        for env in GEMINI_KEY_ENV:
            monkeypatch.delenv(env, raising=False)
        monkeypatch.setenv(GEMINI_KEY_ENV[0], "   ")
        assert resolve_provider_name() == "extractive"

    def test_environment_variable_selects_the_provider(self, monkeypatch):
        monkeypatch.setenv(AI_PROVIDER_ENV, "mock")
        assert resolve_provider_name() == "mock"

    def test_explicit_argument_wins_over_the_environment(self, monkeypatch):
        monkeypatch.setenv(AI_PROVIDER_ENV, "mock")
        assert resolve_provider_name("extractive") == "extractive"

    def test_unknown_provider_is_rejected(self):
        with pytest.raises(ValueError, match="unknown AI provider"):
            resolve_provider_name("definitely-not-a-provider")

    def test_build_provider(self, monkeypatch):
        monkeypatch.setenv(AI_PROVIDER_ENV, "mock")
        assert isinstance(build_provider(), MockAIProvider)

    def test_no_vendor_sdk_is_imported_above_the_provider_package(self):
        """The isolation rule, checked mechanically."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2]
        vendors = ("anthropic", "openai", "google.generativeai", "cohere", "mistralai")
        offenders = []
        for path in list(root.glob("search/**/*.py")) + list(root.glob("data/**/*.py")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for vendor in vendors:
                if "import {0}".format(vendor) in text:
                    offenders.append("{0}: {1}".format(path.name, vendor))
        assert offenders == []


class TestExtractiveProvider:
    async def test_quotes_supplied_context(self):
        provider = ExtractiveProvider()
        content = "{0}\n[S1] Max-Q — dynamic pressure peaks during ascent.".format(
            ExtractiveProvider.CONTEXT_MARKER
        )
        completion = await provider.generate(
            AIRequest(messages=[AIMessage(role=Role.USER, content=content)])
        )
        assert "[S1]" in completion.text
        assert "dynamic pressure" in completion.text

    async def test_says_so_when_no_context_was_supplied(self):
        completion = await ExtractiveProvider().generate(request())
        assert "No context was supplied" in completion.text

    async def test_cannot_invent_text_absent_from_the_context(self):
        """The property that makes it safe offline."""
        provider = ExtractiveProvider()
        content = "{0}\n[S1] Ceres — a dwarf planet in the asteroid belt.".format(
            ExtractiveProvider.CONTEXT_MARKER
        )
        completion = await provider.generate(
            AIRequest(messages=[AIMessage(role=Role.USER, content=content)])
        )
        for line in completion.text.splitlines():
            assert line.strip() in content

    async def test_respects_the_sentence_cap(self):
        provider = ExtractiveProvider(max_sentences=2)
        lines = "\n".join("[S{0}] item {0}".format(i) for i in range(10))
        content = "{0}\n{1}".format(ExtractiveProvider.CONTEXT_MARKER, lines)
        completion = await provider.generate(
            AIRequest(messages=[AIMessage(role=Role.USER, content=content)])
        )
        assert len(completion.text.splitlines()) <= 2


class TestLifecycle:
    async def test_close_is_idempotent(self):
        provider = MockAIProvider()
        await provider.aclose()
        await provider.aclose()
        assert provider.closed is True

    async def test_async_context_manager_closes(self):
        async with MockAIProvider() as provider:
            await provider.generate(request())
        assert provider.closed is True
