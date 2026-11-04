"""EvalHarness -- YAML-driven golden evaluation for PracticalTwinService.

Loads deterministic scenarios, runs them through `analyze_struggle()` with a
`MockSuggestionProvider`, and reports pass/fail per scenario.

Usage:
    harness = EvalHarness(scenarios_path="tests/unit/learning/fixtures/eval_scenarios.yaml")
    report = await harness.run()
    assert report.passed == report.total
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import yaml
from loguru import logger

from src.core.learning.events.event_bus import TwinEventBus
from src.core.learning.interfaces.llm_provider import MockSuggestionProvider
from src.core.learning.observers.user_behavior_observer import UserBehaviorObserver
from src.core.learning.services.practical_twin_service import PracticalTwinService


@dataclass
class EvalScenario:
    """Single golden scenario definition."""

    id: str
    name: str
    context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    user_profile: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    user_id: str | None = None
    tenant_id: int | None = None
    mock_response: str = ""
    raise_error: bool = False
    expected: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )
    consent: dict[str, bool] | None = None


@dataclass
class EvalResult:
    """Outcome for one scenario."""

    scenario_id: str
    passed: bool
    actual: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    expected: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    errors: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    """Aggregate report across all scenarios."""

    results: list[EvalResult]
    passed: int
    failed: int
    total: int


class EvalHarness:
    """Run golden `analyze_struggle()` scenarios against a deterministic provider."""

    def __init__(
        self,
        scenarios_path: Path | str,
        observer: UserBehaviorObserver | None = None,
        cost_tracker: Any | None = None,  # TODO(TYPE): replace Any with concrete CostTracker type
        event_bus: TwinEventBus | None = None,
    ) -> None:
        self._scenarios_path = Path(scenarios_path)
        self._observer = observer or MagicMock(spec=UserBehaviorObserver)
        self._cost = cost_tracker
        self._bus = event_bus

    def _validate_path(self) -> None:
        """Ensure the scenario file exists and stays within the project tree."""
        if not self._scenarios_path.exists():
            raise FileNotFoundError(f"Scenario file not found: {self._scenarios_path}")
        if not self._scenarios_path.is_file():
            raise ValueError(f"Scenario path is not a file: {self._scenarios_path}")

        resolved = self._scenarios_path.resolve()
        project_root = Path(__file__).resolve().parents[3]
        if not resolved.is_relative_to(project_root):
            raise ValueError(f"Scenario file must be inside project root: {resolved}")

    def _load_scenarios(self) -> list[EvalScenario]:
        """Parse the YAML scenario file into EvalScenario objects."""
        self._validate_path()
        raw = yaml.safe_load(self._scenarios_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "scenarios" not in raw:
            raise ValueError(f"Invalid scenario file format: {self._scenarios_path}")
        return [EvalScenario(**item) for item in raw["scenarios"]]

    def _build_consent_manager(
        self, consent: dict[str, bool] | None
    ) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Build a deterministic consent manager mock from scenario consent flags."""
        if consent is None:
            return None

        mgr = AsyncMock()
        categories = MagicMock()
        for key, value in consent.items():
            setattr(categories, key, value)
        mgr.get_consent_categories = AsyncMock(return_value=categories)
        return mgr

    async def run(self) -> EvalReport:
        """Execute all scenarios and return an aggregate report."""
        scenarios = self._load_scenarios()
        results: list[EvalResult] = []
        for scenario in scenarios:
            result = await self._run_scenario(scenario)
            results.append(result)

        passed = sum(1 for r in results if r.passed)
        return EvalReport(
            results=results,
            passed=passed,
            failed=len(results) - passed,
            total=len(results),
        )

    async def _run_scenario(self, scenario: EvalScenario) -> EvalResult:
        """Run a single scenario through PracticalTwinService.analyze_struggle()."""
        llm = MockSuggestionProvider(
            response=scenario.mock_response,
            raise_error=scenario.raise_error,
        )
        consent_manager = self._build_consent_manager(scenario.consent)
        service = PracticalTwinService(
            observer=self._observer,
            llm_provider=llm,
            consent_manager=consent_manager,
            cost_tracker=self._cost,
            event_bus=self._bus,
        )

        actual = await service.analyze_struggle(
            context=scenario.context,
            user_profile=scenario.user_profile,
            user_id=scenario.user_id,
            tenant_id=scenario.tenant_id,
        )
        errors = self._compare(actual, scenario.expected)
        if errors:
            logger.warning(
                "eval_scenario_failed",
                scenario_id=scenario.id,
                errors=errors,
            )

        return EvalResult(
            scenario_id=scenario.id,
            passed=len(errors) == 0,
            actual=actual,
            expected=scenario.expected,
            errors=errors,
        )

    def _compare(
        self,
        actual: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        expected: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:
        """Compare actual result against expected keys, with float tolerance."""
        errors: list[str] = []
        for key, expected_value in expected.items():
            if key not in actual:
                errors.append(f"missing key {key}")
                continue

            actual_value = actual[key]
            if isinstance(expected_value, float):
                if abs(float(actual_value) - expected_value) > 0.001:
                    errors.append(f"{key}: expected {expected_value}, got {actual_value}")
            elif actual_value != expected_value:
                errors.append(f"{key}: expected {expected_value}, got {actual_value}")
        return errors
