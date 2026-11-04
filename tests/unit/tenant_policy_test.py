"""
TDD Tests for TKT-F0-02: Tenant Policy Enforcement
Phase 0 - Contract Foundation
"""

from typing import Any, Dict

import pytest

from src.core.contracts.enforcement import PolicyEnforcer
from src.core.contracts.policy import ApprovalThreshold, CapabilityPolicy, PlanTier, TenantPolicy


class TestTenantPolicy:
    """Happy and unhappy tests for tenant policy"""

    def test_happy_valid_policy_creation(self):
        """Happy: Valid tenant policy -> success"""
        policy = TenantPolicy(
            tenant_id="tenant-123",
            plan_tier=PlanTier.GROWTH,
            enabled_capabilities=["email.send", "sms.send", "slack.notify"],
            provider_priority=["primary", "fallback"],
            approval_thresholds={
                "payment.charge": ApprovalThreshold(amount=1000, currency="EUR"),
                "data.export": ApprovalThreshold(requires_approval=True),
            },
            compliance_profile="standard",
        )

        assert policy.tenant_id == "tenant-123"
        assert policy.plan_tier == PlanTier.GROWTH
        assert "email.send" in policy.enabled_capabilities
        result = policy.can_execute("email.send")
        assert result.allowed is True

    def test_unhappy_capability_not_allowed(self):
        """Unhappy A: capability not allowed in plan -> blocked with policy reason"""
        policy = TenantPolicy(
            tenant_id="tenant-123",
            plan_tier=PlanTier.STARTER,
            enabled_capabilities=["email.send"],  # sms.send NOT included
        )

        result = policy.can_execute("sms.send")
        assert result.allowed is False
        assert "not enabled" in result.reason.lower() or "not allowed" in result.reason.lower()

    def test_unhappy_approval_required_but_missing(self):
        """Unhappy B: approval required but missing -> pending_approval status"""
        policy = TenantPolicy(
            tenant_id="tenant-123",
            plan_tier=PlanTier.GROWTH,
            enabled_capabilities=["payment.charge"],
            approval_thresholds={"payment.charge": ApprovalThreshold(amount=100, currency="EUR")},
        )

        # High-value payment should require approval
        result = policy.check_approval_required("payment.charge", {"amount": 500})
        assert result.policy is not None
        # Check status for approval requirement
        assert result.status == "pending_approval"
        assert result.status == "pending_approval"


class TestPolicyEnforcer:
    """Tests for runtime policy enforcement"""

    @pytest.fixture
    def enforcer(self):
        """Create policy enforcer with test policies"""
        policies = {
            "tenant-starter": TenantPolicy(
                tenant_id="tenant-starter",
                plan_tier=PlanTier.STARTER,
                enabled_capabilities=["email.send"],
            ),
            "tenant-growth": TenantPolicy(
                tenant_id="tenant-growth",
                plan_tier=PlanTier.GROWTH,
                enabled_capabilities=["email.send", "sms.send", "payment.charge"],
                approval_thresholds={"payment.charge": ApprovalThreshold(amount=500)},
            ),
        }
        return PolicyEnforcer(policies)

    def test_happy_allowed_capability(self, enforcer):
        """Happy: allowed capability -> execute success"""
        result = enforcer.enforce(tenant_id="tenant-growth", capability_key="email.send", inputs={})

        assert result.allowed is True
        assert result.policy.tenant_id == "tenant-growth"

    def test_unhappy_capability_not_in_plan(self, enforcer):
        """Unhappy A: capability not in plan -> blocked"""
        result = enforcer.enforce(
            tenant_id="tenant-starter",
            capability_key="sms.send",
            inputs={},  # Not in STARTER plan
        )

        assert result.allowed is False
        assert "not enabled" in result.reason.lower() or "Starter" in result.reason

    def test_unhappy_approval_required(self, enforcer):
        """Unhappy B: approval required -> pending_approval"""
        result = enforcer.enforce(
            tenant_id="tenant-growth",
            capability_key="payment.charge",
            inputs={"amount": 1000},  # Above threshold
        )

        assert result.allowed is False
        assert result.status == "pending_approval"
        # Verify approval context is present
        assert result.execution_context.get("requires_approval") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
