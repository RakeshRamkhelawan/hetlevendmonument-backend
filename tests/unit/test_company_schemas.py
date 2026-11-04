"""Tests for Company Layer Pydantic Schemas - Taak 1.4

TDD tests for API request/response schemas.
"""

import uuid
from datetime import datetime
from typing import Optional

import pytest
from pydantic import ValidationError

# ============================================================================
# Company Schemas Tests
# ============================================================================


class TestCompanyCreate:
    """Tests for CompanyCreate schema"""

    def test_company_create_valid(self):
        """Valid company creation with all required fields"""
        from src.core.company.schemas import CompanyCreate

        data = CompanyCreate(
            name="Acme Corp",
            company_type="mkb",
            sector="technology",
        )

        assert data.name == "Acme Corp"
        assert data.company_type == "mkb"
        assert data.sector == "technology"
        assert data.mission is None
        assert data.template_id is None

    def test_company_create_with_optional_fields(self):
        """Company creation with optional fields"""
        from src.core.company.schemas import CompanyCreate

        template_id = uuid.uuid4()
        data = CompanyCreate(
            name="Acme Corp",
            company_type="enterprise",
            sector="finance",
            mission="Our mission is to...",
            template_id=template_id,
        )

        assert data.mission == "Our mission is to..."
        assert data.template_id == template_id

    def test_company_create_invalid_type(self):
        """Invalid company_type → validation error"""
        from src.core.company.schemas import CompanyCreate

        with pytest.raises(ValidationError) as exc_info:
            CompanyCreate(
                name="Acme Corp",
                company_type="invalid_type",
                sector="technology",
            )

        assert "company_type" in str(exc_info.value)

    def test_company_create_name_too_short(self):
        """Name with < 2 characters → validation error"""
        from src.core.company.schemas import CompanyCreate

        with pytest.raises(ValidationError) as exc_info:
            CompanyCreate(
                name="A",
                company_type="mkb",
                sector="technology",
            )

        assert "name" in str(exc_info.value)


class TestCompanyUpdate:
    """Tests for CompanyUpdate schema"""

    def test_company_update_partial(self):
        """Partial update with only name"""
        from src.core.company.schemas import CompanyUpdate

        data = CompanyUpdate(name="New Name")

        assert data.name == "New Name"
        assert data.company_type is None
        assert data.sector is None

    def test_company_update_all_fields(self):
        """Update all fields"""
        from src.core.company.schemas import CompanyUpdate

        data = CompanyUpdate(
            name="New Name",
            company_type="enterprise",
            sector="healthcare",
            mission="Updated mission",
        )

        assert data.name == "New Name"
        assert data.company_type == "enterprise"
        assert data.sector == "healthcare"
        assert data.mission == "Updated mission"

    def test_company_update_empty(self):
        """Empty update is allowed (no fields)"""
        from src.core.company.schemas import CompanyUpdate

        data = CompanyUpdate()

        assert data.name is None
        assert data.company_type is None


class TestCompanyResponse:
    """Tests for CompanyResponse schema"""

    def test_company_response_valid(self):
        """Valid company response"""
        from src.core.company.schemas import CompanyResponse

        now = datetime.utcnow()
        data = CompanyResponse(
            id=uuid.uuid4(),
            tenant_id=1,
            name="Acme Corp",
            company_type="mkb",
            sector="technology",
            mission="Our mission",
            status="active",
            departments_count=5,
            goals_count=10,
            created_at=now,
        )

        assert data.name == "Acme Corp"
        assert data.departments_count == 5
        assert data.goals_count == 10


