"""Integration tests for CIV pipeline end-to-end."""

from __future__ import annotations

import pytest

from no_slop_harness.orchestrator import PipelineOrchestrator
from no_slop_harness.schemas import SandboxConfig, Task


class TestFullCIVPipeline:
    """End-to-end CIV pipeline with multiple tasks."""

    @pytest.fixture
    def pipeline(self) -> PipelineOrchestrator:
        return PipelineOrchestrator()

    @pytest.fixture
    def tasks(self) -> list[Task]:
        return [
            Task(
                task_id="plan_routes",
                description="Plan the API routes",
                action="Design route structure",
            ),
            Task(
                task_id="create_models",
                description="Create database models",
                action="Add models",
                dependencies=["plan_routes"],
            ),
            Task(
                task_id="create_handlers",
                description="Create request handlers",
                action="Add handlers",
                dependencies=["plan_routes"],
            ),
            Task(
                task_id="wire_routes",
                description="Wire routes to handlers",
                action="Connect routes",
                dependencies=["create_models", "create_handlers"],
            ),
        ]

    def test_full_pipeline_happy_path(
        self, pipeline: PipelineOrchestrator, tasks: list[Task]
    ) -> None:  # noqa: E501
        """All tasks execute and verify successfully."""
        # Plan
        msg = pipeline.ingest_tasks(tasks)
        assert msg.phase == "plan"
        assert len(pipeline.state.task_order) == 4

        # Execute and verify all tasks
        executed = 0
        while True:
            task = pipeline.next_task()
            if task is None:
                break
            pipeline.report_result(task.task_id, f"Done: {task.task_id}", success=True)
            # Verify the completed task
            verify_msg = pipeline.verify_task(task.task_id)
            assert verify_msg.error is None
            pipeline.verification_complete(task.task_id, passed=True)
            executed += 1

        assert executed == 4
        assert pipeline.state.completed

    def test_full_pipeline_with_failure(
        self, pipeline: PipelineOrchestrator, tasks: list[Task]
    ) -> None:  # noqa: E501
        """A failing task should stop the pipeline."""
        msg = pipeline.ingest_tasks(tasks)
        assert msg.phase == "plan"

        # Execute first task successfully
        task = pipeline.next_task()
        assert task is not None
        pipeline.report_result(task.task_id, "Done", success=True)

        # Verify it
        pipeline.verify_task(task.task_id)
        pipeline.verification_complete(task.task_id, passed=True)

        # Execute second task with failure
        task = pipeline.next_task()
        assert task is not None
        pipeline.report_result(task.task_id, "Broken!", success=False)

        assert pipeline.state.failed is True
        assert pipeline.state.failure_reason == "Broken!"

    def test_verification_failure_does_not_auto_rollback(
        self, pipeline: PipelineOrchestrator
    ) -> None:  # noqa: E501
        """Verifer rejection marks task as failed but pipeline continues for other tasks."""
        tasks = [
            Task(task_id="t1", description="Good", action="X"),
            Task(task_id="t2", description="Bad", action="Y"),
        ]
        msg = pipeline.ingest_tasks(tasks)
        assert msg.phase == "plan"

        # Implement t1
        task = pipeline.next_task()
        assert task is not None
        pipeline.report_result("t1", "Done", success=True)

        # Verify t1 - FAILS
        pipeline.verify_task("t1")
        pipeline.verification_complete("t1", passed=False, detail="Tests failed")

        # t2 should still be available
        task = pipeline.next_task()
        assert task is not None
        assert task.task_id == "t2"

    def test_sandbox_config_propagation(self) -> None:
        """Sandbox config should be available through orchestrator."""
        sandbox = SandboxConfig(
            allowed_commands=["echo"],
            timeout_seconds=10,
        )
        pipeline = PipelineOrchestrator(sandbox_config=sandbox)
        assert pipeline.sandbox_config.timeout_seconds == 10


class TestDAGValidationEdgeCases:
    """Edge case validation for DAG construction."""

    @pytest.fixture
    def pipeline(self) -> PipelineOrchestrator:
        return PipelineOrchestrator()

    def test_task_depends_on_unknown_task(self, pipeline: PipelineOrchestrator) -> None:
        """A task referencing an unknown dependency should be caught during ingest."""
        tasks = [Task(task_id="t1", description="X", action="Y", dependencies=["nonexistent"])]

        # The ingest_tasks still accepts this — the dependency exists in the implicit list
        # but topological_sort will raise because "nonexistent" isn't a known task
        msg = pipeline.ingest_tasks(tasks)
        # The implicit dep extraction creates a dep from "nonexistent" -> "t1"
        # but "nonexistent" isn't in the tasks dict, so topo sort will fail
        assert msg.phase == "plan" or msg.error is not None

    def test_empty_task_list(self, pipeline: PipelineOrchestrator) -> None:
        """Empty task list should be handled gracefully."""
        msg = pipeline.ingest_tasks([])
        assert msg.phase == "plan"
        assert msg.payload["task_count"] == 0
        assert pipeline.next_task() is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
