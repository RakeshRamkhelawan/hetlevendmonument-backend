"""
Tests voor Tenant Policy Contract (Fase 0.2)

Happy paths:
- Policy creation met alle velden
- Capability enabled check
- Provider priority retrieval
- Approval threshold validatie
- Approval check met bedrag onder/boven threshold

Unhappy paths:
- Lege tenant_id
- Invalid plan_tier
- Capability niet enabled
- Approval voor niet-enabled capability
- Invalid amount format in approval check
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

from src.core.contracts.policy import (
    ApprovalRequirement,
    ApprovalThreshold,
    ComplianceProfile,
    PlanTier,
    PolicyCheckResult,
    TenantPolicy,
)


class TestTenantPolicy:
    """Test TenantPolicy model."""

    def test_create_policy_minimal(self) -> None:
        """Happy path: Create policy met alleen verplichte velden."""
        policy = TenantPolicy(
            tenant_id="tenant-123",
            plan_tier=PlanTier.STARTER,
        )

        assert policy.tenant_id == "tenant-123"
        assert policy.plan_tier == PlanTier.STARTER
        assert policy.enabled_capabilities == set()
        assert policy.provider_priority == {}
        assert policy.approval_thresholds == {}
        assert policy.compliance_profile == ComplianceProfile.BASIC

    def test_create_policy_complete(self) -> None:
        """Happy path: Create policy met alle velden."""
        policy = TenantPolicy(
            tenant_id="tenant-456",
            plan_tier=PlanTier.PRO,
            enabled_capabilities={"send_email", "process_payment"},
            provider_priority={
                "email": ["sendgrid", "aws_ses"],
                "sms": ["twilio"],
            },
            approval_thresholds={
                "process_payment": ApprovalThreshold(
                    amount_threshold=Decimal("1000.00"),
                    approver_roles={"manager", "finance"},
                )
            },
            compliance_profile=ComplianceProfile.GDPR,
            custom_limits={"max_workflows": 100},
            effective_from="2026-01-01T00:00:00Z",
        )

        assert policy.tenant_id == "tenant-456"
        assert policy.plan_tier == PlanTier.PRO
        assert "send_email" in policy.enabled_capabilities
        assert policy.provider_priority["email"] == ["sendgrid", "aws_ses"]
        assert policy.compliance_profile == ComplianceProfile.GDPR

    def test_empty_tenant_id_raises_error(self) -> None:
        """Unhappy path: Lege tenant_id moet error geven."""
        with pytest.raises(ValueError) as exc_info:
            TenantPolicy(
                tenant_id="",
                plan_tier=PlanTier.STARTER,
            )

        assert "tenant_id" in str(exc_info.value).lower() or "empty" in str(exc_info.value).lower()

    def test_whitespace_tenant_id_raises_error(self) -> None:
        """Unhappy path: Whitespace-only tenant_id moet error geven."""
        with pytest.raises(ValueError) as exc_info:
            TenantPolicy(
                tenant_id="   ",
                plan_tier=PlanTier.STARTER,
            )

        assert "tenant_id" in str(exc_info.value).lower() or "empty" in str(exc_info.value).lower()


class TestCapabilityEnablement:
    """Test capability enablement checks."""

    @pytest.fixture
    def starter_policy(self) -> TenantPolicy:
        return TenantPolicy(
            tenant_id="tenant-123",
            plan_tier=PlanTier.STARTER,
            enabled_capabilities={"send_email", "create_task"},
        )

    def test_capability_enabled_true(self, starter_policy: TenantPolicy) -> None:
        """Happy path: Enabled capability detected."""
        assert starter_policy.is_capability_enabled("send_email") is True
        assert starter_policy.is_capability_enabled("create_task") is True

    def test_capability_enabled_false(self, starter_policy: TenantPolicy) -> None:
        """Happy path: Disabled capability detected."""
        assert starter_policy.is_capability_enabled("delete_data") is False
        assert starter_policy.is_capability_enabled("process_payment") is False

    def test_capability_enabled_empty_set(self) -> None:
        """Unhappy path: Lege enabled_capabilities."""
        policy = TenantPolicy(
            tenant_id="tenant-123",
            plan_tier=PlanTier.STARTER,
            enabled_capabilities=set(),
        )

        assert policy.is_capability_enabled("anything") is False


class TestProviderPriority:
    """Test provider priority retrieval."""

    @pytest.fixture
    def policy_with_providers(self) -> TenantPolicy:
        return TenantPolicy(
            tenant_id="tenant-123",
            plan_tier=PlanTier.PRO,
            provider_priority={
                "email": ["sendgrid", "aws_ses", "mailgun"],
                "sms": ["twilio", "vonage"],
            },
        )

    def test_get_provider_priority_existing(self, policy_with_providers: TenantPolicy) -> None:
        """Happy path: Provider priority voor bestaand type."""
        email_priority = policy_with_providers.get_provider_priority("email")
        assert email_priority == ["sendgrid", "aws_ses", "mailgun"]
        assert email_priority is not None
        assert email_priority[0] == "sendgrid"  # Primary provider

    def test_get_provider_priority_nonexistent(self, policy_with_providers: TenantPolicy) -> None:
        """Happy path: None voor niet-bestaand type."""
        assert policy_with_providers.get_provider_priority("push_notification") is None


class TestApprovalThresholds:
    """Test approval threshold validatie."""

    @pytest.fixture
    def policy_with_thresholds(self) -> TenantPolicy:
        return TenantPolicy(
            tenant_id="tenant-123",
            plan_tier=PlanTier.PRO,
            enabled_capabilities={"process_payment", "refund_payment"},
            approval_thresholds={
                "process_payment": ApprovalThreshold(
                    amount_threshold=Decimal("1000.00"),
                    approver_roles={"manager", "finance"},
                    auto_approve_after_ms=86400000,  # 24h
                ),
                "refund_payment": ApprovalThreshold(
                    amount_threshold=Decimal("500.00"),
                    approver_roles={"manager"},
                    requires_approval=True,
                ),
            },
        )

    def test_get_approval_threshold_existing(self, policy_with_thresholds: TenantPolicy) -> None:
        """Happy path: Get threshold voor enabled capability."""
        threshold = policy_with_thresholds.get_approval_threshold("process_payment")
        assert threshold is not None
        assert threshold.amount_threshold == Decimal("1000.00")
        assert threshold.approver_roles == {"manager", "finance"}

    def test_get_approval_threshold_nonexistent(self, policy_with_thresholds: TenantPolicy) -> None:
        """Happy path: None voor capability zonder threshold."""
        assert policy_with_thresholds.get_approval_threshold("send_email") is None

    def test_approval_threshold_requires_approval_for_over(
        self, policy_with_thresholds: TenantPolicy
    ) -> None:
        """Happy path: Approval nodig voor bedrag boven threshold."""
        threshold = policy_with_thresholds.get_approval_threshold("process_payment")
        assert threshold is not None
        assert threshold.requires_approval_for(Decimal("1500.00")) is True
        assert threshold.requires_approval_for(Decimal("1000.00")) is True  # Exact threshold

    def test_approval_threshold_no_approval_for_under(
        self, policy_with_thresholds: TenantPolicy
    ) -> None:
        """Happy path: Geen approval nodig voor bedrag onder threshold."""
        threshold = policy_with_thresholds.get_approval_threshold("process_payment")
        assert threshold is not None
        assert threshold.requires_approval_for(Decimal("999.99")) is False
        assert threshold.requires_approval_for(Decimal("100.00")) is False

    def test_check_approval_required_over_threshold(
        self, policy_with_thresholds: TenantPolicy
    ) -> None:
        """Happy path: Approval requirement returned voor bedrag boven threshold."""
        input_data: dict[str, Any] = {"amount": Decimal("1500.00"), "description": "Test payment"}  # TODO(TYPE): replace Any with concrete type
        approval_req = policy_with_thresholds.check_approval_required("process_payment", input_data)

        assert approval_req is not None
        assert approval_req.capability_key == "process_payment"
        assert approval_req.amount == Decimal("1500.00")
        assert "manager" in approval_req.approver_roles
        assert approval_req.auto_approve_after_ms == 86400000

    def test_check_approval_required_under_threshold(
        self, policy_with_thresholds: TenantPolicy
    ) -> None:
        """Happy path: Geen approval voor bedrag onder threshold."""
        input_data: dict[str, Any] = {"amount": Decimal("500.00"), "description": "Small payment"}  # TODO(TYPE): replace Any with concrete type
        approval_req = policy_with_thresholds.check_approval_required("process_payment", input_data)

        assert approval_req is None

    def test_check_approval_required_no_amount(self, policy_with_thresholds: TenantPolicy) -> None:
        """Happy path: Geen approval als geen amount in input."""
        input_data: dict[str, Any] = {"description": "Payment without amount"}  # TODO(TYPE): replace Any with concrete type
        approval_req = policy_with_thresholds.check_approval_required("process_payment", input_data)

        assert approval_req is None

    def test_check_approval_required_invalid_amount(
        self, policy_with_thresholds: TenantPolicy
    ) -> None:
        """Unhappy path: Invalid amount format handled gracefully."""
        input_data: dict[str, Any] = {"amount": "not-a-number", "description": "Invalid"}  # TODO(TYPE): replace Any with concrete type
        approval_req = policy_with_thresholds.check_approval_required("process_payment", input_data)

        # Should return None (no approval) rather than crash
        assert approval_req is None

    def test_check_approval_disabled_threshold(self) -> None:
        """Unhappy path: Threshold met requires_approval=False."""
        policy = TenantPolicy(
            tenant_id="tenant-123",
            plan_tier=PlanTier.STARTER,
            enabled_capabilities={"low_risk_action"},
            approval_thresholds={
                "low_risk_action": ApprovalThreshold(
                    amount_threshold=Decimal("1000.00"),
                    approver_roles=set(),
                    requires_approval=False,  # Disabled
                )
            },
        )

        input_data: dict[str, Any] = {"amount": Decimal("5000.00")}  # TODO(TYPE): replace Any with concrete type
        approval_req = policy.check_approval_required("low_risk_action", input_data)

        assert approval_req is None  # Approval uitgeschakeld

    def test_threshold_for_non_enabled_capability_raises_validation_error(self) -> None:
        """Unhappy path: Threshold voor niet-enabled capability moet error geven."""
        with pytest.raises(ValueError) as exc_info:
            TenantPolicy(
                tenant_id="tenant-123",
                plan_tier=PlanTier.STARTER,
                enabled_capabilities={"send_email"},  # Niet process_payment!
                approval_thresholds={
                    "process_payment": ApprovalThreshold(
                        amount_threshold=Decimal("1000.00"),
                        approver_roles={"manager"},
                    )
                },
            )

        assert "process_payment" in str(exc_info.value)
        assert "enabled" in str(exc_info.value).lower()


class TestComplianceProfile:
    """Test compliance profile properties."""

    def test_gdpr_compliance(self) -> None:
        """Happy path: GDPR compliance profile."""
        profile = ComplianceProfile.GDPR

        assert profile.requires_data_residency is True
        assert profile.requires_explicit_consent is True
        assert profile.requires_audit_trail is True
        assert profile.retention_days == 365  # 1 jaar (max per policy)

    def test_basic_compliance(self) -> None:
        """Happy path: Basic compliance profile."""
        profile = ComplianceProfile.BASIC

        assert profile.requires_data_residency is False
        assert profile.requires_explicit_consent is False
        assert profile.requires_audit_trail is False
        assert profile.retention_days == 365  # 1 jaar

    def test_hipaa_compliance(self) -> None:
        """Happy path: HIPAA compliance profile."""
        profile = ComplianceProfile.HIPAA

        assert profile.requires_data_residency is True
        assert profile.requires_explicit_consent is False
        assert profile.requires_audit_trail is True

    def test_policy_with_compliance_profile(self) -> None:
        """Happy path: Policy met specifiek compliance profile."""
        policy = TenantPolicy(
            tenant_id="tenant-123",
            plan_tier=PlanTier.ENTERPRISE,
            compliance_profile=ComplianceProfile.HIPAA,
        )

        assert policy.compliance_profile.requires_audit_trail is True


class TestApprovalRequirement:
    """Test ApprovalRequirement dataclass."""

    def test_create_approval_requirement(self) -> None:
        """Happy path: Create approval requirement."""
        req = ApprovalRequirement(
            capability_key="process_payment",
            amount=Decimal("1500.00"),
            approver_roles={"manager", "finance"},
            reason="Amount exceeds EUR1000 threshold",
            auto_approve_after_ms=86400000,
        )

        assert req.capability_key == "process_payment"
        assert req.amount == Decimal("1500.00")
        assert "manager" in req.approver_roles
        assert req.reason == "Amount exceeds EUR1000 threshold"
        assert req.auto_approve_after_ms == 86400000

    def test_approval_requirement_no_amount(self) -> None:
        """Happy path: Approval requirement zonder amount (non-monetary)."""
        req = ApprovalRequirement(
            capability_key="delete_data",
            amount=None,
            approver_roles={"admin"},
            reason="Destructive action requires approval",
        )

        assert req.amount is None
        assert req.capability_key == "delete_data"


class TestPolicyCheckResult:
    """Test PolicyCheckResult factory methods."""

    def test_allowed_result(self) -> None:
        """Happy path: Allowed result."""
        result = PolicyCheckResult.allowed()

        assert result.allowed is True
        assert result.reason is None
        assert result.violation_type is None
        assert result.requires_approval is False

    def test_denied_result(self) -> None:
        """Happy path: Denied result."""
        result = PolicyCheckResult.denied(
            reason="Capability not in plan",
            violation_type="CAPABILITY_NOT_ENABLED",
            suggested_tier=PlanTier.PRO,
        )

        assert result.allowed is False
        assert result.reason == "Capability not in plan"
        assert result.violation_type == "CAPABILITY_NOT_ENABLED"
        assert result.suggested_tier == PlanTier.PRO

    def test_pending_approval_result(self) -> None:
        """Happy path: Pending approval result."""
        req = ApprovalRequirement(
            capability_key="process_payment",
            amount=Decimal("1500.00"),
            approver_roles={"manager"},
            reason="Amount exceeds threshold",
        )

        result = PolicyCheckResult.pending_approval(req)

        assert result.allowed is False
        assert result.requires_approval is True
        assert result.approval_requirement == req
        assert result.reason is not None and "Amount exceeds threshold" in result.reason


class TestPolicySerialization:
    """Test policy serialization naar dict."""

    def test_to_dict(self) -> None:
        """Happy path: Serialize policy naar dict."""
        policy = TenantPolicy(
            tenant_id="tenant-123",
            plan_tier=PlanTier.PRO,
            enabled_capabilities={"send_email", "process_payment"},
            approval_thresholds={
                "process_payment": ApprovalThreshold(
                    amount_threshold=Decimal("1000.00"),
                    approver_roles={"manager"},
                )
            },
        )

        data = policy.to_dict()

        assert data["tenant_id"] == "tenant-123"
        assert data["plan_tier"] == "pro"
        assert "send_email" in data["enabled_capabilities"]
        assert data["approval_thresholds"]["process_payment"]["amount_threshold"] == "1000.00"


class TestAmountExtraction:
    """Test interne amount extractie uit input data."""

    @pytest.fixture
    def policy(self) -> TenantPolicy:
        return TenantPolicy(
            tenant_id="tenant-123",
            plan_tier=PlanTier.STARTER,
            enabled_capabilities={"process_payment"},
            approval_thresholds={
                "process_payment": ApprovalThreshold(
                    amount_threshold=Decimal("100.00"),
                    approver_roles={"manager"},
                )
            },
        )

    def test_extract_amount_field(self, policy: TenantPolicy) -> None:
        """Happy path: Extract 'amount' field."""
        input_data: dict[str, Any] = {"amount": Decimal("150.00")}  # TODO(TYPE): replace Any with concrete type
        approval_req = policy.check_approval_required("process_payment", input_data)

        assert approval_req is not None
        assert approval_req.amount == Decimal("150.00")

    def test_extract_total_field(self, policy: TenantPolicy) -> None:
        """Happy path: Extract 'total' field als fallback."""
        input_data: dict[str, Any] = {"total": Decimal("200.00")}  # TODO(TYPE): replace Any with concrete type
        approval_req = policy.check_approval_required("process_payment", input_data)

        assert approval_req is not None
        assert approval_req.amount == Decimal("200.00")

    def test_extract_value_field(self, policy: TenantPolicy) -> None:
        """Happy path: Extract 'value' field als fallback."""
        input_data: dict[str, Any] = {"value": Decimal("50.00")}  # TODO(TYPE): replace Any with concrete type
        approval_req = policy.check_approval_required("process_payment", input_data)

        assert approval_req is None  # Onder threshold

    def test_extract_price_field(self, policy: TenantPolicy) -> None:
        """Happy path: Extract 'price' field als fallback."""
        input_data: dict[str, Any] = {"price": Decimal("150.00")}  # TODO(TYPE): replace Any with concrete type
        approval_req = policy.check_approval_required("process_payment", input_data)

        assert approval_req is not None
        assert approval_req.amount == Decimal("150.00")

    def test_extract_cost_field(self, policy: TenantPolicy) -> None:
        """Happy path: Extract 'cost' field als fallback."""
        input_data: dict[str, Any] = {"cost": Decimal("150.00")}  # TODO(TYPE): replace Any with concrete type
        approval_req = policy.check_approval_required("process_payment", input_data)

        assert approval_req is not None
        assert approval_req.amount == Decimal("150.00")

    def test_extract_sum_field(self, policy: TenantPolicy) -> None:
        """Happy path: Extract 'sum' field als fallback."""
        input_data: dict[str, Any] = {"sum": Decimal("150.00")}  # TODO(TYPE): replace Any with concrete type
        approval_req = policy.check_approval_required("process_payment", input_data)

        assert approval_req is not None
        assert approval_req.amount == Decimal("150.00")
