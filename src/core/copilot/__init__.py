"""
SanskritiSetu Co-Pilot package.

This package provides the unified Co-Pilot service for SanskritiSetu, including:

- The Agent Council (src.core.copilot.council) - a seven-Officer governance body
  that approves or denies every Co-Pilot action (proactive or reactive) per
  ADR-027 and EU AI Act art. 12/13/50, GDPR art. 22, ISO 42001 A.6.2.8.

- The Proactive Monitors (src.core.copilot.proactive) - background detectors
  that propose signals to the Council on system health and compliance events.

- The Notification Dispatcher (src.core.copilot.notification) - enforces the
  per-user daily budget (default 25, configurable 0-100) with smart batching
  options.

- The CopilotService (src.core.copilot.service) - single entry point that
  consolidates the previously fragmented HTTP/SSE/WS endpoints into one
  governed flow.

Design references:
    - docs/adr/027-copilot-agent-council.md
    - docs/copilot-architecture.md
    - docs/copilot-sprint-plan.md
    - docs/copilot-feature-context.md (audit baseline 2026-05-22)

All architectural decisions in ADR-027 are binding. Do not bypass the Council
for any user-visible AI action.
"""

from __future__ import annotations

from src.core.copilot.schemas import (
    CopilotAction,
    CopilotTurnRequest,
    CopilotTurnResponse,
)
from src.core.copilot.llm_handler import LLMHandler
from src.core.copilot.proposal_builder import ProposalBuilder

__all__: list[str] = [
    "CopilotAction",
    "CopilotTurnRequest",
    "CopilotTurnResponse",
    "LLMHandler",
    "ProposalBuilder",
]
