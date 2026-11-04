"""
MasterOrchestratorAgent -- Central conductor for the SanskritiSetu multi-agent system.

Responsibilities:
- Accepts high-level goals and decomposes them into sub-tasks
- Delegates sub-tasks to the right specialist agents via AgentRouterAgent
- Tracks progress, handles failures, and retries with alternate agents
- Pipes every ExecutionResult through CriticAgent (ADVISORY mode) for quality telemetry
- Emits structured SystemEvents for observability

Architecture note:
  MasterOrchestratorAgent does NOT execute tasks itself -- it only plans,
  delegates, monitors, and synthesises. Execution always stays with specialists.

M-MDP compliance: sync planning logic, async I/O (delegation, monitoring).
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import redis

    from src.core.agents.agent_router_agent import AgentRouterAgent
    from src.core.agents.performance_optimizer import ParallelExecutor
    from src.core.shared.interfaces import AsyncSessionFactory

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.agents.mixins.critic_mixin import CriticMixin, CriticMode

# Performance optimization imports
try:
    from src.core.agents.performance_optimizer import ParallelExecutor, cached, get_executor, timed

    HAS_OPTIMIZER = True
except ImportError:
    HAS_OPTIMIZER = False

from src.core.agents.llm_types import (
    AgentCategory,
    AgentProfile,
    TaskComplexity,
    agent_model_matcher,
)
from src.core.observability.metrics import master_orchestrator_workflow_duration_seconds
from src.core.shared.interfaces import AgentCapability, ExecutionResult, TaskData
from src.core.types import AgentType

logger = logging.getLogger(__name__)


# --- Supporting types ---


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"  # some sub-tasks failed, others succeeded


@dataclass
class SubTask:
    """A single decomposed unit of work within a workflow."""

    sub_task_id: str
    parent_workflow_id: str
    title: str
    description: str
    required_capabilities: list[str]
    priority: int = 5
    dependencies: list[str] = field(default_factory=list)
    assigned_agent_id: str | None = None
    status: str = "pending"
    result: ExecutionResult | None = None
    attempts: int = 0
    max_attempts: int = 2


@dataclass
class WorkflowPlan:
    """Decomposed workflow produced by the planner."""

    workflow_id: str
    goal: str
    sub_tasks: list[SubTask]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: WorkflowStatus = WorkflowStatus.PENDING
    metadata: dict[str, object] = field(default_factory=dict)


class MasterOrchestratorAgent(CriticMixin, EnhancedBaseAgent):
    """
    Central orchestrator that plans, delegates, and synthesises multi-agent workflows.

    Usage:
        orchestrator = MasterOrchestratorAgent(tenant_id=tenant_id)
        await orchestrator.initialize()
        # Uses EnhancedBaseAgent.process_task -> _execute_task
        result = await orchestrator.process_task(task)  # task.description = high-level goal

    The task.parameters may include:
        "workflow_mode"  -> "sequential" | "parallel" | "auto" (default: "auto")
        "max_agents"     -> int, max concurrent agent calls (default: 5)
        "critic_mode"    -> "SILENT" | "ADVISORY" (default: "SILENT" for subtasks)
    """

    def __init__(
        self,
        agent_id: str = "master_orchestrator_001",
        tenant_id: int = 1,
        async_session_factory: AsyncSessionFactory | None = None,
        redis_client: "redis.Redis | None" = None,  # type: ignore[type-arg]
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.ORCHESTRATOR,
            tenant_id=tenant_id,
        )
        # CriticMixin: ADVISORY -- orchestrator outputs are high-value, critique async
        self.__init_critic__(mode=CriticMode.ADVISORY, score_threshold=0.60)

        self.specialization = "multi_agent_workflow_orchestration"

        # Active workflows: workflow_id -> WorkflowPlan
        self._active_workflows: dict[str, WorkflowPlan] = {}
        self._workflow_lock = asyncio.Lock()

        # Agent router (lazy import to avoid circular deps)
        self._router: AgentRouterAgent | None = None

        # Session factory + Redis client injected from the application layer (ADR-034:
        # agents never import src.core.database/src.core.database.redis directly).
        # Passed through to the AgentRouterAgent singleton in _get_router() so
        # agent-discovery and the cross-worker routing cache work regardless of
        # which call-site creates that singleton first (SP-ADR023-002 Dag 1
        # FA-NEW-001, Dag 2 redis_client).
        self._async_session_factory: AsyncSessionFactory | None = async_session_factory
        self._redis_client: Any | None = redis_client  # TODO(TYPE): replace Any with concrete type

        # Parallel execution (optimized)
        self._executor: ParallelExecutor | None = None
        self._max_concurrent_tasks = 10

        # Workflow cache for idempotent retries
        self._workflow_cache: dict[str, WorkflowPlan] = {}
        self._cache_ttl_seconds = 3600  # 1 hour

        # Metrics
        self._workflows_total = 0
        self._workflows_succeeded = 0
        self._subtasks_delegated = 0
        self._parallel_executions = 0
        self._sequential_executions = 0

        self._register_agent_profile()
        logger.info("MasterOrchestratorAgent %s initialised (tenant=%d)", agent_id, tenant_id)

    def _register_agent_profile(self) -> None:
        profile = AgentProfile(
            agent_type="orchestrator",
            category=AgentCategory.STRATEGIC,
            typical_complexity=TaskComplexity.COMPLEX,
            reasoning_required=0.95,
            speed_priority=0.6,
            cost_sensitivity=0.5,
            context_needs=4000,
            special_requirements=["orchestration", "planning", "reasoning"],
        )
        agent_model_matcher.register_agent_profile(profile)

    async def initialize(self) -> bool:
        logger.info("MasterOrchestratorAgent %s ready (using fallback chain)", self.agent_id)
        return True

    async def get_capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name="workflow_orchestration",
                description="Decomposes complex goals into sub-tasks and orchestrates multi-agent execution",
                input_types=["complex_task", "multi_step_task"],
                output_types=["synthesized_result", "execution_report"],
                resource_requirements={"llm": "required", "cpu": "0.5"},
            ),
            AgentCapability(
                name="task_delegation",
                description="Routes sub-tasks to specialist agents via capability-based matching",
                input_types=["sub_task"],
                output_types=["delegated_result"],
                resource_requirements={"agent_registry": "required"},
            ),
            AgentCapability(
                name="result_synthesis",
                description="Aggregates results from multiple specialist agents into a cohesive output",
                input_types=["partial_results"],
                output_types=["synthesized_output"],
                resource_requirements={"cpu": "0.2"},
            ),
        ]

    # --- Primary interface ---

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """
        Accept a high-level goal, plan, delegate, and synthesise the result.
        This method is the standard EnhancedBaseAgent interface entry point.
        """
        start = time.perf_counter()
        workflow_id = str(uuid.uuid4())
        self._workflows_total += 1

        try:
            # 1. Plan: decompose goal into sub-tasks (sync LLM call -> M-MDP)
            plan = await self._plan_workflow(workflow_id, task)

            async with self._workflow_lock:
                self._active_workflows[workflow_id] = plan

            # 2. Execute: delegate sub-tasks (async)
            mode = task.parameters.get("workflow_mode", "auto")
            results = await self._execute_plan(plan, mode)

            # 3. Synthesise: merge sub-results into final output
            synthesis = self._synthesise_results(plan, results)

            plan.status = (
                WorkflowStatus.SUCCEEDED
                if all(r.success for r in results)
                else WorkflowStatus.PARTIAL
            )
            if plan.status == WorkflowStatus.SUCCEEDED:
                self._workflows_succeeded += 1

            elapsed = round((time.perf_counter() - start) * 1000, 1)
            logger.info(
                "MasterOrchestratorAgent workflow %s completed in %s ms (%s)",
                workflow_id,
                elapsed,
                plan.status.value,
            )
            master_orchestrator_workflow_duration_seconds.labels(
                tenant_id=str(self.tenant_id), status=plan.status.value
            ).observe(time.perf_counter() - start)

            return ExecutionResult(
                task_id=task.id,
                success=True,
                result_data={
                    "workflow_id": workflow_id,
                    "status": plan.status.value,
                    "sub_tasks_count": len(plan.sub_tasks),
                    "synthesis": synthesis,
                    "sub_results": [
                        {
                            "task": st.title,
                            "success": st.result.success if st.result else False,
                        }
                        for st in plan.sub_tasks
                    ],
                },
                execution_time=(time.perf_counter() - start),
            )

        except Exception as exc:
            logger.error(
                "MasterOrchestratorAgent workflow %s failed: %s: %s",
                workflow_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            master_orchestrator_workflow_duration_seconds.labels(
                tenant_id=str(self.tenant_id), status=WorkflowStatus.FAILED.value
            ).observe(time.perf_counter() - start)
            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data={"error": str(exc), "workflow_id": workflow_id},
                execution_time=(time.perf_counter() - start),
            )
        finally:
            async with self._workflow_lock:
                self._active_workflows.pop(workflow_id, None)

    # --- Planning (sync domain logic -- M-MDP) ---

    async def _plan_workflow(self, workflow_id: str, task: TaskData) -> WorkflowPlan:
        """Use LLM to decompose the goal into an ordered list of sub-tasks."""
        import json
        import re
        from src.core.agents.prompt_guard import PromptGuard, Action
        from src.core.services.llm.tenant_deur import TenantTaalmodel
        from src.core.agents.budget_manager import BudgetManager

        # Check budget before planning (Blocker 2)
        session_factory = getattr(self, "_async_session_factory", None)
        if session_factory:
            async with session_factory() as session:
                budget = BudgetManager(session=session, redis_client=self._redis_client)
                check_res = await budget.check_budget(
                    tenant_id=self.tenant_id,
                    agent_id=self.agent_id,
                    estimated_tokens=2000,
                )
                if not check_res.allowed:
                    logger.warning("Planning blocked by budget: %s", check_res.reason)
                    return WorkflowPlan(
                        workflow_id=workflow_id,
                        goal=task.title,
                        sub_tasks=[
                            SubTask(
                                sub_task_id=f"{workflow_id}_st_0",
                                parent_workflow_id=workflow_id,
                                title=task.title,
                                description=task.description,
                                required_capabilities=list(task.metadata.get("capabilities", [])),
                                priority=int(task.metadata.get("priority", 5)),
                            )
                        ],
                    )

        # Sanitize inputs via PromptGuard instance (ADR-015)
        guard = PromptGuard()
        title_scan = await guard.scan_input(task.title)
        desc_scan = await guard.scan_input(task.description)
        safe_title = title_scan.sanitized_text
        safe_desc = desc_scan.sanitized_text

        if title_scan.action == Action.BLOCK or desc_scan.action == Action.BLOCK:
            logger.warning("Prompt injection detected and blocked in orchestrator task.")
            # Return single-task fallback with sanitized content
            return WorkflowPlan(
                workflow_id=workflow_id,
                goal=safe_title,
                sub_tasks=[
                    SubTask(
                        sub_task_id=f"{workflow_id}_st_0",
                        parent_workflow_id=workflow_id,
                        title=safe_title,
                        description=safe_desc,
                        required_capabilities=list(task.metadata.get("capabilities", [])),
                        priority=int(task.metadata.get("priority", 5)),
                    )
                ],
            )

        # Fix MINOR-4: Truncate JSON string explicitly avoiding partial parse issues
        context_str = json.dumps(task.parameters, default=str)
        if len(context_str) > 500:
            context_str = context_str[:497] + "..."

        prompt = f"""You are an expert workflow planner for a multi-agent AI system.
