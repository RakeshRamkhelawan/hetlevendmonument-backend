"""DigitalTwin Service -- AUDIT-DB14b (ADR-033 service layer).

ADR-026: consent-wijzigingen opgeslagen als onveranderlijke log (INSERT, nooit UPDATE).
ADR-003: tenant_id altijd uit JWT ContextVar.
Security: agent_id eigendomscheck vereist voor elke consent-mutatie.
"""

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from src.core.api.v1.digital_twin.dependencies import LLMFallbackChain
    from src.core.models.digital_twin_models import AgentTwinConsentEvent

logger = logging.getLogger(__name__)


class ConsentSettings(BaseModel):
    observe: bool


class DigitalTwinService:
    """Service layer voor agent digital twin operaties (ADR-033).

    Injected via Depends(get_digital_twin_service); nooit direct instantieren.
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id

    def _build_llm_failover_chain(self) -> "LLMFallbackChain":
        """Bouw de LLM failover chain (ADR-026: altijd LLMFallbackChain)."""
        from src.core.api.v1.digital_twin.dependencies import LLMFallbackChain

        return LLMFallbackChain()

    async def _verify_agent_ownership(self, agent_id: int) -> None:
        """Verifieer dat agent_id toebehoort aan self.tenant_id (IDOR-preventie)."""
        from src.core.api.v1.digital_twin.dependencies import Agent

        result = await self.db.execute(
            select(Agent).where(
                Agent.id == agent_id,
                Agent.tenant_id == self.tenant_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise ValueError(f"Agent {agent_id} niet gevonden voor tenant {self.tenant_id}")

    async def update_consent(
        self, agent_id: int, consent: ConsentSettings
    ) -> "AgentTwinConsentEvent":
        """Sla consent op als onveranderlijk log-record (ADR-026: INSERT, nooit UPDATE)."""
        from datetime import datetime, timezone

        from src.core.models.digital_twin_models import AgentTwinConsentEvent

        await self._verify_agent_ownership(agent_id)

        event = AgentTwinConsentEvent(
            agent_id=agent_id,
            tenant_id=self.tenant_id,
            observe=consent.observe,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        logger.info(
            "Consent updated: agent_id=%s tenant=%s observe=%s",
            agent_id,
            self.tenant_id,
            consent.observe,
        )
        return event

    async def get_twin_state(
        self, agent_id: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Haal huidige twin state op voor agent (tenant-gefilterd)."""
        from src.core.models.digital_twin_models import AgentTwinConsentEvent

        await self._verify_agent_ownership(agent_id)
        result = await self.db.execute(
            select(AgentTwinConsentEvent)
            .where(
                AgentTwinConsentEvent.agent_id == agent_id,
                AgentTwinConsentEvent.tenant_id == self.tenant_id,
            )
            .order_by(AgentTwinConsentEvent.created_at.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        observe = latest.observe if latest is not None else False
        return {"agent_id": agent_id, "observe": observe, "tenant_id": self.tenant_id}

    async def get_consent_history(
        self,
        agent_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list["AgentTwinConsentEvent"]:
        """Haal consent-geschiedenis op (tenant-gefilterd, gepagineerd)."""
        from src.core.models.digital_twin_models import AgentTwinConsentEvent

        result = await self.db.execute(
            select(AgentTwinConsentEvent)
            .where(
                AgentTwinConsentEvent.agent_id == agent_id,
                AgentTwinConsentEvent.tenant_id == self.tenant_id,
            )
            .order_by(AgentTwinConsentEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
