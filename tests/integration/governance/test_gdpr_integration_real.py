r"""
GDPR Integration Tests - Real Backend (No Mocks).

These tests run against the actual backend services with a real PostgreSQL database.
They test complete user workflows from API to database.

Requirements:
- PostgreSQL test database running (port 5455)
- All migrations applied
- Real services instantiated (no mocks)

Usage:
    # Setup test database
    # .\scripts\setup_gdpr_test_db.ps1

    # Run all integration tests
    pytest tests/integration/governance/test_gdpr_integration_real.py -v
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Dict

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.core.database.connection import get_sync_db
from src.core.governance.ai_transparency_service import AITransparencyService, ProfilingType
from src.core.governance.cookie_consent import CookieConsentManager, UserConsentRecord
from src.core.governance.dsar_service import DSARService
from src.core.governance.lawful_basis_registry import LawfulBasis, LawfulBasisRegistry
from src.core.governance.retention_cleanup import (
    DataCategory,
    RetentionCleanupService,
    RetentionJurisdiction,
)
from src.main import create_app

# De testdatabase komt uit de expliciete opgave (ADR-036 OP-243). Hier stond tot
# 2026-09-15 een HARDGECODEERDE URL naar poort 5435 -- zonder omgevingsvariabele en zonder
# terugval, dus met geen enkele instelling te sturen. Deze test praatte daarmee altijd met
# wat er toevallig op 5435 luisterde; op 2026-09-14 was dat zes uur lang een vergeten
# `act`-servicecontainer. Dat is de ernstigste variant van OP-243, want deze test gaat over
# persoonsgegevens.
from tests.fixtures.testdatabase import testdatabase_url  # noqa: E402

TEST_DATABASE_URL = testdatabase_url()


# Skip all tests if database is not available
def _check_db_available():
    """Check if test database is available."""
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        engine = create_async_engine(TEST_DATABASE_URL, echo=False, future=True)
        loop.run_until_complete(engine.connect())
        loop.run_until_complete(engine.dispose())
        return True
    except Exception:
        return False
    finally:
        loop.close()


if not _check_db_available():
    pytest.skip("Test database not available on port 5455", allow_module_level=True)

# Skip entire module: incompatible test infrastructure (custom event_loop fixture,
# deprecated pytest-asyncio v0.21 pattern, governance tables not in shared schema)
pytestmark = pytest.mark.skip(
    reason="Incompatible test infrastructure: custom event_loop fixture (deprecated), "
    "governance tables not in shared test schema. "
    "Tests service-layer code already covered by passing phase6 tests."
)


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
    )
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async_session = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session
        # Rollback after test
        await session.rollback()


@pytest.fixture
async def test_user(db_session) -> AsyncGenerator[int, None]:
    """Create a test user in the database."""
    user_id = 999001
    await db_session.execute(
        text(
            f"""
        INSERT INTO users (id, tenant_id, email, hashed_password, is_active, created_at, updated_at)
        VALUES ({user_id}, 1, 'test-user-{user_id}@example.com', 'hashed_password_here', true, NOW(), NOW())
        ON CONFLICT (id) DO NOTHING
    """
        )
    )
    await db_session.commit()

    yield user_id

    # Cleanup - rollback first if transaction failed
    try:
        await db_session.rollback()
        await db_session.execute(text(f"DELETE FROM user_consents WHERE user_id = '{user_id}'"))
        await db_session.execute(
            text(f"DELETE FROM user_profiling_opt_outs WHERE user_id = '{user_id}'")
        )
        await db_session.execute(text(f"DELETE FROM ai_decisions WHERE user_id = '{user_id}'"))
        await db_session.execute(text(f"DELETE FROM dsar_requests WHERE user_id = '{user_id}'"))
    except Exception:
        await db_session.rollback()
    try:
        await db_session.execute(text(f"DELETE FROM users WHERE id = {user_id}"))
        await db_session.commit()
    except Exception:
        await db_session.rollback()


@pytest.fixture
async def test_user_2(db_session) -> AsyncGenerator[int, None]:
    """Create a second test user for cross-user tests."""
    user_id = 999002
    await db_session.execute(
        text(
            f"""
        INSERT INTO users (id, tenant_id, email, hashed_password, is_active, created_at, updated_at)
        VALUES ({user_id}, 1, 'test-user-{user_id}@example.com', 'hashed_password_here', true, NOW(), NOW())
        ON CONFLICT (id) DO NOTHING
    """
        )
    )
    await db_session.commit()

    yield user_id

    # Cleanup - rollback first if transaction failed
    try:
        await db_session.rollback()
        await db_session.execute(text(f"DELETE FROM user_consents WHERE user_id = '{user_id}'"))
        await db_session.execute(
            text(f"DELETE FROM user_profiling_opt_outs WHERE user_id = '{user_id}'")
        )
        await db_session.execute(text(f"DELETE FROM ai_decisions WHERE user_id = '{user_id}'"))
        await db_session.execute(text(f"DELETE FROM dsar_requests WHERE user_id = '{user_id}'"))
    except Exception:
        await db_session.rollback()
    try:
        await db_session.execute(text(f"DELETE FROM users WHERE id = {user_id}"))
        await db_session.commit()
    except Exception:
        await db_session.rollback()


# =============================================================================
# PHASE 1: LAWFUL BASIS REGISTRY INTEGRATION TESTS
# =============================================================================


class TestLawfulBasisIntegration:
    """Integration tests for GDPR Lawful Basis Registry with real database."""

    @pytest.mark.asyncio
    async def test_register_endpoint_with_contract_basis(self, db_session):
        """Test: Register user registration endpoint with CONTRACT lawful basis."""
        registry = LawfulBasisRegistry()

        # Register endpoint for user registration (Art. 6(1)(b) - Contract)
        registry.register_endpoint(
            endpoint="/api/v1/users/register",
            lawful_basis=LawfulBasis.CONTRACT,
            data_categories=["personal", "contact", "authentication"],
            purpose="User account creation for service delivery",
        )

        # Verify registration
        result = await registry.validate_endpoint_access("/api/v1/users/register")

        assert result.is_valid is True
        assert result.lawful_basis == LawfulBasis.CONTRACT
        assert "personal" in result.data_categories
        assert result.purpose == "User account creation for service delivery"

        print(f"✅ Endpoint registered with lawful basis: {result.lawful_basis.value}")

    @pytest.mark.asyncio
    async def test_legitimate_interest_requires_lia(self, db_session):
        """Test: LEGITIMATE_INTEREST without LIA is rejected."""
        registry = LawfulBasisRegistry()

        # Attempt to register without LIA should fail
        with pytest.raises(ValueError) as exc_info:
            registry.register_endpoint(
                endpoint="/api/v1/analytics/track",
                lawful_basis=LawfulBasis.LEGITIMATE_INTEREST,
                data_categories=["usage", "behavioral"],
                purpose="User analytics",
                # Missing legitimate_interest_assessment
            )

        assert "LIA" in str(exc_info.value) or "legitimate interest" in str(exc_info.value).lower()
        print("✅ LIA validation working correctly")

    @pytest.mark.asyncio
    async def test_unregistered_endpoint_blocked(self, db_session):
        """Test: Access to unregistered endpoint is blocked."""
        from src.core.governance.lawful_basis_registry import LawfulBasisMissingError

        registry = LawfulBasisRegistry()

        with pytest.raises(LawfulBasisMissingError):
            await registry.validate_endpoint_access("/api/v1/unregistered/endpoint")

        print("✅ Unregistered endpoint correctly blocked")


# =============================================================================
# PHASE 2: DSAR INTEGRATION TESTS
# =============================================================================


class TestDSARIntegration:
    """Integration tests for DSAR (Data Subject Access Request) with real database."""

    @pytest.mark.asyncio
    async def test_user_can_export_own_data(self, db_session, test_user):
        """Test: User exports their own data (Art. 20)."""
        service = DSARService(db_session)

        # User exports their own data
        export = await service.export_user_data(
            user_id=str(test_user),
            tenant_id=1,
            requested_by_user_id=str(test_user),
        )

        assert export is not None

        print("✅ User data exported successfully")

    @pytest.mark.asyncio
    async def test_cross_user_access_denied(self, db_session, test_user, test_user_2):
        """Test: User cannot access another user's data."""
        from src.core.governance.dsar_service import DSARAuthorizationError

        service = DSARService(db_session)

        # User 1 tries to access user 2's data - should raise exception
        with pytest.raises(DSARAuthorizationError):
            await service.export_user_data(
                user_id=str(test_user_2),  # Target user
                tenant_id=1,
                requested_by_user_id=str(test_user),  # Different user
                is_admin=False,
            )

        print("✅ Cross-user access correctly denied")

    @pytest.mark.asyncio
    async def test_soft_delete_with_grace_period(self, db_session, test_user):
        """Test: User data soft delete with 30-day grace period."""
        service = DSARService(db_session)

        result = await service.delete_user_data(
            user_id=str(test_user),
            tenant_id=1,
            requested_by_user_id=str(test_user),
            hard_delete=False,  # Soft delete
        )

        assert result is not None
        assert result.delete_type == "soft"
        assert result.scheduled_purge_date is not None

        print("✅ Soft delete with grace period scheduled")


