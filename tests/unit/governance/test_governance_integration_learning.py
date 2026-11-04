"""Tests for GovernanceIntegration learning loop extension (Phase 3).

Verifies that governance blocks and drift feed into the learning repositories
and feedback service, closing the governance → learning loop.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.governance.governance_agent.integration import GovernanceIntegration


class TestGovernanceIntegrationLearningInit:
    """Optional learning deps are accepted and stored."""

    def test_accepts_feedback_service(self) -> None:
        feedback = MagicMock()
        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=MagicMock(),
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
            feedback_service=feedback,
        )
        assert integration._feedback is feedback

    def test_accepts_insight_repo(self) -> None:
        insight_repo = MagicMock()
        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=MagicMock(),
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
            insight_repo=insight_repo,
        )
        assert integration._insights is insight_repo

    def test_accepts_adaptation_repo(self) -> None:
        adaptation_repo = MagicMock()
        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=MagicMock(),
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
            adaptation_repo=adaptation_repo,
        )
        assert integration._adaptations is adaptation_repo

    def test_all_learning_deps_default_to_none(self) -> None:
        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=MagicMock(),
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
        )
        assert integration._feedback is None
        assert integration._insights is None
        assert integration._adaptations is None

    def test_existing_init_still_works_without_learning_deps(self) -> None:
        """Backward compatibility: existing callers without learning deps must not break."""
        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=MagicMock(),
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
        )
        assert integration._oversight is not None


class TestGovernanceIntegrationPreExecutionLearning:
    """Governance block feeds a LearningInsight to insight_repo."""

    @pytest.mark.asyncio
    async def test_blocked_result_saves_insight(self) -> None:
        gate = MagicMock()
        gate.check = AsyncMock(return_value=MagicMock(allowed=False, reason="Art. 5 block"))
        insight_repo = MagicMock()
        insight_repo.save = AsyncMock(return_value="insight-id")

        integration = GovernanceIntegration(
            oversight_gate=gate,
            accuracy_monitor=MagicMock(),
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
            insight_repo=insight_repo,
        )

        await integration.pre_execution(
            tenant_id=1,
            user_id=7,
            agent_name="Bot",
            agent_department="Gov",
            agent_specialisation="eval",
            agent_capabilities=["social_scoring"],
            task_action="score",
            task_params={},
        )

        insight_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_allowed_result_does_not_save_insight(self) -> None:
        gate = MagicMock()
        gate.check = AsyncMock(return_value=MagicMock(allowed=True))
        insight_repo = MagicMock()
        insight_repo.save = AsyncMock(return_value="insight-id")

        integration = GovernanceIntegration(
            oversight_gate=gate,
            accuracy_monitor=MagicMock(),
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
            insight_repo=insight_repo,
        )

        await integration.pre_execution(
            tenant_id=1,
            user_id=7,
            agent_name="Bot",
            agent_department="Ops",
            agent_specialisation="auto",
            agent_capabilities=["data_analysis"],
            task_action="process",
            task_params={},
        )

        insight_repo.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_insight_contains_tenant_id(self) -> None:
        gate = MagicMock()
        gate.check = AsyncMock(return_value=MagicMock(allowed=False, reason="block"))
        insight_repo = MagicMock()
        insight_repo.save = AsyncMock(return_value="id")

        integration = GovernanceIntegration(
            oversight_gate=gate,
            accuracy_monitor=MagicMock(),
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
            insight_repo=insight_repo,
        )

        await integration.pre_execution(
            tenant_id=42,
            user_id=1,
            agent_name="Bot",
            agent_department="Gov",
            agent_specialisation="eval",
            agent_capabilities=["social_scoring"],
            task_action="score",
            task_params={},
        )

        call_args = insight_repo.save.call_args
        # Second positional arg is str(tenant_id)
        tenant_arg = call_args.args[1]
        assert tenant_arg == "42"

    @pytest.mark.asyncio
    async def test_no_insight_repo_does_not_raise_on_block(self) -> None:
        """When insight_repo is None, blocked pre_execution must not crash."""
        gate = MagicMock()
        gate.check = AsyncMock(return_value=MagicMock(allowed=False, reason="block"))

        integration = GovernanceIntegration(
            oversight_gate=gate,
            accuracy_monitor=MagicMock(),
            alert_manager=MagicMock(),
            ml_strategy=MagicMock(),
            insight_repo=None,
        )

        result = await integration.pre_execution(
            tenant_id=1,
            user_id=1,
            agent_name="Bot",
            agent_department="Gov",
            agent_specialisation="eval",
            agent_capabilities=["social_scoring"],
            task_action="score",
            task_params={},
        )
        assert result.allowed is False


class TestGovernanceIntegrationPostExecutionLearning:
    """Drift feeds AdaptationRule; feedback_service always receives result."""

    @pytest.mark.asyncio
    async def test_drift_saves_adaptation_rule(self) -> None:
        monitor = MagicMock()
        monitor.track_result = AsyncMock()
        monitor.check_drift = AsyncMock(return_value={"drop_pct": 15.0, "score": 0.15})
        adaptation_repo = MagicMock()
        adaptation_repo.save = AsyncMock(return_value="rule-id")
        ml = MagicMock()
        ml.analyze = AsyncMock(return_value=None)

        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=monitor,
            alert_manager=MagicMock(handle_violation=AsyncMock()),
            ml_strategy=ml,
            adaptation_repo=adaptation_repo,
        )

        await integration.post_execution(
            tenant_id=1,
            agent_name="Bot",
            success=True,
            confidence_score=0.65,
            execution_time_ms=200,
        )

        adaptation_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_drift_does_not_save_adaptation_rule(self) -> None:
        monitor = MagicMock()
        monitor.track_result = AsyncMock()
        monitor.check_drift = AsyncMock(return_value=None)
        adaptation_repo = MagicMock()
        adaptation_repo.save = AsyncMock()
        ml = MagicMock()
        ml.analyze = AsyncMock(return_value=None)

        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=monitor,
            alert_manager=MagicMock(),
            ml_strategy=ml,
            adaptation_repo=adaptation_repo,
        )

        await integration.post_execution(
            tenant_id=1,
            agent_name="Bot",
            success=True,
            confidence_score=0.9,
            execution_time_ms=100,
        )

        adaptation_repo.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_feedback_service_always_called(self) -> None:
        monitor = MagicMock()
        monitor.track_result = AsyncMock()
        monitor.check_drift = AsyncMock(return_value=None)
        feedback = MagicMock()
        feedback.process_feedback = AsyncMock(return_value={})
        ml = MagicMock()
        ml.analyze = AsyncMock(return_value=None)

        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=monitor,
            alert_manager=MagicMock(),
            ml_strategy=ml,
            feedback_service=feedback,
        )

        await integration.post_execution(
            tenant_id=5,
            agent_name="Bot",
            success=False,
            confidence_score=0.4,
            execution_time_ms=300,
        )

        feedback.process_feedback.assert_called_once()

    @pytest.mark.asyncio
    async def test_feedback_payload_contains_tenant_id(self) -> None:
        monitor = MagicMock()
        monitor.track_result = AsyncMock()
        monitor.check_drift = AsyncMock(return_value=None)
        feedback = MagicMock()
        feedback.process_feedback = AsyncMock(return_value={})
        ml = MagicMock()
        ml.analyze = AsyncMock(return_value=None)

        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=monitor,
            alert_manager=MagicMock(),
            ml_strategy=ml,
            feedback_service=feedback,
        )

        await integration.post_execution(
            tenant_id=99,
            agent_name="FeedbackBot",
            success=True,
            confidence_score=0.8,
            execution_time_ms=50,
        )

        payload = feedback.process_feedback.call_args.args[0]
        assert payload["tenant_id"] == 99
        assert payload["agent_name"] == "FeedbackBot"

    @pytest.mark.asyncio
    async def test_no_learning_deps_post_execution_does_not_raise(self) -> None:
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

        # Must not raise even without any learning deps
        await integration.post_execution(
            tenant_id=1,
            agent_name="Bot",
            success=True,
            confidence_score=0.9,
            execution_time_ms=100,
        )
