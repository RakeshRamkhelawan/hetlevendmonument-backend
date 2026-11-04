"""
Policy Enforcement

Runtime enforcement van tenant policies bij capability execution.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, cast

from .capability import CapabilityRegistry, CapabilityResolver, UnknownCapabilityError
from .policy import ApprovalRequirement, PlanTier, PolicyCheckResult, TenantPolicy


class EnforcementResult:
    """
    Compleet resultaat van policy enforcement check.

    Bevat zowel capability validatie als policy checks.
    """

    def __init__(
        self,
        can_execute: bool,
        capability_valid: bool,
        policy_allowed: bool,
        reason: str | None = None,
        violation_type: str | None = None,
        requires_approval: bool = False,
        approval_requirement: ApprovalRequirement | None = None,
        execution_context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self.can_execute = can_execute
        self.capability_valid = capability_valid
        self.policy_allowed = policy_allowed
        self.reason = reason
        self.violation_type = violation_type
        self.requires_approval = requires_approval
        self.approval_requirement = approval_requirement
        self.execution_context = execution_context or {}

    @property
    def is_blocked(self) -> bool:
        """Of execution geblokkeerd is (niet toegestaan en geen approval pending)."""
        return not self.can_execute and not self.requires_approval

    @property
    def is_pending_approval(self) -> bool:
        """Of execution wacht op approval."""
        return self.requires_approval and not self.can_execute

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert naar dictionary voor logging/serialisatie."""
        return {
            "can_execute": self.can_execute,
            "capability_valid": self.capability_valid,
            "policy_allowed": self.policy_allowed,
            "reason": self.reason,
            "violation_type": self.violation_type,
            "requires_approval": self.requires_approval,
            "approval_requirement": (
                {
                    "capability_key": self.approval_requirement.capability_key,
                    "amount": (
                        str(self.approval_requirement.amount)
                        if self.approval_requirement.amount
                        else None
                    ),
                    "approver_roles": list(self.approval_requirement.approver_roles),
                    "reason": self.approval_requirement.reason,
                }
                if self.approval_requirement
                else None
            ),
        }


