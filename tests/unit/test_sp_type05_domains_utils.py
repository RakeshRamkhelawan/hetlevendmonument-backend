"""
SP-TYPE-05 Group A -- type-safety regression tests.

One test per changed file, verifying that:
- Legacy typing aliases (Dict, List, Optional, Set, Tuple) are no longer
  imported from `typing` in the module under test.
- HIGH-confidence narrowed types are present in the source text.
- All modules import without error.
"""

import ast
import importlib
import inspect
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent


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


def _imported_names(rel_path: str) -> set[str]:
    """Return the set of names imported from `typing` in a source file."""
    src = (ROOT / rel_path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                names.add(alias.name)
    return names


# ---------------------------------------------------------------------------
# 1. response_formatter -- removed Dict/List/Optional; html_parts narrowed to list[str]
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_response_formatter_no_legacy_typing_aliases_and_html_parts_narrowed() -> None:
    """Dict/List/Optional removed; html_parts narrowed to list[str]."""
    mod = _import("src.core.generation.response_formatter")
    src = _source(mod)
    for alias in ("Dict", "List", "Optional"):
        assert f", {alias}" not in src and f"import {alias}" not in src, (
            f"Legacy alias '{alias}' still present in response_formatter.py"
        )
    assert "html_parts: list[str]" in src, (
        "html_parts should be narrowed to list[str] in response_formatter.py"
    )


# ---------------------------------------------------------------------------
# 2. template_engine -- removed Dict/List/Optional/Set/Tuple; errors narrowed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_template_engine_no_legacy_typing_aliases_and_errors_narrowed() -> None:
    """Dict/List/Optional/Set/Tuple removed; errors narrowed to list[str]."""
    mod = _import("src.core.generation.template_engine")
    src = _source(mod)
    for alias in ("Dict", "List", "Optional", "Set", "Tuple"):
        assert f", {alias}" not in src and f"import {alias}" not in src, (
            f"Legacy alias '{alias}' still present in template_engine.py"
        )
    assert "errors: list[str]" in src, (
        "errors accumulator should be narrowed to list[str] in template_engine.py"
    )


# ---------------------------------------------------------------------------
# 3. prompt_builder -- removed Dict/List/Optional/Tuple; suggestions narrowed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_prompt_builder_no_legacy_typing_aliases_and_suggestions_narrowed() -> None:
    """Dict/List/Optional/Tuple removed; suggestions lists narrowed to list[str]."""
    mod = _import("src.core.generation.prompt_builder")
    src = _source(mod)
    for alias in ("Dict", "List", "Optional", "Tuple"):
        assert f", {alias}" not in src and f"import {alias}" not in src, (
            f"Legacy alias '{alias}' still present in prompt_builder.py"
        )
    assert "all_suggestions: list[str]" in src, (
        "all_suggestions should be narrowed to list[str] in prompt_builder.py"
    )
    assert "enhancements: list[str]" in src, (
        "enhancements should be narrowed to list[str] in prompt_builder.py"
    )


# ---------------------------------------------------------------------------
# 4. agentic_service -- removed Optional
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_agentic_service_no_optional_import() -> None:
    """Optional removed from agentic_service typing import."""
    mod = _import("src.domains.flows.agentic_service")
    src = _source(mod)
    typing_imports = [
        line for line in src.splitlines() if line.strip().startswith("from typing import")
    ]
    for line in typing_imports:
        assert "Optional" not in line, (
            f"'Optional' still imported from typing in agentic_service.py: {line!r}"
        )


# ---------------------------------------------------------------------------
# 5. pack_activation -- removed Optional; _execute_score lists narrowed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pack_activation_no_optional_and_lists_narrowed() -> None:
    """Optional removed; reasons/matched_signals narrowed to list[str]; scores to list[tuple[float, str]]."""
    mod = _import("src.core.company.pack_activation")
    src = _source(mod)
    typing_imports = [
        line for line in src.splitlines() if line.strip().startswith("from typing import")
    ]
    for line in typing_imports:
        assert "Optional" not in line, (
            f"'Optional' still imported from typing in pack_activation.py: {line!r}"
        )
    assert "reasons: list[str]" in src, "reasons should be narrowed to list[str] in _execute_score"
    assert "matched_signals: list[str]" in src, (
        "matched_signals should be narrowed to list[str] in _execute_score"
    )
    assert "scores: list[tuple[float, str]]" in src, (
        "scores should be narrowed to list[tuple[float, str]] in _execute_score"
    )


# ---------------------------------------------------------------------------
# 6. external_agent_service -- removed Dict/List/Optional; stale_ids narrowed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_external_agent_service_no_legacy_aliases_and_stale_ids_narrowed() -> None:
    """Dict/List/Optional removed; stale_ids narrowed to list[uuid.UUID]."""
    mod = _import("src.core.company.external_agent_service")
    src = _source(mod)
    for alias in ("Dict", "List", "Optional"):
        assert f", {alias}" not in src and f"import {alias}" not in src, (
            f"Legacy alias '{alias}' still present in external_agent_service.py"
        )
    assert "stale_ids: list[uuid.UUID]" in src, (
        "stale_ids should be narrowed to list[uuid.UUID] in external_agent_service.py"
    )


# ---------------------------------------------------------------------------
# 7. external_agent_bridge -- removed Dict/Optional; sla_seconds narrowed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_external_agent_bridge_no_legacy_aliases_and_sla_seconds_narrowed() -> None:
    """Dict/Optional removed; sla_seconds narrowed to int | None."""
    mod = _import("src.core.company.external_agent_bridge")
    src = _source(mod)
    for alias in ("Dict", "Optional"):
        assert f", {alias}" not in src and f"import {alias}" not in src, (
            f"Legacy alias '{alias}' still present in external_agent_bridge.py"
        )
    assert "sla_seconds: int | None" in src, (
        "sla_seconds should be narrowed to int | None in external_agent_bridge.py"
    )


# ---------------------------------------------------------------------------
# 8. domain_pack_registry -- removed Optional; tenant_id narrowed to UUID | str
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_domain_pack_registry_no_optional_and_tenant_id_narrowed() -> None:
    """Optional removed; tenant_id params narrowed to UUID | str."""
    mod = _import("src.core.procedures.domain_pack_registry")
    src = _source(mod)
    typing_imports = [
        line for line in src.splitlines() if line.strip().startswith("from typing import")
    ]
    for line in typing_imports:
        assert "Optional" not in line, (
            f"'Optional' still imported from typing in domain_pack_registry.py: {line!r}"
        )
    # SP-TYPE-05 eiste letterlijk `tenant_id: UUID | str`. Op 2026-08-01 is dat
    # gecorrigeerd naar `int | str`, na uitputtende verificatie dat int de canonieke vorm
    # is: alle 21 `tenant_id`-kolommen in de modellen zijn `Mapped[int]`,
    # DomainPackRepository.list_by_tenant neemt een int, en beide productie-aanroepers
    # (health-check en department_service) geven een int. UUID-only was een echte
    # productiebug -- de health-check van de registry gooide altijd een TypeError.
    # De 480-regelige UUID-testsuite is meegemigreerd; die UUID's draaiden tegen een
    # gemockte repository en zouden tegen een echte kolom stil nul rijen opleveren.
    # De bedoeling van SP-TYPE-05 blijft: geen Optional, geen Any, een expliciete smalle
    # unie. Zie tests/architecture/test_tenant_id_type_matches_model.py.
    assert "tenant_id: int | str" in src, (
        "tenant_id parameters should be an explicit narrow union in domain_pack_registry.py"
    )
    # AST-gebaseerd: de docstring van _normalize_tenant_id LEGT de UUID-historie uit,
    # dus een tekstuele check zou daarop struikelen. Het gaat om code, niet om uitleg.
    import ast as _ast

    _tree = _ast.parse(src)
    _uuid_in_code = [
        node
        for node in _ast.walk(_tree)
        if (isinstance(node, _ast.Name) and node.id == "UUID")
        or (isinstance(node, _ast.Attribute) and getattr(node.value, "id", "") == "UUID")
    ]
    assert not _uuid_in_code, (
        "domain_pack_registry mag geen UUID-tenants meer accepteren -- de kolom is Integer"
    )


# ---------------------------------------------------------------------------
# 9. domain_pack_repository -- typing.Any removed; UUID imported; pack_id: UUID
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_domain_pack_repository_no_any_import_and_pack_id_is_uuid() -> None:
    """typing.Any removed; pack_id params narrowed to UUID in DomainPackRepository."""
    mod = _import("src.core.procedures.domain_pack_repository")
    src = _source(mod)
    # Verify Any is no longer imported from typing
    for line in src.splitlines():
        if line.strip().startswith("from typing import"):
            assert "Any" not in line, (
                f"'Any' still imported from typing in domain_pack_repository.py: {line!r}"
            )
    # Verify UUID is imported
    assert "from uuid import UUID" in src, "UUID should be imported in domain_pack_repository.py"
    # Verify pack_id params are narrowed
    assert "pack_id: UUID" in src, (
        "pack_id parameters should be typed as UUID in domain_pack_repository.py"
    )
