"""TLA+ formal verification bridge.

Generates TLA+ specifications from task descriptions and CIVMessage flows,
runs the TLC model checker (with graceful fallback when TLA+ tools are not
installed), and provides a verification gate compatible with the Verifier agent.

References:
  Engineering_Intent_Framework.md Section 4:
  "TLA+ formal verification, or modality shifts like code-to-test execution"
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class TLCResult:
    """Outcome of a TLC model-checking run."""

    passed: bool
    """True when all invariants and temporal properties hold within the
    configured model bounds."""

    counterexample: str | None = None
    """Human-readable trace showing the state sequence that violated an
    invariant, or None when the check passes."""

    stats: dict[str, Any] = field(default_factory=dict)
    """Arbitrary statistics collected during the run (diameter, states
    checked, distinct states, etc.)."""

    raw_output: str = ""
    """Unprocessed stdout+stderr from the TLC process."""

    error: str | None = None
    """Exception message when TLC could not be invoked at all."""


@dataclass
class StaticAnalysisResult:
    """Result of the built-in static fallback analysis."""

    passed: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# TLA+ specification generator
# ---------------------------------------------------------------------------


class TLASpecGenerator:
    """Converts a task description and CIV message flow into a TLA+ spec.

    The generated specification models the lifecycle of tasks in the
    Coordinator-Implementor-Verifier pipeline as a state machine, making
    it possible to model-check safety and liveness properties.

    Usage::

        gen = TLASpecGenerator()
        spec = gen.generate_spec(
            task_description="Refactor auth module",
            state_machine=civ_messages,
        )
        print(spec)
    """

    #: Default constants injected into every generated spec.
    DEFAULT_CONSTANTS: dict[str, Any] = {
        "MaxTaskCount": 10,
        "MaxRetries": 3,
    }

    def __init__(
        self,
        module_name: str = "CIVPipeline",
        max_tasks: int = 10,
    ) -> None:
        self._module_name = module_name
        self._max_tasks = max_tasks

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_spec(
        self,
        task_description: str,
        state_machine: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate a complete TLA+ specification.

        Args:
            task_description: Human-readable summary of the orchestration
                request (becomes the module doc comment).
            state_machine: Optional list of CIVMessage dicts representing
                the message flow (sender/recipient/phase/payload).  When
                omitted the spec still defines the full state space so that
                the invariants can be checked on any reachable state.

        Returns:
            The full TLA+ source as a single string, suitable for writing
            to a ``.tla`` file.
        """
        lines: list[str] = []

        # Module header
        lines.append(_module_header(self._module_name, task_description))
        lines.append("")

        # Extra modules
        lines.append("EXTENDS Naturals, Sequences, FiniteSets, TLC")
        lines.append("")

        # Constants
        lines.extend(_constants_block(self.DEFAULT_CONSTANTS))
        lines.append("")

        # Task set
        lines.extend(_task_set_block("Tasks", self._max_tasks))
        lines.append("")

        # Variables
        lines.extend(_variables_block())
        lines.append("")

        # Type invariant (TypeOK)
        lines.extend(_type_ok_block())
        lines.append("")

        # Init
        lines.extend(_init_block())
        lines.append("")

        # Transitions / Next
        lines.extend(_next_block(state_machine))
        lines.append("")

        # Spec
        lines.extend(_spec_block())
        lines.append("")

        # Safety invariants
        lines.extend(_safety_block())
        lines.append("")

        # Liveness / temporal properties
        lines.extend(_temporal_block())
        lines.append("")

        # Separator
        lines.append("====")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Shortcut helpers
    # ------------------------------------------------------------------

    def generate_config(self, spec_file_stem: str = "CIVPipeline") -> str:
        """Return a minimal TLC configuration file (``.cfg``)."""
        return _default_cfg(spec_file_stem)


# ---------------------------------------------------------------------------
# TLC model checker runner
# ---------------------------------------------------------------------------


