"""
Tests voor Policy Enforcement (Fase 0.2)

Happy paths:
- Capability check passed
- Capability valid + policy allowed
- Approval vereist maar policy ok
- Provider priority extraction

Unhappy paths:
- Unknown capability
- Invalid input schema
- Capability niet enabled in plan
- Workflow met mixed permissions
"""

from decimal import Decimal
from typing import Any

import pytest

from src.core.contracts.capability import (
    AuditPolicy,
    CapabilityContract,
    CapabilityRegistry,
    FallbackPolicy,
    RetryPolicy,
)
from src.core.contracts.enforcement import (
    EnforcementResult,
    PolicyEnforcer,
    can_execute_capability,
    require_approval_for,
)
from src.core.contracts.policy import ApprovalThreshold, PlanTier, TenantPolicy


@pytest.fixture
def sample_capabilities() -> dict[str, CapabilityContract]:
    """Sample capabilities voor testing."""
    return {
        "crm_createcontact": CapabilityContract(
            capability_key="crm_createcontact",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                },
                "required": ["name"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "created_at": {"type": "string"},
                },
            },
        ),
        "payment_process": CapabilityContract(
            capability_key="payment_process",
            input_schema={
                "type": "object",
                "properties": {
                    "amount": {"type": "number"},
                    "currency": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["amount", "currency"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
        ),
        "email_send": CapabilityContract(
            capability_key="email_send",
            input_schema={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                },
            },
        ),
    }


@pytest.fixture
def registry(sample_capabilities: dict[str, CapabilityContract]) -> CapabilityRegistry:
    """Capability registry met sample capabilities."""
    reg = CapabilityRegistry()
    for cap in sample_capabilities.values():
        reg.register(cap)
    return reg


@pytest.fixture
def starter_policy() -> TenantPolicy:
    """Starter plan policy."""
    return TenantPolicy(
        tenant_id="tenant-starter",
        plan_tier=PlanTier.STARTER,
        enabled_capabilities={"crm_createcontact", "email_send"},
        provider_priority={
            "email_send": ["sendgrid", "aws_ses"],
        },
    )


@pytest.fixture
def pro_policy() -> TenantPolicy:
    """Pro plan policy met payment capabilities."""
    return TenantPolicy(
        tenant_id="tenant-pro",
        plan_tier=PlanTier.PRO,
        enabled_capabilities={"crm_createcontact", "email_send", "payment_process"},
        provider_priority={
            "email_send": ["sendgrid", "aws_ses"],
            "payment_process": ["stripe", "adyen"],
        },
        approval_thresholds={
            "payment_process": ApprovalThreshold(
                amount_threshold=Decimal("1000.00"),
                approver_roles={"manager", "finance"},
            )
        },
    )


class TestPolicyEnforcer:
    """Test PolicyEnforcer klasse."""

    def test_check_execute_permission_allowed(
        self, registry: CapabilityRegistry, starter_policy: TenantPolicy
    ) -> None:
        """Happy path: Capability valid + enabled in policy."""
        enforcer = PolicyEnforcer(registry)
        node: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "capability_key": "crm_createcontact",
            "input": {"name": "John Doe", "email": "john@example.com"},
        }

        result = enforcer.check_execute_permission(node, starter_policy)

        assert result.can_execute is True
        assert result.capability_valid is True
        assert result.policy_allowed is True
        assert result.reason is None

    def test_check_execute_permission_unknown_capability(
        self, registry: CapabilityRegistry, starter_policy: TenantPolicy
    ) -> None:
        """Unhappy path: Unknown capability."""
        enforcer = PolicyEnforcer(registry)
        node: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "capability_key": "unknown_capability",
            "input": {"foo": "bar"},
        }

        result = enforcer.check_execute_permission(node, starter_policy)

        assert result.can_execute is False
        assert result.capability_valid is False
        assert result.violation_type == "UNKNOWN_CAPABILITY"
        assert result.reason is not None
        assert "unknown" in result.reason.lower()

    def test_check_execute_permission_invalid_input(
        self, registry: CapabilityRegistry, starter_policy: TenantPolicy
    ) -> None:
        """Unhappy path: Valid capability maar invalid input."""
        enforcer = PolicyEnforcer(registry)
        node: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "capability_key": "crm_createcontact",
            "input": {},  # Missing required 'name'
        }

        result = enforcer.check_execute_permission(node, starter_policy)

        assert result.can_execute is False
        assert result.capability_valid is True  # Capability bestaat
        assert result.policy_allowed is False
        assert result.violation_type == "INVALID_INPUT"
        assert result.reason is not None
        assert "invalid" in result.reason.lower()

    def test_check_execute_permission_not_enabled(
        self, registry: CapabilityRegistry, starter_policy: TenantPolicy
    ) -> None:
        """Unhappy path: Capability valid maar niet enabled in plan."""
        enforcer = PolicyEnforcer(registry)
        node: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "capability_key": "payment_process",
            "input": {"amount": 100, "currency": "EUR"},
        }

        result = enforcer.check_execute_permission(node, starter_policy)

        assert result.can_execute is False
        assert result.capability_valid is True
        assert result.policy_allowed is False
        assert result.violation_type == "CAPABILITY_NOT_ENABLED"
        assert result.reason is not None
        assert "not enabled" in result.reason.lower()

    def test_check_execute_permission_requires_approval(
        self, registry: CapabilityRegistry, pro_policy: TenantPolicy
    ) -> None:
        """Happy path: Capability valid maar approval required."""
        enforcer = PolicyEnforcer(registry)
        node: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "capability_key": "payment_process",
            "input": {"amount": 1500, "currency": "EUR"},
        }

        result = enforcer.check_execute_permission(node, pro_policy)

        assert result.can_execute is False  # Nog niet toestaan
        assert result.capability_valid is True
        assert result.policy_allowed is True  # Policy technisch toegestaan
        assert result.requires_approval is True
        assert result.violation_type == "APPROVAL_REQUIRED"
        assert result.approval_requirement is not None
        assert result.approval_requirement.amount == Decimal("1500")
        assert "manager" in result.approval_requirement.approver_roles

    def test_check_execute_permission_approval_not_required(
        self, registry: CapabilityRegistry, pro_policy: TenantPolicy
    ) -> None:
        """Happy path: Bedrag onder threshold, geen approval nodig."""
        enforcer = PolicyEnforcer(registry)
        node: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "capability_key": "payment_process",
            "input": {"amount": 500, "currency": "EUR"},
        }

        result = enforcer.check_execute_permission(node, pro_policy)

        assert result.can_execute is True
        assert result.requires_approval is False
        assert result.approval_requirement is None

    def test_enforcement_result_is_blocked(self) -> None:
        """Happy path: is_blocked property."""
        result = EnforcementResult(
            can_execute=False,
            capability_valid=True,
            policy_allowed=False,
            reason="Not enabled",
            violation_type="CAPABILITY_NOT_ENABLED",
        )

        assert result.is_blocked is True
        assert result.is_pending_approval is False

    def test_enforcement_result_is_pending_approval(
        self, registry: CapabilityRegistry, pro_policy: TenantPolicy
    ) -> None:
        """Happy path: is_pending_approval property."""
        enforcer = PolicyEnforcer(registry)
        node: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "capability_key": "payment_process",
            "input": {"amount": 1500, "currency": "EUR"},
        }

        result = enforcer.check_execute_permission(node, pro_policy)

        assert result.is_blocked is False
        assert result.is_pending_approval is True

    def test_enforcement_result_to_dict(
        self, registry: CapabilityRegistry, pro_policy: TenantPolicy
    ) -> None:
        """Happy path: Serialize result to dict."""
        enforcer = PolicyEnforcer(registry)
        node: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "capability_key": "payment_process",
            "input": {"amount": 1500, "currency": "EUR"},
        }

        result = enforcer.check_execute_permission(node, pro_policy)
        data = result.to_dict()

        assert data["can_execute"] is False
        assert data["requires_approval"] is True
        assert data["approval_requirement"]["capability_key"] == "payment_process"
        assert data["approval_requirement"]["amount"] == "1500"


