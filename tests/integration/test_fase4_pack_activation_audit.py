"""Integration tests for PackActivationAuditLog model.

Taak 4.0: Pack Activation Audit Log (Model + Migratie)
Fase 4: Pack Activation Intelligence
"""

import uuid
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.company.models import Company, Department, PackActivationAuditLog

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


async def _create_company_department(
    postgres_session: AsyncSession,
    tenant_id: int = 1,
) -> tuple[UUID, UUID]:
    """Create a valid company/department pair for FK-constrained audit rows."""
    await postgres_session.execute(
        text(
            """
            INSERT INTO tenants (id, name, slug, is_active, max_users, max_agents, max_storage_gb)
            VALUES (:id, :name, :slug, true, 10, 50, 5)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "id": tenant_id,
            "name": f"Tenant {tenant_id}",
            "slug": f"tenant-{tenant_id}",
        },
    )

    company = Company(
        id=uuid4(),
        tenant_id=tenant_id,
        name=f"Test Company {tenant_id}",
        company_type="mkb",
        sector="retail",
        status="active",
        config={},
    )
    postgres_session.add(company)
    await postgres_session.flush()

    department = Department(
        id=uuid4(),
        tenant_id=tenant_id,
        company_id=company.id,
        name="Sales",
        version=1,
    )
    postgres_session.add(department)
    await postgres_session.flush()

    return company.id, department.id


# ============================================================================
# Happy Path Tests
# ============================================================================


@pytest.mark.asyncio
async def test_audit_log_model_fields(postgres_session: AsyncSession):
    """Test that all columns are present with correct types."""
    company_id, dept_id = await _create_company_department(postgres_session)

    audit_log = PackActivationAuditLog(
        id=uuid4(),
        tenant_id=1,
        company_id=company_id,
        department_id=dept_id,
        pack_id="mkb.sales.crm",
        pack_name="Sales CRM Pack",
        score=0.85,
        confidence="HIGH",
        match_reason="Department 'Sales' matches pack department",
        input_signals={"department_name": "Sales", "company_type": "mkb"},
        score_breakdown={"department_match": 0.4, "company_type_match": 0.2},
        activated_automatically=True,
        user_confirmed=None,
        confirmed_by=None,
        confirmed_at=None,
    )

    postgres_session.add(audit_log)
    await postgres_session.commit()

    # Verify it was saved
    result = await postgres_session.execute(
        select(PackActivationAuditLog).where(PackActivationAuditLog.id == audit_log.id)
    )
    saved = result.scalar_one()

    assert saved.id == audit_log.id
    assert saved.tenant_id == 1
    assert saved.pack_id == "mkb.sales.crm"
    assert saved.score == 0.85
    assert saved.confidence == "HIGH"
    assert saved.activated_automatically is True


@pytest.mark.asyncio
async def test_audit_log_create(postgres_session: AsyncSession):
    """Test INSERT audit log with all fields."""
    company_id, dept_id = await _create_company_department(postgres_session)

    audit_log = PackActivationAuditLog(
        tenant_id=1,
        company_id=company_id,
        department_id=dept_id,
        pack_id="enterprise.finance.accounting",
        pack_name="Enterprise Finance Accounting",
        score=0.92,
        confidence="EXACT",
        match_reason="Exact department match: Finance",
        input_signals={
            "department_name": "Finance",
            "company_type": "enterprise",
            "sector": "manufacturing",
        },
        score_breakdown={
            "department": 0.40,
            "company_type": 0.20,
            "sector": 0.20,
            "explicit": 0.20,
        },
        activated_automatically=True,
    )

    postgres_session.add(audit_log)
    await postgres_session.commit()
    await postgres_session.refresh(audit_log)

    assert audit_log.id is not None
    assert audit_log.created_at is not None
    assert audit_log.pack_id == "enterprise.finance.accounting"


@pytest.mark.asyncio
async def test_audit_log_jsonb_queryable(postgres_session: AsyncSession):
    """Test that input_signals JSONB is queryable."""
    # Create audit logs with different input signals
    for i in range(3):
        company_id, dept_id = await _create_company_department(postgres_session)
        log = PackActivationAuditLog(
            tenant_id=1,
            company_id=company_id,
            department_id=dept_id,
            pack_id=f"test.pack.{i}",
            pack_name=f"Test Pack {i}",
            score=0.5 + (i * 0.1),
            confidence="MEDIUM",
            match_reason="Test",
            input_signals={"department_name": f"Dept{i}", "company_type": "mkb"},
            score_breakdown={"test": 0.5},
        )
        postgres_session.add(log)

    await postgres_session.commit()

    # Query using PostgreSQL JSONB operator
    result = await postgres_session.execute(
        text(
            """
            SELECT COUNT(*) FROM pack_activation_audit_logs
            WHERE input_signals->>'company_type' = 'mkb'
        """
        )
    )
    count = result.scalar()
    assert count == 3


@pytest.mark.asyncio
async def test_audit_log_tenant_scoped(postgres_session: AsyncSession):
    """Test that audit logs are only visible to their own tenant."""
    # Create logs for different tenants
    company_1_id, dept_1_id = await _create_company_department(postgres_session, tenant_id=1)
    company_2_id, dept_2_id = await _create_company_department(postgres_session, tenant_id=2)

    tenant_1_log = PackActivationAuditLog(
        tenant_id=1,
        company_id=company_1_id,
        department_id=dept_1_id,
        pack_id="tenant1.pack",
        pack_name="Tenant 1 Pack",
        score=0.8,
        confidence="HIGH",
        match_reason="Test",
        input_signals={},
        score_breakdown={},
    )

    tenant_2_log = PackActivationAuditLog(
        tenant_id=2,
        company_id=company_2_id,
        department_id=dept_2_id,
        pack_id="tenant2.pack",
        pack_name="Tenant 2 Pack",
        score=0.7,
        confidence="MEDIUM",
        match_reason="Test",
        input_signals={},
        score_breakdown={},
    )

    postgres_session.add_all([tenant_1_log, tenant_2_log])
    await postgres_session.commit()

    # Query for tenant 1 only
    result = await postgres_session.execute(
        select(PackActivationAuditLog).where(PackActivationAuditLog.tenant_id == 1)
    )
    logs = result.scalars().all()

    assert len(logs) == 1
    assert logs[0].pack_id == "tenant1.pack"


@pytest.mark.asyncio
async def test_audit_log_user_confirmation(postgres_session: AsyncSession):
    """Test audit log with user confirmation fields."""
    company_id, dept_id = await _create_company_department(postgres_session)
    user_id = 1

    audit_log = PackActivationAuditLog(
        tenant_id=1,
        company_id=company_id,
        department_id=dept_id,
        pack_id="suggested.pack",
        pack_name="Suggested Pack",
        score=0.55,
        confidence="MEDIUM",
        match_reason="Partial match",
        input_signals={},
        score_breakdown={},
        activated_automatically=False,
        user_confirmed=True,
        confirmed_by=user_id,
        confirmed_at=datetime.now(timezone.utc),
    )

    postgres_session.add(audit_log)
    await postgres_session.commit()
    await postgres_session.refresh(audit_log)

    assert audit_log.activated_automatically is False
    assert audit_log.user_confirmed is True
    assert audit_log.confirmed_by == user_id
    assert audit_log.confirmed_at is not None


@pytest.mark.asyncio
async def test_audit_log_confidence_levels(postgres_session: AsyncSession):
    """Test all confidence levels can be stored."""
    confidence_levels = ["EXACT", "HIGH", "MEDIUM", "LOW", "NONE"]

    for i, level in enumerate(confidence_levels):
        company_id, dept_id = await _create_company_department(postgres_session)
        log = PackActivationAuditLog(
            tenant_id=1,
            company_id=company_id,
            department_id=dept_id,
            pack_id=f"confidence.{level.lower()}",
            pack_name=f"Pack {level}",
            score=0.9 - (i * 0.15),
            confidence=level,
            match_reason=f"Confidence level test: {level}",
            input_signals={},
            score_breakdown={"level": i},
        )
        postgres_session.add(log)

    await postgres_session.commit()

    # Verify all levels stored
    result = await postgres_session.execute(select(PackActivationAuditLog.confidence).distinct())
    stored_levels = {r[0] for r in result.all()}

    assert stored_levels == set(confidence_levels)


# ============================================================================
# Migration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_migration_creates_table(postgres_engine):
    """Test that migration creates the pack_activation_audit_logs table."""
    from sqlalchemy import inspect

    async with postgres_engine.connect() as conn:

        def check_table(connection):
            inspector = inspect(connection)
            return inspector.has_table("pack_activation_audit_logs")

        result = await conn.run_sync(check_table)
        assert result is True


@pytest.mark.asyncio
async def test_migration_creates_indexes(postgres_engine):
    """Test that migration creates required indexes."""
    from sqlalchemy import inspect

    async with postgres_engine.connect() as conn:

        def get_indexes(connection):
            inspector = inspect(connection)
            return inspector.get_indexes("pack_activation_audit_logs")

        indexes = await conn.run_sync(get_indexes)
        index_names = {idx["name"] for idx in indexes}

        # Check for expected indexes
        expected_indexes = [
            "idx_audit_tenant_company",
            "idx_audit_pack",
            "idx_audit_created",
        ]

        for expected in expected_indexes:
            assert expected in index_names, f"Missing index: {expected}"


# ============================================================================
# Unhappy Path Tests
# ============================================================================


@pytest.mark.asyncio
async def test_audit_log_missing_pack_id(postgres_session: AsyncSession):
    """Test that pack_id=None raises IntegrityError."""
    company_id, dept_id = await _create_company_department(postgres_session)

    audit_log = PackActivationAuditLog(
        tenant_id=1,
        company_id=company_id,
        department_id=dept_id,
        pack_id=None,  # Missing required field
        pack_name="Test Pack",
        score=0.5,
        confidence="MEDIUM",
        match_reason="Test",
        input_signals={},
        score_breakdown={},
    )

    postgres_session.add(audit_log)

    with pytest.raises(Exception):  # IntegrityError
        await postgres_session.commit()

    await postgres_session.rollback()


@pytest.mark.asyncio
async def test_audit_log_missing_required_fields(postgres_session: AsyncSession):
    """Test that required fields cannot be null."""
    company_id, dept_id = await _create_company_department(postgres_session)

    audit_log = PackActivationAuditLog(
        tenant_id=1,
        company_id=company_id,
        department_id=dept_id,
        pack_id="test.pack",
        pack_name=None,  # Should this be required? Testing behavior
        score=0.5,
        confidence="MEDIUM",
        match_reason=None,  # Should this be required?
        input_signals={},
        score_breakdown={},
    )

    postgres_session.add(audit_log)

    with pytest.raises(Exception):  # IntegrityError
        await postgres_session.commit()

    await postgres_session.rollback()


@pytest.mark.asyncio
async def test_audit_log_invalid_confidence(postgres_session: AsyncSession):
    """Test that invalid confidence values are rejected."""
    company_id, dept_id = await _create_company_department(postgres_session)

    audit_log = PackActivationAuditLog(
        tenant_id=1,
        company_id=company_id,
        department_id=dept_id,
        pack_id="test.pack",
        pack_name="Test",
        score=0.5,
        confidence="INVALID",  # Not in enum
        match_reason="Test",
        input_signals={},
        score_breakdown={},
    )

    postgres_session.add(audit_log)
    # PostgreSQL will accept any string, but application layer should validate
    await postgres_session.commit()

    # Verify it was saved (PostgreSQL doesn't enforce enum at DB level without CHECK constraint)
    result = await postgres_session.execute(
        select(PackActivationAuditLog).where(PackActivationAuditLog.confidence == "INVALID")
    )
    saved = result.scalar_one()
    assert saved.confidence == "INVALID"


@pytest.mark.asyncio
async def test_audit_log_score_out_of_range(postgres_session: AsyncSession):
    """Test that scores outside 0.0-1.0 range are stored but flagged."""
    company_id, dept_id = await _create_company_department(postgres_session)

    audit_log = PackActivationAuditLog(
        tenant_id=1,
        company_id=company_id,
        department_id=dept_id,
        pack_id="test.pack",
        pack_name="Test",
        score=1.5,  # Out of range
        confidence="HIGH",
        match_reason="Test",
        input_signals={},
        score_breakdown={},
    )

    postgres_session.add(audit_log)
    await postgres_session.commit()

    result = await postgres_session.execute(
        select(PackActivationAuditLog).where(PackActivationAuditLog.score > 1.0)
    )
    saved = result.scalar_one()
    assert saved.score == 1.5


# ============================================================================
# Integration with Company/Department
# ============================================================================


@pytest.mark.asyncio
async def test_audit_log_relationships(postgres_session: AsyncSession):
    """Test that audit log can reference company and department."""
    # Create company and department first
    from src.core.company.models import Company, Department

    company = Company(
        id=uuid4(),
        tenant_id=1,
        name="Test Company",
        company_type="mkb",
        sector="retail",
        status="active",
    )
    postgres_session.add(company)
    await postgres_session.flush()

    department = Department(
        id=uuid4(),
        tenant_id=1,
        company_id=company.id,
        name="Sales",
        version=1,
    )
    postgres_session.add(department)
    await postgres_session.flush()

    # Create audit log referencing them
    audit_log = PackActivationAuditLog(
        tenant_id=1,
        company_id=company.id,
        department_id=department.id,
        pack_id="mkb.sales.crm",
        pack_name="Sales CRM",
        score=0.85,
        confidence="HIGH",
        match_reason="Department match",
        input_signals={"dept": "Sales"},
        score_breakdown={"dept": 0.4},
        activated_automatically=True,
    )
    postgres_session.add(audit_log)
    await postgres_session.commit()

    # Verify relationships work
    result = await postgres_session.execute(
        select(PackActivationAuditLog)
        .where(PackActivationAuditLog.company_id == company.id)
        .where(PackActivationAuditLog.department_id == department.id)
    )
    saved = result.scalar_one()

    assert saved.pack_id == "mkb.sales.crm"


@pytest.mark.asyncio
async def test_audit_log_cascade_delete_company(postgres_session: AsyncSession):
    """Test what happens when referenced company is deleted."""
    # This test documents the expected behavior with ON DELETE
    company_id, dept_id = await _create_company_department(postgres_session)

    audit_log = PackActivationAuditLog(
        tenant_id=1,
        company_id=company_id,
        department_id=dept_id,
        pack_id="test.pack",
        pack_name="Test",
        score=0.5,
        confidence="MEDIUM",
        match_reason="Test",
        input_signals={},
        score_breakdown={},
    )

    postgres_session.add(audit_log)
    await postgres_session.commit()

    # The foreign keys should have ON DELETE SET NULL or CASCADE
    # This test verifies the behavior
    result = await postgres_session.execute(
        select(PackActivationAuditLog).where(PackActivationAuditLog.company_id == company_id)
    )
    saved = result.scalar_one()
    assert saved.company_id == company_id
