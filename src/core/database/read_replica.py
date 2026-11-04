"""
SD-5.1: Read Replica Configuration
Configures read replicas for database load distribution.
"""

import logging
import os
import random
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)


class ReplicaStrategy(str, Enum):
    """Strategy for selecting read replicas."""

    RANDOM = "random"
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"


@dataclass
class ReplicaConfig:
    """Configuration for a read replica."""

    url: str
    weight: int = 1  # Weight for load balancing
    region: str = "default"  # For geo-routing


class ReadReplicaRouter:
    """
    SD-5.1: Routes read queries to replicas.

    Features:
    - Multiple replica support
    - Load balancing strategies
    - Automatic failover
    - Health monitoring
    """

    def __init__(
        self,
        primary_url: str,
        replicas: list[ReplicaConfig] | None = None,
        strategy: ReplicaStrategy = ReplicaStrategy.ROUND_ROBIN,
    ) -> None:
        self.primary_url = primary_url
        self.replicas = replicas or []
        self.strategy = strategy

        self._primary_engine: Any = None
        self._replica_engines: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        self._current_index = 0
        self._healthy_replicas: set[int] = set()

    def initialize(self) -> None:
        """Initialize all database connections."""
        # Primary (for writes)
        self._primary_engine = create_async_engine(
            self.primary_url, pool_size=10, max_overflow=20, pool_pre_ping=True
        )

        # Replicas (for reads)
        for replica in self.replicas:
            engine = create_async_engine(
                replica.url, pool_size=5, max_overflow=10, pool_pre_ping=True
            )
            self._replica_engines.append({"config": replica, "engine": engine, "healthy": True})

        self._healthy_replicas = set(range(len(self._replica_engines)))

        logger.info(f"Database router initialized: 1 primary, {len(self.replicas)} replicas")

    def get_write_session(self) -> AsyncSession:
        """Get session for write operations (always uses primary)."""
        if not self._primary_engine:
            self.initialize()

        session_factory = async_sessionmaker(
            self._primary_engine, class_=AsyncSession, expire_on_commit=False
        )
        return session_factory()

    def get_read_session(self, prefer_primary: bool = False) -> AsyncSession:
        """Get session for read operations."""
        if not self._primary_engine:
            self.initialize()

        # Use primary if no replicas or explicitly requested
        if not self._replica_engines or prefer_primary:
            engine = self._primary_engine
        else:
            engine = self._select_replica()

        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        return session_factory()

    def _select_replica(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Select a replica based on strategy."""
        if not self._healthy_replicas:
            logger.warning("No healthy replicas, falling back to primary")
            return self._primary_engine

        if self.strategy == ReplicaStrategy.RANDOM:
            idx = random.choice(list(self._healthy_replicas))
        elif self.strategy == ReplicaStrategy.ROUND_ROBIN:
            healthy_list = sorted(self._healthy_replicas)
            idx = healthy_list[self._current_index % len(healthy_list)]
            self._current_index += 1
        else:
            # Default to first healthy
            idx = min(self._healthy_replicas)

        return self._replica_engines[idx]["engine"]

    async def check_replica_health(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Check health of all replicas."""
        from sqlalchemy import text

        results: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for i, replica in enumerate(self._replica_engines):
            try:
                async with AsyncSession(replica["engine"]) as session:
                    await session.execute(text("SELECT 1"))
                replica["healthy"] = True
                self._healthy_replicas.add(i)
                results[f"replica_{i}"] = "healthy"
            except Exception as e:
                replica["healthy"] = False
                self._healthy_replicas.discard(i)
                results[f"replica_{i}"] = f"unhealthy: {e}"
                logger.warning(f"Replica {i} is unhealthy: {e}")

        return results

    async def get_replication_lag(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get replication lag for each replica (PostgreSQL)."""
        from sqlalchemy import text

        lags: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for i, replica in enumerate(self._replica_engines):
            if not replica["healthy"]:
                lags[f"replica_{i}"] = None
                continue

            try:
                async with AsyncSession(replica["engine"]) as session:
                    result = await session.execute(
                        text(
                            """
                            SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))
                            AS lag_seconds
                        """
                        )
                    )
                    lag = result.scalar()
                    lags[f"replica_{i}"] = lag
            except Exception as e:
                lags[f"replica_{i}"] = f"error: {e}"

        return lags

    async def close(self) -> None:
        """Close all connections."""
        if self._primary_engine:
            await self._primary_engine.dispose()

        for replica in self._replica_engines:
            await replica["engine"].dispose()

        logger.info("Database router closed")


# Factory function
def create_replica_router() -> ReadReplicaRouter:
    """Create router from environment variables."""
    primary = os.getenv("DATABASE_URL", "")

    # Parse replica URLs (comma-separated)
    replica_urls = os.getenv("DATABASE_REPLICA_URLS", "").split(",")
    replicas = [ReplicaConfig(url=url.strip()) for url in replica_urls if url.strip()]

    strategy = ReplicaStrategy(os.getenv("DATABASE_REPLICA_STRATEGY", "round_robin"))

    return ReadReplicaRouter(primary_url=primary, replicas=replicas, strategy=strategy)
