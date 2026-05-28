"""Git worktree isolation for safe Implementor task execution.

Creates isolated git worktrees per task, so the Implementor can
make changes without affecting the main working tree. After
verification passes, changes are merged back automatically.

Workflow:
    1. Create a new branch from HEAD
    2. Create a detached worktree for the branch
    3. Implementor works in the isolated worktree
    4. Verifier checks the changes
    5. On PASS: merge branch back to main, delete worktree
    6. On FAIL: delete branch and worktree, no merge
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class WorktreeIsolation:
    """Manages an isolated git worktree for a single task.

    Usage:
        iso = WorktreeIsolation("/path/to/repo")
        ctx = await iso.isolate("task_add_model")
        # ... implementor works in ctx.worktree_path ...
        if verified:
            await iso.merge(ctx)
        else:
            await iso.abort(ctx)
    """

    repo_path: Path
    worktrees_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.worktrees_dir is None:
            self.worktrees_dir = self.repo_path / ".no-slop" / "worktrees"

    async def isolate(self, task_id: str) -> IsolatedContext:
        """Create an isolated worktree for a task.

        Args:
            task_id: The task identifier (used for branch/worktree naming).

        Returns:
            An IsolatedContext describing the isolated environment.

        Raises:
            RuntimeError: If git operations fail.
        """
        branch_name = f"no-slop/{task_id}-{uuid4().hex[:8]}"
        worktree_path = self.worktrees_dir / task_id  # type: ignore[union-attr]

        # Clean up any previous worktree with this name
        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

        self.worktrees_dir.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]

        logger.info("Creating isolated worktree for task %s: branch=%s", task_id, branch_name)

        try:
            # Create branch from current HEAD
            _git(self.repo_path, "branch", branch_name)

            # Create worktree on that branch
            _git(self.repo_path, "worktree", "add", str(worktree_path), branch_name)
        except subprocess.CalledProcessError as e:
            _cleanup_branch(self.repo_path, branch_name)
            raise RuntimeError(f"Failed to create isolated worktree: {e.stderr}") from e

        return IsolatedContext(
            task_id=task_id,
            branch_name=branch_name,
            worktree_path=worktree_path,
            repo_path=self.repo_path,
        )

    async def merge(self, ctx: IsolatedContext) -> bool:
        """Merge the isolated branch back into the main branch.

        Args:
            ctx: The isolation context from isolate().

        Returns:
            True if merge succeeded.
        """
        logger.info("Merging task %s branch %s back to main", ctx.task_id, ctx.branch_name)

        try:
            # Remove worktree first
            _git(self.repo_path, "worktree", "remove", str(ctx.worktree_path), "--force")

            # Checkout main/master and merge
            try:
                _git(self.repo_path, "checkout", "main")
            except subprocess.CalledProcessError:
                _git(self.repo_path, "checkout", "master")
            _git(self.repo_path, "merge", ctx.branch_name, "--no-ff", "-m",
                 f"feat: implement {ctx.task_id} [no-slop]")

            # Delete the feature branch
            _git(self.repo_path, "branch", "-d", ctx.branch_name)

            # Clean up worktree directory if still present
            if ctx.worktree_path.exists():
                shutil.rmtree(ctx.worktree_path, ignore_errors=True)

            logger.info("Merge successful for task %s", ctx.task_id)
            return True

        except subprocess.CalledProcessError as e:
            logger.error("Merge failed for task %s: %s", ctx.task_id, e.stderr)
            # Attempt abort — remove worktree, delete branch, reset
            await self.abort(ctx)
            return False

    async def abort(self, ctx: IsolatedContext) -> None:
        """Abort the isolated task — delete worktree and branch, no merge.

        Args:
            ctx: The isolation context from isolate().
        """
        logger.info("Aborting task %s — discarding changes", ctx.task_id)

        try:
            _git(self.repo_path, "worktree", "remove", str(ctx.worktree_path), "--force")
        except subprocess.CalledProcessError:
            pass  # Worktree may already be gone

        _cleanup_branch(self.repo_path, ctx.branch_name)

        if ctx.worktree_path.exists():
            shutil.rmtree(ctx.worktree_path, ignore_errors=True)

    def list_active(self) -> list[str]:
        """List active isolated worktree task IDs."""
        if not self.worktrees_dir.exists():  # type: ignore[union-attr]
            return []
        return [d.name for d in self.worktrees_dir.iterdir() if d.is_dir()]  # type: ignore[union-attr]


@dataclass
class IsolatedContext:
    """Context for an isolated task worktree."""

    task_id: str
    branch_name: str
    worktree_path: Path
    repo_path: Path

    @property
    def cwd(self) -> Path:
        """The working directory for the Implementor."""
        return self.worktree_path


def _git(repo_path: Path, *args: str) -> str:
    """Run a git command in the repo and return stdout."""
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo_path), *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _cleanup_branch(repo_path: Path, branch_name: str) -> None:
    """Force-delete a branch if it exists."""
    try:
        _git(repo_path, "branch", "-D", branch_name)
    except subprocess.CalledProcessError:
        pass  # Branch already deleted or never existed
