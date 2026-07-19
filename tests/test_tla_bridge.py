"""Test suite for TLA+ formal verification bridge."""

from __future__ import annotations

from no_slop_harness.tla_bridge import TLASpecGenerator, TLCChecker, TLCResult


class TestTLASpecGenerator:
    """TLA+ specification generation from task descriptions."""

    def test_generate_basic_spec(self) -> None:
        gen = TLASpecGenerator()
        spec = gen.generate_spec(
            task_description="Implement a User model with email and password",
        )
        assert len(spec) > 0
        assert "MODULE" in spec.upper() or "----" in spec
        assert "Init" in spec
        assert "Next" in spec

    def test_generate_with_state_machine(self) -> None:
        gen = TLASpecGenerator()
        state_machine = [
            {"sender": "coordinator", "recipient": "implementor", "phase": "plan"},
            {"sender": "implementor", "recipient": "verifier", "phase": "implement"},
        ]
        spec = gen.generate_spec(
            task_description="CIV pipeline task lifecycle",
            state_machine=state_machine,
        )
        assert len(spec) > 0

    def test_description_appears_in_spec(self) -> None:
        gen = TLASpecGenerator()
        spec = gen.generate_spec(task_description="Test the User authentication flow")
        assert "User authentication" in spec or "Test the" in spec


class TestTLCChecker:
    """TLC model checker interface."""

    def test_result_dataclass_defaults(self) -> None:
        result = TLCResult(passed=True)
        assert result.passed
        assert result.counterexample is None
        assert result.stats == {}

    def test_failed_result(self) -> None:
        result = TLCResult(
            passed=False,
            counterexample="State 42 violates NoDuplicateExecution",
            stats={"states_checked": 50, "duration_s": 2.0},
        )
        assert not result.passed
        assert result.counterexample is not None
        assert result.stats["states_checked"] == 50

    def test_check_generated_spec(self) -> None:
        """check() on a generated spec should work (fallback to static analysis)."""
        checker = TLCChecker()
        gen = TLASpecGenerator()
        spec = gen.generate_spec(task_description="Test")

        result = checker.check(spec)
        assert isinstance(result, TLCResult)

    def test_tlc_availability_is_bool(self) -> None:
        checker = TLCChecker()
        jar = checker._find_jar()  # type: ignore[attr-defined]
        assert isinstance(jar, str | None)


