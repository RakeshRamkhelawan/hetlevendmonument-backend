"""Unit tests for governance hook in websocket.py (Pad 6 - WebSocket LangGraph)."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.core.governance.ai_act_classifier import AIActRiskLevel
from src.core.governance.oversight_gate import OversightResult


def _make_result(
    allowed: bool,
    requires_human_approval: bool = False,
    reason: str = "test",
) -> OversightResult:
    return OversightResult(
        allowed=allowed,
        requires_human_approval=requires_human_approval,
        risk_level=AIActRiskLevel.LIMITED,
        reason=reason,
    )


def _make_user(user_id: int = 1, tenant_id: int = 42):
    user = Mock()
    user.user_id = user_id
    user.tenant_id = tenant_id
    return user


def _make_websocket():
    ws = AsyncMock()
    ws.close = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.accept = AsyncMock()
    return ws


class TestAgentStreamWebsocketGovernance:
    @pytest.mark.asyncio
    async def test_blocked_governance_closes_1008(self):
        from src.core.api.v1.agentic.websocket import agent_stream_websocket

        ws = _make_websocket()
        user = _make_user()

        with (
            patch("src.core.api.v1.agentic.websocket.WorkflowGraphBuilder"),
            patch("src.core.api.v1.agentic.websocket.OversightGate") as gate_cls,
        ):
            # Patch graph build to return a mock app
            mock_graph = MagicMock()
            mock_graph.build.return_value = MagicMock()
            import sys

            imported_module = sys.modules.get("src.core.api.v1.agentic.websocket")
            if imported_module:
                patch_target = "src.core.api.v1.agentic.websocket.WorkflowGraphBuilder"

            gate_cls.return_value.check = AsyncMock(
                return_value=_make_result(allowed=False, reason="policy violation")
            )

            await agent_stream_websocket(ws, user)

        ws.close.assert_awaited_once()
        close_call = ws.close.call_args
        assert close_call.kwargs.get("code") == 1008 or (close_call.args and close_call.args[0] == 1008)

    @pytest.mark.asyncio
    async def test_requires_approval_closes_1008(self):
        from src.core.api.v1.agentic.websocket import agent_stream_websocket

        ws = _make_websocket()
        user = _make_user()

        with (
            patch("src.core.api.v1.agentic.websocket.WorkflowGraphBuilder"),
            patch("src.core.api.v1.agentic.websocket.OversightGate") as gate_cls,
        ):
            gate_cls.return_value.check = AsyncMock(
                return_value=_make_result(
                    allowed=True,
                    requires_human_approval=True,
                    reason="approval needed",
                )
            )

            await agent_stream_websocket(ws, user)

        ws.close.assert_awaited_once()
        close_call = ws.close.call_args
        assert close_call.kwargs.get("code") == 1008 or (close_call.args and close_call.args[0] == 1008)

    @pytest.mark.asyncio
    async def test_governance_error_closes_1011(self):
        from src.core.api.v1.agentic.websocket import agent_stream_websocket

        ws = _make_websocket()
        user = _make_user()

        with (
            patch("src.core.api.v1.agentic.websocket.WorkflowGraphBuilder"),
            patch("src.core.api.v1.agentic.websocket.OversightGate") as gate_cls,
        ):
            gate_cls.return_value.check = AsyncMock(
                side_effect=RuntimeError("Governance service down")
            )

            await agent_stream_websocket(ws, user)

        ws.close.assert_awaited_once()
        close_call = ws.close.call_args
        assert close_call.kwargs.get("code") == 1011 or close_call.args[0] == 1011

    @pytest.mark.asyncio
    async def test_governance_called_with_user_context(self):
        from src.core.api.v1.agentic.websocket import agent_stream_websocket

        ws = _make_websocket()
        user = _make_user(user_id=99, tenant_id=7)

        with (
            patch("src.core.api.v1.agentic.websocket.WorkflowGraphBuilder"),
            patch("src.core.api.v1.agentic.websocket.OversightGate") as gate_cls,
        ):
            gate_cls.return_value.check = AsyncMock(
                return_value=_make_result(allowed=False, reason="blocked")
            )
            await agent_stream_websocket(ws, user)

        call_kwargs = gate_cls.return_value.check.call_args[1]
        assert call_kwargs["agent_name"] == "LangGraphStream"
        assert call_kwargs["tenant_id"] == 7
        assert call_kwargs["user_id"] == 99
        assert call_kwargs["task_params"]["user_id"] == "99"

    @pytest.mark.asyncio
    async def test_graph_build_failure_does_not_reach_governance(self):
        """If the graph fails to build, we close with 1011 before governance."""
        from src.core.api.v1.agentic.websocket import agent_stream_websocket

        ws = _make_websocket()
        user = _make_user()

        with (
            patch(
                "src.core.api.v1.agentic.websocket.WorkflowGraphBuilder",
                side_effect=RuntimeError("Graph build fail"),
            ),
            patch("src.core.api.v1.agentic.websocket.OversightGate") as gate_cls,
        ):
            gate_cls.return_value.check = AsyncMock(return_value=_make_result(allowed=True))
            await agent_stream_websocket(ws, user)

        # Governance should NOT have been called because graph building failed
        gate_cls.return_value.check.assert_not_awaited()
        ws.close.assert_awaited_once()
