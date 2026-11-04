"""
SP-TYPE Batch A -- AST annotation tests for auth + security files.

Files covered:
  - src/core/auth/jwt_handler.py           (5 violations -> all SKIP)
  - src/core/security/tenant_validation.py (5 violations -> all SKIP)

All violations are SKIP (HIGH-confidence analysis):

jwt_handler.py:
  - dict[str, Any] for JWT payload: python-jose jwt.decode() returns
    dict[str, Any]. JWT payload values are heterogeneous (str, int, list,
    datetime, custom claims). A TypedDict would require total=False and still
    expose Any for extension claims. SKIP.
  - _LazyProxy Any params (factory, _instance, __getattr__, __call__): this is
    a generic proxy pattern; narrowing requires Generic[T] + TypeVar which would
    change the public API and interaction with FastAPI dependency injection.
    SKIP.
  - create_token_pair user_data: dict[str, Any]: callers pass varying extra
    claims. Return type is already dict[str, str] (both tokens are str). SKIP.

tenant_validation.py:
  - Callable[..., Any] in decorator factories (validate_tenant_access,
    require_tenant_id): narrowing requires ParamSpec + TypeVar. Known CLAUDE.md
    valkuil: functools.wraps + __future__ annotations breaks FastAPI body
    parameter detection. Risk outweighs benefit. SKIP.
  - resource_id: Any / model_class: Any in verify_tenant_isolation: no external
    callers found; the function is only called by enforce_tenant_isolation which
    passes them through unchanged. SKIP.
  - agent: Any in TenantContext: wraps any agent object. SKIP.

These tests verify structural invariants that must remain true regardless of
future type changes:
  - Return types of security-critical methods stay correct.
  - tenant_id parameters stay int (never Any, str, or optional).
  - __all__ export list stays complete.
  - Callable return types on decorators remain (not removed by mistake).
"""

import ast
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


def _parse(rel_path: str) -> ast.Module:
    return ast.parse((_SRC_ROOT / rel_path).read_text(encoding="utf-8"))


def _method_return(tree: ast.Module, class_name: str, method_name: str) -> str | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in ast.walk(node):
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == method_name
                    and item.returns is not None
                ):
                    return ast.unparse(item.returns)
    return None


def _toplevel_return(tree: ast.Module, func_name: str) -> str | None:
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
            and node.returns is not None
        ):
            return ast.unparse(node.returns)
    return None


def _param_annotation(tree: ast.Module, func_name: str, param_name: str) -> str | None:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            for arg in node.args.args:
                if arg.arg == param_name and arg.annotation is not None:
                    return ast.unparse(arg.annotation)
    return None


def _method_param_annotation(
    tree: ast.Module, class_name: str, method_name: str, param_name: str
) -> str | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in ast.walk(node):
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == method_name
                ):
                    for arg in item.args.args:
                        if arg.arg == param_name and arg.annotation is not None:
                            return ast.unparse(arg.annotation)
    return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def jwt_tree() -> ast.Module:
    return _parse("core/auth/jwt_handler.py")


@pytest.fixture(scope="module")
def tenant_tree() -> ast.Module:
    return _parse("core/security/tenant_validation.py")