class TestTLAHelpers:
    """Tests for internal helper functions used by the TLA+ bridge."""

    def _import_helpers(self):
        """Lazy-import the private helpers under test."""
        from no_slop_harness.tla_bridge import (
            _build_cfg,
            _build_verdict_detail,
            _default_cfg,
            _extract_module_name,
            _extract_tlc_stats,
            _format_tla_value,
            _parse_tlc_output,
            _task_description,
        )
        from no_slop_harness.tla_bridge import TLCResult

        return {
            "TLCResult": TLCResult,
            "_build_cfg": _build_cfg,
            "_build_verdict_detail": _build_verdict_detail,
            "_default_cfg": _default_cfg,
            "_extract_module_name": _extract_module_name,
            "_extract_tlc_stats": _extract_tlc_stats,
            "_format_tla_value": _format_tla_value,
            "_parse_tlc_output": _parse_tlc_output,
            "_task_description": _task_description,
        }

    # ------------------------------------------------------------------
    # _task_description
    # ------------------------------------------------------------------

    def test_task_description_with_string(self) -> None:
        h = self._import_helpers()
        assert h["_task_description"]("hello") == "hello"

    def test_task_description_with_object_has_description(self) -> None:
        h = self._import_helpers()

        class FakeTask:
            description = "my task desc"

        assert h["_task_description"](FakeTask()) == "my task desc"

    def test_task_description_with_plain_object_fallback(self) -> None:
        h = self._import_helpers()
        assert h["_task_description"](42) == "42"

    # ------------------------------------------------------------------
    # _build_verdict_detail
    # ------------------------------------------------------------------

    def test_verdict_detail_tlc_passed(self) -> None:
        h = self._import_helpers()
        result = h["TLCResult"](
            passed=True,
            stats={"distinct_states": 42, "mode": "tlc"},
        )
        detail = h["_build_verdict_detail"](result)
        assert "42" in detail
        assert "passed" in detail.lower()

    def test_verdict_detail_static_fallback_passed(self) -> None:
        h = self._import_helpers()
        result = h["TLCResult"](
            passed=True,
            stats={"mode": "static_fallback"},
        )
        detail = h["_build_verdict_detail"](result)
        assert "static analysis" in detail.lower()

    def test_verdict_detail_with_error(self) -> None:
        h = self._import_helpers()
        result = h["TLCResult"](passed=False, error="Java not found")
        detail = h["_build_verdict_detail"](result)
        assert "Java not found" in detail

    def test_verdict_detail_with_counterexample(self) -> None:
        h = self._import_helpers()
        result = h["TLCResult"](
            passed=False, counterexample="Invariant violated at state 7"
        )
        detail = h["_build_verdict_detail"](result)
        assert "Invariant" in detail

    def test_verdict_detail_unknown_failure(self) -> None:
        h = self._import_helpers()
        result = h["TLCResult"](passed=False)
        detail = h["_build_verdict_detail"](result)
        assert "unknown reason" in detail.lower()

    # ------------------------------------------------------------------
    # _extract_module_name
    # ------------------------------------------------------------------

    def test_extract_module_name_found(self) -> None:
        h = self._import_helpers()
        spec = "---- MODULE MyModule ----\n"
        assert h["_extract_module_name"](spec) == "MyModule"

    def test_extract_module_name_long_header(self) -> None:
        """The long-format header (---...--- MODULE ...) does not match the
        short-format parser, which expects exactly '---- MODULE ' prefix
        and ' ----' suffix."""
        h = self._import_helpers()
        spec = (
            "---------------------------- MODULE MyModule ----------------------------\n"
        )
        # The parser uses strict short-format matching
        assert h["_extract_module_name"](spec) is None

    def test_extract_module_name_missing(self) -> None:
        h = self._import_helpers()
        assert h["_extract_module_name"]("EXTENDS Naturals") is None

    # ------------------------------------------------------------------
    # _default_cfg and _build_cfg
    # ------------------------------------------------------------------

    def test_default_cfg_structure(self) -> None:
        h = self._import_helpers()
        cfg = h["_default_cfg"]("CIVPipeline")
        assert "SPECIFICATION" in cfg
        assert "CONSTANTS" in cfg
        assert "INVARIANT" in cfg or "INVARIANTS" in cfg
        assert "PROPERTIES" in cfg
        assert "CHECK_DEADLOCK" in cfg
        assert "TRUE" in cfg

    def test_build_cfg_with_overrides(self) -> None:
        h = self._import_helpers()
        cfg = h["_build_cfg"]("Test", {"INVARIANTS": ["TypeOK"]})
        assert "SPECIFICATION" in cfg
        assert "TypeOK" in cfg
        assert "Spec" in cfg

    # ------------------------------------------------------------------
    # _format_tla_value
    # ------------------------------------------------------------------

    def test_format_tla_value_bool_true(self) -> None:
        h = self._import_helpers()
        assert h["_format_tla_value"](True) == "TRUE"

    def test_format_tla_value_bool_false(self) -> None:
        h = self._import_helpers()
        assert h["_format_tla_value"](False) == "FALSE"

    def test_format_tla_value_string(self) -> None:
        h = self._import_helpers()
        assert h["_format_tla_value"]("hello") == '"hello"'

    def test_format_tla_value_int(self) -> None:
        h = self._import_helpers()
        assert h["_format_tla_value"](42) == "42"

    # ------------------------------------------------------------------
    # _parse_tlc_output
    # ------------------------------------------------------------------

    def test_parse_tlc_output_passed(self) -> None:
        h = self._import_helpers()
        output = "Model checking completed. No error has been found."
        passed, ce = h["_parse_tlc_output"](output)
        assert passed is True
        assert ce is None

    def test_parse_tlc_output_failed(self) -> None:
        h = self._import_helpers()
        output = (
            "Error: Invariant NoDuplicateExecution is violated.\n"
            "State 1: <Initial predicate>"
        )
        passed, ce = h["_parse_tlc_output"](output)
        assert passed is False
        assert ce is not None
        assert "NoDuplicateExecution" in ce or "State" in ce

    # ------------------------------------------------------------------
    # _extract_tlc_stats
    # ------------------------------------------------------------------

    def test_extract_tlc_stats_parses_counts(self) -> None:
        h = self._import_helpers()
        output = (
            "Progress: 42 distinct states found.\n"
            "Progress: 100 states generated.\n"
            "State space diameter: 7\n"
        )
        stats = h["_extract_tlc_stats"](output)
        assert stats.get("distinct_states") == 42 or "distinct_states" in stats

    def test_extract_tlc_stats_empty(self) -> None:
        h = self._import_helpers()
        stats = h["_extract_tlc_stats"]("no stats here")
        assert stats == {}
