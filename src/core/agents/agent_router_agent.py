"""
AgentRouterAgent - Intent-based task routing for SanskritiSetu.

Extends the existing RouterAgentService (Ollama-based) with:
- Full EnhancedBaseAgent integration (tenant isolation, learning, events)
- Capability-based agent matching against the AgentRegistry
- CriticMixin in SILENT mode (routing telemetry, zero latency overhead)
- Fallback chain: cache -> DB discovery -> capability match -> LLM -> executor fallback
- route_and_execute() convenience method for MasterOrchestratorAgent

Routing strategy (in order):
  1. Cache hit (TTL in-memory, per-tenant)
  2. DB discovery via AgentDiscoveryService (keyword overlap against registered agents)
  3. Capability vector match against in-memory registered manifests
  4. LLM-based intent classification (fast local model via RouterAgentService)
  5. Fallback to ExecutorAgent

M-MDP: sync scoring/matching, async I/O (LLM, DB discovery, agent execution).
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from src.core.agents.agent_discovery import AgentDiscoveryService
    from src.core.agents.agent_load_tracker import AgentLoadTracker
    from src.core.shared.interfaces import AsyncSessionFactory

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.agents.health_scorer import HealthScorer
from src.core.agents.mixins.critic_mixin import CriticMixin, CriticMode
from src.core.agents.llm_types import (
    AgentCategory,
    AgentProfile,
    TaskComplexity,
    agent_model_matcher,
)
from src.core.observability.metrics import (
    agent_router_cache_result_total,
    agent_router_decision_latency_seconds,
)
from src.core.shared.interfaces import AgentCapability, ExecutionResult, TaskData
from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.types import AgentType

logger = logging.getLogger(__name__)


# Weight applied to current_load when computing the composite capability-match score.
# Keeps a fully-loaded agent (1.0) from outranking a healthy one with equal capability score.
_LOAD_COMPOSITE_WEIGHT: float = 0.2


# --- Routing cache (optimized) -----------------------------------------------


@dataclass
class RouteCacheEntry:
    agent_id: str
    agent_type: str
    score: float
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    hits: int = 0


class RouteCache:
    """Optimized TTL cache for routing decisions (avoids repeat LLM calls)."""

    def __init__(self, ttl_seconds: int = 300, max_entries: int = 500) -> None:
        self._store: dict[str, RouteCacheEntry] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max = max_entries
        self._hits = 0
        self._misses = 0

    def _key(self, task_title: str, capabilities: list[str], tenant_id: int) -> str:
        raw = f"{tenant_id}|{task_title}|{','.join(sorted(capabilities))}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(
        self, task_title: str, capabilities: list[str], tenant_id: int
    ) -> RouteCacheEntry | None:
        key = self._key(task_title, capabilities, tenant_id)
        entry = self._store.get(key)
        if entry and datetime.now(timezone.utc) - entry.created_at < self._ttl:
            entry.hits += 1
            self._hits += 1
            return entry
        if key in self._store:
            del self._store[key]
        self._misses += 1
        return None

    def set(
        self, task_title: str, capabilities: list[str], tenant_id: int, entry: RouteCacheEntry
    ) -> None:
        if len(self._store) >= self._max:
            oldest = min(self._store, key=lambda k: self._store[k].created_at)
            del self._store[oldest]
        self._store[self._key(task_title, capabilities, tenant_id)] = entry

    def stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "size": len(self._store),
            "max": self._max,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
        }

    def invalidate_all(self) -> int:
        """Clear all cached entries."""
        count = len(self._store)
        self._store.clear()
        return count


class RedisRouteCacheTier:
    """Optional Redis-backed tier for cross-worker routing cache persistence.

    Key format: route_cache:{tenant_id}:{sha256_cache_key}
    This is the canonical format -- do not change without updating all consumers.

    Fail-graceful: any Redis error logs a warning and returns None/no-op so
    single-worker deployments without Redis continue unaffected.
    """

    _KEY_PREFIX = "route_cache"
    _DEFAULT_TTL = 300

    def __init__(
        # TODO(TYPE): replace Any with concrete type
        self,
        redis_client: Any,
        ttl_seconds: int = _DEFAULT_TTL,
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        self._redis = redis_client
        self._ttl = ttl_seconds

    def _key(self, cache_key: str, tenant_id: int) -> str:
        return f"{self._KEY_PREFIX}:{tenant_id}:{cache_key}"

    async def get(self, cache_key: str, tenant_id: int) -> RouteCacheEntry | None:
        try:
            raw = await self._redis.get(self._key(cache_key, tenant_id))
            if raw is None:
                return None
            data = json.loads(raw)
            return RouteCacheEntry(
                agent_id=data["agent_id"],
                agent_type=data["agent_type"],
                score=data["score"],
            )
        except Exception as exc:
            logger.warning("RedisRouteCacheTier.get failed: %s", exc)
            return None

    async def set(self, cache_key: str, tenant_id: int, entry: RouteCacheEntry) -> None:
        try:
            data = json.dumps(
                {
                    "agent_id": entry.agent_id,
                    "agent_type": entry.agent_type,
                    "score": entry.score,
                }
            )
            await self._redis.setex(self._key(cache_key, tenant_id), self._ttl, data)
        except Exception as exc:
            logger.warning("RedisRouteCacheTier.set failed: %s", exc)


# --- LLM structured routing output --------------------------------------------


class _RoutingDecision(BaseModel):
    """Structured output requested from the LLM in _llm_route() via response_model."""

    agent_id: str


# --- Agent manifest entry -----------------------------------------------------


@dataclass
class AgentManifest:
    """Lightweight descriptor of a registered agent, used for routing decisions."""

    agent_id: str
    agent_type: str
    capabilities: list[str]
    department: str
    current_load: float = 0.0  # 0.0-1.0
    # Default to neutral midpoint so brand-new (unproven) agents don't rank above
    # established agents solely because of a 0 ms latency assumption.
    avg_latency_ms: float = 2500.0
    success_rate: float = 1.0
    # Set by AgentHealthMonitorAgent when health signals are available.
    health_status: str = "UNKNOWN"
    last_seen: datetime | None = None


# --- Main class ---------------------------------------------------------------


class AgentRouterAgent(CriticMixin, EnhancedBaseAgent):
    """
    Routes incoming tasks to the best available specialist agent.

    Public interface:
        result = await router.route_and_execute(task)   # route + execute
        agent_id = await router.route(task)              # route only
        router.register(manifest)                        # add agent to pool
    """

    def __init__(
        self,
        agent_id: str = "agent_router_001",
        tenant_id: int = 1,
        async_session_factory: AsyncSessionFactory | None = None,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.COORDINATOR,
            tenant_id=tenant_id,
        )
        self.__init_critic__(mode=CriticMode.SILENT)

        self.specialization = "intent_based_task_routing"
        self.llm_client: TenantTaalmodel | None = None

        # Agent registry: agent_id -> AgentManifest
        self._manifests: dict[str, AgentManifest] = {}
        self._manifests_lock = asyncio.Lock()

        # Capability index: capability -> [agent_id, ...]
        self._cap_index: dict[str, list[str]] = defaultdict(list)

        # Routing cache (in-memory tier 1)
        self._cache = RouteCache(ttl_seconds=300)

        # Optional Redis-backed routing cache (tier 1.5, set via get_agent_router(redis_client=...))
        self._redis_cache_tier: RedisRouteCacheTier | None = None

        # Session factory injected from the application layer (ADR-034: agents never
        # import src.core.database.database directly -- factory is passed from outside).
        # NOTE: from __future__ import annotations at line 21 makes the AsyncSessionFactory
        # annotation safe under TYPE_CHECKING guard without runtime NameError.
        self._async_session_factory: AsyncSessionFactory | None = async_session_factory

        # Discovery service (lazy-initialized in initialize())
        self._discovery_service: AgentDiscoveryService | None = None

        # Load tracker (lazy-initialized in initialize())
        self._load_tracker: AgentLoadTracker | None = None

        # Metrics
        self._routes_total = 0
        self._cache_hits = 0
        self._discovery_hits = 0
        self._fallbacks_used = 0

        self._register_agent_profile()
        logger.info("AgentRouterAgent %s initialised (tenant=%d)", agent_id, tenant_id)

    def _register_agent_profile(self) -> None:
        profile = AgentProfile(
            agent_type="coordinator",
            category=AgentCategory.STRATEGIC,
            typical_complexity=TaskComplexity.SIMPLE,
            reasoning_required=0.7,
            speed_priority=0.95,  # routing must be fast
            cost_sensitivity=0.9,
            context_needs=1000,
            special_requirements=["routing", "classification"],
        )
        agent_model_matcher.register_agent_profile(profile)

    async def initialize(self) -> bool:
        # Het model van de TENANT van deze router (brief 2026-10-20, ADR-041 B14). Hier stond Google
        # (`config.provider = GOOGLE`) en voor de routering zelf de platformketen.
        self.llm_client = TenantTaalmodel(self.tenant_id)
        logger.info("AgentRouterAgent %s LLM ready", self.agent_id)

        try:
            from src.core.agents.agent_discovery import AgentDiscoveryService

            if self._discovery_service is None:
                self._discovery_service = AgentDiscoveryService(
                    tenant_id=self.tenant_id,
                    async_session_factory=self._async_session_factory,
                )
            logger.info("AgentRouterAgent %s discovery service ready", self.agent_id)
        except Exception as exc:
            logger.warning("AgentRouterAgent discovery service init failed: %s", exc)

        if self._load_tracker is None:
            from src.core.agents.agent_load_tracker import AgentLoadTracker

            self._load_tracker = AgentLoadTracker(tenant_id=self.tenant_id)

        return True

    async def get_capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name="agent_routing",
                description="Intelligent capability-based routing and task dispatching across agents",
                input_types=["task_request", "routing_query"],
                output_types=["agent_selection", "route_resolution"],
            )
        ]

    # -- Registration ----------------------------------------------------------

    async def register(self, manifest: AgentManifest) -> None:
        """Register an agent so the router knows it exists."""
        async with self._manifests_lock:
            self._manifests[manifest.agent_id] = manifest
            for cap in manifest.capabilities:
                if manifest.agent_id not in self._cap_index[cap]:
                    self._cap_index[cap].append(manifest.agent_id)
        logger.debug(
            "AgentRouterAgent registered %s (%s caps)",
            manifest.agent_id,
            len(manifest.capabilities),
        )

    async def deregister(self, agent_id: str) -> None:
        async with self._manifests_lock:
            manifest = self._manifests.pop(agent_id, None)
            if manifest:
                for cap in manifest.capabilities:
                    self._cap_index[cap] = [aid for aid in self._cap_index[cap] if aid != agent_id]

    def get_manifest(self, agent_id: str) -> AgentManifest | None:
        """Return agent manifest by id."""
        return self._manifests.get(agent_id)

    async def update_health_status(
        self, agent_id: str, status: str, metrics: dict[str, float]
    ) -> None:
        """Update manifest health fields on status transition.

        Called by AgentHealthMonitorAgent via write-bridge (CG-005 fix).
        Returns immediately if agent_id is not registered.
        """
        async with self._manifests_lock:
            manifest = self._manifests.get(agent_id)
            if manifest is None:
                return
            manifest.health_status = status
            manifest.success_rate = metrics.get("success_rate", manifest.success_rate)
            manifest.avg_latency_ms = metrics.get("avg_latency_ms", manifest.avg_latency_ms)
        logger.debug(
            "AgentRouterAgent manifest updated agent=%s status=%s",
            agent_id,
            status,
        )

    def cache_lookup(self, task_title: str, capabilities: list[str]) -> RouteCacheEntry | None:
        """Expose safe cache lookup for telemetry consumers."""
        return self._cache.get(task_title, capabilities, self.tenant_id)

    def capability_match(self, capabilities: list[str]) -> str | None:
        """Public wrapper around capability matching."""
        return self._capability_match(capabilities)

    def get_registered_agent_count(self) -> int:
        """Return number of registered agents."""
        return len(self._manifests)

    def get_cache_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Return routing cache statistics."""
        return self._cache.stats()

    # -- Routing ---------------------------------------------------------------

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """Standard agent interface - routes task and returns routing decision."""
        start = time.perf_counter()
        try:
            # Wire BudgetManager (ADR-026 fallback support)
            from src.core.agents.budget_manager import BudgetManager, calculate_cost

            cache_tier = self._redis_cache_tier
            redis_client = cache_tier._redis if cache_tier is not None else None

            # Check budget first -- fail-graceful if no session factory is
            # configured (e.g. lightweight/test agents): skip tracking, still route.
            if self._async_session_factory is not None:
                async with self._async_session_factory() as session:
                    budget = BudgetManager(session=session, redis_client=redis_client)

                    check_res = await budget.check_budget(
                        tenant_id=self.tenant_id,
                        agent_id=self.agent_id,
                        estimated_tokens=500,  # Approx for routing
                    )
                    if not check_res.allowed:
                        logger.warning("Routing blocked: %s", check_res.reason)
                        return ExecutionResult(
                            task_id=task.id,
                            success=False,
                            result_data={"error": f"Budget exceeded: {check_res.reason}"},
                            execution_time=time.perf_counter() - start,
                        )

            # Route via the standard 5-tier routing pipeline
            agent_id = await self.route(task)
            route_info = {"routed_to": agent_id}

            # Record usage
            if self._async_session_factory is not None:
                async with self._async_session_factory() as session:
                    budget = BudgetManager(session=session, redis_client=redis_client)
                    input_tokens, output_tokens = 250, 50
                    await budget.record_usage(
                        tenant_id=self.tenant_id,
                        agent_id=self.agent_id,
                        tokens_used=input_tokens + output_tokens,
                        cost_usd=calculate_cost("routing-model", input_tokens, output_tokens),
                        model_name="routing-model",
                    )

            return ExecutionResult(
                task_id=task.id,
                success=bool(agent_id),
                result_data=route_info,
                execution_time=time.perf_counter() - start,
            )
        except Exception as exc:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data={"error": str(exc)},
                execution_time=time.perf_counter() - start,
            )

    async def _remember_route(
        self, task: TaskData, caps: list[str], cache_key: str, agent_id: str, score: float
    ) -> None:
        """Write a routing decision to both the in-memory (tier 1) and, if
        configured, the Redis (tier 1.5) cache -- SP-ADR023-002 Dag 2 follow-up.

        Without the Redis write, RedisRouteCacheTier is constructed but never
        populated, so the cross-worker cache ADR-023 section 4 describes never
        actually shares a decision between workers.
        """
        entry = RouteCacheEntry(agent_id=agent_id, agent_type="", score=score)
        self._cache.set(task.title, caps, self.tenant_id, entry)
        if self._redis_cache_tier is not None:
            await self._redis_cache_tier.set(cache_key, self.tenant_id, entry)

    async def route(self, task: TaskData) -> str:
        """
        Determine the best agent_id for a task. Returns agent_id string.
        Does NOT execute the task.
        """
        self._routes_total += 1
        start = time.perf_counter()
        caps = list(task.metadata.get("capabilities", []))
        cache_key = self._cache._key(task.title, caps, self.tenant_id)
        tenant_label = str(self.tenant_id)

        # 1. In-memory cache hit (tier 1) -- skip if the cached agent is now overloaded
        cached = self._cache.get(task.title, caps, self.tenant_id)
        if cached:
            manifest = self._manifests.get(cached.agent_id)
            if manifest is None or manifest.current_load < 0.9:
                self._cache_hits += 1
                agent_router_cache_result_total.labels(
                    tenant_id=tenant_label, tier="in_memory", result="hit"
                ).inc()
                agent_router_decision_latency_seconds.labels(
                    tenant_id=tenant_label, tier="in_memory"
                ).observe(time.perf_counter() - start)
                logger.debug("AgentRouterAgent cache hit -> %s", cached.agent_id)
                return cached.agent_id
            logger.debug(
                "AgentRouterAgent cache hit for %s overloaded (load=%.2f), falling through",
                cached.agent_id,
                manifest.current_load,
            )
        agent_router_cache_result_total.labels(
            tenant_id=tenant_label, tier="in_memory", result="miss"
        ).inc()

        # 1.5 Redis cross-worker cache hit (SP-ADR023-002 Dag 2, ADR-023 section 4)
        if self._redis_cache_tier is not None:
            redis_cached = await self._redis_cache_tier.get(cache_key, self.tenant_id)
            if redis_cached:
                manifest = self._manifests.get(redis_cached.agent_id)
                if manifest is None or manifest.current_load < 0.9:
                    self._cache_hits += 1
                    # Populate tier 1 so subsequent calls on THIS worker skip Redis too.
                    self._cache.set(task.title, caps, self.tenant_id, redis_cached)
                    agent_router_cache_result_total.labels(
                        tenant_id=tenant_label, tier="redis", result="hit"
                    ).inc()
                    agent_router_decision_latency_seconds.labels(
                        tenant_id=tenant_label, tier="redis"
                    ).observe(time.perf_counter() - start)
                    logger.debug("AgentRouterAgent Redis cache hit -> %s", redis_cached.agent_id)
                    return redis_cached.agent_id
            agent_router_cache_result_total.labels(
                tenant_id=tenant_label, tier="redis", result="miss"
            ).inc()

        # 2. Database discovery (AgentDiscoveryService)
        agent_id = await self._discovery_route(task)
        if agent_id:
            await self._remember_route(task, caps, cache_key, agent_id, score=0.85)
            agent_router_decision_latency_seconds.labels(
                tenant_id=tenant_label, tier="discovery"
            ).observe(time.perf_counter() - start)
            return agent_id

        # Refresh live load values from Redis in a single MGET round-trip
        if self._load_tracker is not None:
            live_loads = await self._load_tracker.get_loads(list(self._manifests.keys()))
            async with self._manifests_lock:
                for aid, load in live_loads.items():
                    if load is not None and aid in self._manifests:
                        self._manifests[aid].current_load = load

        # 3. Capability match (fast, no LLM)
        agent_id = self._capability_match(caps)
        if agent_id:
            await self._remember_route(task, caps, cache_key, agent_id, score=0.8)
            agent_router_decision_latency_seconds.labels(
                tenant_id=tenant_label, tier="capability"
            ).observe(time.perf_counter() - start)
            return agent_id

        # 4. LLM-based intent match
        agent_id = await self._llm_route(task)
        if agent_id:
            await self._remember_route(task, caps, cache_key, agent_id, score=0.9)
            agent_router_decision_latency_seconds.labels(
                tenant_id=tenant_label, tier="llm"
            ).observe(time.perf_counter() - start)
            return agent_id

        # 5. Fallback: executor
        self._fallbacks_used += 1
        agent_router_decision_latency_seconds.labels(
            tenant_id=tenant_label, tier="fallback"
        ).observe(time.perf_counter() - start)
        logger.warning("AgentRouterAgent falling back to executor for task %s", task.id)
        return "executor_agent_001"

    async def route_and_execute(self, task: TaskData) -> ExecutionResult:
        """Route the task AND execute it via the target agent."""
        start = time.perf_counter()

        # importlib avoids direct ImportFrom (DSM boundary agent_runtime -> governance)
        gov_mod = importlib.import_module("src.core.governance.governance_helper")

        # Enforce governance before routing
        capabilities = (
            [c.name for c in await self.get_capabilities()]
            if hasattr(self, "get_capabilities")
            else []
        )
        allowed, reason = await gov_mod.apply_governance_check(
            agent_name=self.agent_id,
            agent_department=getattr(self, "department", "Operations"),
            agent_specialisation=self.specialization,
            agent_capabilities=capabilities,
            task_action="route_and_execute",
            task_params={"task_title": task.title, "task_description": task.description},
            tenant_id=self.tenant_id,
        )
        if not allowed:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data={"error": reason},
                execution_time=time.perf_counter() - start,
            )

        agent_id = await self.route(task)
        agent = self._resolve_agent(agent_id)
        if agent is None:
            from src.core.observability.metrics import AGENT_EXECUTION_FAILURES_TOTAL

            AGENT_EXECUTION_FAILURES_TOTAL.labels(
                agent_id="unknown", tenant_id=str(self.tenant_id), reason="agent_not_found"
            ).inc()
            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data={"error": f"Agent {agent_id} not found in process"},
                execution_time=time.perf_counter() - start,
            )

        try:
            result = await agent.process_task(task)
            if not result.success:
                from src.core.observability.metrics import AGENT_EXECUTION_FAILURES_TOTAL

                AGENT_EXECUTION_FAILURES_TOTAL.labels(
                    agent_id=str(agent_id), tenant_id=str(self.tenant_id), reason="task_failed"
                ).inc()
            return result  # type: ignore[no-any-return]
        except Exception as exc:
            from src.core.observability.metrics import AGENT_EXECUTION_FAILURES_TOTAL

            AGENT_EXECUTION_FAILURES_TOTAL.labels(
                agent_id=str(agent_id), tenant_id=str(self.tenant_id), reason="exception"
            ).inc()
            logger.error(
                "Agent %s threw an exception during processing: %s",
                agent_id,
                exc,
                exc_info=True,
            )
            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data={"error": str(exc)},
                execution_time=time.perf_counter() - start,
            )

    async def run_agent(
        self,
        agent_id: str,
        instruction: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """IAgentRuntime-compatible adapter over route_and_execute().

        Builds a TaskData from the (agent_id, instruction, context) triple
        and delegates to route_and_execute(). Allows ProductionAgentRuntime
        to delegate to AgentRouterAgent for intelligent routing (SP-AGT-003).
        """
        task = TaskData(
            title=f"route-{agent_id}",
            description=instruction,
            metadata={**context, "requested_agent_id": agent_id},
        )
        try:
            result = await self.route_and_execute(task)
            return {
                "success": result.success,
                "output": result.result_data,
                "agent_id": agent_id,
                "execution_time": result.execution_time,
            }
        except Exception as exc:
            logger.error(
                "AgentRouterAgent.run_agent failed for %s: %s: %s",
                agent_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return {"success": False, "error": "routing failed", "agent_id": agent_id}

    # -- Internal matching (sync - M-MDP) -------------------------------------

    async def _discovery_route(self, task: TaskData) -> str | None:
        """Tier 2: DB discovery via AgentDiscoveryService.

        Returns the best matching agent_id from the database, or None if
        the discovery service is unavailable or no match is found.
        """
        if self._discovery_service is None:
            return None
        try:
            task_text = task.description or task.title
            caps = list(task.parameters.get("capabilities", []))
            agent = await self._discovery_service.find_best_agent_for_task(
                task_text, capabilities=caps
            )
            if agent:
                agent_id = agent.get("agent_id")
                if agent_id:
                    self._discovery_hits += 1
                    logger.debug("AgentRouterAgent discovery hit -> %s", agent_id)
                    return agent_id  # type: ignore[no-any-return]
        except Exception as exc:
            logger.warning("AgentRouterAgent discovery route failed: %s", exc)
        return None

    def _capability_match(self, capabilities: list[str]) -> str | None:
        """Find best agent by capability overlap score combined with health score."""
        if not capabilities:
            return None
        scores: dict[str, int] = defaultdict(int)
        for cap in capabilities:
            for agent_id in self._cap_index.get(cap, []):
                scores[agent_id] += 1
        if not scores:
            return None

        def _composite(aid: str) -> float:
            m = self._manifests.get(aid)
            if m is None:
                return 0.0
            return HealthScorer.score_manifest(m) - m.current_load * _LOAD_COMPOSITE_WEIGHT

        # Try candidates in descending composite score order, skip overloaded agents
        for agent_id in sorted(scores, key=_composite, reverse=True):
            manifest = self._manifests.get(agent_id)
            if manifest and manifest.current_load < 0.9:
                return agent_id
        return None

    async def _llm_route(self, task: TaskData) -> str | None:
        """Use LLM to classify intent and match to agent."""
        if not self.llm_client:
            await self.initialize()
        if not self.llm_client or not self._manifests:
            return None

        try:
            from src.core.agents.prompt_guard import PromptGuard, Action

            guard = PromptGuard()
            title_scan = await guard.scan_input(task.title)
            desc_scan = await guard.scan_input(task.description)
            if title_scan.action == Action.BLOCK or desc_scan.action == Action.BLOCK:
                logger.warning("Prompt injection detected in routing for task %s", task.id)
                return None

            safe_title = title_scan.sanitized_text
            safe_desc = desc_scan.sanitized_text
        except Exception as exc:
            logger.warning("PromptGuard failed in routing: %s", exc, exc_info=True)
            return None

        agent_list = "\n".join(
            f"- {m.agent_id}: {', '.join(m.capabilities[:4])}"
            for m in list(self._manifests.values())[:20]
        )
        prompt = (
            f"Given this task:\nTitle: {safe_title}\nDescription: {safe_desc}\n\n"
            f"Available agents:\n{agent_list}\n\n"
            f'Reply with ONLY JSON of the form {{"agent_id": "<id>"}}. No explanation.'
        )
        try:
            raw = (await self.llm_client.tekst(prompt, max_tokens=100)).strip()

            # Preferred path: the model honored response_model and returned valid JSON.
            try:
                decision = _RoutingDecision.model_validate_json(raw)
                if decision.agent_id in self._manifests:
                    return decision.agent_id
                return None
            except (ValidationError, ValueError):
                # Fallback tier (e.g. local/heuristic model without JSON mode support):
                # degrade to matching the first known agent_id token in free text.
                for word in raw.split():
                    clean = word.strip(".,;:\"'{}")
                    if clean in self._manifests:
                        return clean
        except Exception as exc:
            logger.warning("AgentRouterAgent LLM routing failed: %s", exc)
        return None

    def _resolve_agent(
        self, agent_id: str
    ) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Attempt to get a live agent instance from the process."""
        try:
            from src.core.agents.agent_factory import AgentFactory

            get_instance = getattr(AgentFactory, "get_instance", None)
            if callable(get_instance):
                return get_instance(agent_id, self.tenant_id)
            return None
        except Exception:
            return None

    def metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "routes_total": self._routes_total,
            "cache_hits": self._cache_hits,
            "discovery_hits": self._discovery_hits,
            "fallbacks_used": self._fallbacks_used,
            "registered_agents": len(self._manifests),
            "cache_hit_rate": (
                round(self._cache_hits / self._routes_total, 3) if self._routes_total else 0.0
            ),
        }


# --- Singleton ----------------------------------------------------------------

_instances: dict[int, AgentRouterAgent] = {}
_instances_lock = threading.Lock()


def get_agent_router(
    tenant_id: int = 1,
    redis_client: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    async_session_factory: AsyncSessionFactory | None = None,
) -> AgentRouterAgent:
    """Return the singleton AgentRouterAgent for the given tenant.

    Pass redis_client to enable the RedisRouteCacheTier (cross-worker cache)
    on first creation. Has no effect if the instance is already cached.

    Pass async_session_factory (e.g. db_manager.async_session_maker from
    src.core.database.database) to enable DB-backed agent discovery. Without it,
    discovery degrades to empty results. Wire this from the application layer
    (app_lifespan.py, src/core/api/v1/orchestration/dependencies.py) -- never from
    agents/ (ADR-034).
    """
    with _instances_lock:
        if tenant_id not in _instances:
            instance = AgentRouterAgent(
                agent_id=f"agent_router_{tenant_id:03d}",
                tenant_id=tenant_id,
                async_session_factory=async_session_factory,
            )
            if redis_client is not None:
                instance._redis_cache_tier = RedisRouteCacheTier(redis_client)
            _instances[tenant_id] = instance
        return _instances[tenant_id]


def clear_router_instance(tenant_id: int) -> None:
    """Evict a tenant's cached AgentRouterAgent instance (call on suspend/delete).

    Called from src.core.api.v1.orchestration.dependencies.clear_tenant_cache()
    -- the API layer owns tenant lifecycle events, this module only owns the cache.
    """
    with _instances_lock:
        _instances.pop(tenant_id, None)
