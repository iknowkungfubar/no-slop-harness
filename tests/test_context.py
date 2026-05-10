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
