"""Additional coverage for agents and runner."""

from __future__ import annotations

from pathlib import Path

from no_slop_harness.agents.implementor import ImplementorAgent
from no_slop_harness.agents.verifier import VerifierAgent
from no_slop_harness.llm_client import LLMClient, LLMClientConfig, LLMProvider, LLMResponse
from no_slop_harness.schemas import SandboxConfig, Task


class MockAgentProvider(LLMProvider):
    def __init__(
        self,
        response: str = '{"success": true, "summary": "done", "files_modified": [], "test_output": ""}',  # noqa: E501
    ) -> None:
        self._response = response

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate(
        self, prompt, *, system_prompt=None, temperature=0.7, max_tokens=4096, stop_sequences=None
    ):
        return LLMResponse(content=self._response)

    async def generate_structured(
        self, prompt, output_schema, *, system_prompt=None, temperature=0.0, max_tokens=4096
    ):
        return {}


class TestImplementorExtra:
    def test_execute_with_target_file(self, tmp_path: Path) -> None:
        import asyncio

        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockAgentProvider())

        agent = ImplementorAgent(client, work_dir=tmp_path)
        task = Task(
            task_id="t1", description="Test", action="Do", target_file=str(tmp_path / "out.py")
        )
        result = asyncio.run(agent.execute(task))
        assert "success" in result

    def test_execute_with_dependencies(self, tmp_path: Path) -> None:
        import asyncio

        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockAgentProvider())

        agent = ImplementorAgent(client, work_dir=tmp_path)
        task = Task(
            task_id="t2",
            description="Dep task",
            action="Modify",
            dependencies=["t1"],
            target_file=str(tmp_path / "mod.py"),
        )
        result = asyncio.run(agent.execute(task))
        assert "success" in result

    def test_bash_execute_passthrough(self, tmp_path: Path) -> None:
        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockAgentProvider())
        agent = ImplementorAgent(
            client,
            work_dir=tmp_path,
            sandbox_config=SandboxConfig(allowed_commands=["echo"], timeout_seconds=5),
        )
        code, out, err = agent.bash_execute("echo hello")
        assert code == 0
        assert "hello" in out

    def test_parse_response_non_json(self) -> None:
        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockAgentProvider("plain text response with no json"))
        agent = ImplementorAgent(client)
        task = Task(task_id="t1", description="T", action="Do", target_file="/tmp/x.py")  # noqa: S108
        result = agent._parse_response("just plain text", task)
        assert result["success"] is True
        assert "just plain text" in result["summary"]

    def test_parse_response_with_code_fence(self) -> None:
        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockAgentProvider())
        agent = ImplementorAgent(client)
        task = Task(task_id="t1", description="T", action="Do")
        result = agent._parse_response('```\n{"success": false, "summary": "bad"}\n```', task)
        assert result["success"] is False


class TestVerifierExtra:
    def test_verify_passing_with_files(self, tmp_path: Path) -> None:
        import asyncio

        f = tmp_path / "valid.py"
        f.write_text("x: int = 1\n")

        agent = VerifierAgent(work_dir=tmp_path)
        task = Task(task_id="t1", description="T", action="Do", target_file=str(f))
        result = asyncio.run(agent.verify(task, modified_files=[str(f)]))
        assert "passed" in result

    def test_verify_no_target_file(self, tmp_path: Path) -> None:
        import asyncio

        agent = VerifierAgent(work_dir=tmp_path)
        task = Task(task_id="t1", description="T", action="Do")
        result = asyncio.run(agent.verify(task))
        assert "passed" in result
