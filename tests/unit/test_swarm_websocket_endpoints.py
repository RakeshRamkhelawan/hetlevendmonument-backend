import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from src.core.api import swarm_websocket_endpoints as swarm_endpoints
from src.core.governance.ai_act_classifier import AIActRiskLevel
from src.core.governance.oversight_gate import OversightResult


class TestSwarmEndpoints:
    @pytest.mark.asyncio
    async def test_start_swarm_blocked_by_governance(self):
        mock_service = Mock()
        mock_user = Mock()
        mock_user.tenant_id = 7

        with patch.object(swarm_endpoints.manager, "get_service", return_value=mock_service):
            with patch("src.core.governance.oversight_gate.OversightGate") as gate_cls:
                gate_cls.return_value.check = AsyncMock(
                    return_value=OversightResult(
                        allowed=False,
                        requires_human_approval=False,
                        risk_level=AIActRiskLevel.HIGH_RISK,
                        reason="Policy violation",
                    )
                )

                with pytest.raises(HTTPException) as exc_info:
                    await swarm_endpoints.start_swarm(
                        swarm_endpoints.StartSwarmRequest(objective="deploy all agents"),
                        current_user=mock_user,
                    )

        assert exc_info.value.status_code == 403
        assert "Blocked by governance" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_start_swarm_timeout_returns_504(self):
        mock_service = Mock()
        mock_user = Mock()
        mock_user.tenant_id = 7

        async def slow_start_swarm(*_args, **_kwargs):
            await asyncio.sleep(0.05)

        mock_service.start_swarm = slow_start_swarm

        with patch.object(swarm_endpoints.manager, "get_service", return_value=mock_service):
            with patch("src.core.governance.oversight_gate.OversightGate") as gate_cls:
                gate_cls.return_value.check = AsyncMock(
                    return_value=OversightResult(
                        allowed=True,
                        requires_human_approval=False,
                        risk_level=AIActRiskLevel.LIMITED,
                        reason="Approved",
                    )
                )
                with patch.object(swarm_endpoints, "SWARM_EXECUTION_TIMEOUT_SECONDS", 0.001):
                    with pytest.raises(HTTPException) as exc_info:
                        await swarm_endpoints.start_swarm(
                            swarm_endpoints.StartSwarmRequest(objective="analyze roadmap"),
                            current_user=mock_user,
                        )

        assert exc_info.value.status_code == 504
        assert exc_info.value.detail == "Swarm start timed out"

    @pytest.mark.asyncio
    async def test_health_check_is_dynamic_idle_when_inactive(self):
        original_connections = swarm_endpoints.manager.active_connections
        original_services = swarm_endpoints.manager.services
        swarm_endpoints.manager.active_connections = {}
        swarm_endpoints.manager.services = {}
        try:
            response = await swarm_endpoints.health_check()
        finally:
            swarm_endpoints.manager.active_connections = original_connections
            swarm_endpoints.manager.services = original_services

        assert response["status"] == "idle"
        assert response["active_connections"] == 0
        assert response["active_sessions"] == 0

    @pytest.mark.asyncio
    async def test_health_check_is_dynamic_healthy_when_sessions_exist(self):
        original_connections = swarm_endpoints.manager.active_connections
        original_services = swarm_endpoints.manager.services
        mock_service = Mock()
        mock_service.get_active_sessions.return_value = [Mock(), Mock()]
        swarm_endpoints.manager.active_connections = {"session-1": [Mock()]}
        swarm_endpoints.manager.services = {"7": mock_service}
        try:
            response = await swarm_endpoints.health_check()
        finally:
            swarm_endpoints.manager.active_connections = original_connections
            swarm_endpoints.manager.services = original_services

        assert response["status"] == "healthy"
        assert response["active_connections"] == 1
        assert response["active_sessions"] == 2
