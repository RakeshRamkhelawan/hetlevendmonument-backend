"""
ProactiveMonitor abstract base class.

Each monitor:
    - Detects a condition (per tenant)
    - Builds Signal objects
    - Proposes them to the Agent Council
    - Council decides whether the signal reaches the user

Monitors run on intervals via APScheduler. They MUST be:
    - Idempotent (running twice in a row produces same result)
    - Tenant-scoped (one detection run per tenant)
    - Fast (under 30s per tenant; offload heavy work to Dramatiq)

Per CLAUDE.md regel 6: tenant_id comes from monitor invocation context
(scheduler iterates tenants), never from request body.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar, cast

from src.core.copilot.council.types import (
    CouncilDecision,
    DecisionVerdict,
    Proposal,
    ProposalTrigger,
    Severity,
)
from src.core.copilot.proactive.types import Signal

logger = logging.getLogger(__name__)


class ProactiveMonitor(ABC):
    """Abstract base class for all proactive monitors.

    Subclasses MUST define:
        name: ClassVar[str]
        interval_seconds: ClassVar[int]  # 0 for event-driven monitors

    Event-driven monitors (e.g. PIIExportSignal) set interval_seconds = 0;
    ProactiveScheduler skips these (IntervalTrigger(seconds=0) crashes).
    """

    name: ClassVar[str] = ""
    version: ClassVar[str] = "1.0.0"
    interval_seconds: ClassVar[int] = 300  # default 5 min; 0 = event-driven
    default_severity: ClassVar[Severity] = Severity.LOW
    #: Draait de monitor door voor een stilgezette klant (besluit B ronde 2)? Alleen de
    #: compliance-waakhonden, met een reden bij de klasse; wat eruit voortkomt weigert de
    #: Council voor een stilgezette klant zelf. Elke andere monitor wordt overgeslagen.
    blijft_draaien_bij_noodstop: ClassVar[bool] = False

    def __init__(self, copilot_service: Any, dispatcher: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self._copilot_service = copilot_service
        self._dispatcher = dispatcher

    @abstractmethod
    async def detect(self, tenant_id: int) -> list[Signal]:
        """Detect signals for a tenant. Event-driven monitors return []."""
        ...

    async def propose_to_council(self, signal: Signal) -> CouncilDecision:
        """Build Proposal from Signal and submit to Council.

        Returns CouncilDecision so callers can verify verdict + side-effects
        (Sprint 5 day 5 Q1 asserts decision.verdict).
        Dispatch only happens on APPROVED; DEFERRED/HITL/BLOCKED are
        handled elsewhere (digest queue, OversightGate, refusal-log).
        """
        proposal = Proposal(
            tenant_id=signal.tenant_id,
            user_id=signal.affected_user_id,
            trigger=ProposalTrigger.PROACTIVE_MONITOR,
            action_type="send_notification",
            action_params={
                "signal_id": str(signal.signal_id),
                "title": signal.title,
                "body": signal.body,
                "severity": signal.severity.value,
                "actions": signal.suggested_actions,
                "ai_disclosure": "Deze melding is automatisch gegenereerd door een proactieve monitor.",
            },
            reasoning=signal.detection_reasoning,
            data_classification=signal.data_classification,
            confidence=signal.confidence,
            model_id=f"proactive-monitor:{self.name}",
            model_version=self.version,
            context_snapshot=signal.context,
            message=signal.body,
        )
        decision = await self._copilot_service.submit_proactive_proposal(proposal)
        if decision.verdict == DecisionVerdict.APPROVED:
            await self._dispatcher.dispatch(signal, decision)
        return cast(CouncilDecision, decision)