class TestWorkflowPermissions:
    """Test workflow-level permission checks."""

    def test_check_workflow_permissions_all_allowed(
        self, registry: CapabilityRegistry, starter_policy: TenantPolicy
    ) -> None:
        """Happy path: Alle nodes allowed."""
        enforcer = PolicyEnforcer(registry)
        workflow: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "nodes": [
                {"id": "node-1", "capability_key": "crm_createcontact", "input": {"name": "Alice"}},
                {
                    "id": "node-2",
                    "capability_key": "email_send",
                    "input": {"to": "a@b.com", "subject": "Hi", "body": "Hello"},
                },
            ]
        }

        results = enforcer.check_workflow_permissions(workflow, starter_policy)

        assert len(results) == 2
        assert all(r.can_execute for r in results.values())

    def test_check_workflow_permissions_mixed(
        self, registry: CapabilityRegistry, starter_policy: TenantPolicy
    ) -> None:
        """Happy path: Sommige nodes blocked."""
        enforcer = PolicyEnforcer(registry)
        workflow: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "nodes": [
                {"id": "node-1", "capability_key": "crm_createcontact", "input": {"name": "Alice"}},
                {"id": "node-2", "capability_key": "payment_process", "input": {"amount": 100}},
            ]
        }

        results = enforcer.check_workflow_permissions(workflow, starter_policy)

        assert results["node-1"].can_execute is True
        assert results["node-2"].can_execute is False
        assert results["node-2"].violation_type == "INVALID_INPUT"

    def test_get_blocked_capabilities(
        self, registry: CapabilityRegistry, starter_policy: TenantPolicy
    ) -> None:
        """Happy path: Get lijst van blocked capabilities."""
        enforcer = PolicyEnforcer(registry)
        workflow: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "nodes": [
                {"id": "node-1", "capability_key": "crm_createcontact", "input": {"name": "Alice"}},
                {"id": "node-2", "capability_key": "payment_process", "input": {"amount": 100}},
                {"id": "node-3", "capability_key": "unknown.cap", "input": {}},
            ]
        }

        blocked = enforcer.get_blocked_capabilities(workflow, starter_policy)

        assert len(blocked) == 2
        blocked_keys = {b["node_id"] for b in blocked}
        assert "node-2" in blocked_keys
        assert "node-3" in blocked_keys

    def test_get_pending_approvals(
        self, registry: CapabilityRegistry, pro_policy: TenantPolicy
    ) -> None:
        """Happy path: Get lijst van pending approvals."""
        enforcer = PolicyEnforcer(registry)
        workflow: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "nodes": [
                {"id": "node-1", "capability_key": "crm_createcontact", "input": {"name": "Alice"}},
                {
                    "id": "node-2",
                    "capability_key": "payment_process",
                    "input": {"amount": 1500, "currency": "EUR"},
                },
            ]
        }

        pending = enforcer.get_pending_approvals(workflow, pro_policy)

        assert len(pending) == 1
        assert pending[0]["node_id"] == "node-2"
        assert pending[0]["approval_requirement"].capability_key == "payment_process"

    def test_empty_workflow(
        self, registry: CapabilityRegistry, starter_policy: TenantPolicy
    ) -> None:
        """Edge case: Workflow zonder nodes."""
        enforcer = PolicyEnforcer(registry)
        workflow: dict[str, Any] = {"nodes": []}  # TODO(TYPE): replace Any with concrete type

        results = enforcer.check_workflow_permissions(workflow, starter_policy)

        assert results == {}

    def test_workflow_without_nodes_key(
        self, registry: CapabilityRegistry, starter_policy: TenantPolicy
    ) -> None:
        """Edge case: Workflow zonder 'nodes' key."""
        enforcer = PolicyEnforcer(registry)
        workflow: dict[str, Any] = {"name": "My Workflow"}  # TODO(TYPE): replace Any with concrete type

        results = enforcer.check_workflow_permissions(workflow, starter_policy)

        assert "_workflow" in results
        assert results["_workflow"].violation_type == "INVALID_WORKFLOW"


