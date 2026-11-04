"""
Reusable governance gate helper for AI entrypoints.

Provides `require_council_approval()` which standardises the
Proposal -> Council.deliberate() -> verdict check flow across
all AI-facing routes (Copilot, CVA, Focus Builder, ALS, Agentic).

Usage:
    decision = await require_council_approval(
        council=council,
        tenant_id=tenant_id,
        user_id=user_id,
        action_type="my_domain.my_action",
        action_params={...},
        reasoning="Why this action is proposed",
        data_classification=DataClassification.INTERNAL,
        confidence=1.0,
        model_id="model-name",
        model_version="1.0",
        context_snapshot={...},
    )
    # decision.verdict is guaranteed APPROVED after this call.
    # On BLOCKED/MODIFIED/HITL_REQUIRED/DEFERRED: HTTPException(403) is raised.
    # On Council crash: HTTPException(500) is raised.

This helper exists so that every AI route uses EXACTLY the same
error messages, logging, and fail-secure behaviour.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from src.core.copilot.council.coordinator import AgentCouncil
from src.core.copilot.council.types import (
    CouncilDecision,
    DataClassification,
    DecisionVerdict,
    Proposal,
    ProposalTrigger,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def require_council_approval(
    *,
    council: AgentCouncil,
    tenant_id: int,
    user_id: int,
    action_type: str,
    action_params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    reasoning: str,
    data_classification: DataClassification = DataClassification.INTERNAL,
    confidence: float = 1.0,
    model_id: str = "unknown",
    model_version: str = "1.0",
    context_snapshot: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    trigger: ProposalTrigger = ProposalTrigger.USER_REQUEST,
    db: "AsyncSession | None" = None,
    ticket_action_params: dict[str, Any] | None = None,  # TODO(TYPE): replace Any w/ concrete type
) -> CouncilDecision:
    """
    Submit a Proposal to the Council and enforce an APPROVED verdict.

    Args:
        council: AgentCouncil instance (from dependency injection).
        tenant_id: Resolved tenant ID (from JWT/auth context ONLY).
        user_id: Resolved user ID (from JWT/auth context ONLY).
        action_type: Domain-scoped action identifier, e.g. "cva.chat".
        action_params: Tool-specific parameters (keep PII out -- use keys only).
        reasoning: Natural-language explanation for the proposal.
        data_classification: PII sensitivity level.
        confidence: LLM confidence 0.0-1.0 (default 1.0 for deterministic actions).
        model_id: Model that produced the action.
        model_version: Model version for reproducibility.
        context_snapshot: Optional request context (route, page, recent actions).
        trigger: What triggered the proposal (USER_REQUEST, PROACTIVE_MONITOR, etc.).
        db: DB session for HITL-ticket creation (ADR-036 OP-167, sprint dag 2). Optional
            en met graceful degradation (geen ticket, geen crash) zodat een caller die
            nog niet is bijgewerkt niet breekt -- maar ELKE bijgewerkte caller hoort hem
            mee te geven, anders krijgt een HITL_REQUIRED-verdict op die route nog steeds
            geen ticket.
        ticket_action_params: RUWE tool-parameters voor het ticket, apart van
            `action_params` (dat geredigeerd kan zijn). Valt terug op `action_params`
            zelf als niet gegeven -- zelfde patroon als `background_gate.py`.

    Returns:
        CouncilDecision with verdict == APPROVED.

    Raises:
        HTTPException(403): If the Council returns BLOCKED, MODIFIED, HITL_REQUIRED,
            or DEFERRED. The response body includes decision_id, explanation, and (for
            HITL_REQUIRED with a `db` session) `hitl_request_id` -- the caller/frontend
            can use that ref to check ticket status later (ADR-036 OP-167 sprint dag 2).
        HTTPException(500): If the Council itself crashes (fail-secure).
    """
    proposal = Proposal(
        tenant_id=tenant_id,
        user_id=user_id,
        trigger=trigger,
        action_type=action_type,
        action_params=action_params,
        reasoning=reasoning,
        data_classification=data_classification,
        confidence=confidence,
        model_id=model_id,
        model_version=model_version,
        context_snapshot=context_snapshot or {},
    )

    try:
        decision = await council.deliberate(proposal)
    except Exception as exc:
        logger.error(
            "governance.council_error: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
            extra={"tenant_id": tenant_id, "user_id": user_id, "action_type": action_type},
        )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "COUNCIL_UNAVAILABLE",
                "message": "Governance check failed -- request blocked for safety.",
            },
        ) from exc

    if decision.verdict != DecisionVerdict.APPROVED:
        logger.warning(
            "governance.council_blocked",
            extra={
                "tenant_id": tenant_id,
                "user_id": user_id,
                "action_type": action_type,
                "verdict": decision.verdict.value,
                "decision_id": str(decision.decision_id),
            },
        )

        # ADR-036 OP-167 (sprint dag 2): tot deze fix gaf DEZE poort een HITL_REQUIRED-
        # verdict identiek aan BLOCKED terug -- geen ticket, geen mens werd ooit gevraagd
        # (AI Act art. 14). Zonder `db` (caller nog niet bijgewerkt): graceful degradation,
        # geen ticket, geen crash -- de 403 blijft hetzelfde als voorheen.
        hitl_ticket_ref: str | None = None
        if decision.verdict is DecisionVerdict.HITL_REQUIRED and db is not None:
            # Lazy import: `src/core/copilot` staat in `agent_runtime`'s SOURCE_DIRS
            # (empirisch bevestigd, zie background_gate.py). Zelfde reden als daar.
            import importlib

            hitl_repository = importlib.import_module("src.core.tool_broker.hitl_repository")
            try:
                hitl_ticket_ref = await hitl_repository.HITLTicketRepository(
                    db
                ).create_hitl_request(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    decision_id=str(decision.decision_id),
                    reason=decision.explanation_for_user,
                    action_type=action_type,
                    action_params=(
                        ticket_action_params if ticket_action_params is not None else action_params
                    ),
                )
            except (ValueError, PermissionError) as exc:
                # Zelfde klasse fout als OP-167 elders al moest oplossen (Gate 2, dag 1):
                # nooit een onverwachte exception voor een besluit dat wel degelijk
                # HITL_REQUIRED was. Loggen, geen ticket, de 403 blijft normaal doorgaan.
                logger.warning(
                    "governance.hitl_ticket_refused tenant=%s action=%s: %s: %s",
                    tenant_id,
                    action_type,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                hitl_ticket_ref = None
            else:
                # ADR-036 OP-167-vervolg (dag 4, gevonden door de feature-doc-reviewer):
                # `create_hitl_request()` doet zelf alleen `add()` + `flush()`, nooit
                # `commit()` (`hitl_repository.py::create`). Zonder deze commit hier zou de
                # meteen volgende `raise HTTPException` hieronder propageren tot in
                # `database.py::get_db()`'s `except Exception: await session.rollback()`, wat
                # het net geflushte ticket ONGEDAAN maakt voordat het ooit op schijf staat --
                # de `hitl_request_id` in de 403-body zou dan verwijzen naar een ticket dat
                # nooit heeft bestaan. Alleen op het succespad: bij een geweigerde aanmaak
                # (except hierboven) is er niets te bewaren.
                await db.commit()

        raise HTTPException(
            status_code=403,
            detail={
                "code": "GOVERNANCE_BLOCKED",
                "message": decision.explanation_for_user or "Governance policy violation",
                "decision_id": str(decision.decision_id),
                "verdict": decision.verdict.value,
                "hitl_request_id": hitl_ticket_ref,
            },
        )

    return decision
