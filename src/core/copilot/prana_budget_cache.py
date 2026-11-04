"""Shared ContractManager cache for prana budget checks.

One ContractManager instance per tenant, keyed by tenant_id.
Instances are created lazily on first request within an async context
(required: asyncio.create_task inside ContractManager.__init__).
"""

from src.core.als.enterprise.contracts.a2a_contracts import ContractManager
from src.core.als.infrastructure.redis_pool import get_redis_pool
from src.core.als.infrastructure.signal_bus import SignalBus

# module-level cache -- intentionally NOT bounded (MVP scope; production would use Redis-backed state)
_managers: dict[int, ContractManager] = {}


def get_contract_manager(tenant_id: int) -> ContractManager:
    """Return the ContractManager for tenant_id, creating it on first call.

    Must be called from within an async route handler so that the
    asyncio.create_task call inside ContractManager.__init__ has a
    running event loop available.
    """
    if tenant_id not in _managers:
        pool = get_redis_pool()
        signal_bus = SignalBus(pool)
        _managers[tenant_id] = ContractManager(signal_bus=signal_bus, tenant_id=tenant_id)
    return _managers[tenant_id]
