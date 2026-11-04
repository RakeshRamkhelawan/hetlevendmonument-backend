"""
DepartmentOrchestrator - 16:9 Enterprise Department Hierarchy

Transforms ALS 1.0 "Swarms" into permanent "Departments" with:
- Fixed specialized agents per department
- Local Fractal Memory (department-specific vector DB)
- Internal Token Economy (budget management)
- Cross-department A2A contracts
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.core.als.agents.departments.base_department_agent import DepartmentType
from src.core.als.agents.organism_registry import get_organism_registry
from src.core.als.infrastructure.signal_bus import Signal, SignalBus, SignalTier
from src.core.shared.interfaces import ExecutionResult, TaskData

logger = logging.getLogger("DepartmentOrchestrator")


class Department(Enum):
    """16:9 Enterprise Departments."""

    STRATEGY = "strategy"  # Strategy & Business
    OPERATIONS = "operations"  # Operations & Supply Chain
    OPERATIONS_SUPPLY_CHAIN = "operations_supply_chain"  # Full name for compatibility
    FINANCE = "finance"  # Finance & Treasury
    HR = "hr"  # HR & Culture
    SALES_MARKETING = "sales_marketing"
    PRODUCT_INNOVATION = "product_innovation"  # R&D
    IT_SECURITY = "it_security"
    LEGAL_COMPLIANCE = "legal_compliance"
    CUSTOMER_EXPERIENCE = "customer_experience"
    DATA_AI_GOVERNANCE = "data_ai_governance"


@dataclass
class DepartmentBudget:
    """Internal Token Economy for a department.

    Each department has a compute budget ("prana") that agents
    spend to execute tasks. This creates natural resource limits
    and incentivizes efficiency.
    """

    department: Department
    total_prana: int = 10000  # Total compute budget
    allocated_prana: int = 0  # Currently allocated
    spent_prana: int = 0  # Actually spent
    cycle_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cycle_duration_hours: int = 24  # Budget cycle

    # Cost multipliers per agent type
    agent_costs: dict[str, int] = field(
        default_factory=lambda: {
            "ml": 10,  # ML inference cost
            "llm": 50,  # LLM generation cost
            "vision": 100,  # Vision processing cost
            "hybrid": 75,  # Hybrid agent cost
        }
    )

    def get_available_prana(self) -> int:
        """Get remaining compute budget."""
        return self.total_prana - self.allocated_prana

    def can_afford(self, agent_type: str, num_calls: int = 1) -> bool:
        """Check if department can afford N calls of agent type."""
        cost = self.agent_costs.get(agent_type, 10) * num_calls
        return cost <= self.get_available_prana()

    def allocate(self, agent_type: str, num_calls: int = 1) -> bool:
        """Allocate budget for agent calls."""
        cost = self.agent_costs.get(agent_type, 10) * num_calls
        if cost <= self.get_available_prana():
            self.allocated_prana += cost
            return True
        return False

    def spend(self, agent_type: str, num_calls: int = 1) -> None:
        """Mark allocated budget as actually spent."""
        cost = self.agent_costs.get(agent_type, 10) * num_calls
        self.spent_prana += cost
        # Note: We don't reduce allocated_prana here to track overruns

    def release_allocation(self, agent_type: str, num_calls: int = 1) -> None:
        """Release allocated budget (task cancelled)."""
        cost = self.agent_costs.get(agent_type, 10) * num_calls
        self.allocated_prana = max(0, self.allocated_prana - cost)

    def reset_cycle(self) -> None:
        """Reset budget for new cycle."""
        self.spent_prana = 0
        self.allocated_prana = 0
        self.cycle_start = datetime.now(timezone.utc)


@dataclass
class FractalMemory:
    """Department-specific vector database for collective memory.

    Unlike the global collective memory, FractalMemory stores
    department-internal knowledge and embeddings.
    """

    department: Department
    tenant_id: int

    # Memory categories
    patterns: dict[str, Any] = field(default_factory=dict)  # Learned patterns  # TODO(TYPE): replace Any with concrete type
    decisions: list[dict[str, Any]] = field(default_factory=list)  # Past decisions  # TODO(TYPE): replace Any with concrete type
    embeddings: dict[str, list[float]] = field(default_factory=dict)  # Vector storage

    async def store_pattern(self, pattern_id: str, pattern: Any, embedding: list[float]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Store a learned pattern with its embedding."""
        self.patterns[pattern_id] = {
            "data": pattern,
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "access_count": 0,
        }
        self.embeddings[pattern_id] = embedding

    async def retrieve_similar(self, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Retrieve top-k similar patterns using cosine similarity."""
        from numpy import dot
        from numpy.linalg import norm

        results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for pattern_id, emb in self.embeddings.items():
            similarity = dot(query_embedding, emb) / (norm(query_embedding) * norm(emb))
            results.append((pattern_id, similarity))

        # Sort by similarity (descending)
        results.sort(key=lambda x: x[1], reverse=True)

        # Return top-k with full data
        return [
            {"pattern_id": pid, "similarity": sim, "data": self.patterns.get(pid, {})}
            for pid, sim in results[:top_k]
        ]

    async def store_decision(self, decision: dict[str, Any], context: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Store a decision for future reference."""
        self.decisions.append(
            {
                "decision": decision,
                "context": context,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Keep only last 1000 decisions (fractal compression)
        if len(self.decisions) > 1000:
            self.decisions = self.decisions[-1000:]


@dataclass
class SwarmTeam:
    """Dynamic team formation within a department.

    Swarms are temporary formations for specific micro-tasks,
    formed within the context of a permanent department.
    """

    swarm_id: str
    department: Department
    task_type: str
    agents: list[str] = field(default_factory=list)
    formed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_seconds: int = 3600  # Time to live

    def is_expired(self) -> bool:
        """Check if swarm has expired."""
        elapsed = (datetime.now(timezone.utc) - self.formed_at).total_seconds()
        return elapsed > self.ttl_seconds


class DepartmentOrchestrator:
    """
    DepartmentOrchestrator - Manages a 16:9 Enterprise Department.

    Sits between ChiefOrchestrator (enterprise level) and individual agents.

    Responsibilities:
    - Manage department-specific agents (4 per department)
    - Handle internal task routing
    - Maintain Fractal Memory
    - Enforce budget constraints
    - Form SwarmTeams for micro-tasks
    - Negotiate A2A contracts with other departments

    Example:
        dept = DepartmentOrchestrator(
            department=Department.FINANCE,
            tenant_id=123,
            signal_bus=signal_bus
        )
        await dept.initialize()

        # Route task to best agent in department
        result = await dept.route_task(task_data)
    """

    def __init__(
        self,
        department: Department,
        tenant_id: int,
        signal_bus: SignalBus,
        chief_orchestrator_id: str = "chief_orchestrator",
    ) -> None:
        self.department = department
        self.tenant_id = tenant_id
        self.signal_bus = signal_bus
        self.chief_orchestrator_id = chief_orchestrator_id

        # Department resources
        self.budget = DepartmentBudget(department=department)
        self.memory = FractalMemory(department=department, tenant_id=tenant_id)

        # Agent management
        self.agents: dict[str, dict[str, Any]] = {}  # agent_id -> metadata  # TODO(TYPE): replace Any with concrete type
        self.swarm_teams: dict[str, SwarmTeam] = {}

        # Task routing
        self._task_queue: asyncio.PriorityQueue[tuple[int, Any]] = asyncio.PriorityQueue()  # TODO(TYPE): replace Any with concrete type
        self._active_tasks: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

        # State
        self._initialized = False
        self._monitor_task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type

        logger.info(
            "DepartmentOrchestrator initialized",
            extra={"department": department.value, "tenant_id": tenant_id},
        )

    async def initialize(self) -> bool:
        """Initialize department orchestrator."""
        try:
            # Load agents from organism registry
            await self._load_department_agents()

            # Start budget monitoring
            self._monitor_task = asyncio.create_task(self._budget_monitor())

            # Start signal listener for department-specific signals
            asyncio.create_task(self._listen_for_signals())

            self._initialized = True
            logger.info(
                "DepartmentOrchestrator ready",
                extra={
                    "department": self.department.value,
                    "agent_count": len(self.agents),
                },
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize department: {e}")
            return False

    def _map_to_department_type(self, dept: Department) -> DepartmentType:
        """Map local Department enum to DepartmentType used by organism registry."""
        mapping = {
            Department.STRATEGY: DepartmentType.STRATEGY_BUSINESS,
            Department.OPERATIONS: DepartmentType.OPERATIONS_SUPPLY_CHAIN,
            Department.OPERATIONS_SUPPLY_CHAIN: DepartmentType.OPERATIONS_SUPPLY_CHAIN,
            Department.FINANCE: DepartmentType.FINANCE_TREASURY,
            Department.HR: DepartmentType.HR_CULTURE,
            Department.SALES_MARKETING: DepartmentType.SALES_MARKETING,
            Department.PRODUCT_INNOVATION: DepartmentType.PRODUCT_INNOVATION,
            Department.IT_SECURITY: DepartmentType.IT_SECURITY,
            Department.LEGAL_COMPLIANCE: DepartmentType.LEGAL_COMPLIANCE,
            Department.CUSTOMER_EXPERIENCE: DepartmentType.CUSTOMER_EXPERIENCE,
            Department.DATA_AI_GOVERNANCE: DepartmentType.DATA_AI_GOVERNANCE,
        }
        return mapping.get(dept, DepartmentType.STRATEGY_BUSINESS)

    async def _load_department_agents(self) -> None:
        """Load agents belonging to this department."""
        registry = get_organism_registry()
        dept_type = self._map_to_department_type(self.department)
        department_agents = registry.get_department_agents(dept_type)

        for reg in department_agents:
            self.agents[reg.agent_id] = {
                "agent_class": reg.agent_class,
                "technology": reg.technology.value,
                "priority": reg.priority.value,
                "human_role": reg.human_role,
                "status": "idle",
                "current_load": 0.0,
            }

    async def route_task(
        self, task: TaskData, source_department: Department | None = None
    ) -> ExecutionResult:
        """
        Route task to best agent in department.

        If source_department is different from self.department,
        this is a cross-department request that requires A2A contract.
        """
        # Check cross-department contract if needed
        if source_department and source_department != self.department:
            can_execute = await self._check_cross_dept_permission(source_department, task)
            if not can_execute:
                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    error_message=f"No A2A contract with {source_department.value}",
                )

        # Check budget
        agent_type = self._infer_agent_type(task)
        if not self.budget.can_afford(agent_type):
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"Department {self.department.value} budget exhausted",
            )

        # Select best agent
        best_agent = self._select_best_agent(task, agent_type)
        if not best_agent:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"No available agents in {self.department.value}",
            )

        # Allocate budget
        self.budget.allocate(agent_type)

        # Route via signal bus
        signal = Signal(
            tenant_id=self.tenant_id,
            source_agent_id=f"dept_{self.department.value}",
            target_agent_ids=[best_agent],
            tier=SignalTier.COGNITIVE,
            payload={
                "action": "execute_task",
                "task": task.model_dump(),
                "department": self.department.value,
            },
        )

        await self.signal_bus.emit(signal)

        return ExecutionResult(
            task_id=task.id,
            success=True,
            result_data={
                "status": "routed",
                "department": self.department.value,
                "assigned_agent": best_agent,
                "budget_remaining": self.budget.get_available_prana(),
            },
        )

    async def form_swarm(
        self, task_type: str, required_capabilities: list[str], ttl_seconds: int = 3600
    ) -> SwarmTeam | None:
        """
        Form a temporary SwarmTeam within the department.

        Swarms are for micro-tasks like M&A due diligence
        within Finance department.
        """
        import uuid

        # Find agents with required capabilities
        matching_agents: list[str] = []
        for agent_id, meta in self.agents.items():
            if meta["status"] == "idle":
                # Check capability match (simplified)
                if meta["technology"] in required_capabilities:
                    matching_agents.append(agent_id)

        if len(matching_agents) < 2:
            logger.warning(f"Not enough agents for swarm in {self.department.value}")
            return None

        swarm = SwarmTeam(
            swarm_id=str(uuid.uuid4()),
            department=self.department,
            task_type=task_type,
            agents=matching_agents[:4],  # Max 4 agents per swarm
            ttl_seconds=ttl_seconds,
        )

        self.swarm_teams[swarm.swarm_id] = swarm

        logger.info(
            "Swarm formed",
            extra={
                "swarm_id": swarm.swarm_id,
                "department": self.department.value,
                "agents": matching_agents,
            },
        )

        return swarm

    def get_department_health(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get health status of department."""
        return {
            "department": self.department.value,
            "tenant_id": self.tenant_id,
            "total_agents": len(self.agents),
            "idle_agents": sum(1 for a in self.agents.values() if a["status"] == "idle"),
            "busy_agents": sum(1 for a in self.agents.values() if a["status"] == "busy"),
            "budget_available": self.budget.get_available_prana(),
            "budget_total": self.budget.total_prana,
            "active_swarms": len(self.swarm_teams),
            "memory_patterns": len(self.memory.patterns),
        }

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info(f"DepartmentOrchestrator {self.department.value} shutdown")

    # Internal methods

    def _select_best_agent(self, task: TaskData, agent_type: str) -> str | None:
        """Select best agent based on load and capability."""
        candidates = [
            (aid, meta)
            for aid, meta in self.agents.items()
            if meta["status"] == "idle" and meta["technology"] == agent_type
        ]

        if not candidates:
            return None

        # Select lowest load
        best = min(candidates, key=lambda x: x[1]["current_load"])
        return best[0]

    def _infer_agent_type(self, task: TaskData) -> str:
        """Infer required agent type from task."""
        task_type = task.type.lower()

        if any(x in task_type for x in ["image", "visual", "design", "ui"]):
            return "vision"
        elif any(x in task_type for x in ["predict", "forecast", "classify", "analyze"]):
            return "ml"
        elif any(x in task_type for x in ["generate", "write", "reason", "plan"]):
            return "llm"
        else:
            return "hybrid"

    async def _check_cross_dept_permission(self, source_dept: Department, task: TaskData) -> bool:
        """Check if cross-department request is allowed."""
        # This will integrate with A2A Contract Manager
        # For now, allow all cross-dept requests
        return True

    async def _budget_monitor(self) -> None:
        """Monitor budget and reset cycles."""
        while True:
            try:
                await asyncio.sleep(3600)  # Check every hour

                # Check if cycle needs reset
                elapsed = (datetime.now(timezone.utc) - self.budget.cycle_start).total_seconds()
                if elapsed > (self.budget.cycle_duration_hours * 3600):
                    self.budget.reset_cycle()
                    logger.info(f"Budget cycle reset for {self.department.value}")

                # Clean up expired swarms
                expired = [sid for sid, swarm in self.swarm_teams.items() if swarm.is_expired()]
                for sid in expired:
                    del self.swarm_teams[sid]

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Budget monitor error: {e}")

    async def _listen_for_signals(self) -> None:
        """Listen for department-specific signals."""
        # Listen on department-specific channel
        channel = f"dept:{self.tenant_id}:{self.department.value}"

        # This would subscribe to Redis channel
        # Implementation depends on SignalBus integration
        pass
