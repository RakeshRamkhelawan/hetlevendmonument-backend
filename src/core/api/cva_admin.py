# orphan:exempt reason: legacy flat file, routes geconsolideerd in v1/cva/ (SP-API-006 Dag 2)
from typing import Any

from src.core.api.v1.cva.management_router import management_router as router  # noqa: F401


async def get_cva_agent(tenant_id: int = 0, cache_provider: Any = None) -> Any:
    """Compatibility wrapper for legacy get_cva_agent import.

    Delegates to the ADR-033 state module when no cache_provider is supplied,
    otherwise uses the injected provider to stay compatible with existing tests.
    """
    if cache_provider is not None:
        return await cache_provider.get_or_create(tenant_id=tenant_id)

    from src.core.api.v1.cva.state import get_cva_agent as _get_cva_agent

    return await _get_cva_agent(tenant_id=tenant_id)
