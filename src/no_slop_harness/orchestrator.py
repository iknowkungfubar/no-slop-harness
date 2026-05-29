"""CIV Pipeline Orchestrator.

Coordinates the Coordinator -> Implementor -> Verifier lifecycle.
"""

# mypy: disable-error-code="call-arg"

from __future__ import annotations

import logging
from uuid import uuid4

from .dag import CyclicDependencyError, topological_sort
from .schemas import (
    CIVMessage,
    PipelineState,
    SandboxConfig,
    Task,
    TaskDependency,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestrates the CIV pipeline for a single user request."""

    def __init__(self, sandbox_config: SandboxConfig | None = None) -> None:
        self.sandbox_config = sandbox_config or SandboxConfig()
        self.state = PipelineState(
            request_id=str(uuid4()),
            tasks={},
            task_order=[],
            current_index=0,
        )

    @property
    def request_id(self) -> str:
        return self.state.request_id

    # --- Coordinator phase -------------------------------------------------

    def ingest_tasks(
        self, tasks: list[Task], deps: list[TaskDependency] | None = None
    ) -> CIVMessage:  # noqa: E501
        """Accept the task plan from the Coordinator."""
        for t in tasks:
            self.state.tasks[t.task_id] = t

        deps = deps or []
        dep_list: list[TaskDependency] = []
        seen_edges: set[tuple[str, str]] = set()
        for t in tasks:
            for dep_tid in t.dependencies:
                edge = (dep_tid, t.task_id)
                if edge not in seen_edges:
                    dep_list.append(TaskDependency(predecessor=dep_tid, successor=t.task_id))
                    seen_edges.add(edge)
        dep_list.extend(deps)

        try:
            self.state.task_order = topological_sort(tasks, dep_list)
        except CyclicDependencyError as e:
            self.state.failed = True
            self.state.failure_reason = str(e)
            return CIVMessage(
                sender="orchestrator",
                recipient="coordinator",
                phase="plan",
                error=str(e),
            )
        except ValueError as e:
            self.state.failed = True
            self.state.failure_reason = str(e)
            return CIVMessage(
                sender="orchestrator",
                recipient="coordinator",
                phase="plan",
                error=str(e),
            )

        msg = CIVMessage(
            sender="orchestrator",
            recipient="implementor",
            phase="plan",
            payload={
                "task_order": self.state.task_order,
                "task_count": len(tasks),
            },
        )
        logger.info("Plan accepted: %d tasks", len(tasks))
        return msg

    # --- Implementor phase --------------------------------------------------

    def next_task(self) -> Task | None:
        """Return the next pending task, or None if pipeline is done."""
        if self.state.failed or self.state.completed:
            return None

        ordered = [self.state.tasks[tid] for tid in self.state.task_order]
        for task in ordered:
            if task.status in (TaskStatus.PENDING, TaskStatus.ASSIGNED):
                task.status = TaskStatus.IN_PROGRESS
                return task

        return None

    def report_result(self, task_id: str, result: str, success: bool) -> CIVMessage:
        """Record the outcome of an Implementor task."""
        task = self.state.tasks.get(task_id)
        if task is None:
            return CIVMessage(
                sender="orchestrator",
                recipient="implementor",
                task_id=task_id,
                phase="implement",
                error=f"Unknown task_id: {task_id}",
            )

        task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        task.result = result

        # Re-queue for verification if this was a retry of a previously failed task
        if not success:
            self.state.failed = True
            self.state.failure_reason = result

        phase = "verify" if success else "done"
        return CIVMessage(
            sender="orchestrator",
            recipient="verifier" if success else "coordinator",
            task_id=task_id,
            phase=phase,
            payload={"status": task.status.value, "result": result},
        )

    # --- Verifier phase ----------------------------------------------------

    def verify_task(self, task_id: str) -> CIVMessage:
        """Trigger verification for a completed task."""
        task = self.state.tasks.get(task_id)
        if task is None:
            return CIVMessage(
                sender="orchestrator",
                recipient="verifier",
                task_id=task_id,
                phase="verify",
                error=f"Unknown task_id: {task_id}",
            )

        if task.status != TaskStatus.COMPLETED:
            return CIVMessage(
                sender="orchestrator",
                recipient="verifier",
                task_id=task_id,
                phase="verify",
                error=f"Task {task_id} status is {task.status.value}, expected completed",
            )

        task.status = TaskStatus.VERIFYING
        return CIVMessage(
            sender="orchestrator",
            recipient="verifier",
            task_id=task_id,
            phase="verify",
            payload={
                "action": "run_tests",
                "target_file": task.target_file,
            },
        )

    def verification_complete(self, task_id: str, passed: bool, detail: str = "") -> CIVMessage:
        """Record the verification verdict."""
        task = self.state.tasks.get(task_id)
        if task is None:
            return CIVMessage(
                sender="orchestrator",
                recipient="verifier",
                task_id=task_id,
                phase="verify",
                error=f"Unknown task_id: {task_id}",
            )

        task.status = TaskStatus.COMPLETED if passed else TaskStatus.FAILED
        task.result = detail

        all_done = all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.ROLLED_BACK)
            for t in self.state.tasks.values()
        )
        if all_done:
            self.state.completed = True

        return CIVMessage(
            sender="orchestrator",
            recipient="coordinator",
            task_id=task_id,
            phase="done" if self.state.completed else "verify",
            payload={"passed": passed, "detail": detail, "all_complete": self.state.completed},
        )

    # --- Pipeline status ---------------------------------------------------

    def status(self) -> dict:
        """Return a serializable status dict for UI or logging."""
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
        }
