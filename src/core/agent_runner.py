"""AgentRunner -- pacemaker that executes OODA loops for active agent configs."""
from __future__ import annotations
import asyncio
import logging
from typing import Any
from collections.abc import Awaitable, Callable
from src.core.als.infrastructure.agent_circuit_breaker import AgentCircuitBreaker
from src.core.middleware.tenant_context import set_tenant_id, clear_tenant_context
from src.core.als.infrastructure.signal_bus import Signal, SignalBus, SignalTier
from src.core.repositories.agent_config_repository import AgentConfigRepository
from src.core.agents.hitl_router import resolve_hitl_recipient

logger = logging.getLogger(__name__)

_AgentConfig = Any  # avoids circular import  # TODO(TYPE): replace Any with concrete type

class AgentRunner:
    def __init__(self, db_factory: Callable[[], Awaitable[Any]], signal_bus: SignalBus, agent_factory: Callable[[Any], Awaitable[Any]] | None = None, redis_pool: Any | None = None, max_concurrent_loops: int = 50, loop_timeout: float = 30.0, backoff_seconds: float = 5.0, circuit_failure_threshold: int = 5, circuit_reset_timeout: int = 30) -> None:  # TODO(TYPE): replace Any with concrete type
        self._db_factory = db_factory
        self._signal_bus = signal_bus
        self._agent_factory = agent_factory or self._default_agent_factory
        self._redis_pool = redis_pool
        self._max_concurrent = max_concurrent_loops
        self._loop_timeout = loop_timeout
        self._backoff = backoff_seconds
        self._circuit_failure_threshold = circuit_failure_threshold
        self._circuit_reset_timeout = circuit_reset_timeout
        self._stop_event = asyncio.Event()
        self._circuit_breakers: dict[str, AgentCircuitBreaker] = {}

    async def _default_agent_factory(self, config: _AgentConfig) -> Any:  # TODO(TYPE): replace Any with concrete type
        return _DummyAgent(config)

    def _get_circuit_breaker(self, config: _AgentConfig) -> AgentCircuitBreaker | None:
        if self._redis_pool is None:
            return None
        key = f"{config.tenant_id}:{config.agent_id}"
        if key not in self._circuit_breakers:
            self._circuit_breakers[key] = AgentCircuitBreaker(self._redis_pool, config.tenant_id, config.agent_id, failure_threshold=self._circuit_failure_threshold, reset_timeout_seconds=self._circuit_reset_timeout)
        return self._circuit_breakers[key]

    async def _load_active_configs(self) -> list[_AgentConfig]:
        session = await self._db_factory()
        try:
            repo = AgentConfigRepository(session)
            return await repo.get_active_configs()
        finally:
            await session.close()

    async def start(self) -> None:
        self._stop_event.clear()
        configs = await self._load_active_configs()
        if not configs:
            logger.info("agent_runner_no_active_configs")
            return
        sem = asyncio.Semaphore(self._max_concurrent)
        tasks = [asyncio.create_task(self._run_with_sem(sem, cfg)) for cfg in configs]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("agent_runner_all_loops_ended")

    async def _run_with_sem(self, sem: asyncio.Semaphore, config: _AgentConfig) -> None:
        async with sem:
            try:
                await asyncio.wait_for(self._run_agent_loop(config), timeout=self._loop_timeout)
            except asyncio.TimeoutError:
                logger.warning("agent_loop_timeout", extra={"agent_id": config.agent_id})
            except Exception:
                logger.exception("agent_loop_error", extra={"agent_id": config.agent_id})
                await asyncio.sleep(self._backoff)

    async def _run_agent_loop(self, config: _AgentConfig) -> None:
        agent = await self._agent_factory(config)
        cb = self._get_circuit_breaker(config)
        topics = config.subscribed_topics if config.subscribed_topics else ["default"]
        while not self._stop_event.is_set():
            try:
                signal = await self._signal_bus.wait_for_signal(topics=topics, tenant_id=config.tenant_id, timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if signal is None:
                continue
            if cb is not None and not await cb.allow():
                logger.warning("agent_loop_circuit_open", extra={"agent_id": config.agent_id})
                continue
            set_tenant_id(config.tenant_id)
            try:
                await self._dispatch_action(agent, signal, config)
                if cb is not None:
                    await cb.record_success()
            except Exception:
                if cb is not None:
                    await cb.record_failure()
                raise
            finally:
                clear_tenant_context()

    async def _dispatch_action(self, agent: Any, signal: Signal, config: _AgentConfig) -> None:  # TODO(TYPE): replace Any with concrete type
        """Execute agent action with tenant context and optional HITL gate."""
        # VERPLICHT per ADR-015: tenant_id als eerste call
        set_tenant_id(config.tenant_id)

        # Execute OODA
        await agent.execute_ooda(signal)

        # HITL routing check (placeholder -- real implementation would classify risk)
        # For MVP, we log the HITL routing capability
        if getattr(config, "department_user_id", None) is not None:
            logger.info("hitl_department_user_available", extra={"agent_id": config.agent_id, "department_user_id": config.department_user_id})

    async def stop(self) -> None:
        self._stop_event.set()
        logger.info("agent_runner_stop_requested")

class _DummyAgent:
    def __init__(self, config: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self.config = config
    async def execute_ooda(self, signal: Signal) -> None:
        logger.info("dummy_agent_execute", extra={"agent_id": self.config.agent_id, "topic": signal.topic})
