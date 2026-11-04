"""Tests for GovernanceIntegration (Phase 2: Integration Strategy).

Covers: init wiring, pre_execution delegates to OversightGate,
post_execution calls accuracy tracking + drift + ML analysis.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.governance.governance_agent.integration import GovernanceIntegration


class TestGovernanceIntegrationInit:
    def test_accepts_all_four_dependencies(self) -> None:
        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=MagicMock(),
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
        )
        assert integration is not None

    def test_stores_oversight_gate(self) -> None:
        gate = MagicMock()
        integration = GovernanceIntegration(
            oversight_gate=gate,
            accuracy_monitor=MagicMock(),
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
        )
        assert integration._oversight is gate

    def test_stores_accuracy_monitor(self) -> None:
        monitor = MagicMock()
        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=monitor,
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
        )
        assert integration._accuracy is monitor


class TestGovernanceIntegrationPreExecution:
    """pre_execution must delegate to OversightGate.check()."""

    @pytest.mark.asyncio
    async def test_pre_execution_calls_oversight_gate(self) -> None:
        gate = MagicMock()
        gate.check = AsyncMock(return_value=MagicMock(allowed=True))
        integration = GovernanceIntegration(
            oversight_gate=gate,
            accuracy_monitor=MagicMock(),
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
        )

        await integration.pre_execution(
            tenant_id=1,
            user_id=7,
            agent_name="Bot",
            agent_department="Ops",
            agent_specialisation="automation",
            agent_capabilities=["data_analysis"],
            task_action="process",
            task_params={},
        )

        gate.check.assert_called_once()

    @pytest.mark.asyncio
    async def test_pre_execution_passes_tenant_id(self) -> None:
        gate = MagicMock()
        gate.check = AsyncMock(return_value=MagicMock(allowed=True))
        integration = GovernanceIntegration(
            oversight_gate=gate,
            accuracy_monitor=MagicMock(),
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
        )

        await integration.pre_execution(
            tenant_id=42,
            user_id=7,
            agent_name="Bot",
            agent_department="Ops",
            agent_specialisation="automation",
            agent_capabilities=[],
            task_action="process",
            task_params={},
        )

        call_kwargs = gate.check.call_args.kwargs
        assert call_kwargs["tenant_id"] == 42

    @pytest.mark.asyncio
    async def test_pre_execution_returns_oversight_result(self) -> None:
        expected = MagicMock(allowed=True)
        gate = MagicMock()
        gate.check = AsyncMock(return_value=expected)
        integration = GovernanceIntegration(
            oversight_gate=gate,
            accuracy_monitor=MagicMock(),
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
        )

        result = await integration.pre_execution(
            tenant_id=1,
            user_id=1,
            agent_name="Bot",
            agent_department="Ops",
            agent_specialisation="auto",
            agent_capabilities=[],
            task_action="x",
            task_params={},
        )

        assert result is expected


class TestGovernanceIntegrationPostExecution:
    """post_execution calls accuracy tracking, drift check, and ML analysis."""

    @pytest.mark.asyncio
    async def test_post_execution_tracks_accuracy(self) -> None:
        monitor = MagicMock()
        monitor.track_result = AsyncMock()
        monitor.check_drift = AsyncMock(return_value=None)
        ml = MagicMock()
        ml.analyze = AsyncMock(return_value=None)

        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=monitor,
            alert_manager=MagicMock(),
            ml_strategy=ml,
        )

        await integration.post_execution(
            tenant_id=1,
            agent_name="Bot",
            success=True,
            confidence_score=0.9,
            execution_time_ms=100,
        )

        monitor.track_result.assert_called_once_with(
            tenant_id=1,
            agent_name="Bot",
            success=True,
            confidence_score=0.9,
            execution_time_ms=100,
        )

    @pytest.mark.asyncio
    async def test_post_execution_checks_drift(self) -> None:
        monitor = MagicMock()
        monitor.track_result = AsyncMock()
        monitor.check_drift = AsyncMock(return_value=None)
        ml = MagicMock()
        ml.analyze = AsyncMock(return_value=None)

        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=monitor,
            alert_manager=MagicMock(),
            ml_strategy=ml,
        )

        await integration.post_execution(
            tenant_id=5,
            agent_name="DriftBot",
            success=False,
            confidence_score=None,
            execution_time_ms=200,
        )

        monitor.check_drift.assert_called_once_with(5, "DriftBot")

    @pytest.mark.asyncio
    async def test_post_execution_raises_alert_on_drift(self) -> None:
        monitor = MagicMock()
        monitor.track_result = AsyncMock()
        drift_info = {"drop_pct": 15.0}
        monitor.check_drift = AsyncMock(return_value=drift_info)
        alert_manager = MagicMock()
        alert_manager.handle_violation = AsyncMock(return_value=None)
        ml = MagicMock()
        ml.analyze = AsyncMock(return_value=None)

        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=monitor,
            alert_manager=alert_manager,
            ml_strategy=ml,
        )

        await integration.post_execution(
            tenant_id=1,
            agent_name="Bot",
            success=True,
            confidence_score=0.6,
            execution_time_ms=100,
        )

        alert_manager.handle_violation.assert_called_once_with(
            tenant_id=1,
            agent_name="Bot",
            violation_type="accuracy_drift",
            details=drift_info,
        )

    @pytest.mark.asyncio
    async def test_post_execution_runs_ml_analysis(self) -> None:
        monitor = MagicMock()
        monitor.track_result = AsyncMock()
        monitor.check_drift = AsyncMock(return_value=None)
        ml = MagicMock()
        ml.analyze = AsyncMock(return_value=None)

        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=monitor,
            alert_manager=MagicMock(),
            ml_strategy=ml,
        )

        await integration.post_execution(
            tenant_id=3,
            agent_name="MLBot",
            success=True,
            confidence_score=0.8,
            execution_time_ms=50,
        )

        ml.analyze.assert_called_once()
        call_args = ml.analyze.call_args
        assert call_args.args[0] == 3  # tenant_id

    @pytest.mark.asyncio
    async def test_post_execution_raises_alert_on_ml_violation(self) -> None:
        monitor = MagicMock()
        monitor.track_result = AsyncMock()
        monitor.check_drift = AsyncMock(return_value=None)
        ml = MagicMock()
        ml.analyze = AsyncMock(return_value={"type": "cross_tenant_access", "confidence": 0.99})
        alert_manager = MagicMock()
        alert_manager.handle_violation = AsyncMock(return_value=None)

        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=monitor,
            alert_manager=alert_manager,
            ml_strategy=ml,
        )

        await integration.post_execution(
            tenant_id=1,
            agent_name="Bot",
            success=True,
            confidence_score=0.9,
            execution_time_ms=100,
        )

        alert_manager.handle_violation.assert_called_once()
        kwargs = alert_manager.handle_violation.call_args.kwargs
        assert kwargs["violation_type"] == "cross_tenant_access"
