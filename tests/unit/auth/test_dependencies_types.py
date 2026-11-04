"""Type-contract tests for src.core.auth.dependencies."""

from __future__ import annotations

import ast
import inspect
from typing import Any

import pytest

from src.core.auth.dependencies import (
    _get_user_from_token,
    get_current_user_id,
    get_current_user_ws,
)


def _function_has_local_annotation(func: Any, var_name: str, annotation: str) -> bool:
    """Return True if *func* assigns *var_name* with the given annotation."""
    source = inspect.getsource(func)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == var_name:
                return ast.unparse(node.annotation) == annotation
    return False


@pytest.mark.unit
class TestDependenciesTypeContract:
    """Ensure auth.dependencies uses VerifiedJWTPayload for decoded tokens."""

    def test_get_user_from_token_payload_typed(self) -> None:
        assert _function_has_local_annotation(
            _get_user_from_token, "payload", "VerifiedJWTPayload | None"
        ), "_get_user_from_token payload must be typed VerifiedJWTPayload | None"

    def test_get_user_from_token_rejects_none_payload(self) -> None:
        source = inspect.getsource(_get_user_from_token)
        assert "if payload is None:" in source
        assert "raise _credentials_exception()" in source

    def test_get_current_user_id_payload_typed(self) -> None:
        assert _function_has_local_annotation(
            get_current_user_id, "payload", "VerifiedJWTPayload | None"
        ), "get_current_user_id payload must be typed VerifiedJWTPayload | None"

    def test_get_current_user_ws_rejects_missing_token(self) -> None:
        source = inspect.getsource(get_current_user_ws)
        assert "if not token:" in source
        assert "status.HTTP_401_UNAUTHORIZED" in source
