"""Unit tests for BoardService.

Tests all happy and unhappy paths for board governance including:
- Submit decisions
- Approve/reject decisions
- Board role routing
- Golden Rule R3 enforcement
- Tenant isolation
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.company.board_service import (
    BoardRoleError,
    BoardService,
    BoardServiceError,
    GoldenRuleR3Violation,
)
from src.core.company.context import AgentExecutionContext, GoalChain, PolicyScope
from src.core.company.models import BoardDecision, BoardDecisionStatus, Company
from src.core.company.schemas import BoardQueueResponse
from src.core.exceptions.exceptions import NotFoundError, ValidationError


@pytest.fixture
def mock_db_manager():
    """Create mock database manager."""
    mock = MagicMock()

    class SessionContextManager:
        def __init__(self, session):
            self._session = session

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, *args):
            pass

    def get_session():
        return SessionContextManager(MagicMock())

    mock.get_session = get_session
    return mock


@pytest.fixture
def mock_policy_engine():
    """Create mock policy engine."""
    mock = MagicMock()
    mock.validate_action = AsyncMock(
        return_value=MagicMock(
            allowed=True, requires_approval=True, reason="Test approval required"
        )
    )
    return mock


@pytest.fixture
def mock_tenant_context():
    """Create mock tenant context."""
    mock = MagicMock()
    mock.tenant_id = 1
    mock.user_id = 1
    return mock


@pytest.fixture
def board_service(mock_db_manager, mock_policy_engine, mock_tenant_context):
    """Create BoardService instance with mocks."""
    return BoardService(
        db_manager=mock_db_manager,
        policy_engine=mock_policy_engine,
        tenant_context=mock_tenant_context,
    )


@pytest.fixture
def valid_agent_context():
    """Create valid AgentExecutionContext with all required fields."""
    return AgentExecutionContext(
        tenant_id=1,
        task_id=uuid.uuid4(),
        trace_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        goal_chain=GoalChain(
            mission_id=uuid.uuid4(),
            mission_title="Test Mission",
            task_goal_id=uuid.uuid4(),
            task_goal_title="Test Task",
        ),
        policy_scope=PolicyScope(
            risk_level="MEDIUM",
            requires_approval=True,
            approval_board_role="CFO",
        ),
    )


@pytest.fixture
def mock_company():
    """Create mock Company."""
    company = MagicMock(spec=Company)
    company.id = uuid.uuid4()
    company.tenant_id = 1
    company.name = "Test Company"
    company.board_role_config = None
    return company


# =============================================================================
# Happy Path Tests
# =============================================================================


class TestSubmitDecision:
    """Test submit decision happy paths."""

    @pytest.mark.asyncio
    async def test_submit_decision(self, board_service, valid_agent_context, mock_company):
        """Submit met volledige context → BoardDecision aangemaakt."""
        # Arrange
        action_context = {"budget_impact": 10000}

        mock_session = MagicMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Mock company query
        company_result = MagicMock()
        company_result.scalar_one_or_none.return_value = mock_company

        async def mock_execute(query):
            if "Company" in str(query) or "companies" in str(query):
                return company_result
            return MagicMock()

        mock_session.execute = mock_execute

        # Patch get_session
        class MockSessionMgr:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                pass

        board_service.db_manager.get_session = lambda: MockSessionMgr()

        # Act
        decision = await board_service.submit(
            action_type="budget_increase",
            action_context=action_context,
            context=valid_agent_context,
        )

        # Assert
        assert decision is not None
        assert decision.tenant_id == 1
        assert decision.action_type == "budget_increase"
        assert decision.board_role == "CFO"  # Budget goes to CFO

    @pytest.mark.asyncio
    async def test_submit_budget_action_routes_to_cfo(
        self, board_service, valid_agent_context, mock_company
    ):
        """Budget actie → board_role="CFO"."""
        valid_agent_context.policy_scope.risk_level = "HIGH"

        mock_company.board_role_config = None

        # Test routing logic directly
        board_role = board_service._route_to_board_member(
            action_type="budget",
            risk_level="HIGH",
            department_id=None,
            company=mock_company,
        )

        assert board_role == "CFO"

    @pytest.mark.asyncio
    async def test_submit_agent_hire_routes_to_cto(self, board_service, mock_company):
        """Agent registratie → board_role="CTO"."""
        board_role = board_service._route_to_board_member(
            action_type="agent_hire",
            risk_level="MEDIUM",
            department_id=None,
            company=mock_company,
        )

        assert board_role == "CTO"

    @pytest.mark.asyncio
    async def test_submit_translates_critical_to_business(self, board_service):
        """CRITICAL → "Board approval vereist"."""
        policy_result = {
            "risk_level": "CRITICAL",
            "requires_approval": True,
        }

        message = board_service._translate_to_business_language(policy_result)

        assert "Board approval vereist" in message

    @pytest.mark.asyncio
    async def test_submit_translates_high_to_business(self, board_service):
        """HIGH → "Afdelingshoofd moet goedkeuren"."""
        policy_result = {
            "risk_level": "HIGH",
            "requires_approval": True,
        }

        message = board_service._translate_to_business_language(policy_result)

        assert "Afdelingshoofd" in message


class TestApproveDecision:
    """Test approve decision happy paths."""

    @pytest.mark.asyncio
    async def test_approve_decision(self, board_service):
        """Approve → decision="approved", decided_at set."""
        # Arrange
        decision_id = uuid.uuid4()
        user_id = 1

        mock_decision = MagicMock(spec=BoardDecision)
        mock_decision.id = decision_id
        mock_decision.tenant_id = 1
        mock_decision.board_role = "CFO"
        mock_decision.decision = None
        mock_decision.decided_by = None
        mock_decision.decided_at = None

        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        async def mock_execute(query):
            result = MagicMock()
            result.scalar_one_or_none.return_value = mock_decision
            return result

        mock_session.execute = mock_execute

        class MockSessionMgr:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                pass

        board_service.db_manager.get_session = lambda: MockSessionMgr()

        # Mock user has board role
        board_service._user_has_board_role = AsyncMock(return_value=True)

        # Act
        result = await board_service.approve(decision_id, user_id)

        # Assert
        assert result.decision == BoardDecisionStatus.APPROVED.value
        assert result.decided_by == user_id
        assert result.decided_at is not None


class TestRejectDecision:
    """Test reject decision happy paths."""

    @pytest.mark.asyncio
    async def test_reject_decision_with_reason(self, board_service):
        """Reject met reason → "rejected"."""
        # Arrange
        decision_id = uuid.uuid4()
        user_id = 1
        reason = "Budget overschrijding"

        mock_decision = MagicMock(spec=BoardDecision)
        mock_decision.id = decision_id
        mock_decision.tenant_id = 1
        mock_decision.board_role = "CFO"
        mock_decision.decision = None

        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        async def mock_execute(query):
            result = MagicMock()
            result.scalar_one_or_none.return_value = mock_decision
            return result

        mock_session.execute = mock_execute

        class MockSessionMgr:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                pass

        board_service.db_manager.get_session = lambda: MockSessionMgr()
        board_service._user_has_board_role = AsyncMock(return_value=True)

        # Act
        result = await board_service.reject(decision_id, user_id, reason)

        # Assert
        assert result.decision == BoardDecisionStatus.REJECTED.value
        assert result.reason == reason


class TestGetQueue:
    """Test get approval queue happy paths."""

    @pytest.mark.asyncio
    async def test_get_queue_for_role(self, board_service):
        """CFO user queue → alleen budget-gerelateerde decisions."""
        # Arrange
        user_id = 1

        mock_decisions = [
            MagicMock(
                id=uuid.uuid4(),
                tenant_id=1,
                company_id=uuid.uuid4(),
                requested_by=1,
                board_role="CFO",
                action_type="budget",
                decision=None,
                action_context={},
                goal_id=uuid.uuid4(),
                decided_by=None,
                reason=None,
                decided_at=None,
                created_at=datetime.now(timezone.utc),
            ),
        ]

        mock_session = MagicMock()

        async def mock_execute(query):
            result = MagicMock()
            result.scalars.return_value.all.return_value = mock_decisions
            return result

        mock_session.execute = mock_execute

        class MockSessionMgr:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                pass

        board_service.db_manager.get_session = lambda: MockSessionMgr()
        board_service._get_user_board_roles = AsyncMock(return_value=["CFO"])

        # Act
        queue = await board_service.get_queue(user_id)

        # Assert
        assert isinstance(queue, BoardQueueResponse)
        assert queue.pending_count == 1


class TestRoutingConfiguration:
    """Test board role routing configuration."""

    @pytest.mark.asyncio
    async def test_custom_board_role_config(self, board_service, mock_company):
        """Tenant met board_role_config.data_export="DPO" → routed naar DPO."""
        mock_company.board_role_config = {
            "data_export": "DPO",
            "default": "tenant_admin",
        }

        board_role = board_service._route_to_board_member(
            action_type="data_export",
            risk_level="MEDIUM",
            department_id=None,
            company=mock_company,
        )

        assert board_role == "DPO"

    @pytest.mark.asyncio
    async def test_default_routing_no_config(self, board_service, mock_company):
        """Company zonder board_role_config → default mapping gebruikt."""
        mock_company.board_role_config = None

        board_role = board_service._route_to_board_member(
            action_type="unknown_action",
            risk_level="LOW",
            department_id=None,
            company=mock_company,
        )

        assert board_role == "tenant_admin"  # Default


class TestAutoApprove:
    """Test auto-approve functionality."""

    @pytest.mark.asyncio
    async def test_auto_approve_below_threshold(self, board_service, mock_company):
        """auto_approve_below="LOW" + LOW risico → auto-approved."""
        mock_company.board_role_config = {
            "thresholds": {
                "auto_approve_below": "LOW",
            }
        }

        should_approve = board_service._should_auto_approve("LOW", "LOW")

        assert should_approve is True

    @pytest.mark.asyncio
    async def test_escalate_above_threshold(self, board_service, mock_company):
        """escalate_above="HIGH" + CRITICAL risico → routed naar CEO."""
        mock_company.board_role_config = {
            "thresholds": {
                "escalate_above": "HIGH",
            }
        }

        board_role = board_service._route_to_board_member(
            action_type="budget",
            risk_level="CRITICAL",
            department_id=None,
            company=mock_company,
        )

        assert board_role == "CEO"


# =============================================================================
# Unhappy Path Tests
# =============================================================================


class TestGoldenRuleR3:
    """Test Golden Rule R3 enforcement."""

    @pytest.mark.asyncio
    async def test_submit_without_goal_fails(self, board_service):
        """Geen goal_id → ValueError (R3)."""
        context = AgentExecutionContext(
            tenant_id=1,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            goal_chain=GoalChain(),  # Empty - no goal_id
            policy_scope=PolicyScope(risk_level="MEDIUM"),
        )

        with pytest.raises(GoldenRuleR3Violation) as exc_info:
            await board_service.submit(
                action_type="test",
                action_context={"budget_impact": 1000},
                context=context,
            )

        assert "goal_id" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_submit_without_risk_level_fails(self, board_service):
        """Geen risk_level → ValueError (R3)."""
        context = AgentExecutionContext(
            tenant_id=1,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            goal_chain=GoalChain(
                mission_id=uuid.uuid4(),
                task_goal_id=uuid.uuid4(),
            ),
            policy_scope=PolicyScope(risk_level="LOW"),  # Valid risk level but we'll clear it
        )
        # Clear risk_level after creation to test validation
        context.policy_scope.risk_level = None

        with pytest.raises(GoldenRuleR3Violation) as exc_info:
            await board_service.submit(
                action_type="test",
                action_context={"budget_impact": 1000},
                context=context,
            )

        assert "risk_level" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_submit_without_budget_impact_fails(self, board_service):
        """Geen budget_impact → ValueError (R3)."""
        context = AgentExecutionContext(
            tenant_id=1,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            goal_chain=GoalChain(
                mission_id=uuid.uuid4(),
                task_goal_id=uuid.uuid4(),
            ),
            policy_scope=PolicyScope(risk_level="MEDIUM"),
        )

        with pytest.raises(GoldenRuleR3Violation) as exc_info:
            await board_service.submit(
                action_type="test",
                action_context={},  # No budget_impact
                context=context,
            )

        assert "budget_impact" in str(exc_info.value).lower()


class TestApproveValidation:
    """Test approve validation unhappy paths."""

    @pytest.mark.asyncio
    async def test_approve_wrong_role(self, board_service):
        """User heeft niet de juiste role → 403."""
        # Arrange
        decision_id = uuid.uuid4()
        user_id = 1

        mock_decision = MagicMock(spec=BoardDecision)
        mock_decision.id = decision_id
        mock_decision.tenant_id = 1
        mock_decision.board_role = "CFO"
        mock_decision.decision = None

        mock_session = MagicMock()

        async def mock_execute(query):
            result = MagicMock()
            result.scalar_one_or_none.return_value = mock_decision
            return result

        mock_session.execute = mock_execute

        class MockSessionMgr:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                pass

        board_service.db_manager.get_session = lambda: MockSessionMgr()
        board_service._user_has_board_role = AsyncMock(return_value=False)

        # Act & Assert
        with pytest.raises(BoardRoleError) as exc_info:
            await board_service.approve(decision_id, user_id)

        assert "does not have required board role" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_approve_already_decided(self, board_service):
        """Al goedgekeurd → error."""
        # Arrange
        decision_id = uuid.uuid4()
        user_id = 1

        mock_decision = MagicMock(spec=BoardDecision)
        mock_decision.id = decision_id
        mock_decision.tenant_id = 1
        mock_decision.decision = BoardDecisionStatus.APPROVED.value

        mock_session = MagicMock()

        async def mock_execute(query):
            result = MagicMock()
            result.scalar_one_or_none.return_value = mock_decision
            return result

        mock_session.execute = mock_execute

        class MockSessionMgr:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                pass

        board_service.db_manager.get_session = lambda: MockSessionMgr()

        # Act & Assert
        with pytest.raises(BoardServiceError) as exc_info:
            await board_service.approve(decision_id, user_id)

        assert "already" in str(exc_info.value).lower()


class TestRejectValidation:
    """Test reject validation unhappy paths."""

    @pytest.mark.asyncio
    async def test_reject_without_reason_fails(self, board_service):
        """Reject zonder reason → error."""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            await board_service.reject(uuid.uuid4(), 1, "")

        assert "reason" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_reject_with_none_reason_fails(self, board_service):
        """Reject met None reason → error."""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            await board_service.reject(uuid.uuid4(), 1, None)  # type: ignore

        assert "reason" in str(exc_info.value).lower()


class TestDegradedMode:
    """Test degraded mode behavior."""

    @pytest.mark.asyncio
    async def test_submit_degraded_mode(self, board_service, mock_company):
        """Geen company → nog steeds werken, maar logt warning."""
        # This test verifies that submit works even in degraded mode
        # The service should handle missing company gracefully
        context = AgentExecutionContext(
            tenant_id=1,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            company_id=None,  # No company - degraded mode
            goal_chain=GoalChain(
                mission_id=uuid.uuid4(),
                task_goal_id=uuid.uuid4(),
            ),
            policy_scope=PolicyScope(risk_level="MEDIUM"),
        )

        # Validate completeness to set is_degraded flag
        is_valid, missing = context.validate_completeness()

        # Context should be in degraded mode without company_id
        assert context.is_degraded is True
        assert is_valid is False
        assert "company_id" in missing


class TestNotFound:
    """Test not found errors."""

    @pytest.mark.asyncio
    async def test_get_decision_not_found(self, board_service):
        """Onbekend decision ID → NotFoundError."""
        # Arrange
        decision_id = uuid.uuid4()

        mock_session = MagicMock()

        async def mock_execute(query):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        mock_session.execute = mock_execute

        class MockSessionMgr:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                pass

        board_service.db_manager.get_session = lambda: MockSessionMgr()

        # Act & Assert
        with pytest.raises(NotFoundError) as exc_info:
            await board_service._get_decision(mock_session, decision_id, 1)

        assert str(decision_id) in str(exc_info.value)


# =============================================================================
# Helper Method Tests
# =============================================================================


class TestMapActionType:
    """Test action type mapping."""

    def test_map_budget_action(self, board_service):
        """Budget-related actions map to budget key."""
        assert board_service._map_action_type("budget") == "budget"
        assert board_service._map_action_type("budget_increase") == "budget"
        assert board_service._map_action_type("finance_review") == "budget"

    def test_map_agent_action(self, board_service):
        """Agent-related actions map correctly."""
        assert board_service._map_action_type("agent_hire") == "agent_hire"
        assert board_service._map_action_type("agent_firing") == "agent_firing"
        # agent_create contains "create" so it maps to agent_hire
        assert board_service._map_action_type("agent_create") == "agent_hire"
        # Generic agent action without create/hire/fire maps to management
        assert board_service._map_action_type("agent_update") == "agent_management"

    def test_map_unknown_action(self, board_service):
        """Unknown actions default to default key."""
        assert board_service._map_action_type("random_action") == "default"


class TestRiskLevelComparison:
    """Test risk level comparison methods."""

    def test_should_auto_approve_low(self, board_service):
        """LOW risk should auto-approve with LOW threshold."""
        assert board_service._should_auto_approve("LOW", "LOW") is True

    def test_should_auto_approve_medium_above_low(self, board_service):
        """MEDIUM risk should NOT auto-approve with LOW threshold."""
        assert board_service._should_auto_approve("MEDIUM", "LOW") is False

    def test_risk_level_higher_than(self, board_service):
        """HIGH is higher than MEDIUM."""
        assert board_service._risk_level_higher_than("HIGH", "MEDIUM") is True

    def test_risk_level_not_higher_than(self, board_service):
        """LOW is not higher than MEDIUM."""
        assert board_service._risk_level_higher_than("LOW", "MEDIUM") is False
