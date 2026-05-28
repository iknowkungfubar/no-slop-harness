"""Tree-sitter powered AST editing (stub).

Full AST editing requires tree-sitter bindings with language grammars.
This module provides the interface and a safe fallback implementation.
"""

from __future__ import annotations

import re
from pathlib import Path


class ASTEditError(Exception):
    """Raised when an AST edit fails."""


class ASTEditor:
    """AST-based file editor using tree-sitter.

    In production, this would use tree-sitter to perform precise
    syntax-aware edits. This stub provides regex-based fallback
    suitable for well-structured code.
    """

    def __init__(self, grammar: str = "python") -> None:
        self.grammar = grammar
        self._available = False
        self._try_init_tree_sitter()

    def _try_init_tree_sitter(self) -> None:
        try:
            import tree_sitter  # noqa: F401

            self._available = True
        except ImportError:
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def edit(
        self,
        path: Path,
        node_target: str,
        replacement: str,
    ) -> bool:
        """Perform an AST edit on the file at `path`.

        Args:
            path: Path to the source file.
            node_target: Tree-sitter node selector (e.g. function name).
            replacement: New content for the matched node.

        Returns:
            True if the edit was applied, False otherwise.

        Raises:
            ASTEditError: If the edit cannot be performed safely.
        """
        content = path.read_text(encoding="utf-8")

        if self._available:
            return self._edit_tree_sitter(path, content, node_target, replacement)
        else:
            return self._edit_fallback(path, content, node_target, replacement)

    def _edit_tree_sitter(
        self,
        path: Path,
        content: str,
        node_target: str,
        replacement: str,
    ) -> bool:
        # Full tree-sitter implementation would go here
        # Fall back to regex-based editing when tree-sitter is not fully wired up
        return self._edit_fallback(path, content, node_target, replacement)

    def _edit_fallback(
        self,
        path: Path,
        content: str,
        node_target: str,
        replacement: str,
    ) -> bool:
        """Regex-based fallback — validates syntax after edit."""
        # Match function/class definition by name
        pattern = rf"((?:def|class)\s+{re.escape(node_target)}\s*\(.*?\n(?:.*?\n)*?(?=\n(?:def|class)\s|\Z))"  # noqa: E501
        match = re.search(pattern, content, re.MULTILINE)
        if not match:
            return False

        new_content = content[: match.start()] + replacement + content[match.end() :]

        # Syntax validation for Python
        try:
            compile(new_content, path, "exec")
        except SyntaxError:
            return False

        path.write_text(new_content, encoding="utf-8")
        return True
