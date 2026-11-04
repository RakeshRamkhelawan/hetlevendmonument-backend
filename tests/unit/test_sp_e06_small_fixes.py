"""
Tests for SP-E06: AdaptationService Redis injection, ALS ping, Tenant stats.

TDD: tests were RED before implementation and GREEN after (18/18 PASS verified).

Two fixes:
- Fix A: inject Redis into AdaptationRuleService (agentic/dependencies.py)
- Fix B: ALS ping sends real Signal via SignalBus (als/router.py)

NOTE: TestALSPing reads files via pathlib.Path to avoid inspect.getsource()
failure from __init__.py name shadowing (the als package exports
`router = APIRouter(...)` which shadows the submodule name).

NOTE: Fix C (TenantStats) tests moved to tests/unit/services/test_tenant_service.py
as part of AUDIT-DB-01 service-layer migration (BE-SVC-034).
"""

import inspect
import pathlib

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

_ROOT = pathlib.Path(__file__).parent.parent.parent


def _read_source(rel_path: str) -> str:
    return (_ROOT / rel_path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fix A -- AdaptationService Redis injection
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAdaptationServiceRedis:
    def test_redis_client_none_removed(self) -> None:
        """redis_client=None must not appear in adaptation service dependencies."""
        source = _read_source("src/core/api/v1/agentic/dependencies.py")
        assert "redis_client=None" not in source

    def test_redis_url_not_hardcoded(self) -> None:
        """No hardcoded redis:// URL in adaptation dependencies (CLAUDE.md Sec. 8)."""
        source = _read_source("src/core/api/v1/agentic/dependencies.py")
        assert "redis://localhost" not in source

    def test_get_redis_client_imported(self) -> None:
        """get_redis_client must be imported from src.core.database.redis."""
        source = _read_source("src/core/api/v1/agentic/dependencies.py")
        assert "get_redis_client" in source

    @pytest.mark.asyncio
    async def test_adaptation_service_receives_non_none_redis_behavioral(self) -> None:
        """Behavioral: create_cached_adaptation_service NOT called with redis_client=None."""
        mock_db = AsyncMock()
        mock_redis = MagicMock()

        with (
            patch(
                "src.core.api.v1.agentic.dependencies.get_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch(
                "src.core.api.v1.agentic.dependencies.create_cached_adaptation_service"
            ) as mock_create,
        ):
            mock_create.return_value = MagicMock()
            from src.core.api.v1.agentic.dependencies import get_adaptation_service

            await get_adaptation_service(db=mock_db)

            mock_create.assert_called_once()
            call_args, call_kwargs = mock_create.call_args
            redis_arg = call_kwargs.get(
                "redis_client", call_args[1] if len(call_args) > 1 else None
            )
            assert redis_arg is not None


# ---------------------------------------------------------------------------
# Fix B -- ALS ping via SignalBus
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestALSPing:
    _SRC = "src/core/api/v1/als/als_agents_router.py"

    def test_todo_comment_removed(self) -> None:
        """TODO placeholder comment must be removed from ALS ping endpoint."""
        assert "TODO: Implement ping via signal bus" not in _read_source(self._SRC)

    def test_signal_tier_used_in_router(self) -> None:
        """SignalTier must be present in ALS router."""
        assert "SignalTier" in _read_source(self._SRC)

    def test_emit_called_in_ping_function(self) -> None:
        """ping_agent function must call .emit."""
        assert ".emit(" in _read_source(self._SRC)

    def test_ping_response_has_success_field(self) -> None:
        """ALS ping response must follow standard {success, data} format (CLAUDE.md Sec. 12)."""
        source = _read_source(self._SRC)
        assert '"success"' in source or "'success'" in source

    def test_ping_timestamp_uses_timezone_utc(self) -> None:
        """Ping timestamp must use timezone-aware datetime (CLAUDE.md Sec. 3)."""
        source = _read_source(self._SRC)
        if "datetime.now" in source:
            assert "timezone.utc" in source or "timezone" in source

    @pytest.mark.asyncio
    async def test_als_ping_emits_signal_behavioral(self) -> None:
        """Behavioral: operator pings agent -> SignalBus.emit is called once."""
        mock_signal_bus = MagicMock()
        mock_signal_bus.emit = AsyncMock(return_value="signal-id-123")
        mock_orchestrator = MagicMock()
        mock_orchestrator.signal_bus = mock_signal_bus

        with patch(
            "src.core.api.v1.als.als_agents_router.get_orchestrator",  # ADR-033 Strangler Fig
            return_value=mock_orchestrator,
        ):
            from src.core.api.v1.als.als_agents_router import ping_agent

            result = await ping_agent(agent_id="agent-001", tenant_id=42)

        mock_signal_bus.emit.assert_called_once()
        assert result.get("success") is True
        assert result["data"]["agent_id"] == "agent-001"
        assert result["data"]["ping"] == "sent"
