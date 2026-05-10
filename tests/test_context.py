"""Tests for context management."""

from __future__ import annotations

from pathlib import Path

from harness.context import ContextManager


class TestContextManager:
    def test_load_empty(self, tmp_path: Path):
        cm = ContextManager(tmp_path)
        assert cm.load() == ""

    def test_load_md_files(self, tmp_path: Path):
        sdlc = tmp_path / ".sdlc" / "context"
        sdlc.mkdir(parents=True)
        (sdlc / "alpha.md").write_text("Alpha content")
        (sdlc / "beta.md").write_text("Beta content")
        cm = ContextManager(tmp_path)
        ctx = cm.load()
        assert "## alpha" in ctx
        assert "Alpha content" in ctx
        assert "## beta" in ctx
        assert "Beta content" in ctx

    def test_save_task_summary(self, tmp_path: Path):
        cm = ContextManager(tmp_path)
        path = cm.save_task_summary("t1", "Do something", "completed", "log line")
        assert path.exists()
        content = path.read_text()
        assert "t1" in content
        assert "completed" in content
        assert "log line" in content

    def test_save_json(self, tmp_path: Path):
        cm = ContextManager(tmp_path)
        path = cm.save_json("state", {"key": "value"})
        assert path.exists()
        assert '"key"' in path.read_text()

    def test_load_json(self, tmp_path: Path):
        cm = ContextManager(tmp_path)
        cm.save_json("state", {"key": "value"})
        items = cm.load_json()
        assert len(items) == 1
        assert items[0]["key"] == "value"

    def test_list_entries(self, tmp_path: Path):
        cm = ContextManager(tmp_path)
        cm.save_task_summary("t1", "desc", "done")
        cm.save_json("info", {"a": 1})
        entries = cm.list_entries()
        assert "task_t1.md" in entries
        assert "info.json" in entries

    def test_gitkeep_excluded(self, tmp_path: Path):
        cm = ContextManager(tmp_path)
        (cm.context_dir / ".gitkeep").touch()
        assert ".gitkeep" not in cm.list_entries()

    def test_sanitize_task_id(self, tmp_path: Path):
        cm = ContextManager(tmp_path)
        path = cm.save_task_summary("../../etc/passwd", "evil", "failed")
        assert ".." not in path.name
        assert "/" not in path.name
        assert path.parent == cm.context_dir

    def test_sanitize_json_name(self, tmp_path: Path):
        cm = ContextManager(tmp_path)
        path = cm.save_json("../../../etc/shadow", {"x": 1})
        assert ".." not in path.name
        assert path.parent == cm.context_dir

    def test_deep_traversal_task_id(self, tmp_path: Path):
        """Deep ../ segments must not escape context_dir."""
        cm = ContextManager(tmp_path)
        path = cm.save_task_summary(
            "../../../../../../../../tmp/evil", "deep escape", "failed"
        )
        resolved = path.resolve()
        assert resolved.parent == cm.context_dir.resolve()
        assert ".." not in str(resolved)

    def test_deep_traversal_json_name(self, tmp_path: Path):
        """Deep ../ segments in JSON name must not escape context_dir."""
        cm = ContextManager(tmp_path)
        path = cm.save_json("../../../../../../../../tmp/evil", {"x": 1})
        resolved = path.resolve()
        assert resolved.parent == cm.context_dir.resolve()
        assert ".." not in str(resolved)

    def test_safe_path_rejects_escape(self, tmp_path: Path):
        """_safe_path raises ValueError if filename somehow escapes."""
        cm = ContextManager(tmp_path)
        import pytest

        with pytest.raises(ValueError, match="escapes context directory"):
            cm._safe_path("../../escape.md")
