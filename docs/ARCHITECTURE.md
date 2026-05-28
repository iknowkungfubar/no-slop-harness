# Architecture — No-Slop Harness

## Design Philosophy

No-Slop Harness is built on three axioms:

1. **LLMs are unreliable without structure** — Every LLM output must pass through a validated schema before entering the system.
2. **Determinism is achievable through constraints** — By limiting the tool surface and enforcing a state machine, we eliminate ambiguity.
3. **Verification is non-negotiable** — No code enters the codebase without passing automated checks.

## System Overview

```
                          ┌───────────────────────────────────────┐
                          │            User Request               │
                          └───────────────┬───────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           CIV Pipeline                                   │
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐               │
│  │ Coordinator  │───▶│ Implementor  │───▶│   Verifier   │               │
│  │              │    │              │    │              │               │
│  │  decompose   │    │  read_file   │    │  run_tests   │               │
│  │  into DAG    │    │  write_file  │    │  run_lint    │               │
│  │  of Tasks    │    │  edit_ast    │    │  run_typeck  │               │
│  │              │    │  bash_exec   │    │  verify_diff │               │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘               │
│         │                   │                   │                        │
│         │    ┌──────────────┴───────────────────┘                        │
│         │    │                                                           │
│         ▼    ▼                                                           │
│  ┌──────────────────────────────────────────────┐                        │
│  │            PipelineOrchestrator               │                        │
│  │                                               │                        │
│  │  ┌─────────────┐  ┌──────────────┐           │                        │
│  │  │ dag.py       │  │ sandbox.py   │           │                        │
│  │  │ topo sort    │  │ allowlist    │           │                        │
│  │  │ validate     │  │ timeout      │           │                        │
│  │  └─────────────┘  └──────────────┘           │                        │
│  │                                               │                        │
│  │  PipelineState {tasks, order, index, flags}   │                        │
│  └──────────────────────────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────────┘
```

## Module Deep Dives

### schemas.py — The Type System

All inter-component communication flows through Pydantic v2 models. Every model uses `extra = "forbid"` to reject unknown fields at the boundary — this is intentional: if the LLM emits an unexpected field, we want to catch it immediately rather than silently ignore it.

**Key models:**

| Model | Purpose | Key Constraints |
|-------|---------|-----------------|
| `Task` | Unit of work | `task_id` validated as identifier, `dependencies` form DAG edges |
| `CIVMessage` | Inter-agent protocol | `sender`, `recipient`, `phase` form state machine transitions |
| `ToolCall` | LLM tool invocation | `name` constrained to `ToolName` enum, `params` validated per-tool |
| `SandboxConfig` | Security policy | `timeout_seconds` bounded 1-300, `max_output_bytes` caps at 1 MiB |
| `PipelineState` | Global state | Serialized to disk for resumability |

**Design decision — Pydantic vs dataclasses**: Pydantic was chosen for its runtime validation, serialization, and JSON Schema generation. Dataclasses lack validation; attrs adds a dependency without Pydantic's ecosystem integration.

### dag.py — Deterministic Scheduling

Implements Kahn's algorithm with a stable sort tiebreaker. The sort order is: descending priority → ascending task_id (alphabetical). This guarantees deterministic ordering regardless of insertion order.

**Key functions:**

- `topological_sort(tasks, deps)` → `list[str]`: Returns task IDs in execution order. Raises `CyclicDependencyError` if cycles exist.
- `validate_dag(tasks, deps)` → `list[str]`: Returns list of validation errors (empty = valid). Checks: orphan dependencies, self-references, cycles.
- `_insert_sorted(queue, task_id, tasks)`: Internal helper that maintains priority ordering in the BFS queue.

**Time complexity**: O(V + E) for sort, O(V + E) for validation.

### orchestrator.py — State Machine

`PipelineOrchestrator` implements the CIV lifecycle as an explicit state machine:

```
PENDING → ASSIGNED → IN_PROGRESS → COMPLETED → VERIFYING → COMPLETED|FAILED
                                                   ↓
                                               ROLLED_BACK (reserved)
```

**Phase transitions:**

