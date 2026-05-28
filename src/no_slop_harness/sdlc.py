""".sdlc/ context injection system.

Loads structured project context from a .sdlc/ directory and injects
it into agent prompts. Supports Architecture Decision Records (ADRs),
coding standards, project conventions, and persistent memory.

Directory structure:
    .sdlc/
    ├── adr/           # Architecture Decision Records (markdown)
    │   ├── 001-use-civ-pattern.md
    │   └── 002-sandbox-all-commands.md
    ├── standards/     # Coding standards and conventions
    │   ├── python.md
    │   └── testing.md
    ├── patterns/      # Code patterns and examples
    │   └── model-template.py
    ├── memory/        # Persistent agent memory (key-value)
    │   └── memory.json
    └── config.yaml    # Context injection configuration
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml as _yaml

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False
    _yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass
class SDLCContext:
    """Loaded .sdlc/ context ready for prompt injection."""

    adrs: list[dict[str, str]] = field(default_factory=list)
    standards: list[dict[str, str]] = field(default_factory=list)
    patterns: list[dict[str, str]] = field(default_factory=list)
    memory: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)

    def to_prompt_text(self, max_chars: int = 4000) -> str:
        """Render context as text suitable for injection into a prompt.

        Args:
            max_chars: Maximum characters to include (truncates oldest ADRs first).

        Returns:
            Formatted context string.
        """
        sections: list[str] = []

        if self.adrs:
            adr_text = "## Architecture Decisions\n\n"
            for adr in self.adrs[-5:]:  # Most recent 5 ADRs
                adr_text += f"### {adr.get('title', 'ADR')}\n{adr.get('content', '')}\n\n"
            sections.append(adr_text)

        if self.standards:
            std_text = "## Coding Standards\n\n"
            for std in self.standards:
                std_text += f"### {std.get('title', 'Standard')}\n{std.get('content', '')}\n\n"
            sections.append(std_text)

        if self.patterns:
            pat_text = "## Code Patterns\n\n"
            for pat in self.patterns[:3]:  # Max 3 patterns
                pat_text += (
                    f"### {pat.get('title', 'Pattern')}\n```\n{pat.get('content', '')}\n```\n\n"  # noqa: E501
                )
            sections.append(pat_text)

        combined = "\n\n".join(sections)
        if len(combined) > max_chars:
            # Truncate the oldest ADRs first
            combined = combined[-max_chars:]
            combined = "...(truncated)\n\n" + combined[combined.find("\n##", 10) :]

        return combined.strip()


class SDLCLoader:
    """Loads structured project context from a .sdlc/ directory.

    Usage:
        loader = SDLCLoader("/path/to/project")
        context = loader.load()
        prompt += context.to_prompt_text()
    """

    def __init__(self, project_root: Path | str) -> None:
        self._root = Path(project_root)
        self._sdlc_dir = self._root / ".sdlc"

    @property
    def exists(self) -> bool:
        """Whether the .sdlc/ directory exists."""
        return self._sdlc_dir.is_dir()

    def load(self) -> SDLCContext:
        """Load all .sdlc/ context.

        Returns:
            SDLCContext with all loaded data.
        """
        context = SDLCContext()

        if not self.exists:
            logger.debug("No .sdlc/ directory found at %s", self._sdlc_dir)
            return context

        # Load ADRs
        adr_dir = self._sdlc_dir / "adr"
        if adr_dir.is_dir():
            for adr_file in sorted(adr_dir.glob("*.md")):
                try:
                    content = adr_file.read_text()
                    title = (
                        content.split("\n")[0].lstrip("# ").strip() if content else adr_file.stem
                    )  # noqa: E501
                    context.adrs.append(
                        {
                            "title": title,
                            "content": content,
                            "file": str(adr_file.name),
                        }
                    )
                except Exception as e:
                    logger.warning("Failed to load ADR %s: %s", adr_file, e)

        # Load standards
        std_dir = self._sdlc_dir / "standards"
        if std_dir.is_dir():
            for std_file in sorted(std_dir.glob("*.md")):
                try:
                    content = std_file.read_text()
                    title = (
                        content.split("\n")[0].lstrip("# ").strip() if content else std_file.stem
                    )  # noqa: E501
                    context.standards.append(
                        {
                            "title": title,
                            "content": content,
                            "file": str(std_file.name),
                        }
                    )
                except Exception as e:
                    logger.warning("Failed to load standard %s: %s", std_file, e)

        # Load patterns
        pat_dir = self._sdlc_dir / "patterns"
        if pat_dir.is_dir():
            for pat_file in sorted(pat_dir.glob("*")):
                if pat_file.suffix in (".py", ".ts", ".go", ".rs", ".js", ".md"):
                    try:
                        content = pat_file.read_text()
                        context.patterns.append(
                            {
                                "title": pat_file.stem.replace("-", " ").replace("_", " ").title(),
                                "content": content,
                                "file": str(pat_file.name),
                            }
                        )
                    except Exception as e:
                        logger.warning("Failed to load pattern %s: %s", pat_file, e)

        # Load persistent memory
        memory_file = self._sdlc_dir / "memory" / "memory.json"
        if memory_file.is_file():
            try:
                context.memory = json.loads(memory_file.read_text())
            except Exception as e:
                logger.warning("Failed to load memory: %s", e)

        # Load config
        config_file = self._sdlc_dir / "config.yaml"
        if config_file.is_file():
            try:
                raw = config_file.read_text()
                if _HAS_YAML:
                    context.config = _yaml.safe_load(raw) or {}
                else:
                    context.config = json.loads(raw) if raw.strip().startswith("{") else {}
            except Exception as e:
                logger.warning("Failed to load config: %s", e)

        logger.info(
            "Loaded .sdlc/ context: %d ADRs, %d standards, %d patterns, %d memory keys",
            len(context.adrs),
            len(context.standards),
            len(context.patterns),
            len(context.memory),
        )
        return context

    def save_memory(self, key: str, value: Any) -> None:
        """Save a key-value pair to persistent memory.

        Args:
            key: Memory key.
            value: Memory value (must be JSON-serializable).
        """
        memory_dir = self._sdlc_dir / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        memory_file = memory_dir / "memory.json"
        memory: dict[str, Any] = {}
        if memory_file.is_file():
            try:
                memory = json.loads(memory_file.read_text())
            except json.JSONDecodeError:
                pass

        memory[key] = value
        memory_file.write_text(json.dumps(memory, indent=2))

    def init_sdlc(self) -> Path:
        """Initialize a .sdlc/ directory with skeleton structure.

        Returns:
            Path to the created .sdlc/ directory.
        """
        self._sdlc_dir.mkdir(parents=True, exist_ok=True)
        (self._sdlc_dir / "adr").mkdir(exist_ok=True)
        (self._sdlc_dir / "standards").mkdir(exist_ok=True)
        (self._sdlc_dir / "patterns").mkdir(exist_ok=True)
        (self._sdlc_dir / "memory").mkdir(exist_ok=True)

        # Write skeleton config
        config = {
            "max_context_chars": 4000,
            "max_adrs": 5,
            "max_patterns": 3,
            "inject_into": ["coordinator", "implementor"],
        }
        config_file = self._sdlc_dir / "config.yaml"
        if _HAS_YAML:
            config_file.write_text(_yaml.dump(config, default_flow_style=False))
        else:
            config_file.write_text(json.dumps(config, indent=2))

        # Write skeleton coding standard
        std_file = self._sdlc_dir / "standards" / "python.md"
        if not std_file.exists():
            std_file.write_text(
                "# Python Coding Standards\n\n"
                "- Use type annotations on all public functions\n"
                "- Line length: 100 characters\n"
                "- Use `from __future__ import annotations` in every file\n"
                '- Pydantic models: set `model_config = {"extra": "forbid"}`\n'
                "- Tests: one test file per source module, class-based organization\n"
            )

        logger.info("Initialized .sdlc/ at %s", self._sdlc_dir)
        return self._sdlc_dir
