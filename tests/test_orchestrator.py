"""Test suite for PipelineOrchestrator."""

from __future__ import annotations

from no_slop_harness.orchestrator import PipelineOrchestrator
from no_slop_harness.schemas import SandboxConfig, Task, TaskDependency, TaskStatus


class TestPipelineOrchestratorPlan:
    """Coordinator -> Orchestrator plan acceptance."""

    def test_ingest_empty_tasks(self) -> None:
        pipe = PipelineOrchestrator()
        msg = pipe.ingest_tasks([])
        assert msg.phase == "plan"
        assert msg.payload["task_count"] == 0

    def test_ingest_tasks_no_deps(self) -> None:
        tasks = [
            Task(task_id="t1", description="First", action="Create file"),
            Task(task_id="t2", description="Second", action="Edit file"),
        ]
        pipe = PipelineOrchestrator()
        msg = pipe.ingest_tasks(tasks)
        assert msg.phase == "plan"
        assert msg.payload["task_count"] == 2
        assert "t1" in msg.payload["task_order"]
        assert "t2" in msg.payload["task_order"]

    def test_ingest_tasks_with_deps(self) -> None:
        tasks = [
            Task(task_id="t1", description="Base", action="Create"),
            Task(task_id="t2", description="Derived", action="Modify", dependencies=["t1"]),
        ]
        pipe = PipelineOrchestrator()
        msg = pipe.ingest_tasks(tasks, deps=[TaskDependency(predecessor="t1", successor="t2")])
        assert msg.phase == "plan"
        assert msg.payload["task_order"] == ["t1", "t2"]

    def test_cyclic_plan_rejected(self) -> None:
        tasks = [
            Task(task_id="a", description="A", action="X", dependencies=["b"]),
            Task(task_id="b", description="B", action="Y", dependencies=["a"]),
        ]
        pipe = PipelineOrchestrator()
        msg = pipe.ingest_tasks(tasks)
        assert msg.error is not None
        assert "Cyclic" in msg.error or "cycle" in msg.error.lower()


class TestPipelineOrchestratorImplement:
    """Implementor task lifecycle."""

    def test_next_task_returns_pending(self) -> None:
        tasks = [Task(task_id="t1", description="X", action="Y")]
        pipe = PipelineOrchestrator()
        pipe.ingest_tasks(tasks)
        task = pipe.next_task()
        assert task is not None
        assert task.task_id == "t1"

    def test_next_task_after_completion_returns_none(self) -> None:
        tasks = [Task(task_id="t1", description="X", action="Y")]
        pipe = PipelineOrchestrator()
        pipe.ingest_tasks(tasks)
        pipe.next_task()
        pipe.report_result("t1", "Done", success=True)
        assert pipe.next_task() is None

    def test_report_failure_sets_state(self) -> None:
        tasks = [Task(task_id="t1", description="X", action="Y")]
        pipe = PipelineOrchestrator()
        pipe.ingest_tasks(tasks)
        pipe.next_task()
        msg = pipe.report_result("t1", "Compilation error", success=False)
        assert msg.phase == "done"
        assert pipe.state.failed is True
        assert pipe.state.failure_reason == "Compilation error"

    def test_report_success_triggers_verify(self) -> None:
        tasks = [Task(task_id="t1", description="X", action="Y")]
        pipe = PipelineOrchestrator()
        pipe.ingest_tasks(tasks)
        pipe.next_task()
        msg = pipe.report_result("t1", "Created file", success=True)
        assert msg.phase == "verify"
        assert msg.task_id == "t1"

    def test_unknown_task_result_rejected(self) -> None:
        pipe = PipelineOrchestrator()
        pipe.ingest_tasks([])
        msg = pipe.report_result("nonexistent", "", success=True)
        assert msg.error is not None


class TestPipelineOrchestratorVerify:
    """Verifier lifecycle."""

    def test_verify_completed_task(self) -> None:
        tasks = [Task(task_id="t1", description="X", action="Y")]
        pipe = PipelineOrchestrator()
        pipe.ingest_tasks(tasks)
        pipe.next_task()
        pipe.report_result("t1", "Done", success=True)

        msg = pipe.verify_task("t1")
        assert msg.phase == "verify"
        assert msg.payload["action"] == "run_tests"

    def test_verify_uncompleted_task_rejected(self) -> None:
        tasks = [Task(task_id="t1", description="X", action="Y")]
        pipe = PipelineOrchestrator()
        pipe.ingest_tasks(tasks)
        msg = pipe.verify_task("t1")
        assert msg.error is not None
        assert "expected completed" in msg.error

    def test_verification_pass_completes_pipeline(self) -> None:
        tasks = [Task(task_id="t1", description="X", action="Y")]
        pipe = PipelineOrchestrator()
        pipe.ingest_tasks(tasks)
        pipe.next_task()
        pipe.report_result("t1", "Done", success=True)
        pipe.verify_task("t1")

        msg = pipe.verification_complete("t1", passed=True, detail="All tests pass")
        assert msg.phase == "done"  # Only task, so pipeline done
        assert pipe.state.completed is True

    def test_verification_fail_marks_task_failed(self) -> None:
        tasks = [Task(task_id="t1", description="X", action="Y")]
        pipe = PipelineOrchestrator()
        pipe.ingest_tasks(tasks)
        pipe.next_task()
        pipe.report_result("t1", "Done", success=True)
        pipe.verify_task("t1")

        msg = pipe.verification_complete("t1", passed=False, detail="Test failure")
        assert msg  # noqa: F841 — verify return is not None
        assert pipe.state.tasks["t1"].status == TaskStatus.FAILED


class TestPipelineStatus:
    """Status reporting."""

    def test_status_counts(self) -> None:
        tasks = [
            Task(task_id="t1", description="A", action="X"),
            Task(task_id="t2", description="B", action="Y"),
            Task(task_id="t3", description="C", action="Z"),
        ]
        pipe = PipelineOrchestrator()
        pipe.ingest_tasks(tasks)

        status = pipe.status()
        assert status["total_tasks"] == 3
        assert status["pending"] == 3
        assert status["completed"] == 0

    def test_request_id_present(self) -> None:
        pipe = PipelineOrchestrator()
        status = pipe.status()
        assert len(status["request_id"]) > 0

    def test_all_done_flag(self) -> None:
        tasks = [Task(task_id="t1", description="X", action="Y")]
        pipe = PipelineOrchestrator()
        pipe.ingest_tasks(tasks)
        pipe.next_task()
        pipe.report_result("t1", "Done", success=True)
        pipe.verify_task("t1")
        pipe.verification_complete("t1", passed=True)

        status = pipe.status()
        assert status["all_done"] is True


class TestSandboxedInOrchestrator:
    """Sandbox config propagation."""

    def test_sandbox_config_stored(self) -> None:
        sandbox = SandboxConfig(
            allowed_commands=["echo", "ls"],
            blocked_commands=["rm"],
            timeout_seconds=30,
        )
        pipe = PipelineOrchestrator(sandbox_config=sandbox)
        assert pipe.sandbox_config.allowed_commands == ["echo", "ls"]

    def test_default_sandbox_has_blocked_commands(self) -> None:
        pipe = PipelineOrchestrator()
        assert len(pipe.sandbox_config.blocked_commands) > 0
