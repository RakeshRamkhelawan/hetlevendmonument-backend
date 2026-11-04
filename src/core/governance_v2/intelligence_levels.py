"""
TKT-F3-01: Intelligence Levels Enforcement

Implements intelligence levels: autonomous, approval-required, restricted.
Threshold rules based on action type + plan tier.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Set, Tuple, cast
from collections.abc import Callable
from re import Pattern


class IntelligenceLevel(Enum):
    """Intelligence level for action execution"""

    AUTONOMOUS = "autonomous"  # Direct execution
    APPROVAL_REQUIRED = "approval_required"  # Needs explicit approval
    RESTRICTED = "restricted"  # Blocked, requires manual override


class ActionRiskLevel(Enum):
    """Risk level of an action"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PlanTier(Enum):
    """Plan tier for tenant"""

    STARTER = "starter"
    GROWTH = "growth"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass
class ActionType:
    """Definition of an action type"""

    action_key: str
    name: str
    description: str
    default_risk: ActionRiskLevel
    category: str  # e.g., "financial", "data", "communication"


@dataclass
class IntelligenceDecision:
    """Decision from intelligence level enforcement"""

    decision_id: str
    tenant_id: str
    action_key: str
    intelligence_level: IntelligenceLevel
    risk_level: ActionRiskLevel
    plan_tier: PlanTier
    allowed: bool
    reasoning: str
    requires_approval: bool
    approver_roles: list[str] = field(default_factory=list)
    blocked_reason: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize to dictionary"""
        return {
            "decision_id": self.decision_id,
            "tenant_id": self.tenant_id,
            "action_key": self.action_key,
            "intelligence_level": self.intelligence_level.value,
            "risk_level": self.risk_level.value,
            "plan_tier": self.plan_tier.value,
            "allowed": self.allowed,
            "reasoning": self.reasoning,
            "requires_approval": self.requires_approval,
            "approver_roles": self.approver_roles,
            "blocked_reason": self.blocked_reason,
            "timestamp": self.timestamp.isoformat(),
        }


class IntelligenceEnforcer:
    """
    Enforces intelligence levels on actions.

    Rules:
    - LOW risk: Autonomous execution
    - MEDIUM risk: Autonomous for Pro/Growth, Approval for Starter
    - HIGH risk: Approval required for all tiers
    - CRITICAL risk: Restricted for Starter, Approval for others

    Usage:
        enforcer = IntelligenceEnforcer()
        enforcer.register_action("payment.process", ActionRiskLevel.HIGH)

        decision = enforcer.evaluate(
            tenant_id="tenant-123",
            action_key="payment.process",
            plan_tier=PlanTier.GROWTH,
            context={"amount": 5000}
        )

        if not decision.allowed:
            handle_blocked(decision)
        elif decision.requires_approval:
            queue_for_approval(decision)
        else:
            execute_action()
    """

    # Risk threshold mapping: (risk_level_value, plan_tier_value) -> intelligence_level_value
    DEFAULT_RULES = {
        # LOW risk: Always autonomous
        ("low", "starter"): "autonomous",
        ("low", "growth"): "autonomous",
        ("low", "pro"): "autonomous",
        ("low", "enterprise"): "autonomous",
        # MEDIUM risk: Starter needs approval
        ("medium", "starter"): "approval_required",
        ("medium", "growth"): "autonomous",
        ("medium", "pro"): "autonomous",
        ("medium", "enterprise"): "autonomous",
        # HIGH risk: All need approval
        ("high", "starter"): "approval_required",
        ("high", "growth"): "approval_required",
        ("high", "pro"): "approval_required",
        ("high", "enterprise"): "approval_required",
        # CRITICAL risk: Starter blocked, others need approval
        ("critical", "starter"): "restricted",
        ("critical", "growth"): "approval_required",
        ("critical", "pro"): "approval_required",
        ("critical", "enterprise"): "autonomous",
    }

    # Approver roles per risk level
    APPROVER_ROLES = {
        ActionRiskLevel.MEDIUM: ["manager"],
        ActionRiskLevel.HIGH: ["manager", "admin"],
        ActionRiskLevel.CRITICAL: ["admin", "compliance_officer"],
    }

    def __init__(self) -> None:
        self._actions: dict[str, ActionType] = {}
        self._rules: dict[tuple[str, str], str] = self.DEFAULT_RULES.copy()
        self._decisions: list[IntelligenceDecision] = []
        self._context_thresholds: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

    def _lookup_rule(self, lookup_key: tuple[str, str]) -> str:
        """Lookup intelligence level by (risk_value, tier_value) tuple"""
        return self._rules.get(lookup_key, "approval_required")  # Default safe

    def register_action(
        self,
        action_key: str,
        risk_level: ActionRiskLevel,
        name: str = "",
        description: str = "",
        category: str = "general",
    ) -> None:
        """Register an action type with its risk level"""
        self._actions[action_key] = ActionType(
            action_key=action_key,
            name=name or action_key,
            description=description,
            default_risk=risk_level,
            category=category,
        )

    def set_context_threshold(
        self,
        action_key: str,
        threshold_key: str,
        threshold_value: Any,  # TODO(TYPE): replace Any with concrete type
        elevated_risk: ActionRiskLevel,
    ) -> None:
        """
        Set context-aware thresholds that can elevate risk.

        Example:
            set_context_threshold("payment.process", "amount", 10000, ActionRiskLevel.CRITICAL)
        """
        if action_key not in self._context_thresholds:
            self._context_thresholds[action_key] = {}
        self._context_thresholds[action_key][threshold_key] = {
            "threshold": threshold_value,
            "elevated_risk": elevated_risk,
        }

    def evaluate(
        self,
        tenant_id: str,
        action_key: str,
        plan_tier: PlanTier,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> IntelligenceDecision:
        """
        Evaluate if an action is allowed under intelligence levels.

        Args:
            tenant_id: Tenant identifier
            action_key: The action to evaluate
            plan_tier: Tenant's plan tier
            context: Additional context (e.g., amount, sensitivity)

        Returns:
            IntelligenceDecision with allowance and requirements
        """
        decision_id = str(uuid.uuid4())
        context = context or {}

        # Get action definition
        action = self._actions.get(action_key)
        if not action:
            decision = IntelligenceDecision(
                decision_id=decision_id,
                tenant_id=tenant_id,
                action_key=action_key,
                intelligence_level=IntelligenceLevel.RESTRICTED,
                risk_level=ActionRiskLevel.CRITICAL,
                plan_tier=plan_tier,
                allowed=False,
                reasoning=f"Unknown action type: {action_key}",
                requires_approval=False,
                blocked_reason="Action not registered",
            )
            self._decisions.append(decision)
            return decision

        # Determine risk level with context
        risk_level = self._determine_risk_level(action_key, action.default_risk, context)

        # Get intelligence level from rules using string values for lookup
        lookup_key = (risk_level.value, plan_tier.value)
        intelligence_level_value = self._lookup_rule(lookup_key)
        intelligence_level = IntelligenceLevel(intelligence_level_value)

        # Build decision
        if intelligence_level == IntelligenceLevel.RESTRICTED:
            decision = IntelligenceDecision(
                decision_id=decision_id,
                tenant_id=tenant_id,
                action_key=action_key,
                intelligence_level=intelligence_level,
                risk_level=risk_level,
                plan_tier=plan_tier,
                allowed=False,
                reasoning=f"Action restricted for {plan_tier.value} tier",
                requires_approval=False,
                blocked_reason=f"{action_key} requires higher plan tier",
            )
        elif intelligence_level == IntelligenceLevel.APPROVAL_REQUIRED:
            approver_roles = self.APPROVER_ROLES.get(risk_level, ["admin"])
            decision = IntelligenceDecision(
                decision_id=decision_id,
                tenant_id=tenant_id,
                action_key=action_key,
                intelligence_level=intelligence_level,
                risk_level=risk_level,
                plan_tier=plan_tier,
                allowed=True,
                reasoning=f"{risk_level.value} risk action requires approval",
                requires_approval=True,
                approver_roles=approver_roles,
            )
        else:  # AUTONOMOUS
            decision = IntelligenceDecision(
                decision_id=decision_id,
                tenant_id=tenant_id,
                action_key=action_key,
                intelligence_level=intelligence_level,
                risk_level=risk_level,
                plan_tier=plan_tier,
                allowed=True,
                reasoning=f"{risk_level.value} risk action allowed for {plan_tier.value}",
                requires_approval=False,
            )

        self._decisions.append(decision)
        return decision

    def _determine_risk_level(
        self, action_key: str, base_risk: ActionRiskLevel, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> ActionRiskLevel:
        """Determine final risk level considering context thresholds"""
        thresholds = self._context_thresholds.get(action_key, {})

        for key, config in thresholds.items():
            if key in context:
                value = context[key]
                threshold = config["threshold"]

                # Numeric comparison
                if isinstance(value, (int, float)) and isinstance(threshold, (int, float)):
                    if value >= threshold:
                        elevated: ActionRiskLevel = config["elevated_risk"]
                        return elevated
                # String/other equality
                elif value == threshold:
                    elevated = config["elevated_risk"]
                    return elevated

        return base_risk

    def get_decisions(self, tenant_id: str | None = None) -> list[IntelligenceDecision]:
        """Get decision history"""
        if tenant_id:
            return [d for d in self._decisions if d.tenant_id == tenant_id]
        return self._decisions.copy()

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get enforcement statistics"""
        total = len(self._decisions)
        if total == 0:
            return {"total": 0}

        autonomous = sum(
            1 for d in self._decisions if d.intelligence_level == IntelligenceLevel.AUTONOMOUS
        )
        approval_required = sum(
            1
            for d in self._decisions
            if d.intelligence_level == IntelligenceLevel.APPROVAL_REQUIRED
        )
        restricted = sum(
            1 for d in self._decisions if d.intelligence_level == IntelligenceLevel.RESTRICTED
        )

        return {
            "total": total,
            "autonomous": autonomous,
            "approval_required": approval_required,
            "restricted": restricted,
            "blocked": sum(1 for d in self._decisions if not d.allowed),
        }
