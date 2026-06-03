"""Test suite for the Implementor and Verifier agents."""

from __future__ import annotations

import json

import pytest  # noqa: F401

from no_slop_harness.agents.implementor import ImplementorAgent
from no_slop_harness.agents.verifier import VerifierAgent
from no_slop_harness.llm_client import LLMClient, LLMClientConfig, LLMProvider, LLMResponse
from no_slop_harness.schemas import SandboxConfig, Task


class MockImplementorProvider(LLMProvider):
    """Mock LLM that returns predefined implementor responses."""

    def __init__(self, response: str | None = None) -> None:
        self._response = response or json.dumps(
            {
                "success": True,
                "summary": "Created User model with email and password fields",
                "files_modified": ["/app/models/user.py"],
                "test_output": "3 passed",
            }
        )

    @property
    def provider_name(self) -> str:
        return "mock_implementor"

    async def generate(
        self, prompt, *, system_prompt=None, temperature=0.7, max_tokens=4096, stop_sequences=None
    ):  # noqa: E501
        return LLMResponse(content=self._response)

    async def generate_structured(
        self, prompt, output_schema, *, system_prompt=None, temperature=0.0, max_tokens=4096
    ):  # noqa: E501
        return {}


class TestImplementorAgent:
    """Implementor agent task execution."""

    def test_execute_returns_result(self) -> None:
        import asyncio

        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockImplementorProvider())

        agent = ImplementorAgent(client)
        task = Task(task_id="t1", description="Test", action="Do")
        result = asyncio.run(agent.execute(task))

        assert result["success"] is True
        assert "files_modified" in result

    def test_execute_non_json_fallback(self) -> None:
        import asyncio

        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockImplementorProvider("Just some plain text response"))

        agent = ImplementorAgent(client)
        task = Task(task_id="t1", description="Test", action="Do")
        result = asyncio.run(agent.execute(task))

        # Should fall back to wrapping the text
        assert result["success"] is True
        assert "Just some plain text" in result["summary"]

    def test_read_file(self, tmp_path) -> None:
        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockImplementorProvider())

        agent = ImplementorAgent(client, work_dir=tmp_path)
        f = tmp_path / "test.txt"
        f.write_text("hello")

        assert agent.read_file(str(f)) == "hello"

    def test_write_file(self, tmp_path) -> None:
        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockImplementorProvider())

        agent = ImplementorAgent(client, work_dir=tmp_path)
        f = tmp_path / "out.py"
        assert agent.write_file(str(f), "x = 1\n")
        assert f.read_text() == "x = 1\n"

    def test_write_file_rejects_syntax_error(self, tmp_path) -> None:
        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockImplementorProvider())

        agent = ImplementorAgent(client, work_dir=tmp_path)
        f = tmp_path / "broken.py"
        assert agent.write_file(str(f), "def broken(:\n") is False

    def test_sandbox_config_passed_through(self) -> None:
        sandbox = SandboxConfig(allowed_commands=["echo"], timeout_seconds=10)
        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockImplementorProvider())

        agent = ImplementorAgent(client, sandbox_config=sandbox)
        assert agent._sandbox.allowed_commands == ["echo"]


class TestVerifierAgent:
    """Verifier agent checks."""

    def test_verify_passing_code(self, tmp_path) -> None:
        import asyncio

        # Write a valid Python file
        f = tmp_path / "good.py"
        f.write_text("def hello():\\n    return 'world'\\n")

        agent = VerifierAgent(work_dir=tmp_path)
        task = Task(task_id="t1", description="Test", action="Add", target_file=str(f))
        result = asyncio.run(agent.verify(task, modified_files=[str(f)]))

        assert "passed" in result

    def test_verify_syntax_error(self, tmp_path) -> None:
        import asyncio

        f = tmp_path / "bad.py"
        f.write_text("def broken(:\\n")

        agent = VerifierAgent(work_dir=tmp_path)
        task = Task(task_id="t1", description="Test", action="Add", target_file=str(f))
        result = asyncio.run(agent.verify(task, modified_files=[str(f)]))

        assert result["passed"] is False
        assert "Syntax error" in result["detail"]

    def test_verify_nonexistent_file_not_fatal(self, tmp_path) -> None:
        import asyncio

        agent = VerifierAgent(work_dir=tmp_path)
        task = Task(
            task_id="t1", description="Test", action="Add", target_file="/nonexistent/file.py"
        )  # noqa: E501
        result = asyncio.run(agent.verify(task, modified_files=["/nonexistent/file.py"]))
        assert "passed" in result
