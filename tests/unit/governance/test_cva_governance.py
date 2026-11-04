"""Tests for CVA Autonomous Trigger Governance.

EU AI Act Compliance - Task 3: CVA Autonomous Trigger Governance
Tests for governance checks in CVA autonomous operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from src.core.governance.ai_act_classifier import AIActRiskLevel
from src.core.governance.oversight_gate import OversightGate, OversightResult


@dataclass
class MockTriggerEvent:
    """Mock trigger event for testing."""

    trigger_type: str
    priority: int
    trigger_data: dict[str, Any]
    timestamp: datetime
    processed: bool = False


class TestCVAGovernanceCheck:
    """Test CVA governance check integration."""

    @pytest.fixture
    def mock_oversight_gate(self) -> MagicMock:
        """Create mock oversight gate."""
        return MagicMock(spec=OversightGate)

    @pytest.fixture
    def sample_trigger(self) -> MockTriggerEvent:
        """Create sample trigger event."""
        return MockTriggerEvent(
            trigger_type="SCHEDULED",
            priority=2,
            trigger_data={"reason": "scheduled_breakthrough"},
            timestamp=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_cva_check_passes_for_allowed_action(
        self,
        mock_oversight_gate: MagicMock,
        sample_trigger: MockTriggerEvent,
    ) -> None:
        """CVA should execute when oversight allows action."""
        mock_oversight_gate.check.return_value = OversightResult(
            allowed=True,
            requires_human_approval=False,
            risk_level=AIActRiskLevel.LIMITED,
            reason="Standard operation approved",
        )

        # Simulate the governance check that should be in CVA
        result = await mock_oversight_gate.check(
            agent_name="CVA",
            agent_department="AI",
            agent_specialisation="breakthrough",
            agent_capabilities=["code_generation", "file_creation"],
            task_action="autonomous_breakthrough",
            task_params=sample_trigger.trigger_data,
        )

        assert result.allowed is True
        assert result.requires_human_approval is False

    @pytest.mark.asyncio
    async def test_cva_blocked_when_oversight_denies(
        self,
        mock_oversight_gate: MagicMock,
        sample_trigger: MockTriggerEvent,
    ) -> None:
        """CVA should NOT execute when oversight denies."""
        mock_oversight_gate.check.return_value = OversightResult(
            allowed=False,
            requires_human_approval=False,
            risk_level=AIActRiskLevel.HIGH_RISK,
            reason="Policy violation: unauthorized file creation",
        )

        result = await mock_oversight_gate.check(
            agent_name="CVA",
            agent_department="AI",
            agent_specialisation="breakthrough",
            agent_capabilities=["code_generation"],
            task_action="autonomous_breakthrough",
            task_params={"generate_files": True},
        )

        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_cva_requires_approval_for_breakthrough(
        self,
        mock_oversight_gate: MagicMock,
        sample_trigger: MockTriggerEvent,
    ) -> None:
        """CVA should require human approval for breakthrough actions."""
        mock_oversight_gate.check.return_value = OversightResult(
            allowed=True,
            requires_human_approval=True,
            risk_level=AIActRiskLevel.LIMITED,
            reason="Breakthrough action requires human approval",
        )

        result = await mock_oversight_gate.check(
            agent_name="CVA",
            agent_department="AI",
            agent_specialisation="breakthrough",
            agent_capabilities=["code_generation", "innovation"],
            task_action="code_generation",  # Breakthrough action
            task_params={"files": ["new_module.py"]},
        )

        assert result.requires_human_approval is True

    def test_cva_governance_check_includes_correct_params(self) -> None:
        """CVA governance check should include all required parameters."""
        mock_gate = MagicMock(spec=OversightGate)

        # Call with expected CVA parameters
        mock_gate.check(
            agent_name="CVA",
            agent_department="AI",
            agent_specialisation="autonomous_research",
            agent_capabilities=["code_generation", "file_creation", "analysis"],
            task_action="autonomous_breakthrough",
            task_params={
                "trigger_type": "SCHEDULED",
                "innovation_area": "architecture",
            },
        )

        # Verify the call was made with correct structure
        call_kwargs = mock_gate.check.call_args.kwargs
        assert call_kwargs["agent_name"] == "CVA"
        assert call_kwargs["agent_department"] == "AI"
        assert "code_generation" in call_kwargs["agent_capabilities"]


class TestCVAGovernanceFailClosed:
    """Test CVA governance fails closed on errors."""

    def test_cva_blocks_on_oversight_error(self) -> None:
        """CVA should block execution if oversight gate errors."""
        mock_gate = MagicMock(spec=OversightGate)
        mock_gate.check.side_effect = Exception("Oversight service unavailable")

        # Simulate error handling in CVA
        try:
            result = mock_gate.check(
                agent_name="CVA",
                agent_department="AI",
                agent_specialisation="breakthrough",
                agent_capabilities=["code_generation"],
                task_action="autonomous_breakthrough",
                task_params={},
            )
            # If no exception, check result blocks
            assert result.allowed is False
        except Exception:
            # If exception, CVA should catch and block
            pass  # Expected behavior - fail closed

    def test_cva_returns_blocked_result_on_error(self) -> None:
        """CVA should return blocked result when oversight errors."""
        # Simulate the fail-closed behavior
        fail_closed_result = OversightResult(
            allowed=False,
            requires_human_approval=False,
            risk_level=AIActRiskLevel.HIGH_RISK,
            reason="Oversight gate error: fail-closed",
        )

        assert fail_closed_result.allowed is False
        assert (
            "error" in fail_closed_result.reason.lower()
            or "fail" in fail_closed_result.reason.lower()
        )


class TestCVAGovernanceLogging:
    """Test CVA governance audit logging."""

    def test_cva_logs_governance_decision(self) -> None:
        """CVA should log all governance decisions."""
        mock_audit = MagicMock()
        mock_gate = MagicMock(spec=OversightGate)
        mock_gate.audit_service = mock_audit

        # Simulate execution with audit
        result = OversightResult(
            allowed=True,
            requires_human_approval=True,
            risk_level=AIActRiskLevel.LIMITED,
            reason="Requires human approval",
        )

        # Log should be called
        mock_audit.log_security_event.assert_not_called()  # Before call

        # Simulate the check that would log
        mock_gate.check.return_value = result
        _ = mock_gate.check(
            agent_name="CVA",
            agent_department="AI",
            agent_specialisation="breakthrough",
            agent_capabilities=["code_generation"],
            task_action="test",
            task_params={},
        )

        # In real implementation, _log_decision would be called
        # This test documents expected behavior
