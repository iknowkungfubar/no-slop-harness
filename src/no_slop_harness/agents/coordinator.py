"""Coordinator agent — decomposes user requests into Task DAGs.

Uses an LLM to analyze a user's software engineering request and produce
a structured list of atomic tasks with dependency ordering.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from no_slop_harness.llm_client import LLMClient
from no_slop_harness.schemas import Task

logger = logging.getLogger(__name__)

# Load the coordinator system prompt
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "coordinator.txt"
_COORDINATOR_SYSTEM_PROMPT = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""


class CoordinatorAgent:
    """Agent that decomposes user requests into ordered Task lists.

    Usage:
        coordinator = CoordinatorAgent(llm_client)
        tasks = await coordinator.decompose(
            "Add a User model with email/password and a login endpoint"
        )
        # tasks is a list[Task] with dependency ordering
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._client = llm_client
        self._system_prompt = _COORDINATOR_SYSTEM_PROMPT

    async def decompose(self, request: str, context_files: list[str] | None = None) -> list[Task]:
        """Decompose a user request into a DAG of Tasks.

        Args:
            request: The natural language user request.
            context_files: Optional list of file paths for context.

        Returns:
            A list of Task objects with dependency ordering.

        Raises:
            ValueError: If the LLM response cannot be parsed.
        """
        prompt = request
        if context_files:
            prompt += "\n\nRelevant files:\n" + "\n".join(f"- {f}" for f in context_files)

        logger.info("Coordinator decomposing request: %s...", request[:80])

        response = await self._client.generate(
            prompt,
            system_prompt=self._system_prompt,
            temperature=0.2,  # Low temperature for structured decomposition
        )

        tasks = self._parse_response(response.content)
        logger.info("Coordinator produced %d tasks: %s", len(tasks), [t.task_id for t in tasks])
        return tasks

    def _parse_response(self, content: str) -> list[Task]:
        """Parse the LLM response into Task objects with validation.

        Handles both raw JSON arrays and markdown-fenced JSON.
        """
        content = content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        try:
            raw_tasks = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error("Coordinator produced invalid JSON: %s", e)
            logger.debug("Raw response: %s", content[:500])
            raise ValueError(f"Coordinator produced invalid JSON: {e}") from e

        if not isinstance(raw_tasks, list):
            raise ValueError(f"Coordinator output is not a list: {type(raw_tasks)}")

        tasks: list[Task] = []
        for i, raw in enumerate(raw_tasks):
            try:
                task = Task.model_validate(raw)
                tasks.append(task)
            except Exception as e:
                logger.warning("Task %d failed validation: %s — raw: %s", i, e, raw)
                # Attempt to fix common issues
                if "task_id" not in raw:
                    raw["task_id"] = f"task_{i}"
                if "description" not in raw:
                    raw["description"] = str(raw.get("action", f"Task {i}"))
                if "action" not in raw:
                    raw["action"] = raw.get("description", f"Execute task_{i}")
                try:
                    task = Task.model_validate(raw)
                    tasks.append(task)
                    logger.info("Auto-fixed task %d: %s", i, task.task_id)
                except Exception:
                    logger.error("Could not fix task %d, skipping", i)

        return tasks
