"""Factory for creating PracticalTwinService instances with full wiring.

Usage:
    service = await create_practical_twin_service(db, tenant_id, redis_client)
    trace_id = await service.track_behavior(...)
"""

import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loguru import logger
from src.core.learning.batching.batch_manager import get_batch_manager
from src.core.learning.consent.consent_manager import TwinConsentManager
from src.core.learning.cost.cost_tracker import CostTracker
from src.core.learning.events.event_bus import get_twin_event_bus
from src.core.learning.interfaces.failover_llm_provider import FailoverLLMProvider
from src.core.learning.interfaces.llm_provider import (
    ILLMSuggestionProvider,
    MockSuggestionProvider,
    TenantSuggestionProvider,
)
from src.core.learning.observers.user_behavior_observer import UserBehaviorObserver
from src.core.learning.rate_limiting.redis_rate_limiter import RedisRateLimiter
from src.core.learning.services.practical_twin_service import PracticalTwinService
from src.core.models.rbac_models import Tenant
from src.core.services.llm.tenant_deur import keuze_van_de_tenant


def _build_provider_chain(
    tenant_id: int,
    eu_only: bool = False,
    budget_status: str = "ok",
    tenant_keuze: str = "mistral",
) -> list[ILLMSuggestionProvider]:
    """De providers van de twin voor DEZE tenant (ADR-026, brief 2026-10-20).

    Het taalmodel is de keuze van de tenant (`TenantSuggestionProvider`, de ene deur). Hier stond een keten
    uit de omgevingssleutels (Claude, Gemini, Ollama) die in een vaste tekst eindigde.

    Args:
        tenant_id: de tenant van wie het gedrag wordt geobserveerd.
        eu_only: heeft GEEN invloed meer op de keuze: beide keuzes (Mistral EU, eigen Ollama) zijn EU.
        budget_status: "ok" | "soft_cap" | "hard_cap".
            - "hard_cap": alleen de vaste pauzetekst (een BUDGETbesluit, geen model dat zich voordoet);
            - "soft_cap": alleen een kosteloos eigen model (`tenant_keuze == "ollama"`), anders de vaste tekst;
            - "ok": het model van de tenant.
        tenant_keuze: `mistral` of `ollama` (zie `tenant_llm_keuze`).
    """
    pauzetekst = "Overweeg even een pauze te nemen of een collega te raadplegen."
    configured = os.getenv("LLM_PROVIDER", "").lower()

    if budget_status == "hard_cap":
        return [MockSuggestionProvider(response=pauzetekst)]

    # Een UITDRUKKELIJKE `LLM_PROVIDER=mock` (ontwikkelomgeving) blijft werken.
    if configured == "mock":
        return [MockSuggestionProvider(response=pauzetekst)]

    if budget_status == "soft_cap" and tenant_keuze != "ollama":
        return [MockSuggestionProvider(response=pauzetekst)]

    return [TenantSuggestionProvider(tenant_id)]


async def _is_eu_only_tenant(db: AsyncSession, tenant_id: int) -> bool:
    """Check if a tenant has EU-only data residency.

    Returns:
        True if tenant.data_residency == 'eu-only'.
    """
    try:
        result = await db.execute(select(Tenant.data_residency).where(Tenant.id == tenant_id))
        residency = result.scalar_one_or_none()
        return residency == "eu-only"
    except Exception as exc:
        logger.warning(
            "eu_only_check_failed",
            tenant_id=tenant_id,
            error_type=type(exc).__name__,
            exc_info=True,
        )
        # Fail-secure: cannot verify residency -> protect eu-only data
        return True


async def create_practical_twin_service(
    db: AsyncSession,
    tenant_id: int,
    redis_client: Any | None = None,  # TODO(TYPE): replace Any with concrete type
) -> PracticalTwinService:
    """Create a fully wired PracticalTwinService.

    Args:
        db: SQLAlchemy async session for consent queries.
        tenant_id: Tenant ID for residency-based provider selection.
        redis_client: Optional Redis client for caching and rate limiting.

    Returns:
        PracticalTwinService with singleton batch manager and event bus.
    """
    batch_manager = await get_batch_manager()
    consent_manager = TwinConsentManager(db=db, cache=redis_client)
    rate_limiter = RedisRateLimiter(redis_client=redis_client)
    event_bus = get_twin_event_bus()
    cost_tracker = CostTracker(db=db)

    # Build failover chain based on tenant residency + budget (ADR-026 S.1.2.2)
    eu_only = await _is_eu_only_tenant(db, tenant_id)
    budget_status = await cost_tracker.check_budget_status(tenant_id)
    tenant_keuze = await keuze_van_de_tenant(tenant_id)
    chain = _build_provider_chain(
        tenant_id, eu_only=eu_only, budget_status=budget_status, tenant_keuze=tenant_keuze
    )
    llm_provider = FailoverLLMProvider(chain)

    observer = UserBehaviorObserver(
        batch_manager=batch_manager,
        consent_manager=consent_manager,
        rate_limiter=rate_limiter,
        event_bus=event_bus,
    )

    service = PracticalTwinService(
        observer=observer,
        llm_provider=llm_provider,  # type: ignore[arg-type]
        consent_manager=consent_manager,
        cost_tracker=cost_tracker,
        event_bus=event_bus,
    )
    return service
