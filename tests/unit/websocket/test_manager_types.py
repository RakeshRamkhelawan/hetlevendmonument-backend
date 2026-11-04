"""Type-contract tests for src.core.websocket.manager."""

from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any

import pytest

from src.core.websocket.manager import ConnectionManager


def _function_has_local_annotation(func: Any, var_name: str, annotation: str) -> bool:
    """Return True if *func* assigns *var_name* with the given annotation."""
    source = inspect.getsource(func)
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == var_name:
                return ast.unparse(node.annotation) == annotation
    return False


@pytest.mark.unit
class TestConnectionManagerTypeContract:
    """Ensure ConnectionManager uses VerifiedJWTPayload for decoded tokens."""

    def test_connect_payload_typed(self) -> None:
        assert _function_has_local_annotation(
            ConnectionManager.connect, "payload", "VerifiedJWTPayload | None"
        ), "ConnectionManager.connect payload must be typed VerifiedJWTPayload | None"

    def test_connect_gives_an_anonymous_connection_no_tenant(self) -> None:
        # Hier stond `assert "tenant_id: int = 1" in source`: deze test legde de standaardtenant
        # vast die acceptant scenario 5 (2026-10-05) als beveiligingsfout aanwees. Een verbinding
        # zonder token hoort bij geen tenant; het gedrag staat in test_geen_standaardtenant.py.
        source = inspect.getsource(ConnectionManager.connect)
        assert "tenant_id: int | None = None" in source
