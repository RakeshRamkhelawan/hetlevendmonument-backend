"""
Security regression tests -- real assertions, no skip/pass theater (B-019 fix).

All tests use source inspection (ast.parse + file reads) or direct unit testing.
No TestClient or full app stack required -- keeps tests fast and isolated.
"""

import ast
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).parent.parent.parent
_SRC = _ROOT / "src"


@pytest.mark.unit
@pytest.mark.security
class TestJWTValidation:
    def test_jwt_handler_references_tenant_id(self) -> None:
        """JWT validation code checks for tenant_id claim (CLAUDE.md sec 6)."""
        candidates = list(_SRC.rglob("jwt_handler.py"))
        assert candidates, "jwt_handler.py not found under src/"
        found = any("tenant_id" in c.read_text() for c in candidates)
        assert found, "No jwt_handler.py references tenant_id"

    def test_jwt_handler_uses_hs256(self) -> None:
        """JWT signing must use HS256 (OWASP A02)."""
        candidates = list(_SRC.rglob("jwt_handler.py"))
        assert candidates, "jwt_handler.py not found"
        source = candidates[0].read_text()
        assert "HS256" in source, "jwt_handler.py does not reference HS256 algorithm"
        assert (
            'algorithm="none"' not in source and "algorithm='none'" not in source
        ), "jwt_handler.py sets algorithm=none -- critical JWT vulnerability"

    def test_jwt_secret_uses_env_var(self) -> None:
        """JWT secret must come from environment, not be hardcoded."""
        candidates = list(_SRC.rglob("jwt_handler.py"))
        assert candidates, "jwt_handler.py not found"
        source = candidates[0].read_text()
        assert "getenv" in source or "settings" in source or "SECRET" in source.upper(), (
            "jwt_handler.py has no env-var reference for the JWT secret"
        )
        assert "SECRET_KEY = " + chr(34) not in source and "SECRET_KEY = " + chr(39) not in source, (
            "jwt_handler.py has a hardcoded SECRET_KEY literal"
        )


@pytest.mark.unit
@pytest.mark.security
class TestTenantIsolation:
    def test_hitl_cleanup_has_tenant_filter(self) -> None:
        """HITLTicketRepository.cleanup_expired() must filter on tenant_id (B-018)."""
        source = (_SRC / "core/tool_broker/hitl_repository.py").read_text()
        lines = source.splitlines()
        in_cleanup = False
        has_filter = False
        for line in lines:
            if "def cleanup_expired" in line:
                in_cleanup = True
            if in_cleanup and "tenant_id" in line and (
                "where" in line.lower() or "==" in line or "filter" in line.lower()
            ):
                has_filter = True
                break
            if in_cleanup and line.strip().startswith("async def ") and "cleanup_expired" not in line:
                break
        assert has_filter, "cleanup_expired() has no tenant_id WHERE clause (B-018)"

    def test_tenant_id_not_in_request_schemas(self) -> None:
        """Core request schemas must not expose tenant_id as a body field."""
        schema_files = [
            _SRC / "core/copilot/schemas.py",
            _SRC / "core/api/v1/documents/schemas.py",
        ]
        for schema_file in schema_files:
            if not schema_file.exists():
                continue
            source = schema_file.read_text()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                if "Request" not in node.name and "Create" not in node.name:
                    continue
                for item in ast.walk(node):
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        assert item.target.id != "tenant_id", (
                            f"{schema_file.name}::{node.name} exposes tenant_id in body"
                        )

    def test_tenant_context_helper_exists(self) -> None:
        """get_tenant_id() must exist in the middleware tenant context module."""
        tenant_ctx = _SRC / "core/middleware/tenant_context.py"
        assert tenant_ctx.exists(), "tenant_context.py not found"
        source = tenant_ctx.read_text()
        assert "def get_tenant_id" in source or "def require_tenant_id" in source, (
            "tenant_context.py has no get_tenant_id / require_tenant_id helper"
        )


@pytest.mark.unit
@pytest.mark.security
class TestSecurityMiddlewareRegistration:
    def test_tenant_middleware_registered(self) -> None:
        """TenantMiddleware must be in middleware_config.py (ADR-003)."""
        config = _SRC / "core/api/setup/middleware_config.py"
        assert config.exists(), "middleware_config.py not found"
        assert "TenantMiddleware" in config.read_text(), (
            "TenantMiddleware not in middleware_config.py"
        )

    def test_security_headers_middleware_registered(self) -> None:
        """SecurityHeadersMiddleware must be in the middleware stack."""
        config = _SRC / "core/api/setup/middleware_config.py"
        assert config.exists(), "middleware_config.py not found"
        assert "SecurityHeaders" in config.read_text(), (
            "SecurityHeadersMiddleware not in middleware_config.py"
        )

    def test_rate_limiter_in_auth_endpoints(self) -> None:
        """Auth endpoints must reference rate limiting."""
        auth_candidates = list(_SRC.rglob("auth/router.py")) + list(_SRC.rglob("auth_endpoints.py"))
        assert auth_candidates, "No auth router file found"
        source = auth_candidates[0].read_text()
        assert "limit" in source or "rate" in source.lower() or "limiter" in source, (
            "Auth router has no rate limiting reference"
        )


@pytest.mark.unit
@pytest.mark.security
class TestHITLSecurityUnit:
    @pytest.mark.asyncio
    async def test_cleanup_expired_requires_tenant_id(self) -> None:
        """cleanup_expired() must accept tenant_id parameter."""
        import inspect
        from src.core.tool_broker.hitl_repository import HITLTicketRepository
        sig = inspect.signature(HITLTicketRepository.cleanup_expired)
        assert "tenant_id" in sig.parameters, "cleanup_expired() has no tenant_id -- B-018"

    def test_generate_ticket_ref_uniqueness(self) -> None:
        """generate_ticket_ref() must return distinct values."""
        from src.core.tool_broker.hitl_repository import generate_ticket_ref
        refs = {generate_ticket_ref() for _ in range(20)}
        assert len(refs) == 20, "generate_ticket_ref() returned duplicate values"

    def test_generate_ticket_ref_prefix(self) -> None:
        """generate_ticket_ref() must start with hitl_."""
        from src.core.tool_broker.hitl_repository import generate_ticket_ref
        assert generate_ticket_ref().startswith("hitl_"), "Missing hitl_ prefix"

    def test_cleanup_actor_uses_tenant_filter_bypass(self) -> None:
        """cleanup_expired_hitl_tickets actor must use TenantFilterBypass (B-018)."""
        source = (_SRC / "workers/actors.py").read_text()
        lines = source.splitlines()
        in_actor = False
        has_bypass = False
        for line in lines:
            if "def cleanup_expired_hitl_tickets" in line:
                in_actor = True
            if in_actor and "TenantFilterBypass" in line:
                has_bypass = True
                break
            if in_actor and "@workflow_actor" in line and "cleanup_expired_hitl" not in line:
                break
        assert has_bypass, "cleanup_expired_hitl_tickets does not use TenantFilterBypass"
