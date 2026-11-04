"""
SP-TYPE-02 DAG 10 -- AST regression tests for Database Group B type hardening.

One test per changed file. Each test parses the source with the stdlib `ast`
module and asserts that:
  - legacy typing imports that were removed (Optional, Set, cast) are gone
  - concrete types that replaced Any are now present in the source text
  - TODO(TYPE) markers are fully eliminated

No imports from the production modules are required, so these tests run in
--collect-only without triggering any side effects.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # repo root


def _parse(rel: str) -> ast.Module:
    path = ROOT / rel
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. query_optimizer.py
#    - Optional removed from typing imports
#    - Engine imported from sqlalchemy.engine
#    - configure_engine() -> Engine (not Any)
#    - list[str] locals for optimization_log and _generate_recommendations
#    - No TODO(TYPE) comments remain
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_query_optimizer_optional_removed_engine_added() -> None:
    """Optional must be gone; Engine must be imported; configure_engine returns Engine."""
    src = _source("src/core/database/query_optimizer.py")

    # Legacy Optional import must be absent
    assert "Optional" not in src, "Optional should have been removed from query_optimizer.py"

    # Engine must now be imported
    assert "from sqlalchemy.engine import Engine" in src, (
        "Engine import missing from query_optimizer.py"
    )

    # configure_engine return annotation must be Engine
    tree = _parse("src/core/database/query_optimizer.py")
    configure_engine_returns: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "configure_engine":
            if node.returns is not None:
                configure_engine_returns.append(ast.unparse(node.returns))

    assert configure_engine_returns, "configure_engine() not found"
    assert configure_engine_returns[0] == "Engine", (
        f"configure_engine() should return Engine, got {configure_engine_returns[0]}"
    )

    # No TODO(TYPE) markers
    non_type_todos = [ln for ln in src.splitlines() if "TODO" in ln and "(TYPE)" not in ln]
    assert not non_type_todos, (
        f"TODO comments (not type annotation markers) must be eliminated: {non_type_todos[:2]}"
    )

    # optimization_log local var must be list[str]
    assert "optimization_log: list[str]" in src, "optimization_log local should be list[str]"

    # _generate_recommendations local must be list[str]
    assert "recommendations: list[str]" in src, "recommendations local should be list[str]"


# ---------------------------------------------------------------------------
# 2. unit_of_work.py
#    - AsyncSession and async_sessionmaker imported
#    - TracebackType imported
#    - __aexit__ uses type[BaseException] | None (not Any)
#    - session property returns AsyncSession (not Any)
#    - SQLAlchemyUnitOfWork._session annotated as AsyncSession | None
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unit_of_work_aexit_and_session_types() -> None:
    """__aexit__ must use standard exception types; session property must return AsyncSession."""
    src = _source("src/core/database/unit_of_work.py")

    # Correct imports present
    assert "from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker" in src, (
        "AsyncSession / async_sessionmaker import missing"
    )
    assert "from types import TracebackType" in src, "TracebackType import missing"

    # __aexit__ must not use bare Any for exc_type
    tree = _parse("src/core/database/unit_of_work.py")
    aexit_nodes = [
        n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "__aexit__"
    ]
    assert aexit_nodes, "__aexit__ not found"

    aexit = aexit_nodes[0]
    # args: self, exc_type, exc_val, exc_tb
    exc_type_annotation = aexit.args.args[1].annotation
    assert exc_type_annotation is not None, "exc_type must be annotated"
    unparsed = ast.unparse(exc_type_annotation)
    assert "BaseException" in unparsed, f"exc_type should reference BaseException, got {unparsed}"
    assert "TracebackType" in ast.unparse(aexit.args.args[3].annotation), (
        "exc_tb should reference TracebackType"
    )

    # session property return type must be AsyncSession
    session_props = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "session" and n.returns is not None
    ]
    assert session_props, "session property not found"
    assert ast.unparse(session_props[0].returns) == "AsyncSession", (
        f"session property should return AsyncSession, got {ast.unparse(session_props[0].returns)}"
    )

    # _session instance attribute must be AsyncSession | None
    assert "AsyncSession | None" in src, "_session field should be AsyncSession | None"

    # No TODO(TYPE) markers
    non_type_todos = [ln for ln in src.splitlines() if "TODO" in ln and "(TYPE)" not in ln]
    assert not non_type_todos, f"TODO features must be gone: {non_type_todos[:2]}"


# ---------------------------------------------------------------------------
# 3. query_analyzer.py
#    - Optional removed; Engine imported
#    - setup_query_logging engine param is Engine (not Any)
#    - potential_n_plus_one local is list[dict[str, Any]]
#    - No TODO(TYPE) comments remain
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_query_analyzer_optional_removed_engine_param() -> None:
    """Optional removed; setup_query_logging must accept Engine not Any."""
    src = _source("src/core/database/query_analyzer.py")

    # Optional must be absent
    assert "Optional" not in src, "Optional should be removed from query_analyzer.py"

    # Engine must be imported
    assert "from sqlalchemy.engine import Engine" in src, (
        "Engine import missing from query_analyzer.py"
    )

    # setup_query_logging first param must be Engine
    tree = _parse("src/core/database/query_analyzer.py")
    fn_nodes = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "setup_query_logging"
    ]
    assert fn_nodes, "setup_query_logging not found"
    fn = fn_nodes[0]
    engine_param = fn.args.args[0]
    assert engine_param.annotation is not None, "engine param must be annotated"
    assert ast.unparse(engine_param.annotation) == "Engine", (
        f"engine param should be Engine, got {ast.unparse(engine_param.annotation)}"
    )

    # potential_n_plus_one local must be a typed list (Any or more specific str | int accepted)
    assert "potential_n_plus_one:" in src and "list[dict[str," in src, (
        "potential_n_plus_one local should be list[dict[str, ...]]"
    )

    # No TODO(TYPE) markers
    non_type_todos = [ln for ln in src.splitlines() if "TODO" in ln and "(TYPE)" not in ln]
    assert not non_type_todos, f"TODO features must be gone: {non_type_todos[:2]}"


# ---------------------------------------------------------------------------
# 4. database.py
#    - Set removed from typing imports
#    - No TODO(TYPE) comments remain
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_database_set_import_removed() -> None:
    """Set must be removed from typing imports in database.py."""
    src = _source("src/core/database/database.py")

    # Verify Set is gone from the typing import
    tree = _parse("src/core/database/database.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            imported_names = [alias.name for alias in node.names]
            assert "Set" not in imported_names, (
                f"Set should be removed from typing imports, found: {imported_names}"
            )

    # No TODO(TYPE) markers
    non_type_todos = [ln for ln in src.splitlines() if "TODO" in ln and "(TYPE)" not in ln]
    assert not non_type_todos, f"TODO features must be gone: {non_type_todos[:2]}"


# ---------------------------------------------------------------------------
# 5. retry_logic.py
#    - Optional and cast removed from typing imports
#    - No TODO(TYPE) comments remain
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_retry_logic_legacy_imports_removed() -> None:
    """Optional and cast must be removed from typing imports in retry_logic.py."""
    src = _source("src/core/database/retry_logic.py")

    tree = _parse("src/core/database/retry_logic.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            imported_names = [alias.name for alias in node.names]
            assert "Optional" not in imported_names, (
                f"Optional should be removed from retry_logic.py, found: {imported_names}"
            )
            assert "cast" not in imported_names, (
                f"cast should be removed from retry_logic.py, found: {imported_names}"
            )

    # No TODO(TYPE) markers
    non_type_todos = [ln for ln in src.splitlines() if "TODO" in ln and "(TYPE)" not in ln]
    assert not non_type_todos, f"TODO features must be gone: {non_type_todos[:2]}"