class TestCompanyListResponse:
    """Tests for CompanyListResponse schema"""

    def test_company_list_response(self):
        """List response with companies"""
        from src.core.company.schemas import CompanyListResponse, CompanyResponse

        now = datetime.utcnow()
        companies = [
            CompanyResponse(
                id=uuid.uuid4(),
                tenant_id=1,
                name="Company 1",
                company_type="mkb",
                sector="tech",
                status="active",
                departments_count=2,
                goals_count=3,
                created_at=now,
            ),
            CompanyResponse(
                id=uuid.uuid4(),
                tenant_id=1,
                name="Company 2",
                company_type="enterprise",
                sector="finance",
                status="active",
                departments_count=5,
                goals_count=10,
                created_at=now,
            ),
        ]

        response = CompanyListResponse(companies=companies, total=2)

        assert len(response.companies) == 2
        assert response.total == 2


# ============================================================================
# Department Schemas Tests
# ============================================================================


class TestDepartmentCreate:
    """Tests for DepartmentCreate schema"""

    def test_department_create_minimal(self):
        """Minimal department creation"""
        from src.core.company.schemas import DepartmentCreate

        data = DepartmentCreate(name="Engineering")

        assert data.name == "Engineering"
        assert data.parent_department_id is None
        assert data.head_user_id is None

    def test_department_create_full(self):
        """Full department creation with all fields"""
        from src.core.company.schemas import DepartmentCreate

        parent_id = uuid.uuid4()
        head_id = uuid.uuid4()

        data = DepartmentCreate(
            name="Engineering",
            parent_department_id=parent_id,
            head_user_id=head_id,
            board_role="CTO",
            budget_monthly_tokens=100000,
        )

        assert data.parent_department_id == parent_id
        assert data.head_user_id == head_id
        assert data.board_role == "CTO"
        assert data.budget_monthly_tokens == 100000


class TestDepartmentUpdate:
    """Tests for DepartmentUpdate schema with optimistic locking"""

    def test_department_update_with_version(self):
        """Update with expected_version for optimistic locking"""
        from src.core.company.schemas import DepartmentUpdate

        data = DepartmentUpdate(
            name="New Name",
            expected_version=5,
        )

        assert data.name == "New Name"
        assert data.expected_version == 5

    def test_department_update_partial(self):
        """Partial update without version"""
        from src.core.company.schemas import DepartmentUpdate

        data = DepartmentUpdate(board_role="CFO")

        assert data.board_role == "CFO"
        assert data.expected_version is None


class TestDepartmentResponse:
    """Tests for DepartmentResponse schema"""

    def test_department_response(self):
        """Valid department response"""
        from src.core.company.schemas import DepartmentResponse

        data = DepartmentResponse(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            name="Engineering",
            parent_department_id=None,
            head_user_id=uuid.uuid4(),
            board_role="CTO",
            budget_monthly_tokens=100000,
            domain_pack_ids=["pack-1", "pack-2"],
            version=3,
            children_count=2,
        )

        assert data.name == "Engineering"
        assert data.version == 3
        assert data.children_count == 2
        assert len(data.domain_pack_ids) == 2


class TestOrgChartResponse:
    """Tests for OrgChartResponse schema"""

    def test_org_chart_response(self):
        """Org chart with tree structure"""
        from src.core.company.schemas import DepartmentResponse, OrgChartResponse

        departments = [
            DepartmentResponse(
                id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                name="Engineering",
                board_role="CTO",
                domain_pack_ids=[],
                version=1,
                children_count=2,
            ),
        ]
        tree = {
            "root": departments[0].id,
            "children": {},
        }

        response = OrgChartResponse(departments=departments, tree_structure=tree)

        assert len(response.departments) == 1
        assert "root" in response.tree_structure


# ============================================================================
# Goal Schemas Tests
# ============================================================================