# ---------------------------------------------------------------------------
# jwt_handler.py -- JWTHandler method return types
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJwtHandlerReturnAnnotations:
    """Return type invariants for JWTHandler methods."""

    def test_verify_token_returns_verified_payload_union_none(
        self, jwt_tree: ast.Module
    ) -> None:
        """verify_token -> VerifiedJWTPayload | None."""
        ret = _method_return(jwt_tree, "JWTHandler", "verify_token")
        assert ret is not None, "verify_token must have a return annotation"
        assert "VerifiedJWTPayload" in ret, f"Expected VerifiedJWTPayload in return type, got: {ret}"
        assert "None" in ret, f"Expected None in return type, got: {ret}"

    def test_verify_token_with_blacklist_returns_verified_payload_union_none(
        self, jwt_tree: ast.Module
    ) -> None:
        """verify_token_with_blacklist -> VerifiedJWTPayload | None."""
        ret = _method_return(jwt_tree, "JWTHandler", "verify_token_with_blacklist")
        assert ret is not None
        assert "VerifiedJWTPayload" in ret
        assert "None" in ret

    def test_create_access_token_returns_str(self, jwt_tree: ast.Module) -> None:
        """create_access_token -> str (encoded JWT string)."""
        ret = _method_return(jwt_tree, "JWTHandler", "create_access_token")
        assert ret == "str", f"Expected 'str', got: {ret}"

    def test_create_token_pair_returns_dict_str_str(self, jwt_tree: ast.Module) -> None:
        """create_token_pair -> dict[str, str] (both tokens are plain strings).

        This is the one field that was already narrowed from dict[str, Any]
        to dict[str, str] -- verify the narrowing stays in place.
        """
        ret = _method_return(jwt_tree, "JWTHandler", "create_token_pair")
        assert ret is not None, "create_token_pair must have a return annotation"
        assert "dict" in ret and "str" in ret, f"Expected dict[str, str], got: {ret}"
        assert "Any" not in ret, (
            "create_token_pair must return dict[str, str], not dict[str, Any]; "
            "this narrowing was already applied -- do not revert it"
        )

    def test_hash_password_returns_str(self, jwt_tree: ast.Module) -> None:
        """hash_password -> str."""
        ret = _method_return(jwt_tree, "JWTHandler", "hash_password")
        assert ret == "str", f"Expected 'str', got: {ret}"

    def test_verify_password_returns_bool(self, jwt_tree: ast.Module) -> None:
        """verify_password -> bool (not Any, not int)."""
        ret = _method_return(jwt_tree, "JWTHandler", "verify_password")
        assert ret == "bool", f"Expected 'bool', got: {ret}"

    def test_get_secret_key_returns_str(self, jwt_tree: ast.Module) -> None:
        """_get_secret_key -> str."""
        ret = _method_return(jwt_tree, "JWTHandler", "_get_secret_key")
        assert ret == "str", f"Expected 'str', got: {ret}"

    def test_validate_secret_for_production_returns_bool(self, jwt_tree: ast.Module) -> None:
        """_validate_secret_for_production -> bool."""
        ret = _method_return(jwt_tree, "JWTHandler", "_validate_secret_for_production")
        assert ret == "bool", f"Expected 'bool', got: {ret}"


@pytest.mark.unit
class TestJwtHandlerLazyProxy:
    """_LazyProxy structural invariants."""

    def test_lazy_proxy_class_present(self, jwt_tree: ast.Module) -> None:
        """_LazyProxy class must exist in jwt_handler module."""
        names = [n.name for n in ast.walk(jwt_tree) if isinstance(n, ast.ClassDef)]
        assert "_LazyProxy" in names, "_LazyProxy class not found in jwt_handler.py"

    def test_lazy_proxy_get_instance_annotated(self, jwt_tree: ast.Module) -> None:
        """_LazyProxy._get_instance must carry a return annotation (even if Any)."""
        ret = _method_return(jwt_tree, "_LazyProxy", "_get_instance")
        assert ret is not None, "_get_instance must have a return annotation"

    def test_lazy_proxy_repr_returns_str(self, jwt_tree: ast.Module) -> None:
        """_LazyProxy.__repr__ -> str (not Any)."""
        ret = _method_return(jwt_tree, "_LazyProxy", "__repr__")
        assert ret == "str", f"__repr__ must return str, got: {ret}"

    def test_any_imported_from_typing(self, jwt_tree: ast.Module) -> None:
        """'Any' must be imported from typing (used for JWT dict payload)."""
        for node in ast.walk(jwt_tree):
            if isinstance(node, ast.ImportFrom) and node.module == "typing":
                names = [a.name for a in node.names]
                assert "Any" in names, f"'Any' not in typing imports: {names}"
                return
        pytest.fail("No 'from typing import ...' found in jwt_handler.py")


