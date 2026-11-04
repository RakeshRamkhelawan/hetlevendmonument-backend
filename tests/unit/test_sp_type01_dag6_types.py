"""
SP-TYPE-01 dag 6 -- type-annotation tests for collaboration_endpoints_complex.py
and ai_features_endpoints.py.

RED before refactoring, GREEN after.
"""

import ast
from pathlib import Path

import pytest

_COLLAB = Path("src/core/api/collaboration_endpoints_complex.py")
_AI = Path("src/core/api/v1/ai_features/routing_router.py")


def _get_local_annotation(filepath: Path, fn_name: str, var_name: str) -> str:
    """Return the annotation of a local variable inside a function, as unparse'd string."""
    tree = ast.parse(filepath.read_text(encoding="utf-8-sig"))  # utf-8-sig handles BOM
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == fn_name:
            for stmt in ast.walk(node):
                if (
                    isinstance(stmt, ast.AnnAssign)
                    and isinstance(stmt.target, ast.Name)
                    and stmt.target.id == var_name
                ):
                    return ast.unparse(stmt.annotation)
    return "NOT_FOUND"


def _get_param_annotation(filepath: Path, fn_name: str, param_name: str) -> str:
    """Return the annotation of a function parameter, as unparse'd string."""
    tree = ast.parse(filepath.read_text(encoding="utf-8-sig"))  # utf-8-sig handles BOM
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == fn_name:
            for arg in node.args.args + node.args.kwonlyargs:
                if arg.arg == param_name and arg.annotation:
                    return ast.unparse(arg.annotation)
    return "NOT_FOUND"


@pytest.mark.unit
def test_register_agent_capabilities_is_list_str() -> None:
    """capabilities local variable in register_agent must be list[str], not list[Any]."""
    annotation = _get_local_annotation(_COLLAB, "register_agent", "capabilities")
    assert annotation == "list[str]", f"Expected list[str], got {annotation}"


@pytest.mark.unit
def test_receive_messages_processed_is_list_dict() -> None:
    """processed_messages in receive_messages must be list[dict[str, Any]], not list[Any]."""
    annotation = _get_local_annotation(_COLLAB, "receive_messages", "processed_messages")
    assert annotation == "list[dict[str, Any]]", f"Expected list[dict[str, Any]], got {annotation}"


@pytest.mark.unit
def test_get_routing_decisions_router_is_intelligent_router() -> None:
    """router_instance param in get_routing_decisions must be IntelligentRouter, not Any."""
    annotation = _get_param_annotation(_AI, "route_request", "router_instance")
    assert annotation == "IntelligentRouter", f"Expected IntelligentRouter, got {annotation}"