class TestGoalCreate:
    """Tests for GoalCreate schema"""

    def test_goal_create_minimal(self):
        """Minimal goal creation"""
        from src.core.company.schemas import GoalCreate

        data = GoalCreate(
            goal_type="task",
            title="Complete feature",
        )

        assert data.goal_type == "task"
        assert data.title == "Complete feature"
        assert data.parent_goal_id is None

    def test_goal_create_with_kpis(self):
        """Goal creation with KPIs"""
        from src.core.company.schemas import GoalCreate

        deadline = datetime.utcnow()
        data = GoalCreate(
            goal_type="strategic",
            title="Increase revenue",
            description="Grow by 50%",
            kpis=["metric-1", "metric-2"],
            deadline=deadline,
        )

        assert data.goal_type == "strategic"
        assert len(data.kpis) == 2
        assert data.deadline == deadline

    def test_goal_create_invalid_type(self):
        """Invalid goal_type → validation error"""
        from src.core.company.schemas import GoalCreate

        with pytest.raises(ValidationError) as exc_info:
            GoalCreate(
                goal_type="invalid",
                title="Test",
            )

        assert "goal_type" in str(exc_info.value)


class TestGoalUpdate:
    """Tests for GoalUpdate schema"""

    def test_goal_update_progress(self):
        """Update goal progress"""
        from src.core.company.schemas import GoalUpdate

        data = GoalUpdate(
            status="in_progress",
            progress_pct=50,
        )

        assert data.status == "in_progress"
        assert data.progress_pct == 50

    def test_goal_update_progress_out_of_range(self):
        """Progress > 100 → validation error"""
        from src.core.company.schemas import GoalUpdate

        with pytest.raises(ValidationError) as exc_info:
            GoalUpdate(progress_pct=150)

        assert "progress_pct" in str(exc_info.value)


class TestGoalResponse:
    """Tests for GoalResponse schema"""

    def test_goal_response(self):
        """Valid goal response"""
        from src.core.company.schemas import GoalResponse

        data = GoalResponse(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            goal_type="strategic",
            title="Revenue Growth",
            description="Grow revenue",
            status="active",
            progress_pct=75,
            kpis=["revenue", "customers"],
            deadline=None,
            parent_goal_id=None,
            children_count=3,
        )

        assert data.progress_pct == 75
        assert data.children_count == 3


class TestGoalAncestryResponse:
    """Tests for GoalAncestryResponse schema"""

    def test_goal_ancestry_response(self):
        """Goal ancestry with chain"""
        from src.core.company.context import GoalChain
        from src.core.company.schemas import GoalAncestryResponse, GoalResponse

        goals = [
            GoalResponse(
                id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                goal_type="mission",
                title="Mission",
                status="active",
                progress_pct=0,
                children_count=1,
            ),
        ]
        chain = GoalChain(mission_id=goals[0].id)

        response = GoalAncestryResponse(chain=goals, goal_chain=chain)

        assert len(response.chain) == 1
        assert response.goal_chain.mission_id == goals[0].id


# ============================================================================
# External Agent Schemas Tests
# ============================================================================


class TestExternalAgentRegister:
    """Tests for ExternalAgentRegister schema"""

    def test_external_agent_register_minimal(self):
        """Minimal external agent registration"""
        from src.core.company.schemas import ExternalAgentRegister

        data = ExternalAgentRegister(
            name="Agent-1",
            runtime="python-3.11",
            capabilities=["data-processing", "api-integration"],
        )

        assert data.name == "Agent-1"
        assert data.runtime == "python-3.11"
        assert len(data.capabilities) == 2

    def test_external_agent_register_full(self):
        """Full registration with optional fields"""
        from src.core.company.schemas import ExternalAgentRegister

        dept_id = uuid.uuid4()
        data = ExternalAgentRegister(
            name="Agent-1",
            runtime="python-3.11",
            capabilities=["ml"],
            heartbeat_interval_seconds=60,
            webhook_url="https://example.com/webhook",
            department_id=dept_id,
        )

        assert data.heartbeat_interval_seconds == 60
        assert data.webhook_url == "https://example.com/webhook"
        assert data.department_id == dept_id


