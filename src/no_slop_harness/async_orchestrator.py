"""Asynchronous CIV Pipeline Orchestrator.

Extends the synchronous PipelineOrchestrator with asyncio-based
parallel task execution, concurrent verification, and timeout management.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from uuid import uuid4

from .dag import CyclicDependencyError, topological_sort
from .logging_config import PipelineLogger
from .metrics import MetricsRegistry
from .schemas import (
    CIVMessage,
    PipelineState,
    SandboxConfig,
    Task,
    TaskDependency,
    TaskStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class AsyncPipelineConfig:
    """Configuration for the async pipeline orchestrator."""

    max_parallel_tasks: int = 4
    task_timeout_seconds: float = 300.0
    max_retries_per_task: int = 3
    retry_delay_seconds: float = 2.0
    metrics: MetricsRegistry = field(default_factory=MetricsRegistry)


class AsyncPipelineOrchestrator:
    """Asynchronous CIV pipeline orchestrator with parallel task execution.

    Tasks are executed in dependency order, with independent tasks
    running concurrently up to `max_parallel_tasks`.

    Usage:
        orchestrator = AsyncPipelineOrchestrator()
        orchestrator.ingest_tasks(tasks)

        async def implement(task: Task) -> str:
            # LLM implements the task
            return "done"

        async def verify(task_id: str, result: str) -> bool:
            # Run tests and checks
            return True

        await orchestrator.run(implement, verify)
        print(orchestrator.state.completed)
    """

    def __init__(
        self,
        sandbox_config: SandboxConfig | None = None,
        config: AsyncPipelineConfig | None = None,
    ) -> None:
        self.sandbox_config = sandbox_config or SandboxConfig()
        self.config = config or AsyncPipelineConfig()
        self.state = PipelineState(
            request_id=str(uuid4()),
            tasks={},
            task_order=[],
            current_index=0,
        )
        self._plog = PipelineLogger("async_orchestrator", request_id=self.state.request_id)

        # Metrics
        self._task_timer = self.config.metrics.timer("async_task_duration_ms")
        self._task_counter = self.config.metrics.counter("async_tasks_total")
        self._parallel_hist = self.config.metrics.histogram(
            "async_parallel_tasks", buckets=(1, 2, 3, 4, 5, 8, 10, 16)
        )
        self._retry_counter = self.config.metrics.counter("async_task_retries")

    @property
    def request_id(self) -> str:
        return self.state.request_id

    # ── Coordinator phase ────────────────────────────────────────────────

    def ingest_tasks(
        self, tasks: list[Task], deps: list[TaskDependency] | None = None
    ) -> CIVMessage:
        """Accept the task plan from the Coordinator (synchronous DAG validation)."""
        for t in tasks:
            self.state.tasks[t.task_id] = t

        deps = deps or []
        dep_list: list[TaskDependency] = []
        for t in tasks:
            for dep_tid in t.dependencies:
                dep_list.append(TaskDependency(predecessor=dep_tid, successor=t.task_id))
        dep_list.extend(deps)

        try:
            self.state.task_order = topological_sort(tasks, dep_list)
        except (CyclicDependencyError, ValueError) as e:
            self.state.failed = True
            self.state.failure_reason = str(e)
            return CIVMessage(
                sender="orchestrator",
                recipient="coordinator",
                phase="plan",
                error=str(e),
            )

        self._plog.info("Plan accepted", task_count=len(tasks))
        return CIVMessage(
            sender="orchestrator",
            recipient="implementor",
            phase="plan",
            payload={"task_order": self.state.task_order, "task_count": len(tasks)},
        )

    # ── Pipeline execution ────────────────────────────────────────────────

    async def run(
        self,
        implement_fn: Callable[[Task], Awaitable[str]],
        verify_fn: Callable[[str, str], Awaitable[bool]],
    ) -> bool:
        """Run the full pipeline asynchronously.

        Args:
            implement_fn: Async callable that executes a task and returns its result.
            verify_fn: Async callable that verifies a task result. Returns True if passed.

        Returns:
            True if all tasks completed and verified successfully.
        """
        self._plog.info("Pipeline starting", task_order=self.state.task_order)

        completed: set[str] = set()
        failed_tasks: set[str] = set()

        while len(completed) + len(failed_tasks) < len(self.state.task_order):
            # Find ready tasks (all dependencies completed)
            ready = self._get_ready_tasks(completed, failed_tasks)

            if not ready:
                if failed_tasks:
                    self._plog.warning(
                        "Pipeline stalled due to failed dependencies",
                        failed=list(failed_tasks),
                        completed=list(completed),
                    )
                    self.state.failed = True
                    self.state.failure_reason = f"Failed tasks blocking pipeline: {failed_tasks}"
                    return False
                # Shouldn't happen if DAG is valid, but guard against infinite loop
                break

            self._parallel_hist.observe(len(ready))

            # Execute ready tasks in parallel
            results = await asyncio.gather(
                *[self._execute_task(tid, implement_fn, verify_fn) for tid in ready],
                return_exceptions=True,
            )

            for tid, result in zip(ready, results, strict=False):
                if isinstance(result, Exception):
                    logger.error("Task %s crashed: %s", tid, result)
                    failed_tasks.add(tid)
                    self.state.tasks[tid].status = TaskStatus.FAILED
                    self.state.tasks[tid].result = str(result)
                elif result:
                    completed.add(tid)
                else:
                    failed_tasks.add(tid)

        success = len(failed_tasks) == 0
        self.state.completed = success
        self._plog.info(
            "Pipeline finished",
            success=success,
            completed=len(completed),
            failed=len(failed_tasks),
        )
        return success

    async def _execute_task(
        self,
        task_id: str,
        implement_fn: Callable[[Task], Awaitable[str]],
        verify_fn: Callable[[str, str], Awaitable[bool]],
    ) -> bool:
        """Execute and verify a single task with retry logic.

        Returns:
            True if the task was implemented and verified successfully.
        """
        task = self.state.tasks[task_id]
        task.status = TaskStatus.IN_PROGRESS
        self._plog.info("Task starting", task_id=task_id)

        for attempt in range(self.config.max_retries_per_task + 1):
            try:
                with self._task_timer.time():
                    result = await asyncio.wait_for(
                        implement_fn(task),
                        timeout=self.config.task_timeout_seconds,
                    )
            except TimeoutError:
                self._plog.warning(
                    "Task timed out",
                    task_id=task_id,
                    attempt=attempt + 1,
                )
                task.result = f"Timeout after {self.config.task_timeout_seconds}s"
                if attempt < self.config.max_retries_per_task:
                    await asyncio.sleep(self.config.retry_delay_seconds)
                    continue
                task.status = TaskStatus.FAILED
                self._task_counter.inc()
                return False
            except Exception as e:
                self._plog.warning("Task error", task_id=task_id, error=str(e), attempt=attempt + 1)
                task.result = str(e)
                if attempt < self.config.max_retries_per_task:
                    await asyncio.sleep(self.config.retry_delay_seconds)
                    continue
                task.status = TaskStatus.FAILED
                self._task_counter.inc()
                return False

            task.result = result
            task.status = TaskStatus.COMPLETED

            # Verify
            task.status = TaskStatus.VERIFYING
            try:
                passed = await verify_fn(task_id, result)
            except Exception as e:
                logger.error("Verification error for task %s: %s", task_id, e)
                passed = False

            if passed:
                task.status = TaskStatus.COMPLETED
                self._task_counter.inc()
                self._plog.info("Task verified", task_id=task_id)
                return True

            self._plog.warning(
                "Verification failed",
                task_id=task_id,
                attempt=attempt + 1,
            )
            self._retry_counter.inc()

            if attempt < self.config.max_retries_per_task:
                task.status = TaskStatus.PENDING  # Reset for retry
                await asyncio.sleep(self.config.retry_delay_seconds)
                task.status = TaskStatus.IN_PROGRESS

        task.status = TaskStatus.FAILED
        self._task_counter.inc()
        return False

    def _get_ready_tasks(self, completed: set[str], failed: set[str]) -> list[str]:
        """Get task IDs that are ready to execute (all deps satisfied)."""
        ready: list[str] = []
        for tid in self.state.task_order:
            if tid in completed or tid in failed:
                continue
            task = self.state.tasks[tid]
            if task.status in (TaskStatus.IN_PROGRESS, TaskStatus.VERIFYING):
                continue

            deps_satisfied = all(dep in completed for dep in task.dependencies)
            if deps_satisfied:
                # Check if any dependency failed
                dep_failed = any(dep in failed for dep in task.dependencies)
                if not dep_failed:
                    ready.append(tid)

        return ready[: self.config.max_parallel_tasks]

    # ── Status ───────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return a serializable status dict."""
        return {
            "request_id": self.request_id,
            "total_tasks": len(self.state.tasks),
            "completed": sum(
                1 for t in self.state.tasks.values() if t.status == TaskStatus.COMPLETED
            ),  # noqa: E501
            "failed": sum(1 for t in self.state.tasks.values() if t.status == TaskStatus.FAILED),
            "in_progress": sum(
                1 for t in self.state.tasks.values() if t.status == TaskStatus.IN_PROGRESS
            ),  # noqa: E501
            "pending": sum(1 for t in self.state.tasks.values() if t.status == TaskStatus.PENDING),
            "all_done": self.state.completed or self.state.failed,
            "metrics": self.config.metrics.report(),
        }
