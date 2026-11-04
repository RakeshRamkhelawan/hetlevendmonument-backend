"""
Multi-Agent Registry System
Manages discovery, registration, and coordination of all agents in the system
FASE 6: Converted to use database persistence
FASE 10: Added EU AI Act governance integration
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.models import RegisteredAgent  # Phase 6 Task 6: Migrated to domain module
from src.core.shared.interfaces import Agent, ExecutionResult, IAgentRegistryRepository, TaskData
from src.core.types import AgentType


logger = logging.getLogger(__name__)


def _infer_department(capabilities: Any) -> str:  # TODO(TYPE): replace Any with concrete type
    """Infer department from capability tags."""
    cap_list: list[str] = []
    if isinstance(capabilities, dict):
        cap_list = list(capabilities.keys())
    elif isinstance(capabilities, list):
        cap_list = [str(c) for c in capabilities]

    dept_map = {
        "ai": "DATA_AI_GOVERNANCE",
        "cloud": "OPERATIONS",
        "security": "IT_SECURITY",
        "sales": "SALES_MARKETING",
        "hr": "HR",
        "legal": "LEGAL_COMPLIANCE",
        "devops": "OPERATIONS",
        "data": "DATA_AI_GOVERNANCE",
    }
    for cap in cap_list:
        cap_lower = str(cap).lower()
        for key, dept in dept_map.items():
            if key in cap_lower:
                return dept
    return "GENERAL"


def _extract_capabilities(
    capabilities: Any,  # TODO(TYPE): replace Any with concrete type
) -> list[str]:  # TODO(TYPE): replace Any with concrete type
    """Normalize capabilities to list of strings."""
    if isinstance(capabilities, dict):
        return list(capabilities.keys())
    elif isinstance(capabilities, list):
        return [str(c) for c in capabilities]
    return []


class DatabaseAgentWrapper:
    """Wrapper for database agents to make them compatible with Agent interface"""

    def __init__(
        self,
        agent_dict: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        self.agent_id = agent_dict.get("agent_id", "")
        self.address = agent_dict.get("address", "")
        self.capabilities = agent_dict.get("capabilities", [])
        self._original = agent_dict

    async def process_task(self, task: TaskData) -> ExecutionResult:
        """Default task processing for database agents"""
        # S-2: use %s-style logging, not f-string
        logger.info("DatabaseAgent %s processing task %s", self.agent_id, task.id)
        return ExecutionResult(
            task_id=task.id,
            success=True,
            result_data={
                "agent_id": self.agent_id,
                "address": self.address,
                "task": task.title,
                "input": task.description,
            },
            execution_time=0.1,
            logs=["DatabaseAgent %s processed task" % self.agent_id],
        )


class AgentRegistry:
    """Central registry for all agents in the multi-agent system - Database persistent.

    EU AI Act Compliance: Optional OversightGate integration for pre-execution
    governance checks. When provided, all task distributions are validated
    against governance policies before execution.
    """

    def __init__(
        self,
        db_session: AsyncSession | None = None,
        oversight_gate: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        # S-3: optional tenant_id for contexts where ContextVar is unavailable
        tenant_id: int | None = None,
        repository: IAgentRegistryRepository | None = None,
    ) -> None:
        # In-memory cache for active agents (for performance)
        self._agents: dict[str, Agent] = {}
        self._agents_by_type: dict[AgentType, list[str]] = defaultdict(list)
        self._agent_capabilities: dict[str, set[str]] = defaultdict(set)

        # Health monitoring (still in-memory for real-time needs)
        self._agent_health: dict[str, datetime] = {}
        self._agent_load: dict[str, float] = defaultdict(float)
        # TODO(TYPE): replace Any with concrete type
        self._agent_stats: dict[str, dict[str, Any]] = (
            defaultdict(  # TODO(TYPE): replace Any with concrete type
                dict
            )
        )  # TODO(TYPE): replace Any with concrete type

        # Task routing (still in-memory for performance)
        self._active_tasks: dict[str, str] = {}  # task_id -> agent_id
        self._task_queue: list[TaskData] = []

        # Event callbacks
        self._event_callbacks: dict[str, list[Callable[..., Any]]] = defaultdict(
            list
        )  # TODO(TYPE): replace Any with concrete type

        # Database session for dependency injection (testing)
        self._db_session = db_session

        # Repository for structured DB access (ADR-034 -- preferred over raw db_session)
        self._repository = repository

        # EU AI Act: Oversight gate for governance
        self.oversight_gate = oversight_gate

        # S-3: store optional tenant_id for contexts without ContextVar middleware
        self._tenant_id = tenant_id

        # MEMORY LEAK FIX: Add background cleanup task
        self._cleanup_task: (
            # TODO(TYPE): replace Any with concrete type
            asyncio.Task[Any] | None
        ) = (  # TODO(TYPE): replace Any with concrete type
            None  # TODO(TYPE): replace Any with concrete type
        )
        self._max_task_queue_size = 1000  # Limit queue growth
        self._max_completed_tasks_history = 500  # Limit stats history

        logger.info(
            "AgentRegistry initialized with database persistence and memory leak protection"
        )

    async def register_agent(self, agent: Agent) -> bool:
        """Register a new agent in the system with database persistence"""
        try:
            agent_id = agent.agent_id
            agent_type = agent.agent_type

            # Get capabilities
            capabilities = await agent.get_capabilities()
            capabilities_dict = {cap.name: cap.description for cap in capabilities}

            # Get tenant_id from context (fallback to 1 for tests without middleware)
            import os

            from src.core.middleware.tenant_context import get_tenant_id

            tenant_id = get_tenant_id()
            if tenant_id is None:
                # Fall back to instance-level tenant_id if set (S-3)
                if self._tenant_id is not None:
                    tenant_id = self._tenant_id
                elif os.getenv("TESTING") == "1":
                    # In test mode without middleware, use default tenant
                    tenant_id = 1
                    logger.warning(
                        "No tenant context for agent registration, using default tenant_id=1 (TEST MODE)"
                    )
                else:
                    raise RuntimeError(
                        "Cannot register agent without tenant context. "
                        "Ensure TenantMiddleware is running and user is authenticated."
                    )

            # Store in database
            # Extract name/description from agent if available
            agent_name = getattr(agent, "name", None)
            agent_description = getattr(agent, "description", None)

            if self._repository is not None:
                # Repository path (ADR-034): no raw session, caller owns transaction
                existing_agent = await self._repository.get_registered_agent_by_agent_id(
                    agent_id, tenant_id
                )
                if existing_agent:
                    # C-6: UPDATE filtered on tenant_id to prevent cross-tenant writes
                    uv: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                        "address": str(agent.address),
                        "capabilities": capabilities_dict,
                        "last_heartbeat": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc),
                    }
                    if agent_name:
                        uv["name"] = agent_name
                    if agent_description:
                        uv["description"] = agent_description
                    await self._repository.update_agent(agent_id, tenant_id, uv)
                else:
                    new_record = RegisteredAgent(
                        agent_id=agent_id,
                        address=str(agent.address),
                        capabilities=capabilities_dict,
                        tenant_id=tenant_id,
                        last_heartbeat=datetime.now(timezone.utc),
                        **({"name": agent_name} if agent_name else {}),
                        **({"description": agent_description} if agent_description else {}),
                    )
                    await self._repository.register_agent(new_record)
            elif self._db_session is not None:
                # Legacy session path: direct session inject (e.g. tests with mock session)
                result = await self._db_session.execute(
                    select(RegisteredAgent).where(
                        RegisteredAgent.agent_id == agent_id,
                        RegisteredAgent.tenant_id == tenant_id,
                    )
                )
                existing_agent = result.scalar_one_or_none()
                if existing_agent:
                    update_values: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                        "address": str(agent.address),
                        "capabilities": capabilities_dict,
                        "tenant_id": tenant_id,
                        "last_heartbeat": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc),
                    }
                    if agent_name:
                        update_values["name"] = agent_name
                    if agent_description:
                        update_values["description"] = agent_description
                    stmt: Any = (  # TODO(TYPE): replace Any with concrete type
                        update(RegisteredAgent)
                        .where(
                            RegisteredAgent.agent_id == agent_id,
                            RegisteredAgent.tenant_id == tenant_id,
                        )
                        .values(**update_values)
                    )
                else:
                    insert_values: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                        "agent_id": agent_id,
                        "address": str(agent.address),
                        "capabilities": capabilities_dict,
                        "tenant_id": tenant_id,
                        "last_heartbeat": datetime.now(timezone.utc),
                    }
                    if agent_name:
                        insert_values["name"] = agent_name
                    if agent_description:
                        insert_values["description"] = agent_description
                    stmt = insert(RegisteredAgent).values(**insert_values)
                await self._db_session.execute(stmt)
                await self._db_session.flush()
            else:
                raise RuntimeError(
                    "AgentRegistry requires a repository or db_session for persistence."
                )

            # Store in memory cache
            self._agents[agent_id] = agent
            self._agents_by_type[agent_type].append(agent_id)
            self._agent_capabilities[agent_id] = {cap.name for cap in capabilities}

            # Initialize health tracking
            self._agent_health[agent_id] = datetime.now(timezone.utc)
            self._agent_load[agent_id] = 0.0

            # Initialize stats
            self._agent_stats[agent_id] = {
                "tasks_completed": 0,
                "tasks_failed": 0,
                "total_execution_time": 0.0,
                "average_response_time": 0.0,
                "registered_at": datetime.now(timezone.utc),
                "last_active": datetime.now(timezone.utc),
            }

            # I-3: %s-style logging
            logger.info("Agent registered in database: %s (type: %s)", agent_id, agent_type)
            await self._emit_event(
                "agent_registered",
                {
                    "agent_id": agent_id,
                    "agent_type": agent_type,
                    "capabilities": list(self._agent_capabilities[agent_id]),
                },
            )

            return True

        except Exception as e:
            # I-3 + I-4: %s-style + exc_info=True
            logger.error(
                "Failed to register agent %s: %s: %s",
                agent.agent_id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            return False

    async def get_agent_by_id(self, agent_id: str) -> Agent | None:
        """Retrieve agent instance from local cache or database."""
        # RC-005b: resolve tenant_id BEFORE cache check to enable isolation verification
        import os

        from src.core.middleware.tenant_context import get_tenant_id

        tenant_id = get_tenant_id()
        if tenant_id is None:
            if self._tenant_id is not None:
                tenant_id = self._tenant_id
            elif os.getenv("TESTING") == "1":
                tenant_id = 1
            else:
                raise RuntimeError(
                    "Cannot look up agent without tenant context. "
                    "Ensure TenantMiddleware is running and user is authenticated."
                )

        # Check in-memory cache with tenant verification (RC-005b)
        if agent_id in self._agents:
            cached_agent = self._agents[agent_id]
            if getattr(cached_agent, "tenant_id", None) == tenant_id:
                return cached_agent
            # tenant_id mismatch -- different tenant's agent in shared cache; skip to DB

        # Fall back to database for seeded/registered agents -- always filter by tenant_id
        try:
            db_agent: Any = None  # TODO(TYPE): replace Any with concrete type
            if self._repository is not None:
                db_agent = await self._repository.get_registered_agent_by_agent_id(
                    agent_id, tenant_id
                )
            elif self._db_session is not None:
                result = await self._db_session.execute(
                    select(RegisteredAgent).where(
                        RegisteredAgent.agent_id == agent_id,
                        RegisteredAgent.tenant_id == tenant_id,
                    )
                )
                db_agent = result.scalar_one_or_none()

            if db_agent:
                agent_dict = {
                    "agent_id": db_agent.agent_id,
                    "address": db_agent.address,
                    "capabilities": db_agent.capabilities or [],
                    "last_heartbeat": db_agent.last_heartbeat,
                }
                from typing import cast

                return cast(Agent, DatabaseAgentWrapper(agent_dict))
        except Exception as e:
            # I-3 + I-4: %s-style + exc_info=True
            logger.error(
                "Failed to retrieve agent %s from database: %s: %s",
                agent_id,
                type(e).__name__,
                e,
                exc_info=True,
            )

        return None

    async def get_all_agents(
        self, tenant_id: int
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get all registered agents from database for the given tenant.

        C-5: Always filter by tenant_id to prevent cross-tenant data leakage.
        """
        try:
            if self._repository is not None:
                db_records = await self._repository.get_registered_agents(tenant_id=tenant_id)
                agents = db_records
            elif self._db_session is not None:
                result = await self._db_session.execute(
                    select(RegisteredAgent).where(RegisteredAgent.tenant_id == tenant_id)
                )
                agents = list(result.scalars().all())
            else:
                raise RuntimeError(
                    "AgentRegistry requires a repository or db_session for get_all_agents."
                )

            agent_list: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for agent in agents:
                agent_list.append(
                    {
                        "agent_id": agent.agent_id,
                        "name": agent.name,  # Include name from database
                        "description": agent.description,  # Include description from database
                        "address": agent.address,
                        "capabilities": agent.capabilities,
                        "last_heartbeat": agent.last_heartbeat,
                        "created_at": agent.created_at,
                        "updated_at": agent.updated_at,
                    }
                )

            return agent_list

        except Exception as e:
            # I-3 + I-4: %s-style + exc_info=True
            logger.error(
                "Failed to get all agents from database: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
            return []

    async def get_discovery_agents(
        self, tenant_id: int
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get agents formatted for discovery API."""
        db_agents = await self.get_all_agents(tenant_id)

        # Async health checks OUTSIDE list comprehension
        health_checks = await asyncio.gather(
            *[self._is_agent_healthy(a["agent_id"]) for a in db_agents],
            return_exceptions=True,
        )

        return [
            {
                "agent_id": a["agent_id"],
                "name": a.get("name", a["agent_id"]),
                "department": _infer_department(a.get("capabilities", [])),
                "functions": _extract_capabilities(a.get("capabilities", [])),
                "description": a.get("description", ""),
                "status": "active" if (health_checks[i] is True) else "inactive",
            }
            for i, a in enumerate(db_agents)
        ]

    async def find_best_agent_for_task(self, task: TaskData) -> Agent | None:
        """Find the best available agent for a specific task"""
        try:
            # Get task requirements from metadata
            task.metadata.get("type", "general")
            required_capabilities = task.metadata.get("capabilities", [])
            preferred_agent_type = task.metadata.get("agent_type")
            preferred_agent_id = task.metadata.get("agent_id")

            if preferred_agent_id:
                preferred_agent = await self.get_agent_by_id(preferred_agent_id)
                if preferred_agent and await self._is_agent_healthy(preferred_agent_id):
                    return preferred_agent
                logger.warning(
                    "Preferred agent %s unavailable; falling back to best match",
                    preferred_agent_id,
                )

            # Resolve tenant_id for all downstream calls in this method
            from src.core.middleware.tenant_context import get_tenant_id as _get_tid

            _raw_tid = _get_tid()
            resolved_tenant_id = _raw_tid if _raw_tid is not None else self._tenant_id

            candidate_agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            # If specific agent type is preferred, check those first
            if preferred_agent_type:
                try:
                    agent_type = AgentType(preferred_agent_type)
                    candidate_agents = await self.get_agents_by_type(
                        agent_type, tenant_id=resolved_tenant_id
                    )
                except ValueError:
                    # I-3: %s-style logging
                    logger.warning("Unknown agent type requested: %s", preferred_agent_type)

            # If no candidates yet, check by capabilities
            if not candidate_agents and required_capabilities:
                for capability in required_capabilities:
                    agents_with_cap = await self.get_agents_with_capability(
                        capability, tenant_id=resolved_tenant_id
                    )
                    candidate_agents.extend(agents_with_cap)

            # If still no candidates, get all specialist agents
            if not candidate_agents:
                candidate_agents = await self.get_agents_by_type(
                    AgentType.SPECIALIST, tenant_id=resolved_tenant_id
                )
                # If no specialists, get CVA as fallback
                if not candidate_agents:
                    candidate_agents = await self.get_agents_by_type(
                        AgentType.CVA, tenant_id=resolved_tenant_id
                    )

            # Score agents based on load, performance, and availability
            if candidate_agents:
                scored_agents: list[tuple[float, Agent]] = []
                for agent in candidate_agents:
                    agent_id = agent.agent_id

                    # Check if agent is healthy and active
                    if not await self._is_agent_healthy(agent_id):
                        continue

                    # Calculate score (lower is better)
                    load_score = self._agent_load.get(agent_id, 0.0)
                    stats = self._agent_stats.get(agent_id, {})
                    performance_score = 1.0 - (
                        stats.get("tasks_completed", 0)
                        / max(
                            stats.get("tasks_completed", 0) + stats.get("tasks_failed", 0) + 1,
                            1,
                        )
                    )

                    total_score = load_score + performance_score
                    scored_agents.append((total_score, agent))

                if scored_agents:
                    # Return agent with best (lowest) score
                    scored_agents.sort(key=lambda x: x[0])
                    return scored_agents[0][1]

            # I-3: %s-style logging
            logger.warning("No suitable agent found for task: %s", task.id)
            return None

        except Exception as e:
            # I-3 + I-4: %s-style + exc_info=True
            logger.error(
                "Error finding agent for task %s: %s: %s",
                task.id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            return None

    async def distribute_task(self, task: TaskData) -> ExecutionResult | None:
        """Distribute task to the best available agent"""
        start_time = datetime.now(timezone.utc)
        try:
            # Find best agent
            agent = await self.find_best_agent_for_task(task)
            if not agent:
                # I-3: %s-style logging
                logger.error("No agent available for task: %s", task.id)
                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    error_message="No suitable agent available",
                    execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                )

            agent_id = agent.agent_id

            # EU AI Act: Pre-execution governance check
            if self.oversight_gate is not None:
                try:
                    # Get agent metadata from task or use defaults
                    agent_metadata = task.metadata or {}
                    oversight_result = await self.oversight_gate.check(
                        agent_name=agent_metadata.get("agent_name", agent_id),
                        agent_department=agent_metadata.get("department", "unknown"),
                        agent_specialisation=agent_metadata.get("specialisation", "general"),
                        agent_capabilities=agent_metadata.get("capabilities", []),
                        task_action=agent_metadata.get("action", "process_task"),
                        task_params=agent_metadata.get("params", {}),
                    )

                    if not oversight_result.allowed:
                        # I-3: %s-style logging
                        logger.warning(
                            "Task %s blocked by governance: %s",
                            task.id,
                            oversight_result.reason,
                        )
                        return ExecutionResult(
                            task_id=task.id,
                            success=False,
                            error_message="Blocked by governance: %s" % oversight_result.reason,
                            execution_time=(
                                datetime.now(timezone.utc) - start_time
                            ).total_seconds(),
                            result_data={
                                "blocked": True,
                                "governance_reason": oversight_result.reason,
                                "risk_level": oversight_result.risk_level.value,
                            },
                        )

                    if oversight_result.requires_human_approval:
                        # I-3: %s-style logging
                        logger.warning(
                            "Task %s requires human approval: %s",
                            task.id,
                            oversight_result.reason,
                        )
                        return ExecutionResult(
                            task_id=task.id,
                            success=False,
                            error_message="Pending human approval: %s" % oversight_result.reason,
                            execution_time=(
                                datetime.now(timezone.utc) - start_time
                            ).total_seconds(),
                            result_data={
                                "pending_approval": True,
                                "governance_reason": oversight_result.reason,
                                "risk_level": oversight_result.risk_level.value,
                            },
                        )

                except Exception as e:
                    # I-3 + I-4: %s-style + exc_info=True
                    logger.error(
                        "Governance check error for task %s: %s: %s",
                        task.id,
                        type(e).__name__,
                        e,
                        exc_info=True,
                    )
                    # Fail closed on governance error
                    return ExecutionResult(
                        task_id=task.id,
                        success=False,
                        error_message="Governance check error: %s" % e,
                        execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                        result_data={"error": "governance_failure"},
                    )

            # Track task assignment
            self._active_tasks[task.id] = agent_id
            self._agent_load[agent_id] += 0.1  # Increment load

            # I-3: %s-style logging
            logger.info("Distributing task %s to agent %s", task.id, agent_id)

            # Execute task
            try:
                result = await agent.process_task(task)

                # Update stats
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                stats = self._agent_stats[agent_id]

                # Initialize stats if not present
                if "tasks_completed" not in stats:
                    stats["tasks_completed"] = 0
                if "tasks_failed" not in stats:
                    stats["tasks_failed"] = 0
                if "total_execution_time" not in stats:
                    stats["total_execution_time"] = 0.0

                if result.success:
                    stats["tasks_completed"] += 1
                else:
                    stats["tasks_failed"] += 1

                stats["total_execution_time"] += execution_time
                stats["average_response_time"] = stats["total_execution_time"] / (
                    stats["tasks_completed"] + stats["tasks_failed"]
                )
                stats["last_active"] = datetime.now(timezone.utc)

                await self._emit_event(
                    "task_completed",
                    {
                        "task_id": task.id,
                        "agent_id": agent_id,
                        "success": result.success,
                        "execution_time": execution_time,
                    },
                )

                return result

            finally:
                # Clean up task tracking
                self._active_tasks.pop(task.id, None)
                self._agent_load[agent_id] = max(0.0, self._agent_load[agent_id] - 0.1)

        except Exception as e:
            # I-3 + I-4: %s-style + exc_info=True
            logger.error(
                "Error distributing task %s: %s: %s",
                task.id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message="Task distribution failed: %s" % e,
                execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
            )

    async def get_agents_by_type(
        self, agent_type: AgentType, tenant_id: int | None = None
    ) -> list[Agent]:
        """Get all agents of a specific type from cache and database.

        C-5: tenant_id is required for database lookups; pass it explicitly.
        """
        agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Get from in-memory cache
        agent_ids = self._agents_by_type[agent_type]
        agents.extend([self._agents[aid] for aid in agent_ids if aid in self._agents])

        # Get from database for seeded agents (all seeded agents are specialists)
        try:
            if agent_type == AgentType.SPECIALIST:
                # C-5: resolve tenant_id; fall back to instance tenant_id
                resolved_tid = tenant_id if tenant_id is not None else self._tenant_id
                if resolved_tid is not None:
                    db_agents = await self.get_all_agents(resolved_tid)
                    for agent_dict in db_agents:
                        agents.append(cast(Agent, DatabaseAgentWrapper(agent_dict)))
                else:
                    logger.warning(
                        "get_agents_by_type called without tenant_id; skipping DB lookup"
                    )
        except Exception as e:
            # I-3 + I-4: %s-style + exc_info=True
            logger.warning(
                "Failed to get agents by type from database: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )

        return agents

    async def get_agents_with_capability(
        self, capability: str, tenant_id: int | None = None
    ) -> list[Agent]:
        """Get all agents that have a specific capability from cache and database.

        C-5: tenant_id filters DB query to the calling tenant.
        I-5: deduplicates results by agent_id.
        """
        matching_agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # I-5: track agent_ids already added to avoid duplicates
        seen_ids: set[str] = set()

        # Check in-memory cache
        for agent_id, capabilities in self._agent_capabilities.items():
            if capability in capabilities:
                if agent_id in self._agents:
                    matching_agents.append(self._agents[agent_id])
                    seen_ids.add(agent_id)

        # Check database for seeded agents
        try:
            # C-5: resolve tenant_id; fall back to instance tenant_id
            resolved_tid = tenant_id if tenant_id is not None else self._tenant_id
            if resolved_tid is not None:
                db_agents = await self.get_all_agents(resolved_tid)
                for agent_dict in db_agents:
                    a_id = agent_dict.get("agent_id", "")
                    # I-5: skip if already present from in-memory cache
                    if a_id in seen_ids:
                        continue
                    if agent_dict.get("capabilities") and capability in agent_dict.get(
                        "capabilities", []
                    ):
                        matching_agents.append(cast(Agent, DatabaseAgentWrapper(agent_dict)))
                        seen_ids.add(a_id)
            else:
                logger.warning(
                    "get_agents_with_capability called without tenant_id; skipping DB lookup"
                )
        except Exception as e:
            # I-3 + I-4: %s-style + exc_info=True
            logger.warning(
                "Failed to get agents with capability from database: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )

        return matching_agents

    async def get_system_status(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive system status"""
        total_agents = len(self._agents)

        # Calculate healthy agents properly (avoid async generator)
        healthy_agents = 0
        for aid in self._agents.keys():
            if await self._is_agent_healthy(aid):
                healthy_agents += 1

        agents_by_type: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for agent_type in AgentType:
            count = len(self._agents_by_type[agent_type])
            agents_by_type[agent_type.value] = count

        # Calculate system load
        total_load = sum(self._agent_load.values())
        avg_load = total_load / max(total_agents, 1)

        # Aggregate stats
        total_tasks_completed = sum(
            stats.get("tasks_completed", 0) for stats in self._agent_stats.values()
        )
        total_tasks_failed = sum(
            stats.get("tasks_failed", 0) for stats in self._agent_stats.values()
        )

        return {
            "total_agents": total_agents,
            "healthy_agents": healthy_agents,
            "agents_by_type": agents_by_type,
            "active_tasks": len(self._active_tasks),
            "system_load": avg_load,
            "tasks_completed": total_tasks_completed,
            "tasks_failed": total_tasks_failed,
            "success_rate": total_tasks_completed
            / max(total_tasks_completed + total_tasks_failed, 1)
            * 100,
            "uptime": datetime.now(timezone.utc).isoformat(),
        }

    async def _is_agent_healthy(self, agent_id: str) -> bool:
        """Check if agent is healthy (responded recently or is registered in database)"""
        # If agent has sent heartbeat, check it's recent
        if agent_id in self._agent_health:
            last_health = self._agent_health[agent_id]
            health_timeout = timedelta(minutes=5)  # 5 minute health timeout
            # I-1: use UTC-aware datetime for comparison
            return datetime.now(timezone.utc) - last_health < health_timeout

        # For database registered agents (seeded agents), consider them healthy by default
        # They haven't sent heartbeats yet but are registered and ready to execute
        try:
            agent = await self.get_agent_by_id(agent_id)
            if agent:
                return True  # Found in database, consider healthy
        except Exception:
            pass

        return False

    async def _emit_event(
        self,
        event_type: str,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Emit system event to registered callbacks"""
        try:
            if event_type in self._event_callbacks:
                for callback in self._event_callbacks[event_type]:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(data)
                        else:
                            callback(data)
                    except Exception as e:
                        # I-3 + I-4: %s-style + exc_info=True
                        logger.error(
                            "Event callback error for %s: %s: %s",
                            event_type,
                            type(e).__name__,
                            e,
                            exc_info=True,
                        )
        except Exception as e:
            # I-3 + I-4: %s-style + exc_info=True
            logger.error(
                "Error emitting event %s: %s: %s",
                event_type,
                type(e).__name__,
                e,
                exc_info=True,
            )

    # MEMORY LEAK FIX: Add cleanup methods
    async def start_background_cleanup(self) -> None:
        """Start background task for periodic memory cleanup"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            logger.info("Background cleanup task started")

    async def _periodic_cleanup(self) -> None:
        """Periodically clean up stale data to prevent memory leaks"""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes

                # I-1: UTC-aware datetime
                now = datetime.now(timezone.utc)
                cleanup_count = 0

                # Clean up unhealthy agents
                unhealthy_agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
                for agent_id, last_health in list(self._agent_health.items()):
                    if now - last_health > timedelta(hours=1):  # 1 hour threshold
                        unhealthy_agents.append(agent_id)

                for agent_id in unhealthy_agents:
                    await self._remove_agent(agent_id)
                    cleanup_count += 1

                # Clean up task queue if it grows too large
                if len(self._task_queue) > self._max_task_queue_size:
                    removed = len(self._task_queue) - self._max_task_queue_size
                    self._task_queue = self._task_queue[-self._max_task_queue_size :]
                    cleanup_count += removed
                    # I-3: %s-style logging
                    logger.warning("Task queue exceeded limit, removed %s old tasks", removed)

                if cleanup_count > 0:
                    # I-3: %s-style logging
                    logger.info("Cleanup completed: removed %s stale items", cleanup_count)

            except Exception as e:
                # I-3 + I-4: %s-style + exc_info=True
                logger.error(
                    "Error during periodic cleanup: %s: %s",
                    type(e).__name__,
                    e,
                    exc_info=True,
                )

    async def _remove_agent(self, agent_id: str) -> None:
        """Remove agent and clean up all related data"""
        try:
            # Remove from in-memory structures
            if agent_id in self._agents:
                agent = self._agents.pop(agent_id)
                agent_type = agent.agent_type

                # Remove from type mapping
                if agent_id in self._agents_by_type[agent_type]:
                    self._agents_by_type[agent_type].remove(agent_id)

            # Clean up all related data
            self._agent_capabilities.pop(agent_id, None)
            self._agent_health.pop(agent_id, None)
            self._agent_load.pop(agent_id, None)
            self._agent_stats.pop(agent_id, None)

            # Remove from database (C-6: filter on tenant_id)
            from src.core.middleware.tenant_context import get_tenant_id

            _ctxvar = get_tenant_id()
            resolved_tenant_id = _ctxvar if _ctxvar is not None else self._tenant_id
            if resolved_tenant_id is None:
                raise RuntimeError("Cannot remove agent: tenant_id is not available.")
            if self._repository is not None:
                await self._repository.delete_agent(agent_id, resolved_tenant_id)
            elif self._db_session is not None:
                stmt = delete(RegisteredAgent).where(
                    RegisteredAgent.agent_id == agent_id,
                    RegisteredAgent.tenant_id == resolved_tenant_id,
                )
                await self._db_session.execute(stmt)
                await self._db_session.flush()
            else:
                raise RuntimeError(
                    "AgentRegistry requires a repository or db_session for _remove_agent."
                )

            # I-3: %s-style logging
            logger.info("Agent removed from registry: %s", agent_id)

            await self._emit_event("agent_removed", {"agent_id": agent_id})

        except Exception as e:
            # I-3 + I-4: %s-style + exc_info=True
            logger.error(
                "Error removing agent %s: %s: %s",
                agent_id,
                type(e).__name__,
                e,
                exc_info=True,
            )

    async def shutdown(self) -> None:
        """Shutdown registry and cleanup resources"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("AgentRegistry shutdown completed")
