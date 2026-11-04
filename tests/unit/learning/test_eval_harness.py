"""Unit tests for EvalHarness golden analyze_struggle() scenarios (SP-AGT-009 Dag 2).

Covers BE-AGT-028: a YAML-driven evaluation harness for PracticalTwinService
that uses MockSuggestionProvider to keep scenarios deterministic.
"""

from pathlib import Path

import pytest

from src.core.learning.eval_harness import EvalHarness, EvalReport


@pytest.fixture
def scenarios_path() -> Path:
    """Path to the committed golden scenario definitions."""
    return Path(__file__).with_name("fixtures") / "eval_scenarios.yaml"


@pytest.mark.unit
@pytest.mark.asyncio
class TestEvalHarness:
    async def test_harness_loads_all_scenarios(self, scenarios_path: Path) -> None:
        """Harness must parse exactly the 5 golden scenarios."""
        harness = EvalHarness(scenarios_path=scenarios_path)
        scenarios = harness._load_scenarios()
        assert len(scenarios) == 5

    async def test_harness_runs_all_scenarios(self, scenarios_path: Path) -> None:
        """All golden scenarios must pass against the deterministic service."""
        harness = EvalHarness(scenarios_path=scenarios_path)
        report = await harness.run()

        assert isinstance(report, EvalReport)
        assert report.total == 5
        assert report.passed == 5
        assert report.failed == 0

    async def test_harness_uses_mock_provider_response(self, scenarios_path: Path) -> None:
        """The mock LLM response must appear in the result when intervention is triggered."""
        harness = EvalHarness(scenarios_path=scenarios_path)
        report = await harness.run()

        crisis = next(r for r in report.results if r.scenario_id == "multi_factor_crisis")
        assert crisis.passed
        assert crisis.actual["suggestion"] == "Try splitting the function into smaller pieces."

    async def test_harness_reports_consent_opt_out(self, scenarios_path: Path) -> None:
        """A high struggle score with ai_interventions=False must be blocked."""
        harness = EvalHarness(scenarios_path=scenarios_path)
        report = await harness.run()

        opt_out = next(r for r in report.results if r.scenario_id == "consent_opt_out")
        assert opt_out.passed
        assert opt_out.actual["reason"] == "user_opted_out_art22"
        assert opt_out.actual["suggestion"] == ""

    async def test_harness_handles_llm_failure(self, scenarios_path: Path) -> None:
        """A failing LLM provider must not crash the harness; suggestion stays empty."""
        harness = EvalHarness(scenarios_path=scenarios_path)
        report = await harness.run()

        failure = next(r for r in report.results if r.scenario_id == "llm_failure")
        assert failure.passed
        assert failure.actual["needs_intervention"] is True
        assert failure.actual["suggestion"] == ""
