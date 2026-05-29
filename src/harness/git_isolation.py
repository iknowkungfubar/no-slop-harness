"""Git worktree isolation for task execution."""

from __future__ import annotations

import subprocess
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator


@dataclass
class Worktree:
    """Handle to an active git worktree."""

    path: Path
    branch: str
    base_branch: str

    def __repr__(self) -> str:
        return f"Worktree(branch={self.branch!r}, path={self.path})"


class WorktreeManager:
    """Creates and manages isolated git worktrees per task."""

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).resolve()
        self._active: list[Worktree] = []

    # -- helpers -------------------------------------------------------------

    def _git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        )

    def current_branch(self) -> str:
        result = self._git("rev-parse", "--abbrev-ref", "HEAD")
        return result.stdout.strip()

    # -- lifecycle -----------------------------------------------------------

    @contextmanager
    def isolated(self, task_id: str | None = None) -> Generator[Worktree, None, None]:
        """Context manager: create a worktree, yield it, clean up on exit."""
        task_id = task_id or uuid.uuid4().hex[:8]
        branch = f"task/{task_id}"
        wt_dir = self.repo_path.parent / ".worktrees" / task_id

        base = self.current_branch()
        wt_dir.parent.mkdir(parents=True, exist_ok=True)
        self._git("worktree", "add", "-b", branch, str(wt_dir))

        wt = Worktree(path=wt_dir, branch=branch, base_branch=base)
        self._active.append(wt)
        try:
            yield wt
        finally:
            self._remove(wt)

    # -- operations ----------------------------------------------------------

    def commit(self, wt: Worktree, message: str) -> str | None:
        """Stage all and commit. Returns SHA or ``None`` if tree is clean."""
        self._git("add", "-A", cwd=wt.path)
        try:
            self._git("diff", "--cached", "--quiet", cwd=wt.path)
            return None  # nothing staged
        except subprocess.CalledProcessError:
            pass  # staged changes exist
        self._git("commit", "-m", message, cwd=wt.path)
        result = self._git("rev-parse", "HEAD", cwd=wt.path)
        return result.stdout.strip()

    def diff_from_base(self, wt: Worktree) -> str:
        """Return the diff between base branch and worktree branch."""
        try:
            result = self._git("diff", f"{wt.base_branch}...{wt.branch}", cwd=wt.path)
            return result.stdout
        except subprocess.CalledProcessError:
            return ""

    def merge_to_base(self, wt: Worktree) -> bool:
        """Merge worktree branch into base without checking out."""
        try:
            self._git(
                "fetch", ".", f"{wt.branch}:{wt.base_branch}",
            )
            return True
        except subprocess.CalledProcessError:
            pass
        # Fallback: fast-forward failed, attempt a merge commit
        try:
            self._git("checkout", wt.base_branch)
            self._git("merge", "--no-ff", wt.branch, "-m", f"Merge {wt.branch}")
            return True
        except subprocess.CalledProcessError:
            try:
                self._git("merge", "--abort")
            except subprocess.CalledProcessError:
                pass
            return False

    # -- cleanup -------------------------------------------------------------

    def _remove(self, wt: Worktree) -> None:
        if wt.path.exists():
            try:
                self._git("worktree", "remove", "--force", str(wt.path))
            except subprocess.CalledProcessError:
                pass
        try:
            self._git("branch", "-D", wt.branch)
        except subprocess.CalledProcessError:
            pass
        if wt in self._active:
            self._active.remove(wt)

    def cleanup(self) -> None:
        """Remove all managed worktrees."""
        for wt in list(self._active):
            self._remove(wt)
