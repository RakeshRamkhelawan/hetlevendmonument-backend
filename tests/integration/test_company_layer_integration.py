"""Company Layer Integration Tests - Fase 1 Data Foundation

Integration tests for Company Layer with REAL database backend.
Tests database models, migrations, context objects, and schemas end-to-end.

Environment: PostgreSQL 15+ (Docker)
Execution: pytest tests/integration/test_company_layer_integration.py -v -m integration

SKIPPED: Duplicate of test_company_layer_isolated.py which passes all tests.
Re-enable when fixture conflicts are resolved (tenant_id missing on Company model).
"""

import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import pytest

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Mark all tests as integration tests. De `skip` stond hier eerder als een TWEEDE, losse
# `pytestmark =`-toekenning -- die overschrijft de eerste volledig i.p.v. hem aan te vullen,
# waardoor de skip nooit werkte en dit bestand (met een BEKEND fixture-conflict, zie de
# moduledocstring) gewoon meedraaide onder `-m integration`.
pytestmark = [
    pytest.mark.skip(
        reason="Duplicate of test_company_layer_isolated.py. "
        "Fixture conflict: Company model requires tenant_id not provided by fixtures."
    ),
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


# ============================================================================
# FIXTURE: PostgreSQL Database Session


@pytest_asyncio.fixture(scope="function", autouse=True)
async def ensure_tables(postgres_engine):
    """Recreate all tables before each test function.

    NOTE: Function-scoped to match postgres_engine scope for pytest-asyncio 0.24+.
    """
    from src.core.database.database import Base

    async with postgres_engine.begin() as conn:
        # Create pgvector extension first (required for vector embeddings)
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.run_sync(Base.metadata.create_all)
    # Transaction committed; tables are visible to other connections
    yield


# ============================================================================


@pytest.fixture(scope="session")
def postgres_url() -> str:
    """Get PostgreSQL connection URL from environment or default."""
    from tests.integration.conftest import TEST_DB_URL

    return TEST_DB_URL


@pytest_asyncio.fixture(scope="function")
async def postgres_engine(postgres_url: str):
    """Create PostgreSQL engine for integration tests.

    NOTE: Function-scoped to avoid ScopeMismatch with pytest-asyncio 0.24+
    auto mode which uses function-scoped event loop runners.
    """
    engine = create_async_engine(
        postgres_url,
        echo=False,
        poolclass=NullPool,
    )

    # Verify connection
    async with engine.connect() as conn:
        result = await conn.execute(select(1))
        assert result.scalar() == 1

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def postgres_session(postgres_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create fresh session with transaction rollback for isolation."""
    session_factory = async_sessionmaker(
        postgres_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session
        # Rollback all changes after test
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def test_tenant_id(postgres_session: AsyncSession) -> int:
    """Create a test tenant and return its ID."""
    from src.core.models.rbac_models import Tenant

    tenant = Tenant(
        name=f"test_tenant_{uuid.uuid4().hex[:8]}",
        domain=f"test-{uuid.uuid4().hex[:8]}.example.com",
    )
    postgres_session.add(tenant)
    await postgres_session.commit()
    await postgres_session.refresh(tenant)
    return tenant.id


# ============================================================================
# TEST SUITE: Database Models Integration
# ============================================================================


class TestCompanyModelIntegration:
    """Integration tests for Company model with real PostgreSQL."""

    async def test_create_company_real_database(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Create company in real PostgreSQL database."""
        from src.core.company.models import Company

        company = Company(
            tenant_id=test_tenant_id,
            name="Integration Test Corp",
            company_type="mkb",
            sector="technology",
            mission="Test mission",
            config={"key": "value"},
        )

        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        # Verify company was created
        assert company.id is not None
        assert company.name == "Integration Test Corp"
        assert company.company_type == "mkb"
        assert company.config == {"key": "value"}
        assert company.created_at is not None

        # Verify we can query it back
        result = await postgres_session.execute(select(Company).where(Company.id == company.id))
        fetched = result.scalar_one()
        assert fetched.name == "Integration Test Corp"

    async def test_company_tenant_isolation(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Verify companies are isolated by tenant."""
        from src.core.company.models import Company

        # Create company for test tenant
        company = Company(
            tenant_id=test_tenant_id,
            name="Tenant Company",
            company_type="enterprise",
            sector="finance",
        )
        postgres_session.add(company)
        await postgres_session.commit()

        # Query by tenant should find it
        result = await postgres_session.execute(
            select(Company).where(Company.tenant_id == test_tenant_id)
        )
        companies = result.scalars().all()
        assert len(companies) == 1
        assert companies[0].name == "Tenant Company"


class TestDepartmentModelIntegration:
    """Integration tests for Department model."""

    async def test_create_department_with_parent(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Create department hierarchy in real database."""
        from src.core.company.models import Company, Department

        # Create parent company
        company = Company(
            tenant_id=test_tenant_id,
            name="Parent Company",
            company_type="enterprise",
            sector="technology",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        # Create parent department
        parent = Department(
            tenant_id=test_tenant_id,
            company_id=company.id,
            name="Engineering",
            board_role="CTO",
            budget_monthly_tokens=100000,
        )
        postgres_session.add(parent)
        await postgres_session.commit()
        await postgres_session.refresh(parent)

        # Create child department
        child = Department(
            tenant_id=test_tenant_id,
            company_id=company.id,
            name="Backend Team",
            parent_department_id=parent.id,
            budget_monthly_tokens=50000,
        )
        postgres_session.add(child)
        await postgres_session.commit()

        # Verify hierarchy
        assert child.parent_department_id == parent.id
        assert child.company_id == company.id

    async def test_department_version_optimistic_locking(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Verify version field for optimistic locking."""
        from src.core.company.models import Company, Department

        company = Company(
            tenant_id=test_tenant_id,
            name="Version Test Company",
            company_type="mkb",
            sector="healthcare",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        dept = Department(
            tenant_id=test_tenant_id,
            company_id=company.id,
            name="Test Dept",
            version=1,
        )
        postgres_session.add(dept)
        await postgres_session.commit()
        await postgres_session.refresh(dept)

        assert dept.version == 1


class TestGoalModelIntegration:
    """Integration tests for Goal model hierarchy."""

    async def test_create_goal_hierarchy(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Create mission → strategic → project → task chain."""
        from src.core.company.models import Company, Goal

        # Create company
        company = Company(
            tenant_id=test_tenant_id,
            name="Goal Test Company",
            company_type="mkb",
            sector="technology",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        # Create mission
        mission = Goal(
            tenant_id=test_tenant_id,
            company_id=company.id,
            goal_type="mission",
            title="Company Mission",
            description="Our mission",
            status="active",
            progress_pct=100,
        )
        postgres_session.add(mission)
        await postgres_session.commit()
        await postgres_session.refresh(mission)

        # Create strategic goal
        strategic = Goal(
            tenant_id=test_tenant_id,
            company_id=company.id,
            parent_goal_id=mission.id,
            goal_type="strategic",
            title="Strategic Goal 2026",
            status="active",
            progress_pct=50,
        )
        postgres_session.add(strategic)
        await postgres_session.commit()

        # Verify hierarchy
        assert strategic.parent_goal_id == mission.id
        assert strategic.goal_type == "strategic"

    async def test_goal_progress_validation(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Verify goal progress is stored correctly."""
        from src.core.company.models import Company, Goal

        company = Company(
            tenant_id=test_tenant_id,
            name="Progress Test",
            company_type="mkb",
            sector="tech",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        goal = Goal(
            tenant_id=test_tenant_id,
            company_id=company.id,
            goal_type="task",
            title="Task",
            status="in_progress",
            progress_pct=75,
        )
        postgres_session.add(goal)
        await postgres_session.commit()
        await postgres_session.refresh(goal)

        assert goal.progress_pct == 75


class TestExternalAgentIntegration:
    """Integration tests for ExternalAgent model."""

    async def test_register_external_agent(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Register external agent in database."""
        import hashlib

        from src.core.company.models import ExternalAgent

        agent = ExternalAgent(
            tenant_id=test_tenant_id,
            name="Test Agent",
            runtime="python-3.11",
            capabilities=["data-processing", "ml"],
            heartbeat_interval_seconds=30,
            status="registered",
            metrics={"tasks_completed": 0},
            api_key_hash=hashlib.sha256(b"test-api-key").hexdigest(),
        )

        postgres_session.add(agent)
        await postgres_session.commit()
        await postgres_session.refresh(agent)

        assert agent.id is not None
        assert agent.name == "Test Agent"
        assert agent.capabilities == ["data-processing", "ml"]
        assert agent.status == "registered"

    async def test_external_agent_heartbeat_tracking(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Track agent heartbeat timestamp."""
        from src.core.company.models import ExternalAgent

        now = datetime.now(timezone.utc)
        import hashlib

        agent = ExternalAgent(
            tenant_id=test_tenant_id,
            name="Heartbeat Agent",
            runtime="python-3.11",
            capabilities=["test"],
            status="active",
            last_heartbeat_at=now,
            api_key_hash=hashlib.sha256(b"heartbeat-api-key").hexdigest(),
        )

        postgres_session.add(agent)
        await postgres_session.commit()
        await postgres_session.refresh(agent)

        assert agent.last_heartbeat_at is not None


class TestBoardDecisionIntegration:
    """Integration tests for BoardDecision model."""

    async def test_create_board_decision(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Create board decision for approval."""
        from src.core.company.models import BoardDecision, Company

        company = Company(
            tenant_id=test_tenant_id,
            name="Board Test Company",
            company_type="enterprise",
            sector="finance",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        from src.core.models.rbac_models import User

        user = User(
            tenant_id=test_tenant_id,
            email="requester@example.com",
            hashed_password="hashed",
        )
        postgres_session.add(user)
        await postgres_session.commit()
        await postgres_session.refresh(user)

        decision = BoardDecision(
            tenant_id=test_tenant_id,
            company_id=company.id,
            requested_by=user.id,
            board_role="CTO",
            action_type="budget_increase",
            action_context={"amount": 50000, "reason": "Expansion"},
            decision=None,  # Pending
        )

        postgres_session.add(decision)
        await postgres_session.commit()
        await postgres_session.refresh(decision)

        assert decision.id is not None
        assert decision.decision is None  # Still pending
        assert decision.board_role == "CTO"

    async def test_approve_board_decision(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Approve a pending board decision."""
        from src.core.company.models import BoardDecision, BoardDecisionStatus, Company
        from src.core.models.rbac_models import User

        # Setup
        company = Company(
            tenant_id=test_tenant_id,
            name="Approval Test",
            company_type="mkb",
            sector="tech",
        )
        postgres_session.add(company)

        requester = User(
            tenant_id=test_tenant_id,
            email="requester@example.com",
            hashed_password="hashed",
        )
        approver = User(
            tenant_id=test_tenant_id,
            email="approver@example.com",
            hashed_password="hashed",
        )
        postgres_session.add(requester)
        postgres_session.add(approver)
        await postgres_session.commit()
        await postgres_session.refresh(requester)
        await postgres_session.refresh(approver)

        # Create pending decision
        decision = BoardDecision(
            tenant_id=test_tenant_id,
            company_id=company.id,
            requested_by=requester.id,
            board_role="CTO",
            action_type="deploy_agent",
            action_context={"agent_name": "Test"},
            decision=BoardDecisionStatus.APPROVED,
            decided_by=approver.id,
            reason="Approved for production",
            decided_at=datetime.now(timezone.utc),
        )

        postgres_session.add(decision)
        await postgres_session.commit()

        assert decision.decision == BoardDecisionStatus.APPROVED
        assert decision.decided_by == approver.id


# ============================================================================
# TEST SUITE: Context Objects Integration
# ============================================================================


class TestAgentExecutionContextIntegration:
    """Integration tests for AgentExecutionContext with database."""

    async def test_context_with_real_company(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Create context with real company from database."""
        from src.core.company.context import AgentExecutionContext, GoalChain
        from src.core.company.models import Company

        # Create company in DB
        company = Company(
            tenant_id=test_tenant_id,
            name="Context Test Company",
            company_type="mkb",
            sector="technology",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        # Create context using real company ID
        context = AgentExecutionContext(
            tenant_id=test_tenant_id,
            company_id=company.id,
            company_type=company.company_type,
            sector=company.sector,
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            goal_chain=GoalChain(
                mission_id=uuid.uuid4(),
                task_goal_id=uuid.uuid4(),
            ),
        )

        # Validate
        is_valid, missing = context.validate_completeness()
        assert is_valid is True
        assert missing == []
        assert context.is_degraded is False

    async def test_context_degraded_mode(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Context without company goes into degraded mode."""
        from src.core.company.context import AgentExecutionContext, GoalChain

        context = AgentExecutionContext(
            tenant_id=test_tenant_id,
            company_id=None,  # Missing
            task_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            goal_chain=GoalChain(),  # Empty
        )

        is_valid, missing = context.validate_completeness()
        assert is_valid is False
        assert "company_id" in missing
        assert "goal_chain" in missing
        assert context.is_degraded is True


# ============================================================================
# TEST SUITE: Schema Validation Integration
# ============================================================================


class TestSchemaDatabaseIntegration:
    """Integration tests for schemas with database models."""

    async def test_company_response_from_model(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Create CompanyResponse from database model."""
        from src.core.company.models import Company
        from src.core.company.schemas import CompanyResponse

        # Create model in DB
        company = Company(
            tenant_id=test_tenant_id,
            name="Schema Test",
            company_type="enterprise",
            sector="healthcare",
            mission="Test mission",
            status="active",
        )
        postgres_session.add(company)
        await postgres_session.commit()

        # Convert to response schema
        response = CompanyResponse.model_validate(company)

        assert response.name == "Schema Test"
        assert response.company_type == "enterprise"
        assert response.tenant_id == test_tenant_id

    async def test_goal_chain_from_ancestry_db(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Build GoalChain from database ancestry query."""
        from src.core.company.context import GoalChain
        from src.core.company.models import Company, Goal

        # Setup company and goals
        company = Company(
            tenant_id=test_tenant_id,
            name="Goal Chain Test",
            company_type="mkb",
            sector="tech",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        # Create goals
        mission = Goal(
            tenant_id=test_tenant_id,
            company_id=company.id,
            goal_type="mission",
            title="Mission",
            status="active",
        )
        postgres_session.add(mission)
        await postgres_session.commit()
        await postgres_session.refresh(mission)

        task = Goal(
            tenant_id=test_tenant_id,
            company_id=company.id,
            parent_goal_id=mission.id,
            goal_type="task",
            title="Task",
            status="in_progress",
        )
        postgres_session.add(task)
        await postgres_session.commit()

        # Query goals and build chain
        result = await postgres_session.execute(
            select(Goal).where(Goal.company_id == company.id).order_by(Goal.created_at)
        )
        goals = result.scalars().all()

        ancestry = [{"id": g.id, "title": g.title, "goal_type": g.goal_type} for g in goals]

        chain = GoalChain.from_ancestry(ancestry)

        assert chain.mission_id == mission.id
        assert chain.task_goal_id == task.id
        assert chain.is_complete() is True


# ============================================================================
# TEST SUITE: End-to-End Flow
# ============================================================================


class TestEndToEndCompanyFlow:
    """End-to-end tests simulating real API usage."""

    async def test_full_company_creation_flow(
        self,
        postgres_session: AsyncSession,
        test_tenant_id: int,
    ):
        """Complete flow: Create company → departments → goals."""
        from src.core.company.models import Company, Department, Goal
        from src.core.company.schemas import (
            CompanyCreate,
            CompanyResponse,
            DepartmentCreate,
            DepartmentResponse,
            GoalCreate,
            GoalResponse,
        )

        # Step 1: Create company from schema
        create_data = CompanyCreate(
            name="E2E Test Corp",
            company_type="enterprise",
            sector="technology",
            mission="End-to-end test",
        )

        company = Company(
            tenant_id=test_tenant_id,
            name=create_data.name,
            company_type=create_data.company_type,
            sector=create_data.sector,
            mission=create_data.mission,
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        # Verify response
        response = CompanyResponse.model_validate(company)
        assert response.name == "E2E Test Corp"

        # Step 2: Create department
        dept_create = DepartmentCreate(
            name="Engineering",
            board_role="CTO",
            budget_monthly_tokens=100000,
        )

        dept = Department(
            tenant_id=test_tenant_id,
            company_id=company.id,
            name=dept_create.name,
            board_role=dept_create.board_role,
            budget_monthly_tokens=dept_create.budget_monthly_tokens,
        )
        postgres_session.add(dept)
        await postgres_session.commit()

        dept_response = DepartmentResponse.model_validate(dept)
        assert dept_response.company_id == company.id

        # Step 3: Create goal
        goal_create = GoalCreate(
            goal_type="mission",
            title="Company Mission",
            description="Our mission",
        )

        goal = Goal(
            tenant_id=test_tenant_id,
            company_id=company.id,
            department_id=dept.id,
            goal_type=goal_create.goal_type,
            title=goal_create.title,
            description=goal_create.description,
            status="active",
            progress_pct=0,
        )
        postgres_session.add(goal)
        await postgres_session.commit()

        goal_response = GoalResponse.model_validate(goal)
        assert goal_response.company_id == company.id

        # Verify complete flow
        assert response.tenant_id == test_tenant_id
        assert dept_response.company_id == company.id
        assert goal_response.company_id == company.id
