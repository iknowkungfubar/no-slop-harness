"""Test suite for DAG utilities."""

from __future__ import annotations

import pytest

from no_slop_harness.dag import (
    CyclicDependencyError,
    topological_sort,
    validate_dag,
)
from no_slop_harness.schemas import Task, TaskDependency


def _make_task(tid: str, deps: list[str] | None = None, priority: int = 0) -> Task:
    return Task(
        task_id=tid,
        description=f"Task {tid}",
        action=f"Action {tid}",
        dependencies=deps or [],
        priority=priority,
    )


class TestTopologicalSort:
    """Topological sort produces valid execution order."""

    def test_single_task_no_deps(self) -> None:
        tasks = [_make_task("t1")]
        result = topological_sort(tasks, [])
        assert result == ["t1"]

    def test_linear_chain(self) -> None:
        tasks = [_make_task("t1"), _make_task("t2", deps=["t1"]), _make_task("t3", deps=["t2"])]
        result = topological_sort(tasks, [])
        assert result.index("t1") < result.index("t2")
        assert result.index("t2") < result.index("t3")

    def test_diamond_dependency(self) -> None:
        """t1 -> t2, t1 -> t3, t2 + t3 -> t4"""
        tasks = [
            _make_task("t1"),
            _make_task("t2", deps=["t1"]),
            _make_task("t3", deps=["t1"]),
            _make_task("t4", deps=["t2", "t3"]),
        ]
        result = topological_sort(tasks, [])
        assert result.index("t1") < result.index("t2")
        assert result.index("t1") < result.index("t3")
        assert result.index("t2") < result.index("t4")
        assert result.index("t3") < result.index("t4")

    def test_independent_tasks_ordered_by_priority(self) -> None:
        tasks = [
            _make_task("low", priority=1),
            _make_task("high", priority=10),
            _make_task("mid", priority=5),
        ]
        result = topological_sort(tasks, [])
        assert result[0] == "high"
        assert result[1] == "mid"
        assert result[2] == "low"

    def test_cyclic_dependency_raises(self) -> None:
        tasks = [_make_task("a", deps=["b"]), _make_task("b", deps=["a"])]
        with pytest.raises(CyclicDependencyError):
            topological_sort(tasks, [])

    def test_three_cycle_raises(self) -> None:
        tasks = [
            _make_task("a", deps=["c"]),
            _make_task("b", deps=["a"]),
            _make_task("c", deps=["b"]),
        ]
        with pytest.raises(CyclicDependencyError):
            topological_sort(tasks, [])


class TestValidateDAG:
    """DAG validation returns list of errors."""

    def test_valid_dag(self) -> None:
        tasks = [_make_task("t1"), _make_task("t2", deps=["t1"])]
        errors = validate_dag(tasks, [])
        assert errors == []

    def test_orphan_predecessor(self) -> None:
        tasks = [_make_task("t1", deps=["ghost"])]
        errors = validate_dag(tasks, [])
        assert len(errors) > 0
        assert any("ghost" in e for e in errors)

    def test_self_reference(self) -> None:
        tasks = [_make_task("t1", deps=["t1"])]
        errors = validate_dag(tasks, [])
        assert any("itself" in e for e in errors)

    def test_explicit_dependencies_validated(self) -> None:
        tasks = [_make_task("t1")]
        deps = [TaskDependency(predecessor="t1", successor="nonexistent")]
        errors = validate_dag(tasks, deps)
        assert len(errors) > 0
        assert any("nonexistent" in e for e in errors)
