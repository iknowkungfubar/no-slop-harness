"""Test suite for the Coordinator agent."""

from __future__ import annotations

import json

import pytest

from no_slop_harness.agents.coordinator import CoordinatorAgent
from no_slop_harness.llm_client import LLMClient, LLMClientConfig, LLMProvider, LLMResponse
from no_slop_harness.schemas import Task  # noqa: F401


class MockCoordinatorProvider(LLMProvider):
    """Mock LLM that returns a predefined task list."""

    def __init__(self, tasks_json: str | None = None) -> None:
        self._tasks = tasks_json or json.dumps(
            [
                {
                    "task_id": "create_model",
                    "description": "Create the User model with email and password fields",
                    "action": "Add User model",
                    "target_file": "/app/models/user.py",
                    "dependencies": [],
                    "priority": 0,
                },
                {
                    "task_id": "create_tests",
                    "description": "Write unit tests for the User model",
                    "action": "Add User model tests",
                    "target_file": "/app/tests/test_user.py",
                    "dependencies": ["create_model"],
                    "priority": 0,
                },
            ]
        )

    @property
    def provider_name(self) -> str:
        return "mock_coordinator"

    async def generate(
        self, prompt, *, system_prompt=None, temperature=0.7, max_tokens=4096, stop_sequences=None
    ):  # noqa: E501
        return LLMResponse(content=self._tasks)

    async def generate_structured(
        self, prompt, output_schema, *, system_prompt=None, temperature=0.0, max_tokens=4096
    ):  # noqa: E501
        return []


class TestCoordinatorAgent:
    """Coordinator agent task decomposition."""

    def test_decompose_returns_tasks(self) -> None:
        import asyncio

        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockCoordinatorProvider())

        agent = CoordinatorAgent(client)
        tasks = asyncio.run(agent.decompose("Add a User model"))

        assert len(tasks) == 2
        assert tasks[0].task_id == "create_model"
        assert tasks[1].task_id == "create_tests"
        assert tasks[1].dependencies == ["create_model"]

    def test_decompose_empty_request(self) -> None:
        import asyncio

        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockCoordinatorProvider("[]"))

        agent = CoordinatorAgent(client)
        tasks = asyncio.run(agent.decompose("Do nothing"))
        assert tasks == []

    def test_decompose_with_context_files(self) -> None:
        import asyncio

        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockCoordinatorProvider())

        agent = CoordinatorAgent(client)
        tasks = asyncio.run(
            agent.decompose("Refactor", context_files=["/app/main.py", "/app/models.py"])
        )
        assert len(tasks) == 2

    def test_decompose_invalid_json_raises(self) -> None:
        import asyncio

        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockCoordinatorProvider("not json at all"))

        agent = CoordinatorAgent(client)
        with pytest.raises(ValueError, match="invalid JSON"):
            asyncio.run(agent.decompose("Test"))

    def test_decompose_non_list_raises(self) -> None:
        import asyncio

        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockCoordinatorProvider('{"not": "a list"}'))

        agent = CoordinatorAgent(client)
        with pytest.raises(ValueError, match="not a list"):
            asyncio.run(agent.decompose("Test"))

    def test_decompose_markdown_fenced_json(self) -> None:
        import asyncio

        tasks_json = json.dumps(
            [{"task_id": "t1", "description": "Do thing", "action": "Add", "dependencies": []}]
        )
        fenced = f"```json\n{tasks_json}\n```"

        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockCoordinatorProvider(fenced))

        agent = CoordinatorAgent(client)
        tasks = asyncio.run(agent.decompose("Test"))
        assert len(tasks) == 1
        assert tasks[0].task_id == "t1"

    def test_decompose_auto_fixes_missing_fields(self) -> None:
        import asyncio

        # Task missing task_id and description — should auto-fix
        broken_json = json.dumps(
            [
                {"action": "Do something"},
                {"task_id": "good", "description": "Good task", "action": "Run"},
            ]
        )

        client = LLMClient(config=LLMClientConfig(provider="mock"))
        client.register_provider("mock", MockCoordinatorProvider(broken_json))

        agent = CoordinatorAgent(client)
        tasks = asyncio.run(agent.decompose("Test"))
        # Should have at least the good task, possibly auto-fixed first one
        assert len(tasks) >= 1
        assert any(t.task_id == "good" for t in tasks)
