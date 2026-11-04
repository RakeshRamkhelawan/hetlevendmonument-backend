"""Sharding - Multi-Layer Sharding for governance monitoring (Phase 2: Performance).

Fixes over v1:
- SHA-256 instead of MD5 (OWASP compliance)
- tenant_id in shard routing key
- Bounded buffer with backpressure
- Deterministic sampling (not random.random())
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ShardConfig:
    shard_id: int
    agent_names: list[str] = field(default_factory=list)
    max_agents: int = 30


class ShardedGovernanceMonitor:
    """Distributes governance monitoring over multiple shards.

    Each shard is a separate consumer via Redis Pub/Sub (ADR-006).
    Shard assignment is consistent via SHA-256 so the same agent
    always lands on the same shard within a tenant.
    """

    NUM_SHARDS = 10

    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        self.shards: dict[int, ShardConsumer] = {}
        self._initialize_shards()

    def _initialize_shards(self) -> None:
        for shard_id in range(self.NUM_SHARDS):
            self.shards[shard_id] = ShardConsumer(
                shard_id=shard_id,
                tenant_id=self.tenant_id,
                queue_name=f"governance.t{self.tenant_id}.shard.{shard_id}",
            )

    def get_shard_for_agent(self, agent_id: str) -> int:
        """Consistent shard assignment via SHA-256 (not MD5)."""
        hash_val = int(
            hashlib.sha256(f"{self.tenant_id}:{agent_id}".encode()).hexdigest(),
            16,
        )
        return hash_val % self.NUM_SHARDS

    async def route_event(self, event: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        shard_id = self.get_shard_for_agent(event.agent_id)
        await self.shards[shard_id].enqueue(event)

    async def start_all(self) -> None:
        await asyncio.gather(*(shard.start() for shard in self.shards.values()))


class ShardConsumer:
    """Single shard consumer with bounded buffer.

    Fixes over v1:
    - deque(maxlen=) instead of unbounded list
    - Backpressure: reject events when buffer is full
    - Deterministic sampling via event hash
    """

    MAX_BUFFER = 1000
    BATCH_SIZE = 100

    def __init__(
        self,
        shard_id: int,
        tenant_id: int,
        queue_name: str,
    ) -> None:
        self.shard_id = shard_id
        self.tenant_id = tenant_id
        self.queue_name = queue_name
        self._buffer: deque[dict[str, Any]] = deque(  # TODO(TYPE): replace Any with concrete type
            maxlen=self.MAX_BUFFER
        )  # TODO(TYPE): replace Any with concrete type
        self.recorded_violations: deque[dict[str, Any]] = deque(  # TODO(TYPE): replace Any with concrete type
            maxlen=self.MAX_BUFFER
        )

    async def enqueue(self, event: Any) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Enqueue with backpressure. Returns False if buffer is full."""
        if len(self._buffer) >= self.MAX_BUFFER:
            return False
        self._buffer.append(event)
        if len(self._buffer) >= self.BATCH_SIZE:
            await self._process_batch()
        return True

    async def start(self) -> None:
        """Start consumer (Redis Pub/Sub via pubsub_manager).

        Raises:
            NotImplementedError: Standalone consumer loop is not yet wired to Redis Pub/Sub per ADR-006.
        """
        raise NotImplementedError(
            "ShardConsumer background listener is not yet wired to Redis Pub/Sub. See ADR-006."
        )

    async def _process_batch(self) -> None:
        batch = [self._buffer.popleft() for _ in range(min(self.BATCH_SIZE, len(self._buffer)))]
        violations = await asyncio.gather(*(self._analyze_event(event) for event in batch))
        real = [v for v in violations if v is not None]
        if real:
            await self._handle_violations(real)

    def should_deep_check(
        self, event: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Deterministic sampling via SHA-256 event hash (reproducible for audit)."""
        risk = event.get("risk_level", "low")
        sampling_rate = {"high": 1.0, "medium": 0.5, "low": 0.1}
        rate = sampling_rate.get(risk, 0.1)

        event_hash = int(
            hashlib.sha256(str(event.get("event_id", "")).encode()).hexdigest(),
            16,
        )
        normalized = (event_hash % 10000) / 10000.0
        return normalized < rate

    async def _analyze_event(
        self, event: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Analyze an event for governance compliance and policy violations."""
        if not event:
            return None

        # Check forbidden actions
        if event.get("action") in {"unauthorized_access", "privilege_escalation", "data_exfiltration"}:
            return {
                "shard_id": self.shard_id,
                "tenant_id": self.tenant_id,
                "event_id": event.get("event_id"),
                "reason": f"forbidden_action_{event.get('action')}",
                "details": event,
            }

        # Check explicit policy violations
        if event.get("violation") or event.get("error") or event.get("is_blocked"):
            return {
                "shard_id": self.shard_id,
                "tenant_id": self.tenant_id,
                "event_id": event.get("event_id"),
                "reason": str(event.get("violation") or event.get("error") or "blocked"),
                "details": event,
            }

        # Deep check sampling
        if self.should_deep_check(event) and event.get("unauthorized"):
            return {
                "shard_id": self.shard_id,
                "tenant_id": self.tenant_id,
                "event_id": event.get("event_id"),
                "reason": "sampled_deep_check_unauthorized",
                "details": event,
            }

        # Check critical or high risk
        if event.get("risk_level") in ("critical", "high"):
            return {
                "shard_id": self.shard_id,
                "tenant_id": self.tenant_id,
                "event_id": event.get("event_id"),
                "reason": "high_or_critical_risk",
                "details": event,
            }

        return None

    async def _handle_violations(
        self, violations: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Record and log governance violations detected on this shard."""
        if not hasattr(self, "recorded_violations") or not isinstance(self.recorded_violations, deque):
            self.recorded_violations = deque(maxlen=self.MAX_BUFFER)
        for v in violations:
            logger.warning(
                "Governance policy violation detected on shard %s (tenant %s): event_id=%s, reason=%s",
                self.shard_id,
                self.tenant_id,
                v.get("event_id"),
                v.get("reason"),
                extra={"tenant_id": self.tenant_id, "shard_id": self.shard_id, "violation": v},
            )
            self.recorded_violations.append(v)
