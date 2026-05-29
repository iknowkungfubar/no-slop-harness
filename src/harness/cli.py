"""CLI entry point for the harness."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .client import InferenceClient
from .config import HarnessConfig, default_toml, load_config
from .orchestrator import Orchestrator, OrchestratorResult, TaskResult
from .schemas import Task, TaskStatus

console = Console(stderr=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness",
        description="Minimalist Agentic Harness — CIV Pattern",
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "-c", "--config", default="harness.toml", help="Config file path (default: harness.toml)"
    )
    parser.add_argument("--repo", default=".", help="Repository path")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Execute full CIV pipeline")
    run_cmd.add_argument("prompt", help="User request")

    plan_cmd = sub.add_parser("plan", help="Generate execution plan only")
    plan_cmd.add_argument("prompt", help="User request")

    sub.add_parser("init", help="Create a default harness.toml")

    sub.add_parser("verify", help="Check inference endpoint health")

    sub.add_parser("info", help="Show supported languages and configuration")

    return parser


def _setup_logging(config: HarnessConfig, verbose: bool) -> None:
    raw_level = config.logging.level.upper()
    level = logging.DEBUG if verbose else getattr(logging, raw_level, logging.INFO)
    fmt = "%(levelname)s %(name)s: %(message)s"
    if config.logging.format == "json":
        fmt = '{"level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}'
    logging.basicConfig(level=level, format=fmt, force=True)


def _make_client(config: HarnessConfig) -> InferenceClient:
    return InferenceClient.from_config(config)


def _render_plan_table(tasks: list[Task]) -> Table:
    table = Table(title="Execution Plan", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("Description")
    table.add_column("Deps")
    table.add_column("Agent")
    for t in tasks:
        table.add_row(
            t.id, t.description, ", ".join(t.dependencies) or "-", t.assigned_agent
        )
    return table


def _render_result(result: OrchestratorResult) -> None:
    console.print(_render_plan_table(result.plan.tasks))

    table = Table(title="Execution Results", show_lines=True)
    table.add_column("Task ID", style="cyan")
    table.add_column("Status")
    table.add_column("Commit")

    for tr in result.results:
        style = "green" if tr.task.status == TaskStatus.COMPLETED else "red"
        table.add_row(
            tr.task.id,
            Text(tr.task.status.value, style=style),
            tr.commit_sha[:8] if tr.commit_sha else "-",
        )

    console.print(table)
    console.print(Panel(f"[bold]{result.summary()}[/bold]"))

    failed = [r for r in result.results if r.task.status == TaskStatus.FAILED]
    for f in failed:
        if f.verification and f.verification.failures:
            console.print(
                Panel(
                    "\n".join(f.verification.failures),
                    title=f"[red]Failures: {f.task.id}[/red]",
                )
            )


class _LiveDisplay:
    """Live-updating TUI during orchestration."""

    def __init__(self):
        self._live: Live | None = None
        self._current_task: str = ""
        self._completed: list[tuple[str, str]] = []

    def start(self) -> None:
        self._live = Live(self._build(), console=console, refresh_per_second=4)
        self._live.start()

    def stop(self) -> None:
        if self._live:
            self._live.stop()

    def on_task_start(self, task: Task) -> None:
        self._current_task = f"{task.id}: {task.description}"
        self._update()

    def on_task_end(self, tr: TaskResult) -> None:
        status = tr.task.status.value
        self._completed.append((tr.task.id, status))
        self._current_task = ""
        self._update()

    def _update(self) -> None:
        if self._live:
            self._live.update(self._build())

    def _build(self) -> Panel:
        lines: list[str] = []
        for tid, status in self._completed:
            marker = "[green]OK[/green]" if status == "completed" else "[red]FAIL[/red]"
            lines.append(f"  {marker}  {tid}")
        if self._current_task:
            lines.append(f"  [yellow]>>>[/yellow]  {self._current_task}")
        body = "\n".join(lines) if lines else "  Waiting..."
        return Panel(body, title="[bold]CIV Pipeline[/bold]", border_style="blue")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _cmd_init(args: argparse.Namespace) -> None:
    path = Path(args.config) if hasattr(args, "config") else Path("harness.toml")
    if path.exists():
        console.print(f"[yellow]{path} already exists.[/yellow]")
        return
    path.write_text(default_toml())
    console.print(f"[green]Created {path}[/green]")


def _cmd_info(config: HarnessConfig) -> None:
    from .tools import supported_languages

    table = Table(title="Harness Info", show_lines=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    table.add_row("Version", __version__)
    table.add_row("Model", config.inference.model)
    table.add_row("Endpoint", config.inference.base_url)
    table.add_row("Max retries", str(config.inference.max_retries))
    table.add_row("Bash timeout", f"{config.tools.bash_timeout}s")
    table.add_row("Path restriction", str(config.security.restrict_paths))
    table.add_row("AST languages", ", ".join(supported_languages()) or "none")
    console.print(table)


def _cmd_verify(config: HarnessConfig) -> None:
    client = _make_client(config)
    console.print("Checking inference endpoint...", end=" ")
    if client.health_check():
        console.print("[green]OK[/green]")
    else:
        console.print("[red]UNREACHABLE[/red]")
        sys.exit(1)


def _cmd_plan(config: HarnessConfig, prompt: str) -> None:
    from .agents import Coordinator

    client = _make_client(config)
    coordinator = Coordinator(client)
    plan = coordinator.plan(prompt)
    console.print(_render_plan_table(plan.tasks))


def _cmd_run(config: HarnessConfig, repo: str, prompt: str) -> None:
    client = _make_client(config)
    orch = Orchestrator(client, repo, config=config)

    display = _LiveDisplay()
    orch.on_task_start(display.on_task_start)
    orch.on_task_end(display.on_task_end)

    display.start()
    try:
        result = orch.run(prompt)
    finally:
        display.stop()

    _render_result(result)
    sys.exit(0 if result.all_passed else 1)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    config = load_config(args.config)
    _setup_logging(config, args.verbose)

    if args.command == "init":
        _cmd_init(args)
    elif args.command == "info":
        _cmd_info(config)
    elif args.command == "verify":
        _cmd_verify(config)
    elif args.command == "plan":
        _cmd_plan(config, args.prompt)
    elif args.command == "run":
        _cmd_run(config, args.repo, args.prompt)
