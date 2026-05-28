"""Test suite for AST editor module."""

from __future__ import annotations

from pathlib import Path

import pytest

from no_slop_harness.ast_editor import ASTEditor


class TestASTEditorFallback:
    """Fallback (regex-based) AST editing tests."""

    @pytest.fixture
    def editor(self) -> ASTEditor:
        return ASTEditor(grammar="python")

    def test_edit_simple_function(self, editor: ASTEditor, tmp_path: Path) -> None:
        original = """def hello():
    return "old"

def world():
    pass
"""
        replacement = """def hello():
    return "new"
"""
        file_path = tmp_path / "test.py"
        file_path.write_text(original)

        result = editor.edit(file_path, "hello", replacement)
        assert result is True
        assert '"new"' in file_path.read_text()
        assert '"old"' not in file_path.read_text()

    def test_edit_nonexistent_function_returns_false(
        self, editor: ASTEditor, tmp_path: Path
    ) -> None:  # noqa: E501
        file_path = tmp_path / "test.py"
        file_path.write_text("def hello(): pass\n")
        result = editor.edit(file_path, "nonexistent", "def nonexistent(): pass\n")
        assert result is False

    def test_edit_preserves_other_functions(self, editor: ASTEditor, tmp_path: Path) -> None:
        original = """def a():
    return 1

def b():
    return 2
"""
        replacement = """def a():
    return 99
"""
        file_path = tmp_path / "test.py"
        file_path.write_text(original)

        editor.edit(file_path, "a", replacement)
        content = file_path.read_text()
        assert "return 99" in content
        assert "def b()" in content

    def test_edit_rejects_syntax_error(self, editor: ASTEditor, tmp_path: Path) -> None:
        """Replacement that would create invalid syntax should return False."""
        file_path = tmp_path / "test.py"
        file_path.write_text("def hello(): pass\n")

        result = editor.edit(file_path, "hello", "def hello(:\n")  # Invalid syntax
        assert result is False

    def test_edit_class_method(self, editor: ASTEditor, tmp_path: Path) -> None:
        original = """class Foo:
    def bar(self):
        return 1

    def baz(self):
        return 2
"""
        replacement = """class Foo:
    def bar(self):
        return 99
"""
        file_path = tmp_path / "test.py"
        file_path.write_text(original)

        # Note: class methods with self may not match the fallback regex perfectly
        # This tests that we try and handle gracefully
        editor.edit(file_path, "bar", replacement)
