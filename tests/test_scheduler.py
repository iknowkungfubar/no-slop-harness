"""Test suite for pipeline scheduler."""

from __future__ import annotations

import pytest

from no_slop_harness.pipeline_scheduler import ResultCollector, TaskScheduler
from no_slop_harness.schemas import Task, TaskStatus


class TestTaskScheduler:
    """TaskScheduler correctly orders and advances through tasks."""

    def test_simple_ordering(self) -> None:
        tasks = [
            Task(task_id="t1", description="A", action="X", priority=1),
            Task(task_id="t2", description="B", action="Y", priority=0),
            Task(task_id="t3", description="C", action="Z", priority=5),
        ]
        scheduler = TaskScheduler(tasks, [])
        order = [t.task_id for t in scheduler.ordered_tasks]
        # Highest priority first
        assert order[0] == "t3"

    def test_dependencies_respected(self) -> None:
        tasks = [
            Task(task_id="t1", description="A", action="X"),
            Task(task_id="t2", description="B", action="Y", dependencies=["t1"]),
        ]
        scheduler = TaskScheduler(tasks, [])
        order = [t.task_id for t in scheduler.ordered_tasks]
        assert order.index("t1") < order.index("t2")

    def test_next_iterates_through_tasks(self) -> None:
        tasks = [
            Task(task_id="t1", description="A", action="X"),
            Task(task_id="t2", description="B", action="Y"),
        ]
        scheduler = TaskScheduler(tasks, [])
        assert scheduler.next().task_id == "t1"
        assert scheduler.next().task_id == "t2"
        assert scheduler.next() is None

    def test_cyclic_dependency_raises(self) -> None:
        tasks = [
            Task(task_id="a", description="A", action="X", dependencies=["b"]),
            Task(task_id="b", description="B", action="Y", dependencies=["a"]),
        ]
        with pytest.raises(ValueError, match="Invalid DAG"):
            TaskScheduler(tasks, [])

    def test_mark_complete(self) -> None:
        tasks = [Task(task_id="t1", description="A", action="X")]
        scheduler = TaskScheduler(tasks, [])
        task = scheduler.next()
        scheduler.mark_complete(task.task_id, "Done!")
        assert task.status == TaskStatus.COMPLETED
        assert task.result == "Done!"


class TestResultCollector:
    """ResultCollector aggregates pipeline results."""

    def test_empty_collector(self) -> None:
        rc = ResultCollector()
        assert rc.success is True  # vacuously true
        assert "0/0 completed" in rc.summary()

    def test_all_success(self) -> None:
        rc = ResultCollector()
        rc.add("t1", "completed", "output1")
        rc.add("t2", "completed", "output2")
        assert rc.success is True
        assert "2/2 completed" in rc.summary()

    def test_one_failure(self) -> None:
        rc = ResultCollector()
        rc.add("t1", "completed", "ok")
        rc.add("t2", "failed", "error")
        assert rc.success is False
        assert "1 failed" in rc.summary()

    def test_report_returns_records(self) -> None:
        rc = ResultCollector()
        rc.add("t1", "completed", "ok", duration_ms=123.0)
        report = rc.report()
        assert len(report) == 1
        assert report[0]["task_id"] == "t1"
        assert report[0]["duration_ms"] == 123.0
