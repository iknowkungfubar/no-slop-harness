"""Pydantic schemas for the four core tools and agent communication."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Tool input schemas
# ---------------------------------------------------------------------------


class ReadFileArgs(BaseModel):
    """Arguments for read_file."""

    path: str = Field(description="File path to read")


class WriteFileArgs(BaseModel):
    """Arguments for write_file."""

    path: str = Field(description="File path to write")
    content: str = Field(description="Full file content")


class EditFileAstArgs(BaseModel):
    """Arguments for edit_file_ast (tree-sitter powered)."""

    path: str = Field(description="Path to the source file")
    node_target: str = Field(description="Tree-sitter S-expression query with a capture")
    replacement: str = Field(description="Replacement source text for the captured node")


class BashExecuteArgs(BaseModel):
    """Arguments for bash_execute."""

    cmd: str = Field(description="Shell command to execute")


# ---------------------------------------------------------------------------
# Tool output schemas
# ---------------------------------------------------------------------------


class ReadFileResult(BaseModel):
    content: str
    success: bool = True
    error: str | None = None


class WriteFileResult(BaseModel):
    success: bool
    error: str | None = None


class EditFileAstResult(BaseModel):
    success: bool
    error: str | None = None


class BashExecuteResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


# ---------------------------------------------------------------------------
# Agent communication schemas
# ---------------------------------------------------------------------------


class ToolCall(BaseModel):
    """A single tool invocation."""

    name: Literal["read_file", "write_file", "edit_file_ast", "bash_execute"]
    arguments: dict


class AgentAction(BaseModel):
    """Agent output: invoke a tool or signal completion."""

    action: Literal["call_tool", "finish"]
    tool_call: ToolCall | None = None
    summary: str = ""


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(BaseModel):
    """A single unit of work assigned by the Coordinator."""

    id: str
    description: str
    dependencies: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Literal["implementor", "verifier"] = "implementor"
    tool_hints: list[str] = Field(default_factory=list)


class TaskPlan(BaseModel):
    """Coordinator output: dependency-ordered task list."""

    tasks: list[Task]


class VerificationResult(BaseModel):
    """Verifier output: pass/fail assessment."""

    passed: bool
    failures: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
