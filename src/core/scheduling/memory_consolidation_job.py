"""Scheduled job for memory consolidation.

Runs nightly to process unresolved session memory events into
durable memory items. See src/domains/memory/services/consolidation_worker.py.
"""

from typing import Any, Optional

from loguru import logger

from src.core.container import get_container
from src.core.database.bypass_session import adopt_tenant
from src.domains.memory.services.consolidation_worker import MemoryConsolidationWorker
from src.domains.memory.services.drift_engine import DriftEvent, ProfileDriftEngine


async def run_consolidation(tenant_id: int, agent_id: str | None = None) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Run memory consolidation for a tenant.

    Args:
        tenant_id: Tenant to consolidate for.
        agent_id: Optional agent filter. None = all agents.

    Returns:
        Consolidation run result (MemoryConsolidationRun or metrics dict).
    """
    container = get_container()
    session_factory = container.session_factory()

    async with session_factory() as db:
        # De tenant wordt AANGENOMEN, niet alleen doorgegeven (ADR-036 OP-153).
        #
        # Deze taak draait nachtelijks, buiten elk verzoek, dus de ContextVar is leeg.
        # `MemoryConsolidationWorker` krijgt `tenant_id` wel als argument en filtert er
        # in Python mee, maar Row Level Security leest de klant uit de PostgreSQL-
        # instelling `app.current_tenant` -- en die wordt gevuld vanuit diezelfde
        # ContextVar (`database.py::_zet_tenantcontext`). Zonder deze regel draait de
        # consolidatie na de omschakeling naar `sanskritisetu_app` met een LEGE context.
        #
        # Wat dat oplevert, gemeten 2026-09-15 op PostgreSQL 15.19: SELECT geeft nul
        # rijen en UPDATE/DELETE raken nul rijen, alle drie ZONDER foutmelding. Deze
        # taak zou dus elke nacht "succesvol" nul geheugenitems consolideren.
        #
        # `tenant_id` komt van de aanroeper (de planner), nooit uit gebruikersinvoer.
        async with adopt_tenant(db, tenant_id):
            worker = MemoryConsolidationWorker(db=db, tenant_id=tenant_id)
            result = await worker.run(agent_id=agent_id)
            logger.info(f"Memory consolidation complete for tenant {tenant_id}: {result}")
            return result


async def run_drift_check(tenant_id: int, agent_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Run drift detection for a specific agent.

    Args:
        tenant_id: Tenant context.
        agent_id: Agent to check for drift.

    Returns:
        Dict with drift_score and severity.
    """
    container = get_container()
    session_factory = container.session_factory()

    async with session_factory() as db:
        # Zelfde reden als in `run_consolidation` hierboven: zonder aangenomen tenant
        # leest `ProfileDriftEngine` na de omschakeling nul observaties en meldt hij
        # stil "geen drift" -- de gevaarlijkste uitkomst die deze functie kan geven.
        async with adopt_tenant(db, tenant_id):
            engine = ProfileDriftEngine(db=db, tenant_id=tenant_id)
            event: DriftEvent | None = await engine.detect(agent_id)
            if event is None:
                return {"drift_score": 0.0, "severity": "none", "agent_id": agent_id}
            result = {
                "drift_score": event.drift_score,
                "severity": event.severity,
                "agent_id": event.agent_id,
            }
            if event.drift_score >= 0.4:
                logger.warning(f"Drift detected for agent {agent_id}: {result}")
            return result
