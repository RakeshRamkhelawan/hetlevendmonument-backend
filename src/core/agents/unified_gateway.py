"""
Unified Agent Execution Gateway
Phase A Implementation: Consolidate all 6 execution paths through single gateway
All execution must pass through mandatory governance pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, cast
from collections.abc import Callable, Awaitable

from pydantic import BaseModel, Field

from src.core.agents.agent_registry import AgentRegistry

if TYPE_CHECKING:
    from src.core.ethics.ethics_gate import EthicsGate
from src.core.shared.interfaces import ExecutionResult, TaskData
from src.core.tool_broker.resilience import CircuitBreaker, CircuitBreakerConfig
from src.core.types import AgentType

logger = logging.getLogger(__name__)


class ExecutionDeadline(BaseModel):
    """Deadline contract for execution propagation."""

    deadline: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    timeout_seconds: float = 300.0  # Default 5 minutes
    soft_timeout_seconds: float | None = None  # Graceful shutdown before hard timeout


class UnifiedAgentGatewayConfig(BaseModel):
    """Configuration for the unified gateway."""

    enable_ethics_gate: bool = True
    enable_oversight_gate: bool = True
    enable_authority_check: bool = True
    enable_circuit_breaker: bool = True
    default_timeout_seconds: float = 300.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout_seconds: float = 60.0


class UnifiedAgentGateway:
    """
    Single execution gateway for all agent execution paths.

    Mandatory pipeline:
    1. Ethics Gate check
    2. Oversight Gate check
    3. Authority validation
    4. Circuit breaker check
    5. Agent execution with deadline propagation
    6. Audit logging
    """

    def __init__(
        self,
        registry: AgentRegistry,
        ethics_gate: EthicsGate | None = None,
        oversight_gate: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        config: UnifiedAgentGatewayConfig | None = None,
    ):
        self.registry = registry
        if ethics_gate is None:
            import importlib

            _eg_mod = importlib.import_module("src.core.ethics.ethics_gate")
            # TODO(TYPE): replace Any with concrete type
            self.ethics_gate: Any = (
                _eg_mod.EthicsGate()
            )  # TODO(TYPE): replace Any with concrete type
        else:
            self.ethics_gate = ethics_gate
        self.oversight_gate: Any | None = (  # TODO(TYPE): replace Any with concrete type
            oversight_gate  # TODO(TYPE): replace Any with concrete type
        )
        self.config = config or UnifiedAgentGatewayConfig()

        # Circuit breaker for agent execution (per agent type)
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

        if self.config.enable_oversight_gate and self.oversight_gate is None:
            logger.warning(
                "[GATEWAY] oversight_gate=None while enable_oversight_gate=True -- "
                "EU AI Act oversight check SKIPPED. Inject OversightGate via constructor."
            )
        logger.info("UnifiedAgentGateway initialized")

    def _get_circuit_breaker(self, agent_id: str) -> CircuitBreaker:
        """Get or create circuit breaker for agent."""
        if agent_id not in self._circuit_breakers:
            config = CircuitBreakerConfig(
                failure_threshold=self.config.circuit_breaker_failure_threshold,
                reset_timeout_seconds=int(self.config.circuit_breaker_recovery_timeout_seconds),
            )
            self._circuit_breakers[agent_id] = CircuitBreaker(
                name=f"agent_execution_{agent_id}",
                config=config,
            )
        return self._circuit_breakers[agent_id]

    @staticmethod
    def _agent_value(
        agent: Any, key: str, default: Any = None
    ) -> (
        # TODO(TYPE): replace Any with concrete type
        Any
    ):  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        """Read a field from either dict-like or object-like agent records."""
        if isinstance(agent, dict):
            return agent.get(key, default)
        return getattr(agent, key, default)

    async def _apply_ethics_gate(self, task: TaskData) -> None:
        """Ethics compliance check (mandatory)."""
        if not self.config.enable_ethics_gate:
            return

        logger.info(f"[GATEWAY] Applying ethics gate for task {task.id}")
        try:
            # Evaluate task description for ethical compliance
            evaluation = await self.ethics_gate.evaluate(
                content=task.description,
                context={"agent_id": task.agent_id, "tenant_id": task.tenant_id},
            )

            if evaluation.level.value == "blocked":
                raise ValueError(f"Ethics gate blocked task: {evaluation.concerns}")

            logger.debug(f"[GATEWAY] Ethics gate PASSED for task {task.id}")
        except Exception as e:
            logger.error(f"[GATEWAY] Ethics gate FAILED: {e}")
            raise

    async def _apply_oversight_gate(self, task: TaskData) -> None:
        """EU AI Act governance check (mandatory)."""
        if not self.config.enable_oversight_gate:
            return
        if self.oversight_gate is None:
            raise ValueError(
                "OversightGate is enabled (enable_oversight_gate=True) but no gate was "
                "injected. Inject OversightGate via constructor or set enable_oversight_gate=False."
            )

        logger.info(f"[GATEWAY] Applying oversight gate for task {task.id}")
        try:
            # Get agent details from registry if available
            agent = await self.registry.get_agent_by_id(task.agent_id) if task.agent_id else None
            agent_name = task.agent_id or "unknown"
            agent_department = "general"
            agent_specialisation = "specialist"
            agent_capabilities = []

            if agent:
                agent_name = self._agent_value(agent, "name", task.agent_id)
                agent_department = self._agent_value(agent, "department", "general")
                agent_specialisation = self._agent_value(agent, "specialisation", "specialist")
                agent_capabilities = self._agent_value(agent, "capabilities", [])

            # Check oversight gate
            result = await self.oversight_gate.check(
                agent_name=agent_name,
                agent_department=agent_department,
                agent_specialisation=agent_specialisation,
                agent_capabilities=agent_capabilities,
                task_action=task.title or "execute",
                task_params=task.metadata or {},
                tenant_id=task.tenant_id,
            )

            if not result.allowed:
                raise ValueError(f"Oversight gate blocked: {result.reason}")

            if result.requires_human_approval:
                raise ValueError(f"Oversight gate requires human approval: {result.reason}")

            logger.debug(f"[GATEWAY] Oversight gate PASSED for task {task.id}")
        except Exception as e:
            logger.error(f"[GATEWAY] Oversight gate FAILED: {e}")
            raise

    async def _check_authority(
        self,
        task: TaskData,
        agent_type: AgentType,
        agent: object,
    ) -> None:
        """Agent authority/capability check."""
        if not self.config.enable_authority_check:
            return

        logger.info(f"[GATEWAY] Checking authority for {agent_type} on task {task.id}")

        # Minimal authority matrix hardening.
        high_authority_agents = {
            AgentType.CVA,
            AgentType.ORCHESTRATOR,
            AgentType.COORDINATOR,
            AgentType.AUTONOMOUS,
        }
        restricted_action = bool((task.metadata or {}).get("restricted_action"))
        if restricted_action and agent_type not in high_authority_agents:
            raise ValueError(
                "Authority check failed: restricted action requires orchestrator-level agent"
            )

        required_capability = (task.metadata or {}).get("required_capability")
        if required_capability:
            capabilities = set(self._agent_value(agent, "capabilities", []) or [])
            if required_capability not in capabilities:
                raise ValueError(
                    f"Authority check failed: missing required capability '{required_capability}'"
                )

        logger.debug(f"[GATEWAY] Authority check PASSED for task {task.id}")

    async def _apply_governance_pipeline(self, task: TaskData) -> None:
        """Apply mandatory governance pipeline sequentially."""
        logger.info(f"[GATEWAY] Starting governance pipeline for task {task.id}")

        # 1. Ethics gate
        await self._apply_ethics_gate(task)

        # 2. Oversight gate
        await self._apply_oversight_gate(task)

        # 3. Authority check
        if not task.agent_id:
            raise ValueError("Authority check failed: task missing agent_id")

        agent = await self.registry.get_agent_by_id(task.agent_id)
        if not agent:
            raise ValueError(f"Authority check failed: unknown agent '{task.agent_id}'")
        agent_type = self._agent_value(agent, "agent_type", AgentType.SPECIALIST)
        await self._check_authority(task, agent_type, agent)

        logger.info(f"[GATEWAY] Governance pipeline PASSED for task {task.id}")

    async def _check_circuit_breaker(self, agent_id: str) -> None:
        """Check if agent circuit breaker is healthy."""
        if not self.config.enable_circuit_breaker:
            return

        breaker = self._get_circuit_breaker(agent_id)
        state = breaker.get_state()
        if state["state"] == "open":
            raise RuntimeError(
                f"Circuit breaker OPEN for agent {agent_id}. "
                f"Failures: {state['failure_count']}, "
                f"State changed: {state['state_change_time']}"
            )

    async def _propagate_deadline(self, task: TaskData) -> ExecutionDeadline:
        """Extract or create execution deadline."""
        if (
            hasattr(task, "execution_deadline")
            and task.execution_deadline
            and isinstance(task.execution_deadline, datetime)
        ):
            # Calculate timeout based on deadline
            now = datetime.now(timezone.utc)
            remaining = (task.execution_deadline - now).total_seconds()
            timeout = max(1.0, remaining)  # At least 1 second
            return ExecutionDeadline(
                deadline=task.execution_deadline,
                timeout_seconds=timeout,
            )

        deadline = ExecutionDeadline(timeout_seconds=self.config.default_timeout_seconds)
        return deadline

    async def execute(
        self,
        task: TaskData,
        executor: Callable[[TaskData], ExecutionResult],
    ) -> ExecutionResult:
        """
        Main execution gateway.

        Args:
            task: Task to execute
            executor: Async callable that performs actual execution

        Returns:
            ExecutionResult with outcome and timing

        Raises:
            ValueError: If governance gates fail
            RuntimeError: If circuit breaker is open
            asyncio.TimeoutError: If execution exceeds deadline
        """
        execution_start = datetime.now(timezone.utc)
        logger.info(f"[GATEWAY] execute() START for task {task.id}, agent {task.agent_id}")

        try:
            if not task.agent_id:
                raise ValueError("Task missing required agent_id")

            # 1. Apply governance pipeline (mandatory)
            await self._apply_governance_pipeline(task)

            # 2. Check circuit breaker
            await self._check_circuit_breaker(task.agent_id)

            # 3. Propagate deadline
            deadline = await self._propagate_deadline(task)

            # 4. Execute with timeout through circuit breaker
            logger.info(
                f"[GATEWAY] Executing agent {task.agent_id} with "
                f"timeout {deadline.timeout_seconds}s"
            )

            # Wrap executor with circuit breaker protection
            breaker = self._get_circuit_breaker(task.agent_id)

            async def protected_execute() -> ExecutionResult:
                return await asyncio.wait_for(
                    cast(Awaitable[ExecutionResult], executor(task)),
                    timeout=deadline.timeout_seconds,
                )

            result = await breaker.call(protected_execute)

            execution_time = (datetime.now(timezone.utc) - execution_start).total_seconds()
            logger.info(f"[GATEWAY] execute() SUCCESS for task {task.id} ({execution_time:.2f}s)")

            # Executor may return ExecutionResult or a plain dict; both are valid
            if isinstance(result, ExecutionResult):
                result_data = result.result_data
            elif isinstance(result, dict):
                result_data = result
            else:
                result_data = None

            return ExecutionResult(
                task_id=task.id,
                success=True,
                result_data=result_data,
                execution_time=execution_time,
            )

        except TimeoutError:
            execution_time = (datetime.now(timezone.utc) - execution_start).total_seconds()
            logger.error(f"[GATEWAY] TIMEOUT for task {task.id} after {execution_time:.2f}s")

            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data=None,
                execution_time=execution_time,
                error_message=f"Execution timed out after {execution_time:.2f}s",
            )

        except (ValueError, RuntimeError) as e:
            execution_time = (datetime.now(timezone.utc) - execution_start).total_seconds()
            logger.error(f"[GATEWAY] GOVERNANCE/CIRCUIT BREAKER FAILURE: {e}")

            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data=None,
                execution_time=execution_time,
                error_message=str(e),
            )

        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - execution_start).total_seconds()
            logger.exception(f"[GATEWAY] UNEXPECTED ERROR: {e}")

            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data=None,
                execution_time=execution_time,
                error_message=f"Unexpected error: {str(e)}",
            )

    def get_breaker_status(self, agent_id: str) -> dict[str, object]:
        """Get circuit breaker status for an agent."""
        breaker = self._get_circuit_breaker(agent_id)
        return breaker.get_state()

    def get_all_breaker_statuses(self) -> dict[str, dict[str, object]]:
        """Get circuit breaker statuses for all agents."""
        return {
            agent_id: breaker.get_state() for agent_id, breaker in self._circuit_breakers.items()
        }
