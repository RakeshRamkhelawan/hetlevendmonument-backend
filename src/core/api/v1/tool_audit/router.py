"""ADR-033 Laag 1 -- tenant-scoped tool-audit read endpoint (BPA-009 read-pad).

The write side (ToolAuditRepository.log_execution + hash-chain) is already DB-backed and
is NOT touched here; this only exposes a read view for the ToolAuditLogs UI.
"""

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request

from src.core.api.v1.tool_audit.dependencies import get_tool_audit_repo
from src.core.auth.runtime_deps import UserResponse, get_current_user, is_tenant_admin
from src.core.shared.rate_limiter import ai_transparency_limit

if TYPE_CHECKING:
    from src.core.tool_broker.audit_repository import ToolAuditRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Tool Audit"])


#: Canoniek in `src/core/auth/dependencies.py` -- deze naam blijft als alias, want hij wordt in
#: dit bestand en in tests aangeroepen. Zie ADR-036 OP-31: er waren twee identieke kopieen en er
#: was een derde nodig; dat is nu een consolidatie geworden.
_is_tenant_admin = is_tenant_admin


@router.get("/tool-audit-logs", summary="Tenant tool-execution audit logs (admin only)")
@ai_transparency_limit
async def list_tool_audit_logs(
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    repo: "ToolAuditRepository" = Depends(get_tool_audit_repo),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    if not _is_tenant_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")

    total = await repo.count_logs()
    logs = await repo.get_logs(limit=limit, offset=offset)
    data = [
        {
            "id": log.id,
            "agent_id": log.agent_id,
            "tool_name": log.tool_name,
            "risk_level": log.risk_level,
            "status": log.status,
            "task_id": log.task_id,
            "duration_seconds": log.duration_seconds,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "audit_hash": log.audit_hash,
        }
        for log in logs
    ]
    return {"success": True, "data": data, "total": total}
