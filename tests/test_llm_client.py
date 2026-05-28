"""Test suite for the LLM client abstraction layer."""

from __future__ import annotations

import asyncio

import pytest

from no_slop_harness.llm_client import (
    LLMClient,
    LLMClientConfig,
    LLMProvider,
    LLMResponse,
)
from no_slop_harness.metrics import MetricsRegistry


class MockProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(
        self,
        responses: list[LLMResponse] | None = None,
        fail_count: int = 0,
    ) -> None:
        self.responses = responses or []
        self.fail_count = fail_count
        self.call_count = 0
        self.last_prompt: str | None = None

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        self.call_count += 1
        self.last_prompt = prompt
        if self.fail_count > 0:
            self.fail_count -= 1
            raise RuntimeError("Simulated provider failure")
        if not self.responses:
            return LLMResponse(content="mock response")
        return self.responses.pop(0)

    async def generate_structured(
        self,
        prompt: str,
        output_schema: type,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> object:
        return {"parsed": True, "prompt": prompt}


class TestLLMClientConfig:
    """LLMClientConfig defaults and overrides."""

    def test_defaults(self) -> None:
        cfg = LLMClientConfig()
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o"
        assert cfg.temperature == 0.7
        assert cfg.max_tokens == 4096
        assert cfg.max_retries == 3

    def test_custom_values(self) -> None:
        cfg = LLMClientConfig(provider="anthropic", model="claude-4", temperature=0.0)
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-4"
        assert cfg.temperature == 0.0


class TestLLMClient:
    """LLMClient manages providers and handles generation with retries."""

    def test_register_and_get_provider(self) -> None:
        client = LLMClient()
        mock = MockProvider()
        client.register_provider("mock", mock)
        assert client.get_provider("mock") is mock

    def test_get_unknown_provider_raises(self) -> None:
        client = LLMClient()
        with pytest.raises(ValueError, match="not registered"):
            client.get_provider("nonexistent")

    def test_list_providers(self) -> None:
        client = LLMClient()
        client.register_provider("a", MockProvider())
        client.register_provider("b", MockProvider())
        providers = client.list_providers()
        assert set(providers) == {"a", "b"}

    def test_generate_returns_response(self) -> None:
        client = LLMClient(config=LLMClientConfig(provider="mock"))
        mock = MockProvider(responses=[LLMResponse(content="hello")])
        client.register_provider("mock", mock)

        result = asyncio.run(client.generate("test prompt"))
        assert result.content == "hello"
        assert mock.call_count == 1

    def test_generate_with_config_defaults(self) -> None:
        client = LLMClient(config=LLMClientConfig(provider="mock", temperature=0.3))
        mock = MockProvider()
        client.register_provider("mock", mock)

        asyncio.run(client.generate("prompt"))
        assert mock.last_prompt == "prompt"

    def test_generate_retries_on_failure(self) -> None:
        client = LLMClient(
            config=LLMClientConfig(
                provider="mock",
                max_retries=3,
                retry_delay_seconds=0.01,
            )
        )
        # Fail twice, succeed on third
        mock = MockProvider(fail_count=2, responses=[LLMResponse(content="success")])
        client.register_provider("mock", mock)

        result = asyncio.run(client.generate("prompt"))
        assert result.content == "success"
        assert mock.call_count == 3  # 2 failures + 1 success

    def test_generate_exhausts_retries(self) -> None:
        client = LLMClient(
            config=LLMClientConfig(
                provider="mock",
                max_retries=2,
                retry_delay_seconds=0.01,
            )
        )
        mock = MockProvider(fail_count=99)  # Always fails
        client.register_provider("mock", mock)

        with pytest.raises(RuntimeError, match="failed after"):
            asyncio.run(client.generate("prompt"))

    def test_generate_structured(self) -> None:
        client = LLMClient(config=LLMClientConfig(provider="mock"))
        mock = MockProvider()
        client.register_provider("mock", mock)

        result = asyncio.run(client.generate_structured("prompt", dict))
        assert result["parsed"] is True

    def test_metrics_collected(self) -> None:
        metrics = MetricsRegistry()
        client = LLMClient(
            config=LLMClientConfig(provider="mock"),
            metrics=metrics,
        )
        mock = MockProvider()
        client.register_provider("mock", mock)

        asyncio.run(client.generate("test"))
        report = metrics.report()
        assert report["timers"]["llm_generate_ms"]["count"] > 0
        assert report["counters"]["llm_requests_total"]["value"] > 0


class TestLLMResponse:
    """LLMResponse dataclass."""

    def test_defaults(self) -> None:
        resp = LLMResponse(content="test")
        assert resp.content == "test"
        assert resp.model == ""
        assert resp.finish_reason == "stop"
        assert resp.raw is None

    def test_custom_fields(self) -> None:
        resp = LLMResponse(
            content="result",
            model="gpt-4o",
            usage={"tokens": 100},
            finish_reason="length",
        )
        assert resp.model == "gpt-4o"
        assert resp.usage == {"tokens": 100}
        assert resp.finish_reason == "length"
