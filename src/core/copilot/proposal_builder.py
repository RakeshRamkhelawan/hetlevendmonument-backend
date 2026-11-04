"""
ProposalBuilder -- converts a CopilotAction into a Proposal for the Council.

Per ADR-027 and copilot-architecture.md:
    - Every user-facing AI action becomes a Proposal before Council deliberation.
    - DataClassification is derived from action type and parameters (conservative).
    - tenant_id and user_id come from JWT, never from request body (CLAUDE.md regel 6).

Per CLAUDE.md regel 10: ASCII-only in source code.
"""

from __future__ import annotations

from typing import Any

from src.core.copilot.council.types import (
    DataClassification,
    Proposal,
    ProposalTrigger,
)
from src.core.copilot.schemas import AI_DISCLOSURE_NOTICE, CopilotAction

NOOP_ACTION_TYPE = "noop"
"""Het action_type van een beurt waarin het taalmodel geen actie koos."""

CONVERSATIONAL_ACTION_TYPES: frozenset[str] = frozenset(
    {NOOP_ACTION_TYPE, "clarify", "confirm", "unknown"}
)
"""Gespreksantwoorden, geen uitvoerbare acties (brief 2026-10-05, A-01).

Deze beurten krijgen het gewone gespreksantwoord: geen weigering "actie zonder uitvoerder"
en geen aanroep van de tool broker (die kent ze niet en zou TB_2002 geven).
"""

PII_ACTION_PREFIXES = frozenset(
    {
        "export_",
        "share_",
        "send_email",
        "send_sms",
        "publish_",
    }
)

RESTRICTED_PARAM_KEYS = frozenset(
    {
        "email",
        "phone",
        "ssn",
        "iban",
        "passport",
        "bsn",
        "health_record",
    }
)


class ProposalBuilder:
    """Builds Council Proposals from LLM output."""

    def build(
        self,
        tenant_id: int,
        user_id: int,
        action: CopilotAction,
        trigger: ProposalTrigger,
        model_id: str,
        model_version: str,
        context_snapshot: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        capabilities: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> Proposal:
        """Construct an immutable Proposal for Council deliberation."""
        classification = self._classify(action.action, action.action_params)
        # EU AI Act art. 50 / ADR-036 D9: every copilot-proposed action is AI-generated,
        # so the proposal always carries the AI-disclosure marker the Council's
        # ComplianceOfficer requires. An explicit value from the action is respected.
        action_params = dict(action.action_params)
        action_params.setdefault("ai_disclosure", AI_DISCLOSURE_NOTICE)
        return Proposal(
            tenant_id=tenant_id,
            user_id=user_id,
            trigger=trigger,
            action_type=action.action or NOOP_ACTION_TYPE,
            action_params=action_params,
            message=action.message,
            reasoning=action.reasoning,
            data_classification=classification,
            confidence=action.confidence,
            model_id=model_id,
            model_version=model_version,
            context_snapshot=dict(context_snapshot),
            capabilities=capabilities or {},
        )

    def _classify(
        self,
        action_type: str | None,
        action_params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> DataClassification:
        """Conservative data classification based on action type and params.

        Returns RESTRICTED if the action involves PII-related prefixes or
        if restricted parameter keys are present.  Returns PUBLIC only when
        action_type is None (pure conversational response).  Everything else
        defaults to INTERNAL.
        """
        if action_type is None:
            return DataClassification.PUBLIC
        if any(action_type.startswith(p) for p in PII_ACTION_PREFIXES):
            return DataClassification.RESTRICTED
        if any(k in (action_params or {}) for k in RESTRICTED_PARAM_KEYS):
            return DataClassification.RESTRICTED
        return DataClassification.INTERNAL
