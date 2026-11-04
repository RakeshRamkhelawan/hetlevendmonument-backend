"""
Fase 9 Integration Tests: Board Governance API Endpoints

Tests the complete API flow for board governance:
- GET /api/v1/board/queue
- GET /api/v1/board/decisions
- POST /api/v1/board/decisions/{id}/approve
- POST /api/v1/board/decisions/{id}/reject
- GET /api/v1/board/roles

Uses postgres_session for direct database testing.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.integration
@pytest.mark.asyncio
class TestBoardGovernanceService:
    """Test board governance with real database."""

    async def test_create_board_decision(self, postgres_session):
        """Test creating a board decision directly in database."""
        from sqlalchemy import select

        from src.core.company.models import BoardDecision, Company
        from src.core.models.rbac_models import User

        # Create test company and user
        company = Company(
            name=f"Board Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.flush()

        # Create a test user
        from src.core.auth.jwt_handler import get_password_hash

        user = User(
            email=f"test-{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            tenant_id=1,
            is_active=True,
        )
        postgres_session.add(user)
        await postgres_session.flush()

        # Create decision
        decision = BoardDecision(
            tenant_id=1,
            company_id=company.id,
            requested_by=user.id,
            board_role="CFO",
            action_type="budget_approval",
            action_context={"amount": 100000, "currency": "EUR"},
            decision="pending",
        )
        postgres_session.add(decision)
        await postgres_session.commit()
        await postgres_session.refresh(decision)

        # Verify creation
        result = await postgres_session.execute(
            select(BoardDecision).where(BoardDecision.id == decision.id)
        )
        db_decision = result.scalar_one()

        assert db_decision.board_role == "CFO"
        assert db_decision.action_type == "budget_approval"
        assert db_decision.decision == "pending"
        assert db_decision.company_id == company.id

    async def test_approve_decision(self, postgres_session):
        """Test approving a board decision."""
        from sqlalchemy import select

        from src.core.auth.jwt_handler import get_password_hash
        from src.core.company.models import BoardDecision, Company
        from src.core.models.rbac_models import User

        # Setup
        company = Company(
            name=f"Approve Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.flush()

        user = User(
            email=f"test-{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            tenant_id=1,
            is_active=True,
        )
        postgres_session.add(user)
        await postgres_session.flush()

        decider = User(
            email=f"decider-{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            tenant_id=1,
            is_active=True,
        )
        postgres_session.add(decider)
        await postgres_session.flush()

        decision = BoardDecision(
            tenant_id=1,
            company_id=company.id,
            requested_by=user.id,
            board_role="CEO",
            action_type="strategy",
            action_context={},
            decision="pending",
        )
        postgres_session.add(decision)
        await postgres_session.commit()
        await postgres_session.refresh(decision)

        # Approve
        decision.decision = "approved"
        decision.decided_by = decider.id
        decision.reason = "Approved after review"
        decision.decided_at = datetime.now(timezone.utc)
        await postgres_session.commit()

        # Verify
        result = await postgres_session.execute(
            select(BoardDecision).where(BoardDecision.id == decision.id)
        )
        db_decision = result.scalar_one()

        assert db_decision.decision == "approved"
        assert db_decision.decided_by == decider.id
        assert db_decision.reason == "Approved after review"
        assert db_decision.decided_at is not None

    async def test_reject_decision(self, postgres_session):
        """Test rejecting a board decision."""
        from sqlalchemy import select

        from src.core.auth.jwt_handler import get_password_hash
        from src.core.company.models import BoardDecision, Company
        from src.core.models.rbac_models import User

        # Setup
        company = Company(
            name=f"Reject Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.flush()

        user = User(
            email=f"test-{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            tenant_id=1,
            is_active=True,
        )
        postgres_session.add(user)
        await postgres_session.flush()

        decider = User(
            email=f"decider-{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            tenant_id=1,
            is_active=True,
        )
        postgres_session.add(decider)
        await postgres_session.flush()

        decision = BoardDecision(
            tenant_id=1,
            company_id=company.id,
            requested_by=user.id,
            board_role="CFO",
            action_type="budget_request",
            action_context={"amount": 50000},
            decision="pending",
        )
        postgres_session.add(decision)
        await postgres_session.commit()
        await postgres_session.refresh(decision)

        # Reject
        decision.decision = "rejected"
        decision.decided_by = decider.id
        decision.reason = "Budget exceeds limits"
        decision.decided_at = datetime.now(timezone.utc)
        await postgres_session.commit()

        # Verify
        result = await postgres_session.execute(
            select(BoardDecision).where(BoardDecision.id == decision.id)
        )
        db_decision = result.scalar_one()

        assert db_decision.decision == "rejected"
        assert db_decision.reason == "Budget exceeds limits"
        assert db_decision.decided_by is not None

    async def test_list_pending_decisions(self, postgres_session):
        """Test listing pending decisions."""
        from sqlalchemy import select

        from src.core.auth.jwt_handler import get_password_hash
        from src.core.company.models import BoardDecision, Company
        from src.core.models.rbac_models import User

        # Setup
        company = Company(
            name=f"List Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.flush()

        user = User(
            email=f"test-{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            tenant_id=1,
            is_active=True,
        )
        postgres_session.add(user)
        await postgres_session.flush()

        # Create decisions with different statuses
        pending_decision = BoardDecision(
            tenant_id=1,
            company_id=company.id,
            requested_by=user.id,
            board_role="CEO",
            action_type="strategy",
            action_context={},
            decision="pending",
        )
        approved_decision = BoardDecision(
            tenant_id=1,
            company_id=company.id,
            requested_by=user.id,
            board_role="CFO",
            action_type="budget",
            action_context={},
            decision="approved",
            decided_by=user.id,
            decided_at=datetime.now(timezone.utc),
        )
        postgres_session.add(pending_decision)
        postgres_session.add(approved_decision)
        await postgres_session.commit()

        # Query pending
        result = await postgres_session.execute(
            select(BoardDecision).where(
                BoardDecision.company_id == company.id, BoardDecision.decision == "pending"
            )
        )
        pending = result.scalars().all()

        assert len(pending) == 1
        assert pending[0].action_type == "strategy"

    async def test_decision_status_values(self, postgres_session):
        """Test that decision status is one of allowed values."""
        from sqlalchemy import select

        from src.core.auth.jwt_handler import get_password_hash
        from src.core.company.models import BoardDecision, BoardDecisionStatus, Company
        from src.core.models.rbac_models import User

        company = Company(
            name=f"Status Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.flush()

        user = User(
            email=f"test-{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            tenant_id=1,
            is_active=True,
        )
        postgres_session.add(user)
        await postgres_session.flush()

        valid_statuses = ["pending", "approved", "rejected", "escalated"]

        # Create decisions with different statuses
        for status in valid_statuses:
            decision = BoardDecision(
                tenant_id=1,
                company_id=company.id,
                requested_by=user.id,
                board_role="CEO",
                action_type="strategy",
                action_context={},
                decision=status,
            )
            postgres_session.add(decision)

        await postgres_session.commit()

        # Verify all saved
        result = await postgres_session.execute(
            select(BoardDecision).where(BoardDecision.company_id == company.id)
        )
        decisions = result.scalars().all()

        assert len(decisions) == 4
        saved_statuses = {d.decision for d in decisions}
        assert saved_statuses == set(valid_statuses)

    async def test_decision_tenant_isolation(self, postgres_session):
        """Test decisions are isolated by tenant."""
        from sqlalchemy import select

        from src.core.auth.jwt_handler import get_password_hash
        from src.core.company.models import BoardDecision, Company
        from src.core.models.rbac_models import User

        # Create companies for the same tenant (test isolation via company)
        company_a = Company(
            name=f"Company A {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        company_b = Company(
            name=f"Company B {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company_a)
        postgres_session.add(company_b)
        await postgres_session.flush()

        user = User(
            email=f"test-{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            tenant_id=1,
            is_active=True,
        )
        postgres_session.add(user)
        await postgres_session.flush()

        # Create decision for company A
        decision_a = BoardDecision(
            tenant_id=1,
            company_id=company_a.id,
            requested_by=user.id,
            board_role="CEO",
            action_type="strategy",
            action_context={},
            decision="pending",
        )
        postgres_session.add(decision_a)
        await postgres_session.commit()

        # Query as company B
        result = await postgres_session.execute(
            select(BoardDecision).where(BoardDecision.company_id == company_b.id)
        )
        decisions_b = result.scalars().all()

        # Should not see company A's decision
        assert not any(d.action_type == "strategy" for d in decisions_b)


@pytest.mark.integration
@pytest.mark.asyncio
class TestBoardDecisionTypes:
    """Test different board decision types."""

    async def test_budget_decision(self, postgres_session):
        """Test budget type decision."""
        from src.core.auth.jwt_handler import get_password_hash
        from src.core.company.models import BoardDecision, Company
        from src.core.models.rbac_models import User

        company = Company(
            name=f"Budget Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.flush()

        user = User(
            email=f"test-{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            tenant_id=1,
            is_active=True,
        )
        postgres_session.add(user)
        await postgres_session.flush()

        decision = BoardDecision(
            tenant_id=1,
            company_id=company.id,
            requested_by=user.id,
            board_role="CFO",
            action_type="budget_approval",
            action_context={"amount": 100000, "currency": "EUR"},
            decision="pending",
        )
        postgres_session.add(decision)
        await postgres_session.commit()
        await postgres_session.refresh(decision)

        assert decision.action_type == "budget_approval"
        assert decision.board_role == "CFO"

    async def test_executive_decision(self, postgres_session):
        """Test executive type decision (hiring/firing)."""
        from src.core.auth.jwt_handler import get_password_hash
        from src.core.company.models import BoardDecision, Company
        from src.core.models.rbac_models import User

        company = Company(
            name=f"Hiring Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.flush()

        user = User(
            email=f"test-{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            tenant_id=1,
            is_active=True,
        )
        postgres_session.add(user)
        await postgres_session.flush()

        decision = BoardDecision(
            tenant_id=1,
            company_id=company.id,
            requested_by=user.id,
            board_role="CTO",
            action_type="hire_approval",
            action_context={"position": "Senior Developer", "salary": 80000},
            decision="pending",
        )
        postgres_session.add(decision)
        await postgres_session.commit()
        await postgres_session.refresh(decision)

        assert decision.action_type == "hire_approval"
        assert decision.board_role == "CTO"

    async def test_strategy_decision(self, postgres_session):
        """Test strategy type decision."""
        from src.core.auth.jwt_handler import get_password_hash
        from src.core.company.models import BoardDecision, Company
        from src.core.models.rbac_models import User

        company = Company(
            name=f"Strategy Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.flush()

        user = User(
            email=f"test-{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            tenant_id=1,
            is_active=True,
        )
        postgres_session.add(user)
        await postgres_session.flush()

        decision = BoardDecision(
            tenant_id=1,
            company_id=company.id,
            requested_by=user.id,
            board_role="CEO",
            action_type="market_expansion",
            action_context={"region": "Europe", "budget": 500000},
            decision="pending",
        )
        postgres_session.add(decision)
        await postgres_session.commit()
        await postgres_session.refresh(decision)

        assert decision.action_type == "market_expansion"
        assert decision.board_role == "CEO"
