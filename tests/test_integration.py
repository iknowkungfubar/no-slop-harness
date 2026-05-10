"""Integration tests with mocked inference client."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness.agents import Coordinator, Implementor, Verifier
from harness.config import HarnessConfig
from harness.executor import ToolExecutor
from harness.orchestrator import CyclicDependencyError, Orchestrator, _topological_sort
from harness.schemas import (
    AgentAction,
    Task,
    TaskPlan,
    TaskStatus,
    ToolCall,
    VerificationResult,
)


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for testing."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    (tmp_path / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    return tmp_path


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.health_check.return_value = True
    return client


class TestCoordinator:
    def test_plan(self):
        client = _mock_client()
        plan = TaskPlan(tasks=[
            Task(id="t1", description="Write hello.py"),
            Task(id="t2", description="Test hello.py", dependencies=["t1"]),
        ])
        client.generate_structured.return_value = plan
        coord = Coordinator(client)
        result = coord.plan("Create hello world")
        assert len(result.tasks) == 2
        assert result.tasks[1].dependencies == ["t1"]


class TestImplementor:
    def test_execute_with_finish(self):
        client = _mock_client()
        client.generate_structured.return_value = AgentAction(
            action="finish", summary="Done"
        )
        impl = Implementor(client)
        task = Task(id="t1", description="Do something")
        log = impl.execute(task)
        assert len(log) == 1
        assert log[0]["action"] == "finish"

    def test_execute_with_tool_call(self, tmp_path: Path):
        client = _mock_client()
        target = tmp_path / "output.txt"

        call_action = AgentAction(
            action="call_tool",
            tool_call=ToolCall(
                name="write_file",
                arguments={"path": str(target), "content": "hello"},
            ),
        )
        finish_action = AgentAction(action="finish", summary="Wrote file")
        client.generate_structured.side_effect = [call_action, finish_action]

        impl = Implementor(client)
        task = Task(id="t1", description="Write a file")
        log = impl.execute(task)

        assert len(log) == 2
        assert log[0]["tool"] == "write_file"
        assert target.read_text() == "hello"

    def test_execute_with_executor(self, tmp_path: Path):
        client = _mock_client()
        cfg = HarnessConfig()
        executor = ToolExecutor(cfg, tmp_path)

        target = tmp_path / "out.txt"
        call_action = AgentAction(
            action="call_tool",
            tool_call=ToolCall(
                name="write_file",
                arguments={"path": str(target), "content": "secure"},
            ),
        )
        finish_action = AgentAction(action="finish", summary="Done")
        client.generate_structured.side_effect = [call_action, finish_action]

        impl = Implementor(client, executor=executor)
        task = Task(id="t1", description="Write securely")
        impl.execute(task)
        assert target.read_text() == "secure"

    def test_max_steps_limit(self):
        client = _mock_client()
        call_action = AgentAction(
            action="call_tool",
            tool_call=ToolCall(name="bash_execute", arguments={"cmd": "echo step"}),
        )
        client.generate_structured.return_value = call_action

        impl = Implementor(client)
        impl.MAX_STEPS = 3
        task = Task(id="t1", description="Loop forever")
        log = impl.execute(task)
        assert len(log) == 3


class TestVerifier:
    def test_verify_pass(self):
        client = _mock_client()
        client.generate_structured.return_value = VerificationResult(passed=True)
        v = Verifier(client)
        task = Task(id="t1", description="Check")
        result = v.verify(task, [{"action": "finish"}], "")
        assert result.passed

    def test_verify_fail(self):
        client = _mock_client()
        client.generate_structured.return_value = VerificationResult(
            passed=False, failures=["Tests failed"]
        )
        v = Verifier(client)
        task = Task(id="t1", description="Check")
        result = v.verify(task, [], "bad diff")
        assert not result.passed
        assert "Tests failed" in result.failures


class TestOrchestratorIntegration:
    def test_full_pipeline(self, git_repo: Path):
        client = _mock_client()

        plan = TaskPlan(tasks=[
            Task(id="t1", description="Create file"),
        ])
        finish = AgentAction(action="finish", summary="Created")
        verification = VerificationResult(passed=True)

        client.generate_structured.side_effect = [plan, finish, verification]

        orch = Orchestrator(client, git_repo)
        result = orch.run("Create a file")

        assert result.all_passed
        assert len(result.results) == 1
        assert result.results[0].task.status == TaskStatus.COMPLETED

    def test_failed_verification_aborts(self, git_repo: Path):
        client = _mock_client()

        plan = TaskPlan(tasks=[
            Task(id="t1", description="Bad task"),
            Task(id="t2", description="Never runs", dependencies=["t1"]),
        ])
        finish = AgentAction(action="finish", summary="Attempted")
        verification = VerificationResult(passed=False, failures=["Broken"])

        client.generate_structured.side_effect = [plan, finish, verification]

        orch = Orchestrator(client, git_repo)
        result = orch.run("Do bad thing")

        assert not result.all_passed
        assert result.results[0].task.status == TaskStatus.FAILED

    def test_callbacks_invoked(self, git_repo: Path):
        client = _mock_client()

        plan = TaskPlan(tasks=[Task(id="t1", description="Task")])
        finish = AgentAction(action="finish", summary="Done")
        verification = VerificationResult(passed=True)
        client.generate_structured.side_effect = [plan, finish, verification]

        starts: list[str] = []
        ends: list[str] = []

        orch = Orchestrator(client, git_repo)
        orch.on_task_start(lambda t: starts.append(t.id))
        orch.on_task_end(lambda tr: ends.append(tr.task.id))

        orch.run("Do task")
        assert starts == ["t1"]
        assert ends == ["t1"]

    def test_context_persisted(self, git_repo: Path):
        client = _mock_client()

        plan = TaskPlan(tasks=[Task(id="ctx1", description="Context test")])
        finish = AgentAction(action="finish", summary="Done")
        verification = VerificationResult(passed=True)
        client.generate_structured.side_effect = [plan, finish, verification]

        orch = Orchestrator(client, git_repo)
        orch.run("Test context")

        ctx_file = git_repo / ".sdlc" / "context" / "task_ctx1.md"
        assert ctx_file.exists()
        assert "completed" in ctx_file.read_text()


class TestTopologicalSort:
    def test_cycle_detected(self):
        tasks = [
            Task(id="a", description="A", dependencies=["b"]),
            Task(id="b", description="B", dependencies=["a"]),
        ]
        with pytest.raises(CyclicDependencyError, match="Cycle detected"):
            _topological_sort(tasks)

    def test_valid_dag_sorted(self):
        tasks = [
            Task(id="c", description="C", dependencies=["b"]),
            Task(id="b", description="B", dependencies=["a"]),
            Task(id="a", description="A"),
        ]
        result = _topological_sort(tasks)
        ids = [t.id for t in result]
        assert ids.index("a") < ids.index("b") < ids.index("c")
