"""Signal Bus - Central message bus for the symbiotic organism.

Implements the nervous system for agent communication with:
- Signal tiers (REFLEX, COGNITIVE, EMOTIONAL, SYNAPTIC)
- Tenant isolation via channel names
- Broadcast storm prevention via cooldowns
- Non-blocking audit logging
"""

import asyncio
import hashlib
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Union, cast
from collections.abc import Callable


from src.core.als.models.signal_audit_log import SignalAuditLog
from src.core.database.session import get_db_session


def get_tenant_id() -> int | None:
    """Retrieve the current tenant ID from request context middleware."""
    try:
        from src.core.middleware.tenant_context import get_tenant_id as _get_ctx_tenant_id

        return _get_ctx_tenant_id()
    except Exception:
        return None


logger = logging.getLogger(__name__)


class SignalTier(Enum):
    """Signal priority tiers.

    REFLEX:     Urgent, automatic responses (< 10ms target)
    COGNITIVE:  Normal queries and responses (< 100ms target)
    EMOTIONAL:  Agent state and sentiment sharing
    SYNAPTIC:   Direct agent-to-agent communication
    BROADCAST:  System-wide announcements
    """

    REFLEX = "reflex"
    COGNITIVE = "cognitive"
    EMOTIONAL = "emotional"
    SYNAPTIC = "synaptic"
    BROADCAST = "broadcast"


@dataclass
class Signal:
    """A signal transmitted through the nervous system.

    Attributes:
        tenant_id: Tenant identifier
        source_agent_id: Agent that emitted the signal
        target_agent_ids: Specific recipients (empty = broadcast)
        tier: Signal priority tier
        payload: Signal data
        signal_id: Unique signal identifier
        timestamp: Emission time
        correlation_id: For tracking related signals
        trace_id: Global execution trace ID
        hop_count: Number of times this signal has been re-processed
        attachments: list[Any] of associated file metadata (Fix: Phase 7)  # TODO(TYPE): replace Any with concrete type
    """

    tenant_id: int
    source_agent_id: str
    target_agent_ids: list[str]  # Empty = broadcast
    tier: SignalTier | str
    payload: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str | None = None
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    hop_count: int = 0
    attachments: list[dict[str, Any]] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=list
    )  # TODO(TYPE): replace Any with concrete type
    topic: str | None = None

    def get_payload_hash(self) -> str:
        """
        Generate SHA-256 hash of payload (Fix #12).

        Returns:
            64-character hex string (SHA-256)
        """
        import hashlib

        payload_str = json.dumps(self.payload, sort_keys=True, default=str)
        return hashlib.sha256(payload_str.encode()).hexdigest()

    def to_json(self) -> str:
        """Serialize signal to JSON."""
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_json(cls, data: str) -> "Signal":
        """Deserialize signal from JSON."""
        obj = json.loads(data)
        # Handle enum serialization - tier is stored as lowercase string
        tier_value = obj["tier"]
        if isinstance(tier_value, str):
            # Try to match by value (lowercase)
            try:
                obj["tier"] = SignalTier(tier_value)
            except ValueError:
                # Try with extracted name if format is SignalTier.REFLEX
                if tier_value.startswith("SignalTier."):
                    tier_value = tier_value.split(".")[-1].lower()
                    try:
                        obj["tier"] = SignalTier(tier_value)
                    except ValueError as e:
                        raise ValueError(f"Invalid tier: {tier_value}") from e
                else:
                    raise ValueError(f"Invalid tier: {tier_value}")
        obj["timestamp"] = datetime.fromisoformat(obj["timestamp"])
        return cls(**obj)


def _tier_value(tier: SignalTier | str) -> str:
    """Extract string value from a signal tier (SignalTier or raw str)."""
    return tier.value if isinstance(tier, SignalTier) else tier


def _to_signal_tier(tier: SignalTier | str) -> SignalTier:
    """Normalize to a SignalTier enum member."""
    return tier if isinstance(tier, SignalTier) else SignalTier(tier)


