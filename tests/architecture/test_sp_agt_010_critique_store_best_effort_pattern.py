"""SP-AGT-010 architecture invariant: DB writes in CritiqueStore are best-effort wrapped.

Verifieert dat _persist_to_db() en _refresh_mv() in src/core/agents/critique_store.py
de database-sessie openen BINNEN een best_effort async-with context. Dit is patroon-3
uit de quality gates: audit-adjacent / secondary DB writes mogen nooit de primaire
operatie laten falen.
"""

import ast
from pathlib import Path

import pytest


def _critique_store_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "core"
        / "agents"
        / "critique_store.py"
    )


def _method_node(source_path: Path, class_name: str, method_name: str) -> ast.AsyncFunctionDef:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for class_node in ast.walk(tree):
        if isinstance(class_node, ast.ClassDef) and class_node.name == class_name:
            for item in class_node.body:
                if isinstance(item, ast.AsyncFunctionDef) and item.name == method_name:
                    return item
    raise AssertionError(f"{class_name}.{method_name} not found in {source_path}")


def _is_session_inside_best_effort(method_node: ast.AsyncFunctionDef) -> bool:
    """Return True if db_manager.get_session() is inside a best_effort async-with."""
    for node in ast.walk(method_node):
        if not isinstance(node, (ast.AsyncWith, ast.With)):
            continue

        uses_best_effort = any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Name)
            and item.context_expr.func.id == "best_effort"
            for item in node.items
        )
        if not uses_best_effort:
            continue

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Attribute) and func.attr == "get_session":
                    return True
                if isinstance(func, ast.Name) and func.id == "get_session":
                    return True
    return False


@pytest.mark.architecture
def test_persist_to_db_session_inside_best_effort() -> None:
    """_persist_to_db opent get_session binnen best_effort."""
    method = _method_node(_critique_store_path(), "CritiqueStore", "_persist_to_db")
    assert _is_session_inside_best_effort(method), (
        "_persist_to_db must open db_manager.get_session() inside a best_effort context"
    )


@pytest.mark.architecture
def test_refresh_mv_session_inside_best_effort() -> None:
    """_refresh_mv opent get_session binnen best_effort."""
    method = _method_node(_critique_store_path(), "CritiqueStore", "_refresh_mv")
    assert _is_session_inside_best_effort(method), (
        "_refresh_mv must open db_manager.get_session() inside a best_effort context"
    )
