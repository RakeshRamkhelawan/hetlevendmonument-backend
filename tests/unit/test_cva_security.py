"""Security tests for CVA service.

Ref: CVA Audit Phase 1 - Critical Security Fixes
"""

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.services.cva_service import CVAService


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def cva_service(mock_db):
    with patch("src.core.services.cva_service.LLMService"):
        return CVAService(db_session=mock_db)


class TestGetConversationTenantIsolation:
    """_get_conversation must use a SINGLE query with tenant_id + user_id."""

    @pytest.mark.asyncio
    async def test_cross_tenant_returns_same_error_as_missing(self, cva_service, mock_db):
        """
        Requesting conversation 42 as tenant_id=2 when it belongs to
        tenant_id=1 MUST raise the same error as a non-existent id.
        """
        # Simulate: conversation exists for tenant 1, caller is tenant 2
        # Single query with all filters returns None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Conversation not found or access denied"):
            await cva_service._get_conversation(conversation_id=42, user_id=1, tenant_id=2)

    @pytest.mark.asyncio
    async def test_nonexistent_conversation_same_error(self, cva_service, mock_db):
        """Non-existent conversation must produce identical error message."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Conversation not found or access denied"):
            await cva_service._get_conversation(conversation_id=9999, user_id=1, tenant_id=1)

    @pytest.mark.asyncio
    async def test_single_query_includes_all_filters(self, cva_service, mock_db):
        """The SQL query must filter on id + user_id + tenant_id + is_active in ONE query."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError):
            await cva_service._get_conversation(conversation_id=1, user_id=1, tenant_id=1)

        # Verify: execute called exactly ONCE (not two-step)
        assert mock_db.execute.call_count == 1

        # Verify: the compiled SQL contains all four filters
        call_args = mock_db.execute.call_args
        query = call_args[0][0]
        compiled = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id" in compiled
        assert "user_id" in compiled
        assert "is_active" in compiled


class TestNoDebugPrints:
    """Production code must not contain print() calls."""

    def test_cva_service_has_no_print_calls(self):
        source_path = Path("src/core/services/cva_service.py")
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        print_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "print":
                    print_calls.append(node.lineno)

        assert print_calls == [], (
            f"Found print() calls at lines: {print_calls}. " "Use logger.debug() instead."
        )


class TestNoFileWrites:
    """Endpoints must not write to the filesystem directly."""

    def test_cva_endpoints_no_open_file_write(self):
        source_path = Path("src/core/api/cva_endpoints.py")
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        open_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "open":
                    open_calls.append(node.lineno)

        assert open_calls == [], (
            f"Found open() calls at lines: {open_calls}. "
            "Use structured logging instead of file writes."
        )


class TestNoGlobalSingletonAgent:
    """CVA agent must not be a single global singleton."""

    def test_no_module_level_cva_agent_variable(self):
        source_path = Path("src/core/api/cva_endpoints.py")
        source = source_path.read_text(encoding="utf-8")

        # The old pattern: _cva_agent: Optional[...] = None at module level
        assert "_cva_agent:" not in source or "_cva_agent: " not in source, (
            "Module-level _cva_agent singleton found. " "Use per-tenant caching instead."
        )

    def test_get_cva_agent_requires_tenant_id(self):
        """get_cva_agent() must require tenant_id parameter."""
        source_path = Path("src/core/api/cva_endpoints.py")
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_cva_agent":
                param_names = [arg.arg for arg in node.args.args]
                assert "tenant_id" in param_names, "get_cva_agent() must accept tenant_id parameter"
                return

        # If function not found as async, check regular def
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_cva_agent":
                param_names = [arg.arg for arg in node.args.args]
                assert "tenant_id" in param_names, "get_cva_agent() must accept tenant_id parameter"
                return

        pytest.skip("get_cva_agent function not found")


class TestNoInternalErrorExposure:
    """500 responses must not include internal error details."""

    def test_generic_500_error_detail(self):
        source_path = Path("src/core/api/cva_endpoints.py")
        source = source_path.read_text(encoding="utf-8")

        # Should not interpolate exception message into HTTP response
        assert 'detail=f"CVA chat failed: {str(e)}"' not in source, (
            "Internal error details exposed to client via HTTPException detail. "
            "Use a generic message and log the actual error server-side."
        )
