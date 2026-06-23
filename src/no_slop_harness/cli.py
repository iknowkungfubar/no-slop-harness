"""CLI entrypoint for the No-Slop Harness."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from no_slop_harness import __version__
from no_slop_harness.orchestrator import PipelineOrchestrator
from no_slop_harness.schemas import SandboxConfig

console = Console()


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging.")
@click.option("--json", "json_flag", is_flag=True, help="Output machine-parseable JSON instead of rich tables.")
@click.pass_context
def main(ctx: click.Context, verbose: bool, json_flag: bool) -> None:
    """No-Slop Harness — deterministic LLM orchestration via the CIV pattern."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_flag


@main.command()
@click.argument("task", nargs=-1, required=True)
@click.option("--base-url", default="http://localhost:1234/v1", help="OpenAI-compatible API base URL.")
@click.option("--model", default="qwen/qwen3.6-35b-a3b", help="Model name.")
@click.option("--api-key", default="not-needed", help="API key (default: 'not-needed' for local LM Studio).")
@click.option("--timeout", default=120, type=int, help="Command timeout in seconds.")
@click.pass_context
def run(
    ctx: click.Context,
    task: tuple[str, ...],
    base_url: str,
    model: str,
    api_key: str,
    timeout: int,
) -> None:
    """Run a full CIV pipeline from a task description.

    TASK is the natural-language description (e.g. "Add a User model with email field").
    Use quotes for multi-word descriptions.
    """
    task_str = " ".join(task)
    sandbox = SandboxConfig(timeout_seconds=timeout)
    from no_slop_harness.runner import CIVPipeline

    async def _run() -> dict:
        pipeline = CIVPipeline(
            base_url=base_url,
            model=model,
            api_key=api_key,
            sandbox_config=sandbox,
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
            transient=False,
        ) as progress:
            progress.add_task(description="Coordinating, implementing, and verifying...", total=None)
            result = await pipeline.run(task_str)
        await pipeline.close()
        return result

    try:
        result = asyncio.run(_run())
    except Exception as e:
        if _use_json(ctx):
            _print_json({"status": "error", "message": str(e)})
        else:
            console.print(f"[red]Pipeline execution failed: {e}[/red]")
        raise click.Abort()

    if _use_json(ctx):
        _print_json(result)
        return

    if result.get("success"):
        console.print("[bold green]✓ Pipeline completed successfully[/bold green]")
    else:
        console.print("[bold red]✗ Pipeline completed with failures[/bold red]")

    console.print(f"Request ID: {result.get('request_id', 'N/A')}")
    table = Table(title="Pipeline Results")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Total tasks", str(result.get("tasks_total", 0)))
    table.add_row("Completed", str(result.get("tasks_completed", 0)))
    table.add_row("Failed", str(result.get("tasks_failed", 0)))
    console.print(table)

    summary = result.get("summary", "")
    if summary:
        console.print(f"\n{summary}")

    if not result.get("success"):
        raise click.Abort()