class TestConvenienceFunctions:
    """Test convenience functies."""

    def test_can_execute_capability_true(
        self, registry: CapabilityRegistry, starter_policy: TenantPolicy
    ) -> None:
        """Happy path: can_execute_capability returns True."""
        result = can_execute_capability(
            "crm_createcontact", {"name": "Alice"}, starter_policy, registry
        )

        assert result is True

    def test_can_execute_capability_false(
        self, registry: CapabilityRegistry, starter_policy: TenantPolicy
    ) -> None:
        """Happy path: can_execute_capability returns False."""
        result = can_execute_capability(
            "payment_process", {"amount": 100}, starter_policy, registry
        )

        assert result is False

    def test_require_approval_for_over_threshold(self, pro_policy: TenantPolicy) -> None:
        """Happy path: require_approval_for returns requirement."""
        from core.contracts.policy import ApprovalRequirement

        result: ApprovalRequirement | None = require_approval_for(
            "payment_process", Decimal("1500.00"), pro_policy
        )

        assert result is not None
        assert result.capability_key == "payment_process"
        assert result.amount == Decimal("1500.00")

    def test_require_approval_for_under_threshold(self, pro_policy: TenantPolicy) -> None:
        """Happy path: require_approval_for returns None."""
        from core.contracts.policy import ApprovalRequirement

        result: ApprovalRequirement | None = require_approval_for(
            "payment_process", Decimal("500.00"), pro_policy
        )

        assert result is None


