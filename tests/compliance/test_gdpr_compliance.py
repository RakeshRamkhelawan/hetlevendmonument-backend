"""
SP-H08: GDPR & Governance Compliance Tests -- echte service-aanroepen.

Vervangt de mock-only assertions door async integratietests die echte
TwinConsentManager, GDPREnforcer en DSARService aanroepen.

Bevat 10 tests (8 happy path + 2 unhappy path):
- Consent create default disabled (GDPR Art. 7)
- Consent enable + check
- Consent revoke + tracking stop
- Twin hard-delete request flag (Art. 17)
- PII detectie (email)
- DSAR export user data (Art. 15 + 20)
- DSAR export includes audit trail (Art. 15)
- DSAR soft delete marks inactive (Art. 17)
- DSAR hard delete rejects non-admin (Art. 17 auth)
- DSAR cross-tenant rejection (Art. 32)
"""

import pytest
from sqlalchemy import select

from src.core.governance.dsar_service import (
    DSARAuthorizationError,
    DSARService,
    DSARTenantIsolationError,
)
from src.core.governance.gdpr_enforcer import GDPREnforcer
from src.core.learning.consent.consent_manager import TwinConsentManager, TwinConsentStatus
from src.core.models.rbac_models import User

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestConsentManagement:
    """GDPR Artikel 7 -- expliciete toestemming."""

    async def test_consent_create_defaults_to_disabled(self, postgres_session):
        """Nieuw consent record default disabled (opt-in vereist)."""
        mgr = TwinConsentManager(db=postgres_session)
        status = await mgr.get_consent_status(
            user_id="gdpr-test-user-001", tenant_id=1
        )
        assert status == TwinConsentStatus.DISABLED

    async def test_consent_enable_and_check(self, postgres_session):
        """Expliciete opt-in maakt consent actief."""
        mgr = TwinConsentManager(db=postgres_session)
        await mgr.set_consent_status(
            user_id="gdpr-test-user-002",
            tenant_id=1,
            status=TwinConsentStatus.ENABLED,
        )
        status = await mgr.get_consent_status(
            user_id="gdpr-test-user-002", tenant_id=1
        )
        assert status == TwinConsentStatus.ENABLED

    async def test_consent_revoke_clears_tracking(self, postgres_session):
        """Opt-out stopt tracking onmiddellijk."""
        mgr = TwinConsentManager(db=postgres_session)
        uid = "gdpr-test-user-003"

        # Enable
        await mgr.set_consent_status(
            user_id=uid, tenant_id=1, status=TwinConsentStatus.ENABLED
        )
        assert await mgr.is_tracking_enabled(user_id=uid, tenant_id=1) is True

        # Revoke
        await mgr.set_consent_status(
            user_id=uid, tenant_id=1, status=TwinConsentStatus.DISABLED
        )
        assert await mgr.is_tracking_enabled(user_id=uid, tenant_id=1) is False

    async def test_twin_request_hard_delete_sets_flag(self, postgres_session):
        """Art. 17 request markeert twin voor erasure."""
        mgr = TwinConsentManager(db=postgres_session)
        uid = "gdpr-test-user-004"

        await mgr.request_hard_delete(user_id=uid, tenant_id=1)
        record = await mgr._get_or_create_consent(uid, 1)
        assert record.hard_delete_requested is True


class TestPIIDetection:
    """GDPREnforcer PII detectie."""

    def test_pii_detection_finds_email(self):
        """detect_pii herkent email-patronen in payload."""
        enforcer = GDPREnforcer()
        detected = enforcer.detect_pii({"contact": "test@integration.local"})
        assert "email" in detected


class TestDSARAccessAndErasure:
    """GDPR Artikel 15 (Access), 17 (Erasure), 20 (Portability)."""

    async def test_dsar_export_returns_user_data(self, postgres_session):
        """DSAR export geeft user data terug voor bestaande user."""
        service = DSARService(db=postgres_session)
        result = await service.export_user_data(
            user_id="2",
            tenant_id=1,
            requested_by_user_id="2",
            is_admin=False,
        )
        assert result.user_id == "2"
        assert result.tenant_id == 1
        assert "user_profile" in result.data
        assert result.total_records >= 1

    async def test_dsar_export_includes_audit_trail(self, postgres_session):
        """Art. 15 export bevat audit trail categorie."""
        service = DSARService(db=postgres_session)
        result = await service.export_user_data(
            user_id="2",
            tenant_id=1,
            requested_by_user_id="2",
            is_admin=False,
        )
        assert "audit_logs" in result.data

    async def test_dsar_soft_delete_marks_inactive(self, postgres_session):
        """Art. 17 soft delete zet user inactive met grace period."""
        service = DSARService(db=postgres_session)
        result = await service.delete_user_data(
            user_id="2",
            tenant_id=1,
            hard_delete=False,
            requested_by_user_id="2",
            is_admin=False,
        )
        assert result.delete_type == "soft"

        # Verify user is marked inactive within the same transaction
        user_result = await postgres_session.execute(
            select(User).where(User.id == 2, User.tenant_id == 1)
        )
        user = user_result.scalar_one()
        assert user.is_active is False
        assert user.deleted_at is not None
        assert user.deletion_scheduled_for is not None

    async def test_dsar_hard_delete_rejects_non_admin(self, postgres_session):
        """Art. 17 hard delete vereist admin privileges."""
        service = DSARService(db=postgres_session)
        with pytest.raises(DSARAuthorizationError):
            await service.delete_user_data(
                user_id="2",
                tenant_id=1,
                hard_delete=True,
                requested_by_user_id="2",
                is_admin=False,
            )

    async def test_dsar_export_rejects_cross_tenant(self, postgres_session):
        """Cross-tenant DSAR export wordt afgewezen."""
        service = DSARService(db=postgres_session)
        with pytest.raises(DSARTenantIsolationError):
            await service.export_user_data(
                user_id="2",
                tenant_id=999,
                requested_by_user_id="2",
                is_admin=False,
            )
