"""AgentCircuitBreaker -- Redis-backed circuit breaker per agent."""

from __future__ import annotations
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class _CircuitBreakerConfig:
    failure_threshold: int
    success_threshold: int
    reset_timeout_seconds: int


class AgentCircuitBreaker:
    def __init__(
        self,
        pool: Any,  # TODO(TYPE): replace Any with concrete type
        tenant_id: int,
        agent_id: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        reset_timeout_seconds: int = 30,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if success_threshold < 1:
            raise ValueError("success_threshold must be >= 1")
        if reset_timeout_seconds < 0:
            raise ValueError("reset_timeout_seconds must be >= 0")
        self.pool = pool
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.config = _CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            reset_timeout_seconds=reset_timeout_seconds,
        )
        self._key = f"circuit:{tenant_id}:{agent_id}"
        self._metrics_initialized = False

    def _init_metrics(self) -> None:
        if self._metrics_initialized:
            return
        try:
            from src.core.monitoring.agent_circuit_metrics import (
                AGENT_CIRCUIT_STATE,
                _state_to_float,
            )

            AGENT_CIRCUIT_STATE.labels(tenant_id=str(self.tenant_id), agent_id=self.agent_id).set(
                _state_to_float(CircuitState.CLOSED)
            )
        except Exception:
            pass
        self._metrics_initialized = True

    async def get_state(self) -> CircuitState:
        client = await self.pool.get_client()
        data = await client.hgetall(self._key)
        if not data:
            return CircuitState.CLOSED
        raw = data.get(b"state") or data.get("state")
        if raw is None:
            return CircuitState.CLOSED
        try:
            return CircuitState(raw.decode() if isinstance(raw, bytes) else raw)
        except ValueError:
            return CircuitState.CLOSED

    async def allow(self) -> bool:
        self._init_metrics()
        client = await self.pool.get_client()
        data = await client.hgetall(self._key)
        state = self._parse_state(data)
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.OPEN:
            last_fail = self._parse_int(data, "last_failure_time")
            if last_fail and (time.time() - last_fail) >= self.config.reset_timeout_seconds:
                await client.hset(self._key, "state", CircuitState.HALF_OPEN.value)
                await client.hset(self._key, "success_count", 0)
                self._update_metric_state(CircuitState.HALF_OPEN)
                return True
            return False
        if state == CircuitState.HALF_OPEN:
            return True
        return True

    async def record_success(self) -> CircuitState:
        client = await self.pool.get_client()
        data = await client.hgetall(self._key)
        state = self._parse_state(data)
        self._inc_metric("successes")
        if state == CircuitState.HALF_OPEN:
            success_count = await client.hincrby(self._key, "success_count", 1)
            if success_count >= self.config.success_threshold:
                await self._reset_to_closed(client)
                return CircuitState.CLOSED
            return CircuitState.HALF_OPEN
        await client.hset(self._key, "failure_count", 0)
        return CircuitState.CLOSED

    async def record_failure(self) -> CircuitState:
        client = await self.pool.get_client()
        data = await client.hgetall(self._key)
        state = self._parse_state(data)
        self._inc_metric("failures")
        now = int(time.time())
        if state == CircuitState.HALF_OPEN:
            await self._open_circuit(client, now)
            return CircuitState.OPEN
        failure_count = await client.hincrby(self._key, "failure_count", 1)
        await client.hset(self._key, "last_failure_time", now)
        if failure_count >= self.config.failure_threshold:
            await self._open_circuit(client, now)
            return CircuitState.OPEN
        return CircuitState.CLOSED

    def _parse_state(self, data: dict[bytes | str, bytes | str]) -> CircuitState:
        raw = data.get(b"state") or data.get("state")
        if raw is None:
            return CircuitState.CLOSED
        try:
            return CircuitState(raw.decode() if isinstance(raw, bytes) else raw)
        except ValueError:
            return CircuitState.CLOSED

    def _parse_int(self, data: dict[bytes | str, bytes | str], field: str) -> int | None:
        raw = data.get(field.encode()) or data.get(field)
        if raw is None:
            return None
        try:
            return int(raw.decode() if isinstance(raw, bytes) else raw)
        except ValueError:
            return None

    async def _open_circuit(self, client: Any, now: int) -> None:  # TODO(TYPE): replace Any with concrete type
        await client.hset(self._key, "state", CircuitState.OPEN.value)
        await client.hset(self._key, "last_failure_time", now)
        await client.hset(self._key, "failure_count", 0)
        await client.hset(self._key, "success_count", 0)
        self._update_metric_state(CircuitState.OPEN)
        self._inc_metric("opens")

    async def _reset_to_closed(self, client: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        await client.hset(self._key, "state", CircuitState.CLOSED.value)
        await client.hset(self._key, "failure_count", 0)
        await client.hset(self._key, "success_count", 0)
        self._update_metric_state(CircuitState.CLOSED)

    async def reset(self) -> None:
        client = await self.pool.get_client()
        await self._reset_to_closed(client)

    def _update_metric_state(self, state: CircuitState) -> None:
        try:
            from src.core.monitoring.agent_circuit_metrics import (
                AGENT_CIRCUIT_STATE,
                _state_to_float,
            )

            AGENT_CIRCUIT_STATE.labels(tenant_id=str(self.tenant_id), agent_id=self.agent_id).set(
                _state_to_float(state)
            )
        except Exception:
            pass

    def _inc_metric(self, name: str) -> None:
        try:
            if name == "failures":
                from src.core.monitoring.agent_circuit_metrics import AGENT_CIRCUIT_FAILURES_TOTAL

                AGENT_CIRCUIT_FAILURES_TOTAL.labels(
                    tenant_id=str(self.tenant_id), agent_id=self.agent_id
                ).inc()
            elif name == "successes":
                from src.core.monitoring.agent_circuit_metrics import AGENT_CIRCUIT_SUCCESSES_TOTAL

                AGENT_CIRCUIT_SUCCESSES_TOTAL.labels(
                    tenant_id=str(self.tenant_id), agent_id=self.agent_id
                ).inc()
            elif name == "opens":
                from src.core.monitoring.agent_circuit_metrics import AGENT_CIRCUIT_OPENS_TOTAL

                AGENT_CIRCUIT_OPENS_TOTAL.labels(
                    tenant_id=str(self.tenant_id), agent_id=self.agent_id
                ).inc()
        except Exception:
            pass