# =============================================================================
# PHASE 3: AI TRANSPARENCY INTEGRATION TESTS
# =============================================================================


class TestAITransparencyIntegration:
    """Integration tests for AI Transparency with real database."""

    @pytest.mark.asyncio
    async def test_log_ai_decision_with_explanation(self, db_session, test_user):
        """Test: AI decision logged with required explanation."""
        service = AITransparencyService(db_session)

        decision_id = await service.log_ai_decision(
            user_id=str(test_user),
            tenant_id=1,
            agent_id="loan-evaluator",
            decision_type="LOAN_APPROVAL",
            input_data={"amount": 5000, "term": 24},
            output_data={"approved": True, "rate": 0.05},
            confidence_score=0.88,
            explanation="Loan approved based on debt-to-income ratio of 25% and payment history. "
            "Your stable employment history supports this decision.",
        )

        assert decision_id is not None

        print(f"✅ AI decision {decision_id} logged with explanation")

    @pytest.mark.asyncio
    async def test_explanation_required_validation(self, db_session, test_user):
        """Test: AI decision without explanation is rejected."""
        from src.core.governance.ai_transparency_service import ExplanationRequiredError

        service = AITransparencyService(db_session)

        with pytest.raises(ExplanationRequiredError):
            await service.log_ai_decision(
                user_id=str(test_user),
                tenant_id=1,
                agent_id="test-agent",
                decision_type="TEST",
                input_data={},
                output_data={},
                confidence_score=0.5,
                explanation="",  # Empty - not allowed!
            )

        print("✅ Empty explanation correctly rejected")

    @pytest.mark.asyncio
    async def test_user_can_opt_out_of_profiling(self, db_session, test_user):
        """Test: User opts out of behavioral profiling (Art. 21)."""
        service = AITransparencyService(db_session)

        # User opts out
        await service.set_profiling_opt_out(
            user_id=str(test_user),
            tenant_id=1,
            profiling_type=ProfilingType.BEHAVIORAL,
            opt_out=True,
        )

        # Verify opt-out
        is_opted_out = await service.check_profiling_opt_out(
            user_id=str(test_user),
            tenant_id=1,
            profiling_type=ProfilingType.BEHAVIORAL,
        )

        assert is_opted_out is True

        print("✅ Profiling opt-out working correctly")


