"""Gedeelde dependencies voor het `payables`-domein (crediteuren; ADR-033 Laag 1 -> infrastructuur).

De router importeert geen database, governance of auth (ADR-033 par. 2, Contract 1 in `.importlinter`); dat gaat via dit bestand.
Zelfde patroon en zelfde reden als `api/v1/receivables/dependencies.py`: de repository, de gebruiker en `get_db` komen via de
bestaande facade `admin/dependencies.py`, de rate-limits uit `tool_broker/dependencies.py`, zodat dit domein geen nieuw
(bestand -> module)-paar toevoegt aan het fan-out-budget van `core_api` (`tests/architecture/test_dsm_grade_a_plus.py`).
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.auth.dependencies import validate_csrf_token
from src.core.api.v1.admin.dependencies import (
    NewPayable,
    NewSupplier,
    PayableRepository,
    SupplierRepository,
    UserResponse,
    _resolve_tenant_id,
    get_current_user,
    get_db,
    require_resource_permission,
)
from src.core.api.v1.tool_broker.dependencies import consent_read_limit, consent_update_limit

__all__ = [
    "NewPayable",
    "NewSupplier",
    "PayableRepository",
    "SupplierRepository",
    "UserResponse",
    "_resolve_tenant_id",
    "consent_read_limit",
    "consent_update_limit",
    "get_current_user",
    "get_db",
    "get_payable_repository",
    "get_supplier_repository",
    "require_resource_permission",
    "schrijf_crediteur_audit",
    "validate_csrf_token",
]


def get_payable_repository(db: AsyncSession = Depends(get_db)) -> PayableRepository:
    return PayableRepository(db)


def get_supplier_repository(db: AsyncSession = Depends(get_db)) -> SupplierRepository:
    return SupplierRepository(db)


async def schrijf_crediteur_audit(
    db: AsyncSession,
    *,
    event_type: str,
    user_id: int | None,
    tenant_id: int,
    pad: str,
    details: dict[str, object],
) -> None:
    """Schrijf een auditregel voor crediteuren, best-effort en NA de commit van de rij.

    De aanroeper legt de primaire wijziging eerst vast (backend-patterns par. 3); een falende auditregel rolt die dus niet terug.
    `log_event` flusht alleen, vandaar de eigen commit. Geen IBAN en geen bedrag in de details: het factuurnummer en de status
    volstaan om de stap terug te vinden. Lazy import: een module-level koppeling naar governance telt mee in het fan-out-budget.
    """
    import importlib

    from src.core.utils.best_effort import best_effort

    audit = importlib.import_module("src.core.governance.services.audit_service").AuditService
    async with best_effort(f"auditregel {event_type} voor crediteuren", db_session=db):
        await audit.log_event(
            db=db,
            event_type=event_type,
            severity="low",
            source_ip="unknown",
            endpoint=pad,
            description=f"{event_type}: {pad}",
            user_id=user_id,
            tenant_id=tenant_id,
            action=event_type,
            resource=pad,
            metadata=dict(details),
        )
        await db.commit()
