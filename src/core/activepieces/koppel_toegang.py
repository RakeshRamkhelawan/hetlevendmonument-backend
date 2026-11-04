"""Wie koppelingen mag beheren, en het logboek daarvan (SP-KOPPEL-001 dag 1).

Dit staat in het domeinpakket en niet in `api/v1/activepieces/dependencies.py`, zodat de API-laag
een facade importeert in plaats van auth, database en tenant los te kennen (ADR-033; de
fan-out-gate telt unieke bestand-module-paren).
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import UserResponse, get_current_user, is_admin
from src.core.database.database import get_db
from src.core.governance.services.audit_service import log_security_event
from src.core.middleware.tenant_context import safe_get_tenant_id
from src.core.utils.best_effort import best_effort

__all__ = ["KoppelAudit", "get_koppel_audit", "require_koppel_beheerder"]


async def require_koppel_beheerder(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """Koppelingen aanmaken, wijzigen, testen of verwijderen mag alleen de beheerder van de klant.

    Via `is_admin` (de centrale definitie voor beheer BINNEN een tenant, ADR-039: "koppelingen
    beheren" is een beheerbevoegdheid). Lezen blijft voor elke gebruiker van de klant.
    """
    if not is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Alleen de beheerder van uw organisatie mag koppelingen beheren.",
        )
    return current_user


class KoppelAudit:
    """Schrijft de auditregel van een koppelingshandeling: wie, welke klant, welk piece.

    De aanroeper geeft zelf de `details` mee en legt er NOOIT een sleutel of token in. De regel
    is best-effort en komt na de primaire handeling (backend-patterns regel 3); `commit()` hoort
    erbij omdat `log_security_event` alleen flusht en `get_db` bij een latere fout terugdraait.
    """

    def __init__(self, db: AsyncSession, user_id: int | None, tenant_id: int, ip_address: str):
        self._db = db
        self._user_id = user_id
        self._tenant_id = tenant_id
        self._ip_address = ip_address

    async def schrijf(
        self, event_type: str, request_method: str, details: dict[str, object]
    ) -> None:
        async with best_effort(
            f"auditregel {event_type} voor koppelingenbeheer", db_session=self._db
        ):
            await log_security_event(
                event_type=event_type,
                user_id=self._user_id,
                tenant_id=self._tenant_id,
                request_path="/integrations/connections",
                request_method=request_method,
                ip_address=self._ip_address,
                details=details,
                db=self._db,
            )
            await self._db.commit()


async def get_koppel_audit(
    http_request: Request,
    beheerder: UserResponse = Depends(require_koppel_beheerder),
    tenant_id: int = Depends(safe_get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> KoppelAudit:
    """De auditschrijver voor deze beheerder en deze klant (tenant uit het token)."""
    ip = http_request.client.host if http_request.client else "unknown"
    return KoppelAudit(db, getattr(beheerder, "id", None), tenant_id, ip)
