"""Test suite for the end-to-end CIV pipeline runner."""

from __future__ import annotations

import json

import pytest  # noqa: F401

from no_slop_harness.llm_client import (  # noqa: F401
    LLMClient,
    LLMClientConfig,
    LLMProvider,
    LLMResponse,
)
from no_slop_harness.runner import CIVPipeline


class MockPipelineProvider(LLMProvider):
    """Mock LLM that returns coordinator + implementor responses."""

    def __init__(self) -> None:
        self.coord_calls = 0
        self.impl_calls = 0

    @property
    def provider_name(self) -> str:
        return "mock_pipeline"

    async def generate(
        self, prompt, *, system_prompt=None, temperature=0.7, max_tokens=4096, stop_sequences=None
    ):  # noqa: E501
        sp = system_prompt or ""
        if "You are a Coordinator" in sp:
            self.coord_calls += 1
            return LLMResponse(
                content=json.dumps(
                    [
                        {
                            "task_id": "add_function",
                            "description": "Add a hello() function",
                            "action": "Add hello function",
                            "target_file": "/tmp/test_output.py",  # noqa: S108
                            "dependencies": [],
                            "priority": 0,
                        }
                    ]
                )
            )
        else:
            self.impl_calls += 1
            return LLMResponse(
                content=json.dumps(
                    {
                        "success": True,
                        "summary": "Added hello() function",
                        "files_modified": ["/tmp/test_output.py"],  # noqa: S108
                        "test_output": "",
                    }
                )
            )

    async def generate_structured(
        self, prompt, output_schema, *, system_prompt=None, temperature=0.0, max_tokens=4096
    ):  # noqa: E501
        return []


class TestCIVPipeline:
    """End-to-end CIV pipeline tests."""

    def test_pipeline_initialization(self) -> None:
        pipeline = CIVPipeline(
            base_url="https://example.com/v1",
            model="test-model",
            api_key="test-key",
        )
        assert pipeline._client is not None
        assert pipeline._coordinator is not None
        assert pipeline._implementor is not None
        assert pipeline._verifier is not None

    def test_pipeline_run_no_tasks(self) -> None:
        import asyncio

        # Provider that returns empty task list from coordinator
        class EmptyProvider(LLMProvider):
            @property
            def provider_name(self) -> str:
                return "empty"

            async def generate(
                self,
                prompt,
                *,
                system_prompt=None,
                temperature=0.7,
                max_tokens=4096,
                stop_sequences=None,
            ):  # noqa: E501
                return LLMResponse(content="[]")

            async def generate_structured(
                self, prompt, output_schema, *, system_prompt=None, temperature=0.0, max_tokens=4096
            ):  # noqa: E501
                return []

        pipeline = CIVPipeline(
            base_url="https://example.com/v1",
            model="test",
        )
        # Override the provider with our mock
        pipeline._client._providers.clear()
        pipeline._client.register_provider("openai_compatible", EmptyProvider())
        pipeline._client.config.provider = "openai_compatible"

        result = asyncio.run(pipeline.run("Do nothing"))
        assert result["success"] is False
        assert "no tasks" in result.get("error", "").lower()

    def test_pipeline_close(self) -> None:
        import asyncio

        pipeline = CIVPipeline(base_url="https://example.com/v1", model="test")
        asyncio.run(pipeline.close())
        # Should not raise

    def test_pipeline_with_mock_complete_run(self) -> None:
        """A full pipeline run with mocked LLM that returns valid tasks
        and implementor outputs. The verifier will run real checks on
        the filesystem."""
        import asyncio

        pipeline = CIVPipeline(
            base_url="https://example.com/v1",
            model="test",
        )
        # Replace provider with mock
        pipeline._client._providers.clear()
        pipeline._client.register_provider("openai_compatible", MockPipelineProvider())
        pipeline._client.config.provider = "openai_compatible"

        result = asyncio.run(pipeline.run("Add a hello() function"))

        assert "success" in result
        assert "request_id" in result
        assert result["tasks_total"] >= 1

    def test_pipeline_sandbox_config(self) -> None:
        from no_slop_harness.schemas import SandboxConfig

        sandbox = SandboxConfig(allowed_commands=["echo"], timeout_seconds=30)
        pipeline = CIVPipeline(
            base_url="https://example.com/v1",
            model="test",
            sandbox_config=sandbox,
        )
        assert pipeline._sandbox.allowed_commands == ["echo"]
        assert pipeline._sandbox.timeout_seconds == 30
