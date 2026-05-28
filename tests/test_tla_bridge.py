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
        assert isinstance(jar, (str, type(None)))
