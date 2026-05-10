"""Persistent agent memory via .sdlc/context/."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


class ContextManager:
    """Reads and writes persistent context from ``.sdlc/context/``."""

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root).resolve()
        self.context_dir = self.repo_root / ".sdlc" / "context"
        self.context_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> str:
        """Concatenate all ``.md`` files in context dir into a single string."""
        parts: list[str] = []
        for f in sorted(self.context_dir.glob("*.md")):
            parts.append(f"## {f.stem}\n{f.read_text(encoding='utf-8').strip()}")
        return "\n\n".join(parts)

    def load_json(self) -> list[dict]:
        """Load all ``.json`` context files as a list of dicts."""
        items: list[dict] = []
        for f in sorted(self.context_dir.glob("*.json")):
            items.append(json.loads(f.read_text(encoding="utf-8")))
        return items

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Strip path-traversal characters from a context entry name."""
        return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)

    def _safe_path(self, filename: str) -> Path:
        """Build a path inside context_dir and verify it cannot escape.

        Uses strict parent equality (not ``is_relative_to``) so only flat
        filenames are accepted.  If subdirectory support is ever needed,
        switch to ``path.is_relative_to(self.context_dir.resolve())``.
        """
        path = (self.context_dir / filename).resolve()
        if not path.parent == self.context_dir.resolve():
            raise ValueError(
                f"Path escapes context directory: {filename!r}"
            )
        return path

    def save_task_summary(
        self, task_id: str, description: str, status: str, log_excerpt: str = ""
    ) -> Path:
        """Write a task execution summary to context dir."""
        task_id = self._sanitize_name(task_id)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        content = (
            f"# Task: {task_id}\n\n"
            f"- **Status:** {status}\n"
            f"- **Timestamp:** {ts}\n"
            f"- **Description:** {description}\n"
        )
        if log_excerpt:
            content += f"\n## Execution Log Excerpt\n```\n{log_excerpt}\n```\n"

        path = self._safe_path(f"task_{task_id}.md")
        path.write_text(content, encoding="utf-8")
        return path

    def save_json(self, name: str, data: dict) -> Path:
        """Write a JSON context file."""
        name = self._sanitize_name(name)
        path = self._safe_path(f"{name}.json")
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def list_entries(self) -> list[str]:
        """List all context entry filenames."""
        return sorted(
            f.name for f in self.context_dir.iterdir() if f.is_file() and f.name != ".gitkeep"
        )