class TestTierSuggestion:
    """Test tier suggestion logica."""

    def test_suggest_tier_for_known_capability_not_enabled(
        self, registry: CapabilityRegistry
    ) -> None:
        """Happy path: Known capability not enabled suggereert tier."""
        enforcer = PolicyEnforcer(registry)
        # Create policy zonder payment_process (die wel in registry zit)
        policy = TenantPolicy(
            tenant_id="test",
            plan_tier=PlanTier.STARTER,
            enabled_capabilities={"crm_createcontact"},  # Only enable one
        )

        node: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "capability_key": "payment_process",
            "input": {"amount": 100, "currency": "EUR"},
        }

        result = enforcer.check_execute_permission(node, policy)

        # Should be CAPABILITY_NOT_ENABLED with suggested_tier
        assert result.can_execute is False
        assert result.violation_type == "CAPABILITY_NOT_ENABLED"
        assert "suggested_tier" in result.execution_context
        # payment_process is medium/high value, suggests pro
        assert result.execution_context["suggested_tier"] == "pro"

    def test_suggest_tier_for_basic_capability(self, registry: CapabilityRegistry) -> None:
        """Happy path: Basic capability suggereert Starter."""
        enforcer = PolicyEnforcer(registry)
        # Create policy zonder email_send (die wel in registry zit)
        policy = TenantPolicy(
            tenant_id="test",
            plan_tier=PlanTier.STARTER,
            enabled_capabilities={"crm_createcontact"},  # Only enable one
        )

        node: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "capability_key": "email_send",
            "input": {"to": "test@test.com", "subject": "Test", "body": "Hello"},
        }

        result = enforcer.check_execute_permission(node, policy)

        # Should be CAPABILITY_NOT_ENABLED with suggested_tier
        assert result.can_execute is False
        assert result.violation_type == "CAPABILITY_NOT_ENABLED"
        assert "suggested_tier" in result.execution_context
        # email_send is basic value, suggests starter
        assert result.execution_context["suggested_tier"] == "starter"
