"""Tests for the git worktree isolation layer."""

from __future__ import annotations

from pathlib import Path

from harness.git_isolation import WorktreeManager


class TestWorktreeManager:
    def test_isolated_creates_and_cleans_worktree(self, git_repo: Path):
        mgr = WorktreeManager(git_repo)
        with mgr.isolated("test-task") as wt:
            assert wt.path.exists()
            assert wt.branch == "task/test-task"
            (wt.path / "new_file.py").write_text("x = 1\n")
        assert not wt.path.exists()

    def test_commit_returns_sha(self, git_repo: Path):
        mgr = WorktreeManager(git_repo)
        with mgr.isolated("commit-test") as wt:
            (wt.path / "file.txt").write_text("data")
            sha = mgr.commit(wt, "Add file")
            assert sha is not None
            assert len(sha) == 40

    def test_commit_no_changes_returns_none(self, git_repo: Path):
        mgr = WorktreeManager(git_repo)
        with mgr.isolated("empty-test") as wt:
            sha = mgr.commit(wt, "No changes")
            assert sha is None

    def test_diff_from_base(self, git_repo: Path):
        mgr = WorktreeManager(git_repo)
        with mgr.isolated("diff-test") as wt:
            (wt.path / "new.txt").write_text("content\n")
            mgr.commit(wt, "Add new.txt")
            diff = mgr.diff_from_base(wt)
            assert "new.txt" in diff

    def test_cleanup(self, git_repo: Path):
        mgr = WorktreeManager(git_repo)
        with mgr.isolated("cleanup-test") as wt:
            (wt.path / "x.txt").write_text("y")
        assert not wt.path.exists()
        mgr.cleanup()
