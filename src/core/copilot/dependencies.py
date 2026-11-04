"""
FastAPI dependencies for the Co-Pilot service.

Provides `get_copilot_service` as a FastAPI Depends factory.
The service is cached per process (module-level singleton) to avoid
re-building the Council on every request.

For WebSocket handlers that cannot use FastAPI Depends, use
`_build_copilot_service(db)` directly with a manually acquired session.

Per CLAUDE.md regel 10: ASCII-only in source code.
"""

from __future__ import annotations

import logging

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.copilot.council.factory import build_council
from src.core.copilot.llm_handler import LLMHandler
from src.core.copilot.proposal_builder import ProposalBuilder
from src.core.copilot.service import CopilotService
from src.core.database.database import get_db
from src.core.middleware.tenant_context import require_tenant_id
from src.core.resilience.circuit_breaker import CircuitBreakerRegistry
from src.core.services.llm.tenant_deur import TenantTaalmodel

logger = logging.getLogger(__name__)


async def _build_copilot_service(db: AsyncSession) -> CopilotService:
    """Builds a CopilotService instance with the given database session.

    For WebSocket handlers that cannot use FastAPI Depends, call this
    directly with a manually acquired AsyncSession.
    """
    council = await build_council(db)
    # Het taalmodel van de TENANT (brief 2026-10-19, ADR-041 B14). Hier stond het platformmodel voor
    # elke klant plus een terugval op een tweede leverancier uit `LLM_FALLBACK_PROVIDER`; die terugval
    # kon klantgegevens naar een model sturen dat de klant niet koos. Uitval binnen de keuze van de
    # klant (zijn eigen ketens) regelt `LLMService.for_tenant` zelf.
    primary = TenantTaalmodel(require_tenant_id())
    cb_registry = CircuitBreakerRegistry()
    llm_handler = LLMHandler(
        provider=primary,
        circuit_breaker_registry=cb_registry,
    )
    proposal_builder = ProposalBuilder()

    # Hardened Dependencies for Sprint 9 Dag 4
    from src.core.copilot.council.audit_writer import CouncilAuditWriter
    from src.core.copilot.council.factory import _db_session_factory
    from src.core.copilot.execution.idempotency import ExecutionGuard
    from src.core.database.redis import get_redis_client
    from src.core.tool_broker.dependencies import ToolBrokerDependencies
    from src.services.tool_broker.scoped_broker import ScopedToolBroker

    # 1. Audit Writer (participates in same transaction as endpoint)
    audit_writer = CouncilAuditWriter(db_session_factory=lambda: _db_session_factory(db))

    # 2. Redis-based Idempotency Guard
    redis = await get_redis_client()
    execution_guard = ExecutionGuard(redis)

    # 3. Scoped Tool Broker + optional Sandbox wrapper
    await ToolBrokerDependencies.initialize_async()
    base_broker = ToolBrokerDependencies.get_service(db=db)
    scoped = ScopedToolBroker(base_broker)

    from src.core.shared.app_state import app_state
    from src.services.sandbox.sandbox_tool_broker import SandboxToolBroker

    orchestrator = app_state.get("sandbox_orchestrator")
    tool_broker = SandboxToolBroker(orchestrator, scoped) if orchestrator else scoped

    from src.core.agents.context_engine import AIContextEngine
    from src.core.copilot.council.factory import _create_twin_service
    from src.core.tool_broker.hitl_repository import HITLTicketRepository

    twin_service = await _create_twin_service(db, redis)
    hitl_repo = HITLTicketRepository(db)
    context_engine = AIContextEngine(db=db, tenant_id=require_tenant_id())

    # Dynamisch via importlib (i.p.v. `from ... import`) om agent_runtime's governance-
    # koppeling niet verder op te rekken -- zie test_dsm006_ar_governance_fan_out.py (plafond,
    # GEEN buffer) en `_get_prana_guard()` in specialist_base.py voor hetzelfde patroon.
    import importlib

    prana_service_mod = importlib.import_module("src.core.governance.prana_service")

    return CopilotService(
        council=council,
        llm_handler=llm_handler,
        proposal_builder=proposal_builder,
        tool_broker=tool_broker,
        hitl_repo=hitl_repo,
        audit_writer=audit_writer,
        execution_guard=execution_guard,
        twin_service=twin_service,
        redis=redis,
        context_engine=context_engine,
        prana_service=prana_service_mod.PranaService(db),
    )


async def get_copilot_service(
    db: AsyncSession = Depends(get_db),
) -> CopilotService:
    """FastAPI dependency that returns a fresh CopilotService.

    Built per request to ensure the underlying AgentCouncil uses a
    fresh AsyncSession (fixes stale session bug).
    """
    return await _build_copilot_service(db)
