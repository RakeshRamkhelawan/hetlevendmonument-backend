"""
SP-TYPE-01 dag 8 -- type-annotation tests for v1/agentic/learning.py
and v1/system/llm_health.py.

RED before refactoring, GREEN after.
"""

import ast
from pathlib import Path

import pytest

_LEARNING = Path("src/core/api/v1/agentic/learning.py")
_LLM = Path("src/core/api/v1/system/llm_health.py")


def _param_ann(filepath: Path, fn_name: str, param: str) -> str:
    tree = ast.parse(filepath.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == fn_name:
            for arg in node.args.args + node.args.kwonlyargs:
                if arg.arg == param and arg.annotation:
                    return ast.unparse(arg.annotation)
    return "NOT_FOUND"


def _local_ann(filepath: Path, fn_name: str, var: str) -> str:
    tree = ast.parse(filepath.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == fn_name:
            for stmt in ast.walk(node):
                if (
                    isinstance(stmt, ast.AnnAssign)
                    and isinstance(stmt.target, ast.Name)
                    and stmt.target.id == var
                ):
                    return ast.unparse(stmt.annotation)
    return "NOT_FOUND"


# --- learning.py tests ---


@pytest.mark.unit
def test_learning_current_user_is_user_response() -> None:
    """_current_user in learning endpoints must be UserResponse, not Any."""
    from src.core.auth.auth_service import UserResponse

    ann = _param_ann(_LEARNING, "get_learning_insights", "_current_user")
    assert ann == "UserResponse", f"Expected UserResponse, got {ann}"


@pytest.mark.unit
def test_learning_all_endpoints_have_user_response() -> None:
    """All 11 learning endpoints must type _current_user as UserResponse."""
    endpoints = [
        "get_learning_insights",
        "get_insight",
        "get_adaptation_rules",
        "create_adaptation",
        "activate_adaptation",
        "deactivate_adaptation",
        "get_adaptation_stats",
        "get_feedback_trends",
        "get_learning_stats",
        "trigger_feedback_analysis",
        "get_learning_patterns",
    ]
    for name in endpoints:
        ann = _param_ann(_LEARNING, name, "_current_user")
        assert ann == "UserResponse", f"{name}._current_user: expected UserResponse, got {ann}"


# --- llm_health.py tests ---


@pytest.mark.unit
def test_llm_health_current_user_is_user_response() -> None:
    """current_user in llm_health endpoints must be UserResponse, not Any."""
    for fn in (
        "llm_health_check",
        "llm_test_prompt",
        "llm_providers_info",
        "llm_switch_provider",
        "llm_metrics",
    ):
        ann = _param_ann(_LLM, fn, "current_user")
        assert ann == "UserResponse", f"{fn}.current_user: expected UserResponse, got {ann}"


@pytest.mark.unit
def test_llm_target_is_llm_provider_type() -> None:
    """target local var in llm_switch_provider must be LLMProviderType, not Any."""
    ann = _local_ann(_LLM, "llm_switch_provider", "target")
    assert ann == "LLMProviderType", f"Expected LLMProviderType, got {ann}"