class TLCChecker:
    """Runs the TLC model checker on a generated TLA+ specification.

    Uses ``java -jar tla2tools.jar`` when a TLA+ distribution is found on
    the system.  Otherwise falls back to a lightweight static analysis that
    validates the structure of the spec without exhaustively exploring the
    state space.

    Usage::

        checker = TLCChecker()
        result = checker.check(spec_text)
        if result.passed:
            print("All invariants hold!")
        else:
            print("Counterexample:", result.counterexample)
    """

    # Common locations where the TLA+ tools jar may be found.
    _KNOWN_JAR_PATHS: tuple[str, ...] = (
        "tla2tools.jar",
        "/usr/local/lib/tla2tools.jar",
        "/opt/tla/tla2tools.jar",
        str(Path.home() / ".local/share/tla/tla2tools.jar"),
        str(Path.home() / "tla/tla2tools.jar"),
    )

    def __init__(
        self,
        *,
        java_bin: str = "java",
        tla_jar: str | Path | None = None,
        heap_mb: int = 1024,
        timeout_seconds: int = 120,
    ) -> None:
        """Configure the TLC runner.

        Args:
            java_bin: Path or name of the ``java`` executable.
            tla_jar: Explicit path to ``tla2tools.jar``.  When *None* the
                checker probes the known locations listed above.
            heap_mb: Maximum Java heap in MiB (``-Xmx``).
            timeout_seconds: Wall-clock limit for the TLC subprocess.
        """
        self._java = java_bin
        self._jar: Path | None = None
        self._heap_mb = heap_mb
        self._timeout = timeout_seconds

        if tla_jar:
            candidate = Path(tla_jar)
            if candidate.exists():
                self._jar = candidate
            else:
                logger.warning("TLA+ jar not found at %s — will use static fallback", tla_jar)
        else:
            self._jar = self._find_jar()

        self._tla_available = self._jar is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        spec_text: str,
        config_overrides: dict[str, Any] | None = None,
        *,
        cleanup: bool = True,
    ) -> TLCResult:
        """Run TLC on *spec_text*.

        Args:
            spec_text: Full TLA+ source (as returned by
                :meth:`TLASpecGenerator.generate_spec`).
            config_overrides: Optional dict merged into the default
                ``.cfg`` (e.g. ``{"SPECIFICATION": "Spec", "INVARIANT":
                "TypeOK"}``).
            cleanup: When *True* (default) the temporary working directory
                is removed after the run.

        Returns:
            A :class:`TLCResult` summarising the outcome.
        """
        if not self._tla_available:
            logger.info("TLA+ tools not installed — running static analysis fallback")
            return self._static_check(spec_text)

        work_dir = Path(tempfile.mkdtemp(prefix="tla_check_"))
        try:
            return self._run_tlc(spec_text, config_overrides, work_dir)
        finally:
            if cleanup:
                try:
                    shutil.rmtree(work_dir)
                except OSError:
                    pass

    def is_available(self) -> bool:
        """Return *True* when TLC can be invoked natively."""
        return self._tla_available

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @classmethod
    def _find_jar(cls) -> Path | None:
        """Search known locations for ``tla2tools.jar``."""
        for candidate in cls._KNOWN_JAR_PATHS:
            if Path(candidate).exists():
                logger.debug("Found tla2tools.jar at %s", candidate)
                return Path(candidate)
        return None

    def _run_tlc(
        self,
        spec_text: str,
        config_overrides: dict[str, Any] | None,
        work_dir: Path,
    ) -> TLCResult:
        """Write files, invoke TLC, and parse the output."""

        module_name = _extract_module_name(spec_text) or "CIVPipeline"

        # Write .tla
        tla_path = work_dir / f"{module_name}.tla"
        tla_path.write_text(spec_text)

        # Write .cfg
        cfg_path = work_dir / f"{module_name}.cfg"
        cfg_content = _build_cfg(module_name, config_overrides)
        cfg_path.write_text(cfg_content)

        # Build command
        assert self._jar is not None  # guarded by _tla_available
        cmd = [
            self._java,
            f"-Xmx{self._heap_mb}m",
            "-cp",
            str(self._jar),
            "tlc2.TLC",
            str(tla_path),
            "-config",
            str(cfg_path),
            "-workers",
            "auto",
        ]

        logger.debug("Running TLC: %s", " ".join(cmd))

        try:
            proc = subprocess.run(  # noqa: S603
                cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            raw = proc.stdout + "\n" + proc.stderr
            passed, counterexample = _parse_tlc_output(raw)

            return TLCResult(
                passed=passed,
                counterexample=counterexample,
                stats=_extract_tlc_stats(raw),
                raw_output=raw,
            )
        except subprocess.TimeoutExpired:
            return TLCResult(
                passed=False,
                error=f"TLC timed out after {self._timeout}s",
                raw_output="",
            )
        except FileNotFoundError:
            return TLCResult(
                passed=False,
                error=f"Java executable '{self._java}' not found",
                raw_output="",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("TLC run failed unexpectedly")
            return TLCResult(
                passed=False,
                error=str(exc),
                raw_output="",
            )

    def _static_check(self, spec_text: str) -> TLCResult:
        """Lightweight offline analysis when TLC is unavailable."""
        result = _static_analyze(spec_text)

        stats = {
            "mode": "static_fallback",
            "warnings_count": len(result.warnings),
            "errors_count": len(result.errors),
        }

        if not result.passed:
            return TLCResult(
                passed=False,
                counterexample="\n".join(result.errors + result.warnings),
                stats=stats,
                error="TLC not available — static analysis found issues",
            )

        return TLCResult(
            passed=True,
            stats=stats,
        )


# ---------------------------------------------------------------------------
# Verification gate (Verifier integration)
# ---------------------------------------------------------------------------


class TLAVerificationGate:
    """Bridge between the TLA+ tooling and the Verifier agent.

    Generates a spec from a task, runs TLC (or the static fallback), and
    returns a verdict dict that matches the shape expected by
    :class:`no_slop_harness.agents.verifier.VerifierAgent.verify`.

    Usage::

        gate = TLAVerificationGate()
        verdict = gate.verify(task, spec_text=existing_spec)
        if not verdict["passed"]:
            print(verdict["detail"])
    """

    def __init__(
        self,
        checker: TLCChecker | None = None,
        generator: TLASpecGenerator | None = None,
    ) -> None:
        self._checker = checker or TLCChecker()
        self._generator = generator or TLASpecGenerator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(
        self,
        task: Any,  # Task-like: accepts anything with .description (or a str)
        spec_text: str | None = None,
        state_machine: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Verify a task via TLA+ model checking.

        Args:
            task: A ``Task`` (or any object with a ``.description`` str
                attribute), or a plain string used as the description.
            spec_text: Pre-generated TLA+ spec.  When *None* a new spec is
                generated from *task* and *state_machine*.
            state_machine: Optional CIV message flow used when generating
                the spec.

        Returns:
            A verdict dict compatible with ``VerifierAgent.verify``::

                {
                  "passed": bool,
                  "detail": str,
                  "tla_passed": bool,
                  "tla_counterexample": str | None,
                  "tla_stats": dict,
                  "tla_available": bool,
                  "static_fallback": bool,
                }
        """
        description = _task_description(task)

        # Generate spec if not provided
        if spec_text is None:
            spec_text = self._generator.generate_spec(description, state_machine)

        # Run TLC
        result = self._checker.check(spec_text)

        # Build Verifier-compatible verdict
        tla_passed = result.passed and result.error is None
        static = result.stats.get("mode") == "static_fallback"

        # Note: we distinguish "TLC check passed" from the overall verdict.
        # The overall "passed" key reflects TLC success; the Verifier can
        # still fail the task for separate reasons (tests, lint, etc.)
        verdict: dict[str, Any] = {
            "passed": tla_passed,
            "detail": _build_verdict_detail(result),
            "tla_passed": tla_passed,
            "tla_counterexample": result.counterexample,
            "tla_stats": result.stats,
            "tla_available": self._checker.is_available(),
            "static_fallback": static,
        }

        if not tla_passed and result.error:
            verdict["detail"] += f" (error: {result.error})"

        logger.info(
            "TLAVerificationGate verdict: %s (tlc=%s, static=%s)",
            "PASS" if tla_passed else "FAIL",
            tla_passed,
            static,
        )
        return verdict


# ====================================================================
# Internal helpers — TLA+ code generation
# ====================================================================


def _module_header(name: str, description: str) -> str:
    """Return the TLA+ module header block."""
    desc = description.replace("\n", " ").strip()
    return (
        f"---------------------------- MODULE {name} ----------------------------\n"
        f"\\* {desc}\n"
        f"\\* Auto-generated by no-slop-harness TLA+ bridge\n"
        f"\\* Generated: {datetime.now(UTC).isoformat()}"
    )


def _constants_block(constants: dict[str, Any]) -> list[str]:
    """Return CONSTANTS declarations."""
    lines: list[str] = ["\\* Model constants", "CONSTANTS"]
    for name in constants:
        lines.append(f"    {name},")
    # Remove trailing comma from last entry
    if len(constants) > 0:
        lines[-1] = lines[-1].rstrip(",")
    lines.append("")
    lines.append("ASSUME (MaxTaskCount \\in Nat) /\\ (MaxTaskCount >= 1)")
    lines.append("ASSUME (MaxRetries \\in Nat)  /\\ (MaxRetries  >= 1)")
    return lines


def _task_set_block(name: str, count: int) -> list[str]:
    """Define the finite set of task identifiers."""
    return [
        "\\* Finite set of task identifiers",
        f"{name} == 1 .. {count}",
        "",
        "\\* Task states that the pipeline recognises",
        'Pending   == "pending"',
        'Assigned  == "assigned"',
        'Running   == "in_progress"',
        'Verifying == "verifying"',
        'Completed == "completed"',
        'Failed    == "failed"',
        'RolledBack == "rolled_back"',
        "",
        "TaskStates == {Pending, Assigned, Running, Verifying, Completed, Failed, RolledBack}",
    ]


def _variables_block() -> list[str]:
    """Return the VARIABLES declaration block."""
    return [
        "\\* State variables",
        "VARIABLES",
        "    task_state,      \\* Tasks -> TaskStates",
        "    task_deps,       \\* Tasks -> SUBSET Tasks  (immediate predecessors)",
        "    executions,      \\* Tasks -> Nat  (count of executions, for dedup)",
        "    blocked,         \\* BOOLEAN: True iff there exists a deadlocked task",
        "    completed_tasks, \\* SUBSET Tasks that have reached Completed",
        "    failed_tasks,    \\* SUBSET Tasks that have reached Failed",
    ]


def _type_ok_block() -> list[str]:
    """Return the TypeOK invariant."""
    return [
        "\\* Type invariant — every reachable state must satisfy this.",
        "TypeOK ==",
        "    /\\ task_state      \\in [Tasks -> TaskStates]",
        "    /\\ task_deps       \\in [Tasks -> SUBSET Tasks]",
        "    /\\ executions      \\in [Tasks -> Nat]",
        "    /\\ blocked         \\in BOOLEAN",
        "    /\\ completed_tasks \\subseteq Tasks",
        "    /\\ failed_tasks    \\subseteq Tasks",
    ]


def _init_block() -> list[str]:
    """Return the Init predicate."""
    return [
        "\\* Initial state: every task is Pending, no dependencies satisfied,",
        "\\* no executions, no blocked flag, empty final-sets.",
        "Init ==",
        "    /\\ task_state      = [t \\in Tasks |-> Pending]",
        "    /\\ task_deps       = [t \\in Tasks |-> {}]",
        "    /\\ executions      = [t \\in Tasks |-> 0]",
        "    /\\ blocked         = FALSE",
        "    /\\ completed_tasks = {}",
        "    /\\ failed_tasks    = {}",
    ]


def _next_block(state_machine: list[dict[str, Any]] | None) -> list[str]:
    """Build the Next action, incorporating CIV message flow if provided.

    The state machine transitions are:

    1. **Assign**    — Pending → Assigned
    2. **Start**     — Assigned → Running   (dependencies satisfied)
    3. **Verify**    — Running → Verifying
    4. **Complete**  — Verifying → Completed
    5. **Fail**      — any active → Failed
    6. **Retry**     — Failed → Pending     (< MaxRetries)
    7. **RollBack**  — Failed → RolledBack
    8. **Stutter**   — UNCHANGED vars
    """
    lines: list[str] = []

    lines.append("\\* Next-state relation — the union of all allowed transitions.")
    lines.append("")

    # Assign
    lines.append("Assign(t) ==")
    lines.append("    /\\ task_state[t] = Pending")
    lines.append("    /\\ task_state' = [task_state EXCEPT ![t] = Assigned]")
    lines.append(
        "    /\\ UNCHANGED <<task_deps, executions, blocked, completed_tasks, failed_tasks>>"
    )  # noqa: E501
    lines.append("")

    # Start (only when dependencies are satisfied)
    lines.append("\\* A task can start when all its dependencies are completed.")
    lines.append("Start(t) ==")
    lines.append("    /\\ task_state[t] = Assigned")
    lines.append("    /\\ task_deps[t] \\subseteq completed_tasks   \\* DependencyRespect")
    lines.append(
        "    /\\ executions[t] = 0                            \\* NoDuplicateExecution guard"
    )  # noqa: E501
    lines.append("    /\\ task_state' = [task_state EXCEPT ![t] = Running]")
    lines.append("    /\\ executions' = [executions EXCEPT ![t] = executions[t] + 1]")
    lines.append("    /\\ UNCHANGED <<task_deps, blocked, completed_tasks, failed_tasks>>")
    lines.append("")

    # Verify
    lines.append("Verify(t) ==")
    lines.append("    /\\ task_state[t] = Running")
    lines.append("    /\\ task_state' = [task_state EXCEPT ![t] = Verifying]")
    lines.append(
        "    /\\ UNCHANGED <<task_deps, executions, blocked, completed_tasks, failed_tasks>>"
    )  # noqa: E501
    lines.append("")

    # Complete
    lines.append("Complete(t) ==")
    lines.append("    /\\ task_state[t] = Verifying")
    lines.append("    /\\ task_state' = [task_state EXCEPT ![t] = Completed]")
    lines.append("    /\\ completed_tasks' = completed_tasks \\union {t}")
    lines.append("    /\\ UNCHANGED <<task_deps, executions, blocked, failed_tasks>>")
    lines.append("")

    # Fail
    lines.append("Fail(t) ==")
    lines.append("    /\\ task_state[t] \\in {Assigned, Running, Verifying}")
    lines.append("    /\\ task_state' = [task_state EXCEPT ![t] = Failed]")
    lines.append("    /\\ failed_tasks' = failed_tasks \\union {t}")
    lines.append("    /\\ UNCHANGED <<task_deps, executions, blocked, completed_tasks>>")
    lines.append("")

    # Retry
    lines.append("Retry(t) ==")
    lines.append("    /\\ task_state[t] = Failed")
    lines.append("    /\\ executions[t] < MaxRetries")
    lines.append("    /\\ task_state' = [task_state EXCEPT ![t] = Pending]")
    lines.append("    /\\ failed_tasks' = failed_tasks \\ {t}")
    lines.append("    /\\ UNCHANGED <<task_deps, executions, blocked, completed_tasks>>")
    lines.append("")

    # RollBack
    lines.append("RollBack(t) ==")
    lines.append("    /\\ task_state[t] = Failed")
    lines.append("    /\\ executions[t] >= MaxRetries")
    lines.append("    /\\ task_state' = [task_state EXCEPT ![t] = RolledBack]")
    lines.append(
        "    /\\ UNCHANGED <<task_deps, executions, blocked, completed_tasks, failed_tasks>>"
    )  # noqa: E501
    lines.append("")

    # Deadlock detection
    lines.append("\\* A task is deadlocked when it is Assigned but its dependencies")
    lines.append("\\* will never be satisfied (some dependency is Failed).")
    lines.append("Deadlocked(t) ==")
    lines.append("    /\\ task_state[t] = Assigned")
    lines.append("    /\\ \\E d \\in task_deps[t] : task_state[d] \\in {Failed, RolledBack}")
    lines.append("")
    lines.append("SetBlocked ==")
    lines.append("    /\\ \\E t \\in Tasks : Deadlocked(t)")
    lines.append("    /\\ blocked' = TRUE")
    lines.append(
        "    /\\ UNCHANGED <<task_state, task_deps, executions, completed_tasks, failed_tasks>>"
    )  # noqa: E501
    lines.append("")

    # Next
    lines.append("\\* The complete next-state relation.")
    lines.append("Next ==")
    lines.append("    \\/ \\E t \\in Tasks : Assign(t)")
    lines.append("    \\/ \\E t \\in Tasks : Start(t)")
    lines.append("    \\/ \\E t \\in Tasks : Verify(t)")
    lines.append("    \\/ \\E t \\in Tasks : Complete(t)")
    lines.append("    \\/ \\E t \\in Tasks : Fail(t)")
    lines.append("    \\/ \\E t \\in Tasks : Retry(t)")
    lines.append("    \\/ \\E t \\in Tasks : RollBack(t)")
    lines.append("    \\/ SetBlocked")
    lines.append("    \\/ UNCHANGED vars")

    return lines


def _spec_block() -> list[str]:
    """Return the Spec definition."""
    return [
        "\\* Full specification: initial state + next-state relation.",
        "Spec == Init /\\ [][Next]_vars",
    ]


def _safety_block() -> list[str]:
    """Build the safety invariants: TypeOK, NoDeadlock, NoDuplicateExecution,
    DependencyRespect."""
    return [
        "========================================================================",
        "\\* Safety invariants",
        "========================================================================",
        "",
        "\\* NoDeadlock: there is never a state where *all* tasks are blocked.",
        "\\* (A single deadlocked task sets the blocked flag; see SetBlocked.)",
        "NoDeadlock ==",
        "    blocked = FALSE",
        "",
        "\\* NoDuplicateExecution: each task runs at most once.",
        "NoDuplicateExecution ==",
        "    \\A t \\in Tasks : executions[t] <= 1",
        "",
        "\\* DependencyRespect: a non-Pending, non-Failed task only exists",
        "\\* if all its dependencies are completed.",
        "DependencyRespect ==",
        "    \\A t \\in Tasks :",
        "        task_state[t] \\notin {Pending, Failed, RolledBack}",
        "        => task_deps[t] \\subseteq completed_tasks",
    ]


def _temporal_block() -> list[str]:
    """Build temporal (liveness) properties."""
    return [
        "========================================================================",
        "\\* Temporal properties (liveness)",
        "========================================================================",
        "",
        "\\* TerminationGuarantee: every task eventually reaches Completed or Failed.",
        "\\* This is a weak-fairness property — if a task is continuously enabled",
        "\\* it must eventually be taken.",
        "TerminationGuarantee ==",
        "    \\A t \\in Tasks : <>(task_state[t] \\in {Completed, Failed, RolledBack})",
        "",
        "\\* EventualCompletion: under the assumption that tasks don't fail,",
        "\\* every task will complete.",
        "EventualCompletion ==",
        "    completed_tasks = Tasks ~> (\\A t \\in Tasks : task_state[t] = Completed)",
    ]


# ====================================================================
# Internal helpers — TLC configuration
# ====================================================================


def _default_cfg(spec_stem: str) -> str:
    """Return a minimal TLC configuration file."""
    return (
        "SPECIFICATION\n"
        "    Spec\n"
        "\n"
        "CONSTANTS\n"
        "    MaxTaskCount = 10\n"
        "    MaxRetries   = 3\n"
        "\n"
        "INVARIANT\n"
        "    TypeOK\n"
        "    NoDeadlock\n"
        "    NoDuplicateExecution\n"
        "    DependencyRespect\n"
        "\n"
        "PROPERTIES\n"
        "    TerminationGuarantee\n"
        "\n"
        "CHECK_DEADLOCK\n"
        "    TRUE\n"
    )


def _build_cfg(module_name: str, overrides: dict[str, Any] | None) -> str:
    """Build a ``.cfg`` string, merging overrides on top of defaults."""
    cfg = {
        "SPECIFICATION": "Spec",
        "CONSTANTS": {"MaxTaskCount": 10, "MaxRetries": 3},
        "INVARIANTS": [
            "TypeOK",
            "NoDeadlock",
            "NoDuplicateExecution",
            "DependencyRespect",
        ],
        "PROPERTIES": ["TerminationGuarantee"],
        "CHECK_DEADLOCK": "TRUE",
    }
    if overrides:
        cfg.update(overrides)

    lines: list[str] = []

    lines.append("SPECIFICATION")
    lines.append(f"    {cfg['SPECIFICATION']}")
    lines.append("")

    if "CONSTANTS" in cfg:
        lines.append("CONSTANTS")
        consts = cfg["CONSTANTS"]
        if isinstance(consts, dict):
            for k, v in consts.items():
                lines.append(f"    {k} = {_format_tla_value(v)}")
        lines.append("")

    if "INVARIANTS" in cfg:
        lines.append("INVARIANTS")
        for inv in cfg["INVARIANTS"]:
            lines.append(f"    {inv}")
        lines.append("")

    if "PROPERTIES" in cfg:
        lines.append("PROPERTIES")
        for prop in cfg["PROPERTIES"]:
            lines.append(f"    {prop}")
        lines.append("")

    if "CHECK_DEADLOCK" in cfg:
        lines.append("CHECK_DEADLOCK")
        lines.append(f"    {cfg['CHECK_DEADLOCK']}")
        lines.append("")

    return "\n".join(lines)


def _format_tla_value(value: Any) -> str:
    """Format a Python value as a TLA+ literal."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, str):
        # Wrap strings in double quotes for TLA+
        return f'"{value}"'
    if isinstance(value, int):
        return str(value)
    return str(value)


# ====================================================================
# Internal helpers — parsing & static analysis
# ====================================================================


def _extract_module_name(spec_text: str) -> str | None:
    """Extract the MODULE name from a TLA+ spec."""
    for line in spec_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("---- MODULE ") and stripped.endswith(" ----"):
            return stripped[len("---- MODULE ") : -len(" ----")].strip()
    return None


def _parse_tlc_output(raw: str) -> tuple[bool, str | None]:
    """Parse TLC's stdout/stderr to determine pass/fail and extract a
    counterexample when available.

    The heuristic looks for:
    - ``Model checking completed. No error has been found.`` → passed
    - ``Error: Invariant ... is violated.`` → failed + counterexample
    """
    passed = "No error has been found" in raw or (
        "Model checking completed" in raw and "Error" not in raw
    )

    counterexample: str | None = None

    if not passed:
        # Try to extract the counterexample trace
        lines = raw.splitlines()
        capture = False
        trace_lines: list[str] = []
        for line in lines:
            if "Invariant" in line and "is violated" in line:
                capture = True
                trace_lines.append(line)
                continue
            if capture:
                if line.strip().startswith("State ") or "(" in line:
                    trace_lines.append(line)
                elif trace_lines and line.strip() == "":
                    # Stop at first blank line after trace
                    if len(trace_lines) > 3:
                        break
                    trace_lines.append(line)
                elif trace_lines:
                    trace_lines.append(line)
        if trace_lines:
            counterexample = "\n".join(trace_lines[:80])  # cap at 80 lines
        else:
            counterexample = raw[:4000]  # fallback: first 4k chars

    return passed, counterexample


def _extract_tlc_stats(raw: str) -> dict[str, Any]:
    """Pull statistics from TLC output."""
    stats: dict[str, Any] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if "distinct states" in stripped.lower():
            try:
                stats["distinct_states"] = int(stripped.split(":")[-1].strip())
            except ValueError:
                stats["distinct_states"] = stripped.split(":")[-1].strip()
        elif "states generated" in stripped.lower():
            try:
                stats["states_generated"] = int(stripped.split(":")[-1].strip())
            except ValueError:
                stats["states_generated"] = stripped.split(":")[-1].strip()
        elif "state space diameter" in stripped.lower():
            try:
                stats["diameter"] = int(stripped.split(":")[-1].strip())
            except ValueError:
                stats["diameter"] = stripped.split(":")[-1].strip()
        elif "the coverage is" in stripped.lower():
            stats["coverage"] = stripped.split(":")[-1].strip()
    return stats


def _static_analyze(spec_text: str) -> StaticAnalysisResult:
    """Lightweight structural validation of a TLA+ spec.

    Checks for:
    - Module header
    - Required keywords (EXTENDS, VARIABLES, Init, Next, Spec)
    - Each invariant/property keyword presence
    - Matching ``====`` terminator
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Module header
    if not any("MODULE" in line for line in spec_text.splitlines()[:3]):
        errors.append("Missing MODULE header")

    # Required keywords
    required = ["EXTENDS", "VARIABLES", "Init ==", "Next ==", "Spec =="]
    for kw in required:
        if kw not in spec_text:
            errors.append(f"Missing required keyword: {kw}")

    # Terminator
    if "====" not in spec_text:
        warnings.append("Missing '====' module terminator")

    # Invariant presence
    invariants = ["NoDeadlock", "NoDuplicateExecution", "DependencyRespect"]
    for inv in invariants:
        if inv not in spec_text:
            warnings.append(f"Invariant '{inv}' not found in spec")

    # Temporal properties
    if "TerminationGuarantee" not in spec_text:
        warnings.append("Temporal property 'TerminationGuarantee' not found")

    # Look for obvious syntax issues
    lines = spec_text.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Unbalanced /\ or \/ at line start with no content
        if stripped in ("/\\", "\\/"):
            warnings.append(f"Line {i}: potentially empty conjunction/disjunction")

    return StaticAnalysisResult(
        passed=len(errors) == 0,
        warnings=warnings,
        errors=errors,
    )


def _task_description(task: Any) -> str:
    """Extract a description string from various task representations."""
    if isinstance(task, str):
        return task
    if hasattr(task, "description"):
        return str(task.description)
    return str(task)


def _build_verdict_detail(result: TLCResult) -> str:
    """Construct a human-readable detail string for the Verifier verdict."""
    if result.passed and result.error is None:
        mode = result.stats.get("mode", "tlc")
        if mode == "static_fallback":
            return "TLA+ static analysis passed (TLC not available — limited checking)."
        states = result.stats.get("distinct_states", "?")
        return f"TLC model check passed ({states} distinct states explored)."

    if result.error:
        return f"TLA+ verification error: {result.error}"

    if result.counterexample:
        # Truncate for the verdict detail field
        ce = result.counterexample[:500]
        return f"TLA+ invariant violation found. Counterexample: {ce}"

    return "TLA+ model check failed for unknown reason."