# =============================================================================
# PHASE 4: COOKIE CONSENT INTEGRATION TESTS
# =============================================================================


class TestCookieConsentIntegration:
    """Integration tests for Cookie Consent with real database."""

    @pytest.mark.asyncio
    async def test_user_accepts_all_cookies(self, db_session, test_user):
        """Test: User accepts all cookie categories."""
        manager = CookieConsentManager(db_session)

        result = await manager.update_consent(
            user_id=str(test_user),
            tenant_id=1,
            preferences={
                "essential": True,
                "analytics": True,
                "marketing": True,
                "personalization": True,
            },
            policy_version="1.0.0",
        )

        assert result.essential is True
        assert result.analytics is True
        assert result.marketing is True
        assert result.personalization is True

        print("✅ All cookies accepted and stored")

    @pytest.mark.asyncio
    async def test_user_customizes_preferences(self, db_session, test_user):
        """Test: User selectively enables only analytics."""
        manager = CookieConsentManager(db_session)

        result = await manager.update_consent(
            user_id=str(test_user),
            tenant_id=1,
            preferences={
                "essential": True,  # Always required
                "analytics": True,
                "marketing": False,
                "personalization": False,
            },
            policy_version="1.0.0",
        )

        assert result.analytics is True
        assert result.marketing is False
        assert result.personalization is False

        print("✅ Custom preferences saved")

    @pytest.mark.asyncio
    async def test_essential_cookies_always_enabled(self, db_session, test_user):
        """Test: Essential cookies cannot be disabled."""
        manager = CookieConsentManager(db_session)

        # Try to disable essential
        result = await manager.update_consent(
            user_id=str(test_user),
            tenant_id=1,
            preferences={
                "essential": False,  # System will force to True
                "analytics": False,
                "marketing": False,
                "personalization": False,
            },
            policy_version="1.0.0",
        )

        # Essential should still be True
        assert result.essential is True

        print("✅ Essential cookies enforced")

    @pytest.mark.asyncio
    async def test_user_can_view_current_consent(self, db_session, test_user):
        """Test: User views their current consent preferences."""
        manager = CookieConsentManager(db_session)

        # First set consent
        await manager.update_consent(
            user_id=str(test_user),
            tenant_id=1,
            preferences={
                "essential": True,
                "analytics": True,
                "marketing": False,
                "personalization": True,
            },
            policy_version="1.0.0",
        )

        # Then retrieve it
        consent = await manager.get_consent(user_id=str(test_user), tenant_id=1)

        assert consent.analytics is True
        assert consent.marketing is False
        assert consent.personalization is True
        assert consent.essential is True  # Always true

        print("✅ User consent retrieved successfully")


