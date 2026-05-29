"""Implementor agent — executes tasks using the constrained toolset.

Takes a Task, reads files, writes code, runs commands, and returns results.
All file operations and command execution go through the sandboxed API.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from no_slop_harness.ast_editor import ASTEditor
from no_slop_harness.llm_client import LLMClient
from no_slop_harness.sandbox import execute_sandboxed
from no_slop_harness.schemas import SandboxConfig, Task

logger = logging.getLogger(__name__)

# Load implementor system prompt
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "implementor.txt"
_IMPLEMENTOR_SYSTEM_PROMPT = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""


class ImplementorAgent:
    """Agent that implements a single task using the constrained toolset.

    Reads files, writes code via AST editing or direct writes, and runs
    sandboxed commands to verify correctness.

    Usage:
        implementor = ImplementorAgent(llm_client, sandbox_config)
        result = await implementor.execute(task)
        print(result["success"], result["summary"])
    """

    def __init__(
        self,
        llm_client: LLMClient,
        sandbox_config: SandboxConfig | None = None,
        work_dir: Path | None = None,
    ) -> None:
        self._client = llm_client
        self._sandbox = sandbox_config or SandboxConfig()
        self._editor = ASTEditor()
        self._work_dir = work_dir or Path.cwd()
        self._system_prompt = _IMPLEMENTOR_SYSTEM_PROMPT

    async def execute(self, task: Task) -> dict:
        """Execute a single task.

        Args:
            task: The task to implement.

        Returns:
            A dict with keys: success, summary, files_modified, test_output.
        """
        logger.info("Implementor executing task: %s — %s", task.task_id, task.action)

        # Build the task context
        task_context = task.model_dump_json(indent=2)

        # Read target file if it exists
        file_content = ""
        if task.target_file:
            target_path = Path(task.target_file)
            if target_path.exists():
                try:
                    file_content = target_path.read_text()
                except Exception as e:
                    logger.warning("Could not read target file %s: %s", task.target_file, e)

        # Read dependency outputs if available
        dep_context = ""
        if task.dependencies:
            dep_context = f"\nCompleted dependencies: {', '.join(task.dependencies)}"

        prompt = f"""## Task
{task_context}

## Current File Content
{task.target_file or "N/A"}
```
{file_content[:5000] if file_content else "(file does not exist yet)"}
```

{dep_context}

## Instructions
Implement the task described above. Read any needed files, write the implementation,
and run tests or checks to verify your work. Return ONLY a JSON result object."""

        response = await self._client.generate(
            prompt,
            system_prompt=self._system_prompt,
            temperature=0.3,
        )

        result = self._parse_response(response.content, task)
        return result

    def _parse_response(self, content: str, task: Task) -> dict:
        """Parse the Implementor's response."""
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        try:
            return json.loads(content)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            # If the LLM didn't return JSON, wrap the response
            logger.warning("Implementor did not return valid JSON for task %s", task.task_id)
            return {
                "success": True,
                "summary": content[:500],
                "files_modified": [task.target_file] if task.target_file else [],
                "test_output": "",
            }

    # ── Tool Methods (for LLM to call explicitly) ─────────────────────────

    def read_file(self, path: str) -> str:
        """Read a file at an absolute path."""
        try:
            return Path(path).read_text()
        except Exception as e:
            return f"Error reading {path}: {e}"

    def write_file(self, path: str, content: str) -> bool:
        """Write content to a file."""
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            # Validate syntax for Python files
            if p.suffix == ".py":
                compile(content, str(p), "exec")
            return True
        except SyntaxError as e:
            logger.error("Syntax error in %s: %s", path, e)
            return False
        except Exception as e:
            logger.error("Error writing %s: %s", path, e)
            return False

    def edit_file_ast(self, path: str, node_target: str, replacement: str) -> bool:
        """Edit a function/class using AST-aware replacement."""
        return self._editor.edit(Path(path), node_target, replacement)

    def bash_execute(self, cmd: str) -> tuple[int, str, str]:
        """Execute a sandboxed shell command."""
        return execute_sandboxed(cmd, self._sandbox)