@main.command()
@click.option(
    "--sandbox-allowlist",
    multiple=True,
    help="Whitelisted commands for bash_execute (repeatable).",
)
@click.option("--timeout", default=60, type=int, help="Command timeout in seconds.")
@click.option(
    "--request-id",
    default=None,
    help="Override the auto-generated request ID.",
)
def init(sandbox_allowlist: tuple[str, ...], timeout: int, request_id: str | None) -> None:
    """Initialize a new CIV pipeline session."""
    import os

    sandbox = SandboxConfig(
        allowed_commands=list(sandbox_allowlist),
        timeout_seconds=timeout,
    )
    pipe = PipelineOrchestrator(sandbox_config=sandbox)
    state = pipe.state
    state.request_id = request_id or pipe.request_id

    # Persist state to disk
    state_dir = Path(os.environ.get("NO_SLOP_STATE_DIR", ".no-slop"))
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / f"pipeline-{state.request_id}.json"
    # Restrict permissions to owner-only (may contain file paths, config, secrets)
    state_path.write_text(state.model_dump_json(indent=2))
    os.chmod(str(state_path), 0o600)

    console.print(f"[bold green]Pipeline initialized:[/bold green] {state.request_id}")
    console.print(f"State file: {state_path}")
    if sandbox.allowed_commands:
        console.print(f"Command allowlist: {sandbox.allowed_commands}")


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show the current pipeline status."""
    state = _load_state()
    if state is None:
        if _use_json(ctx):
            _print_json({"status": "no_state", "message": "No pipeline state found."})
        else:
            console.print("[yellow]No pipeline state found.[/yellow]")
        return

    if _use_json(ctx):
        _print_json(state)
        return

    table = Table(title=f"Pipeline {state.get('request_id', 'unknown')}")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Total tasks", str(state.get("total_tasks", 0)))
    table.add_row("Completed", str(state.get("completed", 0)))
    table.add_row("Failed", str(state.get("failed", 0)))
    table.add_row("In Progress", str(state.get("in_progress", 0)))
    table.add_row("Pending", str(state.get("pending", 0)))
    table.add_row("Done", str(state.get("all_done", False)))
    console.print(table)


@main.command()
@click.argument("task_id")
@click.option("--result", "-r", default="", help="Task result output.")
@click.option("--success/--fail", default=True, help="Whether the task succeeded.")
@click.pass_context
def report(ctx: click.Context, task_id: str, result: str, success: bool) -> None:
    """Report the result of an implemented task.

    Wires through to PipelineOrchestrator.report_result() and persists the
    updated pipeline state to disk.
    """
    state = _load_state()
    if state is None:
        if _use_json(ctx):
            _print_json({"status": "error", "message": "No pipeline state found. Run 'no-slop init' first."})
        else:
            console.print("[red]No pipeline state found. Run 'no-slop init' first.[/red]")
        return

    tasks = state.get("tasks", {}).get(task_id)
    if not tasks:
        if _use_json(ctx):
            _print_json({"status": "error", "message": f"Unknown task_id: {task_id}"})
        else:
            console.print(f"[red]Unknown task_id: {task_id}[/red]")
        return

    # Reconstruct orchestrator and state from disk
    from no_slop_harness.schemas import PipelineState

    pipeline_state = PipelineState.model_validate(state)
    orchestrator = PipelineOrchestrator()
    orchestrator.state = pipeline_state

    # Call the orchestrator's report_result method
    msg = orchestrator.report_result(task_id, result, success)
    if msg.error:
        _save_state(orchestrator.state)
        if _use_json(ctx):
            _print_json({"status": "error", "task_id": task_id, "message": msg.error, "result": result, "success": success})
        else:
            console.print(f"[red]Error reporting result: {msg.error}[/red]")
        return

    # Persist updated state
    _save_state(orchestrator.state)

    if _use_json(ctx):
        _print_json({
            "status": "ok",
            "task_id": task_id,
            "result": result,
            "success": success,
            "next_phase": msg.phase,
        })
        return

    if success:
        console.print(f"[green]Task {task_id}: COMPLETED[/green]")
    else:
        console.print(f"[red]Task {task_id}: FAILED — {result}[/red]")

    # Show next steps
    next_phase = msg.phase
    if next_phase == "verify":
        console.print(f"Run [bold]'no-slop verify {task_id}'[/bold] to verify this task.")


@main.command()
@click.argument("task_id")
@click.option("--passed/--failed", default=True, help="Whether verification passed.")
@click.option("--detail", "-d", default="", help="Verification detail.")
@click.pass_context
def verify(ctx: click.Context, task_id: str, passed: bool, detail: str) -> None:
    """Verify a completed task.

    Calls PipelineOrchestrator.verify_task() to transition the task state,
    runs the Verifier checks (pytest, lint, typecheck) on modified files,
    then records the verdict via verification_complete().
    """
    state = _load_state()
    if state is None:
        if _use_json(ctx):
            _print_json({"status": "error", "message": "No pipeline state found. Run 'no-slop init' first."})
        else:
            console.print("[red]No pipeline state found. Run 'no-slop init' first.[/red]")
        return

    tasks = state.get("tasks", {}).get(task_id)
    if not tasks:
        if _use_json(ctx):
            _print_json({"status": "error", "message": f"Unknown task_id: {task_id}"})
        else:
            console.print(f"[red]Unknown task_id: {task_id}[/red]")
        return

    from no_slop_harness.schemas import PipelineState

    pipeline_state = PipelineState.model_validate(state)
    orchestrator = PipelineOrchestrator()
    orchestrator.state = pipeline_state

    # Transition task to verifying state
    verify_msg = orchestrator.verify_task(task_id)
    if verify_msg.error:
        if _use_json(ctx):
            _print_json({"status": "error", "task_id": task_id, "message": verify_msg.error})
        else:
            console.print(f"[red]Error starting verification: {verify_msg.error}[/red]")
        return

    # Run the Verifier checks
    from no_slop_harness.verifier import Verifier

    verifier = Verifier()
    target_file = tasks.get("target_file")
    if target_file:
        test_result = verifier.run_pytest() if Path(target_file).name.startswith("test_") else None
    else:
        test_result = None

    lint_result = verifier.run_lint()
    type_result = verifier.run_typecheck()

    # Determine pass/fail from actual checks, unless explicitly overridden
    all_passed = lint_result.passed and type_result.passed
    if test_result is not None:
        all_passed = all_passed and test_result.passed

    # Build detail from actual results
    detail_parts: list[str] = []
    if test_result and not test_result.passed:
        detail_parts.append(f"Tests: {test_result.output[:200]}")
    if not lint_result.passed:
        detail_parts.append(f"Lint: {lint_result.output[:200]}")
    if not type_result.passed:
        detail_parts.append(f"Typecheck: {type_result.output[:200]}")

    # Detect explicit --passed/--failed override
    import sys

    has_explicit = "--passed" in sys.argv[1:] or "--failed" in sys.argv[1:]
    actual_passed = passed if has_explicit else all_passed

    # Record verdict
    detail_str = detail if detail else "; ".join(detail_parts) if detail_parts else ("All checks passed." if actual_passed else "Verification failed.")
    complete_msg = orchestrator.verification_complete(task_id, actual_passed, detail_str)

    # Persist updated state
    _save_state(orchestrator.state)

    if _use_json(ctx):
        _print_json({
            "status": "ok" if actual_passed else "failed",
            "task_id": task_id,
            "passed": actual_passed,
            "detail": detail_str,
            "test_output": test_result.output if test_result else "",
            "lint_output": lint_result.output,
            "typecheck_output": type_result.output,
        })
        return

    if actual_passed:
        console.print(f"[green]Task {task_id}: VERIFIED ✓[/green]")
    else:
        console.print(
            Panel.fit(detail_str or "Verification failed", title=f"[red]Task {task_id}: FAILED[/red]")
        )


@main.command(name="list")
@click.pass_context
def list_tasks(ctx: click.Context) -> None:
    """List all tasks in the current pipeline."""
    state = _load_state()
    if state is None:
        if _use_json(ctx):
            _print_json({"status": "no_state", "message": "No pipeline state found."})
        else:
            console.print("[yellow]No pipeline state found.[/yellow]")
        return

    tasks = state.get("tasks", {})
    if not tasks:
        if _use_json(ctx):
            _print_json({"status": "no_tasks", "request_id": state.get("request_id")})
        else:
            console.print("[yellow]No tasks in pipeline.[/yellow]")
        return

    if _use_json(ctx):
        output = {
            "request_id": state.get("request_id"),
            "tasks": [
                {
                    "task_id": tid,
                    "description": t.get("description", ""),
                    "status": t.get("status", "unknown"),
                    "dependencies": t.get("dependencies", []),
                }
                for tid, t in sorted(tasks.items())
            ],
        }
        _print_json(output)
        return

    table = Table(title=f"Tasks — Pipeline {state.get('request_id', 'unknown')}")
    table.add_column("Task ID", style="bold")
    table.add_column("Description")
    table.add_column("Status")
    table.add_column("Dependencies")

    order = state.get("task_order", [])
    for tid in order:
        t = tasks.get(tid, {})
        task_status = t.get("status", "unknown")
        color = {
            "completed": "green",
            "failed": "red",
            "in_progress": "yellow",
            "verifying": "cyan",
            "pending": "white",
        }.get(task_status, "white")

        table.add_row(
            tid,
            t.get("description", ""),
            f"[{color}]{task_status}[/{color}]",
            ", ".join(t.get("dependencies", [])) or "—",
        )

    console.print(table)


@main.command()
@click.pass_context
def version(ctx: click.Context) -> None:
    """Show the No-Slop Harness version."""
    if _use_json(ctx):
        _print_json({"name": "no-slop-harness", "version": __version__})
    else:
        console.print(f"No-Slop Harness v{__version__}")


def _use_json(ctx: click.Context) -> bool:
    """Check whether JSON output mode is active (global --json flag)."""
    # Walk up the context chain to find the root ctx.obj
    c = ctx
    while c.parent is not None:
        c = c.parent
    return bool(c.obj.get("json", False))


def _print_json(data: dict) -> None:
    """Print data as JSON to stdout."""
    click.echo(json.dumps(data, indent=2, default=str))


def _save_state(state: object) -> None:
    """Persist a PipelineState object to the state directory."""
    import os

    state_dir = Path(os.environ.get("NO_SLOP_STATE_DIR", ".no-slop"))
    state_dir.mkdir(parents=True, exist_ok=True)
    request_id = getattr(state, "request_id", "unknown")
    state_path = state_dir / f"pipeline-{request_id}.json"
    serialized = json.loads(state.model_dump_json()) if hasattr(state, "model_dump_json") else {}
    state_path.write_text(json.dumps(serialized, indent=2, default=str))
    os.chmod(str(state_path), 0o600)


def _load_state() -> dict | None:
    """Load pipeline state from the state directory."""
    import json
    import os

    state_dir = Path(os.environ.get("NO_SLOP_STATE_DIR", ".no-slop"))
    json_files = list(state_dir.glob("pipeline-*.json"))
    if not json_files:
        return None
    # Load the most recent by modification time
    try:
        latest = sorted(json_files, key=lambda p: p.stat().st_mtime)[-1]
    except (IndexError, OSError):
        latest = json_files[0]
    return json.loads(latest.read_text())  # type: ignore[no-any-return]


if __name__ == "__main__":
    main()