# =============================================================================
# PHASE 5: RETENTION CLEANUP INTEGRATION TESTS
# =============================================================================


class TestRetentionCleanupIntegration:
    """Integration tests for Retention Cleanup with real database."""

    @pytest.fixture
    async def old_audit_logs(self, db_session):
        """Create old audit logs for cleanup testing."""
        # Insert old audit logs (8 years old)
        old_date = datetime.now(timezone.utc) - timedelta(days=8 * 365)

        await db_session.execute(
            text(
                f"""
            INSERT INTO audit_logs (
                tenant_id, action, resource,
                details, timestamp, user_id, event_type, threat_level,
                client_ip, endpoint, description, event_metadata
            ) VALUES
            (1, 'test.action', 'test:old-1', '{{}}', '{old_date.isoformat()}', NULL, 'test', 'info', '127.0.0.1', '/test', 'Test', '{{}}'),
            (1, 'test.action', 'test:old-2', '{{}}', '{old_date.isoformat()}', NULL, 'test', 'info', '127.0.0.1', '/test', 'Test', '{{}}'),
            (1, 'test.action', 'test:old-3', '{{}}', '{old_date.isoformat()}', NULL, 'test', 'info', '127.0.0.1', '/test', 'Test', '{{}}')
        """
            )
        )
        await db_session.commit()

        yield 3  # Count of old records

        # Cleanup
        await db_session.execute(
            text(
                """
            DELETE FROM audit_logs
            WHERE resource IN ('test:old-1', 'test:old-2', 'test:old-3')
        """
            )
        )
        await db_session.commit()

    @pytest.mark.asyncio
    async def test_cleanup_expired_audit_logs(self, db_session, old_audit_logs):
        """Test: Cleanup of expired audit logs (older than 7 years)."""
        service = RetentionCleanupService(db_session, tenant_id=1)

        # Run cleanup for EU jurisdiction
        result = await service.cleanup_expired_data(
            category=DataCategory.AUDIT_LOG,
            jurisdiction=RetentionJurisdiction.EU,
            dry_run=False,
        )

        assert result.records_deleted >= 0
        assert result.jurisdiction == "eu"
        assert "GDPR" in result.regulatory_basis

        print(f"✅ Cleaned {result.records_deleted} expired audit logs")

    @pytest.mark.asyncio
    async def test_dry_run_does_not_delete(self, db_session, old_audit_logs):
        """Test: Dry run mode only counts, doesn't delete."""
        service = RetentionCleanupService(db_session, tenant_id=1)

        # Count before
        count_before = await db_session.execute(
            text(
                """
            SELECT COUNT(*) FROM audit_logs
            WHERE resource IN ('test:old-1', 'test:old-2', 'test:old-3')
        """
            )
        )
        before = count_before.scalar()

        # Dry run
        result = await service.cleanup_expired_data(
            category=DataCategory.AUDIT_LOG,
            jurisdiction=RetentionJurisdiction.EU,
            dry_run=True,  # Don't actually delete
        )

        # Count after
        count_after = await db_session.execute(
            text(
                """
            SELECT COUNT(*) FROM audit_logs
            WHERE resource IN ('test:old-1', 'test:old-2', 'test:old-3')
        """
            )
        )
        after = count_after.scalar()

        # Should be same count
        assert before == after
        assert result.records_deleted >= 0

        print(f"✅ Dry run counted {result.records_deleted} records without deleting")

    @pytest.mark.asyncio
    async def test_retention_report_generation(self, db_session):
        """Test: Generate retention compliance report."""
        service = RetentionCleanupService(db_session, tenant_id=1)

        report = await service.generate_retention_report(jurisdiction=RetentionJurisdiction.EU)

        assert report.total_records >= 0
        assert report.jurisdiction == "eu"
        assert report.compliance_status in ["compliant", "attention_required"]
        assert isinstance(report.records_by_category, dict)

        print(f"✅ Retention report generated: {report.total_records} total records")


