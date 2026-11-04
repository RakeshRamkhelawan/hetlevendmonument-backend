"""Shared dependencies for ActivePieces domain (ADR-033 Laag 1)."""

from src.core.activepieces.client import get_activepieces_client as get_ap_client
from src.core.activepieces.koppel_toegang import (
    KoppelAudit,
    get_koppel_audit,
    require_koppel_beheerder,
)
from src.core.activepieces.service import get_activepieces_service as get_ap_service
from src.core.governance.rate_limiter import (
    integration_read_limit,
    integration_write_limit,
)

__all__ = [
    "KoppelAudit",
    "get_ap_client",
    "get_ap_service",
    "get_koppel_audit",
    "integration_read_limit",
    "integration_write_limit",
    "require_koppel_beheerder",
]
