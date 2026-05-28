# AGENTS.md — No-Slop Harness

> **Purpose**: This file provides operating rules, context conventions, and workflow patterns for AI agents (Claude, Codex, GPT, etc.) working on this repository. Load this at the start of every agent session.

## Project Identity

**No-Slop Harness** is a deterministic, local-first LLM orchestration framework implementing the CIV (Coordinator-Implementor-Verifier) pattern. Every line of code here serves to eliminate "slop" — unverified, unstructured, or hallucinated output from LLM pipelines.

## Core Principles

1. **Schema-first design** — All data crossing agent boundaries MUST pass through a Pydantic model. No dicts, no strings pretending to be JSON.
2. **Deterministic scheduling** — Task execution order is computed by Kahn's algorithm, not by LLM judgment.
3. **Sandbox everything** — Any command executed by an agent goes through `execute_sandboxed()` with explicit allowlisting.
4. **Verify before accept** — No task output enters the codebase without passing the Verifier phase.
5. **Structured communication** — Inter-agent messages use `CIVMessage` schema exclusively.

## Agent Roles

### Coordinator Agent

**Constraints:**
- Output MUST be a list of `Task` objects (see `src/no_slop_harness/schemas.py:Task`)
- Each `Task` MUST have: `task_id`, `description`, `action`
- Dependencies express a DAG — no cycles allowed
- Target files MUST be absolute paths
- Cannot use `bash_execute` — plan only, no execution

**Input format:**
```
User request: <natural language>
Context files: <paths to relevant source files>
```

**Output format:**
```json
[
  {
    "task_id": "string (slug or UUID)",
    "description": "Human-readable description",
    "action": "High-level imperative",
    "target_file": "/absolute/path/to/file.py",
    "dependencies": ["task_id_of_prerequisite"],
    "priority": 0
  }
]
```

### Implementor Agent

**Constraints:**
- ONLY use the four sanctioned tools: `read_file`, `write_file`, `edit_file_ast`, `bash_execute`
- All `bash_execute` calls go through sandbox (allowlist enforced)
- Output MUST include a diff summary
- Must respect DAG ordering — never work ahead of dependencies
- Status report format: `{"task_id": "...", "status": "completed|failed", "diff": "...", "test_output": "..."}`

**Tool Contracts:**
| Tool | Input | Output | Constraints |
|------|-------|--------|-------------|
| `read_file` | `{path: str}` | `str` | Must be absolute path |
| `write_file` | `{path: str, content: str}` | `bool` | Overwrites, syntax-validated |
| `edit_file_ast` | `{path: str, node_target: str, replacement: str}` | `bool` | AST/syntax validated |
| `bash_execute` | `{cmd: str}` | `(int, str, str)` | Sandbox-enforced, timeout-limited |

### Verifier Agent

**Constraints:**
- Runs automated checks: test suite, linter, type checker
- Output is binary: `PASS` or `FAIL` with detail
- Rejection MUST include actionable feedback for the Implementor
- Cannot modify code — observe and report only
- If tests don't exist for the changed code, flag as `FAIL` with "missing test coverage"

**Verification pipeline:**
1. `pytest` on affected test files
2. `ruff check` on modified source files
3. `mypy` type checking
4. Syntax validation via `compile()`

## Context Injection

When an agent session starts, inject these files into context:

### Layer 1: Core Schema (always)
```
src/no_slop_harness/schemas.py      — All Pydantic models
src/no_slop_harness/errors.py       — Exception hierarchy
```

### Layer 2: Role-Specific (by agent type)
```
Coordinator:  src/no_slop_harness/dag.py
Implementor:  src/no_slop_harness/sandbox.py, src/no_slop_harness/ast_editor.py
Verifier:     src/no_slop_harness/verifier.py
```

### Layer 3: Task Context (dynamic)
```
The specific files the task references (target_file, dependency outputs)
Previous task results from the pipeline state
```

## Workflow Conventions

### Branch Naming
```
feature/<short-description>
fix/<short-description>
docs/<short-description>
refactor/<short-description>
```

### Commit Messages
```
<type>: <imperative description>

Types: feat, fix, docs, refactor, test, chore, security
```

### Code Style
- Line length: 100 (configured in pyproject.toml)
- All public functions have type annotations
- Docstrings for all public modules, classes, and functions
- `from __future__ import annotations` in every file
- Pydantic models use `model_config = {"extra": "forbid"}`

### Test Conventions
- One test file per source module in `tests/`
- Class-based test organization with descriptive names
- Use `pytest` fixtures and parametrize where appropriate
- Coverage target: >90% on all non-CLI modules

## Error Handling Protocol

1. **Schema violations** → `TaskValidationError` (reject at boundary)
2. **Cyclic dependencies** → `CyclicDependencyError` (reject plan)
3. **Sandbox violations** → `SandboxViolationError` (block command, report)
4. **Verification failures** → `VerificationError` (return to Implementor with feedback)
5. **Tool execution failures** → `ToolExecutionError` (retry or escalate)

## Chained Prompt Patterns

### Pattern 1: Full Pipeline

```
[User Request]
    ↓
[Coordinator: decompose into Tasks]
    ↓
[Orchestrator: topo sort, schedule]
    ↓
[Implementor: execute task N] ← ─┐
    ↓                            │
[Verifier: validate output] ─────┘ (retry if FAIL)
    ↓
[Orchestrator: advance to task N+1 or signal DONE]
```

### Pattern 2: Fix-Forward

When Verifier rejects an Implementor output:
1. Verifier provides structured `FAIL` with: `{task_id, reason, suggested_fix, failing_test}`
2. Orchestrator routes `FAIL` back to Implementor
3. Implementor receives full context (original task + verification failure)
4. Implementor produces corrected output
5. Verifier re-runs verification
6. Max 3 retries before escalation to Coordinator for re-planning

### Pattern 3: Parallel Task Execution

When DAG permits (independent tasks with no shared target files):
1. Orchestrator identifies parallel-ready tasks
2. Dispatches each to separate Implementor instances
3. Verifier processes results independently
4. Orchestrator merges results when all parallel tasks complete

## State Persistence

Pipeline state is serialized to disk at `$NO_SLOP_STATE_DIR/pipeline-{request_id}.json`. The file contains the full `PipelineState` model:

```json
{
  "request_id": "uuid",
  "tasks": {"task_id": Task},
  "task_order": ["task_id", ...],
  "current_index": 0,
  "completed": false,
  "failed": false,
  "failure_reason": null
}
```

Agents can resume interrupted pipelines by loading this state file.

## Quick Reference: Schema Fields

### Task
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | `str` (1-64, identifier) | Yes | Unique task identifier |
| `description` | `str` (max 500) | Yes | Human-readable description |
| `action` | `str` (max 200) | Yes | High-level imperative |
| `target_file` | `str \| None` | No | Primary file path |
| `dependencies` | `list[str]` | No | Prerequisite task IDs |
| `priority` | `int` | No | Scheduling priority (higher = first) |
| `status` | `TaskStatus` | No | Lifecycle state |
| `result` | `str \| None` | No | Outcome string |

### CIVMessage
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sender` | `str` | Yes | Role name |
| `recipient` | `str` | Yes | Target role name |
| `task_id` | `str \| None` | No | Task reference |
| `phase` | `str` | Yes | Pipeline phase |
| `payload` | `dict` | No | Structured data |
| `error` | `str \| None` | No | Error message |
