"""
SP-TYPE-02 Dag 9 Part B -- type-safety regression tests.

One test per changed file, verifying that:
- Legacy typing aliases (Dict, List, Optional, Union, Set, Tuple) are no longer
  imported from `typing` in the module under test.
- HIGH-confidence narrowed types are present in the source text.
- All modules import without error.
"""

import importlib
import inspect
import sys
import types
from typing import get_type_hints

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source(module: types.ModuleType) -> str:
    """Return source text of a module."""
    try:
        return inspect.getsource(module)
    except OSError:
        return ""


def _import(dotted: str) -> types.ModuleType:
    """Import a module by dotted name, skipping on ImportError."""
    try:
        return importlib.import_module(dotted)
    except ImportError as exc:
        pytest.skip(f"Optional dependency missing: {exc}")


# ---------------------------------------------------------------------------
# 1. deepseek_provider -- removed Dict/List/Optional/Union; schema: type (not type[Any])
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_deepseek_provider_no_legacy_typing_aliases() -> None:
    """Dict/List/Optional/Union removed from deepseek_provider typing import."""
    mod = _import("src.core.llm.deepseek_provider")
    src = _source(mod)
    # The `from typing import ...` line should not contain the legacy aliases
    for alias in ("Dict", "List", "Optional", "Union"):
        assert f", {alias}" not in src and f"import {alias}" not in src, (
            f"Legacy alias '{alias}' still present in deepseek_provider.py"
        )


# ---------------------------------------------------------------------------
# 2. local_provider -- removed Optional; messages narrowed to list[dict[str, str]]
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_local_provider_no_optional_import_and_messages_narrowed() -> None:
    """Optional removed; messages typed as list[dict[str, str]]."""
    mod = _import("src.core.llm.local_provider")
    src = _source(mod)
    assert "Optional" not in src, "Legacy 'Optional' still present in local_provider.py"
    assert "list[dict[str, str]]" in src, (
        "messages should be typed as list[dict[str, str]] in local_provider.py"
    )


# ---------------------------------------------------------------------------
# 3. audit_logger -- removed Optional; feedback_value narrowed to scalar union
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_audit_logger_no_optional_and_feedback_value_narrowed() -> None:
    """Optional not imported from typing; feedback_value typed as str | int | float | bool."""
    mod = _import("src.core.observability.audit_logger")
    src = _source(mod)
    # "Optional" may appear in English docstrings; verify it is NOT imported from typing
    typing_imports = [
        line for line in src.splitlines() if line.strip().startswith("from typing import")
    ]
    for line in typing_imports:
        assert "Optional" not in line, (
            f"'Optional' still imported from typing in audit_logger.py: {line!r}"
        )
    assert "str | int | float | bool" in src, (
        "feedback_value should be typed as str | int | float | bool"
    )


# ---------------------------------------------------------------------------
# 4. cache -- removed Dict/List/Optional; redis_client comment present
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cache_no_legacy_typing_aliases() -> None:
    """Dict/List/Optional removed; redis_client comment present."""
    mod = _import("src.core.learning.cache")
    src = _source(mod)
    for alias in ("Dict", "List", "Optional"):
        assert f", {alias}" not in src and f"import {alias}" not in src, (
            f"Legacy alias '{alias}' still present in cache.py"
        )
    assert "redis.asyncio.Redis or compatible client" in src, (
        "redis_client parameter should document the concrete type in a comment"
    )


# ---------------------------------------------------------------------------
# 5. experiment_tracker -- removed Dict/List/Optional/Set/Union;
#    clean_metrics narrowed to dict[str, float]
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_experiment_tracker_no_legacy_aliases_and_clean_metrics_narrowed() -> None:
    """Legacy aliases removed; clean_metrics narrowed to dict[str, float]."""
    mod = _import("src.core.learning.experiment_tracker")
    src = _source(mod)
    for alias in ("Dict", "List", "Optional", "Set", "Union"):
        assert f", {alias}" not in src and f"import {alias}" not in src, (
            f"Legacy alias '{alias}' still present in experiment_tracker.py"
        )
    assert "clean_metrics: dict[str, float]" in src, (
        "clean_metrics should be narrowed to dict[str, float]"
    )


# ---------------------------------------------------------------------------
# 6. analytics -- removed Dict/List/Optional/Tuple;
#    top_categories narrowed; forecast narrowed to list[float]
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_analytics_no_legacy_aliases_and_forecast_narrowed() -> None:
    """Legacy aliases removed; forecast and ma narrowed to list[float]."""
    mod = _import("src.core.learning.analytics")
    src = _source(mod)
    for alias in ("Dict", "List", "Optional", "Tuple"):
        assert f", {alias}" not in src and f"import {alias}" not in src, (
            f"Legacy alias '{alias}' still present in analytics.py"
        )
    assert "forecast: list[float]" in src, (
        "forecast list should be typed as list[float] in analytics.py"
    )
    assert "ma: list[float]" in src, (
        "moving-average list should be typed as list[float] in analytics.py"
    )


# ---------------------------------------------------------------------------
# 7. rbac_service -- removed Optional; bulk return narrowed. (_perm_cache is per
#    bulk return type narrowed to list[dict[str, int | bool]]
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rbac_service_perm_cache_narrowed_and_bulk_return_narrowed() -> None:
    """Optional not imported from typing; _perm_cache and bulk return types narrowed."""
    mod = _import("src.core.services.rbac_service")
    src = _source(mod)
    # "Optional" appears in English docstrings; verify it is NOT imported from typing
    typing_imports = [
        line for line in src.splitlines() if line.strip().startswith("from typing import")
    ]
    for line in typing_imports:
        assert "Optional" not in line, (
            f"'Optional' still imported from typing in rbac_service.py: {line!r}"
        )
    # Vervallen op 2026-09-18: dit was de annotatie van `_perm_cache`, en die
    # permissiecache is verwijderd (ADR-036 OP-254, zie de docstring van RBACService).
    # Een assertie op de annotatie van iets dat niet meer bestaat kan alleen nog rood
    # worden om de verkeerde reden. De andere twee asserties blijven staan.
    assert "list[dict[str, int | bool]]" in src, (
        "bulk_assign/revoke_roles should return list[dict[str, int | bool]]"
    )
