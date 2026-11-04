"""
TDD tests voor Batch D type hardening.
Run BEFORE implementatie -> verwacht FAIL (RED).
Run AFTER implementatie  -> verwacht PASS (GREEN).
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent


def _annotation_of_function(filepath: Path, fn_name: str) -> str | None:
    """Return string representation of a function's return annotation."""
    src = filepath.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            if node.returns:
                return ast.unparse(node.returns)
    return None


def _param_annotation(filepath: Path, fn_name: str, param_name: str) -> str | None:
    """Return string representation of a specific parameter annotation."""
    src = filepath.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            for arg in node.args.args:
                if arg.arg == param_name and arg.annotation:
                    return ast.unparse(arg.annotation)
    return None


def _module_defines_name(filepath: Path, name: str) -> bool:
    """Return True if the module defines a class or TypeAlias with the given name."""
    src = filepath.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return True
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            return True
    return False


@pytest.mark.unit
class TestLearningWorkerTyping:
    """learning/worker.py: FeedbackPayload TypedDict + cleanup TypedDicts."""

    TARGET = ROOT / "src/core/learning/worker.py"

    def test_feedback_payload_typeddict_exists(self) -> None:
        assert _module_defines_name(self.TARGET, "FeedbackPayload"), (
            "learning/worker.py moet FeedbackPayload TypedDict definiëren"
        )

    def test_insight_cleanup_typeddict_exists(self) -> None:
        assert _module_defines_name(self.TARGET, "InsightCleanupDict"), (
            "learning/worker.py moet InsightCleanupDict TypedDict definiëren"
        )

    def test_observation_cleanup_typeddict_exists(self) -> None:
        assert _module_defines_name(self.TARGET, "ObservationCleanupDict"), (
            "learning/worker.py moet ObservationCleanupDict TypedDict definiëren"
        )

    def test_costlog_cleanup_typeddict_exists(self) -> None:
        assert _module_defines_name(self.TARGET, "CostLogCleanupDict"), (
            "learning/worker.py moet CostLogCleanupDict TypedDict definiëren"
        )

    def test_process_feedback_actor_param_is_dict_and_payload_typeddict_exists(self) -> None:
        # Dramatiq actors must accept dict[str, Any] (raw JSON from Redis).
        # FeedbackPayload TypedDict serves as documentation for callers building the dict.
        ann = _param_annotation(self.TARGET, "process_feedback_async", "feedback_data")
        assert ann is not None, "feedback_data annotation missing"
        assert "dict" in ann, f"feedback_data moet een dict zijn: {ann}"
        # The TypedDict must still exist as caller documentation
        assert _module_defines_name(self.TARGET, "FeedbackPayload"), (
            "FeedbackPayload TypedDict moet bestaan als caller-documentatie"
        )

    def test_cleanup_old_insights_return_no_bare_any(self) -> None:
        ann = _annotation_of_function(self.TARGET, "cleanup_old_insights")
        assert ann is not None
        assert "Any" not in ann, f"cleanup_old_insights return heeft bare Any: {ann}"


@pytest.mark.unit
class TestAnalyticsTyping:
    """analytics.py: AsyncSession | None voor db_session; rapport TypedDicts."""

    TARGET = ROOT / "src/core/learning/analytics.py"

    def test_db_session_init_param_no_bare_any(self) -> None:
        ann = _param_annotation(self.TARGET, "__init__", "db_session")
        assert ann is not None
        assert "Any" not in ann, f"db_session in __init__ heeft bare Any: {ann}"

    def test_daily_report_typeddict_exists(self) -> None:
        assert _module_defines_name(self.TARGET, "DailyReportDict"), (
            "analytics.py moet DailyReportDict TypedDict definiëren"
        )

    def test_weekly_report_typeddict_exists(self) -> None:
        assert _module_defines_name(self.TARGET, "WeeklyReportDict"), (
            "analytics.py moet WeeklyReportDict TypedDict definiëren"
        )

    def test_generate_daily_report_return_no_bare_any(self) -> None:
        ann = _annotation_of_function(self.TARGET, "generate_daily_report")
        assert ann is not None
        assert "Any" not in ann, f"generate_daily_report return heeft bare Any: {ann}"


# `TestWorkflowWorkerTyping` stond hier, tegen `src/core/workflow/worker.py` -- bevestigd
# dode code (ADR-036 OP-158 D2b), 2026-08-27 verwijderd. De ECHTE, gedeployde module
# (`src/workers/workflow_worker.py`) heeft de `ExecutionResultDict`/`HealthStatusDict`-
# TypedDicts NOOIT gekregen -- `WorkflowTaskResult`/`HealthStatus` zijn daar nog steeds
# `TypeAlias = dict[str, Any]` (`# type: ignore[misc, unused-ignore]`, regel 84-85). Dat is
# een echt, ongedekt stukje typeschuld, maar het overzetten vraagt een verificatie tegen de
# daadwerkelijke dict-vormen op alle aanroepplekken in de LEVENDE module (die kunnen zijn
# gaan afwijken van de dode kopie) -- een eigen, kleine wijziging, niet deze opruimactie.


@pytest.mark.unit
class TestVibeMonitoringTyping:
    """vibe_monitoring.py: HealthCheckResultDict TypedDict."""

    TARGET = ROOT / "src/core/monitoring/vibe_monitoring.py"

    def test_health_check_result_typeddict_exists(self) -> None:
        assert _module_defines_name(self.TARGET, "HealthCheckResultDict"), (
            "vibe_monitoring.py moet HealthCheckResultDict TypedDict definiëren"
        )

    def test_check_all_return_no_bare_any(self) -> None:
        ann = _annotation_of_function(self.TARGET, "check_all")
        assert ann is not None
        assert "Any" not in ann, f"check_all return heeft bare Any: {ann}"
