"""Governance contract: autonomy level + risk category binding for EU AI Act ADR-031."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from src.core.shared.ai_act_types import AIActRiskLevel


class AutonomyLevel(str, Enum):
    HUMAN_IN_LOOP = "HUMAN_IN_LOOP"
    HUMAN_ON_LOOP = "HUMAN_ON_LOOP"
    HUMAN_OUT_OF_LOOP = "HUMAN_OUT_OF_LOOP"
    ADVISORY = "ADVISORY"


@dataclass
class GovernanceContract:
    """Governance contract voor een AI-agent conform ADR-031.

    Binds an agent_id to its permitted autonomy level, risk category,
    and compliance evidence. Call `is_action_permitted()` before executing
    any side-effecting action.
    """

    agent_id: str
    tenant_id: int
    autonomy_level: AutonomyLevel = AutonomyLevel.HUMAN_IN_LOOP
    risk_category: AIActRiskLevel = AIActRiskLevel.LIMITED
    evidence: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.agent_id or not self.agent_id.strip():
            raise ValueError("agent_id is required")
        if not isinstance(self.tenant_id, int) or self.tenant_id <= 0:
            raise ValueError("tenant_id must be a positive integer")

    def is_action_permitted(self, action: str) -> bool:
        """Returns True if action is allowed under current autonomy/risk constraints."""
        if self.risk_category == AIActRiskLevel.UNACCEPTABLE:
            return False
        if self.autonomy_level == AutonomyLevel.ADVISORY:
            return False
        # HIGH_RISK + HUMAN_OUT_OF_LOOP vereist expliciete goedkeuring
        if (
            self.risk_category == AIActRiskLevel.HIGH_RISK
            and self.autonomy_level == AutonomyLevel.HUMAN_OUT_OF_LOOP
        ):
            return self._is_explicitly_approved(action)
        if self.autonomy_level == AutonomyLevel.HUMAN_IN_LOOP:
            return self._is_explicitly_approved(action)
        return True

    def record_evidence(
        self, key: str, value: Any  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Voeg compliance-evidence toe; ValueError als de sleutel al bestaat."""
        if key in self.evidence:
            raise ValueError(f"evidence key {key!r} already recorded")
        self.evidence[key] = value

    def record_hitl_approval(self, approved_by: str, action: str) -> None:
        """Record a HITL approval decision in evidence (EU AI Act Art. 14 / EU-AI-004).

        Stores the approval in evidence['hitl_approval'] for auditability and
        adds the action to evidence['approved_actions'] so that
        is_action_permitted() permits it for HUMAN_IN_LOOP contracts.
        """
        from datetime import datetime, timezone

        approval_record = {
            "approved_by": approved_by,
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if "hitl_approval" not in self.evidence:
            self.evidence["hitl_approval"] = []
        self.evidence["hitl_approval"].append(approval_record)

        approved_actions = self.evidence.setdefault("approved_actions", [])
        if action not in approved_actions:
            approved_actions.append(action)

    def validate_with_risk_register(self) -> bool:
        """Validate this contract against the global RiskRegister (EU-AI-001 / Art. 9)."""
        from src.core.governance.risk_register import RiskRegister

        register = RiskRegister()
        return register.validate_contract(self)

    def _is_explicitly_approved(self, action: str) -> bool:
        approved = self.evidence.get("approved_actions")
        if not isinstance(approved, list):
            return False
        return action in approved
