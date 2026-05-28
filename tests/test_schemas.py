"""Test suite for no_slop_harness schemas."""

from __future__ import annotations

import pytest

from no_slop_harness.schemas import (
    BashExecuteParams,
    CIVMessage,
    EditFileAstParams,
    PipelineState,
    ReadFileParams,
    SandboxConfig,
    Task,
    TaskDependency,
    TaskStatus,
    ToolCall,
    ToolName,
    WriteFileParams,
)


class TestToolParamSchemas:
    """All tool parameter schemas reject invalid input and accept valid input."""

    def test_read_file_params_valid(self) -> None:
        p = ReadFileParams(path="/etc/hosts")
        assert p.path == "/etc/hosts"

    def test_read_file_params_empty_path_rejected(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            ReadFileParams(path="")

    def test_write_file_params_valid(self) -> None:
        p = WriteFileParams(path="/tmp/out.txt", content="hello")  # noqa: S108
        assert p.path == "/tmp/out.txt"  # noqa: S108
        assert p.content == "hello"

    def test_edit_file_ast_params_valid(self) -> None:
        p = EditFileAstParams(
            path="/src/main.py",
            node_target="my_function",
            replacement="def my_function(): pass",
        )
        assert p.node_target == "my_function"

    def test_bash_execute_params_valid(self) -> None:
        p = BashExecuteParams(cmd="echo hello")
        assert p.cmd == "echo hello"

    def test_bash_execute_params_too_long_rejected(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            BashExecuteParams(cmd="x" * 5000)


class TestTaskSchema:
    """Task schema validation."""

    def test_minimal_task(self) -> None:
        t = Task(task_id="t1", description="Do thing", action="Add feature")
        assert t.task_id == "t1"
        assert t.status == TaskStatus.PENDING
        assert t.dependencies == []

    def test_task_with_dependencies(self) -> None:
        t = Task(
            task_id="t2",
            description="Dep task",
            action="Modify",
            dependencies=["t1"],
        )
        assert t.dependencies == ["t1"]

    def test_task_priority_default_zero(self) -> None:
        t = Task(task_id="t3", description="X", action="Y")
        assert t.priority == 0

    def test_task_invalid_id_rejected(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            Task(task_id="bad id!", description="X", action="Y")


class TestTaskDependency:
    """TaskDependency schema."""

    def test_valid_dependency(self) -> None:
        d = TaskDependency(predecessor="t1", successor="t2")
        assert d.predecessor == "t1"
        assert d.successor == "t2"


class TestCIVMessage:
    """CIVMessage inter-agent communication schema."""

    def test_minimal_message(self) -> None:
        msg = CIVMessage(
            sender="coordinator",
            recipient="implementor",
            phase="plan",
        )
        assert msg.sender == "coordinator"
        assert msg.phase == "plan"
        assert msg.error is None

    def test_message_with_payload(self) -> None:
        msg = CIVMessage(
            sender="orchestrator",
            recipient="implementor",
            phase="plan",
            payload={"task_order": ["t1", "t2"]},
        )
        assert msg.payload["task_order"] == ["t1", "t2"]

    def test_message_with_error(self) -> None:
        msg = CIVMessage(
            sender="orchestrator",
            recipient="implementor",
            phase="implement",
            error="Something went wrong",
        )
        assert msg.error == "Something went wrong"


class TestSandboxConfig:
    """Sandbox security configuration."""

    def test_default_blocked_commands(self) -> None:
        cfg = SandboxConfig()
        blocked_str = " ".join(cfg.blocked_commands)
        assert "rm -rf" in blocked_str
        assert "mkfs" in blocked_str
        assert "chmod 777" in blocked_str

    def test_empty_allowlist_allows_all(self) -> None:
        cfg = SandboxConfig(allowed_commands=[])
        assert len(cfg.blocked_commands) > 0

    def test_timeout_bounds(self) -> None:
        cfg = SandboxConfig(timeout_seconds=120)
        assert cfg.timeout_seconds == 120

    def test_timeout_too_high_rejected(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            SandboxConfig(timeout_seconds=400)

    def test_timeout_too_low_rejected(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            SandboxConfig(timeout_seconds=0)


class TestPipelineState:
    """PipelineState tracks overall CIV pipeline progress."""

    def test_initial_state(self) -> None:
        state = PipelineState(request_id="test-1")
        assert state.request_id == "test-1"
        assert state.completed is False
        assert state.failed is False
        assert len(state.tasks) == 0

    def test_add_task(self) -> None:
        state = PipelineState(request_id="test-2")
        task = Task(task_id="t1", description="X", action="Y")
        state.tasks["t1"] = task
        assert len(state.tasks) == 1


class TestToolCall:
    """ToolCall schema."""

    def test_valid_tool_call(self) -> None:
        tc = ToolCall(
            name=ToolName.READ_FILE,
            params={"path": "/tmp/test.txt"},  # noqa: S108
            rationale="Need to read config",
        )
        assert tc.name == ToolName.READ_FILE

    def test_invalid_tool_name_rejected(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            ToolCall(name="nonexistent_tool", params={})


class TestEnumValues:
    """Ensure enum values are correct."""

    def test_task_statuses(self) -> None:
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.VERIFYING.value == "verifying"
        assert TaskStatus.ROLLED_BACK.value == "rolled_back"

    def test_tool_names(self) -> None:
        assert ToolName.READ_FILE.value == "read_file"
        assert ToolName.WRITE_FILE.value == "write_file"
        assert ToolName.EDIT_FILE_AST.value == "edit_file_ast"
        assert ToolName.BASH_EXECUTE.value == "bash_execute"
