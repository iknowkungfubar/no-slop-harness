"""Verifier agent — validates implemented tasks.

Runs the test suite, linter, and type checker on modified files,
then produces a structured verdict with actionable feedback.
"""

from __future__ import annotations

import logging
from pathlib import Path

from no_slop_harness.llm_client import LLMClient
from no_slop_harness.schemas import Task
from no_slop_harness.verifier import Verifier

logger = logging.getLogger(__name__)

# Load verifier system prompt
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "verifier.txt"
_VERIFIER_SYSTEM_PROMPT = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""


class VerifierAgent:
    """Agent that verifies implemented tasks via automated checks.

    Runs pytest, ruff, mypy, and syntax validation on the modified
    files, then optionally uses an LLM to interpret results and
    produce actionable feedback.

    Usage:
        verifier = VerifierAgent(llm_client)
        verdict = await verifier.verify(task, modified_files=["/path/to/file.py"])
        print(verdict["passed"], verdict["detail"])
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        work_dir: Path | None = None,
    ) -> None:
        self._client = llm_client
        self._verifier = Verifier(working_dir=work_dir)
        self._work_dir = work_dir or Path.cwd()
        self._system_prompt = _VERIFIER_SYSTEM_PROMPT

    async def verify(
        self,
        task: Task,
        modified_files: list[str] | None = None,
    ) -> dict:
        """Verify a completed task.

        Args:
            task: The task that was implemented.
            modified_files: List of files modified by the Implementor.

        Returns:
            A dict with: passed, detail, test_output, lint_output,
            typecheck_output, suggestions.
        """
        logger.info("Verifier checking task: %s", task.task_id)

        files = modified_files or ([task.target_file] if task.target_file else [])

        results: dict = {
            "passed": True,
            "detail": "",
            "test_output": "",
            "lint_output": "",
            "typecheck_output": "",
            "suggestions": "",
        }

        # 1. Run tests for modified test files (not the full suite)
        test_files = [f for f in files if Path(f).name.startswith("test_")]
        if test_files:
            for tf in test_files:
                tf_path = Path(tf)
                if tf_path.exists():
                    test_result = self._verifier.run_pytest(test_path=tf)
                    if test_result.output:
                        results["test_output"] += test_result.output + "\n"
                    if not test_result.passed:
                        results["passed"] = False
                        results["detail"] += f"Tests failed in {tf}. "

        # 2. Run linter
        lint_result = self._verifier.run_lint()
        results["lint_output"] = lint_result.output
        if not lint_result.passed:
            results["passed"] = False
            results["detail"] += "Lint errors found. "

        # 3. Run type checker
        type_result = self._verifier.run_typecheck()
        results["typecheck_output"] = type_result.output
        if not type_result.passed:
            results["passed"] = False
            results["detail"] += "Type errors found. "

        # 4. Syntax validate modified files
        for f in files:
            try:
                content = Path(f).read_text()
                compile(content, f, "exec")
            except SyntaxError as e:
                results["passed"] = False
                results["detail"] += f"Syntax error in {f}: {e}. "
            except FileNotFoundError:
                pass  # File doesn't exist yet — not an error

        if results["passed"]:
            results["detail"] = "All checks passed."
        else:
            results["detail"] = results["detail"].strip()
            # Optionally use LLM to generate suggestions
            if self._client and results["detail"]:
                results["suggestions"] = await self._generate_suggestions(task, results)

        logger.info(
            "Verifier result for %s: %s",
            task.task_id,
            "PASS" if results["passed"] else "FAIL",
        )
        return results

    async def _generate_suggestions(self, task: Task, results: dict) -> str:
        """Use the LLM to generate actionable fix suggestions."""
        if not self._client:
            return "Fix the errors reported above."

        prompt = f"""Task: {task.description}
Test output: {results["test_output"][:2000]}
Lint output: {results["lint_output"][:2000]}
Type check output: {results["typecheck_output"][:2000]}

Provide specific, actionable suggestions for fixing these issues.
Reference exact file:line locations. Be concise."""

        try:
            response = await self._client.generate(
                prompt,
                system_prompt=self._system_prompt,
                temperature=0.3,
            )
            return response.content.strip()
        except Exception as e:
            logger.warning("Failed to generate suggestions: %s", e)
            return "Fix the errors reported above."
