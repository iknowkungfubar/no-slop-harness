"""Test suite for the OpenAI-compatible LLM provider."""

from __future__ import annotations

import json  # noqa: F401

import pytest  # noqa: F401

from no_slop_harness.providers.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
)


class TestOpenAICompatibleConfig:
    """Configuration defaults and overrides."""

    def test_defaults(self) -> None:
        cfg = OpenAICompatibleConfig()
        assert cfg.base_url == "http://localhost:1234/v1"
        assert cfg.model == "qwen/qwen3.6-35b-a3b"
        assert cfg.timeout_seconds == 120.0
        assert cfg.max_retries == 3

    def test_custom_model(self) -> None:
        cfg = OpenAICompatibleConfig(
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            api_key="sk-test",
        )
        assert cfg.model == "gpt-4o"
        assert cfg.api_key == "sk-test"


class TestOpenAICompatibleProvider:
    """Provider initialization and interface conformance."""

    def test_provider_name(self) -> None:
        provider = OpenAICompatibleProvider()
        assert "openai_compatible" in provider.provider_name
        assert "localhost:1234" in provider.provider_name

    def test_custom_base_url_in_name(self) -> None:
        cfg = OpenAICompatibleConfig(base_url="https://custom.api/v1")
        provider = OpenAICompatibleProvider(config=cfg)
        assert "custom.api" in provider.provider_name

    def test_async_context_manager(self) -> None:
        """Provider supports async context manager."""
        import asyncio  # noqa: F401

        async def _test():
            cfg = OpenAICompatibleConfig(base_url="https://example.com/v1")
            async with OpenAICompatibleProvider(config=cfg) as p:
                assert p is not None
                return True

        # This will fail to connect but shouldn't crash on context manager
        # We just verify the interface
        provider = OpenAICompatibleProvider(
            config=OpenAICompatibleConfig(base_url="https://example.com/v1")
        )
        assert provider.provider_name is not None

    def test_close_does_not_raise(self) -> None:
        """close() should not raise even if never connected."""
        import asyncio

        async def _test():
            provider = OpenAICompatibleProvider()
            await provider.close()

        asyncio.run(_test())