class SignalBus:
    """
    Central signal bus for agent communication.

    Now with Loop Detection and Global Observer Hooks.
    """

    MAX_HOPS = 10

    def __init__(self, pool_manager: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self.pool: Any = pool_manager  # TODO(TYPE): replace Any with concrete type
        self._handlers: dict[
            SignalTier, list[Callable[..., Any]]
        ] = {  # TODO(TYPE): replace Any with concrete type
            tier: [] for tier in SignalTier
        }
        # Global observers: list[Any] of callbacks that receive EVERY signal of a specific tier  # TODO(TYPE): replace with concrete type
        self._global_observers: dict[
            SignalTier, list[Callable[..., Any]]
        ] = {  # TODO(TYPE): replace Any with concrete type
            tier: [] for tier in SignalTier
        }
        self._pending_queries: dict[
            str, asyncio.Queue[Any]  # TODO(TYPE): replace Any with concrete type
        ] = {}  # TODO(TYPE): replace Any with concrete type
        self._query_lock = asyncio.Lock()
        self._cooldown_seconds = int(os.getenv("SIGNAL_COOLDOWN_SECONDS", "1"))
        self._listener_tasks: dict[
            str, asyncio.Task[Any]  # TODO(TYPE): replace Any with concrete type
        ] = {}  # TODO(TYPE): replace Any with concrete type

        logger.info("SignalBus initialized with Loop Detection (max_hops=10)")

    def add_global_observer(
        self, tier: SignalTier, handler: Callable[..., Any]
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Register a global observer for a signal tier."""
        self._global_observers[tier].append(handler)

    async def emit(self, signal: Signal, check_cooldown: bool = True) -> str:
        """
        Emit a signal with Loop Detection.
        """
        # 1. Loop Detection
        if signal.hop_count >= self.MAX_HOPS:
            logger.error(
                f"Loop detected: Signal {signal.signal_id} reached {signal.hop_count} hops. Dropping.",
                extra={"trace_id": signal.trace_id, "source": signal.source_agent_id},
            )
            return signal.signal_id

        # 2. Increment hop count for subsequent processing
        signal.hop_count += 1

        # 3. Immune System check
        if await self.is_tenant_blocked(signal.tenant_id):
            return signal.signal_id

        # 4. Trigger Global Observers (Internal, before network)
        tier_key = _to_signal_tier(signal.tier)
        for observer in self._global_observers.get(tier_key, []):
            try:
                # Observers run asynchronously to not block the main bus
                asyncio.create_task(observer(signal))
            except Exception as e:
                logger.error(f"Global observer failed: {e}")

        client = await self.pool.get_client()

        # FIX #17: Check cooldown for non-reflex signals
        if check_cooldown and signal.tier != SignalTier.REFLEX:
            cooldown_key = (
                f"cooldown:{signal.tenant_id}:{_tier_value(signal.tier)}:{signal.source_agent_id}"
            )

            cooldown_set = await client.set(
                cooldown_key,
                "1",
                ex=self._cooldown_seconds,
                nx=True,  # Only set if not exists
            )

            if not cooldown_set:
                logger.debug(
                    f"Signal {signal.signal_id} dropped (cooldown)",
                    extra={
                        "signal_id": signal.signal_id,
                        "source": signal.source_agent_id,
                        "tier": _tier_value(signal.tier),
                    },
                )
                return signal.signal_id

        # Publish to channel
        channel = f"organism:{signal.tenant_id}:{_tier_value(signal.tier)}"
        message = signal.to_json()

        await client.publish(channel, message)
        if getattr(signal, "topic", None):
            topic_channel = f"organism:{signal.tenant_id}:{signal.topic}"
            await client.publish(topic_channel, message)

        # FIX #18: Non-blocking audit log
        # REFLEX signals: fire-and-forget (speed critical)
        # Other tiers: wait for completion
        if signal.tier == SignalTier.REFLEX:
            task = asyncio.create_task(self._log_signal(signal))
            task.add_done_callback(
                lambda t: (
                    logger.error(f"Audit log failed: {t.exception()}") if t.exception() else None
                )
            )
        else:
            await self._log_signal(signal)

        logger.debug(
            f"Signal emitted: {signal.signal_id}",
            extra={
                "signal_id": signal.signal_id,
                "channel": channel,
                "tier": _tier_value(signal.tier),
            },
        )

        return signal.signal_id

    async def query(
        self,
        source_agent: str,
        target_agents: list[str],
        query_type: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout_ms: float = 5000,
        tenant_id: int | None = None,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Send query and collect responses.

        FIX #15: Proper cleanup in finally block prevents memory leaks.
        FIX #14: Uses get_running_loop() (not deprecated get_event_loop()).

        Args:
            source_agent: Agent sending query
            target_agents: Agents to query
            query_type: Type of query
            payload: Query data
            timeout_ms: Maximum wait time
            tenant_id: Tenant scope

        Returns: list[Any] of responses from target agents  # TODO(TYPE): replace Any with concrete type
        """
        # Get tenant_id
        _tid = tenant_id or get_tenant_id()
        if _tid is None:
            raise ValueError("tenant_id is required for query()")
        tenant_id = int(_tid)

        query_id = str(uuid.uuid4())
        response_queue: asyncio.Queue[Any] = (  # TODO(TYPE): replace Any with concrete type
            asyncio.Queue()
        )  # TODO(TYPE): replace Any with concrete type

        # Register pending query
        async with self._query_lock:
            self._pending_queries[query_id] = response_queue

        try:
            # Send query signal
            signal = Signal(
                tenant_id=tenant_id,
                source_agent_id=source_agent,
                target_agent_ids=target_agents,
                tier=SignalTier.COGNITIVE,
                payload={
                    "query_id": query_id,
                    "query_type": query_type,
                    "query_payload": payload,
                },
                correlation_id=query_id,
            )

            await self.emit(signal, check_cooldown=False)

            # Collect responses
            # FIX #14: Use get_running_loop() (Python 3.10+ compatible)
            loop = asyncio.get_running_loop()
            responses: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            start = loop.time()
            deadline = start + (timeout_ms / 1000)

            while loop.time() < deadline:
                try:
                    remaining = deadline - loop.time()
                    response = await asyncio.wait_for(
                        response_queue.get(), timeout=max(0, min(0.1, remaining))
                    )
                    responses.append(response)
                except TimeoutError:
                    continue

            return responses

        finally:
            # FIX #15: CRITICAL - cleanup to prevent memory leak
            async with self._query_lock:
                self._pending_queries.pop(query_id, None)

    async def respond_to_query(
        self,
        query_id: str,
        responder: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Respond to a pending query."""
        async with self._query_lock:
            if query_id in self._pending_queries:
                await self._pending_queries[query_id].put(
                    {
                        "responder": responder,
                        "payload": payload,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

    async def listen(
        self, tenant_id: int, tier: SignalTier, handler: Callable[..., Any]
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """
        Listen for signals on a channel.

        Args:
            tenant_id: Tenant to listen for
            tier: Signal tier to listen on
            handler: Callback function for received signals
        """
        channel = f"organism:{tenant_id}:{tier.value}"
        client = await self.pool.get_client()
        pubsub = client.pubsub()

        await pubsub.subscribe(channel)

        logger.info(f"Listening on {channel}")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        signal = Signal.from_json(message["data"])
                        await handler(signal)
                    except Exception as e:
                        logger.error(f"Error handling signal: {e}")
        finally:
            await pubsub.unsubscribe(channel)

    # Immune System Integration
    async def block_tenant(self, tenant_id: int, duration_s: int = 300) -> None:
        """
        Block all signals for a tenant.

        Used by immune system to isolate compromised tenants.

        Args:
            tenant_id: Tenant to block
            duration_s: Block duration in seconds
        """
        client = await self.pool.get_client()
        block_key = f"blocked_tenant:{tenant_id}"
        await client.set(block_key, "1", ex=duration_s)

        logger.critical(
            f"Tenant {tenant_id} blocked for {duration_s}s by immune system",
            extra={
                "event": "tenant_blocked",
                "tenant_id": tenant_id,
                "duration_s": duration_s,
            },
        )

    async def unblock_tenant(self, tenant_id: int) -> None:
        """Unblock a previously blocked tenant."""
        client = await self.pool.get_client()
        block_key = f"blocked_tenant:{tenant_id}"
        await client.delete(block_key)

        logger.info(
            f"Tenant {tenant_id} unblocked",
            extra={"event": "tenant_unblocked", "tenant_id": tenant_id},
        )

    async def is_tenant_blocked(self, tenant_id: int) -> bool:
        """Check if tenant is currently blocked."""
        client = await self.pool.get_client()
        result = await client.exists(f"blocked_tenant:{tenant_id}")
        return cast(int, result) > 0

    async def _log_signal(self, signal: Signal) -> None:
        """Log signal to database for audit."""
        try:
            # FIX #12: Use SHA-256 (not Python hash())
            payload_str = json.dumps(signal.payload, sort_keys=True, default=str)
            payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()[:64]

            async with get_db_session() as session:
                log_entry = SignalAuditLog(
                    tenant_id=signal.tenant_id,
                    signal_id=signal.signal_id,
                    source_agent=signal.source_agent_id,
                    target_agents=signal.target_agent_ids,
                    tier=_tier_value(signal.tier),
                    payload_hash=payload_hash,
                    payload_size_bytes=len(payload_str),
                    processed_at=datetime.now(timezone.utc),
                )
                session.add(log_entry)
                await session.commit()

        except Exception as e:
            logger.error(f"Failed to log signal: {e}")
            # Don't raise - audit failure shouldn't break signal flow

    async def wait_for_signal(
        self,
        topics: list[str],
        tenant_id: int,
        timeout: float = 30.0,
    ) -> "Signal | None":
        """Wait for a signal on any of the given topics with timeout."""
        client = await self.pool.get_client()
        pubsub = client.pubsub()
        channels = [f"organism:{tenant_id}:{topic}" for topic in topics]
        if not channels:
            return None
        await pubsub.subscribe(*channels)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        try:
            while loop.time() < deadline:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return None
                message = await pubsub.get_message(timeout=min(1.0, remaining))
                if message and message["type"] == "message":
                    try:
                        return Signal.from_json(message["data"])
                    except Exception as e:
                        logger.error(
                            "Failed to parse signal: %s", e, extra={"tenant_id": tenant_id}
                        )
                        continue
            return None
        finally:
            await pubsub.unsubscribe(*channels)
            await pubsub.close()


__all__ = [
    "SignalBus",
    "Signal",
    "SignalTier",
]
