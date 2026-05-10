"""Tests for Pydantic schemas."""

from harness.schemas import (
    AgentAction,
    BashExecuteArgs,
    EditFileAstArgs,
    ReadFileArgs,
    Task,
    TaskPlan,
    TaskStatus,
    ToolCall,
    VerificationResult,
    WriteFileArgs,
)


class TestToolSchemas:
    def test_read_file_args(self):
        args = ReadFileArgs(path="/tmp/test.py")
        assert args.path == "/tmp/test.py"

    def test_write_file_args(self):
        args = WriteFileArgs(path="/tmp/test.py", content="print('hi')")
        assert args.content == "print('hi')"

    def test_edit_file_ast_args(self):
        args = EditFileAstArgs(
            path="/tmp/test.py",
            node_target="(function_definition name: (identifier) @name)",
            replacement="new_name",
        )
        assert args.node_target.startswith("(")

    def test_bash_execute_args(self):
        args = BashExecuteArgs(cmd="echo hello")
        assert args.cmd == "echo hello"


class TestAgentSchemas:
    def test_tool_call(self):
        tc = ToolCall(name="read_file", arguments={"path": "/tmp/x"})
        assert tc.name == "read_file"

    def test_agent_action_call_tool(self):
        action = AgentAction(
            action="call_tool",
            tool_call=ToolCall(name="bash_execute", arguments={"cmd": "ls"}),
        )
        assert action.action == "call_tool"
        assert action.tool_call is not None

    def test_agent_action_finish(self):
        action = AgentAction(action="finish", summary="Done")
        assert action.tool_call is None

    def test_task_defaults(self):
        t = Task(id="x", description="y")
        assert t.status == TaskStatus.PENDING
        assert t.dependencies == []
        assert t.assigned_agent == "implementor"

    def test_task_plan(self):
        plan = TaskPlan(
            tasks=[
                Task(id="t1", description="Step one"),
                Task(id="t2", description="Step two", dependencies=["t1"]),
            ]
        )
        assert len(plan.tasks) == 2
        assert plan.tasks[1].dependencies == ["t1"]

    def test_task_plan_json_roundtrip(self):
        plan = TaskPlan(
            tasks=[Task(id="t1", description="Do X", tool_hints=["read_file"])]
        )
        raw = plan.model_dump_json()
        restored = TaskPlan.model_validate_json(raw)
        assert restored.tasks[0].id == "t1"

    def test_verification_result_defaults(self):
        v = VerificationResult(passed=True)
        assert v.failures == []
        assert v.suggestions == []
