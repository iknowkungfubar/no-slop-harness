"""DAG utilities for the CIV pipeline task scheduler."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence

from .schemas import Task, TaskDependency


class CyclicDependencyError(ValueError):
    """Raised when the task graph contains a cycle."""


def topological_sort(tasks: Sequence[Task], deps: Sequence[TaskDependency]) -> list[str]:
    """Kahn's algorithm for deterministic topological sorting.

    Returns task IDs in execution order.  Raises CyclicDependencyError
    if the graph contains a cycle.
    """
    task_ids = {t.task_id for t in tasks}
    in_degree: dict[str, int] = {tid: 0 for tid in task_ids}
    adj: dict[str, list[str]] = {tid: [] for tid in task_ids}

    # Add edges from explicit deps
    for dep in deps:
        if dep.predecessor not in task_ids:
            raise ValueError(f"Dependency references unknown predecessor: {dep.predecessor}")
        if dep.successor not in task_ids:
            raise ValueError(f"Dependency references unknown successor: {dep.successor}")
        adj[dep.predecessor].append(dep.successor)
        in_degree[dep.successor] += 1

    # Add edges from task.dependencies (implicit deps)
    for task in tasks:
        for dep_tid in task.dependencies:
            if dep_tid not in task_ids:
                raise ValueError(f"Dependency references unknown task: {dep_tid}")
            if dep_tid != task.task_id:  # skip self-refs, caught in validate
                adj[dep_tid].append(task.task_id)
                in_degree[task.task_id] += 1

    # Stable sort by priority (desc), then task_id (asc) for determinism
    queue = sorted(
        [tid for tid, deg in in_degree.items() if deg == 0],
        key=lambda tid: (-next(t.priority for t in tasks if t.task_id == tid), tid),
    )
    queue = deque(queue)
    result: list[str] = []

    while queue:
        node = queue.popleft()
        result.append(node)

        # Sort neighbours for deterministic ordering
        for neighbour in sorted(adj[node]):
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                # Insert maintaining descending priority order
                _insert_sorted(queue, neighbour, tasks)

    if len(result) != len(task_ids):
        remaining = task_ids - set(result)
        raise CyclicDependencyError(f"Cyclic dependency detected among tasks: {remaining}")

    return result


def _insert_sorted(queue: deque, task_id: str, tasks: Sequence[Task]) -> None:
    """Insert task_id into queue maintaining descending priority, then alphabetical."""
    priority_map = {t.task_id: t.priority for t in tasks}
    p = priority_map.get(task_id, 0)
    inserted = False
    for i, qid in enumerate(queue):
        qp = priority_map.get(qid, 0)
        if p > qp or (p == qp and task_id < qid):
            queue.insert(i, task_id)
            inserted = True
            break
    if not inserted:
        queue.append(task_id)


def validate_dag(tasks: Sequence[Task], deps: Sequence[TaskDependency]) -> list[str]:
    """Validate the DAG and return a list of error strings (empty = valid)."""
    errors: list[str] = []
    task_ids = {t.task_id for t in tasks}

    # Check for orphan dependencies (explicit)
    for dep in deps:
        if dep.predecessor not in task_ids:
            errors.append(f"Orphan predecessor '{dep.predecessor}' not in task set")
        if dep.successor not in task_ids:
            errors.append(f"Orphan successor '{dep.successor}' not in task set")

    # Check for orphan dependencies (implicit from task.dependencies)
    for task in tasks:
        for dep_tid in task.dependencies:
            if dep_tid not in task_ids:
                errors.append(f"Orphan dependency '{dep_tid}' not in task set")

    # Check for self-referencing (explicit)
    for dep in deps:
        if dep.predecessor == dep.successor:
            errors.append(f"Task '{dep.predecessor}' depends on itself")

    # Check for self-referencing (implicit)
    for task in tasks:
        if task.task_id in task.dependencies:
            errors.append(f"Task '{task.task_id}' depends on itself")

    # Check for cycles by attempting topo sort
    try:
        topological_sort(tasks, deps)
    except CyclicDependencyError as e:
        errors.append(str(e))
    except ValueError as e:
        errors.append(str(e))

    return errors
