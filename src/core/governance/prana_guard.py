"""PranaGuard -- thin wrapper over the persistent PranaService (ADR-021).

Historically this read ``tenants.prana_spent`` / ``tenants.prana_budget`` columns that
never existed (latent-broken: any real DB call raised). It is now a flag-guarded wrapper
over the single PranaService:

- with ``PRANA_ENFORCEMENT_ENABLED`` OFF (default) every method is a no-op (allow), which
  also stops the broken column reads;
- with enforcement ON it checks/charges the tenant's *department* budget atomically,
  translating the ALS ``DepartmentType`` to the canonical ``PranaDepartment``.

Re-exports ``InsufficientPranaError`` (now the PranaService one) so existing importers keep
working.
"""

import logging

from src.core.database.database import db_manager
from src.core.governance.prana_config import prana_enforcement_enabled
from src.core.governance.prana_departments import prana_department_for_als
from src.core.governance.prana_service import InsufficientPranaError as InsufficientPranaError
from src.core.governance.prana_service import PranaService

logger = logging.getLogger(__name__)

# Synthetic action_type for ALS specialist steps; cost is set by the agent-type ``tier``.
_ALS_ACTION = "als_step"


class PranaGuard:
    """Enforces the department prana budget for ALS specialist steps (ADR-021)."""

    async def check_budget(
        self, tenant_id: int, department: str | None = None, agent_type: str = "llm"
    ) -> None:
        """Advisory pre-check before an ALS step. Raises InsufficientPranaError if the
        department budget cannot cover a step of the given agent type. No-op when
        enforcement is off."""
        if not prana_enforcement_enabled():
            return
        dept = prana_department_for_als(department).value
        async with db_manager.get_session() as db:
            ok = await PranaService(db).has_budget(tenant_id, dept, _ALS_ACTION, tier=agent_type)
            if not ok:
                raise InsufficientPranaError(
                    f"Tenant {tenant_id} department {dept} has insufficient Prana budget."
                )

    async def charge_prana(
        self, tenant_id: int, department: str | None = None, agent_type: str = "llm"
    ) -> None:
        """Atomically charge a successful ALS step to the tenant's department budget
        (priced by the agent-type tier). No-op when enforcement is off."""
        if not prana_enforcement_enabled():
            return
        dept = prana_department_for_als(department).value
        async with db_manager.get_session() as db:
            await PranaService(db).charge(tenant_id, dept, _ALS_ACTION, tier=agent_type)
            await db.commit()
