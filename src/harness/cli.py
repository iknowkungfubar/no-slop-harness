"""CLI entry point for the harness."""

from __future__ import annotations

import argparse
import logging
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .client import InferenceClient
from .orchestrator import Orchestrator, OrchestratorResult
from .schemas import TaskStatus

console = Console()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness",
        description="Minimalist Agentic Harness — CIV Pattern",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000/v1",
        help="OpenAI-compatible inference endpoint (default: %(default)s)",
    )
    parser.add_argument("--model", default="default", help="Model identifier")
    parser.add_argument("--api-key", default="not-needed", help="API key")
    parser.add_argument("--repo", default=".", help="Repository path")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Execute full CIV pipeline")
    run_cmd.add_argument("prompt", help="User request")

    plan_cmd = sub.add_parser("plan", help="Generate execution plan only")
    plan_cmd.add_argument("prompt", help="User request")

    return parser


def _render_plan(result: OrchestratorResult) -> None:
    table = Table(title="Execution Plan", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("Description")
    table.add_column("Deps")
    table.add_column("Agent")
    for t in result.plan.tasks:
        table.add_row(
            t.id, t.description, ", ".join(t.dependencies) or "-", t.assigned_agent
        )
    console.print(table)


def _render_result(result: OrchestratorResult) -> None:
    _render_plan(result)

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

    if result.all_passed:
        console.print(Panel("[green]All tasks completed.[/green]"))
    else:
        failed = [r for r in result.results if r.task.status == TaskStatus.FAILED]
        for f in failed:
            if f.verification and f.verification.failures:
                console.print(
                    Panel(
                        "\n".join(f.verification.failures),
                        title=f"[red]Failures: {f.task.id}[/red]",
                    )
                )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    client = InferenceClient(
        base_url=args.base_url, api_key=args.api_key, model=args.model
    )

    if args.command == "plan":
        from .agents import Coordinator

        coordinator = Coordinator(client)
        plan = coordinator.plan(args.prompt)
        table = Table(title="Execution Plan", show_lines=True)
        table.add_column("ID", style="cyan")
        table.add_column("Description")
        table.add_column("Deps")
        table.add_column("Agent")
        for t in plan.tasks:
            table.add_row(
                t.id,
                t.description,
                ", ".join(t.dependencies) or "-",
                t.assigned_agent,
            )
        console.print(table)

    elif args.command == "run":
        orch = Orchestrator(client, args.repo)
        result = orch.run(args.prompt)
        _render_result(result)

    sys.exit(0)
