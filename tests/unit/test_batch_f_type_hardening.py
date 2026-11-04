"""
TDD tests voor Batch F type hardening.
Run BEFORE implementatie -> verwacht FAIL (RED).
Run AFTER implementatie  -> verwacht PASS (GREEN).
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent


def _module_defines_name(filepath: Path, name: str) -> bool:
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


def _class_field_annotation(filepath: Path, class_name: str, field_name: str) -> str | None:
    """Return annotation of a dataclass / class field."""
    src = filepath.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    if stmt.target.id == field_name:
                        return ast.unparse(stmt.annotation)
    return None


def _return_annotation(filepath: Path, fn_name: str) -> str | None:
    src = filepath.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            if node.returns:
                return ast.unparse(node.returns)
    return None


@pytest.mark.unit
class TestFallbackChainTyping:
    """`_StatsDict` TypedDict moet bestaan in fallback_chain.py."""

    TARGET = ROOT / "src/core/llm/fallback_chain.py"

    def test_stats_typeddict_exists(self) -> None:
        assert _module_defines_name(self.TARGET, "_StatsDict"), (
            "fallback_chain.py moet _StatsDict TypedDict definiëren"
        )

    def test_stats_field_uses_typeddict_not_bare_any(self) -> None:
        src = self.TARGET.read_text(encoding="utf-8")
        # Look for _stats annotation that still says dict[str, Any]
        for line in src.splitlines():
            if "self._stats" in line and ": dict[str, Any]" in line:
                # Check it doesn't have a TODO on the same line
                if "# TODO" not in line and "# type:" not in line:
                    pytest.fail(f"_stats heeft nog bare dict[str, Any]: {line.strip()}")

    def test_get_stats_return_no_bare_any(self) -> None:
        ann = _return_annotation(self.TARGET, "get_stats")
        assert ann is not None
        assert "Any" not in ann, f"get_stats return heeft bare Any: {ann}"


@pytest.mark.unit
class TestRetryPolicyTyping:
    """`circuit_breaker: Any | None` moet `CircuitBreaker | None` zijn."""

    TARGET = ROOT / "src/core/resilience/retry_policy.py"

    def test_circuit_breaker_annotation_no_bare_any(self) -> None:
        ann = _class_field_annotation(self.TARGET, "RetryConfig", "circuit_breaker")
        assert ann is not None, "circuit_breaker field niet gevonden in RetryConfig"
        assert "Any" not in ann, f"circuit_breaker annotatie heeft bare Any: {ann}"

    def test_circuit_breaker_import_present(self) -> None:
        src = self.TARGET.read_text(encoding="utf-8")
        assert "CircuitBreaker" in src, "retry_policy.py moet CircuitBreaker importeren"


@pytest.mark.unit
class TestPubSubManagerTyping:
    """listening_task moet `asyncio.Task[None]` zijn."""

    TARGET = ROOT / "src/core/events/pubsub_manager.py"

    def test_listening_task_no_bare_any(self) -> None:
        src = self.TARGET.read_text(encoding="utf-8")
        for line in src.splitlines():
            if "listening_task" in line and "Task[Any]" in line:
                if "# TODO" not in line and "# type:" not in line:
                    pytest.fail(f"listening_task heeft bare Task[Any]: {line.strip()}")


@pytest.mark.unit
class TestRedisCacheTyping:
    """`_local_cache` moet `dict[str, object]` zijn."""

    TARGET = ROOT / "src/core/infrastructure/redis_cache.py"

    def test_local_cache_no_bare_any(self) -> None:
        src = self.TARGET.read_text(encoding="utf-8")
        for line in src.splitlines():
            if "_local_cache" in line and ": dict[str, Any]" in line:
                if "# TODO" not in line and "# type:" not in line:
                    pytest.fail(f"_local_cache heeft bare dict[str, Any]: {line.strip()}")