class TestExternalAgentResponse:
    """Tests for ExternalAgentResponse schema"""

    def test_external_agent_response(self):
        """Valid external agent response"""
        from src.core.company.schemas import ExternalAgentResponse

        now = datetime.utcnow()
        data = ExternalAgentResponse(
            agent_id=uuid.uuid4(),
            name="Agent-1",
            runtime="python-3.11",
            capabilities=["ml"],
            status="active",
            last_heartbeat_at=now,
            metrics={"tasks_completed": 100},
        )

        assert data.status == "active"
        assert data.metrics["tasks_completed"] == 100


class TestHeartbeatRequest:
    """Tests for HeartbeatRequest schema"""

    def test_heartbeat_request_idle(self):
        """Heartbeat with idle status"""
        from src.core.company.schemas import HeartbeatRequest

        data = HeartbeatRequest(status="idle")

        assert data.status == "idle"
        assert data.current_task_id is None

    def test_heartbeat_request_busy(self):
        """Heartbeat with busy status and progress"""
        from src.core.company.schemas import HeartbeatRequest

        task_id = uuid.uuid4()
        data = HeartbeatRequest(
            status="busy",
            current_task_id=task_id,
            progress=75.5,
            metrics={"cpu": 80},
        )

        assert data.status == "busy"
        assert data.current_task_id == task_id
        assert data.progress == 75.5

    def test_heartbeat_request_invalid_status(self):
        """Invalid status → validation error"""
        from src.core.company.schemas import HeartbeatRequest

        with pytest.raises(ValidationError) as exc_info:
            HeartbeatRequest(status="unknown")

        assert "status" in str(exc_info.value)


class TestHeartbeatResponse:
    """Tests for HeartbeatResponse schema"""

    def test_heartbeat_response(self):
        """Valid heartbeat response"""
        from src.core.company.schemas import HeartbeatResponse

        data = HeartbeatResponse(
            ack=True,
            pending_tasks=["task-1", "task-2"],
        )

        assert data.ack is True
        assert len(data.pending_tasks) == 2


class TestTaskNextResponse:
    """Tests for TaskNextResponse schema"""

    def test_task_next_response(self):
        """Valid task assignment response"""
        from src.core.company.context import AgentExecutionContext
        from src.core.company.schemas import TaskNextResponse

        context = AgentExecutionContext(
            tenant_id=1,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
        )

        data = TaskNextResponse(
            task_id=uuid.uuid4(),
            action="process_data",
            input={"data": "value"},
            context=context,
            sla_seconds=3600,
        )

        assert data.action == "process_data"
        assert data.sla_seconds == 3600
        assert data.context.tenant_id == 1


class TestTaskCompleteRequest:
    """Tests for TaskCompleteRequest schema"""

    def test_task_complete_success(self):
        """Successful task completion"""
        from src.core.company.schemas import TaskCompleteRequest

        data = TaskCompleteRequest(
            status="completed",
            output={"result": "success"},
        )

        assert data.status == "completed"
        assert data.output["result"] == "success"

    def test_task_complete_failure(self):
        """Failed task completion"""
        from src.core.company.schemas import TaskCompleteRequest

        data = TaskCompleteRequest(
            status="failed",
            output={"error": "Timeout"},
            reasoning_trace="Error occurred during processing",
        )

        assert data.status == "failed"
        assert data.reasoning_trace is not None


# ============================================================================
# Board Governance Schemas Tests
# ============================================================================


class TestBoardDecisionResponse:
    """Tests for BoardDecisionResponse schema"""

    def test_board_decision_response_pending(self):
        """Pending board decision"""
        from src.core.company.schemas import BoardDecisionResponse

        now = datetime.utcnow()
        data = BoardDecisionResponse(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            requested_by=uuid.uuid4(),
            board_role="CTO",
            action_type="budget_increase",
            action_context={"amount": 10000},
            goal_id=None,
            decision=None,
            decided_by=None,
            reason=None,
            decided_at=None,
            created_at=now,
        )

        assert data.decision is None
        assert data.decided_by is None

    def test_board_decision_response_approved(self):
        """Approved board decision"""
        from src.core.company.schemas import BoardDecisionResponse

        now = datetime.utcnow()
        data = BoardDecisionResponse(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            requested_by=uuid.uuid4(),
            board_role="CTO",
            action_type="budget_increase",
            action_context={"amount": 10000},
            decision="approved",
            decided_by=uuid.uuid4(),
            reason="Within budget",
            decided_at=now,
            created_at=now,
        )

        assert data.decision == "approved"
        assert data.reason == "Within budget"


