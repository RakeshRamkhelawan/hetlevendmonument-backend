"""
SP-TYPE-01 dag 7 -- type-annotation tests for user_helpers.py and
v1/company/template_router.py.

RED before refactoring, GREEN after.
"""

import ast
from pathlib import Path

import pytest

_HELPERS = Path("src/core/api/user_helpers.py")
_TEMPLATE = Path("src/core/api/v1/company/template_router.py")


def _local_ann(filepath: Path, fn_name: str, var_name: str) -> str:
    tree = ast.parse(filepath.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef, ast.ClassDef))
            and getattr(node, "name", None) == fn_name
        ):
            for stmt in ast.walk(node):
                if (
                    isinstance(stmt, ast.AnnAssign)
                    and isinstance(stmt.target, ast.Name)
                    and stmt.target.id == var_name
                ):
                    return ast.unparse(stmt.annotation)
    return "NOT_FOUND"


@pytest.mark.unit
def test_get_user_id_local_vars_typed() -> None:
    """user_id and result locals in get_user_id must be int | None, not Any."""
    assert _local_ann(_HELPERS, "get_user_id", "user_id") == "int | None"
    assert _local_ann(_HELPERS, "get_user_id", "result") == "int | None"


@pytest.mark.unit
def test_get_user_email_local_vars_typed() -> None:
    """email and email_result locals in get_user_email must be str | None, not Any."""
    assert _local_ann(_HELPERS, "get_user_email", "email") == "str | None"
    assert _local_ann(_HELPERS, "get_user_email", "email_result") == "str | None"


@pytest.mark.unit
def test_get_user_tenant_id_local_vars_typed() -> None:
    """tenant_id and tenant_result locals must be int | None, not Any."""
    assert _local_ann(_HELPERS, "get_user_tenant_id", "tenant_id") == "int | None"
    assert _local_ann(_HELPERS, "get_user_tenant_id", "tenant_result") == "int | None"


@pytest.mark.unit
def test_get_user_role_id_local_vars_typed() -> None:
    """role_id and role_result locals must be int | None, not Any."""
    assert _local_ann(_HELPERS, "get_user_role_id", "role_id") == "int | None"
    assert _local_ann(_HELPERS, "get_user_role_id", "role_result") == "int | None"


@pytest.mark.unit
def test_simple_db_manager_session_typed() -> None:
    """SimpleDBManager._session must be AsyncSession, not Any."""
    ann = _local_ann(_TEMPLATE, "SimpleDBManager", "_session")
    assert ann == "AsyncSession", f"Expected AsyncSession, got {ann}"
