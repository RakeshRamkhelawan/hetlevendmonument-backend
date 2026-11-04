"""
Tenant Policy Contract

Implementeert tenant policy enforcement voor capability execution.
Beheert plan tiers, enabled capabilities, approval thresholds en compliance.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field, root_validator, validator


class PlanTier(str, Enum):
    """Subscription plan tiers."""

    STARTER = "starter"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class ComplianceProfile(str, Enum):
    """Compliance profile voor data handling en retentie."""

    BASIC = "basic"
    GDPR = "gdpr"
    HIPAA = "hipaa"
    SOX = "sox"

    @property
    def requires_data_residency(self) -> bool:
        """Of data in specifieke regio moet blijven."""
        return self in {ComplianceProfile.GDPR, ComplianceProfile.HIPAA}

    @property
    def requires_explicit_consent(self) -> bool:
        """Of explicit consent nodig is voor data processing."""
        return self in {ComplianceProfile.GDPR}

    @property
    def retention_days(self) -> int:
        """Default retention period in dagen."""
        retention_map = {
            ComplianceProfile.BASIC: 365,  # 1 jaar
            ComplianceProfile.GDPR: 365,  # 1 jaar (max per audit policy) (belasting)
            ComplianceProfile.HIPAA: 2555,  # 7 jaar
            ComplianceProfile.SOX: 2555,  # 7 jaar
        }
        return retention_map.get(self, 365)

    @property
    def requires_audit_trail(self) -> bool:
        """Of complete audit trail vereist is."""
        return self in {ComplianceProfile.GDPR, ComplianceProfile.HIPAA, ComplianceProfile.SOX}


@dataclass(frozen=True)
class ApprovalThreshold:
    """
    Threshold voor wanneer approval vereist is.

    Bijvoorbeeld: payments > EUR1000 vereisen manager approval.
    """

    amount_threshold: Decimal
    requires_approval: bool = True
    approver_roles: set[str] = field(default_factory=set)
    auto_approve_after_ms: int | None = None  # Auto-approve na timeout
    escalation_roles: set[str] = field(default_factory=set)  # Escalatie na timeout

    def requires_approval_for(self, amount: Decimal) -> bool:
        """Check of approval vereist is voor gegeven bedrag."""
        if not self.requires_approval:
            return False
        return amount >= self.amount_threshold


@dataclass(frozen=True)
class ApprovalRequirement:
    """Geexporteerde approval requirement na policy check."""

    capability_key: str
    amount: Decimal | None
    approver_roles: set[str]
    reason: str
    auto_approve_after_ms: int | None = None


class TenantPolicy(BaseModel):
    """
    Policy configuratie voor een tenant.

    Definieert:
    - Welke capabilities enabled zijn (per plan tier)
    - Provider priority/fallback volgorde
    - Approval thresholds voor gevoelige acties
    - Compliance vereisten
    """

    tenant_id: str = Field(..., min_length=1, max_length=100)
    plan_tier: PlanTier

    # Enabled capabilities voor deze tenant
    enabled_capabilities: set[str] = Field(default_factory=set)

    # Provider priority per capability type
    # Bijvoorbeeld: {"email": ["sendgrid", "aws_ses", "mailgun"]}
    provider_priority: dict[str, list[str]] = Field(default_factory=dict)

    # Approval thresholds per capability
    # Bijvoordeeld: {"payment": ApprovalThreshold(amount_threshold=1000, ...)}
    approval_thresholds: dict[str, ApprovalThreshold] = Field(default_factory=dict)

    # Compliance profile
    compliance_profile: ComplianceProfile = Field(default=ComplianceProfile.BASIC)

    # Extra metadata
    custom_limits: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    effective_from: str | None = None  # ISO datetime
    effective_until: str | None = None  # ISO datetime

    @validator("tenant_id")
    def validate_tenant_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("tenant_id cannot be empty")
        return v.strip()

    @root_validator(skip_on_failure=True)
    def validate_thresholds_for_enabled_capabilities(
        cls,
        values: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Valideer dat approval thresholds alleen voor enabled capabilities gelden."""
        enabled = values.get("enabled_capabilities", set())
        thresholds = values.get("approval_thresholds", {})

        for capability_key in thresholds.keys():
            if capability_key not in enabled:
                raise ValueError(
                    f"Approval threshold for '{capability_key}' is set but capability "
                    f"is not enabled. Add '{capability_key}' to enabled_capabilities first."
                )

        return values

    def is_capability_enabled(self, capability_key: str) -> bool:
        """Check of een capability enabled is voor deze tenant."""
        return capability_key in self.enabled_capabilities

    def get_provider_priority(self, capability_type: str) -> list[str] | None:
        """Get provider priority lijst voor een capability type."""
        return self.provider_priority.get(capability_type)

    def get_approval_threshold(self, capability_key: str) -> ApprovalThreshold | None:
        """Get approval threshold voor een capability."""
        return self.approval_thresholds.get(capability_key)

    def check_approval_required(
        self,
        capability_key: str,
        input_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> ApprovalRequirement | None:
        """
        Check of approval vereist is voor deze execution.

        Returns:
            ApprovalRequirement als approval nodig is, None otherwise.
        """
        if not self.is_capability_enabled(capability_key):
            return None  # Capability niet enabled, wordt elders afgehandeld

        threshold = self.get_approval_threshold(capability_key)
        if not threshold:
            return None  # Geen threshold configured

        if not threshold.requires_approval:
            return None  # Approval uitgeschakeld voor deze capability

        # Zoek amount in input data
        amount = self._extract_amount(input_data)
        if amount is None:
            # Geen amount gevonden, geen approval nodig
            return None

        if threshold.requires_approval_for(amount):
            return ApprovalRequirement(
                capability_key=capability_key,
                amount=amount,
                approver_roles=threshold.approver_roles,
                reason=f"Amount {amount} exceeds threshold {threshold.amount_threshold}",
                auto_approve_after_ms=threshold.auto_approve_after_ms,
            )

        return None

    def _extract_amount(
        self,
        input_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> Decimal | None:  # TODO(TYPE): replace Any with concrete type
        """Probeer amount te extraheren uit input data."""
        # Common field names voor bedragen
        amount_fields = ["amount", "total", "value", "price", "cost", "sum"]

        for field_name in amount_fields:
            if field_name in input_data:
                value = input_data[field_name]
                try:
                    return Decimal(str(value))
                except (ValueError, TypeError, Exception):
                    # Invalid format (e.g., "not-a-number")
                    continue

        return None

    def get_capability_limit(
        self, limit_name: str, default: Any = None
    ) -> object:
        """Get custom limit voor deze tenant."""
        return self.custom_limits.get(limit_name, default)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize policy naar dictionary."""
        return {
            "tenant_id": self.tenant_id,
            "plan_tier": self.plan_tier.value,
            "enabled_capabilities": list(self.enabled_capabilities),
            "provider_priority": self.provider_priority,
            "approval_thresholds": {
                k: {
                    "amount_threshold": str(v.amount_threshold),
                    "requires_approval": v.requires_approval,
                    "approver_roles": list(v.approver_roles),
                }
                for k, v in self.approval_thresholds.items()
            },
            "compliance_profile": self.compliance_profile.value,
            "custom_limits": self.custom_limits,
        }


class PolicyCheckResult:
    """Resultaat van een policy check."""

    def __init__(
        self,
        allowed: bool,
        reason: str | None = None,
        violation_type: str | None = None,
        requires_approval: bool = False,
        approval_requirement: ApprovalRequirement | None = None,
        suggested_tier: PlanTier | None = None,
    ) -> None:
        self.allowed = allowed  # type: ignore[assignment]
        self.reason = reason
        self.violation_type = violation_type
        self.requires_approval = requires_approval
        self.approval_requirement = approval_requirement
        self.suggested_tier = suggested_tier

    @classmethod
    def allowed(cls) -> "PolicyCheckResult":
        """Factory method voor toegestaan resultaat."""
        return cls(allowed=True)

    @classmethod
    def denied(
        cls, reason: str, violation_type: str, suggested_tier: PlanTier | None = None
    ) -> "PolicyCheckResult":
        """Factory method voor geweigerd resultaat."""
        return cls(
            allowed=False,
            reason=reason,
            violation_type=violation_type,
            suggested_tier=suggested_tier,
        )

    @classmethod
    def pending_approval(cls, approval_requirement: ApprovalRequirement) -> "PolicyCheckResult":
        """Factory method voor approval pending resultaat."""
        return cls(
            allowed=False,
            reason=f"Approval required: {approval_requirement.reason}",
            violation_type="APPROVAL_REQUIRED",
            requires_approval=True,
            approval_requirement=approval_requirement,
        )
