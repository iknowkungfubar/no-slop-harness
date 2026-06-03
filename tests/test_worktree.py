"""Test suite for git worktree isolation."""

from __future__ import annotations

import subprocess

import pytest

from no_slop_harness.worktree import WorktreeIsolation


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)  # noqa: S603, S607
    subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), "config", "user.email", "test@test.com"],  # noqa: S607
        check=True,
        capture_output=True,
    )  # noqa: E501, S603, S607
    subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
        capture_output=True,  # noqa: S607
    )  # noqa: E501, S603, S607
    (repo / "README.md").write_text("# Test Repo\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)  # noqa: S603, S607
    subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), "commit", "-m", "initial"],
        check=True,
        capture_output=True,  # noqa: S607
    )  # noqa: E501, S603, S607
    return repo


class TestWorktreeIsolation:
    """Git worktree creation and lifecycle."""

    def test_isolate_creates_worktree(self, git_repo) -> None:
        import asyncio

        iso = WorktreeIsolation(git_repo)
        ctx = asyncio.run(iso.isolate("test_task"))

        assert ctx.worktree_path.exists()
        assert ctx.branch_name.startswith("no-slop/test_task-")
        assert ctx.cwd == ctx.worktree_path

        # Clean up
        asyncio.run(iso.abort(ctx))

    def test_isolate_creates_unique_branches(self, git_repo) -> None:
        import asyncio

        iso = WorktreeIsolation(git_repo)
        ctx1 = asyncio.run(iso.isolate("task_a"))
        ctx2 = asyncio.run(iso.isolate("task_b"))

        assert ctx1.branch_name != ctx2.branch_name

        asyncio.run(iso.abort(ctx1))
        asyncio.run(iso.abort(ctx2))

    def test_merge_after_changes(self, git_repo) -> None:
        import asyncio

        iso = WorktreeIsolation(git_repo)
        ctx = asyncio.run(iso.isolate("merge_test"))

        # Make a change in the worktree
        (ctx.worktree_path / "new_file.txt").write_text("hello")
        subprocess.run(  # noqa: S603
            ["git", "-C", str(ctx.worktree_path), "add", "."],
            check=True,
            capture_output=True,  # noqa: S607
        )  # noqa: E501, S603, S607
        subprocess.run(  # noqa: S603
            ["git", "-C", str(ctx.worktree_path), "commit", "-m", "feat: add file"],  # noqa: S607
            check=True,
            capture_output=True,
        )  # noqa: E501, S603, S607

        # Merge back
        result = asyncio.run(iso.merge(ctx))
        assert result is True
        assert (git_repo / "new_file.txt").exists()
        assert (git_repo / "new_file.txt").read_text() == "hello"

    def test_abort_discards_changes(self, git_repo) -> None:
        import asyncio

        iso = WorktreeIsolation(git_repo)
        ctx = asyncio.run(iso.isolate("abort_test"))

        (ctx.worktree_path / "junk.txt").write_text("should be discarded")
        subprocess.run(  # noqa: S603
            ["git", "-C", str(ctx.worktree_path), "add", "."],
            check=True,
            capture_output=True,  # noqa: S607
        )  # noqa: E501, S603, S607
        subprocess.run(  # noqa: S603
            ["git", "-C", str(ctx.worktree_path), "commit", "-m", "junk"],  # noqa: S607
            check=True,
            capture_output=True,
        )  # noqa: E501, S603, S607

        asyncio.run(iso.abort(ctx))
        assert not ctx.worktree_path.exists()
        assert not (git_repo / "junk.txt").exists()

    def test_list_active(self, git_repo) -> None:
        import asyncio

        iso = WorktreeIsolation(git_repo)
        ctx = asyncio.run(iso.isolate("active_test"))

        active = iso.list_active()
        assert "active_test" in active

        asyncio.run(iso.abort(ctx))
        assert "active_test" not in iso.list_active()

    def test_isolated_context_attributes(self, git_repo) -> None:
        import asyncio

        iso = WorktreeIsolation(git_repo)
        ctx = asyncio.run(iso.isolate("ctx_test"))

        assert ctx.task_id == "ctx_test"
        assert ctx.repo_path == git_repo
        assert isinstance(ctx.branch_name, str)
        assert ctx.cwd == ctx.worktree_path

        asyncio.run(iso.abort(ctx))
