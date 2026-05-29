"""Tests for the four core tools."""

from __future__ import annotations

from pathlib import Path

from harness.schemas import BashExecuteArgs, EditFileAstArgs, ReadFileArgs, WriteFileArgs
from harness.tools import bash_execute, edit_file_ast, read_file, write_file


class TestReadFile:
    def test_success(self, tmp_dir: Path):
        f = tmp_dir / "hello.txt"
        f.write_text("content")
        result = read_file(ReadFileArgs(path=str(f)))
        assert result.success
        assert result.content == "content"

    def test_missing_file(self):
        result = read_file(ReadFileArgs(path="/nonexistent/path/file.txt"))
        assert not result.success
        assert result.error is not None


class TestWriteFile:
    def test_success(self, tmp_dir: Path):
        f = tmp_dir / "out.txt"
        result = write_file(WriteFileArgs(path=str(f), content="hello"))
        assert result.success
        assert f.read_text() == "hello"

    def test_creates_parents(self, tmp_dir: Path):
        f = tmp_dir / "a" / "b" / "c.txt"
        result = write_file(WriteFileArgs(path=str(f), content="deep"))
        assert result.success
        assert f.read_text() == "deep"


class TestBashExecute:
    def test_echo(self):
        result = bash_execute(BashExecuteArgs(cmd="echo hello"))
        assert result.exit_code == 0
        assert result.stdout.strip() == "hello"

    def test_failing_command(self):
        result = bash_execute(BashExecuteArgs(cmd="false"))
        assert result.exit_code != 0


class TestEditFileAst:
    def test_rename_function(self, sample_python_file: Path):
        result = edit_file_ast(
            EditFileAstArgs(
                path=str(sample_python_file),
                node_target="(function_definition name: (identifier) @target)",
                replacement="greet",
            )
        )
        assert result.success
        content = sample_python_file.read_text()
        assert "greet" in content
        assert "hello" not in content

    def test_no_match(self, sample_python_file: Path):
        result = edit_file_ast(
            EditFileAstArgs(
                path=str(sample_python_file),
                node_target="(class_definition name: (identifier) @target)",
                replacement="Foo",
            )
        )
        assert not result.success
        assert "No AST node" in (result.error or "")

    def test_unsupported_extension(self, tmp_dir: Path):
        f = tmp_dir / "test.xyz"
        f.write_text("some content")
        result = edit_file_ast(
            EditFileAstArgs(
                path=str(f),
                node_target="(expression) @target",
                replacement="new content",
            )
        )
        assert not result.success
        assert "No tree-sitter grammar" in (result.error or "")
