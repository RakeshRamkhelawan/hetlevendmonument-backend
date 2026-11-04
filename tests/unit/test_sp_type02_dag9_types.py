"""
SP-TYPE-02 Dag 9 — Type annotation regression tests.

Verifies that legacy typing aliases (Dict, List, Optional, Union, Set, Tuple)
have been removed from the target files and that narrowed types are present.
"""

import ast
import importlib
import importlib.util
import pathlib

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent


def _source(rel_path: str) -> str:
    """Return source text of a file relative to repo root."""
    return (_REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _typing_imports(src: str) -> list[str]:
    """Return all names imported from `typing` in the source."""
    names: list[str] = []
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing" and node.names:
            for alias in node.names:
                names.append(alias.name)
    return names


# ---------------------------------------------------------------------------
# llm_provider.py
# ---------------------------------------------------------------------------


def test_llm_provider_no_legacy_typing_imports() -> None:
    """Verifies that the legacy Dict and Optional typing imports have been removed from llm_provider.py."""
    src = _source("src/core/learning/interfaces/llm_provider.py")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module == "typing":
                names = [alias.name for alias in node.names]
                assert "Dict" not in names, "Legacy 'Dict' still imported from typing"
                assert "Optional" not in names, "Legacy 'Optional' still imported from typing"


# ---------------------------------------------------------------------------
# deepseek_provider.py
# ---------------------------------------------------------------------------


def test_deepseek_provider_no_legacy_typing_aliases() -> None:
    """Verifies Dict/List/Optional/Union are no longer imported from typing in deepseek_provider.py."""
    src = _source("src/core/llm/deepseek_provider.py")
    imported = _typing_imports(src)
    for alias in ("Dict", "List", "Optional", "Union"):
        assert alias not in imported, (
            f"Legacy '{alias}' still imported from typing in deepseek_provider.py"
        )


# ---------------------------------------------------------------------------
# local_provider.py
# ---------------------------------------------------------------------------


def test_local_provider_no_optional_import_and_messages_narrowed() -> None:
    """Verifies Optional is removed and messages list is narrowed to list[dict[str, str]]."""
    src = _source("src/core/llm/local_provider.py")
    imported = _typing_imports(src)
    assert "Optional" not in imported, (
        "Legacy 'Optional' still imported from typing in local_provider.py"
    )
    assert "list[dict[str, str]]" in src, (
        "messages list not narrowed to list[dict[str, str]] in local_provider.py"
    )


# ---------------------------------------------------------------------------
# audit_logger.py
# ---------------------------------------------------------------------------


def test_audit_logger_no_optional_and_feedback_value_narrowed() -> None:
    """Verifies Optional not imported from typing; feedback_value narrowed to scalar union."""
    src = _source("src/core/observability/audit_logger.py")
    imported = _typing_imports(src)
    assert "Optional" not in imported, (
        "Legacy 'Optional' still imported from typing in audit_logger.py"
    )
    assert "str | int | float | bool" in src, (
        "feedback_value not narrowed to scalar union in audit_logger.py"
    )


# ---------------------------------------------------------------------------
# cache.py
# ---------------------------------------------------------------------------


def test_cache_no_legacy_typing_aliases() -> None:
    """Verifies Dict/List/Optional removed and redis_client has a descriptive comment."""
    src = _source("src/core/learning/cache.py")
    imported = _typing_imports(src)
    for alias in ("Dict", "List", "Optional"):
        assert alias not in imported, f"Legacy '{alias}' still imported from typing in cache.py"
    assert "redis.asyncio.Redis or compatible client" in src, (
        "redis_client comment missing in cache.py"
    )


# ---------------------------------------------------------------------------
# experiment_tracker.py
# ---------------------------------------------------------------------------


def test_experiment_tracker_no_legacy_aliases_and_clean_metrics_narrowed() -> None:
    """Verifies legacy aliases removed and clean_metrics narrowed to dict[str, float]."""
    src = _source("src/core/learning/experiment_tracker.py")
    imported = _typing_imports(src)
    for alias in ("Dict", "List", "Optional", "Set", "Union"):
        assert alias not in imported, (
            f"Legacy '{alias}' still imported from typing in experiment_tracker.py"
        )
    assert "clean_metrics: dict[str, float]" in src, (
        "clean_metrics not narrowed to dict[str, float] in experiment_tracker.py"
    )


# ---------------------------------------------------------------------------
# analytics.py
# ---------------------------------------------------------------------------


def test_analytics_no_legacy_aliases_and_forecast_narrowed() -> None:
    """Verifies legacy aliases removed; forecast and moving-average lists narrowed to list[float]."""
    src = _source("src/core/learning/analytics.py")
    imported = _typing_imports(src)
    for alias in ("Dict", "List", "Optional", "Tuple"):
        assert alias not in imported, f"Legacy '{alias}' still imported from typing in analytics.py"
    assert "forecast: list[float]" in src, "forecast not narrowed to list[float] in analytics.py"
    assert "ma: list[float]" in src, "ma not narrowed to list[float] in analytics.py"


# ---------------------------------------------------------------------------
# rbac_service.py
# ---------------------------------------------------------------------------


def test_rbac_service_perm_cache_narrowed_and_bulk_return_narrowed() -> None:
    """Verifies Optional not imported, _perm_cache narrowed, bulk methods narrowed."""
    src = _source("src/core/services/rbac_service.py")
    imported = _typing_imports(src)
    assert "Optional" not in imported, (
        "Legacy 'Optional' still imported from typing in rbac_service.py"
    )
    # De assertie op `dict[str, tuple[bool, float]]` is op 2026-09-18 vervallen: dat was de
    # annotatie van `_perm_cache`, en die permissiecache is verwijderd (ADR-036 OP-254,
    # zie de docstring van RBACService voor de vier metingen onder dat besluit). Een
    # assertie op een annotatie van iets dat niet meer bestaat kan alleen nog rood worden
    # om de verkeerde reden. De twee andere asserties in deze test blijven wel staan.
    assert "list[dict[str, int | bool]]" in src, (
        "bulk return not narrowed to list[dict[str, int | bool]] in rbac_service.py"
    )
