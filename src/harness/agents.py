"""CIV agent definitions: Coordinator, Implementor, Verifier."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from .schemas import (
    AgentAction,
    Task,
    TaskPlan,
    VerificationResult,
)
from .tools import TOOL_ARGS_MAP, TOOL_REGISTRY

if TYPE_CHECKING:
    from .client import InferenceClient
    from .executor import ToolExecutor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompts (< 1 000 tokens each per README spec)
# ---------------------------------------------------------------------------

_COORDINATOR_SYSTEM = (
    "You are the Coordinator. Decompose the user request into a dependency-ordered "
    "JSON execution plan. Each task has: id, description, dependencies (list of task "
    "ids), assigned_agent ('implementor' or 'verifier'), and tool_hints. "
    "Output only valid JSON matching the TaskPlan schema. Zero conversational filler."
)

_IMPLEMENTOR_SYSTEM = (
    "You are the Implementor. Execute the task using tool calls. "
    'Respond with JSON: {"action":"call_tool","tool_call":{"name":...,"arguments":{...}}} '
    'or {"action":"finish","summary":"..."}. '
    "Tools: read_file(path), write_file(path,content), "
    "edit_file_ast(path,node_target,replacement), bash_execute(cmd). "
    "Respond only with JSON."
)

_VERIFIER_SYSTEM = (
    "You are the Verifier. Assess the diff and execution log. "
    'Output JSON: {"passed":bool,"failures":[...],"suggestions":[...]}. '
    "If tests fail, include the exact failure trace. Reject incomplete work."
)


# ---------------------------------------------------------------------------
# Agent classes
# ---------------------------------------------------------------------------


class Coordinator:
    """Decomposes user prompts into a task DAG."""

    def __init__(self, client: InferenceClient):
        self.client = client

    def plan(self, prompt: str, context: str = "") -> TaskPlan:
        messages = [
            {"role": "system", "content": _COORDINATOR_SYSTEM},
            {"role": "user", "content": f"Context:\n{context}\n\nRequest:\n{prompt}"},
        ]
        return self.client.generate_structured(messages=messages, schema=TaskPlan)


class Implementor:
    """Executes a single task via iterative tool calls."""

    MAX_STEPS = 20

    def __init__(self, client: InferenceClient, executor: ToolExecutor | None = None):
        self.client = client
        self.executor = executor

    def execute(self, task: Task, context: str = "") -> list[dict]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": _IMPLEMENTOR_SYSTEM},
            {"role": "user", "content": f"Task: {task.description}\nContext:\n{context}"},
        ]

        log: list[dict] = []
        for step in range(self.MAX_STEPS):
            action = self.client.generate_structured(messages=messages, schema=AgentAction)

            if action.action == "finish":
                log.append({"action": "finish", "summary": action.summary})
                break

            if action.tool_call is None:
                break

            tc = action.tool_call

            if self.executor is not None:
                try:
                    result = self.executor.execute(tc.name, tc.arguments)
                except Exception as e:
                    result = self.executor.make_error_result(tc.name, str(e))
                    log.append({"tool": tc.name, "arguments": tc.arguments, "error": str(e)})
                    messages.append({"role": "assistant", "content": action.model_dump_json()})
                    messages.append({"role": "user", "content": f"Error: {e}"})
                    continue
            else:
                args_cls = TOOL_ARGS_MAP.get(tc.name)
                handler = TOOL_REGISTRY.get(tc.name)
                if not args_cls or not handler:
                    log.append({"error": f"Unknown tool: {tc.name}"})
                    break
                parsed_args = args_cls(**tc.arguments)
                result = handler(parsed_args)

            entry = {
                "tool": tc.name,
                "arguments": tc.arguments,
                "result": result.model_dump(),
            }
            log.append(entry)
            logger.debug("Step %d: %s -> %s", step, tc.name, result.model_dump())

            messages.append({"role": "assistant", "content": action.model_dump_json()})
            messages.append({"role": "user", "content": f"Result: {result.model_dump_json()}"})

        return log


class Verifier:
    """Structural gate: validates implementation output."""

    def __init__(self, client: InferenceClient):
        self.client = client

    def verify(
        self, task: Task, execution_log: list[dict], diff: str = ""
    ) -> VerificationResult:
        messages = [
            {"role": "system", "content": _VERIFIER_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Task: {task.description}\n"
                    f"Execution log:\n{json.dumps(execution_log, indent=2)}\n"
                    f"Diff:\n{diff}"
                ),
            },
        ]
        return self.client.generate_structured(messages=messages, schema=VerificationResult)
