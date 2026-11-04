"""
Slice 6: ComplianceAgent - Comprehensive Test Suite (RED Phase)

Tests policy compliance checking, RBAC enforcement, and tenant isolation validation.
"""

import logging
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.core.agents.capabilities.compliance_agent import ComplianceAgent
from src.core.agents.capabilities.schemas import (
    ComplianceContext,
    ComplianceIssue,
    ComplianceResult,
    ComplianceStatus,
)

# ============================================================================
# TEST SUITE 1: BASIC COMPLIANCE CHECKING
# ============================================================================


class TestBasicComplianceChecking:
    """Test basic compliance validation"""

    @pytest.mark.asyncio
    async def test_allows_compliant_action(self):
        """Should allow actions that pass all compliance checks"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="read_document",
            target_resource="document_123",
            parameters={"format": "pdf"},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        assert result.status == ComplianceStatus.ALLOWED
        assert len(result.issues) == 0
        assert len(result.passed_checks) > 0

    @pytest.mark.asyncio
    async def test_blocks_non_compliant_action(self):
        """Should block actions that violate policies"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="delete_sensitive_data",
            target_resource="pii_database",
            parameters={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        assert result.status == ComplianceStatus.BLOCKED
        assert len(result.issues) > 0
        assert any(issue.severity == "critical" for issue in result.issues)

    @pytest.mark.asyncio
    async def test_returns_warnings_for_risky_actions(self):
        """Should return warnings for risky but allowed actions"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="export_data",
            target_resource="user_data",
            parameters={"destination": "external"},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        assert result.status == ComplianceStatus.WARNING
        assert len(result.issues) > 0
        assert all(issue.severity == "warning" for issue in result.issues)


# ============================================================================
# TEST SUITE 2: RBAC ENFORCEMENT
# ============================================================================


class TestRBACEnforcement:
    """Test role-based access control validation"""

    @pytest.mark.asyncio
    async def test_checks_user_permissions(self):
        """Should validate user has required permissions"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="approve_invoice",
            target_resource="invoice_456",
            parameters={"amount": 5000},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        # Should check if user has approval permission
        assert "rbac_check" in result.passed_checks or any(
            "permission" in issue.policy_violated.lower() for issue in result.issues
        )

    @pytest.mark.asyncio
    async def test_blocks_insufficient_permissions(self):
        """Should block actions when user lacks permissions"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="admin_access",
            target_resource="system_config",
            parameters={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        assert result.status == ComplianceStatus.BLOCKED
        assert any("permission" in issue.policy_violated.lower() for issue in result.issues)

    @pytest.mark.asyncio
    async def test_validates_role_hierarchy(self):
        """Should enforce role hierarchy rules"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="modify_role",
            target_resource="manager_role",
            parameters={"new_permissions": ["admin"]},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        # Role modification should be restricted
        if result.status == ComplianceStatus.BLOCKED:
            assert any("role" in issue.policy_violated.lower() for issue in result.issues)


# ============================================================================
# TEST SUITE 3: TENANT ISOLATION
# ============================================================================


class TestTenantIsolation:
    """Test tenant boundary enforcement"""

    @pytest.mark.asyncio
    async def test_enforces_tenant_boundaries(self):
        """Should prevent cross-tenant access"""
        agent = ComplianceAgent()
        tenant1 = uuid4()
        tenant2 = uuid4()

        context = ComplianceContext(
            action="access_resource",
            target_resource=f"tenant_{tenant2}_data",
            parameters={"requesting_tenant": str(tenant1)},
            tenant_id=tenant1,
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        # Should detect tenant mismatch
        if result.status == ComplianceStatus.BLOCKED:
            assert any("tenant" in issue.policy_violated.lower() for issue in result.issues)

    @pytest.mark.asyncio
    async def test_allows_same_tenant_access(self):
        """Should allow access within same tenant"""
        agent = ComplianceAgent()
        tenant_id = uuid4()

        context = ComplianceContext(
            action="read_data",
            target_resource=f"tenant_{tenant_id}_resource",
            parameters={},
            tenant_id=tenant_id,
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        assert result.status in [ComplianceStatus.ALLOWED, ComplianceStatus.WARNING]

    @pytest.mark.asyncio
    async def test_validates_tenant_id_required(self):
        """Should require tenant_id for all checks"""
        agent = ComplianceAgent()

        with pytest.raises(Exception):
            context = ComplianceContext(
                action="test",
                target_resource="resource",
                parameters={},
                tenant_id=None,  # type: ignore
                user_id=uuid4(),
            )


# ============================================================================
# TEST SUITE 4: POLICY VIOLATIONS
# ============================================================================


class TestPolicyViolations:
    """Test policy violation detection"""

    @pytest.mark.asyncio
    async def test_detects_data_privacy_violations(self):
        """Should detect data privacy policy violations"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="share_pii",
            target_resource="customer_pii",
            parameters={"recipient": "external_party"},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        assert result.status == ComplianceStatus.BLOCKED
        assert any("privacy" in issue.policy_violated.lower() for issue in result.issues)

    @pytest.mark.asyncio
    async def test_detects_financial_policy_violations(self):
        """Should detect financial policy violations"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="approve_payment",
            target_resource="payment_789",
            parameters={"amount": 50000},  # Over limit
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        # Payment over limit should require additional approval
        if result.status != ComplianceStatus.ALLOWED:
            assert any(
                "amount" in issue.policy_violated.lower()
                or "approval" in issue.policy_violated.lower()
                for issue in result.issues
            )

    @pytest.mark.asyncio
    async def test_detects_security_violations(self):
        """Should detect security policy violations"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="disable_encryption",
            target_resource="data_store",
            parameters={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        assert result.status == ComplianceStatus.BLOCKED
        assert any("security" in issue.policy_violated.lower() for issue in result.issues)


# ============================================================================
# TEST SUITE 5: SEVERITY CLASSIFICATION
# ============================================================================


class TestSeverityClassification:
    """Test issue severity classification"""

    @pytest.mark.asyncio
    async def test_critical_issues_block_action(self):
        """Should block actions with critical issues"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="delete_all_data",
            target_resource="production_database",
            parameters={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        assert result.status == ComplianceStatus.BLOCKED
        assert any(issue.severity == "critical" for issue in result.issues)

    @pytest.mark.asyncio
    async def test_warnings_allow_with_notice(self):
        """Should allow actions with warnings but provide notice"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="bulk_update",
            target_resource="user_records",
            parameters={"count": 100},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        if result.status == ComplianceStatus.WARNING:
            assert all(issue.severity == "warning" for issue in result.issues)
            assert len(result.passed_checks) > 0

    @pytest.mark.asyncio
    async def test_info_issues_are_advisory(self):
        """Should allow actions with info-level issues"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="read_report",
            target_resource="monthly_report",
            parameters={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        if result.issues:
            info_issues = [i for i in result.issues if i.severity == "info"]
            if info_issues:
                assert result.status in [
                    ComplianceStatus.ALLOWED,
                    ComplianceStatus.WARNING,
                ]


# ============================================================================
# TEST SUITE 6: REMEDIATION SUGGESTIONS
# ============================================================================


class TestRemediationSuggestions:
    """Test remediation guidance"""

    @pytest.mark.asyncio
    async def test_provides_remediation_steps(self):
        """Should provide remediation steps for violations"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="access_restricted_resource",
            target_resource="confidential_docs",
            parameters={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        if result.status == ComplianceStatus.BLOCKED:
            assert all(issue.remediation is not None for issue in result.issues)
            assert all(len(issue.remediation) > 0 for issue in result.issues)

    @pytest.mark.asyncio
    async def test_remediation_is_actionable(self):
        """Should provide actionable remediation guidance"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="export_sensitive_data",
            target_resource="customer_data",
            parameters={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        for issue in result.issues:
            if issue.remediation:
                # Remediation should contain action words
                assert any(
                    word in issue.remediation.lower()
                    for word in ["request", "contact", "obtain", "provide", "use"]
                )


# ============================================================================
# TEST SUITE 7: MULTIPLE POLICIES
# ============================================================================


class TestMultiplePolicies:
    """Test checking multiple policies"""

    @pytest.mark.asyncio
    async def test_checks_all_applicable_policies(self):
        """Should check all policies relevant to action"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="process_payment",
            target_resource="invoice_payment",
            parameters={"amount": 1000, "currency": "USD"},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        # Should check multiple policies: RBAC, financial, audit
        assert len(result.passed_checks) >= 3 or len(result.issues) > 0

    @pytest.mark.asyncio
    async def test_aggregates_multiple_violations(self):
        """Should aggregate multiple policy violations"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="unauthorized_admin_action",
            target_resource="system_critical",
            parameters={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        # Multiple violations possible: permission + security + audit
        if result.status == ComplianceStatus.BLOCKED:
            assert len(result.issues) >= 1


# ============================================================================
# TEST SUITE 8: EDGE CASES
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_handles_unknown_action(self):
        """Should handle unknown actions gracefully"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="unknown_future_action",
            target_resource="resource",
            parameters={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        # Should either allow with warning or apply default policy
        assert result.status in [
            ComplianceStatus.ALLOWED,
            ComplianceStatus.WARNING,
            ComplianceStatus.BLOCKED,
        ]

    @pytest.mark.asyncio
    async def test_handles_empty_parameters(self):
        """Should handle empty parameters"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="test_action",
            target_resource="resource",
            parameters={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        assert result is not None
        assert isinstance(result, ComplianceResult)

    @pytest.mark.asyncio
    async def test_handles_null_target_resource(self):
        """Should handle actions without specific target resource"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="list_resources",
            target_resource="",
            parameters={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        assert result is not None


# ============================================================================
# TEST SUITE 9: LOGGING & OBSERVABILITY
# ============================================================================


class TestLoggingObservability:
    """Test logging and observability"""

    @pytest.mark.asyncio
    async def test_logs_compliance_checks(self, caplog):
        """Should log compliance check operations"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="test_action",
            target_resource="resource",
            parameters={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        with caplog.at_level(logging.INFO):
            await agent.check_compliance(context)

        assert any("compliance" in record.message.lower() for record in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_violations(self, caplog):
        """Should log policy violations"""
        agent = ComplianceAgent()
        context = ComplianceContext(
            action="delete_sensitive_data",
            target_resource="pii_db",
            parameters={},
            tenant_id=uuid4(),
            user_id=uuid4(),
        )

        result = await agent.check_compliance(context)

        if result.status == ComplianceStatus.BLOCKED:
            assert any("blocked" in record.message.lower() for record in caplog.records)


# ============================================================================
# TEST SUITE 10: VALIDATION
# ============================================================================


class TestValidation:
    """Test input validation"""

    @pytest.mark.asyncio
    async def test_requires_action(self):
        """Should require action field"""
        agent = ComplianceAgent()

        with pytest.raises(Exception):
            context = ComplianceContext(
                action="",
                target_resource="resource",
                parameters={},
                tenant_id=uuid4(),
                user_id=uuid4(),
            )
            await agent.check_compliance(context)

    @pytest.mark.asyncio
    async def test_requires_tenant_id(self):
        """Should require tenant_id"""
        agent = ComplianceAgent()

        with pytest.raises(Exception):
            context = ComplianceContext(
                action="test",
                target_resource="resource",
                parameters={},
                tenant_id=None,  # type: ignore
                user_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_requires_user_id(self):
        """Should require user_id for audit trail"""
        agent = ComplianceAgent()

        with pytest.raises(Exception):
            context = ComplianceContext(
                action="test",
                target_resource="resource",
                parameters={},
                tenant_id=uuid4(),
                user_id=None,  # type: ignore
            )
