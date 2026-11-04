"""ALS Initialization - Setup the symbiotic organism.

This module handles the initialization of all ALS components
in the correct order.
"""

import logging
from typing import Optional

from src.core.als.agents.chief_orchestrator import ChiefOrchestrator
from src.core.als.immune.immune_system import ImmuneSystem
from src.core.als.infrastructure.redis_pool import get_redis_pool
from src.core.als.infrastructure.signal_bus import SignalBus

logger = logging.getLogger(__name__)


class ALSInitialization:
    """Manages ALS initialization for a tenant."""

    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        self.signal_bus: SignalBus | None = None
        self.orchestrator: ChiefOrchestrator | None = None
        self.immune_system: ImmuneSystem | None = None
        self._initialized = False

    async def initialize(self) -> bool:
        """
        Initialize ALS in correct order:
        1. Redis Pool
        2. Signal Bus
        3. Immune System
        4. Chief Orchestrator
        5. Start monitoring
        """
        try:
            logger.info(f"Initializing ALS for tenant {self.tenant_id}")

            # 1. Redis Pool (already global singleton)
            pool = get_redis_pool()
            if not await pool.health_check():
                raise RuntimeError("Redis connection failed")

            # 2. Signal Bus
            self.signal_bus = SignalBus(pool)
            logger.info("SignalBus initialized")

            # 3. Immune System (before orchestrator for protection)
            self.immune_system = ImmuneSystem(tenant_id=self.tenant_id, signal_bus=self.signal_bus)
            await self.immune_system.initialize()
            await self.immune_system.start_monitoring()
            logger.info("ImmuneSystem initialized and monitoring")

            # 4. Chief Orchestrator
            self.orchestrator = ChiefOrchestrator(
                tenant_id=self.tenant_id, signal_bus=self.signal_bus
            )
            await self.orchestrator.initialize()
            logger.info("ChiefOrchestrator initialized")

            self._initialized = True

            logger.info(
                f"ALS fully initialized for tenant {self.tenant_id}",
                extra={"tenant_id": self.tenant_id, "event": "als_initialized"},
            )

            return True

        except Exception as e:
            logger.error(
                f"ALS initialization failed: {e}",
                extra={"tenant_id": self.tenant_id, "error": str(e)},
            )
            return False

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        if self.orchestrator:
            await self.orchestrator.shutdown()

        logger.info(f"ALS shutdown for tenant {self.tenant_id}")

    def get_orchestrator(self) -> ChiefOrchestrator | None:
        """Get orchestrator instance."""
        return self.orchestrator

    def get_signal_bus(self) -> SignalBus | None:
        """Get signal bus instance."""
        return self.signal_bus


# Global registry of ALS instances per tenant
_als_instances: dict[int, ALSInitialization] = {}


def get_als(tenant_id: int) -> ALSInitialization:
    """Get or create ALS instance for tenant."""
    if tenant_id not in _als_instances:
        _als_instances[tenant_id] = ALSInitialization(tenant_id)
    return _als_instances[tenant_id]


async def initialize_all_tenants() -> None:
    """Initialize ALS for all active tenants."""
    # TODO: Query database for active tenants
    # For now, initialize for default tenants
    pass


async def shutdown_all() -> None:
    """Shutdown all ALS instances."""
    for tenant_id, als in _als_instances.items():
        await als.shutdown()

    _als_instances.clear()
