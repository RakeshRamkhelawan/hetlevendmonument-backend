"""Symbiotic Agent Base Class - Integration with ALS.

This class extends EnhancedBaseAgent with ALS capabilities:
- Signal-based communication (OODA loop)
- Collective memory access
- Immune system integration
- Heartbeat registration
"""

import asyncio
import logging
from abc import abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.agents.base_agent import AgentCapability, EnhancedBaseAgent
from src.core.als.infrastructure.signal_bus import Signal, SignalBus, SignalTier
from src.core.als.models.organism_registry import OrganismRegistry
from src.core.database.session import get_db_session
from src.core.shared.interfaces import ExecutionResult

logger = logging.getLogger(__name__)

__all__ = ["SymbioticAgent", "ExecutionResult"]


class SymbioticAgent(EnhancedBaseAgent):
    """
    Base class for agents in the symbiotic organism.

    Implements the OODA loop pattern:
    - Observe: Gather data from signals
    - Orient: Analyze using collective memory
    - Decide: Choose action
    - Act: Execute and emit result signal

    Example:
        class MyAgent(SymbioticAgent):
            async def observe(self, signal: Signal) -> Dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
                return {"data": signal.payload}

            async def orient(self, observation: Dict[str, Any]) -> Dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
                return {"analysis": observation["data"]}

            async def decide(self, orientation: Dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
                return "execute_task"

            async def act(self, decision: str) -> ExecutionResult:
                return ExecutionResult(success=True)
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: Any,  # TODO(TYPE): replace Any with concrete type
        tenant_id: int,
        signal_bus: SignalBus | None = None,
        department: str = "general",
        **kwargs: Any,
    ) -> None:
        # Call parent with tenant_id. department is forwarded so ai_act_classifier.
        # classify_agent() (GOV-002/003/005, Groep 3) sees the real department instead
        # of silently falling back to "general" for every ALS department agent.
        super().__init__(
            agent_id=agent_id,
            agent_type=agent_type,
            tenant_id=tenant_id,
            department=department,
            **kwargs,
        )

        self.signal_bus = signal_bus
        self.department = department
        self._organism_id = f"{tenant_id}:{agent_id}"
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._listener_task: asyncio.Task[None] | None = None

        # Emotional state (for load reporting)
        self._emotional_state = {"stress_level": 0.0, "energy": 1.0, "mood": "neutral"}

        # Capabilities
        self._capabilities: list[AgentCapability] = []

        logger.info(
            f"SymbioticAgent {agent_id} initialized",
            extra={
                "organism_id": self._organism_id,
                "department": department,
                "tenant_id": tenant_id,
            },
        )

    async def initialize(self) -> bool:
        """Register with organism and start heartbeat."""
        try:
            # Register in organism registry
            await self._register_with_organism()

            # Start heartbeat
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # Start listening for signals
            self._listener_task = asyncio.create_task(self._listen_loop())

            logger.info(f"Agent {self.agent_id} registered with organism")
            return True

        except Exception as e:
            logger.error(f"Agent {self.agent_id} initialization failed: {e}")
            return False

    # OODA Loop Implementation
    @abstractmethod
    async def observe(
        self, signal: Signal
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Observe phase - gather data from signal.

        Args:
            signal: Incoming signal

        Returns:
            Observation data
        """
        pass

    @abstractmethod
    async def orient(
        self, observation: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Orient phase - analyze observation.

        Args:
            observation: Data from observe phase

        Returns:
            Oriented understanding
        """
        pass

    @abstractmethod
    async def decide(
        self, orientation: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """
        Decide phase - choose action.

        Args:
            orientation: Analysis from orient phase

        Returns:
            Decision identifier
        """
        pass

    @abstractmethod
    async def act(self, decision: str) -> ExecutionResult:
        """
        Act phase - execute decision.

        Args:
            decision: Action to take

        Returns:
            Execution result
        """
        pass

    async def execute_ooda(self, signal: Signal) -> ExecutionResult:
        """
        Execute full OODA loop.

        This is the main entry point for processing signals.
        """
        try:
            # Observe
            observation = await self.observe(signal)

            # Orient
            orientation = await self.orient(observation)

            # Decide
            decision = await self.decide(orientation)

            # Act
            result = await self.act(decision)

            # Emit result signal
            await self._emit_result(signal, result)

            return result

        except Exception as e:
            logger.error(f"OODA loop error: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e),
                task_id=getattr(signal.payload, "get", lambda x, y: "unknown")(
                    "task_id", "unknown"
                ),
            )

    # Communication helpers
    async def emit_signal(
        self,
        tier: SignalTier,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        target_agents: list[str] | None = None,
    ) -> str:
        """Emit signal to nervous system."""
        if self.signal_bus is None:
            raise RuntimeError("Signal bus not configured")

        signal = Signal(
            tenant_id=self.tenant_id,
            source_agent_id=self.agent_id,
            target_agent_ids=target_agents or [],
            tier=tier,
            payload=payload,
        )
        return await self.signal_bus.emit(signal)

    async def query_agents(
        self,
        target_agents: list[str],
        query_type: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout_ms: float = 5000,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Query other agents."""
        if self.signal_bus is None:
            raise RuntimeError("Signal bus not configured")

        return await self.signal_bus.query(
            source_agent=self.agent_id,
            target_agents=target_agents,
            query_type=query_type,
            payload=payload,
            timeout_ms=timeout_ms,
            tenant_id=self.tenant_id,
        )

    # Internal methods
    async def _register_with_organism(self) -> None:
        """Register agent in organism registry."""

        async with get_db_session() as session:
            registry_entry = OrganismRegistry(
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                agent_type=(
                    self.agent_type.value
                    if hasattr(self.agent_type, "value")
                    else str(self.agent_type)
                ),
                department=self.department,
                workload={"current_load": 0.0},
                emotional_state=self._emotional_state,
                status="healthy",
            )

            session.add(registry_entry)
            await session.commit()

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats."""
        while True:
            try:
                await asyncio.sleep(30)  # Every 30s

                # Update registry
                from sqlalchemy import update

                async with get_db_session() as session:
                    await session.execute(
                        update(OrganismRegistry)
                        .where(
                            OrganismRegistry.tenant_id == self.tenant_id,
                            OrganismRegistry.agent_id == self.agent_id,
                        )
                        .values(
                            last_heartbeat=datetime.now(timezone.utc),
                            workload={"current_load": self._get_load()},
                            emotional_state=self._emotional_state,
                        )
                    )
                    await session.commit()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

    async def _listen_loop(self) -> None:
        """Listen for incoming signals."""
        if self.signal_bus is None:
            logger.warning(
                f"Agent {self.agent_id}: Signal bus not configured, skipping listen loop"
            )
            return

        await self.signal_bus.listen(
            tenant_id=self.tenant_id,
            tier=SignalTier.COGNITIVE,
            handler=self._handle_signal,
        )

    async def _handle_signal(self, signal: Signal) -> None:
        """Handle incoming signal."""
        # Check if signal is for us
        if signal.target_agent_ids and self.agent_id not in signal.target_agent_ids:
            return

        # Execute OODA loop
        await self.execute_ooda(signal)

    async def _emit_result(self, original_signal: Signal, result: ExecutionResult) -> None:
        """Emit result signal."""
        if self.signal_bus is None:
            logger.debug(
                f"Agent {self.agent_id}: Signal bus not configured, skipping result emission"
            )
            return

        await self.emit_signal(
            tier=SignalTier.COGNITIVE,
            payload={
                "type": "task_result",
                "original_signal_id": original_signal.signal_id,
                "result": {
                    "success": result.success,
                    "data": result.result_data,
                    "error": result.error_message,
                },
            },
            target_agents=[original_signal.source_agent_id],
        )

    def _get_load(self) -> float:
        """Calculate current load (0.0 - 1.0)."""
        # Simple implementation - override in subclasses
        return 0.0

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._listener_task:
            self._listener_task.cancel()

        # Update status to zombie
        from sqlalchemy import update

        async with get_db_session() as session:
            await session.execute(
                update(OrganismRegistry)
                .where(
                    OrganismRegistry.tenant_id == self.tenant_id,
                    OrganismRegistry.agent_id == self.agent_id,
                )
                .values(status="zombie")
            )
            await session.commit()

        logger.info(f"Agent {self.agent_id} shutdown")
