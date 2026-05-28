"""Test suite for the async pipeline orchestrator."""

from __future__ import annotations

import asyncio

from no_slop_harness.async_orchestrator import (
    AsyncPipelineConfig,
    AsyncPipelineOrchestrator,
)
from no_slop_harness.schemas import (
    SandboxConfig,
    Task,
    TaskStatus,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


async def _always_pass_implement(task: Task) -> str:
    """Implementor that always succeeds."""
    return f"Done: {task.task_id}"


async def _always_pass_verify(task_id: str, result: str) -> bool:
    """Verifier that always passes."""
    return True


async def _always_fail_implement(task: Task) -> str:
    """Implementor that always fails verification scenario."""
    raise RuntimeError("Simulated failure")


async def _conditional_verify(task_id: str, result: str) -> bool:
    """Verifier that passes for specific task IDs."""
    return task_id != "bad_task"


class TestAsyncPipelineConfig:
    """AsyncPipelineConfig defaults and overrides."""

    def test_defaults(self) -> None:
        cfg = AsyncPipelineConfig()
        assert cfg.max_parallel_tasks == 4
        assert cfg.task_timeout_seconds == 300.0
        assert cfg.max_retries_per_task == 3

    def test_custom_values(self) -> None:
        cfg = AsyncPipelineConfig(max_parallel_tasks=2, max_retries_per_task=1)
        assert cfg.max_parallel_tasks == 2
        assert cfg.max_retries_per_task == 1


class TestAsyncOrchestratorPlan:
    """Async orchestrator plan acceptance (ingest_tasks)."""

    def test_ingest_empty_tasks(self) -> None:
        orch = AsyncPipelineOrchestrator()
        msg = orch.ingest_tasks([])
        assert msg.phase == "plan"
        assert msg.payload["task_count"] == 0

    def test_ingest_tasks_with_deps(self) -> None:
        tasks = [
            Task(task_id="t1", description="First", action="Create"),
            Task(task_id="t2", description="Second", action="Modify", dependencies=["t1"]),
        ]
        orch = AsyncPipelineOrchestrator()
        msg = orch.ingest_tasks(tasks)
        assert msg.phase == "plan"
        assert msg.payload["task_order"] == ["t1", "t2"]

    def test_cyclic_plan_rejected(self) -> None:
        tasks = [
            Task(task_id="a", description="A", action="X", dependencies=["b"]),
            Task(task_id="b", description="B", action="Y", dependencies=["a"]),
        ]
        orch = AsyncPipelineOrchestrator()
        msg = orch.ingest_tasks(tasks)
        assert msg.error is not None

    def test_priority_ordering(self) -> None:
        tasks = [
            Task(task_id="low", description="Low", action="X", priority=1),
            Task(task_id="high", description="High", action="Y", priority=10),
            Task(task_id="mid", description="Mid", action="Z", priority=5),
        ]
        orch = AsyncPipelineOrchestrator()
        orch.ingest_tasks(tasks)
        order = orch.state.task_order
        assert order[0] == "high"


class TestAsyncOrchestratorRun:
    """Async pipeline execution."""

    def test_single_task_success(self) -> None:
        orch = AsyncPipelineOrchestrator(
            config=AsyncPipelineConfig(max_parallel_tasks=2),
        )
        tasks = [Task(task_id="t1", description="Test", action="Do")]
        orch.ingest_tasks(tasks)

        success = asyncio.run(orch.run(_always_pass_implement, _always_pass_verify))
        assert success is True
        assert orch.state.completed is True
        assert orch.state.tasks["t1"].status == TaskStatus.COMPLETED

    def test_multiple_independent_tasks(self) -> None:
        orch = AsyncPipelineOrchestrator(
            config=AsyncPipelineConfig(max_parallel_tasks=4),
        )
        tasks = [
            Task(task_id="t1", description="A", action="X"),
            Task(task_id="t2", description="B", action="Y"),
            Task(task_id="t3", description="C", action="Z"),
        ]
        orch.ingest_tasks(tasks)

        success = asyncio.run(orch.run(_always_pass_implement, _always_pass_verify))
        assert success is True
        for tid in ("t1", "t2", "t3"):
            assert orch.state.tasks[tid].status == TaskStatus.COMPLETED

    def test_dependent_tasks_ordered(self) -> None:
        """Tasks with dependencies execute in order."""
        execution_order: list[str] = []

        async def tracking_implement(task: Task) -> str:
            execution_order.append(task.task_id)
            return f"Done: {task.task_id}"

        orch = AsyncPipelineOrchestrator(
            config=AsyncPipelineConfig(max_parallel_tasks=1),
        )
        tasks = [
            Task(task_id="t1", description="Base", action="Create"),
            Task(task_id="t2", description="Derived", action="Modify", dependencies=["t1"]),
            Task(task_id="t3", description="Final", action="Polish", dependencies=["t2"]),
        ]
        orch.ingest_tasks(tasks)

        success = asyncio.run(orch.run(tracking_implement, _always_pass_verify))
        assert success is True
        assert execution_order == ["t1", "t2", "t3"]

    def test_verification_failure(self) -> None:
        """A task that fails verification should cause the pipeline to fail."""
        orch = AsyncPipelineOrchestrator(
            config=AsyncPipelineConfig(max_parallel_tasks=2, max_retries_per_task=1),
        )
        tasks = [Task(task_id="bad_task", description="Will fail", action="X")]
        orch.ingest_tasks(tasks)

        success = asyncio.run(orch.run(_always_pass_implement, _conditional_verify))
        assert success is False
        assert orch.state.tasks["bad_task"].status == TaskStatus.FAILED

    def test_task_timeout(self) -> None:
        """A slow task should timeout."""

        async def slow_implement(task: Task) -> str:
            await asyncio.sleep(1.0)
            return "too late"

        orch = AsyncPipelineOrchestrator(
            config=AsyncPipelineConfig(
                max_parallel_tasks=1,
                task_timeout_seconds=0.1,
                max_retries_per_task=0,
            ),
        )
        tasks = [Task(task_id="slow", description="Slow", action="X")]
        orch.ingest_tasks(tasks)

        success = asyncio.run(orch.run(slow_implement, _always_pass_verify))
        assert success is False
        assert orch.state.tasks["slow"].status == TaskStatus.FAILED

    def test_diamond_dependency(self) -> None:
        """Diamond DAG: t1 -> t2, t1 -> t3, t2 + t3 -> t4."""
        orch = AsyncPipelineOrchestrator(
            config=AsyncPipelineConfig(max_parallel_tasks=4),
        )
        tasks = [
            Task(task_id="t1", description="Root", action="Create"),
            Task(task_id="t2", description="Left", action="Modify", dependencies=["t1"]),
            Task(task_id="t3", description="Right", action="Modify", dependencies=["t1"]),
            Task(task_id="t4", description="Merge", action="Integrate", dependencies=["t2", "t3"]),
        ]
        orch.ingest_tasks(tasks)

        success = asyncio.run(orch.run(_always_pass_implement, _always_pass_verify))
        assert success is True
        for tid in ("t1", "t2", "t3", "t4"):
            assert orch.state.tasks[tid].status == TaskStatus.COMPLETED

    def test_retry_on_verification_failure(self) -> None:
        """Task retries on verification failure."""
        attempt_counts: dict[str, int] = {}

        async def track_implement(task: Task) -> str:
            attempt_counts[task.task_id] = attempt_counts.get(task.task_id, 0) + 1
            return f"attempt {attempt_counts[task.task_id]}"

        async def pass_on_retry(task_id: str, result: str) -> bool:
            return "attempt 2" in result

        orch = AsyncPipelineOrchestrator(
            config=AsyncPipelineConfig(
                max_parallel_tasks=1,
                max_retries_per_task=2,
                retry_delay_seconds=0.01,
            ),
        )
        tasks = [Task(task_id="t1", description="Retry", action="X")]
        orch.ingest_tasks(tasks)

        success = asyncio.run(orch.run(track_implement, pass_on_retry))
        assert success is True
        assert attempt_counts["t1"] == 2

    def test_status_report(self) -> None:
        orch = AsyncPipelineOrchestrator()
        tasks = [Task(task_id="t1", description="X", action="Y")]
        orch.ingest_tasks(tasks)

        status = orch.status()
        assert status["total_tasks"] == 1
        assert status["pending"] == 1
        assert "metrics" in status

    def test_sandbox_config_stored(self) -> None:
        sandbox = SandboxConfig(timeout_seconds=120)
        orch = AsyncPipelineOrchestrator(sandbox_config=sandbox)
        assert orch.sandbox_config.timeout_seconds == 120

    def test_request_id_unique(self) -> None:
        orch1 = AsyncPipelineOrchestrator()
        orch2 = AsyncPipelineOrchestrator()
        assert orch1.request_id != orch2.request_id

    def test_failed_dependency_blocks_downstream(self) -> None:
        """When a dependency fails, downstream tasks should not execute."""

        async def fail_first(task: Task) -> str:
            if task.task_id == "t1":
                raise RuntimeError("t1 failed")
            return f"Done: {task.task_id}"

        orch = AsyncPipelineOrchestrator(
            config=AsyncPipelineConfig(max_parallel_tasks=1, max_retries_per_task=0),
        )
        tasks = [
            Task(task_id="t1", description="Fail", action="X"),
            Task(task_id="t2", description="Never runs", action="Y", dependencies=["t1"]),
        ]
        orch.ingest_tasks(tasks)

        success = asyncio.run(orch.run(fail_first, _always_pass_verify))
        assert success is False
        assert orch.state.tasks["t1"].status == TaskStatus.FAILED
        # t2 should be PENDING (never got past dependency check)
        assert orch.state.tasks["t2"].status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