class PolicyEnforcer:
    """
    Enforces tenant policies op workflow execution.

    Combinatie van:
    - Capability resolutie (is de capability geldig?)
    - Policy checks (mag de tenant deze capability gebruiken?)
    - Approval checks (is approval nodig?)
    """

    def __init__(self, capability_registry: CapabilityRegistry) -> None:
        self.registry = capability_registry
        self.resolver = CapabilityResolver(capability_registry)

    def check_execute_permission(
        self, node: dict[str, Any], policy: TenantPolicy  # TODO(TYPE): replace Any with concrete type
    ) -> EnforcementResult:
        """
        Check of een node uitgevoerd mag worden volgens policy.

        Args:
            node: Workflow node met capability_key en input
            policy: Tenant policy om tegen te checken

        Returns:
            EnforcementResult met complete status
        """
        capability_key: str | None = node.get("capability_key")
        input_data: dict[str, Any] = node.get("input", {})  # TODO(TYPE): replace Any with concrete type

        # Type check voor capability_key
        if capability_key is None or not isinstance(capability_key, str):
            return EnforcementResult(
                can_execute=False,
                capability_valid=False,
                policy_allowed=False,
                reason="Missing or invalid capability_key in node",
                violation_type="INVALID_NODE",
            )

        # Stap 1: Capability resolutie
        try:
            capability = self.registry.resolve(capability_key)
        except UnknownCapabilityError:
            return EnforcementResult(
                can_execute=False,
                capability_valid=False,
                policy_allowed=False,
                reason=f"Unknown capability: '{capability_key}'",
                violation_type="UNKNOWN_CAPABILITY",
            )

        # Stap 2: Input validatie
        validation_result = self.resolver.validate_node(node)
        if not validation_result.is_valid:
            return EnforcementResult(
                can_execute=False,
                capability_valid=True,  # Capability bestaat, input is invalid
                policy_allowed=False,
                reason=f"Invalid input: {'; '.join(validation_result.errors)}",
                violation_type="INVALID_INPUT",
            )

        # Stap 3: Policy check - is capability enabled?
        if not policy.is_capability_enabled(capability_key):
            # Bepaal suggested tier
            suggested_tier = self._suggest_tier_for_capability(capability_key)

            return EnforcementResult(
                can_execute=False,
                capability_valid=True,
                policy_allowed=False,
                reason=f"Capability '{capability_key}' is not enabled in your plan ({policy.plan_tier.value})",
                violation_type="CAPABILITY_NOT_ENABLED",
                execution_context={
                    "suggested_tier": suggested_tier.value if suggested_tier else None
                },
            )

        # Stap 4: Approval check
        approval_req = policy.check_approval_required(capability_key, input_data)
        if approval_req:
            return EnforcementResult(
                can_execute=False,  # Nog niet toestaan, wacht op approval
                capability_valid=True,
                policy_allowed=True,  # Policy technisch toegestaan, maar approval nodig
                reason=f"Approval required: {approval_req.reason}",
                violation_type="APPROVAL_REQUIRED",
                requires_approval=True,
                approval_requirement=approval_req,
                execution_context={
                    "approver_roles": list(approval_req.approver_roles),
                    "auto_approve_after_ms": approval_req.auto_approve_after_ms,
                },
            )

        # Stap 5: Alle checks geslaagd!
        return EnforcementResult(
            can_execute=True,
            capability_valid=True,
            policy_allowed=True,
            execution_context={
                "capability_key": capability_key,
                "plan_tier": policy.plan_tier.value,
                "compliance_profile": policy.compliance_profile.value,
            },
        )

    def check_workflow_permissions(
        self, workflow: dict[str, Any], policy: TenantPolicy  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, EnforcementResult]:
        """
        Check alle nodes in een workflow.

        Returns: Dict[str, Any] mapping node_id -> EnforcementResult  # TODO(TYPE): replace Any with concrete type
        """
        results: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        if "nodes" not in workflow:
            return {
                "_workflow": EnforcementResult(
                    can_execute=False,
                    capability_valid=False,
                    policy_allowed=False,
                    reason="Workflow has no nodes",
                    violation_type="INVALID_WORKFLOW",
                )
            }

        for node in workflow["nodes"]:
            node_id = str(node.get("id", "unknown"))
            results[node_id] = self.check_execute_permission(node, policy)

        return results

    def get_blocked_capabilities(self, workflow: dict[str, Any], policy: TenantPolicy) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Get lijst van capabilities die geblokkeerd zijn."""
        blocked: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        results = self.check_workflow_permissions(workflow, policy)

        for node_id, result in results.items():
            if result.is_blocked:
                blocked.append(
                    {
                        "node_id": node_id,
                        "reason": result.reason,
                        "violation_type": result.violation_type,
                    }
                )

        return blocked

    def get_pending_approvals(self, workflow: dict[str, Any], policy: TenantPolicy) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Get lijst van capabilities die approval pending zijn."""
        pending: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        results = self.check_workflow_permissions(workflow, policy)

        for node_id, result in results.items():
            if result.is_pending_approval:
                pending.append(
                    {
                        "node_id": node_id,
                        "approval_requirement": result.approval_requirement,
                    }
                )

        return pending

    def _suggest_tier_for_capability(self, capability_key: str) -> PlanTier | None:
        """
        Suggesteer een plan tier voor een capability.

        Dit is een simplified mapping - in productie zou dit uit een database komen.
        """
        # High-value capabilities -> Pro/Enterprise
        high_value = {
            "process_payment",
            "payment_process",
            "delete_data",
            "export_bulk",
            "api_access",
        }
        # Medium-value -> Basic/Pro
        medium_value = {"send_sms", "advanced_reporting", "webhook"}

        if capability_key in high_value:
            return PlanTier.PRO
        elif capability_key in medium_value:
            return PlanTier.BASIC
        else:
            return PlanTier.STARTER


# Convenience functies voor common checks


def can_execute_capability(
    capability_key: str,
    input_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    policy: TenantPolicy,
    registry: CapabilityRegistry,
) -> bool:
    """Quick check: mag deze capability uitgevoerd worden?"""
    enforcer = PolicyEnforcer(registry)
    node = {"capability_key": capability_key, "input": input_data}
    result = enforcer.check_execute_permission(node, policy)
    return result.can_execute


def require_approval_for(
    capability_key: str, amount: Decimal, policy: TenantPolicy
) -> ApprovalRequirement | None:
    """Quick check: is approval vereist voor dit bedrag?"""
    input_data = {"amount": amount}
    return policy.check_approval_required(capability_key, input_data)
