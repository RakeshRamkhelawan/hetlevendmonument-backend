"""Tests for Oversight Gate.

EU AI Act Compliance - Task 2: Pre-execution Governance
Tests for pre-execution policy validation and human oversight.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src.core.governance.ai_act_classifier import AIActRiskLevel
from src.core.governance.oversight_gate import OversightGate, OversightResult


@dataclass
class MockAgent:
    """Mock agent for testing."""

    name: str
    department: str
    specialisation: str
    capabilities: List[str]


@dataclass
class MockTask:
    """Mock task for testing."""

    id: str
    description: str
    action_type: str
    params: dict[str, Any]


class TestOversightResult:
    """Test OversightResult dataclass."""

    def test_result_creation(self) -> None:
        """Should create result with all fields."""
        result = OversightResult(
            allowed=True,
            requires_human_approval=False,
            risk_level=AIActRiskLevel.LIMITED,
            reason="Standard operation",
        )
        assert result.allowed is True
        assert result.requires_human_approval is False
        assert result.risk_level == AIActRiskLevel.LIMITED
        assert result.reason == "Standard operation"

    def test_blocked_result(self) -> None:
        """Should create blocked result."""
        result = OversightResult(
            allowed=False,
            requires_human_approval=False,
            risk_level=AIActRiskLevel.HIGH_RISK,
            reason="Policy violation detected",
        )
        assert result.allowed is False


class TestOversightGateInit:
    """Test OversightGate initialization."""

    def test_gate_initializes_with_dependencies(self) -> None:
        """Should initialize with policy engine and audit service."""
        mock_policy = AsyncMock()
        mock_audit = AsyncMock()

        gate = OversightGate(
            policy_engine=mock_policy,
            audit_service=mock_audit,
        )

        assert gate.policy_engine is mock_policy
        assert gate.audit_service is mock_audit


class TestOversightGateCheck:
    """Test OversightGate.check() method."""

    @pytest.fixture
    def gate(self) -> OversightGate:
        """Create gate with mocked dependencies."""
        mock_policy = AsyncMock()
        mock_audit = AsyncMock()
        return OversightGate(
            policy_engine=mock_policy,
            audit_service=mock_audit,
        )

    @pytest.fixture
    def low_risk_agent(self) -> MockAgent:
        return MockAgent(
            name="Simple Bot",
            department="Operations",
            specialisation="automation",
            capabilities=["data_processing"],
        )

    @pytest.fixture
    def high_risk_agent(self) -> MockAgent:
        return MockAgent(
            name="Recruitment Bot",
            department="HR",
            specialisation="recruitment",
            capabilities=["resume_screening"],
        )

    @pytest.fixture
    def sample_task(self) -> MockTask:
        return MockTask(
            id="task-001",
            description="Process documents",
            action_type="process",
            params={"files": ["doc1.pdf"]},
        )

    @pytest.mark.asyncio
    async def test_low_risk_agent_allowed_without_approval(
        self,
        gate: OversightGate,
        low_risk_agent: MockAgent,
        sample_task: MockTask,
    ) -> None:
        gate.policy_engine.validate_action.return_value = {
            "allowed": True,
            "violations": [],
        }

        result = await gate.check(
            agent_name=low_risk_agent.name,
            agent_department=low_risk_agent.department,
            agent_specialisation=low_risk_agent.specialisation,
            agent_capabilities=low_risk_agent.capabilities,
            task_action=sample_task.action_type,
            task_params=sample_task.params,
        )

        assert result.allowed is True
        assert result.requires_human_approval is False
        assert result.risk_level == AIActRiskLevel.LIMITED

    @pytest.mark.asyncio
    async def test_high_risk_agent_requires_approval(
        self,
        gate: OversightGate,
        high_risk_agent: MockAgent,
        sample_task: MockTask,
    ) -> None:
        gate.policy_engine.validate_action.return_value = {
            "allowed": True,
            "violations": [],
        }

        result = await gate.check(
            agent_name=high_risk_agent.name,
            agent_department=high_risk_agent.department,
            agent_specialisation=high_risk_agent.specialisation,
            agent_capabilities=high_risk_agent.capabilities,
            task_action=sample_task.action_type,
            task_params=sample_task.params,
        )

        assert result.allowed is True
        assert result.requires_human_approval is True
        assert result.risk_level == AIActRiskLevel.HIGH_RISK
        assert "human approval" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_policy_violation_blocks_execution(
        self,
        gate: OversightGate,
        low_risk_agent: MockAgent,
        sample_task: MockTask,
    ) -> None:
        gate.policy_engine.validate_action.return_value = {
            "allowed": False,
            "violations": ["PII exposure risk"],
        }

        result = await gate.check(
            agent_name=low_risk_agent.name,
            agent_department=low_risk_agent.department,
            agent_specialisation=low_risk_agent.specialisation,
            agent_capabilities=low_risk_agent.capabilities,
            task_action=sample_task.action_type,
            task_params=sample_task.params,
        )

        assert result.allowed is False
        assert result.requires_human_approval is False
        assert "policy" in result.reason.lower() or "violation" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_audit_log_created_on_check(self, gate: OversightGate) -> None:
        gate.policy_engine.validate_action.return_value = {
            "allowed": True,
            "violations": [],
        }

        await gate.check(
            agent_name="Test Agent",
            agent_department="Test",
            agent_specialisation="testing",
            agent_capabilities=["test"],
            task_action="test_action",
            task_params={},
        )

        gate.audit_service.log_security_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_breakthrough_action_requires_approval(
        self,
        gate: OversightGate,
        low_risk_agent: MockAgent,
    ) -> None:
        gate.policy_engine.validate_action.return_value = {
            "allowed": True,
            "violations": [],
        }

        result = await gate.check(
            agent_name=low_risk_agent.name,
            agent_department=low_risk_agent.department,
            agent_specialisation=low_risk_agent.specialisation,
            agent_capabilities=low_risk_agent.capabilities,
            task_action="code_generation",
            task_params={"generate_files": True},
        )

        assert result.requires_human_approval is True
        assert "breakthrough" in result.reason.lower() or "code" in result.reason.lower()


class TestOversightGateArt5Block:
    """Art. 5: UNACCEPTABLE risk agents must be hard-blocked, no override."""

    @pytest.fixture
    def gate(self) -> OversightGate:
        mock_policy = AsyncMock()
        mock_audit = AsyncMock()
        return OversightGate(policy_engine=mock_policy, audit_service=mock_audit)

    @pytest.mark.asyncio
    async def test_unacceptable_agent_is_blocked(self, gate: OversightGate) -> None:
        gate.policy_engine.validate_action.return_value = {
            "allowed": True,
            "violations": [],
        }

        result = await gate.check(
            agent_name="Social Score Bot",
            agent_department="Government",
            agent_specialisation="citizen_ranking",
            agent_capabilities=["social_scoring"],
            task_action="process",
            task_params={},
        )

        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_unacceptable_agent_does_not_require_human_approval(
        self, gate: OversightGate
    ) -> None:
        gate.policy_engine.validate_action.return_value = {
            "allowed": True,
            "violations": [],
        }

        result = await gate.check(
            agent_name="Surveillance Bot",
            agent_department="Security",
            agent_specialisation="monitoring",
            agent_capabilities=["mass_surveillance"],
            task_action="monitor",
            task_params={},
        )

        assert result.allowed is False
        assert result.requires_human_approval is False

    @pytest.mark.asyncio
    async def test_unacceptable_reason_references_article_5(self, gate: OversightGate) -> None:
        gate.policy_engine.validate_action.return_value = {
            "allowed": True,
            "violations": [],
        }

        result = await gate.check(
            agent_name="Manipulation Bot",
            agent_department="Marketing",
            agent_specialisation="persuasion",
            agent_capabilities=["subliminal_manipulation"],
            task_action="send_campaign",
            task_params={},
        )

        assert "5" in result.reason or "art" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_unacceptable_block_skips_policy_engine(self, gate: OversightGate) -> None:
        result = await gate.check(
            agent_name="Exploitation Bot",
            agent_department="Marketing",
            agent_specialisation="targeting",
            agent_capabilities=["exploitation_vulnerable_groups"],
            task_action="target",
            task_params={},
        )

        assert result.allowed is False
        gate.policy_engine.validate_action.assert_not_called()

    @pytest.mark.asyncio
    async def test_unacceptable_risk_level_in_result(self, gate: OversightGate) -> None:
        result = await gate.check(
            agent_name="Score Bot",
            agent_department="Gov",
            agent_specialisation="eval",
            agent_capabilities=["social_scoring"],
            task_action="score",
            task_params={},
        )

        assert result.risk_level == AIActRiskLevel.UNACCEPTABLE


class TestOversightGateTenantIdType:
    """tenant_id must be int | None, matching database FK (not str)."""

    def test_tenant_id_annotation_is_int_or_none(self) -> None:
        hints = OversightGate.check.__annotations__
        annotation = hints.get("tenant_id", "")
        assert annotation in (
            "int | None",
            "Optional[int]",
        ), f"Expected int | None, got {annotation}"

    @pytest.mark.asyncio
    async def test_check_accepts_int_tenant_id(self) -> None:
        gate = OversightGate(
            policy_engine=AsyncMock(
                validate_action=MagicMock(return_value={"allowed": True, "violations": []})
            ),
            audit_service=AsyncMock(),
        )
        result = await gate.check(
            agent_name="Test Agent",
            agent_department="Operations",
            agent_specialisation="automation",
            agent_capabilities=["data_processing"],
            task_action="process",
            task_params={},
            tenant_id=42,
            user_id=7,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_check_accepts_none_tenant_id(self) -> None:
        gate = OversightGate(
            policy_engine=AsyncMock(
                validate_action=MagicMock(return_value={"allowed": True, "violations": []})
            ),
            audit_service=AsyncMock(),
        )
        result = await gate.check(
            agent_name="Test Agent",
            agent_department="Operations",
            agent_specialisation="automation",
            agent_capabilities=["data_processing"],
            task_action="process",
            task_params={},
            tenant_id=None,
        )
        assert result is not None


class TestOversightGateFailClosed:
    """Test that gate fails closed on errors."""

    @pytest.mark.asyncio
    async def test_error_results_in_blocked(self) -> None:
        mock_policy = AsyncMock()
        mock_policy.validate_action.side_effect = Exception("Policy engine down")
        mock_audit = AsyncMock()

        gate = OversightGate(
            policy_engine=mock_policy,
            audit_service=mock_audit,
        )

        result = await gate.check(
            agent_name="Test Agent",
            agent_department="Test",
            agent_specialisation="testing",
            agent_capabilities=["test"],
            task_action="test_action",
            task_params={},
        )

        assert result.allowed is False
        assert "error" in result.reason.lower() or "gate" in result.reason.lower()
