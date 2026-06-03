"""End-to-end CIV pipeline runner.

Ties together the Coordinator, Implementor, and Verifier agents
with the PipelineOrchestrator to execute a complete user request
from natural language to verified implementation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from no_slop_harness.agents.coordinator import CoordinatorAgent
from no_slop_harness.agents.implementor import ImplementorAgent
from no_slop_harness.agents.verifier import VerifierAgent
from no_slop_harness.llm_client import LLMClient, LLMClientConfig
from no_slop_harness.orchestrator import PipelineOrchestrator
from no_slop_harness.providers.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
)
from no_slop_harness.schemas import SandboxConfig, Task, TaskStatus  # noqa: F401

logger = logging.getLogger(__name__)


class CIVPipeline:
    """Complete CIV pipeline — Coordinator, Implementor, Verifier.

    Usage:
        pipeline = CIVPipeline(
            base_url="http://localhost:1234/v1",
            model="qwen/qwen3.6-35b-a3b",
        )

        result = await pipeline.run(
            "Add a User model with email and password fields, plus a login endpoint"
        )
        print(result["success"], result["summary"])
    """

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model: str = "qwen/qwen3.6-35b-a3b",
        api_key: str = "not-needed",
        sandbox_config: SandboxConfig | None = None,
        work_dir: Path | None = None,
        max_retries: int = 3,
        temperature: float = 0.3,
    ) -> None:
        self._work_dir = work_dir or Path.cwd()

        # Set up the LLM client with a concrete provider
        provider_config = OpenAICompatibleConfig(
            base_url=base_url,
            model=model,
            api_key=api_key,
        )
        provider = OpenAICompatibleProvider(config=provider_config)

        llm_config = LLMClientConfig(
            provider="openai_compatible",
            model=model,
            temperature=temperature,
            max_retries=max_retries,
        )
        self._client = LLMClient(config=llm_config)
        self._client.register_provider("openai_compatible", provider)
        self._provider = provider  # Keep reference for cleanup

        # Set up sandbox
        self._sandbox = sandbox_config or SandboxConfig(
            allowed_commands=["python", "pytest", "ruff", "mypy", "echo", "ls", "cat"],
            timeout_seconds=120,
        )

        # Create agents
        self._coordinator = CoordinatorAgent(self._client)
        self._implementor = ImplementorAgent(
            self._client, sandbox_config=self._sandbox, work_dir=self._work_dir
        )
        self._verifier = VerifierAgent(self._client, work_dir=self._work_dir)

        # Create orchestrator (fresh per run)
        self._orchestrator = PipelineOrchestrator(sandbox_config=self._sandbox)

    async def run(
        self,
        request: str,
        context_files: list[str] | None = None,
        max_verification_retries: int = 3,
    ) -> dict[str, Any]:
        """Execute a full CIV pipeline from user request to verified result.

        Args:
            request: The natural language user request.
            context_files: Optional list of file paths for context.
            max_verification_retries: Max times to retry a failed verification.

        Returns:
            A dict with: success, request_id, tasks_completed, tasks_failed,
            task_results, summary.
        """
        logger.info("CIV Pipeline starting for request: %s", request[:80])

        # Phase 1: Coordinator decomposes the request
        logger.info("Phase 1: Coordinator decomposing request...")
        tasks = await self._coordinator.decompose(request, context_files)
        if not tasks:
            return {
                "success": False,
                "request_id": self._orchestrator.request_id,
                "error": "Coordinator produced no tasks",
            }

        # Phase 2: Orchestrator plans the execution order
        logger.info("Phase 2: Orchestrator planning %d tasks...", len(tasks))
        plan_msg = self._orchestrator.ingest_tasks(tasks)
        if plan_msg.error:
            return {
                "success": False,
                "request_id": self._orchestrator.request_id,
                "error": plan_msg.error,
            }

        # Phase 3: Execute and verify each task
        logger.info("Phase 3: Executing %d tasks...", len(tasks))
        task_results: dict[str, dict] = {}

        while True:
            task = self._orchestrator.next_task()
            if task is None:
                break

            logger.info("--- Task: %s — %s ---", task.task_id, task.action)

            # Implement
            impl_result = await self._implementor.execute(task)
            success = impl_result.get("success", False)
            summary = impl_result.get("summary", "")

            if not success:
                logger.warning("Task %s implementation reported failure: %s", task.task_id, summary)
                self._orchestrator.report_result(task.task_id, summary, success=False)
                task_results[task.task_id] = {
                    "success": False,
                    "phase": "implement",
                    "summary": summary,
                }
                continue

            # Report success to orchestrator
            self._orchestrator.report_result(task.task_id, summary, success=True)

            # Verify with retries
            verified = False
            verification_detail = ""
            for attempt in range(max_verification_retries + 1):
                self._orchestrator.verify_task(task.task_id)

                modified_files = impl_result.get("files_modified", [])
                verdict = await self._verifier.verify(task, modified_files=modified_files)

                if verdict["passed"]:
                    self._orchestrator.verification_complete(
                        task.task_id, passed=True, detail=verdict["detail"]
                    )  # noqa: E501
                    verified = True
                    verification_detail = verdict["detail"]
                    logger.info("Task %s: VERIFIED ✓ (attempt %d)", task.task_id, attempt + 1)
                    break
                else:
                    logger.warning(
                        "Task %s: FAILED verification (attempt %d/%d): %s",
                        task.task_id,
                        attempt + 1,
                        max_verification_retries + 1,
                        verdict["detail"],
                    )
                    verification_detail = verdict["detail"]

                    if attempt < max_verification_retries:
                        # Feed suggestions back to implementor for retry
                        retry_prompt = (
                            f"Your previous implementation failed verification. "
                            f"Issues: {verdict['detail']}\n"
                            f"Suggestions: {verdict.get('suggestions', 'Fix the errors.')}\n"
                            f"Please fix and retry."
                        )
                        # Re-execute with feedback
                        task.description = f"{task.description}\n\nRETRY: {retry_prompt}"
                        impl_result = await self._implementor.execute(task)
                        if not impl_result.get("success", False):
                            break

            if not verified:
                self._orchestrator.verification_complete(
                    task.task_id, passed=False, detail=verification_detail
                )
                task_results[task.task_id] = {
                    "success": False,
                    "phase": "verify",
                    "summary": verification_detail,
                }
            else:
                task_results[task.task_id] = {
                    "success": True,
                    "phase": "done",
                    "summary": summary,
                    "verification": verification_detail,
                }

        # Build final result
        status = self._orchestrator.status()
        return {
            "success": not self._orchestrator.state.failed,
            "request_id": self._orchestrator.request_id,
            "tasks_total": status["total_tasks"],
            "tasks_completed": status["completed"],
            "tasks_failed": status["failed"],
            "task_results": task_results,
            "summary": (
                f"Pipeline complete: {status['completed']}/{status['total_tasks']} tasks passed, "
                f"{status['failed']} failed."
            ),
        }

    async def close(self) -> None:
        """Clean up resources."""
        await self._provider.close()


async def run_pipeline(
    request: str,
    base_url: str = "http://localhost:1234/v1",
    model: str = "qwen/qwen3.6-35b-a3b",
    api_key: str = "not-needed",
    work_dir: str | None = None,
    context_files: list[str] | None = None,
) -> dict[str, Any]:
    """Convenience function to run a full CIV pipeline.

    Args:
        request: The natural language user request.
        base_url: OpenAI-compatible API base URL.
        model: Model name.
        api_key: API key (or "not-needed" for local LM Studio).
        work_dir: Working directory for file operations.
        context_files: Optional list of file paths for context.

    Returns:
        Pipeline result dict.
    """
    wd = Path(work_dir) if work_dir else Path.cwd()
    pipeline = CIVPipeline(
        base_url=base_url,
        model=model,
        api_key=api_key,
        work_dir=wd,
    )
    try:
        return await pipeline.run(request, context_files=context_files)
    finally:
        await pipeline.close()
