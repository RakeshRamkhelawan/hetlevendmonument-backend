"""Type-contract tests for src.core.api.auth.router_token."""

from __future__ import annotations

import ast
import inspect
from typing import Any

import pytest

from src.core.api.auth import router_token


def _function_has_local_annotation(module: Any, func_name: str, var_name: str, annotation: str) -> bool:
    """Return True if *func_name* in *module* assigns *var_name* with the given annotation."""
    source = inspect.getsource(module)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            for child in ast.walk(node):
                if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                    if child.target.id == var_name:
                        return ast.unparse(child.annotation) == annotation
    return False


def _function_calls_method(module: Any, func_name: str, obj_name: str, method_name: str) -> bool:
    """Return True if *func_name* in *module* calls *obj_name*.*method_name*().

    Mutatiebewijs:
    - Verwijder de aanroep -> False (guard rood).
    - Houd de aanroep -> True (guard groen).
    """
    source = inspect.getsource(module)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and isinstance(child.func.value, ast.Name)
                    and child.func.value.id == obj_name
                    and child.func.attr == method_name
                ):
                    return True
    return False


@pytest.mark.unit
class TestRouterTokenTypeContract:
    """Ensure router_token endpoints type decode payloads as VerifiedJWTPayload."""

    def test_revoke_token_payload_typed(self) -> None:
        assert _function_has_local_annotation(
            router_token, "revoke_token_endpoint", "payload", "VerifiedJWTPayload | None"
        ), "revoke_token payload must be typed VerifiedJWTPayload | None"

    def test_validate_token_payload_typed(self) -> None:
        assert _function_has_local_annotation(
            router_token, "validate_token", "payload", "VerifiedJWTPayload | None"
        ), "validate_token payload must be typed VerifiedJWTPayload | None"

    def test_verify_token_endpoint_payload_typed(self) -> None:
        assert _function_has_local_annotation(
            router_token, "verify_token_endpoint", "payload", "VerifiedJWTPayload | None"
        ), "verify_token_endpoint payload must be typed VerifiedJWTPayload | None"

    def test_logout_endpoint_calls_revoke_token(self) -> None:
        """logout_endpoint moet oauth2_service.revoke_token() aanroepen (niet Redis).

        OP-188 (2026-09-30): logout_endpoint delegeert token-intrekking aan revoke_token(),
        die naar PostgreSQL-tabel TokenBlacklist schrijft. De eerdere Redis-schrijfactie
        was ontkoppeld van de leeskant (is_jti_revoked) -- het defect.

        Mutatiebewijs: verwijder de revoke_token()-aanroep uit logout_endpoint ->
        _function_calls_method geeft False en deze test wordt rood.
        """
        assert _function_calls_method(
            router_token, "logout_endpoint", "oauth2_service", "revoke_token"
        ), "logout_endpoint moet oauth2_service.revoke_token() aanroepen -- niet Redis setex (OP-188)"
