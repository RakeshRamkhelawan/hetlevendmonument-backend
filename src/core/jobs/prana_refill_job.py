"""Daily prana refill job (ADR-021).

Resets every (tenant, department) budget to its total (spent -> 0). The reset is
IDEMPOTENT (a fixed target, not an additive credit), so it is safe even if the scheduler
fires it more than once (e.g. one enqueue per web worker) -- running it twice yields the
same balances. Delegates to PranaService.refill_all, which iterates all tenants inside
TenantFilterBypass.
"""

import logging

from src.core.database.database import db_manager
from src.core.governance.prana_service import PranaService

logger = logging.getLogger(__name__)


async def run_prana_refill() -> dict[str, int]:
    """Reset all department budgets. Returns {"reset": <number of budgets reset>}."""
    async with db_manager.get_session() as db:
        reset = await PranaService(db).refill_all()
        await db.commit()
    logger.info("prana refill: reset %s department budgets", reset)
    return {"reset": reset}
