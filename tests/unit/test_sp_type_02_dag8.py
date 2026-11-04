"""
SP-TYPE-02 DAG 8 — AST regression tests for Services + LLM type hardening.

One test per changed file. Each test parses the source with the stdlib `ast`
module and asserts that the specific Any-annotations that were eliminated are
gone, and that the expected concrete types are now present.

No imports from the production modules are required, so these tests run in
--collect-only without triggering any side effects.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # repo root


def _parse(rel: str) -> ast.Module:
    path = ROOT / rel
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. training_service.py — legacy typing imports removed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_training_service_no_legacy_typing_imports() -> None:
    """Dict / List / Optional / Tuple from `typing` must not appear as imports."""
    src = _source("src/core/services/training_service.py")
    tree = _parse("src/core/services/training_service.py")

    removed = {"Dict", "List", "Optional", "Tuple"}
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                imported_names.add(alias.name)

    leaked = removed & imported_names
    assert not leaked, (
        f"Legacy typing names still imported from `typing`: {leaked}. "
        "Use built-in generics (list, dict, tuple) or | union syntax instead."
    )

    # Also confirm Any is still present (we didn't over-strip)
    assert "Any" in imported_names, "Any should still be imported in training_service.py"


# ---------------------------------------------------------------------------
# 2. workflow_generator_service.py — db_session / step_times / settings typed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_workflow_generator_service_types() -> None:
    """
    - db_session param in __init__ and factory must use AsyncSession, not Any.
    - step_times local var must be dict[str, float], not dict[str, Any].
    - _init_*_client methods must accept Settings, not Any.
    - Legacy typing names must not be imported.
    """
    src = _source("src/core/services/workflow_generator_service.py")
    tree = _parse("src/core/services/workflow_generator_service.py")

    # Legacy imports gone
    removed = {"Dict", "List", "Optional", "Tuple"}
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                imported_names.add(alias.name)

    leaked = removed & imported_names
    assert not leaked, f"Legacy typing names still imported: {leaked}"

    # AsyncSession must be imported
    assert "AsyncSession" in src, "AsyncSession must be imported in workflow_generator_service.py"

    # db_session: Any must not appear as a param annotation
    assert "db_session: Any" not in src, (
        "db_session parameter must not be typed as Any; use AsyncSession | None"
    )

    # step_times dict annotation must use float, not Any
    assert "dict[str, float]" in src, "step_times local var must be annotated as dict[str, float]"
    assert "step_times: dict[str, Any]" not in src, "step_times must not use dict[str, Any]"

    # De _init_*_client-methoden zijn weg (brief 2026-10-19: een deur voor het taalmodel); er mag
    # alleen geen `settings: Any` terugkomen.
    assert "settings: Any" not in src, "geen settings: Any in de workflowgenerator"


# ---------------------------------------------------------------------------
# 3. focus_suggestion_service.py — list[Any] → concrete types
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_focus_suggestion_service_types() -> None:
    """
    - Optional must not be imported from typing.
    - detect_keywords local var `detected` must be list[str].
    - _parse_llm_response local var `suggestions` must be list[GhostNodeSuggestion].
    - _generate_rule_based_suggestions local var `suggestions` must be list[GhostNodeSuggestion].
    """
    src = _source("src/core/services/focus_suggestion_service.py")
    tree = _parse("src/core/services/focus_suggestion_service.py")

    # Optional must be gone from typing imports
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                assert alias.name != "Optional", (
                    "Optional must be removed from `typing` imports in focus_suggestion_service.py"
                )

    # detected must be list[str]
    assert "detected: list[str]" in src, (
        "detect_keywords local var `detected` must be annotated as list[str]"
    )
    assert "detected: list[Any]" not in src, "`detected` must not be typed as list[Any]"

    # Both suggestions locals must be list[GhostNodeSuggestion]
    assert src.count("list[GhostNodeSuggestion]") >= 2, (
        "Both `suggestions` local vars must be annotated as list[GhostNodeSuggestion]; "
        f"found {src.count('list[GhostNodeSuggestion]')} occurrence(s)"
    )
    assert "suggestions: list[Any]" not in src, "`suggestions` must not be typed as list[Any]"


# ---------------------------------------------------------------------------
# 4. llm_service.py — legacy typing imports removed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_llm_service_no_legacy_typing_imports() -> None:
    """Dict / List / Optional / Set must not be imported from `typing`."""
    tree = _parse("src/core/llm/llm_service.py")

    removed = {"Dict", "List", "Optional", "Set"}
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                imported_names.add(alias.name)

    leaked = removed & imported_names
    assert not leaked, f"Legacy typing names still imported in llm_service.py: {leaked}"

    # Any and cast must still be present
    assert "Any" in imported_names, "Any must still be imported in llm_service.py"
    assert "cast" in imported_names, "cast must still be imported in llm_service.py"


# ---------------------------------------------------------------------------
# 5. production_llm_client.py — Optional removed, list[str], dict[str, float|int]
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_production_llm_client_types() -> None:
    """
    - Optional must not be imported from typing.
    - _messages_to_prompt local `prompt_parts` must be list[str].
    - get_routing_stats return must be dict[str, float | int].
    """
    src = _source("src/core/llm/production_llm_client.py")
    tree = _parse("src/core/llm/production_llm_client.py")

    # Optional must be gone
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                assert alias.name != "Optional", (
                    "Optional must be removed from `typing` imports in production_llm_client.py"
                )

    # prompt_parts must be list[str]
    assert "prompt_parts: list[str]" in src, (
        "_messages_to_prompt local var `prompt_parts` must be annotated as list[str]"
    )
    assert "prompt_parts: list[Any]" not in src, "`prompt_parts` must not be typed as list[Any]"

    # get_routing_stats return type must be concrete
    assert "dict[str, float | int]" in src, (
        "get_routing_stats must return dict[str, float | int], not dict[str, Any]"
    )
    assert "def get_routing_stats(self) -> dict[str, Any]" not in src, (
        "get_routing_stats must not return dict[str, Any]"
    )
