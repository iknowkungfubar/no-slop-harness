"""CLI entrypoint for the No-Slop Harness."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from no_slop_harness import __version__
from no_slop_harness.orchestrator import PipelineOrchestrator
from no_slop_harness.schemas import SandboxConfig

console = Console()


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging.")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """No-Slop Harness — deterministic LLM orchestration via the CIV pattern."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    ctx.ensure_object(dict)


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
    state_path.write_text(state.model_dump_json(indent=2))

    console.print(f"[bold green]Pipeline initialized:[/bold green] {state.request_id}")
    console.print(f"State file: {state_path}")
    if sandbox.allowed_commands:
        console.print(f"Command allowlist: {sandbox.allowed_commands}")


@main.command()
def status() -> None:
    """Show the current pipeline status."""
    state = _load_state()
    if state is None:
        console.print("[yellow]No pipeline state found.[/yellow]")
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
def report(task_id: str, result: str, success: bool) -> None:
    """Report the result of an implemented task."""
    state = _load_state()
    if state is None:
        console.print("[red]No pipeline state found. Run 'no-slop init' first.[/red]")
        return

    tasks = state.get("tasks", {}).get(task_id)
    if not tasks:
        console.print(f"[red]Unknown task_id: {task_id}[/red]")
        return

    # Simulate the orchestrator report path
    if success:
        console.print(f"[green]Task {task_id}: COMPLETED[/green]")
    else:
        console.print(f"[red]Task {task_id}: FAILED — {result}[/red]")


@main.command()
@click.argument("task_id")
@click.option("--passed/--failed", default=True, help="Whether verification passed.")
@click.option("--detail", "-d", default="", help="Verification detail.")
def verify(task_id: str, passed: bool, detail: str) -> None:
    """Verify a completed task."""
    state = _load_state()
    if state is None:
        console.print("[red]No pipeline state found. Run 'no-slop init' first.[/red]")
        return

    tasks = state.get("tasks", {}).get(task_id)
    if not tasks:
        console.print(f"[red]Unknown task_id: {task_id}[/red]")
        return

    if passed:
        console.print(f"[green]Task {task_id}: VERIFIED ✓[/green]")
    else:
        console.print(
            Panel.fit(detail or "Verification failed", title=f"[red]Task {task_id}: FAILED[/red]")
        )


@main.command()
def list() -> None:
    """List all tasks in the current pipeline."""
    state = _load_state()
    if state is None:
        console.print("[yellow]No pipeline state found.[/yellow]")
        return

    tasks = state.get("tasks", {})
    if not tasks:
        console.print("[yellow]No tasks in pipeline.[/yellow]")
        return

    table = Table(title=f"Tasks — Pipeline {state.get('request_id', 'unknown')}")
    table.add_column("Task ID", style="bold")
    table.add_column("Description")
    table.add_column("Status")
    table.add_column("Dependencies")

    order = state.get("task_order", [])
    for tid in order:
        t = tasks.get(tid, {})
        status = t.get("status", "unknown")
        color = {
            "completed": "green",
            "failed": "red",
            "in_progress": "yellow",
            "verifying": "cyan",
            "pending": "white",
        }.get(status, "white")

        table.add_row(
            tid,
            t.get("description", ""),
            f"[{color}]{status}[/{color}]",
            ", ".join(t.get("dependencies", [])) or "—",
        )

    console.print(table)


@main.command()
def version() -> None:
    """Show the No-Slop Harness version."""
    console.print(f"No-Slop Harness v{__version__}")


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
    return json.loads(latest.read_text())  # type: ignore[return-value]


if __name__ == "__main__":
    main()
