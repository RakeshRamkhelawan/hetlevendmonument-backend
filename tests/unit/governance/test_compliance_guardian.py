"""Tests for ComplianceGuardianAgent (Phase 3: Intelligence + Alerting).

Autonomous post-execution compliance monitoring agent.
Covers: subscription setup, signal handlers for Art. 9/15/17/61/72.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.core.governance.compliance_guardian import ComplianceGuardianAgent


class TestComplianceGuardianAgentInit:
    """Init stores dependencies and subscribes to all required signals."""

    def test_init_stores_signal_bus(self) -> None:
        bus = MagicMock()
        agent = ComplianceGuardianAgent(
            signal_bus=bus,
            alert_manager=MagicMock(),
            authority_reporter=MagicMock(),
            insight_repo=MagicMock(),
            adaptation_repo=MagicMock(),
        )
        assert agent._bus is bus

    def test_init_subscribes_to_task_completed(self) -> None:
        bus = MagicMock()
        ComplianceGuardianAgent(
            signal_bus=bus,
            alert_manager=MagicMock(),
            authority_reporter=MagicMock(),
            insight_repo=MagicMock(),
            adaptation_repo=MagicMock(),
        )
        subscribed_signals = [c.args[0] for c in bus.subscribe.call_args_list]
        assert "task.completed" in subscribed_signals

    def test_init_subscribes_to_task_failed(self) -> None:
        bus = MagicMock()
        ComplianceGuardianAgent(
            signal_bus=bus,
            alert_manager=MagicMock(),
            authority_reporter=MagicMock(),
            insight_repo=MagicMock(),
            adaptation_repo=MagicMock(),
        )
        subscribed_signals = [c.args[0] for c in bus.subscribe.call_args_list]
        assert "task.failed" in subscribed_signals

    def test_init_subscribes_to_governance_block(self) -> None:
        bus = MagicMock()
        ComplianceGuardianAgent(
            signal_bus=bus,
            alert_manager=MagicMock(),
            authority_reporter=MagicMock(),
            insight_repo=MagicMock(),
            adaptation_repo=MagicMock(),
        )
        subscribed_signals = [c.args[0] for c in bus.subscribe.call_args_list]
        assert "governance.block" in subscribed_signals

    def test_init_subscribes_to_accuracy_drift(self) -> None:
        bus = MagicMock()
        ComplianceGuardianAgent(
            signal_bus=bus,
            alert_manager=MagicMock(),
            authority_reporter=MagicMock(),
            insight_repo=MagicMock(),
            adaptation_repo=MagicMock(),
        )
        subscribed_signals = [c.args[0] for c in bus.subscribe.call_args_list]
        assert "accuracy.drift" in subscribed_signals

    def test_init_subscribes_to_agent_lifecycle(self) -> None:
        bus = MagicMock()
        ComplianceGuardianAgent(
            signal_bus=bus,
            alert_manager=MagicMock(),
            authority_reporter=MagicMock(),
            insight_repo=MagicMock(),
            adaptation_repo=MagicMock(),
        )
        subscribed_signals = [c.args[0] for c in bus.subscribe.call_args_list]
        assert any("agent" in s for s in subscribed_signals)


class TestComplianceGuardianOnTaskCompleted:
    """Art. 61: Post-market surveillance — save insight on every completed task."""

    @pytest.mark.asyncio
    async def test_saves_task_surveillance_insight(self) -> None:
        insight_repo = MagicMock()
        insight_repo.save = AsyncMock(return_value="id")
        agent = ComplianceGuardianAgent(
            signal_bus=MagicMock(),
            alert_manager=MagicMock(),
            authority_reporter=MagicMock(),
            insight_repo=insight_repo,
            adaptation_repo=MagicMock(),
        )

        await agent._on_task_completed(
            {
                "tenant_id": 1,
                "agent_name": "BotX",
                "confidence_score": 0.9,
                "duration_ms": 200,
                "risk_level": "medium",
            }
        )

        insight_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_insight_category_is_task_surveillance(self) -> None:
        insight_repo = MagicMock()
        insight_repo.save = AsyncMock(return_value="id")
        agent = ComplianceGuardianAgent(
            signal_bus=MagicMock(),
            alert_manager=MagicMock(),
            authority_reporter=MagicMock(),
            insight_repo=insight_repo,
            adaptation_repo=MagicMock(),
        )

        await agent._on_task_completed(
            {
                "tenant_id": 5,
                "agent_name": "BotY",
                "confidence_score": 0.8,
            }
        )

        saved_insight = insight_repo.save.call_args.args[0]
        assert saved_insight.category == "task_surveillance"


class TestComplianceGuardianOnTaskFailed:
    """Art. 72: Critical failures → authority report."""

    @pytest.mark.asyncio
    async def test_critical_failure_calls_reporter(self) -> None:
        reporter = MagicMock()
        reporter.report_incident = AsyncMock(return_value=MagicMock())
        agent = ComplianceGuardianAgent(
            signal_bus=MagicMock(),
            alert_manager=MagicMock(),
            authority_reporter=reporter,
            insight_repo=MagicMock(),
            adaptation_repo=MagicMock(),
        )

        await agent._on_task_failed(
            {
                "tenant_id": 1,
                "agent_name": "BotZ",
                "severity": "critical",
                "error": "Model failure",
            }
        )

        reporter.report_incident.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_critical_failure_does_not_call_reporter(self) -> None:
        reporter = MagicMock()
        reporter.report_incident = AsyncMock()
        agent = ComplianceGuardianAgent(
            signal_bus=MagicMock(),
            alert_manager=MagicMock(),
            authority_reporter=reporter,
            insight_repo=MagicMock(),
            adaptation_repo=MagicMock(),
        )

        await agent._on_task_failed(
            {
                "tenant_id": 1,
                "agent_name": "BotW",
                "severity": "medium",
            }
        )

        reporter.report_incident.assert_not_called()


class TestComplianceGuardianOnAccuracyDrift:
    """Art. 15: Accuracy drift > 20% → alert."""

    @pytest.mark.asyncio
    async def test_significant_drift_creates_alert(self) -> None:
        alert_manager = MagicMock()
        alert_manager.handle_violation = AsyncMock(return_value=None)
        agent = ComplianceGuardianAgent(
            signal_bus=MagicMock(),
            alert_manager=alert_manager,
            authority_reporter=MagicMock(),
            insight_repo=MagicMock(),
            adaptation_repo=MagicMock(),
        )

        await agent._on_accuracy_drift(
            {
                "tenant_id": 3,
                "agent_name": "DriftBot",
                "drift_score": 0.25,
            }
        )

        alert_manager.handle_violation.assert_called_once()

    @pytest.mark.asyncio
    async def test_small_drift_does_not_alert(self) -> None:
        alert_manager = MagicMock()
        alert_manager.handle_violation = AsyncMock()
        agent = ComplianceGuardianAgent(
            signal_bus=MagicMock(),
            alert_manager=alert_manager,
            authority_reporter=MagicMock(),
            insight_repo=MagicMock(),
            adaptation_repo=MagicMock(),
        )

        await agent._on_accuracy_drift(
            {
                "tenant_id": 3,
                "agent_name": "StableBot",
                "drift_score": 0.05,  # Below 0.2 threshold
            }
        )

        alert_manager.handle_violation.assert_not_called()


class TestComplianceGuardianOnGovernanceBlock:
    """Art. 17: Repeated blocks (>5/24h) → adaptation rule + alert."""

    @pytest.mark.asyncio
    async def test_repeated_blocks_trigger_adaptation(self) -> None:
        adaptation_repo = MagicMock()
        adaptation_repo.save = AsyncMock(return_value="rule-id")
        adaptation_repo.count_recent = AsyncMock(return_value=6)
        alert_manager = MagicMock()
        alert_manager.handle_violation = AsyncMock(return_value=None)

        agent = ComplianceGuardianAgent(
            signal_bus=MagicMock(),
            alert_manager=alert_manager,
            authority_reporter=MagicMock(),
            insight_repo=MagicMock(),
            adaptation_repo=adaptation_repo,
        )

        await agent._on_governance_block(
            {
                "tenant_id": 2,
                "agent": "BlockedBot",
                "reason": "Art. 5 violation",
            }
        )

        adaptation_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_few_blocks_do_not_trigger_adaptation(self) -> None:
        adaptation_repo = MagicMock()
        adaptation_repo.save = AsyncMock()
        adaptation_repo.count_recent = AsyncMock(return_value=2)
        alert_manager = MagicMock()
        alert_manager.handle_violation = AsyncMock()

        agent = ComplianceGuardianAgent(
            signal_bus=MagicMock(),
            alert_manager=alert_manager,
            authority_reporter=MagicMock(),
            insight_repo=MagicMock(),
            adaptation_repo=adaptation_repo,
        )

        await agent._on_governance_block(
            {
                "tenant_id": 2,
                "agent": "OkBot",
                "reason": "single block",
            }
        )

        adaptation_repo.save.assert_not_called()
