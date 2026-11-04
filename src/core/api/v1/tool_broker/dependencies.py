# orphan:exempt reason: Laag 1 dependency module, imported by sub-routers (ADR-033)
"""Shared dependencies for the tool_broker domain (ADR-033 Laag 1).

Dit bestand is het ENIGE toegestane importpunt van dit domein naar infrastructuur en governance.
Contract 1 in `.importlinter` verbiedt routerbestanden om `src.core.database` of
`src.core.governance` rechtstreeks te importeren; via deze facade mag het wel, en dat is precies
het patroon dat ADR-033 par. 2 beschrijft (`allow_indirect_imports = true` -- alleen de directe
sprong vanuit de router telt).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import get_db as get_db
from src.core.governance.rate_limiter import (
    consent_read_limit as consent_read_limit,
    consent_update_limit as consent_update_limit,
)
from src.core.governance.four_eyes import (
    confirm_four_eyes_explanation as confirm_four_eyes_explanation,
    is_four_eyes_required as is_four_eyes_required,
    read_explanation_pending as read_explanation_pending,
    read_four_eyes_actions as read_four_eyes_actions,
    write_four_eyes_actions as write_four_eyes_actions,
)
from src.core.governance.hitl_evidence import build_resource as build_resource
from src.core.governance.services.audit_service import AuditService as AuditService
from src.core.tool_broker.dependencies import (
    get_tool_broker_service as get_tool_broker_service,
)
from src.core.tool_broker.resilience import get_circuit_breaker_registry


async def is_platformbeheerder(gebruiker_id: int, tenant_id: int, db: AsyncSession) -> bool:
    """Is deze gebruiker een platformbeheerder (vlag `is_superuser` of een platformrol)? DE definitie staat in
    `RBACService.is_platformbeheerder`. Via deze laag omdat de routers `src.core.services` niet rechtstreeks
    importeren (ADR-033)."""
    from src.core.api.v1.rbac.dependencies import RBACService

    return await RBACService(db).is_platformbeheerder(gebruiker_id, tenant_id)


def get_circuit_registry() -> object:
    """Return the shared circuit breaker registry."""
    return get_circuit_breaker_registry()


def redact_free_text(text: str) -> str:
    """Door een mens geschreven tekst voor het auditlog: herkende PII gemaskeerd.

    Dezelfde opschoning als tekst richting een taalmodel (`GDPREnforcer.redact_pii`). Via deze
    laag omdat `router.py` het governance-domein niet rechtstreeks importeert (ADR-033).
    """
    from src.core.governance.gdpr_enforcer import GDPREnforcer

    return GDPREnforcer().redact_pii(text)[0]


__all__ = [
    "AuditService",
    "build_resource",
    "confirm_four_eyes_explanation",
    "consent_read_limit",
    "consent_update_limit",
    "get_circuit_registry",
    "get_db",
    "is_four_eyes_required",
    "is_platformbeheerder",
    "redact_free_text",
    "read_explanation_pending",
    "read_four_eyes_actions",
    "write_four_eyes_actions",
]
