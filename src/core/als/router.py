"""
AgentRouterAgent - Two-phase intelligent task routing.

Phase 1: DeterministicRouter selects department (O(1), no LLM).
Phase 2: RouterService selects specific agent via 5-tier strategy.
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.core.exceptions.exceptions import SanskritiError
from src.core.shared.interfaces import TaskData
from src.core.typing import AsyncRedisClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and dataclasses
# ---------------------------------------------------------------------------


class RoutingTier(str, Enum):
    CACHE_MEMORY = "cache_memory"
    CACHE_REDIS = "cache_redis"
    CAPABILITY = "capability"
    LLM = "llm"
    FALLBACK = "fallback"


@dataclass
class RoutingDecision:
    agent_id: str
    agent_class: type  # DepartmentAgent subclass; forward ref avoided (imported below)
    department: object  # Department enum value
    confidence: float
    tier_used: RoutingTier
    routing_latency_ms: float
    attempted_tiers: list[RoutingTier] = field(default_factory=list)
    reasoning: str | None = None


@dataclass
class RouterStats:
    cache_hit_rate: float
    llm_fallback_count: int
    avg_latency_ms: float
    total_requests: int


class RoutingError(SanskritiError):
    def __init__(
        self,
        tenant_id: int,
        task_type: str,
        attempted_tiers: list[RoutingTier],
    ) -> None:
        self.tenant_id = tenant_id
        self.task_type = task_type
        self.attempted_tiers = attempted_tiers
        super().__init__(f"No agent found for task '{task_type}' (tenant={tenant_id})")


class GatekeeperRoutingError(SanskritiError):
    """Raised when Gatekeeper blocks a task from being routed.

    ADR-017: Deterministic policy enforcement integration with routing.
    """

    def __init__(
        self,
        tenant_id: int,
        task_id: str,
        decision: str,
        reason: str,
        hitl_ticket_ref: str | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.task_id = task_id
        self.decision = decision
        self.reason = reason
        self.hitl_ticket_ref = hitl_ticket_ref
        msg = f"Gatekeeper {decision} task '{task_id}' (tenant={tenant_id}): {reason}"
        super().__init__(msg)


class AgentUnhealthyError(SanskritiError):
    """Raised when all candidate agents are unhealthy/disabled.

    ADR-023: Health-aware routing - fail fast when no healthy agents available.
    """

    def __init__(
        self,
        tenant_id: int,
        task_id: str,
        department: str,
        unhealthy_agents: list[str],
    ) -> None:
        self.tenant_id = tenant_id
        self.task_id = task_id
        self.department = department
        self.unhealthy_agents = unhealthy_agents
        msg = (
            f"No healthy agents for task '{task_id}' in {department} "
            f"(tenant={tenant_id}). Unhealthy: {unhealthy_agents}"
        )
        super().__init__(msg)


from src.core.als.agents.departments.base_department_agent import DepartmentType

# ---------------------------------------------------------------------------
# Department enum mapping (mirrors DepartmentOrchestrator._map_to_department_type)
# ---------------------------------------------------------------------------
from src.core.als.enterprise.departments.department_orchestrator import Department
from src.core.als.enterprise.departments.deterministic_router import DeterministicRouter
from src.core.als.agents.organism_registry import AgentRegistration, OrganismRegistry

_DEPT_TO_DEPT_TYPE: dict[Department, DepartmentType] = {
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
# Verify mapping is complete at import time
assert set(Department) <= set(_DEPT_TO_DEPT_TYPE), (
    "Incomplete _DEPT_TO_DEPT_TYPE mapping - add missing Department values"
)

# ---------------------------------------------------------------------------
# Static capability map: agent_id -> keywords for capability matching tier
# ---------------------------------------------------------------------------
_AGENT_CAPABILITIES: dict[str, frozenset[str]] = {
    # Finance & Treasury
    "forecasting_agent": frozenset({"forecast", "predict", "financial", "budget", "revenue"}),
    "accounts_receivable_payable": frozenset(
        {"invoice", "payment", "receivable", "payable", "billing"}
    ),
    "audit_compliance": frozenset({"audit", "compliance", "sox", "gaap", "ifrs"}),
    "tax_compliance": frozenset({"tax", "vat", "gst", "filing", "deduction"}),
    # Legal & Compliance
    "contract_analysis": frozenset({"contract", "clause", "legal", "review", "agreement"}),
    "contract_lifecycle": frozenset({"contract", "lifecycle", "renewal", "expiry", "management"}),
    "gdpr_privacy_guard": frozenset({"gdpr", "privacy", "data_protection", "consent", "dsar"}),
    "regulatory_tracking": frozenset({"regulation", "regulatory", "compliance", "policy", "law"}),
    # Add remaining agents as needed during implementation
    # NOTE: agent_id here must match AgentRegistration.agent_id in OrganismRegistry
}


# ---------------------------------------------------------------------------
# RouterService
# ---------------------------------------------------------------------------
import os

from cachetools import TTLCache

_CACHE_TTL = 300  # 5 minutes
_CACHE_MAX = 500  # max LRU entries
_LLM_TIMEOUT = float(os.getenv("ROUTING_LLM_TIMEOUT_SECONDS", "10"))
_CONFIDENCE_CACHE_THRESHOLD = 0.50
_STATS_WINDOW = 50  # rolling window size per ADR-023


class RouterService:
    """
    Core routing logic. All methods are async.
    Instantiate with sync __init__, then call await initialize() before use.
    """

    def __init__(
        self,
        tenant_id: int,
        redis_client: AsyncRedisClient | None,
        registry: OrganismRegistry | None,
        llm_client: Any,  # NOTE: no shared LLM interface -- genuinely polymorphic  # TODO(TYPE): replace Any with concrete type
        gatekeeper: Any = None,  # ADR-017: Optional Gatekeeper for policy enforcement
        health_monitor: Any = None,  # ADR-023: Optional health monitor for health-aware routing
    ) -> None:
        self._tenant_id = tenant_id
        self._redis = redis_client
        self._registry = registry
        self._llm = llm_client
        self._gatekeeper = gatekeeper  # ADR-017: Deterministic policy enforcement
        self._health_monitor = health_monitor  # ADR-023: Health-aware routing

        # Memory LRU cache (per-worker, intentional - Redis provides cross-node)
        self._mem_cache: TTLCache[str, RoutingDecision] = TTLCache[str, RoutingDecision](
            maxsize=_CACHE_MAX, ttl=_CACHE_TTL
        )

        # Rolling stats window (last 50 requests)
        self._latencies: list[float] = []
        self._total_requests = 0
        self._cache_hits = 0
        self._llm_fallback_count = 0

    async def initialize(self) -> bool:
        """Warm up: verify Redis connectivity."""
        try:
            if self._redis is None:
                return True
            await self._redis.ping()
            logger.info("RouterService initialized", extra={"tenant_id": self._tenant_id})
            return True
        except Exception as exc:
            logger.warning(
                "Redis unavailable on init: %s", exc, extra={"tenant_id": self._tenant_id}
            )
            return True  # degrade gracefully - memory cache still works

    def _build_cache_key(self, task: TaskData) -> str:
        """Build deterministic SHA-256 cache key from tenant + task."""
        raw = f"{self._tenant_id}:{task.title}:{task.description[:512]}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _build_cache_key_with_department(self, task: TaskData, department: object) -> str:
        """Task #3: Build deterministic cache key including department filter.

        Args:
            task: The task being routed
            department: Department enum value for filtering

        Returns:
            SHA-256 hex digest including department constraint
        """
        dept_str = department.value if isinstance(department, Enum) else str(department)
        raw = f"{self._tenant_id}:{task.title}:{task.description[:512]}:dept={dept_str}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get_stats(self) -> RouterStats:
        """Return rolling stats (last 50 requests)."""
        window = self._latencies[-_STATS_WINDOW:]
        avg = sum(window) / len(window) if window else 0.0
        hit_rate = self._cache_hits / self._total_requests if self._total_requests else 0.0
        return RouterStats(
            cache_hit_rate=hit_rate,
            llm_fallback_count=self._llm_fallback_count,
            avg_latency_ms=avg,
            total_requests=self._total_requests,
        )

    async def _check_gatekeeper(self, task: TaskData) -> GatekeeperRoutingError | None:
        """ADR-017: Check Gatekeeper policy enforcement before routing.

        Returns:
            GatekeeperRoutingError if task is blocked, None if allowed.
        """
        if self._gatekeeper is None:
            return None

        try:
            # Evaluate task through Gatekeeper (deterministic, no LLM)
            decision_record = await self._gatekeeper.evaluate_task(task)

            if decision_record.decision.value == "block":
                return GatekeeperRoutingError(
                    tenant_id=self._tenant_id,
                    task_id=task.id,
                    decision="block",
                    reason=f"Policy violation: {decision_record.policy_rules_failed}",
                )

            if decision_record.decision.value == "hitl":
                return GatekeeperRoutingError(
                    tenant_id=self._tenant_id,
                    task_id=task.id,
                    decision="hitl",
                    reason="Human-in-the-loop approval required",
                    hitl_ticket_ref=decision_record.hitl_ticket_ref,
                )

            # Task is allowed (or deferred - routing proceeds)
            return None

        except Exception as exc:
            # Log but continue: configure via GATEKEEPER_FAIL_OPEN env-var (SP-DLP-001)
            logger.error(
                "[ROUTE] Gatekeeper evaluation failed: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
                extra={"tenant_id": self._tenant_id, "task_id": task.id},
            )
            return None

    def _filter_healthy_agents(
        self, agents: list[AgentRegistration], department: str
    ) -> list[AgentRegistration]:
        """ADR-023: Filter out unhealthy/disabled agents.

        Args:
            agents: List of agent registrations
            department: Department name for error context

        Returns:
            List of healthy agents (empty if none healthy)

        Raises:
            AgentUnhealthyError: If all agents are unhealthy and strict mode enabled
        """
        if self._health_monitor is None:
            return agents

        healthy_agents = []
        unhealthy_agents: list[str] = []

        for agent in agents:
            agent_id = getattr(agent, "agent_id", None)
            if agent_id is None:
                healthy_agents.append(agent)
                continue

            # Check if agent is disabled or unhealthy
            if hasattr(self._health_monitor, "is_agent_available"):
                is_available = self._health_monitor.is_agent_available(agent_id)
            elif hasattr(self._health_monitor, "is_disabled"):
                is_available = not self._health_monitor.is_disabled(agent_id)
            else:
                # Health monitor doesn't support availability checks
                healthy_agents.append(agent)
                continue

            if is_available:
                healthy_agents.append(agent)
            else:
                unhealthy_agents.append(agent_id)
                logger.debug(
                    "[ROUTE] Skipping unhealthy agent: %s",
                    agent_id,
                    extra={"tenant_id": self._tenant_id, "agent_id": agent_id},
                )

        # Log warning if some agents were filtered
        if unhealthy_agents and healthy_agents:
            logger.warning(
                "[ROUTE] Filtered %d unhealthy agents: %s",
                len(unhealthy_agents),
                unhealthy_agents,
                extra={"tenant_id": self._tenant_id, "department": department},
            )

        return healthy_agents

    def _filter_agents_by_department(
        self,
        agents: list[AgentRegistration],
        target_department: Department,
    ) -> list[AgentRegistration]:
        """Task #3: Filter agents by department.

        Args:
            agents: List of agent registrations
            target_department: Department enum value to filter by

        Returns:
            List of agents in the specified department
        """
        filtered = []
        for agent in agents:
            agent_dept = getattr(agent, "department", None)
            if agent_dept == target_department:
                filtered.append(agent)
                logger.debug(
                    "[ROUTE] Department filter match: %s",
                    getattr(agent, "agent_id", "unknown"),
                    extra={"tenant_id": self._tenant_id, "department": target_department},
                )
        return filtered

    async def route(self, task: TaskData) -> RoutingDecision:
        """Main entry point. Two-phase routing with 5-tier strategy."""
        start = time.monotonic()
        attempted: list[RoutingTier] = []

        # ADR-017: Gatekeeper policy check BEFORE routing
        gatekeeper_error = await self._check_gatekeeper(task)
        if gatekeeper_error:
            raise gatekeeper_error

        cache_key = self._build_cache_key(task)

        # Phase 1: department selection
        department = DeterministicRouter().route(task.title, task.description)

        if department is None or department not in _DEPT_TO_DEPT_TYPE:
            logger.warning(
                "[ROUTE] unmapped department=%s", department, extra={"tenant_id": self._tenant_id}
            )
            dept_type = None
            agents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        else:
            dept_type = _DEPT_TO_DEPT_TYPE[department]
            # Client-side tenant isolation filter (spec Section 4 - P0 security requirement).
            # OrganismRegistry has no tenant_id param; filter post-lookup.
            # All current agents are platform-level (tenant_id=None) so this passes all through,
            # but the filter must be present to protect future per-tenant agent registrations.
            if self._registry is not None:
                all_agents = self._registry.list_agents(department=dept_type)
            else:
                all_agents = []
                agents = []
            agents = [
                a
                for a in all_agents
                if getattr(a, "tenant_id", None) is None
                or getattr(a, "tenant_id", None) == self._tenant_id
            ]

            # ADR-023: Filter out unhealthy/disabled agents
            agents = self._filter_healthy_agents(agents, str(department))

        # Phase 2 - Tier 1+2: cache
        decision = await self._check_cache(cache_key)
        if decision:
            decision.routing_latency_ms = (time.monotonic() - start) * 1000
            self._record_stats(decision, cache_hit=True)
            return decision

        attempted.extend([RoutingTier.CACHE_MEMORY, RoutingTier.CACHE_REDIS])

        # Tier 3: capability matching (skip if no agents)
        if agents:
            decision = await self._match_capabilities(task, agents)
            if decision:
                decision.attempted_tiers = attempted[:]
                decision.routing_latency_ms = (time.monotonic() - start) * 1000
                await self._write_cache(cache_key, decision)
                self._record_stats(decision, cache_hit=False)
                return decision
            attempted.append(RoutingTier.CAPABILITY)

        # Tier 4: LLM
        decision = await self._route_via_llm(task, agents)
        if decision:
            decision.attempted_tiers = attempted[:]
            decision.routing_latency_ms = (time.monotonic() - start) * 1000
            await self._write_cache(cache_key, decision)
            self._record_stats(decision, cache_hit=False)
            return decision
        attempted.append(RoutingTier.LLM)

        # Tier 5: fallback (raises RoutingError if empty)
        decision = await self._fallback(task, department, agents)
        decision.attempted_tiers = attempted[:]
        decision.routing_latency_ms = (time.monotonic() - start) * 1000
        await self._write_cache(cache_key, decision)
        self._record_stats(decision, cache_hit=False)
        return decision

    def _record_stats(self, decision: RoutingDecision, cache_hit: bool) -> None:
        self._total_requests += 1
        if cache_hit:
            self._cache_hits += 1
        self._latencies.append(decision.routing_latency_ms)
        if len(self._latencies) > _STATS_WINDOW:
            self._latencies.pop(0)

    async def _check_cache(self, key: str) -> RoutingDecision | None:
        """Tier 1+2: check memory LRU then Redis."""
        # Tier 1: memory
        cached: RoutingDecision | None = self._mem_cache.get(key)
        if cached is not None:
            logger.debug("[ROUTE] tier=%s tenant=%s", RoutingTier.CACHE_MEMORY, self._tenant_id)
            cached.tier_used = RoutingTier.CACHE_MEMORY
            return cached

        # Tier 2: Redis
        try:
            if self._redis is None or self._registry is None:
                return None
            raw = await self._redis.get(f"organism:{self._tenant_id}:route:{key}")
            if raw:
                data = json.loads(raw)
                reg = self._registry.get_registration(data["agent_id"])
                if reg:
                    decision = RoutingDecision(
                        agent_id=data["agent_id"],
                        agent_class=reg.agent_class,
                        department=data["department"],
                        confidence=data["confidence"],
                        tier_used=RoutingTier.CACHE_REDIS,
                        attempted_tiers=[RoutingTier.CACHE_MEMORY],
                        routing_latency_ms=0.0,
                    )
                    self._mem_cache[key] = decision  # warm memory cache
                    logger.debug(
                        "[ROUTE] tier=%s tenant=%s", RoutingTier.CACHE_REDIS, self._tenant_id
                    )
                    return decision
        except Exception as exc:
            logger.warning(
                "[ROUTE] Redis read failed: %s - continuing",
                exc,
                extra={"tenant_id": self._tenant_id},
            )
        return None

    async def _match_capabilities(
        self,
        task: TaskData,
        agents: list[AgentRegistration],
    ) -> RoutingDecision | None:
        """Tier 3: keyword set intersection against _AGENT_CAPABILITIES map."""
        # Build task keyword set from title tokens + tags
        title_keywords = frozenset(task.title.lower().replace("-", "_").split("_"))
        tag_keywords = frozenset(t.lower() for t in (task.tags or []))
        task_keywords = title_keywords | tag_keywords

        best: tuple[float, AgentRegistration] | None = None  # (score, AgentRegistration)
        for reg in agents:
            agent_caps = _AGENT_CAPABILITIES.get(reg.agent_id)
            if agent_caps is None:
                continue
            overlap = task_keywords & agent_caps
            if overlap:
                score = len(overlap) / len(agent_caps | task_keywords)
                if best is None or score > best[0]:
                    best = (score, reg)

        if best is None:
            return None

        score, reg = best
        logger.debug(
            "[ROUTE] tier=%s tenant=%s task=%s agent=%s",
            RoutingTier.CAPABILITY,
            self._tenant_id,
            task.title,
            reg.agent_id,
        )
        return RoutingDecision(
            agent_id=reg.agent_id,
            agent_class=reg.agent_class,
            department=reg.department,
            confidence=0.85,
            tier_used=RoutingTier.CAPABILITY,
            attempted_tiers=[RoutingTier.CACHE_MEMORY, RoutingTier.CACHE_REDIS],
            routing_latency_ms=0.0,
        )

    async def _route_via_llm(
        self, task: TaskData, agents: list[AgentRegistration]
    ) -> RoutingDecision | None:
        """Tier 4: ask the tenant's language model (their choice, default Mistral) which agent to use.

        NOTE: agents list may be empty for unmapped departments. In that case,
        the LLM is asked without a candidate list - it may still return a known agent_id
        from general knowledge. If it returns an unknown id, we fall through to fallback.
        """
        agent_list = "\n".join(f"- {r.agent_id}: {r.description}" for r in agents)
        prompt = (
            f"Task: {task.title}\nDescription: {task.description}\n\n"
            f"Available agents:\n{agent_list}\n\n"
            f"Reply with ONLY the agent_id of the best match. No explanation."
        )

        agent_ids = {r.agent_id for r in agents}

        for attempt, provider in enumerate([self._llm], start=1):
            try:
                response = await asyncio.wait_for(
                    provider.generate_response(prompt),
                    timeout=_LLM_TIMEOUT,
                )
                raw = (response.get("text") or response.get("content") or "").strip()
                chosen_id = raw.split()[0] if raw else ""
                if chosen_id not in agent_ids:
                    logger.warning(
                        "[ROUTE] LLM returned unknown agent_id=%s",
                        chosen_id,
                        extra={"tenant_id": self._tenant_id},
                    )
                    return None

                reg = next(r for r in agents if r.agent_id == chosen_id)
                logger.debug(
                    "[ROUTE] tier=%s tenant=%s agent=%s",
                    RoutingTier.LLM,
                    self._tenant_id,
                    chosen_id,
                )
                self._llm_fallback_count += 1
                return RoutingDecision(
                    agent_id=reg.agent_id,
                    agent_class=reg.agent_class,
                    department=reg.department,
                    confidence=0.90,
                    tier_used=RoutingTier.LLM,
                    attempted_tiers=[
                        RoutingTier.CACHE_MEMORY,
                        RoutingTier.CACHE_REDIS,
                        RoutingTier.CAPABILITY,
                    ],
                    routing_latency_ms=0.0,
                    reasoning=f"LLM selected {chosen_id} for task '{task.title}'",
                )
            except TimeoutError:
                logger.warning(
                    "[ROUTE] LLM timeout (attempt %s) tenant=%s",
                    attempt,
                    self._tenant_id,
                )
            except Exception as exc:
                logger.error(
                    "[ROUTE] LLM failed: %s: %s",
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                    extra={"tenant_id": self._tenant_id},
                )
        return None

    async def _fallback(
        self,
        task: TaskData,
        department: Department | None,
        agents: list[AgentRegistration],
    ) -> RoutingDecision:
        """Tier 5: first available agent. Raises RoutingError if list is empty."""
        attempted = [
            RoutingTier.CACHE_MEMORY,
            RoutingTier.CACHE_REDIS,
            RoutingTier.CAPABILITY,
            RoutingTier.LLM,
        ]
        if not agents:
            raise RoutingError(
                tenant_id=self._tenant_id,
                task_type=task.title,
                attempted_tiers=attempted + [RoutingTier.FALLBACK],
            )

        reg = agents[0]
        logger.debug(
            "[ROUTE] tier=%s tenant=%s task=%s agent=%s",
            RoutingTier.FALLBACK,
            self._tenant_id,
            task.title,
            reg.agent_id,
        )
        return RoutingDecision(
            agent_id=reg.agent_id,
            agent_class=reg.agent_class,
            department=reg.department,
            confidence=0.30,
            tier_used=RoutingTier.FALLBACK,
            attempted_tiers=attempted,
            routing_latency_ms=0.0,
        )

    async def route_with_department_filter(
        self, task: TaskData, target_department: Department
    ) -> RoutingDecision:
        """Task #3: Route task with explicit department constraint.

        This method extends the standard 5-tier routing by constraining agent
        selection to a specific department. Useful for patterns like:
        - "Route to Finance department agents only"
        - "Find available agents in Sales"

        Args:
            task: The task to route
            target_department: Department enum value to filter by

        Returns:
            RoutingDecision for an agent in the target department

        Raises:
            RoutingError: If no agents available in target department
            GatekeeperRoutingError: If Gatekeeper blocks the task (ADR-017)
        """
        start = time.monotonic()
        attempted: list[RoutingTier] = []

        # Phase 0: Gatekeeper policy check (same as standard route)
        gatekeeper_error = await self._check_gatekeeper(task)
        if gatekeeper_error:
            raise gatekeeper_error

        # Use department-aware cache key
        cache_key = self._build_cache_key_with_department(task, target_department)

        # Validate target_department is in mapped departments
        if target_department not in _DEPT_TO_DEPT_TYPE:
            logger.warning(
                "[ROUTE] Department filter unmapped: %s",
                target_department,
                extra={"tenant_id": self._tenant_id},
            )
            raise RoutingError(
                tenant_id=self._tenant_id,
                task_type=task.title,
                attempted_tiers=[],
            )

        # Get agents in target department from registry
        dept_type = _DEPT_TO_DEPT_TYPE[target_department]
        if self._registry is not None:
            all_agents = self._registry.list_agents(department=dept_type)
        else:
            all_agents = []
            agents = []
        agents = [
            a
            for a in all_agents
            if getattr(a, "tenant_id", None) is None
            or getattr(a, "tenant_id", None) == self._tenant_id
        ]

        # Apply department filter to ensure exact match
        agents = self._filter_agents_by_department(agents, target_department)

        # Apply health filter (ADR-023)
        agents = self._filter_healthy_agents(agents, str(target_department))

        # Phase 1+2: Cache (same as standard)
        decision = await self._check_cache(cache_key)
        if decision:
            decision.routing_latency_ms = (time.monotonic() - start) * 1000
            self._record_stats(decision, cache_hit=True)
            logger.info(
                "[ROUTE] Department-filtered cache hit: %s (dept=%s)",
                decision.agent_id,
                target_department,
                extra={"tenant_id": self._tenant_id, "department": target_department},
            )
            return decision

        attempted.extend([RoutingTier.CACHE_MEMORY, RoutingTier.CACHE_REDIS])

        # Phase 2 - Tier 3: Capability match (constrained to department)
        if agents:
            decision = await self._match_capabilities(task, agents)
            if decision:
                decision.attempted_tiers = attempted[:]
                decision.routing_latency_ms = (time.monotonic() - start) * 1000
                await self._write_cache(cache_key, decision)
                self._record_stats(decision, cache_hit=False)
                logger.info(
                    "[ROUTE] Department-filtered capability match: %s (dept=%s)",
                    decision.agent_id,
                    target_department,
                    extra={"tenant_id": self._tenant_id, "department": target_department},
                )
                return decision
            attempted.append(RoutingTier.CAPABILITY)

        # Tier 4: LLM (constrained to department agents only)
        decision = await self._route_via_llm(task, agents)
        if decision:
            decision.attempted_tiers = attempted[:]
            decision.routing_latency_ms = (time.monotonic() - start) * 1000
            await self._write_cache(cache_key, decision)
            self._record_stats(decision, cache_hit=False)
            logger.info(
                "[ROUTE] Department-filtered LLM match: %s (dept=%s)",
                decision.agent_id,
                target_department,
                extra={"tenant_id": self._tenant_id, "department": target_department},
            )
            return decision
        attempted.append(RoutingTier.LLM)

        # Tier 5: Fallback to first agent in department
        decision = await self._fallback(task, target_department, agents)
        decision.attempted_tiers = attempted[:]
        decision.routing_latency_ms = (time.monotonic() - start) * 1000
        await self._write_cache(cache_key, decision)
        self._record_stats(decision, cache_hit=False)
        logger.info(
            "[ROUTE] Department-filtered fallback: %s (dept=%s)",
            decision.agent_id,
            target_department,
            extra={"tenant_id": self._tenant_id, "department": target_department},
        )
        return decision

    async def _write_cache(self, key: str, decision: RoutingDecision) -> None:
        """Write to cache only if confidence >= threshold."""
        if decision.confidence < _CONFIDENCE_CACHE_THRESHOLD:
            return
        self._mem_cache[key] = decision
        try:
            payload = json.dumps(
                {
                    "agent_id": decision.agent_id,
                    "department": (
                        decision.department.value
                        if isinstance(decision.department, Enum)
                        else decision.department
                    ),
                    "confidence": decision.confidence,
                }
            )
            if self._redis is None:
                return
            await self._redis.setex(
                f"organism:{self._tenant_id}:route:{key}",
                _CACHE_TTL,
                payload,
            )
        except Exception as exc:
            logger.warning(
                "[ROUTE] Redis write failed: %s - memory cache still set",
                exc,
                extra={"tenant_id": self._tenant_id},
            )

    async def invalidate(self, agent_id: str) -> None:
        """Full tenant cache flush (memory + Redis SCAN)."""
        self._mem_cache.clear()
        try:
            if self._redis is None:
                return
            pattern = f"organism:{self._tenant_id}:route:*"
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break
            logger.info(
                "[ROUTE] Cache invalidated for tenant=%s",
                self._tenant_id,
                extra={"tenant_id": self._tenant_id},
            )
        except Exception as exc:
            logger.warning(
                "[ROUTE] Redis invalidation failed: %s", exc, extra={"tenant_id": self._tenant_id}
            )


# ---------------------------------------------------------------------------
# AgentRouterAgent - thin BaseAgent wrapper
# ---------------------------------------------------------------------------
from src.core.shared.interfaces import BaseAgent, ExecutionResult
from src.core.types import AgentType


class AgentRouterAgent(BaseAgent):
    """
    Thin wrapper making RouterService compatible with the agent ecosystem.
    Delegates all logic to RouterService.

    ADR-017: Integrates Gatekeeper for deterministic policy enforcement.
    ADR-023: Integrates AgentHealthMonitorAgent for health-aware routing.
    """

    def __init__(
        self,
        tenant_id: int,
        signal_bus: Any,  # TODO(TYPE): replace Any with concrete type
        gatekeeper: Any = None,
        health_monitor: Any = None,
    ) -> None:
        super().__init__(
            agent_id="agent_router",
            agent_type=AgentType.ORCHESTRATOR,
        )
        self._service = RouterService(
            tenant_id=tenant_id,
            redis_client=None,  # set in initialize()
            registry=None,
            llm_client=None,
            gatekeeper=gatekeeper,  # ADR-017: Policy enforcement
            health_monitor=health_monitor,  # ADR-023: Health-aware routing
        )
        self._signal_bus = signal_bus
        self._tenant_id = tenant_id
        self._gatekeeper = gatekeeper
        self._health_monitor = health_monitor  # ADR-023: Health-aware routing

    async def initialize(self) -> bool:
        from src.core.als.agents.organism_registry import get_organism_registry
        from src.core.als.infrastructure.redis_pool import RedisPoolManager
        from src.core.services.llm.tenant_deur import TenantTaalmodel

        redis = await RedisPoolManager().get_client()
        registry = get_organism_registry()
        # Taaktitel en omschrijving zijn klantgegevens: het model is de keuze van DEZE tenant
        # (ADR-041 B14), geen harde leverancier.
        llm = TenantTaalmodel(self._tenant_id)
        self._service._redis = redis
        self._service._registry = registry
        self._service._llm = llm

        # ADR-017: Initialize Gatekeeper if provided
        if self._gatekeeper:
            # Ensure gatekeeper has repository for persistence
            if hasattr(self._gatekeeper, "initialize"):
                await self._gatekeeper.initialize()

        return await self._service.initialize()

    async def route(self, task: TaskData) -> RoutingDecision:
        return await self._service.route(task)

    async def process_task(self, task: TaskData) -> ExecutionResult:
        try:
            decision = await self.route(task)
            return ExecutionResult(
                task_id=task.id,
                success=True,
                result_data={
                    "agent_id": decision.agent_id,
                    "department": (
                        decision.department.value
                        if isinstance(decision.department, Enum)
                        else str(decision.department)
                    ),
                    "confidence": decision.confidence,
                    "tier_used": decision.tier_used.value,
                    "routing_latency_ms": decision.routing_latency_ms,
                },
            )
        except GatekeeperRoutingError as exc:
            # ADR-017: Handle Gatekeeper blocks explicitly
            logger.warning(
                "[ROUTE] Gatekeeper %s task=%s: %s",
                exc.decision,
                exc.task_id,
                exc.reason,
                extra={"tenant_id": self._tenant_id, "task_id": exc.task_id},
            )
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"Gatekeeper {exc.decision}: {exc.reason}",
                result_data={
                    "gatekeeper_decision": exc.decision,
                    "hitl_ticket_ref": exc.hitl_ticket_ref,
                },
            )
        except AgentUnhealthyError as exc:
            # ADR-023: Handle unhealthy agent errors
            logger.warning(
                "[ROUTE] No healthy agents for task=%s in %s: %s",
                exc.task_id,
                exc.department,
                exc.unhealthy_agents,
                extra={"tenant_id": self._tenant_id, "task_id": exc.task_id},
            )
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"No healthy agents available in {exc.department}",
                result_data={
                    "unhealthy_agents": exc.unhealthy_agents,
                    "department": exc.department,
                },
            )
        except RoutingError as exc:
            logger.error(
                "[ROUTE] RoutingError: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
                extra={"tenant_id": self._tenant_id},
            )
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=str(exc),
            )


# ---------------------------------------------------------------------------
# Per-tenant singleton management
# ---------------------------------------------------------------------------

# NOTE: These are intentional module-level shared state dicts (not mutable defaults).
_router_cache: dict[int, RouterService] = {}
_router_locks: dict[int, asyncio.Lock] = {}


async def get_router(
    tenant_id: int,
    redis_client: AsyncRedisClient,
    registry: OrganismRegistry,
    llm_client: Any,  # NOTE: no shared LLM interface -- genuinely polymorphic  # TODO(TYPE): replace Any with concrete type
    gatekeeper: Any = None,  # ADR-017: optional gatekeeper for policy enforcement (SP-DLP-001)
) -> RouterService:
    """Get or create a RouterService for a tenant. Thread-safe via asyncio.Lock."""
    if tenant_id not in _router_locks:
        _router_locks[tenant_id] = asyncio.Lock()

    async with _router_locks[tenant_id]:
        if tenant_id not in _router_cache:
            svc = RouterService(
                tenant_id, redis_client, registry, llm_client, gatekeeper=gatekeeper
            )
            await svc.initialize()
            _router_cache[tenant_id] = svc
    return _router_cache[tenant_id]


def clear_router(tenant_id: int) -> None:
    """Remove tenant's RouterService and lock. Call on tenant offboarding."""
    _router_cache.pop(tenant_id, None)
    _router_locks.pop(tenant_id, None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "RoutingTier",
    "RoutingDecision",
    "RouterStats",
    "RoutingError",
    "GatekeeperRoutingError",
    "AgentUnhealthyError",
    "RouterService",
    "AgentRouterAgent",
    "get_router",
    "clear_router",
]