class TestBoardApproveRequest:
    """Tests for BoardApproveRequest schema"""

    def test_board_approve_with_reason(self):
        """Approve with optional reason"""
        from src.core.company.schemas import BoardApproveRequest

        data = BoardApproveRequest(reason="Approved after review")

        assert data.reason == "Approved after review"

    def test_board_approve_without_reason(self):
        """Approve without reason"""
        from src.core.company.schemas import BoardApproveRequest

        data = BoardApproveRequest()

        assert data.reason is None


class TestBoardRejectRequest:
    """Tests for BoardRejectRequest schema"""

    def test_board_reject_with_reason(self):
        """Reject with required reason"""
        from src.core.company.schemas import BoardRejectRequest

        data = BoardRejectRequest(reason="Over budget")

        assert data.reason == "Over budget"

    def test_board_reject_without_reason(self):
        """Reject without reason → validation error"""
        from src.core.company.schemas import BoardRejectRequest

        with pytest.raises(ValidationError) as exc_info:
            BoardRejectRequest()

        assert "reason" in str(exc_info.value)


class TestBoardQueueResponse:
    """Tests for BoardQueueResponse schema"""

    def test_board_queue_response(self):
        """Board queue with pending decisions"""
        from src.core.company.schemas import BoardDecisionResponse, BoardQueueResponse

        now = datetime.utcnow()
        decisions = [
            BoardDecisionResponse(
                id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                requested_by=uuid.uuid4(),
                board_role="CTO",
                action_type="approve",
                action_context={},
                created_at=now,
            ),
        ]

        response = BoardQueueResponse(decisions=decisions, pending_count=1)

        assert len(response.decisions) == 1
        assert response.pending_count == 1


# ============================================================================
# Template Schemas Tests
# ============================================================================


class TestTemplateResponse:
    """Tests for TemplateResponse schema"""

    def test_template_response(self):
        """Valid template response"""
        from src.core.company.schemas import TemplateResponse

        data = TemplateResponse(
            id=uuid.uuid4(),
            name="Tech Startup",
            company_type="mkb",
            sector="technology",
            description="Template for tech startups",
            is_platform_template=True,
            usage_count=150,
            rating_avg=4.5,
        )

        assert data.name == "Tech Startup"
        assert data.rating_avg == 4.5

    def test_template_response_no_rating(self):
        """Template without ratings"""
        from src.core.company.schemas import TemplateResponse

        data = TemplateResponse(
            id=uuid.uuid4(),
            name="New Template",
            company_type="zzp",
            sector="consulting",
            description="New",
            is_platform_template=False,
            usage_count=0,
            rating_avg=None,
        )

        assert data.rating_avg is None


class TestTemplateInstantiateRequest:
    """Tests for TemplateInstantiateRequest schema"""

    def test_template_instantiate(self):
        """Template instantiation request"""
        from src.core.company.schemas import TemplateInstantiateRequest

        template_id = uuid.uuid4()
        data = TemplateInstantiateRequest(
            template_id=template_id,
            company_name="My Company",
            customizations={"mission": "Custom mission"},
        )

        assert data.template_id == template_id
        assert data.company_name == "My Company"
        assert data.customizations["mission"] == "Custom mission"


# ============================================================================
# Onboarding Schemas Tests
# ============================================================================


