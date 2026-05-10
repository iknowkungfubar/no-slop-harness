"""Main CIV orchestration loop."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .agents import Coordinator, Implementor, Verifier
from .client import InferenceClient
from .git_isolation import WorktreeManager
from .schemas import Task, TaskPlan, TaskStatus, VerificationResult

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """Outcome of a single task execution."""

    task: Task
    execution_log: list[dict] = field(default_factory=list)
    verification: VerificationResult | None = None
    commit_sha: str | None = None


@dataclass
class OrchestratorResult:
    """Aggregate outcome of the full CIV pipeline."""

    plan: TaskPlan
    results: list[TaskResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.task.status == TaskStatus.COMPLETED for r in self.results)


class Orchestrator:
    """Runs the full Coordinator -> Implementor -> Verifier pipeline."""

    def __init__(self, client: InferenceClient, repo_path: str | Path):
        self.coordinator = Coordinator(client)
        self.implementor = Implementor(client)
        self.verifier = Verifier(client)
        self.worktrees = WorktreeManager(repo_path)
        self.repo_path = Path(repo_path).resolve()

    def run(self, prompt: str, context: str = "") -> OrchestratorResult:
        """Execute the full CIV pipeline for *prompt*."""
        plan = self.coordinator.plan(prompt, context)
        logger.info("Plan: %d tasks", len(plan.tasks))

        ordered = _topological_sort(plan.tasks)
        results: list[TaskResult] = []

        for task in ordered:
            task.status = TaskStatus.IN_PROGRESS
            tr = self._execute_task(task)
            results.append(tr)

            if task.status == TaskStatus.FAILED:
                logger.warning("Task %s failed — aborting remaining tasks", task.id)
                for remaining in ordered:
                    if remaining.status == TaskStatus.PENDING:
                        remaining.status = TaskStatus.FAILED
                break

        self.worktrees.cleanup()
        return OrchestratorResult(plan=plan, results=results)

    # -- internal ------------------------------------------------------------

    def _execute_task(self, task: Task) -> TaskResult:
        tr = TaskResult(task=task)

        with self.worktrees.isolated(task.id) as wt:
            log = self.implementor.execute(
                task, context=f"Working directory: {wt.path}"
            )
            tr.execution_log = log

            sha = self.worktrees.commit(wt, f"[{task.id}] {task.description}")
            tr.commit_sha = sha

            diff = self.worktrees.diff_from_base(wt) if sha else ""

            verification = self.verifier.verify(task, log, diff)
            tr.verification = verification

            if verification.passed and sha:
                merged = self.worktrees.merge_to_base(wt)
                task.status = TaskStatus.COMPLETED if merged else TaskStatus.FAILED
            elif verification.passed:
                task.status = TaskStatus.COMPLETED
            else:
                task.status = TaskStatus.FAILED
                logger.warning(
                    "Verification failed for %s: %s", task.id, verification.failures
                )

        return tr


def _topological_sort(tasks: list[Task]) -> list[Task]:
    """Sort tasks respecting dependency order (Kahn-style)."""
    by_id = {t.id: t for t in tasks}
    visited: set[str] = set()
    result: list[Task] = []

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        visited.add(task_id)
        task = by_id[task_id]
        for dep in task.dependencies:
            if dep in by_id:
                visit(dep)
        result.append(task)

    for t in tasks:
        visit(t.id)

    return result
