"""Main CIV orchestration loop."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .agents import Coordinator, Implementor, Verifier
from .client import InferenceClient
from .config import HarnessConfig
from .context import ContextManager
from .executor import ToolExecutor
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

    def summary(self) -> str:
        passed = sum(1 for r in self.results if r.task.status == TaskStatus.COMPLETED)
        failed = sum(1 for r in self.results if r.task.status == TaskStatus.FAILED)
        return f"{passed} passed, {failed} failed, {len(self.plan.tasks)} total"


class Orchestrator:
    """Runs the full Coordinator -> Implementor -> Verifier pipeline."""

    def __init__(
        self,
        client: InferenceClient,
        repo_path: str | Path,
        config: HarnessConfig | None = None,
    ):
        self.config = config or HarnessConfig()
        self.repo_path = Path(repo_path).resolve()
        self.client = client

        self._base_executor = ToolExecutor(
            self.config, self.repo_path, protect_sdlc=True
        )
        self.coordinator = Coordinator(client)
        self.implementor = Implementor(client)
        self.verifier = Verifier(client)
        self.worktrees = WorktreeManager(self.repo_path)
        self.context_mgr = ContextManager(self.repo_path)

        self._on_task_start: list = []
        self._on_task_end: list = []

    def on_task_start(self, callback) -> None:
        """Register a callback invoked when a task begins: ``callback(task)``."""
        self._on_task_start.append(callback)

    def on_task_end(self, callback) -> None:
        """Register a callback invoked when a task ends: ``callback(task_result)``."""
        self._on_task_end.append(callback)

    def run(self, prompt: str, context: str = "") -> OrchestratorResult:
        """Execute the full CIV pipeline for *prompt*."""
        persistent_ctx = self.context_mgr.load()
        full_context = f"{persistent_ctx}\n\n{context}".strip()

        plan = self.coordinator.plan(prompt, full_context)
        logger.info("Plan: %d tasks", len(plan.tasks))

        ordered = _topological_sort(plan.tasks)
        results: list[TaskResult] = []

        for task in ordered:
            task.status = TaskStatus.IN_PROGRESS
            for cb in self._on_task_start:
                cb(task)

            tr = self._execute_task(task, full_context)
            results.append(tr)

            for cb in self._on_task_end:
                cb(tr)

            # Persist task summary
            log_excerpt = json.dumps(tr.execution_log[:3], indent=2) if tr.execution_log else ""
            self.context_mgr.save_task_summary(
                task.id, task.description, task.status.value, log_excerpt
            )

            if task.status == TaskStatus.FAILED:
                logger.warning("Task %s failed — aborting remaining tasks", task.id)
                for remaining in ordered:
                    if remaining.status == TaskStatus.PENDING:
                        remaining.status = TaskStatus.FAILED
                break

        self.worktrees.cleanup()
        return OrchestratorResult(plan=plan, results=results)

    # -- internal ------------------------------------------------------------

    def _execute_task(self, task: Task, context: str) -> TaskResult:
        tr = TaskResult(task=task)

        with self.worktrees.isolated(task.id) as wt:
            wt_executor = self._base_executor.with_root(wt.path)
            impl = Implementor(self.client, executor=wt_executor)
            log = impl.execute(
                task, context=f"Working directory: {wt.path}\n{context}"
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


class CyclicDependencyError(ValueError):
    """Raised when the task DAG contains a cycle."""


def _topological_sort(tasks: list[Task]) -> list[Task]:
    """Sort tasks respecting dependency order (DFS with cycle detection)."""
    by_id = {t.id: t for t in tasks}
    visited: set[str] = set()
    in_stack: set[str] = set()
    result: list[Task] = []

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in in_stack:
            raise CyclicDependencyError(
                f"Cycle detected involving task '{task_id}'"
            )
        in_stack.add(task_id)
        task = by_id[task_id]
        for dep in task.dependencies:
            if dep in by_id:
                visit(dep)
        in_stack.discard(task_id)
        visited.add(task_id)
        result.append(task)

    for t in tasks:
        visit(t.id)

    return result
