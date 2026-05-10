"""Core tool implementations and registry."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Union

from .schemas import (
    BashExecuteArgs,
    BashExecuteResult,
    EditFileAstArgs,
    EditFileAstResult,
    ReadFileArgs,
    ReadFileResult,
    WriteFileArgs,
    WriteFileResult,
)

ToolResult = Union[ReadFileResult, WriteFileResult, EditFileAstResult, BashExecuteResult]
ToolArgs = Union[ReadFileArgs, WriteFileArgs, EditFileAstArgs, BashExecuteArgs]

# ---------------------------------------------------------------------------
# Language registry for tree-sitter AST editing
# ---------------------------------------------------------------------------

_LANGUAGE_CACHE: dict[str, object] = {}

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
}


def _get_language(lang_name: str):
    """Load and cache a tree-sitter Language object."""
    if lang_name in _LANGUAGE_CACHE:
        return _LANGUAGE_CACHE[lang_name]

    from tree_sitter import Language  # deferred to avoid hard startup dep

    if lang_name == "python":
        import tree_sitter_python

        language = Language(tree_sitter_python.language())
    else:
        raise ValueError(f"Unsupported language: {lang_name}")

    _LANGUAGE_CACHE[lang_name] = language
    return language


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def read_file(args: ReadFileArgs) -> ReadFileResult:
    try:
        content = Path(args.path).read_text(encoding="utf-8")
        return ReadFileResult(content=content)
    except Exception as e:
        return ReadFileResult(content="", success=False, error=str(e))


def write_file(args: WriteFileArgs) -> WriteFileResult:
    try:
        path = Path(args.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args.content, encoding="utf-8")
        return WriteFileResult(success=True)
    except Exception as e:
        return WriteFileResult(success=False, error=str(e))


def edit_file_ast(args: EditFileAstArgs) -> EditFileAstResult:
    """Tree-sitter powered AST editing — prevents regex slop."""
    try:
        from tree_sitter import Parser, Query, QueryCursor

        path = Path(args.path)
        source = path.read_bytes()

        lang_name = EXTENSION_TO_LANGUAGE.get(path.suffix)
        if not lang_name:
            return EditFileAstResult(
                success=False,
                error=f"No tree-sitter grammar for extension: {path.suffix}",
            )

        language = _get_language(lang_name)
        parser = Parser(language)
        tree = parser.parse(source)

        query = Query(language, args.node_target)
        cursor = QueryCursor(query)
        captures = cursor.captures(tree.root_node)

        if not captures:
            return EditFileAstResult(
                success=False,
                error=f"No AST node matched query: {args.node_target}",
            )

        first_key = next(iter(captures))
        nodes = captures[first_key]
        target = nodes[0] if isinstance(nodes, list) else nodes

        start = target.start_byte
        end = target.end_byte
        new_source = source[:start] + args.replacement.encode("utf-8") + source[end:]
        path.write_bytes(new_source)

        return EditFileAstResult(success=True)
    except ImportError as e:
        return EditFileAstResult(success=False, error=f"Missing dependency: {e}")
    except Exception as e:
        return EditFileAstResult(success=False, error=str(e))


def bash_execute(args: BashExecuteArgs) -> BashExecuteResult:
    try:
        result = subprocess.run(
            args.cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return BashExecuteResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    except subprocess.TimeoutExpired:
        return BashExecuteResult(exit_code=-1, stdout="", stderr="Timed out after 60s")
    except Exception as e:
        return BashExecuteResult(exit_code=-1, stdout="", stderr=str(e))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file_ast": edit_file_ast,
    "bash_execute": bash_execute,
}

TOOL_ARGS_MAP: dict = {
    "read_file": ReadFileArgs,
    "write_file": WriteFileArgs,
    "edit_file_ast": EditFileAstArgs,
    "bash_execute": BashExecuteArgs,
}
