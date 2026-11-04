"""Dependencies voor digital_twin domain (ADR-033 service injectie).

Ook facade voor forbidden-module re-exports (ADR-033): models.py en service.py
mogen src.core.database / src.core.llm / src.core.agents niet direct importeren
in de API-laag -- dat loopt via deze dependencies.py.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.models import Agent as Agent
from src.core.api.v1.digital_twin.service import DigitalTwinService
from src.core.database.database import Base as Base, get_db
from src.core.llm.fallback_chain import LLMFallbackChain as LLMFallbackChain
from src.core.middleware.tenant_context import require_tenant_id


async def get_digital_twin_service(
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
) -> DigitalTwinService:
    """Dependency voor DigitalTwinService (ADR-033)."""
    return DigitalTwinService(db=db, tenant_id=tenant_id)