# ---------------------------------------------------------------------------
# tenant_validation.py -- security invariants
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTenantValidationAnnotations:
    """Return type and parameter invariants for tenant_validation.py."""

    def test_validate_tenant_access_returns_callable(self, tenant_tree: ast.Module) -> None:
        """validate_tenant_access must return a Callable (decorator factory)."""
        ret = _toplevel_return(tenant_tree, "validate_tenant_access")
        assert ret is not None, "validate_tenant_access must have a return annotation"
        assert "Callable" in ret, f"Expected Callable in return type, got: {ret}"

    def test_require_tenant_id_param_is_callable(self, tenant_tree: ast.Module) -> None:
        """require_tenant_id's 'func' parameter must be Callable."""
        ann = _param_annotation(tenant_tree, "require_tenant_id", "func")
        assert ann is not None, "'func' parameter must be annotated"
        assert "Callable" in ann, f"Expected Callable annotation, got: {ann}"

    def test_require_tenant_id_returns_callable(self, tenant_tree: ast.Module) -> None:
        """require_tenant_id -> Callable (returns the wrapped function)."""
        ret = _toplevel_return(tenant_tree, "require_tenant_id")
        assert ret is not None, "require_tenant_id must have a return annotation"
        assert "Callable" in ret, f"Expected Callable in return type, got: {ret}"

    def test_verify_tenant_isolation_returns_bool(self, tenant_tree: ast.Module) -> None:
        """verify_tenant_isolation -> bool (True = resource belongs to tenant)."""
        ret = _toplevel_return(tenant_tree, "verify_tenant_isolation")
        assert ret == "bool", f"Expected 'bool', got: {ret}"

    def test_verify_tenant_isolation_tenant_id_is_int(self, tenant_tree: ast.Module) -> None:
        """verify_tenant_isolation tenant_id must be int -- security invariant.

        tenant_id must never become Any or str, which would allow bypassing
        isolation checks.
        """
        ann = _param_annotation(tenant_tree, "verify_tenant_isolation", "tenant_id")
        assert ann == "int", f"tenant_id MUST be annotated as int (security invariant), got: {ann}"

    def test_enforce_tenant_isolation_returns_none(self, tenant_tree: ast.Module) -> None:
        """enforce_tenant_isolation -> None (raises PermissionError on violation)."""
        ret = _toplevel_return(tenant_tree, "enforce_tenant_isolation")
        assert ret == "None", f"Expected 'None', got: {ret}"

    def test_enforce_tenant_isolation_tenant_id_is_int(self, tenant_tree: ast.Module) -> None:
        """enforce_tenant_isolation tenant_id must be int -- security invariant."""
        ann = _param_annotation(tenant_tree, "enforce_tenant_isolation", "tenant_id")
        assert ann == "int", f"tenant_id MUST be annotated as int (security invariant), got: {ann}"

    def test_tenant_context_class_present(self, tenant_tree: ast.Module) -> None:
        """TenantContext class must exist."""
        names = [n.name for n in ast.walk(tenant_tree) if isinstance(n, ast.ClassDef)]
        assert "TenantContext" in names

    def test_tenant_context_aenter_returns_self_type(self, tenant_tree: ast.Module) -> None:
        """TenantContext.__aenter__ -> 'TenantContext' (async context manager protocol)."""
        ret = _method_return(tenant_tree, "TenantContext", "__aenter__")
        assert ret is not None, "__aenter__ must be annotated"
        assert "TenantContext" in ret, f"Expected TenantContext in return, got: {ret}"

    def test_tenant_context_temporary_tenant_id_param_is_int(self, tenant_tree: ast.Module) -> None:
        """TenantContext.__init__ temporary_tenant_id must be int -- security invariant."""
        ann = _method_param_annotation(
            tenant_tree, "TenantContext", "__init__", "temporary_tenant_id"
        )
        assert ann == "int", f"temporary_tenant_id MUST be int (security invariant), got: {ann}"

    def test_all_exports_complete(self, tenant_tree: ast.Module) -> None:
        """__all__ must export all 5 public names from tenant_validation."""
        expected = {
            "validate_tenant_access",
            "require_tenant_id",
            "verify_tenant_isolation",
            "enforce_tenant_isolation",
            "TenantContext",
        }
        for node in ast.walk(tenant_tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        names = set(
                            elt.value
                            for elt in node.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        )
                        missing = expected - names
                        assert not missing, f"Missing from __all__: {missing}"
                        return
        pytest.fail("__all__ not found in tenant_validation.py")
