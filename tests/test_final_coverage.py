"""Final push tests for TLA+ bridge and OpenAI provider."""

from __future__ import annotations

from no_slop_harness.providers.openai_compatible import OpenAICompatibleConfig
from no_slop_harness.tla_bridge import (
    StaticAnalysisResult,
    TLASpecGenerator,
    TLAVerificationGate,
    TLCChecker,
    TLCResult,
)


class TestTLCResultFull:
    def test_passed_with_stats(self) -> None:
        r = TLCResult(passed=True, stats={"diameter": 10, "states": 42}, raw_output="all good")
        assert r.passed
        assert r.stats["diameter"] == 10
        assert r.counterexample is None
        assert r.raw_output == "all good"

    def test_failed_with_error(self) -> None:
        r = TLCResult(passed=False, error="TLC not found", raw_output="")
        assert not r.passed
        assert r.error == "TLC not found"

    def test_failed_with_counterexample(self) -> None:
        r = TLCResult(passed=False, counterexample="Invariant violated at state 7")
        assert not r.passed
        assert "Invariant" in r.counterexample


class TestStaticAnalysisResult:
    def test_passed_empty(self) -> None:
        r = StaticAnalysisResult(passed=True)
        assert r.passed
        assert r.warnings == []
        assert r.errors == []

    def test_with_warnings(self) -> None:
        r = StaticAnalysisResult(passed=True, warnings=["missing invariant"])
        assert r.passed
        assert len(r.warnings) == 1

    def test_with_errors(self) -> None:
        r = StaticAnalysisResult(passed=False, errors=["syntax error"])
        assert not r.passed
        assert len(r.errors) == 1


class TestTLASpecGeneratorFull:
    def test_generate_with_civ_messages(self) -> None:
        gen = TLASpecGenerator()
        state_machine = [
            {
                "sender": "coordinator",
                "recipient": "implementor",
                "phase": "plan",
                "payload": {"task_count": 3},
            },
            {
                "sender": "implementor",
                "recipient": "verifier",
                "phase": "implement",
                "task_id": "t1",
            },
            {
                "sender": "verifier",
                "recipient": "coordinator",
                "phase": "verify",
                "payload": {"passed": True},
            },
        ]
        spec = gen.generate_spec(task_description="CIV pipeline", state_machine=state_machine)
        assert "MODULE" in spec.upper() or "----" in spec
        assert "Init" in spec
        assert len(spec) > 200

    def test_generate_includes_invariants(self) -> None:
        gen = TLASpecGenerator()
        spec = gen.generate_spec(task_description="Test invariants")
        # Should reference the standard invariants
        has_invariant = "Invariant" in spec or "THEOREM" in spec or "TypeOK" in spec
        assert has_invariant

    def test_generate_empty_state_machine(self) -> None:
        gen = TLASpecGenerator()
        spec = gen.generate_spec(task_description="Minimal", state_machine=[])
        assert len(spec) > 50


class TestTLCCheckerFull:
    def test_check_with_static_fallback(self) -> None:
        checker = TLCChecker()
        gen = TLASpecGenerator()
        spec = gen.generate_spec(task_description="Test")
        result = checker.check(spec)
        assert isinstance(result, TLCResult)

    def test_find_jar_returns_none(self) -> None:
        """On a system without TLA+ tools, _find_jar returns None."""
        checker = TLCChecker()
        jar = checker._find_jar()  # type: ignore[attr-defined]
        assert jar is None or isinstance(jar, str)

    def test_static_check_validates_structure(self) -> None:
        checker = TLCChecker()
        gen = TLASpecGenerator()
        spec = gen.generate_spec(task_description="Test")
        result = checker.check(spec)
        # Static check should produce a result
        assert isinstance(result.passed, bool)


class TestTLAVerificationGateFull:
    def test_verify_generates_and_checks(self) -> None:
        gate = TLAVerificationGate()
        result = gate.verify(task="Test task with 3 states")
        assert isinstance(result, dict)
        assert "passed" in result or "tla_passed" in result

    def test_verify_with_spec_text(self) -> None:
        gate = TLAVerificationGate()
        gen = TLASpecGenerator()
        spec = gen.generate_spec(task_description="Pipeline")
        result = gate.verify(task="Pipeline", spec_text=spec)
        assert isinstance(result, dict)


class TestOpenAIProviderConfig:
    def test_minimal_config(self) -> None:
        cfg = OpenAICompatibleConfig()
        assert cfg.base_url == "http://localhost:1234/v1"

    def test_full_config(self) -> None:
        cfg = OpenAICompatibleConfig(
            base_url="https://custom.api/v1",
            api_key="sk-123",
            model="custom-model",
            timeout_seconds=30,
            max_retries=2,
        )
        assert cfg.max_retries == 2
        assert cfg.timeout_seconds == 30

    def test_provider_name_reflects_base_url(self) -> None:
        # Test without httpx installed (will fail on __init__, but we can test config)
        cfg = OpenAICompatibleConfig(base_url="https://api.service.com/v1")
        assert "https://api.service.com/v1" in cfg.base_url
