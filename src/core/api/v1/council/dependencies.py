"""Council domain FastAPI dependencies (ADR-033).

AUDIT-DB-01: router.py must not import AsyncSession/get_db directly -- the DB
session + tenant-scoped repository construction lives here instead.
"""

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.als.enterprise.gatekeeper_repository import GatekeeperRepository
from src.core.api.dependencies import get_db
from src.core.governance.models import HITLRequestModel
from src.core.middleware.tenant_context import get_tenant_id

__all__ = ["GatekeeperRepository", "HITLRequestModel", "get_council_repository"]


async def get_council_repository(db: AsyncSession = Depends(get_db)) -> GatekeeperRepository:
    """Tenant-scoped GatekeeperRepository for the council domain."""
    tenant_id = get_tenant_id()
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Tenant context required")
    return GatekeeperRepository(db, tenant_id)