# =============================================================================
# END-TO-END USER WORKFLOW TESTS
# =============================================================================


class TestEndToEndUserWorkflows:
    """End-to-end tests simulating real user journeys."""

    @pytest.mark.asyncio
    async def test_complete_gdpr_user_journey(self, db_session, test_user):
        """
        Complete user journey:
        1. User accepts cookies
        2. AI makes decision about user
        3. User opts out of profiling
        4. User exports their data
        5. User requests deletion
        """
        user_id = str(test_user)
        tenant_id = 1

        print(f"\n🚀 Starting GDPR journey for user: {user_id}")

        # 1. User accepts cookies
        cookie_manager = CookieConsentManager(db_session)
        consent = await cookie_manager.update_consent(
            user_id=user_id,
            tenant_id=tenant_id,
            preferences={
                "essential": True,
                "analytics": True,
                "marketing": False,
                "personalization": True,
            },
            policy_version="1.0.0",
        )
        assert consent.analytics is True
        print("  ✓ Step 1: Cookie consent saved")

        # 2. AI decision logged
        ai_service = AITransparencyService(db_session)
        decision_id = await ai_service.log_ai_decision(
            user_id=user_id,
            tenant_id=tenant_id,
            agent_id="onboarding-agent",
            decision_type="WORKFLOW_RECOMMENDATION",
            input_data={"role": "manager", "department": "sales"},
            output_data={"recommended_workflow": "sales-onboarding"},
            confidence_score=0.89,
            explanation="Recommended sales onboarding based on your department and role level.",
        )
        assert decision_id is not None
        print("  ✓ Step 2: AI decision logged")

        # 3. User opts out of profiling
        await ai_service.set_profiling_opt_out(
            user_id=user_id,
            tenant_id=tenant_id,
            profiling_type=ProfilingType.BEHAVIORAL,
            opt_out=True,
        )
        is_opted_out = await ai_service.check_profiling_opt_out(
            user_id=user_id,
            tenant_id=tenant_id,
            profiling_type=ProfilingType.BEHAVIORAL,
        )
        assert is_opted_out is True
        print("  ✓ Step 3: Profiling opt-out confirmed")

        # 4. User exports data
        dsar_service = DSARService(db_session)
        export = await dsar_service.export_user_data(
            user_id=user_id,
            tenant_id=tenant_id,
            requested_by_user_id=user_id,
        )
        assert export is not None
        print("  ✓ Step 4: Data exported")

        # 5. User requests deletion
        deletion = await dsar_service.delete_user_data(
            user_id=user_id,
            tenant_id=tenant_id,
            requested_by_user_id=user_id,
        )
        assert deletion is not None
        print("  ✓ Step 5: Deletion requested")

        print(f"✅ Complete GDPR journey finished for user: {user_id}")


# Run tests with:
# pytest tests/integration/governance/test_gdpr_integration_real.py -v --tb=short
