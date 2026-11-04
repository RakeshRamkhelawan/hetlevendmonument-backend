"""
SP-TYPE-02 Dag 7 — AST regression tests for resilience + middleware type hardening.

Each test parses the source file with the `ast` module and asserts that:
  - Dead legacy typing imports (Dict, Optional, Union, etc.) are gone.
  - New concrete annotations (str | None, list[str], etc.) are present.

These tests have zero runtime dependencies on the modules themselves and
therefore do not trigger any heavy initialisation code.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent  # repo root


def _imported_names(path: Path) -> set[str]:
    """Return every name imported from `typing` or `collections.abc` in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("typing", "collections.abc"):
            for alias in node.names:
                names.add(alias.name)
    return names


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# circuit_breaker.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCircuitBreakerImports:
    """Dead legacy typing imports removed from circuit_breaker.py."""

    FILE = ROOT / "src/core/resilience/circuit_breaker.py"

    def test_dict_not_imported(self) -> None:
        assert "Dict" not in _imported_names(self.FILE), (
            "Dict is a legacy typing alias — use built-in dict[] instead"
        )

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE), (
            "Optional is unused in circuit_breaker.py — remove from imports"
        )

    def test_cast_not_imported(self) -> None:
        assert "cast" not in _imported_names(self.FILE), (
            "cast is not used in circuit_breaker.py — remove from imports"
        )

    def test_any_still_imported(self) -> None:
        # Any is still legitimately needed for Callable[..., Any] signatures
        assert "Any" in _imported_names(self.FILE)


# ---------------------------------------------------------------------------
# retry_policy.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRetryPolicyImports:
    """Dead legacy typing imports removed from retry_policy.py."""

    FILE = ROOT / "src/core/resilience/retry_policy.py"

    def test_list_not_imported(self) -> None:
        assert "List" not in _imported_names(self.FILE), (
            "List is a legacy typing alias — use built-in list[] instead"
        )

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE), (
            "Optional is unused in retry_policy.py — use X | None syntax instead"
        )

    def test_tuple_not_imported(self) -> None:
        assert "Tuple" not in _imported_names(self.FILE), (
            "Tuple is a legacy typing alias — use built-in tuple[] instead"
        )

    def test_type_not_imported(self) -> None:
        assert "Type" not in _imported_names(self.FILE), (
            "Type is a legacy typing alias — use built-in type[] instead"
        )

    def test_union_not_imported(self) -> None:
        assert "Union" not in _imported_names(self.FILE), (
            "Union is unused in retry_policy.py — use X | Y syntax instead"
        )

    def test_cast_still_imported(self) -> None:
        # cast(float, delay) on line ~171 is still in use
        assert "cast" in _imported_names(self.FILE)


# ---------------------------------------------------------------------------
# performance_profiler.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPerformanceProfilerImports:
    """Dead legacy typing imports removed; Optional replaced with | None syntax."""

    FILE = ROOT / "src/core/middleware/performance_profiler.py"

    def test_dict_not_imported(self) -> None:
        assert "Dict" not in _imported_names(self.FILE), (
            "Dict is a legacy typing alias — use built-in dict[] instead"
        )

    def test_list_not_imported(self) -> None:
        assert "List" not in _imported_names(self.FILE), (
            "List is a legacy typing alias — use built-in list[] instead"
        )

    def test_optional_not_in_source(self) -> None:
        src = _source(self.FILE)
        assert "Optional" not in src, (
            "Optional should be replaced with X | None syntax throughout the file"
        )

    def test_instance_annotation_uses_pipe_syntax(self) -> None:
        src = _source(self.FILE)
        assert "PerformanceProfiler | None" in src, (
            "_instance class var should use 'PerformanceProfiler | None' syntax"
        )

    def test_any_still_imported(self) -> None:
        assert "Any" in _imported_names(self.FILE)


# ---------------------------------------------------------------------------
# fallback_chain.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFallbackChainTypes:
    """Concrete type annotations applied to fallback_chain.py."""

    FILE = ROOT / "src/core/llm/fallback_chain.py"

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE), (
            "Optional is unused in fallback_chain.py — use X | None syntax instead"
        )

    def test_union_not_imported(self) -> None:
        assert "Union" not in _imported_names(self.FILE), (
            "Union is unused in fallback_chain.py — use X | Y syntax instead"
        )

    def test_coroutine_not_imported(self) -> None:
        assert "Coroutine" not in _imported_names(self.FILE), (
            "Coroutine was imported but never used — remove from imports"
        )

    def test_call_model_returns_str_or_none(self) -> None:
        tree = ast.parse(self.FILE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_call_model":
                ret = ast.unparse(node.returns) if node.returns else ""
                assert "str | None" in ret, f"_call_model should return 'str | None', got {ret!r}"
                return
        pytest.fail("_call_model not found in fallback_chain.py")

    def test_errors_list_is_list_of_str(self) -> None:
        """errors: list[Any] must be replaced with list[str]."""
        src = _source(self.FILE)
        # The old annotation must be gone
        assert "errors: list[Any]" not in src, (
            "errors variable should be typed as list[str], not list[Any]"
        )
        assert "errors: list[str]" in src, "errors variable should be explicitly typed as list[str]"

    def test_messages_list_is_list_of_dict_str_str(self) -> None:
        """messages: list[Any] in LM Studio / OpenAI helpers must be list[dict[str, str]]."""
        src = _source(self.FILE)
        assert "messages: list[Any]" not in src, (
            "messages variables should be typed as list[dict[str, str]], not list[Any]"
        )
        assert "messages: list[dict[str, str]]" in src, (
            "messages variables should use the concrete list[dict[str, str]] annotation"
        )

    def test_get_stats_has_no_any_intermediate_vars(self) -> None:
        """The three Any-typed intermediate locals in get_stats() should be gone."""
        src = _source(self.FILE)
        assert 'total: Any = self._stats["total_calls"]' not in src, (
            "Redundant 'total: Any' intermediate variable should be removed from get_stats()"
        )
        assert 'success: Any = self._stats["successful_calls"]' not in src, (
            "Redundant 'success: Any' intermediate variable should be removed from get_stats()"
        )
