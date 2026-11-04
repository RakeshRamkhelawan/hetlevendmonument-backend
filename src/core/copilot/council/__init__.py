"""
Agent Council package.

Implements the seven-Officer governance body per ADR-027.

Public API:
    AgentCouncil - Coordinator that aggregates Officer verdicts
    Proposal, CouncilDecision, OfficerVerdict - Core data types
    VerdictType, DecisionVerdict, Severity - Enums

Internal:
    members/ - One module per Officer
    audit_writer.py - Persists decisions to council_decisions table

Usage:
    from src.core.copilot.council import AgentCouncil, Proposal

    council = AgentCouncil(compliance=..., privacy=..., ...)
    decision = await council.deliberate(proposal)
    if decision.verdict == DecisionVerdict.APPROVED:
        # proceed with execution via ToolBroker (ADR-015)
        ...

See docs/copilot-architecture.md sections 5 and 6 for the full design.
"""

from __future__ import annotations

from src.core.copilot.council.coordinator import AgentCouncil
from src.core.copilot.council.types import (
    CouncilDecision,
    DecisionVerdict,
    OfficerVerdict,
    Proposal,
    ProposalTrigger,
    Severity,
    VerdictType,
)

__all__ = [
    "AgentCouncil",
    "CouncilDecision",
    "DecisionVerdict",
    "OfficerVerdict",
    "Proposal",
    "ProposalTrigger",
    "Severity",
    "VerdictType",
]
