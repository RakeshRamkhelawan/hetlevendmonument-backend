"""Integration tests for Fase 6: Board Governance.

End-to-end tests verifying:
1. Board routing logic
2. Golden Rule R3 enforcement
3. Risk level calculations
4. Board role validation

These tests use mocked database sessions to avoid SQLAlchemy async complexities
while still testing the core business logic.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_db_manager():
    """Create mock database manager."""
    mock = MagicMock()

    class AsyncContextManager:
        def __init__(self, session):
            self._session = session

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.flush = AsyncMock()

    mock.get_session = lambda: AsyncContextManager(mock_session)
    return mock, mock_session


@pytest.fixture
def mock_policy_engine():
    """Mock policy engine for testing."""
    mock = MagicMock()
    mock.validate_action = AsyncMock(
        return_value=MagicMock(
            allowed=True, requires_approval=True, reason="Test approval required"
        )
    )
    return mock


@pytest.fixture
def mock_tenant_context():
    """Mock tenant context."""
    mock = MagicMock()
    mock.tenant_id = 1
    mock.user_id = 1
    return mock


@pytest.fixture
def board_service(mock_db_manager, mock_policy_engine, mock_tenant_context):
    """Create BoardService instance with mocks."""
    from src.core.company.board_service import BoardService

    db_manager, _ = mock_db_manager
    return BoardService(
        db_manager=db_manager,
        policy_engine=mock_policy_engine,
        tenant_context=mock_tenant_context,
    )


@pytest.fixture
def mock_company():
    """Create mock Company."""
    company = MagicMock()
    company.id = uuid4()
    company.tenant_id = 1
    company.name = "Test Company"
    company.board_role_config = None
    return company


@pytest.fixture
def valid_agent_context():
    """Create valid AgentExecutionContext with all required fields."""
    from src.core.company.context import AgentExecutionContext, GoalChain, PolicyScope

    return AgentExecutionContext(
        tenant_id=1,
        task_id=uuid4(),
        trace_id=uuid4(),
        company_id=uuid4(),
        goal_chain=GoalChain(
            mission_id=uuid4(),
            mission_title="Test Mission",
            task_goal_id=uuid4(),
            task_goal_title="Test Task",
        ),
        policy_scope=PolicyScope(
            risk_level="HIGH",
            requires_approval=True,
        ),
    )


class TestBoardRouting:
    """Test board role routing logic."""

    def test_routing_budget_to_cfo(self, board_service, mock_company):
        """Budget actie → routed naar CFO."""
        board_role = board_service._route_to_board_member(
            action_type="budget_increase",
            risk_level="HIGH",
            department_id=None,
            company=mock_company,
        )

        assert board_role == "CFO"

    def test_routing_agent_hire_to_cto(self, board_service, mock_company):
        """Agent registratie → routed naar CTO."""
        board_role = board_service._route_to_board_member(
            action_type="agent_hire",
            risk_level="MEDIUM",
            department_id=None,
            company=mock_company,
        )

        assert board_role == "CTO"

    def test_routing_agent_firing_to_chro(self, board_service, mock_company):
        """Agent firing → routed naar CHRO."""
        board_role = board_service._route_to_board_member(
            action_type="agent_firing",
            risk_level="HIGH",
            department_id=None,
            company=mock_company,
        )

        assert board_role == "CHRO"

    def test_routing_data_export_to_compliance(self, board_service, mock_company):
        """Data export → routed naar Compliance Officer."""
        board_role = board_service._route_to_board_member(
            action_type="data_export",
            risk_level="MEDIUM",
            department_id=None,
            company=mock_company,
        )

        assert board_role == "Compliance Officer"

    def test_routing_cross_department_to_ceo(self, board_service, mock_company):
        """Cross-department → routed naar CEO."""
        board_role = board_service._route_to_board_member(
            action_type="cross_department",
            risk_level="MEDIUM",
            department_id=None,
            company=mock_company,
        )

        assert board_role == "CEO"

    def test_routing_default_to_tenant_admin(self, board_service, mock_company):
        """Unknown action → default tenant_admin."""
        board_role = board_service._route_to_board_member(
            action_type="unknown_action",
            risk_level="LOW",
            department_id=None,
            company=mock_company,
        )

        assert board_role == "tenant_admin"


class TestCustomBoardConfig:
    """Test custom board role configuration."""

    def test_custom_board_role_config(self, board_service, mock_company):
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

    def test_escalate_above_threshold(self, board_service, mock_company):
        """escalate_above="HIGH" + CRITICAL risico → routed naar CEO."""
        mock_company.board_role_config = {
            "thresholds": {
                "escalate_above": "HIGH",
            }
        }

        board_role = board_service._route_to_board_member(
            action_type="budget_increase",  # Would normally go to CFO
            risk_level="CRITICAL",
            department_id=None,
            company=mock_company,
        )

        assert board_role == "CEO"


class TestGoldenRuleR3:
    """Test Golden Rule R3 enforcement."""

    def test_validate_golden_rule_r3_missing_goal(self, board_service):
        """Submit zonder goal_id → GoldenRuleR3Violation."""
        from src.core.company.board_service import GoldenRuleR3Violation
        from src.core.company.context import AgentExecutionContext, GoalChain, PolicyScope

        context = AgentExecutionContext(
            tenant_id=1,
            task_id=uuid4(),
            trace_id=uuid4(),
            goal_chain=GoalChain(),  # Empty
            policy_scope=PolicyScope(risk_level="HIGH"),
        )

        with pytest.raises(GoldenRuleR3Violation) as exc_info:
            board_service._validate_golden_rule_r3(
                {"budget_impact": 10000},
                context,
            )

        assert "goal_id" in str(exc_info.value).lower()

    def test_validate_golden_rule_r3_missing_risk_level(self, board_service):
        """Submit zonder risk_level → GoldenRuleR3Violation."""
        from src.core.company.board_service import GoldenRuleR3Violation
        from src.core.company.context import AgentExecutionContext, GoalChain, PolicyScope

        context = AgentExecutionContext(
            tenant_id=1,
            task_id=uuid4(),
            trace_id=uuid4(),
            goal_chain=GoalChain(mission_id=uuid4(), task_goal_id=uuid4()),
            policy_scope=PolicyScope(risk_level="LOW"),
        )
        context.policy_scope.risk_level = None

        with pytest.raises(GoldenRuleR3Violation) as exc_info:
            board_service._validate_golden_rule_r3(
                {"budget_impact": 10000},
                context,
            )

        assert "risk_level" in str(exc_info.value).lower()

    def test_validate_golden_rule_r3_missing_budget_impact(self, board_service):
        """Submit zonder budget_impact → GoldenRuleR3Violation."""
        from src.core.company.board_service import GoldenRuleR3Violation
        from src.core.company.context import AgentExecutionContext, GoalChain, PolicyScope

        context = AgentExecutionContext(
            tenant_id=1,
            task_id=uuid4(),
            trace_id=uuid4(),
            goal_chain=GoalChain(mission_id=uuid4(), task_goal_id=uuid4()),
            policy_scope=PolicyScope(risk_level="HIGH"),
        )

        with pytest.raises(GoldenRuleR3Violation) as exc_info:
            board_service._validate_golden_rule_r3(
                {},  # No budget_impact
                context,
            )

        assert "budget_impact" in str(exc_info.value).lower()

    def test_validate_golden_rule_r3_complete(self, board_service):
        """Submit met complete context → success."""
        from src.core.company.context import AgentExecutionContext, GoalChain, PolicyScope

        context = AgentExecutionContext(
            tenant_id=1,
            task_id=uuid4(),
            trace_id=uuid4(),
            goal_chain=GoalChain(mission_id=uuid4(), task_goal_id=uuid4()),
            policy_scope=PolicyScope(risk_level="HIGH"),
        )

        # Should not raise
        board_service._validate_golden_rule_r3(
            {"budget_impact": 10000},
            context,
        )


class TestRiskLevelCalculations:
    """Test risk level comparison methods."""

    def test_should_auto_approve_low_risk(self, board_service):
        """LOW risk with LOW threshold → auto-approve."""
        assert board_service._should_auto_approve("LOW", "LOW") is True

    def test_should_not_auto_approve_medium_above_low(self, board_service):
        """MEDIUM risk with LOW threshold → NOT auto-approve."""
        assert board_service._should_auto_approve("MEDIUM", "LOW") is False

    def test_should_auto_approve_medium_with_medium_threshold(self, board_service):
        """MEDIUM risk with MEDIUM threshold → auto-approve."""
        assert board_service._should_auto_approve("MEDIUM", "MEDIUM") is True

    def test_risk_level_higher_than(self, board_service):
        """HIGH is higher than MEDIUM."""
        assert board_service._risk_level_higher_than("HIGH", "MEDIUM") is True

    def test_risk_level_not_higher_than(self, board_service):
        """LOW is not higher than MEDIUM."""
        assert board_service._risk_level_higher_than("LOW", "MEDIUM") is False

    def test_critical_higher_than_high(self, board_service):
        """CRITICAL is higher than HIGH."""
        assert board_service._risk_level_higher_than("CRITICAL", "HIGH") is True


class TestActionTypeMapping:
    """Test action type to routing key mapping."""

    def test_map_budget_action(self, board_service):
        """Budget-related actions map to budget key."""
        assert board_service._map_action_type("budget") == "budget"
        assert board_service._map_action_type("budget_increase") == "budget"
        assert board_service._map_action_type("finance_review") == "budget"
        assert board_service._map_action_type("cost_analysis") == "budget"

    def test_map_agent_hire_action(self, board_service):
        """Agent hire actions map to agent_hire key."""
        assert board_service._map_action_type("agent_hire") == "agent_hire"
        assert board_service._map_action_type("agent_add") == "agent_hire"
        assert board_service._map_action_type("agent_create") == "agent_hire"

    def test_map_agent_firing_action(self, board_service):
        """Agent firing actions map to agent_firing key."""
        assert board_service._map_action_type("agent_firing") == "agent_firing"
        assert board_service._map_action_type("agent_remove") == "agent_firing"
        assert board_service._map_action_type("agent_delete") == "agent_firing"

    def test_map_generic_agent_action(self, board_service):
        """Generic agent actions map to agent_management key."""
        assert board_service._map_action_type("agent_update") == "agent_management"
        assert board_service._map_action_type("agent_list") == "agent_management"

    def test_map_data_export_action(self, board_service):
        """Data export actions map to data_export key."""
        assert board_service._map_action_type("data_export") == "data_export"
        assert board_service._map_action_type("download") == "data_export"

    def test_map_security_action(self, board_service):
        """Security actions map to security key."""
        assert board_service._map_action_type("security") == "security"

    def test_map_hr_action(self, board_service):
        """HR actions map to hr key."""
        assert board_service._map_action_type("hr") == "hr"
        assert board_service._map_action_type("employee_review") == "hr"

    def test_map_unknown_action(self, board_service):
        """Unknown actions map to default key."""
        assert board_service._map_action_type("random") == "default"
        assert board_service._map_action_type("unknown") == "default"


class TestBusinessLanguageTranslation:
    """Test translation to business language."""

    def test_translate_critical(self, board_service):
        """CRITICAL → 'Board approval vereist'."""
        result = board_service._translate_to_business_language(
            {
                "risk_level": "CRITICAL",
                "requires_approval": True,
            }
        )

        assert "Board approval vereist" in result

    def test_translate_high(self, board_service):
        """HIGH → 'Afdelingshoofd moet goedkeuren'."""
        result = board_service._translate_to_business_language(
            {
                "risk_level": "HIGH",
                "requires_approval": True,
            }
        )

        assert "Afdelingshoofd" in result

    def test_translate_medium(self, board_service):
        """MEDIUM → 'Team lead notificatie'."""
        result = board_service._translate_to_business_language(
            {
                "risk_level": "MEDIUM",
                "requires_approval": False,
            }
        )

        assert "Team lead" in result or "notificatie" in result

    def test_translate_low(self, board_service):
        """LOW → 'Automatisch goedgekeurd'."""
        result = board_service._translate_to_business_language(
            {
                "risk_level": "LOW",
                "requires_approval": False,
            }
        )

        assert "Automatisch" in result or "goedgekeurd" in result


class TestServiceFlowIntegration:
    """Test complete service flow with mocked database."""

    @pytest.mark.asyncio
    async def test_submit_creates_decision(
        self, board_service, mock_db_manager, valid_agent_context, mock_company
    ):
        """Submit decision creates BoardDecision record."""
        from src.core.company.models import BoardDecision, BoardDecisionStatus

        # Arrange
        mock_db, mock_session = mock_db_manager

        # Mock company query
        company_result = MagicMock()
        company_result.scalar_one_or_none.return_value = mock_company

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:  # First call - get company
                return company_result
            return MagicMock()

        mock_session.execute = mock_execute

        # Act
        decision = await board_service.submit(
            action_type="budget_increase",
            action_context={"budget_impact": 10000},
            context=valid_agent_context,
        )

        # Assert
        assert decision is not None
        assert decision.tenant_id == 1
        assert decision.action_type == "budget_increase"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_updates_decision(self, board_service, mock_db_manager):
        """Approve updates decision status."""
        from src.core.company.models import BoardDecision, BoardDecisionStatus

        # Arrange
        mock_db, mock_session = mock_db_manager

        mock_decision = MagicMock(spec=BoardDecision)
        mock_decision.id = uuid4()
        mock_decision.tenant_id = 1
        mock_decision.board_role = "CFO"
        mock_decision.decision = None
        mock_decision.decided_by = None
        mock_decision.decided_at = None

        decision_result = MagicMock()
        decision_result.scalar_one_or_none.return_value = mock_decision

        board_service._user_has_board_role = AsyncMock(return_value=True)
        mock_session.execute = AsyncMock(return_value=decision_result)

        # Act
        result = await board_service.approve(
            decision_id=mock_decision.id,
            user_id=1,
            reason="Approved",
        )

        # Assert
        assert result.decision == BoardDecisionStatus.APPROVED.value
        assert result.decided_by == 1

    @pytest.mark.asyncio
    async def test_reject_updates_decision(self, board_service, mock_db_manager):
        """Reject updates decision status with reason."""
        from src.core.company.models import BoardDecision, BoardDecisionStatus

        # Arrange
        mock_db, mock_session = mock_db_manager

        mock_decision = MagicMock(spec=BoardDecision)
        mock_decision.id = uuid4()
        mock_decision.tenant_id = 1
        mock_decision.board_role = "CFO"
        mock_decision.decision = None

        decision_result = MagicMock()
        decision_result.scalar_one_or_none.return_value = mock_decision

        board_service._user_has_board_role = AsyncMock(return_value=True)
        mock_session.execute = AsyncMock(return_value=decision_result)

        # Act
        result = await board_service.reject(
            decision_id=mock_decision.id,
            user_id=1,
            reason="Budget too high",
        )

        # Assert
        assert result.decision == BoardDecisionStatus.REJECTED.value
        assert result.reason == "Budget too high"
