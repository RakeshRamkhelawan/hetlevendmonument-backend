"""SP-S02: Tests for HITL cleanup_expired tenant filter (B-018) + security tests (B-019).

B-018: cleanup_expired() has no tenant_id WHERE clause -- cross-tenant ticket modification.
B-019: test_security.py contains only skip/pass tests -- security regressions go undetected.
"""

import pathlib
import pytest

_ROOT = pathlib.Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# DAG 1 -- B-018: HITL cleanup_expired tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
class TestHITLCleanupExpiredTenantIsolation:
    def test_cleanup_expired_accepts_tenant_id_parameter(self) -> None:
        """cleanup_expired() must accept a tenant_id parameter (B-018)."""
        import inspect
        from src.core.tool_broker.hitl_repository import HITLTicketRepository

        sig = inspect.signature(HITLTicketRepository.cleanup_expired)
        assert "tenant_id" in sig.parameters, (
            "HITLTicketRepository.cleanup_expired() has no tenant_id parameter -- "
            "cross-tenant ticket modification possible (B-018)"
        )

    def test_cleanup_expired_has_tenant_where_clause(self) -> None:
        """cleanup_expired() must filter on tenant_id in the WHERE clause."""
        source = (_ROOT / "src/core/tool_broker/hitl_repository.py").read_text()
        lines = source.splitlines()
        in_cleanup = False
        has_tenant_filter = False
        for line in lines:
            if "def cleanup_expired" in line:
                in_cleanup = True
            if (
                in_cleanup
                and "tenant_id" in line
                and ("where" in line.lower() or "filter" in line.lower() or "==" in line)
            ):
                has_tenant_filter = True
                break
            # Stop looking after the next function definition
            if in_cleanup and line.strip().startswith("def ") and "cleanup_expired" not in line:
                break
        assert has_tenant_filter, (
            "cleanup_expired() has no tenant_id WHERE clause -- "
            "cross-tenant UPDATE affects ALL tenants (B-018)"
        )

    def test_cleanup_expired_does_not_bypass_tenant_filter(self) -> None:
        """cleanup_expired() must NOT use a blank or None tenant_id guard."""
        source = (_ROOT / "src/core/tool_broker/hitl_repository.py").read_text()
        # The old cross-tenant pattern: no tenant_id in the function at all
        # We verify by checking the function signature (done above), but also
        # check that the actor in actors.py no longer passes zero arguments.
        actors_source = (_ROOT / "src/workers/actors.py").read_text()
        # Old call: "await repo.cleanup_expired()" with no args
        # New call must pass tenant_id
        assert "await repo.cleanup_expired()" not in actors_source, (
            "actors.py still calls cleanup_expired() without tenant_id -- B-018 not fully fixed. "
            "The actor must loop over tenant_ids and pass each one."
        )

    @pytest.mark.asyncio
    async def test_cleanup_expired_only_updates_given_tenant(self) -> None:
        """cleanup_expired(tenant_id=1) must NOT update tickets of tenant 2."""
        from datetime import datetime, timedelta, timezone
        from unittest.mock import AsyncMock, MagicMock, call

        from src.core.tool_broker.hitl_repository import HITLTicketRepository

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db.execute = AsyncMock(return_value=mock_result)
        db.commit = AsyncMock()

        repo = HITLTicketRepository(db)
        count = await repo.cleanup_expired(tenant_id=1)

        # Verify execute was called
        assert db.execute.called, "cleanup_expired() must call db.execute()"

        # Extract the compiled WHERE clause from the call to verify tenant_id is in it
        call_args = db.execute.call_args
        stmt = call_args[0][0]  # first positional arg is the SQLAlchemy statement
        # Compile the statement and check that tenant_id constraint is present
        from sqlalchemy.dialects import postgresql

        compiled = stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
        compiled_str = str(compiled)
        assert "tenant_id = 1" in compiled_str or "hitlticket.tenant_id = 1" in compiled_str, (
            "cleanup_expired(tenant_id=1) does not filter on tenant_id = 1 in the compiled SQL"
        )
        assert count == 1


# ---------------------------------------------------------------------------
# DAG 2 -- B-019: Real security tests (replaces skip/pass theater)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
class TestSecurityTestFileIsNotTheater:
    """Meta-tests: verify test_security.py has been de-theatered."""

    def test_security_file_has_no_skip_markers(self) -> None:
        """test_security.py must have no @pytest.mark.skip decorators (B-019)."""
        source = (_ROOT / "tests/unit/test_security.py").read_text()
        assert "@pytest.mark.skip" not in source, (
            "test_security.py still contains @pytest.mark.skip -- security theater (B-019)"
        )

    def test_security_file_has_no_bare_pass_tests(self) -> None:
        """test_security.py must have no tests that are just 'pass' (B-019)."""
        import ast

        source = (_ROOT / "tests/unit/test_security.py").read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    body = node.body
                    # A test that is only 'pass' (possibly with a docstring)
                    non_doc = [
                        n
                        for n in body
                        if not (
                            isinstance(n, ast.Expr)
                            and isinstance(n.value, ast.Constant)
                            and isinstance(n.value.value, str)
                        )
                    ]
                    is_pass_only = len(non_doc) == 1 and isinstance(non_doc[0], ast.Pass)
                    assert not is_pass_only, (
                        f"test_security.py::{node.name} is still a bare pass -- "
                        "security theater (B-019)"
                    )

    def test_security_file_has_at_least_ten_real_tests(self) -> None:
        """test_security.py must have >= 10 non-skip, non-pass tests (B-019)."""
        import ast

        source = (_ROOT / "tests/unit/test_security.py").read_text()
        tree = ast.parse(source)
        real_tests = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    # Has skip decorator?
                    has_skip = any(
                        (isinstance(d, ast.Attribute) and d.attr == "skip")
                        or (
                            isinstance(d, ast.Call)
                            and isinstance(d.func, ast.Attribute)
                            and d.func.attr == "skip"
                        )
                        for d in node.decorator_list
                    )
                    if has_skip:
                        continue
                    # Is just pass?
                    non_doc = [
                        n
                        for n in node.body
                        if not (
                            isinstance(n, ast.Expr)
                            and isinstance(n.value, ast.Constant)
                            and isinstance(n.value.value, str)
                        )
                    ]
                    is_pass_only = len(non_doc) == 1 and isinstance(non_doc[0], ast.Pass)
                    if not is_pass_only:
                        real_tests += 1
        assert real_tests >= 10, (
            f"test_security.py has only {real_tests} real tests -- need >= 10 (B-019)"
        )
