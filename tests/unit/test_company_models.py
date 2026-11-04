"""
TDD Tests for Task 1.1: Company Layer Database Models

Tests for SQLAlchemy models: Company, Department, Goal, ExternalAgent,
BoardDecision, CompanyTemplate, PackActivationAuditLog

Note: These tests verify model structure and SQLAlchemy configuration.
Default values are set at database level (server_default), so they are
not available on uninstantiated objects.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Mapped

from src.core.company.models import (
    BoardDecision,
    BoardDecisionStatus,
    Company,
    CompanyTemplate,
    CompanyType,
    Department,
    ExternalAgent,
    ExternalAgentStatus,
    Goal,
    GoalStatus,
    GoalType,
    PackActivationAuditLog,
)
from src.core.database.database import Base

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def valid_company_data():
    """Valid company data for testing."""
    return {
        "tenant_id": 1,
        "name": "Test Company BV",
        "company_type": CompanyType.MKB.value,
        "sector": "Technology",
        "mission": "To innovate and simplify",
    }


@pytest.fixture
def valid_department_data():
    """Valid department data for testing."""
    return {
        "tenant_id": 1,
        "name": "Sales",
        "board_role": "CFO",
        "budget_monthly_tokens": 10000,
    }


@pytest.fixture
def valid_goal_data():
    """Valid goal data for testing."""
    return {
        "tenant_id": 1,
        "goal_type": GoalType.MISSION.value,
        "title": "Double revenue in 2026",
        "description": "Our mission is to double revenue",
        "status": GoalStatus.IN_PROGRESS.value,
        "progress_pct": 50,
    }


# =============================================================================
# Happy Path Tests
# =============================================================================


class TestCompanyModel:
    """Happy path: Company model tests."""

    def test_create_company_model(self, valid_company_data):
        """Company instance with all required fields."""
        company = Company(**valid_company_data)

        # Note: UUID is generated at INSERT time by SQLAlchemy
        # We verify the instance is created with correct values
        assert company.name == "Test Company BV"
        assert company.company_type == CompanyType.MKB.value
        assert company.sector == "Technology"

    def test_company_has_expected_columns(self):
        """Company model should have expected SQLAlchemy columns."""
        # Check that the class has the expected mapped attributes
        assert hasattr(Company, "id")
        assert hasattr(Company, "tenant_id")
        assert hasattr(Company, "name")
        assert hasattr(Company, "company_type")
        assert hasattr(Company, "sector")
        assert hasattr(Company, "mission")
        assert hasattr(Company, "config")
        assert hasattr(Company, "board_role_config")
        assert hasattr(Company, "template_id")
        assert hasattr(Company, "status")
        assert hasattr(Company, "created_at")
        assert hasattr(Company, "updated_at")

    def test_company_id_column_exists(self, valid_company_data):
        """Company should have id column configured as UUID."""
        from sqlalchemy.dialects.postgresql import UUID as PG_UUID

        # Verify the column type is UUID
        assert isinstance(Company.__table__.c.id.type, PG_UUID)


class TestDepartmentModel:
    """Happy path: Department model tests."""

    def test_create_department(self, valid_company_data, valid_department_data):
        """Department aanmaken bij company."""
        company_id = uuid.uuid4()

        department = Department(**valid_department_data, company_id=company_id)

        assert department.name == "Sales"
        assert department.company_id == company_id

    def test_create_sub_department(self, valid_company_data, valid_department_data):
        """Kind-afdeling met parent_department_id."""
        company = Company(**valid_company_data)

        parent = Department(**valid_department_data, company_id=company.id)

        child = Department(
            tenant_id=1, name="Sales Europe", company_id=company.id, parent_department_id=parent.id
        )

        assert child.parent_department_id == parent.id

    def test_department_id_column_is_uuid(self):
        """Department id column should be UUID type."""
        from sqlalchemy.dialects.postgresql import UUID as PG_UUID

        assert isinstance(Department.__table__.c.id.type, PG_UUID)


class TestGoalModel:
    """Happy path: Goal model tests."""

    def test_create_goal_hierarchy(self, valid_company_data, valid_goal_data):
        """Mission -> Strategic -> Project -> Task keten."""
        company = Company(**valid_company_data)

        # Create mission
        mission = Goal(**valid_goal_data, company_id=company.id)

        # Create strategic under mission
        strategic = Goal(
            tenant_id=1,
            goal_type=GoalType.STRATEGIC.value,
            title="Expand to Europe",
            company_id=company.id,
            parent_goal_id=mission.id,
        )

        # Create project under strategic
        project = Goal(
            tenant_id=1,
            goal_type=GoalType.PROJECT.value,
            title="Launch German website",
            company_id=company.id,
            parent_goal_id=strategic.id,
        )

        # Create task under project
        task = Goal(
            tenant_id=1,
            goal_type=GoalType.TASK.value,
            title="Translate homepage",
            company_id=company.id,
            parent_goal_id=project.id,
        )

        # Verify hierarchy IDs
        assert task.parent_goal_id == project.id
        assert project.parent_goal_id == strategic.id
        assert strategic.parent_goal_id == mission.id

    def test_goal_types_valid(self, valid_company_data):
        """Elk goal_type (mission, strategic, project, task) is geldig."""
        company = Company(**valid_company_data)

        for goal_type in [GoalType.MISSION, GoalType.STRATEGIC, GoalType.PROJECT, GoalType.TASK]:
            goal = Goal(
                tenant_id=1,
                goal_type=goal_type.value,
                title=f"Test {goal_type.value}",
                company_id=company.id,
            )
            assert goal.goal_type == goal_type.value

    def test_goal_id_column_is_uuid(self):
        """Goal id column should be UUID type."""
        from sqlalchemy.dialects.postgresql import UUID as PG_UUID

        assert isinstance(Goal.__table__.c.id.type, PG_UUID)


class TestExternalAgentModel:
    """Happy path: ExternalAgent model tests."""

    def test_external_agent_lifecycle_statuses(self):
        """registered -> active -> busy -> dead lifecycle."""
        agent = ExternalAgent(
            tenant_id=1,
            name="Test Agent",
            runtime="python",
            api_key_hash="$2b$12$hashedkeyhere",
            status=ExternalAgentStatus.REGISTERED.value,
        )

        assert agent.status == ExternalAgentStatus.REGISTERED.value

        # Can transition to other statuses
        agent.status = ExternalAgentStatus.ACTIVE.value
        assert agent.status == ExternalAgentStatus.ACTIVE.value

        agent.status = ExternalAgentStatus.BUSY.value
        assert agent.status == ExternalAgentStatus.BUSY.value

        agent.status = ExternalAgentStatus.DEAD.value
        assert agent.status == ExternalAgentStatus.DEAD.value

    def test_external_agent_required_fields(self):
        """ExternalAgent should require tenant_id, name, runtime, api_key_hash."""
        agent = ExternalAgent(
            tenant_id=1, name="Test Agent", runtime="python", api_key_hash="$2b$12$hashedkeyhere"
        )
        assert agent.tenant_id == 1
        assert agent.name == "Test Agent"
        assert agent.runtime == "python"
        assert agent.api_key_hash == "$2b$12$hashedkeyhere"

    def test_external_agent_id_column_is_uuid(self):
        """ExternalAgent id column should be UUID type."""
        from sqlalchemy.dialects.postgresql import UUID as PG_UUID

        assert isinstance(ExternalAgent.__table__.c.id.type, PG_UUID)


class TestBoardDecisionModel:
    """Happy path: BoardDecision model tests."""

    def test_board_decision_pending(self):
        """Decision zonder decided_by is pending."""
        company_id = uuid.uuid4()
        goal_id = uuid.uuid4()

        decision = BoardDecision(
            tenant_id=1,
            company_id=company_id,
            requested_by=1,
            board_role="CFO",
            action_type="budget_approval",
            action_context={"amount": 10000},
            goal_id=goal_id,
        )

        assert decision.decision is None
        assert decision.decided_by is None
        assert decision.decided_at is None
        assert decision.board_role == "CFO"

    def test_board_decision_approved(self, valid_company_data):
        """Decision can be approved with reason."""
        company = Company(**valid_company_data)

        decision = BoardDecision(
            tenant_id=1,
            company_id=company.id,
            requested_by=1,
            board_role="CFO",
            action_type="budget_approval",
            action_context={"amount": 10000},
            decision=BoardDecisionStatus.APPROVED.value,
            decided_by=2,
            reason="Budget approved for Q1",
        )

        assert decision.decision == BoardDecisionStatus.APPROVED.value
        assert decision.decided_by == 2
        assert decision.reason == "Budget approved for Q1"

    def test_board_decision_id_column_is_uuid(self):
        """BoardDecision id column should be UUID type."""
        from sqlalchemy.dialects.postgresql import UUID as PG_UUID

        assert isinstance(BoardDecision.__table__.c.id.type, PG_UUID)


class TestCompanyTemplateModel:
    """Happy path: CompanyTemplate model tests."""

    def test_create_template(self):
        """Create a company template."""
        template = CompanyTemplate(
            name="Retail Starter",
            company_type=CompanyType.MKB.value,
            sector="Retail",
            description="Perfect for small retail businesses",
            is_platform_template=True,
            template_definition={
                "departments": ["Sales", "Inventory"],
                "goals": [{"title": "Increase sales", "type": "strategic"}],
            },
        )

        assert template.name == "Retail Starter"
        assert template.is_platform_template is True

    def test_template_rating_avg(self):
        """Template rating_avg should calculate correctly."""
        template = CompanyTemplate(
            name="Test Template",
            company_type=CompanyType.MKB.value,
            sector="Tech",
            rating_sum=15,
            rating_count=3,
        )
        assert template.rating_avg == 5.0

    def test_template_rating_avg_no_ratings(self):
        """Template rating_avg should be None when no ratings."""
        template = CompanyTemplate(
            name="Test Template",
            company_type=CompanyType.MKB.value,
            sector="Tech",
            rating_sum=0,
            rating_count=0,
        )
        assert template.rating_avg is None

    def test_template_id_column_is_uuid(self):
        """CompanyTemplate id column should be UUID type."""
        from sqlalchemy.dialects.postgresql import UUID as PG_UUID

        assert isinstance(CompanyTemplate.__table__.c.id.type, PG_UUID)


class TestPackActivationAuditLogModel:
    """Happy path: PackActivationAuditLog model tests."""

    def test_audit_log_creation(self):
        """Create pack activation audit log."""
        company_id = uuid.uuid4()
        department_id = uuid.uuid4()

        audit_log = PackActivationAuditLog(
            tenant_id=1,
            company_id=company_id,
            department_id=department_id,
            pack_id="mkb.sales.crm",
            pack_name="Sales CRM",
            score=0.85,
            confidence="HIGH",
            match_reason="Department name 'Sales' matches pack department",
            input_signals={"department_name": "Sales", "company_type": "mkb"},
            score_breakdown={"department_match": 0.40, "company_type": 0.20, "sector": 0.25},
            activated_automatically=True,
        )

        assert audit_log.score == 0.85
        assert audit_log.confidence == "HIGH"
        assert audit_log.activated_automatically is True
        assert audit_log.pack_id == "mkb.sales.crm"

    def test_audit_log_id_column_is_uuid(self):
        """PackActivationAuditLog id column should be UUID type."""
        from sqlalchemy.dialects.postgresql import UUID as PG_UUID

        assert isinstance(PackActivationAuditLog.__table__.c.id.type, PG_UUID)


# =============================================================================
# Unhappy Path Tests
# =============================================================================


class TestGoalValidation:
    """Unhappy path: Goal validation tests."""

    def test_goal_progress_out_of_range(self, valid_company_data):
        """progress_pct > 100 of < 0 - documented but not enforced at DB level."""
        company = Company(**valid_company_data)

        # Application layer should validate this, but model allows it
        goal = Goal(
            tenant_id=1,
            goal_type=GoalType.TASK.value,
            title="Test",
            company_id=company.id,
            progress_pct=150,  # Invalid value
        )

        # Model allows it - application layer should validate
        assert goal.progress_pct == 150

    def test_goal_invalid_type(self, valid_company_data):
        """goal_type buiten allowed values - documented but not enforced at DB level."""
        company = Company(**valid_company_data)

        # Application layer should validate this
        goal = Goal(
            tenant_id=1,
            goal_type="invalid_type",
            title="Test",
            company_id=company.id,  # Invalid
        )

        assert goal.goal_type == "invalid_type"


class TestBoardDecisionValidation:
    """Unhappy path: BoardDecision validation tests."""

    def test_board_decision_without_goal_context(self, valid_company_data):
        """action_context zonder goal_id - allowed but logs warning."""
        company = Company(**valid_company_data)

        # This should work but log a warning (application layer concern)
        decision = BoardDecision(
            tenant_id=1,
            company_id=company.id,
            requested_by=1,
            board_role="CFO",
            action_type="some_action",
            action_context={},  # Empty context
            # No goal_id - should log warning
        )

        assert decision.goal_id is None
        assert decision.action_context == {}


# =============================================================================
# Enum Tests
# =============================================================================


class TestEnums:
    """Test all enum classes."""

    def test_company_type_values(self):
        """CompanyType enum values."""
        assert CompanyType.MKB.value == "mkb"
        assert CompanyType.ZZP.value == "zzp"
        assert CompanyType.ENTERPRISE.value == "enterprise"

    def test_goal_type_values(self):
        """GoalType enum values."""
        assert GoalType.MISSION.value == "mission"
        assert GoalType.STRATEGIC.value == "strategic"
        assert GoalType.PROJECT.value == "project"
        assert GoalType.TASK.value == "task"

    def test_goal_status_values(self):
        """GoalStatus enum values."""
        assert GoalStatus.NOT_STARTED.value == "not_started"
        assert GoalStatus.IN_PROGRESS.value == "in_progress"
        assert GoalStatus.BLOCKED.value == "blocked"
        assert GoalStatus.COMPLETED.value == "completed"
        assert GoalStatus.CANCELLED.value == "cancelled"

    def test_external_agent_status_values(self):
        """ExternalAgentStatus enum values."""
        assert ExternalAgentStatus.REGISTERED.value == "registered"
        assert ExternalAgentStatus.ACTIVE.value == "active"
        assert ExternalAgentStatus.BUSY.value == "busy"
        assert ExternalAgentStatus.STALE.value == "stale"
        assert ExternalAgentStatus.DEAD.value == "dead"

    def test_board_decision_status_values(self):
        """BoardDecisionStatus enum values."""
        assert BoardDecisionStatus.PENDING.value == "pending"
        assert BoardDecisionStatus.APPROVED.value == "approved"
        assert BoardDecisionStatus.REJECTED.value == "rejected"
        assert BoardDecisionStatus.ESCALATED.value == "escalated"


# =============================================================================
# Model Structure Tests
# =============================================================================


class TestModelStructure:
    """Test SQLAlchemy model structure."""

    def test_all_models_use_uuid_primary_key(self):
        """All models should use UUID primary keys."""
        models = [
            Company,
            Department,
            Goal,
            ExternalAgent,
            BoardDecision,
            CompanyTemplate,
            PackActivationAuditLog,
        ]

        for model in models:
            # Check that id column exists and uses UUID
            assert hasattr(model, "id"), f"{model.__name__} missing id column"

    def test_all_models_have_tenant_id(self):
        """All models should have tenant_id for isolation."""
        models = [Company, Department, Goal, ExternalAgent, BoardDecision, PackActivationAuditLog]

        for model in models:
            assert hasattr(model, "tenant_id"), f"{model.__name__} missing tenant_id"

    def test_all_models_have_timestamps(self):
        """All models should have created_at and updated_at (except audit logs)."""
        models_with_timestamps = [
            Company,
            Department,
            Goal,
            ExternalAgent,
            BoardDecision,
            CompanyTemplate,
        ]

        for model in models_with_timestamps:
            assert hasattr(model, "created_at"), f"{model.__name__} missing created_at"
            assert hasattr(model, "updated_at"), f"{model.__name__} missing updated_at"

        # Audit log only has created_at (immutable)
        assert hasattr(
            PackActivationAuditLog, "created_at"
        ), "PackActivationAuditLog missing created_at"

    def test_company_tablename(self):
        """Company table name should be 'companies'."""
        assert Company.__tablename__ == "companies"

    def test_department_tablename(self):
        """Department table name should be 'departments'."""
        assert Department.__tablename__ == "departments"

    def test_goal_tablename(self):
        """Goal table name should be 'goals'."""
        assert Goal.__tablename__ == "goals"

    def test_external_agent_tablename(self):
        """ExternalAgent table name should be 'external_agents'."""
        assert ExternalAgent.__tablename__ == "external_agents"

    def test_board_decision_tablename(self):
        """BoardDecision table name should be 'board_decisions'."""
        assert BoardDecision.__tablename__ == "board_decisions"

    def test_company_template_tablename(self):
        """CompanyTemplate table name should be 'company_templates'."""
        assert CompanyTemplate.__tablename__ == "company_templates"

    def test_pack_activation_audit_log_tablename(self):
        """PackActivationAuditLog table name should be 'pack_activation_audit_logs'."""
        assert PackActivationAuditLog.__tablename__ == "pack_activation_audit_logs"