class TestOnboardingAIMatchRequest:
    """Tests for OnboardingAIMatchRequest schema"""

    def test_onboarding_ai_match_request(self):
        """AI match request"""
        from src.core.company.schemas import OnboardingAIMatchRequest

        data = OnboardingAIMatchRequest(
            description="Tech startup in fintech space with 10 employees",
        )

        assert "fintech" in data.description


class TestOnboardingAIMatchResponse:
    """Tests for OnboardingAIMatchResponse schema"""

    def test_onboarding_ai_match_response(self):
        """AI match response with confidence"""
        from src.core.company.schemas import OnboardingAIMatchResponse

        data = OnboardingAIMatchResponse(
            template_id=uuid.uuid4(),
            template_name="Fintech Startup",
            confidence=0.92,
            match_reason="Matches your fintech industry and startup size",
        )

        assert data.confidence == 0.92
        assert 0 <= data.confidence <= 1


class TestOnboardingCompleteRequest:
    """Tests for OnboardingCompleteRequest schema"""

    def test_onboarding_complete_minimal(self):
        """Minimal onboarding completion"""
        from src.core.company.schemas import OnboardingCompleteRequest

        data = OnboardingCompleteRequest(
            company_name="Acme Corp",
            company_type="mkb",
            sector="technology",
        )

        assert data.company_name == "Acme Corp"
        assert data.template_id is None
        assert data.goals is None

    def test_onboarding_complete_with_goals(self):
        """Onboarding with initial goals"""
        from src.core.company.schemas import GoalCreate, OnboardingCompleteRequest

        data = OnboardingCompleteRequest(
            company_name="Acme Corp",
            company_type="mkb",
            sector="technology",
            mission="Our mission",
            goals=[
                GoalCreate(goal_type="mission", title="Company Mission"),
                GoalCreate(goal_type="strategic", title="Year 1 Goals"),
            ],
        )

        assert len(data.goals) == 2
        assert data.goals[0].goal_type == "mission"


# ============================================================================
# Error Response Schemas Tests
# ============================================================================


class TestConflictResponse:
    """Tests for ConflictResponse schema (409 errors)"""

    def test_conflict_response_full(self):
        """Full conflict response with all fields"""
        from src.core.company.schemas import ConflictResponse

        data = ConflictResponse(
            detail="Department is gewijzigd door andere gebruiker",
            error_code="CONFLICT",
            current_version=5,
            conflicting_user="user@example.com",
        )

        assert data.error_code == "CONFLICT"
        assert data.current_version == 5
        assert data.conflicting_user == "user@example.com"

    def test_conflict_response_defaults(self):
        """Conflict response with defaults"""
        from src.core.company.schemas import ConflictResponse

        data = ConflictResponse(
            detail="Resource modified",
            current_version=3,
        )

        assert data.error_code == "CONFLICT"
        assert data.conflicting_user is None


# ============================================================================
# JSON Serialization Tests
# ============================================================================


class TestJSONSerialization:
    """Tests for JSON serialization of all schemas"""

    def test_company_response_json(self):
        """CompanyResponse serializes to JSON"""
        import json

        from src.core.company.schemas import CompanyResponse

        now = datetime.utcnow()
        data = CompanyResponse(
            id=uuid.uuid4(),
            tenant_id=1,
            name="Acme",
            company_type="mkb",
            sector="tech",
            status="active",
            departments_count=2,
            goals_count=3,
            created_at=now,
        )

        json_str = data.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["name"] == "Acme"
        assert parsed["departments_count"] == 2

    def test_agent_execution_context_in_task_response(self):
        """TaskNextResponse with context serializes correctly"""
        import json

        from src.core.company.context import AgentExecutionContext
        from src.core.company.schemas import TaskNextResponse

        context = AgentExecutionContext(
            tenant_id=1,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
        )

        data = TaskNextResponse(
            task_id=uuid.uuid4(),
            action="test",
            input={},
            context=context,
        )

        json_str = data.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["context"]["tenant_id"] == 1