Decompose the following goal into 2-6 concrete sub-tasks that different specialist agents can execute.

Goal: {safe_title}
Details: {safe_desc}
Context: {context_str}

Respond ONLY with valid JSON -- no markdown, no explanation:
{{
  "sub_tasks": [
    {{
      "title": "<short action title>",
      "description": "<what the agent should do>",
      "required_capabilities": ["<cap1>", "<cap2>"],
      "priority": <1-10>,
      "depends_on": []
    }}
  ]
}}"""

        sub_tasks: list[SubTask] = []
        try:
            # Het model van de TENANT van deze orkestrator (brief 2026-10-20, ADR-041 B14); hier stond de
            # platformketen. Een storing valt hieronder terug op EEN taak (geen ander model).
            raw = await TenantTaalmodel(self.tenant_id).tekst(prompt, max_tokens=2000)
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                for i, st in enumerate(parsed.get("sub_tasks", [])):
                    sub_tasks.append(
                        SubTask(
                            sub_task_id=f"{workflow_id}_st_{i}",
                            parent_workflow_id=workflow_id,
                            title=st.get("title", f"Sub-task {i}"),
                            description=st.get("description", ""),
                            required_capabilities=st.get("required_capabilities", []),
                            priority=int(st.get("priority", 5)),
                            dependencies=st.get("depends_on", []),
                        )
                    )
        except Exception as exc:
            logger.warning("LLM planning failed, using single-task fallback: %s", exc)

        # Fallback: treat entire task as one sub-task
        if not sub_tasks:
            sub_tasks = [
                SubTask(
                    sub_task_id=f"{workflow_id}_st_0",
                    parent_workflow_id=workflow_id,
                    title=safe_title,
                    description=safe_desc,
                    required_capabilities=list(task.metadata.get("capabilities", [])),
                    priority=int(task.metadata.get("priority", 5)),
                )
            ]

        return WorkflowPlan(
            workflow_id=workflow_id,
            goal=safe_title,
            sub_tasks=sub_tasks,
        )

    # --- Execution (async I/O -- M-MDP) ---

    async def _execute_plan(self, plan: WorkflowPlan, mode: str) -> list[ExecutionResult]:
        """Delegate sub-tasks to agents. Supports sequential, parallel, auto."""
        plan.status = WorkflowStatus.RUNNING
        results: list[ExecutionResult] = []

        # Topological sort: tasks with no unresolved deps go first
        ordered = self._topological_sort(plan.sub_tasks)

        if mode == "parallel" or (mode == "auto" and len(ordered) > 1):
            self._parallel_executions += 1
            results = await self._execute_parallel(ordered)
        else:
            self._sequential_executions += 1
            results = await self._execute_sequential(ordered)

        return results

    async def _execute_parallel(self, sub_tasks: list[SubTask]) -> list[ExecutionResult]:
        """Execute sub-tasks in parallel with concurrency limiting."""
        if HAS_OPTIMIZER and self._executor:
            # Use optimized parallel executor
            task_fns = [lambda st=st: self._delegate_sub_task(st) for st in sub_tasks]
            return cast(
                list[ExecutionResult],
                await self._executor.execute(task_fns),  # pyright: ignore[reportArgumentType]
            )
        else:
            # Fallback: basic asyncio.gather with semaphore
            semaphore = asyncio.Semaphore(self._max_concurrent_tasks)

            async def _execute_with_limit(st: SubTask) -> ExecutionResult:
                async with semaphore:
                    return await self._delegate_sub_task(st)

            coros = [_execute_with_limit(st) for st in sub_tasks]
            return list(await asyncio.gather(*coros, return_exceptions=False))

    async def _execute_sequential(self, sub_tasks: list[SubTask]) -> list[ExecutionResult]:
        """Execute sub-tasks sequentially."""
        results: list[ExecutionResult] = []
        for st in sub_tasks:
            result = await self._delegate_sub_task(st)
            results.append(result)

            # Early termination if critical task fails
            if not result.success and st.priority >= 9:
                logger.warning("Critical sub-task %s failed, stopping workflow", st.sub_task_id)
                break

        return results

    async def _delegate_sub_task(self, sub_task: SubTask) -> ExecutionResult:
        """Route one sub-task to the best available agent."""
        self._subtasks_delegated += 1
        sub_task.attempts += 1
        sub_task.status = "running"

        task_data = TaskData(
            id=sub_task.sub_task_id,
            title=sub_task.title,
            description=sub_task.description,
            metadata={
                "type": "orchestrated_subtask",
                "priority": sub_task.priority,
                "capabilities": sub_task.required_capabilities,
            },
            assigned_to=sub_task.assigned_agent_id,
        )

        try:
            # importlib avoids direct ImportFrom (DSM boundary agent_runtime -> governance)
            gov_mod = importlib.import_module("src.core.governance.governance_helper")

            allowed, reason = await gov_mod.apply_governance_check(
                agent_name=self.agent_id,
                task_action="delegate_sub_task",
                agent_department="orchestration",
                agent_specialisation="workflow_planning",
                agent_capabilities=sub_task.required_capabilities,
                task_params={
                    "task_id": sub_task.sub_task_id,
                    "title": sub_task.title,
                    "tenant_id": self.tenant_id,
                },
            )
            if not allowed:
                raise ValueError(f"Governance block on sub-task: {reason}")

            router = self._get_router()
            result = await router.route_and_execute(task_data)
            sub_task.result = result
            sub_task.status = "completed" if result.success else "failed"
            # CriticAgent evaluation via CriticMixin -- ADVISORY mode (configured in __init__)
            # Stores critique asynchronously, does not block caller (per critic_mixin.py:140-143)
            try:
                result = await self.post_process_task(result, task_id=sub_task.sub_task_id)
            except Exception as critic_exc:
                logger.warning(
                    "CriticAgent post_process_task failed, continuing: %s: %s",
                    type(critic_exc).__name__,
                    critic_exc,
                    exc_info=True,
                )
            return result
        except Exception as exc:
            logger.warning(
                "Sub-task %s delegation failed: %s: %s",
                sub_task.sub_task_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            fallback = ExecutionResult(
                task_id=sub_task.sub_task_id,
                success=False,
                result_data={"error": str(exc)},
                execution_time=0.0,
            )
            sub_task.result = fallback
            sub_task.status = "failed"
            return fallback

    # --- Synthesis (sync -- M-MDP) ---

    def _synthesise_results(
        self, plan: WorkflowPlan, results: list[ExecutionResult]
    ) -> dict[str, object]:
        """Merge sub-task results into a coherent summary."""
        succeeded = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        return {
            "goal": plan.goal,
            "total_sub_tasks": len(results),
            "succeeded": len(succeeded),
            "failed": len(failed),
            "outputs": [r.result_data for r in succeeded if r.result_data],
            "errors": [r.result_data.get("error") for r in failed if r.result_data],
        }

    def _topological_sort(self, sub_tasks: list[SubTask]) -> list[SubTask]:
        """Return sub-tasks ordered by dependency resolution (Kahn's algorithm)."""
        id_map = {st.sub_task_id: st for st in sub_tasks}
        in_degree: dict[str, int] = {st.sub_task_id: 0 for st in sub_tasks}
        for st in sub_tasks:
            for dep in st.dependencies:
                if dep in in_degree:
                    in_degree[st.sub_task_id] += 1

        queue = [st for st in sub_tasks if in_degree[st.sub_task_id] == 0]
        ordered: list[SubTask] = []
        while queue:
            current = queue.pop(0)
            ordered.append(current)
            for st in sub_tasks:
                if current.sub_task_id in st.dependencies:
                    in_degree[st.sub_task_id] -= 1
                    if in_degree[st.sub_task_id] == 0:
                        queue.append(st)

        # Append any remaining (cycle-safe fallback)
        seen = {st.sub_task_id for st in ordered}
        for st in sub_tasks:
            if st.sub_task_id not in seen:
                ordered.append(st)
        return ordered

    def _get_router(self) -> AgentRouterAgent:
        """Lazy-load AgentRouterAgent singleton.

        Passes through self._async_session_factory and self._redis_client
        (SP-ADR023-002 Dag 1 FA-NEW-001, Dag 2) -- without them, a tenant whose
        FIRST router access happens through an orchestrated workflow (this
        call-site) rather than an /orchestration/* HTTP request would
        permanently lock that tenant's singleton without DB-backed
        agent-discovery or the cross-worker routing cache, since the singleton
        keeps whichever factory/client the first caller provided. Both are
        injected via __init__ (ADR-034: agents never import src.core.database
        or src.core.database.redis directly) -- see get_master_orchestrator()
        below and its callers.
        """
        if self._router is None:
            from src.core.agents.agent_router_agent import get_agent_router

            self._router = get_agent_router(
                self.tenant_id,
                async_session_factory=self._async_session_factory,
                redis_client=self._redis_client,
            )
        return self._router

    # --- Observability ---

    def metrics(self) -> dict[str, object]:
        total_executions = self._parallel_executions + self._sequential_executions
        parallel_ratio = (
            self._parallel_executions / total_executions if total_executions > 0 else 0.0
        )

        return {
            "workflows_total": self._workflows_total,
            "workflows_succeeded": self._workflows_succeeded,
            "subtasks_delegated": self._subtasks_delegated,
            "active_workflows": len(self._active_workflows),
            "parallel_executions": self._parallel_executions,
            "sequential_executions": self._sequential_executions,
            "parallel_ratio": round(parallel_ratio, 3),
            "success_rate": (
                round(self._workflows_succeeded / self._workflows_total, 3)
                if self._workflows_total
                else 0.0
            ),
            "cache_size": len(self._workflow_cache),
        }

    async def clear_cache(self) -> int:
        """Clear workflow cache and return cleared count."""
        count = len(self._workflow_cache)
        self._workflow_cache.clear()
        logger.info("Cleared %d cached workflows", count)
        return count

    def get_workflow_plan(self, workflow_id: str) -> WorkflowPlan | None:
        """Return an active workflow plan if present."""
        return self._active_workflows.get(workflow_id)

    def get_active_workflow_count(self) -> int:
        """Return number of active workflows."""
        return len(self._active_workflows)


# --- Singleton ---

_instances: dict[int, MasterOrchestratorAgent] = {}
_instances_lock = threading.Lock()


def get_master_orchestrator(
    tenant_id: int = 1,
    async_session_factory: AsyncSessionFactory | None = None,
    redis_client: Any | None = None,  # TODO(TYPE): replace Any with concrete type
) -> MasterOrchestratorAgent:
    """Return the per-tenant MasterOrchestratorAgent singleton.

    Pass async_session_factory (e.g. get_db_session from
    src.core.database.session) so _get_router() can wire it into the
    AgentRouterAgent it delegates to (SP-ADR023-002 Dag 1, FA-NEW-001). Pass
    redis_client (e.g. get_redis_client from src.core.database.redis) for the
    same reason on the cross-worker routing cache (SP-ADR023-002 Dag 2). Wire
    both from the application layer -- never from agents/ (ADR-034). Has no
    effect if the instance is already cached (first-creation-wins, same
    semantics as agent_router_agent.get_agent_router()).
    """
    with _instances_lock:
        if tenant_id not in _instances:
            _instances[tenant_id] = MasterOrchestratorAgent(
                agent_id=f"master_orchestrator_{tenant_id:03d}",
                tenant_id=tenant_id,
                async_session_factory=async_session_factory,
                redis_client=redis_client,
            )
        return _instances[tenant_id]


def clear_orchestrator_instance(tenant_id: int) -> None:
    """Evict a tenant's cached MasterOrchestratorAgent instance (call on suspend/delete).

    Called from src.core.api.v1.orchestration.dependencies.clear_tenant_cache()
    -- mirrors agent_router_agent.clear_router_instance() (SP-ADR023-002 Dag 1).
    """
    with _instances_lock:
        _instances.pop(tenant_id, None)
