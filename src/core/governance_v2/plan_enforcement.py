"""
TKT-F3-03: Starter/Growth/Pro Enforcement

Implements plan enforcement across UI, API, and runtime.
Capability gating, usage thresholds, overage eventing.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from collections.abc import Callable


class PlanTier(Enum):
    """Subscription plan tiers"""

    STARTER = "starter"
    GROWTH = "growth"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class OverageAction(Enum):
    """Action to take on overage"""

    WARN = "warn"
    BLOCK = "block"
    UPGRADE_PROMPT = "upgrade_prompt"
    AUTO_UPGRADE = "auto_upgrade"


@dataclass
class CapabilityGate:
    """Gate for a specific capability"""

    capability_key: str
    allowed_tiers: set[PlanTier]
    requires_approval: list[PlanTier] = field(default_factory=list)

    def is_allowed(self, tier: PlanTier) -> bool:
        """Check if tier can use this capability"""
        return tier in self.allowed_tiers

    def requires_approval_for(self, tier: PlanTier) -> bool:
        """Check if tier requires approval"""
        return tier in self.requires_approval


@dataclass
class UsageThreshold:
    """Usage threshold for a metric"""

    metric_name: str
    starter_limit: int
    growth_limit: int
    pro_limit: int
    enterprise_limit: int = 999999999

    def get_limit(self, tier: PlanTier) -> int:
        """Get limit for tier"""
        limits = {
            PlanTier.STARTER: self.starter_limit,
            PlanTier.GROWTH: self.growth_limit,
            PlanTier.PRO: self.pro_limit,
            PlanTier.ENTERPRISE: self.enterprise_limit,
        }
        return limits.get(tier, 0)

    def check_overage(self, tier: PlanTier, current_usage: int) -> tuple[bool, int]:
        """Check if usage exceeds limit. Returns (is_overage, overage_amount)"""
        limit = self.get_limit(tier)
        if current_usage > limit:
            return True, current_usage - limit
        return False, 0


@dataclass
class OverageEvent:
    """Event when usage exceeds threshold"""

    event_id: str
    tenant_id: str
    plan_tier: PlanTier
    metric_name: str
    threshold: int
    current_usage: int
    overage_amount: int
    action_taken: OverageAction
    timestamp: datetime
    acknowledged: bool = False

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "plan_tier": self.plan_tier.value,
            "metric_name": self.metric_name,
            "threshold": self.threshold,
            "current_usage": self.current_usage,
            "overage_amount": self.overage_amount,
            "action_taken": self.action_taken.value,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged": self.acknowledged,
        }


@dataclass
class PlanDecision:
    """Decision from plan enforcement"""

    decision_id: str
    tenant_id: str
    capability_key: str
    plan_tier: PlanTier
    allowed: bool
    blocked: bool
    requires_approval: bool
    reasoning: str
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "decision_id": self.decision_id,
            "tenant_id": self.tenant_id,
            "capability_key": self.capability_key,
            "plan_tier": self.plan_tier.value,
            "allowed": self.allowed,
            "blocked": self.blocked,
            "requires_approval": self.requires_approval,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp.isoformat(),
        }


class PlanEnforcer:
    """
    Enforces plan tier restrictions across all layers.

    Features:
    - Capability gating by tier
    - Usage threshold enforcement
    - Overage eventing and workflows
    - Consistent enforcement UI/API/Runtime

    Usage:
        enforcer = PlanEnforcer()

        # Register capabilities
        enforcer.register_capability(
            "ai.generate",
            allowed_tiers={PlanTier.GROWTH, PlanTier.PRO},
            requires_approval=[PlanTier.GROWTH]
        )

        # Check capability
        decision = enforcer.check_capability("tenant-123", "ai.generate", PlanTier.STARTER)
        if decision.blocked:
            show_upgrade_prompt()
    """

    # Default plan limits
    DEFAULT_LIMITS = {
        "workflows": UsageThreshold("workflows", 5, 25, 100),
        "executions_per_month": UsageThreshold("executions_per_month", 1000, 10000, 100000),
        "storage_mb": UsageThreshold("storage_mb", 100, 1000, 10000),
        "team_members": UsageThreshold("team_members", 3, 10, 50),
        "api_calls_per_minute": UsageThreshold("api_calls_per_minute", 10, 100, 1000),
    }

    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityGate] = {}
        self._thresholds: dict[str, UsageThreshold] = self.DEFAULT_LIMITS.copy()
        self._usage: dict[str, dict[str, int]] = {}  # tenant_id -> {metric: usage}
        self._decisions: list[PlanDecision] = []
        self._overage_events: list[OverageEvent] = []
        self._overage_handlers: list[Callable[..., Any]] = []  # TODO(TYPE): replace Any with concrete type

    def register_capability(
        self,
        capability_key: str,
        allowed_tiers: set[PlanTier],
        requires_approval: list[PlanTier] | None = None,
    ) -> None:
        """
        Register a capability with tier restrictions.

        Args:
            capability_key: The capability
            allowed_tiers: Which tiers can use this
            requires_approval: Tiers that need approval
        """
        self._capabilities[capability_key] = CapabilityGate(
            capability_key=capability_key,
            allowed_tiers=allowed_tiers,
            requires_approval=requires_approval or [],
        )

    def check_capability(self, tenant_id: str, capability_key: str, tier: PlanTier) -> PlanDecision:
        """
        Check if a capability is allowed for a tenant.

        Args:
            tenant_id: Tenant identifier
            capability_key: Capability to check
            tier: Tenant's plan tier

        Returns:
            PlanDecision with allowance status
        """
        decision_id = str(uuid.uuid4())

        gate = self._capabilities.get(capability_key)
        if not gate:
            # Unknown capability - allow but warn
            decision = PlanDecision(
                decision_id=decision_id,
                tenant_id=tenant_id,
                capability_key=capability_key,
                plan_tier=tier,
                allowed=True,
                blocked=False,
                requires_approval=False,
                reasoning="Capability not registered, allowing by default",
                timestamp=datetime.now(timezone.utc),
            )
            self._decisions.append(decision)
            return decision

        # Check tier allowance
        if not gate.is_allowed(tier):
            decision = PlanDecision(
                decision_id=decision_id,
                tenant_id=tenant_id,
                capability_key=capability_key,
                plan_tier=tier,
                allowed=False,
                blocked=True,
                requires_approval=False,
                reasoning=f"Capability '{capability_key}' not available in {tier.value} plan",
                timestamp=datetime.now(timezone.utc),
            )
            self._decisions.append(decision)
            return decision

        # Check if approval required
        if gate.requires_approval_for(tier):
            decision = PlanDecision(
                decision_id=decision_id,
                tenant_id=tenant_id,
                capability_key=capability_key,
                plan_tier=tier,
                allowed=True,
                blocked=False,
                requires_approval=True,
                reasoning=f"Capability '{capability_key}' requires approval for {tier.value} plan",
                timestamp=datetime.now(timezone.utc),
            )
            self._decisions.append(decision)
            return decision

        # Allowed without restrictions
        decision = PlanDecision(
            decision_id=decision_id,
            tenant_id=tenant_id,
            capability_key=capability_key,
            plan_tier=tier,
            allowed=True,
            blocked=False,
            requires_approval=False,
            reasoning=f"Capability '{capability_key}' allowed for {tier.value} plan",
            timestamp=datetime.now(timezone.utc),
        )
        self._decisions.append(decision)
        return decision

    def record_usage(self, tenant_id: str, metric_name: str, amount: int = 1) -> None:
        """
        Record usage for a tenant.

        Args:
            tenant_id: Tenant identifier
            metric_name: Metric being used
            amount: Amount to add (default 1)
        """
        if tenant_id not in self._usage:
            self._usage[tenant_id] = {}

        current = self._usage[tenant_id].get(metric_name, 0)
        self._usage[tenant_id][metric_name] = current + amount

    def check_usage(
        self, tenant_id: str, tier: PlanTier, metric_name: str
    ) -> tuple[bool, int, int]:
        """
        Check if tenant is within usage limits.

        Args:
            tenant_id: Tenant identifier
            tier: Tenant's plan tier
            metric_name: Metric to check

        Returns: Tuple[Any, ...] of (within_limit, current_usage, limit)  # TODO(TYPE): replace Any with concrete type
        """
        threshold = self._thresholds.get(metric_name)
        if not threshold:
            # No limit defined
            return True, 0, 0

        current_usage = self._usage.get(tenant_id, {}).get(metric_name, 0)
        limit = threshold.get_limit(tier)

        return current_usage <= limit, current_usage, limit

    def check_and_handle_overage(
        self, tenant_id: str, tier: PlanTier, metric_name: str
    ) -> OverageEvent | None:
        """
        Check for overage and trigger event if exceeded.

        Args:
            tenant_id: Tenant identifier
            tier: Tenant's plan tier
            metric_name: Metric to check

        Returns:
            OverageEvent if overage detected, None otherwise
        """
        threshold = self._thresholds.get(metric_name)
        if not threshold:
            return None

        current_usage = self._usage.get(tenant_id, {}).get(metric_name, 0)
        is_overage, overage_amount = threshold.check_overage(tier, current_usage)

        if not is_overage:
            return None

        # Determine action based on overage severity
        action = self._determine_overage_action(tier, metric_name, overage_amount)

        # Create event
        event = OverageEvent(
            event_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            plan_tier=tier,
            metric_name=metric_name,
            threshold=threshold.get_limit(tier),
            current_usage=current_usage,
            overage_amount=overage_amount,
            action_taken=action,
            timestamp=datetime.now(timezone.utc),
        )

        self._overage_events.append(event)

        # Notify handlers
        for handler in self._overage_handlers:
            try:
                handler(event)
            except Exception:
                pass

        return event

    def _determine_overage_action(self, tier: PlanTier, metric: str, overage: int) -> OverageAction:
        """Determine what action to take on overage"""
        # Small overage: warn
        if overage < 10:
            return OverageAction.WARN

        # Medium overage: block for starter, warn for others
        if overage < 100:
            return OverageAction.BLOCK if tier == PlanTier.STARTER else OverageAction.WARN

        # Large overage: prompt upgrade
        return OverageAction.UPGRADE_PROMPT

    def register_overage_handler(self, handler: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Register handler for overage events"""
        self._overage_handlers.append(handler)

    def get_usage(self, tenant_id: str) -> dict[str, int]:
        """Get usage for tenant"""
        return self._usage.get(tenant_id, {}).copy()

    def get_overage_events(
        self, tenant_id: str | None = None, acknowledged: bool | None = None
    ) -> list[OverageEvent]:
        """Get overage events with filtering"""
        events = self._overage_events

        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]

        if acknowledged is not None:
            events = [e for e in events if e.acknowledged == acknowledged]

        return events

    def acknowledge_overage(self, event_id: str) -> bool:
        """Acknowledge an overage event"""
        for event in self._overage_events:
            if event.event_id == event_id:
                event.acknowledged = True
                return True
        return False

    def get_decisions(self, tenant_id: str | None = None) -> list[PlanDecision]:
        """Get plan decisions"""
        if tenant_id:
            return [d for d in self._decisions if d.tenant_id == tenant_id]
        return self._decisions.copy()

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get enforcement statistics"""
        total_decisions = len(self._decisions)
        blocked = sum(1 for d in self._decisions if d.blocked)
        approved = sum(1 for d in self._decisions if d.requires_approval)

        return {
            "total_decisions": total_decisions,
            "blocked": blocked,
            "requires_approval": approved,
            "allowed": total_decisions - blocked,
            "overage_events": len(self._overage_events),
            "unacknowledged_overage": sum(1 for e in self._overage_events if not e.acknowledged),
        }
