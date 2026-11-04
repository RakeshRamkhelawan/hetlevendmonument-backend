"""HITL Router -- routes approval requests to department_user or tenant admin fallback."""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

class HITLRoutingDecision:
    def __init__(self, recipient_user_id: int, fallback: bool = False) -> None:
        self.recipient_user_id = recipient_user_id
        self.fallback = fallback

async def resolve_hitl_recipient(config: Any, db_session: Any | None = None) -> HITLRoutingDecision:  # TODO(TYPE): replace Any with concrete type
    """Resolve HITL recipient: department_user_id if set, else tenant admin."""
    if getattr(config, "department_user_id", None) is not None:
        return HITLRoutingDecision(recipient_user_id=config.department_user_id, fallback=False)
    # Fallback: resolve tenant admin (simplified -- in production, query users table)
    tenant_admin_id = await _get_tenant_admin_id(config.tenant_id, db_session)
    return HITLRoutingDecision(recipient_user_id=tenant_admin_id, fallback=True)

async def _get_tenant_admin_id(tenant_id: int, db_session: Any | None = None) -> int:  # TODO(TYPE): replace Any with concrete type
    """Get tenant admin user id. Placeholder: returns tenant_id as user_id for MVP."""
    # In production: query users table for role=admin and tenant_id
    return tenant_id