| Phase | Method | Pre-condition | Post-condition |
|-------|--------|---------------|----------------|
| Plan | `ingest_tasks()` | Tasks provided | DAG validated, `task_order` computed |
| Implement | `next_task()` | Tasks pending | Task marked `ASSIGNED` |
| Implement | `report_result()` | Task assigned | Task marked `COMPLETED` or `FAILED` |
| Verify | `verify_task()` | Task completed | Task marked `VERIFYING` |
| Verify | `verification_complete()` | Task verifying | Task marked `COMPLETED` or `FAILED` |

### sandbox.py — Security Layer

All command execution goes through `execute_sandboxed(cmd, config)`. Two-tier blocking: implicit blocklist (hardcoded dangerous patterns) + configurable blocklist. Allowlist mode restricts to explicit commands.

**Blocking logic:**
1. Normalize command to lowercase
2. Check implicit blocklist (substring match) → `SandboxViolation`
3. Check config blocklist (substring match) → `SandboxViolation`
4. If allowlist non-empty, check base command → `SandboxViolation`
5. Execute with `subprocess.run(shell=True, timeout, capture_output)`
6. Truncate output if exceeds `max_output_bytes`

### ast_editor.py — Syntax-Aware Editing

Two-phase editing: attempts tree-sitter if available, falls back to regex + `compile()` validation.

**Tree-sitter path**: Uses tree-sitter bindings to parse the AST, locate the target node, and perform surgical replacement. Currently stubbed — full tree-sitter integration requires grammar files.

**Fallback path**: Regex matches function/class definitions by name, replaces, validates with `compile()`. This catches syntax errors but can't handle nested methods, decorated functions, or non-Python files.

### verifier.py — Quality Gate

Three standard checks: pytest, ruff, mypy. Plus `verify_diff()` for patch-level syntax validation.

Each check returns a `TestResult(passed, output, returncode)` — the Verifier agent interprets these and produces a `CIVMessage` with the verdict.

## Data Flow

```
User Request (natural language)
    │
    ▼
Coordinator LLM ──▶ list[Task] (Pydantic validated)
    │
    ▼
Orchestrator.ingest_tasks() ──▶ DAG validation + topo sort
    │
    ▼
For each Task in order:
    │
    ├──▶ Implementor LLM ──▶ ToolCall[] ──▶ sandbox/ast_editor ──▶ diff + result
    │         │
    │         ▼
    ├──▶ Verifier ──▶ pytest + ruff + mypy ──▶ PASS|FAIL
    │         │
    │         ├── PASS ──▶ advance to next task
    │         └── FAIL ──▶ retry (max 3) or escalate
    │
    ▼
PipelineState.completed = True ──▶ serialized to disk
```

## Design Decisions

### Why not LangChain/LlamaIndex?

Those frameworks prioritize flexibility over determinism. They allow arbitrary tool chains, dynamic prompt construction, and unstructured agent communication. No-Slop Harness takes the opposite approach: every transition is a validated schema, every tool call is constrained to an enum, and every output is verified.

### Why shell=True in sandbox?

`shell=True` is necessary because LLMs generate arbitrary shell commands that may include pipes, redirects, or variable expansion. The risk is mitigated by the blocklist/allowlist system and timeout enforcement. A future direction is to parse commands with `shlex` and reconstruct them without shell=True for commands that don't require it.

### Why Kahn's algorithm over DFS?

Kahn's algorithm produces a BFS-based ordering that naturally groups independent tasks, enabling future parallel execution. DFS-based topological sort produces a depth-first ordering that doesn't reflect parallelism opportunities.

### Why NamedTuple for TestResult?

`TestResult` was chosen as a NamedTuple (not a Pydantic model) because it's an internal implementation detail, not a cross-boundary type. It doesn't need validation or serialization — it's a simple value object returned from subprocess calls.

## Future Directions

1. **Full tree-sitter integration** — Grammar bundles for Python, TypeScript, Go, Rust
2. **Distributed pipeline** — Orchestrator as a server, agents as workers communicating via CIVMessage over HTTP/gRPC
3. **Checkpoint/restore** — Resume interrupted pipelines from state file
4. **Policy as code** — SandboxConfig loaded from YAML/TOML with hot-reload
5. **Observability dashboard** — Metrics exported to Prometheus, visualized in Grafana
6. **Multi-language support** — AST editor for TypeScript, Go, Rust via tree-sitter grammars
