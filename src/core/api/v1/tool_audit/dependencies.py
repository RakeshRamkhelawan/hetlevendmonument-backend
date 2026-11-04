"""ADR-033 dependencies facade for the tool-audit read endpoint.

Keeps router.py free of direct database/tool_broker imports (import-linter Contract 1).
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import get_db
from src.core.middleware.tenant_context import require_tenant_id
from src.core.tool_broker.audit_repository import ToolAuditRepository


async def get_tool_audit_repo(
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
) -> ToolAuditRepository:
    """Return a tenant-bound ToolAuditRepository (tenant_id from JWT, never the body)."""
    return ToolAuditRepository(db, tenant_id)
