"""Core data types for the No-Slop Harness CIV pattern."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ToolName(StrEnum):
    """Enumeration of the four core tools available to agents."""

    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    EDIT_FILE_AST = "edit_file_ast"
    BASH_EXECUTE = "bash_execute"


class _ToolParamModel(BaseModel):
    """Base model for tool parameters — prevents extra fields."""

    model_config = {"extra": "forbid"}


class ReadFileParams(_ToolParamModel):
    """Parameters for read_file(path) -> str."""

    path: str = Field(..., min_length=1, description="Absolute path to the file to read.")


class WriteFileParams(_ToolParamModel):
    """Parameters for write_file(path, content) -> bool."""

    path: str = Field(..., description="Absolute path to write to.")
    content: str = Field(..., description="File contents.")


class EditFileAstParams(_ToolParamModel):
    """Parameters for edit_file_ast(path, node_target, replacement) -> bool."""

    path: str = Field(..., description="Absolute path to the file to edit.")
    node_target: str = Field(..., description="Tree-sitter node selector.")
    replacement: str = Field(..., description="AST-compatible replacement string.")


class BashExecuteParams(_ToolParamModel):
    """Parameters for bash_execute(cmd) -> tuple[int, str, str]."""

    cmd: str = Field(
        ...,
        description="Shell command to execute.",
        max_length=4096,
    )


class ToolCall(BaseModel):
    """A single constrained tool call produced by an agent."""

    model_config = {"extra": "forbid"}

    name: ToolName = Field(..., description="Tool to invoke.")
    params: dict[str, Any] = Field(..., description="Validated parameters.")
    rationale: str = Field(
        "",
        description="Brief explanation of why this tool was chosen.",
        max_length=500,
    )


class TaskDependency(BaseModel):
    """A dependency between two tasks in the DAG."""

    model_config = {"extra": "forbid"}

    predecessor: str = Field(..., description="Task ID that must complete first.")
    successor: str = Field(..., description="Task ID that depends on predecessor.")


class TaskStatus(StrEnum):
    """Lifecycle states for a task in the CIV pipeline."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class Task(BaseModel):
    """A single unit of work produced by the Coordinator.

    Tasks form a DAG via their `dependencies` list.  The orchestrator
    topologically sorts them and feeds each one to an Implementor in
    dependency order.
    """

    model_config = {"extra": "forbid"}

    task_id: str = Field(
        ...,
        description="Unique identifier (UUID or short slug).",
        min_length=1,
        max_length=64,
    )
    description: str = Field(
        ...,
        description="Human-readable description of what this task does.",
        max_length=500,
    )
    action: str = Field(
        ...,
        description='High-level imperative, e.g. "Add route handler" or "Fix null check".',
        max_length=200,
    )
    target_file: str | None = Field(
        None,
        description="Primary file path this task modifies (absolute).",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="List of task_ids that must complete before this one starts.",
    )
    priority: int = Field(
        default=0,
        description="Higher priority tasks are scheduled first within a parallel tier.",
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="Current lifecycle state.",
    )
    result: str | None = Field(
        None,
        description="Outcome string (set by Implementor/Verifier).",
    )

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        if not v.isidentifier() and not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("task_id must be a valid Python-style identifier or slug")
        return v


class CIVMessage(BaseModel):
    """A structured message passed between Coordinator, Implementor, and Verifier.

    Every inter-agent communication must conform to this schema, ensuring
    zero-slop deterministic handoffs.
    """

    model_config = {"extra": "forbid"}

    sender: str = Field(..., description="Role name: coordinator | implementor | verifier")
    recipient: str = Field(..., description="Target role name.")
    task_id: str | None = Field(None, description="Task this message concerns.")
    phase: str = Field(..., description="pipeline phase: plan | implement | verify | done")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured data (task list, diff, test results, etc.).",
    )
    error: str | None = Field(None, description="Error message if something went wrong.")


class SandboxConfig(BaseModel):
    """Security sandbox configuration for bash_execute."""

    model_config = {"extra": "forbid"}

    allowed_commands: list[str] = Field(
        default_factory=list,
        description="Whitelist of commands (empty = all, for backward compat).",
    )
    blocked_commands: list[str] = Field(
        default_factory=lambda: [
            "rm -rf /",
            "mkfs",
            "dd if=",
            ">:",
            "chmod 777",
            "chmod -R 777",
            "chown root",
            ":(){ :|:& };:",
            "fork bomb",
            "nohup",
            "shutdown",
            "reboot",
            "halt",
            "poweroff",
        ],
        description="Dangerous commands that are always rejected.",
    )
    timeout_seconds: int = Field(
        default=60,
        description="Maximum wall-clock time per command.",
        ge=1,
        le=300,
    )
    working_directory: str = Field(
        default_factory=lambda: __import__("tempfile").gettempdir(),
        description="CWD for executed commands (defaults to system temp directory).",
    )
    max_output_bytes: int = Field(
        default=1_048_576,  # 1 MiB
        description="Maximum combined stdout+stderr before truncation.",
    )


class PipelineState(BaseModel):
    """Global mutable state of the CIV pipeline for a single request."""

    model_config = {"extra": "forbid"}

    request_id: str = Field(..., description="Unique pipeline invocation ID.")
    tasks: dict[str, Task] = Field(
        default_factory=dict,
        description="task_id -> Task mapping.",
    )
    task_order: list[str] = Field(
        default_factory=list,
        description="Topologically sorted task IDs.",
    )
    current_index: int = Field(
        default=0,
        description="Index into task_order of the currently executing task.",
    )
    completed: bool = Field(default=False)
    failed: bool = Field(default=False)
    failure_reason: str | None = Field(None)
