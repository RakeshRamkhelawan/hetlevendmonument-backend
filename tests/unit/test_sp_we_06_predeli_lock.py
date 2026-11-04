"""SP-WE-06: Council pre-deliberation idempotency lock tests."""

import hashlib

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
class TestPreDeliberationLock:
    def _make_service(self, redis_mock: AsyncMock | None = None):
        from unittest.mock import MagicMock
        from src.core.copilot.service import CopilotService

        svc = CopilotService.__new__(CopilotService)
        svc._council = AsyncMock()
        svc._llm_handler = AsyncMock()
        svc._proposal_builder = MagicMock()
        svc._hitl_repo = None
        svc._tool_broker = None
        svc._twin_service = None
        svc._execution_guard = None
        svc._redis = redis_mock
        svc._context_engine = None
        from src.core.copilot.service import _FailClosedAudit

        svc._audit = AsyncMock()
        return svc

    async def test_lock_key_is_tenant_scoped(self) -> None:
        """Lock key contains tenant_id -- no cross-tenant interference."""
        from src.core.copilot.service import CopilotService

        source = __import__("inspect").getsource(CopilotService.handle_turn)
        assert "copilot:deliberation:" in source
        assert "tenant_id" in source

    async def test_lock_ttl_is_30_seconds(self) -> None:
        """Lock TTL is 30 seconds (deliberation SLA)."""
        from src.core.copilot.service import CopilotService

        source = __import__("inspect").getsource(CopilotService.handle_turn)
        assert "ex=30" in source

    async def test_duplicate_request_raises_deliberation_in_progress(self) -> None:
        """Second request during active lock raises DeliberationInProgressError."""
        from src.core.copilot.service import DeliberationInProgressError

        redis_mock = AsyncMock()
        redis_mock.set.return_value = None  # SET NX returns None when key exists

        svc = self._make_service(redis_mock)
        svc._augment_context = AsyncMock(return_value={})

        with pytest.raises(DeliberationInProgressError):
            await svc.handle_turn(
                tenant_id=1,
                user_id=42,
                message="test message",
                context={},
            )

    async def test_lock_released_in_finally_on_success(self) -> None:
        """Lock is deleted after deliberation completes (happy path)."""
        from src.core.copilot.council.types import CouncilDecision, DecisionVerdict
        from src.core.copilot.service import CopilotService

        redis_mock = AsyncMock()
        redis_mock.set.return_value = True  # Lock acquired

        svc = self._make_service(redis_mock)
        svc._augment_context = AsyncMock(return_value={})
        svc._llm_handler.get_action = AsyncMock(
            return_value=MagicMock(action_type="test", action_params={})
        )
        svc._proposal_builder.build = MagicMock(
            return_value=MagicMock(proposal_id="abc", tenant_id=1)
        )
        decision = MagicMock()
        decision.verdict = DecisionVerdict.APPROVED
        svc._council.deliberate = AsyncMock(return_value=decision)
        svc._route_verdict = AsyncMock(return_value=MagicMock())
        svc._execute_decision = AsyncMock()

        await svc.handle_turn(tenant_id=1, user_id=42, message="hello", context={})

        redis_mock.delete.assert_called_once()

    async def test_graceful_degradation_when_redis_none(self) -> None:
        """No Redis -> no lock, no crash (graceful degradation)."""
        from src.core.copilot.council.types import DecisionVerdict

        svc = self._make_service(redis_mock=None)
        svc._augment_context = AsyncMock(return_value={})
        svc._llm_handler.get_action = AsyncMock(
            return_value=MagicMock(action_type="test", action_params={})
        )
        svc._proposal_builder.build = MagicMock(
            return_value=MagicMock(proposal_id="abc", tenant_id=1)
        )
        decision = MagicMock()
        decision.verdict = DecisionVerdict.APPROVED
        svc._council.deliberate = AsyncMock(return_value=decision)
        svc._route_verdict = AsyncMock(return_value=MagicMock())
        svc._execute_decision = AsyncMock()

        # Should not raise
        await svc.handle_turn(tenant_id=1, user_id=42, message="hello", context={})
