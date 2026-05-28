"""Task scheduling and execution utilities."""

from __future__ import annotations

import logging

from . import schemas
from .dag import topological_sort, validate_dag

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Deterministic task scheduler that respects the DAG."""

    def __init__(self, tasks: list[schemas.Task], deps: list[schemas.TaskDependency]) -> None:
        self.tasks = {t.task_id: t for t in tasks}
        self.deps = deps
        errors = validate_dag(tasks, deps)
        if errors:
            raise ValueError(f"Invalid DAG: {'; '.join(errors)}")
        self._order = topological_sort(tasks, deps)
        self._idx = 0

    @property
    def ready(self) -> bool:
        return self._idx < len(self._order)

    @property
    def ordered_tasks(self) -> list[schemas.Task]:
        return [self.tasks[tid] for tid in self._order]

    def next(self) -> schemas.Task | None:
        if not self.ready:
            return None
        task = self.tasks[self._order[self._idx]]
        self._idx += 1
        return task

    def mark_complete(self, task_id: str, result: str = "") -> None:
        self.tasks[task_id].status = schemas.TaskStatus.COMPLETED
        self.tasks[task_id].result = result

    def mark_failed(self, task_id: str, reason: str = "") -> None:
        self.tasks[task_id].status = schemas.TaskStatus.FAILED
        self.tasks[task_id].result = reason


class ResultCollector:
    """Collects and reports results from the pipeline run."""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def add(self, task_id: str, status: str, output: str = "", duration_ms: float = 0.0) -> None:
        self.records.append({
            "task_id": task_id,
            "status": status,
            "output": output,
            "duration_ms": duration_ms,
        })

    @property
    def success(self) -> bool:
        return all(r["status"] == "completed" for r in self.records)

    def summary(self) -> str:
        total = len(self.records)
        done = sum(1 for r in self.records if r["status"] == "completed")
        failed = sum(1 for r in self.records if r["status"] == "failed")
        return f"{done}/{total} completed, {failed} failed"

    def report(self) -> list[dict]:
        return list(self.records)
