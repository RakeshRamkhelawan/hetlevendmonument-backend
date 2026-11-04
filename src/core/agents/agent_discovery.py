"""
AgentDiscoveryService - database-backed agent discovery for the routing chain.

This service implements Phase 1b: database-backed agent discovery, used as
Tier 2 in the AgentRouterAgent 5-tier routing chain.

All queries are scoped to a single tenant (self._tenant_id). An in-memory
TTL cache (300 s) per-instance avoids redundant DB round-trips while keeping
data reasonably fresh.
"""

import enum
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from collections.abc import AsyncIterator

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.models import RegisteredAgent
from src.core.shared.interfaces import AsyncSessionFactory

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300


class DepartmentFilter(str, enum.Enum):
    """Department identifiers used to narrow agent discovery queries."""

    STRATEGY = "STRATEGY"
    OPERATIONS = "OPERATIONS"
    PRODUCT_INNOVATION = "PRODUCT_INNOVATION"
    DATA_AI_GOVERNANCE = "DATA_AI_GOVERNANCE"
    FINANCE = "FINANCE"
    SALES_MARKETING = "SALES_MARKETING"
    IT_SECURITY = "IT_SECURITY"
    CUSTOMER_EXPERIENCE = "CUSTOMER_EXPERIENCE"
    HR = "HR"
    LEGAL_COMPLIANCE = "LEGAL_COMPLIANCE"
    ALL = "ALL"  # sentinel: no department filter applied


class AgentDiscoveryService:
    """
    Database-backed agent discovery service.

    Tenant isolation invariant: every public method on this class is scoped
    exclusively to self._tenant_id. No cross-tenant data is ever returned.

    Usage:
        svc = AgentDiscoveryService(tenant_id=42)
        agents = await svc.discover_all_agents()
    """

    def __init__(
        self,
        tenant_id: int,
        db_session: AsyncSession | None = None,
        async_session_factory: AsyncSessionFactory | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._db_session = db_session
        self._async_session_factory = async_session_factory
        self._ttl = _CACHE_TTL_SECONDS
        # key -> (value, expires_at)
        self._cache: dict[
            str, tuple[list[dict[str, Any]], datetime]  # TODO(TYPE): replace Any with concrete type
        ] = {}  # TODO(TYPE): replace Any with concrete type

    # ------------------------------------------------------------------
    # Public query methods
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def _session_scope(self) -> AsyncIterator[AsyncSession]:
        """Yield the injected session or factory session; raise when neither is set.

        NOTE: All public methods wrap this in try/except Exception, so a RuntimeError
        from misconfiguration (no session, no factory) is caught and returns [] or None.
        That is pre-existing behaviour -- refactor callers to propagate in a future sprint.
        """
        db_session = getattr(self, "_db_session", None)
        session_factory = getattr(self, "_async_session_factory", None)
        if db_session is not None:
            yield db_session
        elif session_factory is not None:
            async with session_factory() as session:
                yield session
        else:
            raise RuntimeError(
                "AgentDiscoveryService requires either db_session or async_session_factory"
            )

    async def get_agents_by_department(
        self, dept: DepartmentFilter, limit: int = 1000
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Return all agents belonging to the given department for this tenant.

        Uses PostgreSQL JSONB containment (@>) to filter on capabilities.department.
        Falls back to a full scan + Python filter on SQLite (test env).
        """
        cache_key = f"dept:{dept.value}:{limit}:{self._tenant_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            async with self._session_scope() as session:
                stmt = select(RegisteredAgent).where(RegisteredAgent.tenant_id == self._tenant_id)
                if dept != DepartmentFilter.ALL:
                    # JSONB containment: capabilities @> '{"department": "<dept>"}'
                    # NOTE: .contains() is provided by SQLAlchemy JSONB / JSON column
                    stmt = stmt.where(
                        RegisteredAgent.capabilities.contains({"department": dept.value})
                    )
                stmt = stmt.limit(limit)
                result = await session.execute(stmt)
                agents = result.scalars().all()
                value = [self._agent_to_dict(a) for a in agents]
        except Exception as exc:
            logger.error(
                "get_agents_by_department failed for tenant_id=%s dept=%s: %s: %s",
                self._tenant_id,
                dept.value,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return []

        self._set_cache(cache_key, value)
        return value

    async def find_agent_by_id(
        self, agent_id: str
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """
        Return a single agent by its agent_id, scoped to this tenant.

        Returns None if not found or if the DB call fails.
        """
        cache_key = "id:{}:{}".format(agent_id, self._tenant_id)
        cached = self._get_cached(cache_key)
        if cached is not None:
            # Single-item results are stored as a one-element list
            return cached[0] if cached else None

        try:
            async with self._session_scope() as session:
                stmt = select(RegisteredAgent).where(
                    RegisteredAgent.agent_id == agent_id,
                    RegisteredAgent.tenant_id == self._tenant_id,
                )
                result = await session.execute(stmt)
                agent = result.scalar_one_or_none()
        except Exception as exc:
            logger.error(
                "find_agent_by_id failed for tenant_id=%s agent_id=%s: %s: %s",
                self._tenant_id,
                agent_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return None

        if agent is None:
            self._set_cache(cache_key, [])
            return None

        value = [self._agent_to_dict(agent)]
        self._set_cache(cache_key, value)
        return value[0]

    async def find_agents_by_function(
        self,
        function: str,
        department: DepartmentFilter | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Return agents whose capabilities.functions list contains *function*.

        Optionally narrows results to a specific department.
        """
        cache_key = f"func:{function}:{department}:{limit}:{self._tenant_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            async with self._session_scope() as session:
                # JSONB array containment: capabilities @> '{"functions": ["<fn>"]}'
                stmt = select(RegisteredAgent).where(
                    RegisteredAgent.tenant_id == self._tenant_id,
                    RegisteredAgent.capabilities.contains({"functions": [function]}),
                )
                if department is not None and department != DepartmentFilter.ALL:
                    stmt = stmt.where(
                        RegisteredAgent.capabilities.contains({"department": department.value})
                    )
                stmt = stmt.limit(limit)
                result = await session.execute(stmt)
                agents = result.scalars().all()
                value = [self._agent_to_dict(a) for a in agents]
        except Exception as exc:
            logger.error(
                "find_agents_by_function failed for tenant_id=%s function=%s: %s: %s",
                self._tenant_id,
                function,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return []

        self._set_cache(cache_key, value)
        return value

    async def find_agents_by_functions(
        self,
        caps: list[str],
        limit: int = 10,
    ) -> list[RegisteredAgent]:
        """Find registered agents by capability overlap.

        PostgreSQL path: uses JSONB @> containment with OR, activating the GIN index.
        TESTING path: full table scan + Python filter (SQLite has no JSONB operators).

        Args:
            caps: List of capability strings to match against agent capabilities.
            limit: Maximum number of agents to return (default 10).

        Returns:
            List of matching RegisteredAgent ORM objects.
        """
        if not caps:
            return []
        try:
            caps_lower = {c.lower() for c in caps}

            def _cap_set(val: Any) -> set[str]:  # TODO(TYPE): replace Any with concrete type
                if isinstance(val, list):
                    return {c.lower() for c in val}
                if isinstance(val, dict):
                    return {c.lower() for c in val.get("functions", [])}
                return set()

            if os.getenv("TESTING"):
                # SQLite does not support JSONB operators; fetch all agents for this tenant
                # then filter in Python. Queries ORM objects directly (not via _agent_to_dict)
                # so callers receive RegisteredAgent instances with .capabilities, .agent_id etc.
                async with self._session_scope() as session:
                    result = await session.execute(
                        select(RegisteredAgent).where(RegisteredAgent.tenant_id == self._tenant_id)
                    )
                    all_agents = list(result.scalars().all())
                matched = [
                    a for a in all_agents if caps_lower.intersection(_cap_set(a.capabilities))
                ]
                return matched[:limit]
            else:
                # PostgreSQL: JSONB @> containment on {"functions": [...]} activates GIN index.
                # Shape must match the stored dict schema -- a flat list would never match.
                conditions = [
                    RegisteredAgent.capabilities.contains({"functions": [cap]})
                    for cap in caps_lower
                ]
                async with self._session_scope() as session:
                    result = await session.execute(
                        select(RegisteredAgent)
                        .where(or_(*conditions))
                        .where(RegisteredAgent.tenant_id == self._tenant_id)
                        .limit(limit)
                    )
                    return list(result.scalars().all())
        except Exception as exc:
            logger.error(
                "find_agents_by_functions failed for tenant_id=%s: %s: %s",
                self._tenant_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return []

    async def find_best_agent_for_task(
        self,
        task_description: str,
        department: DepartmentFilter | None = None,
        capabilities: list[str] | None = None,
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """
        Return the agent best suited to handle *task_description*.

        Uses keyword overlap between the task description and the agent's
        functions list, plus exact capability matches when *capabilities*
        are provided. The agent with the highest overlap score is returned;
        returns None if no agents are available or all scores are zero.

        NOTE: No caching - result depends on the arbitrary task string.
        """
        try:
            if capabilities:
                orm_agents = await self.find_agents_by_functions(capabilities, limit=100)
                all_agents = [self._agent_to_dict(a) for a in orm_agents]
            elif department is not None and department != DepartmentFilter.ALL:
                all_agents = await self.get_agents_by_department(department)
            else:
                all_agents = await self.discover_all_agents()
        except Exception as exc:
            logger.error(
                "find_best_agent_for_task: agent discovery failed for tenant_id=%s: %s: %s",
                self._tenant_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return None

        if not all_agents:
            return None

        task_words = set(task_description.lower().split())
        cap_set = {c.lower() for c in (capabilities or [])}

        best_agent: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
        best_score = 0

        for agent in all_agents:
            # Optional department filter (if we fetched via find_agents_by_functions or discover_all_agents)
            if department is not None and department != DepartmentFilter.ALL:
                if agent.get("department") != department.value:
                    continue

            functions: list[str] = agent.get("functions", [])
            # Build a set of words from all function strings
            function_words: set[str] = set()
            for fn in functions:
                function_words.update(fn.lower().split("-"))

            # Base score from description word overlap
            score = len(task_words & function_words)

            # Boost from exact capability -> function matches
            if cap_set:
                exact_matches = cap_set.intersection({fn.lower() for fn in functions})
                score += len(exact_matches) * 3
                # Also word-level overlap from capabilities
                cap_words: set[str] = set()
                for cap in cap_set:
                    cap_words.update(cap.lower().split("-"))
                score += len(cap_words & function_words)

            if score > best_score:
                best_score = score
                best_agent = agent

        return best_agent if best_score > 0 else None

    async def discover_all_agents(
        self,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Return all registered agents for this tenant, up to a limit.
        """
        cache_key = f"all:{limit}:{self._tenant_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            async with self._session_scope() as session:
                stmt = select(RegisteredAgent).where(RegisteredAgent.tenant_id == self._tenant_id).limit(limit)
                result = await session.execute(stmt)
                agents = result.scalars().all()
                value = [self._agent_to_dict(a) for a in agents]
        except Exception as exc:
            logger.error(
                "discover_all_agents failed for tenant_id=%s: %s: %s",
                self._tenant_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return []

        self._set_cache(cache_key, value)
        return value

    async def get_department_summary(self) -> dict[str, int]:
        """
        Return a count of agents per department for this tenant.

        Example: {"STRATEGY": 2, "OPERATIONS": 4}
        """
        cache_key = "summary:%s" % self._tenant_id
        cached = self._get_cached(cache_key)
        if cached is not None:
            # Summary is stored as a one-element list wrapping the dict
            return cached[0] if cached else {}

        try:
            all_agents = await self.discover_all_agents()
        except Exception as exc:
            logger.error(
                "get_department_summary: discover_all_agents failed for tenant_id=%s: %s: %s",
                self._tenant_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return {}

        summary: dict[str, int] = {}
        for agent in all_agents:
            dept = agent.get("department", "UNKNOWN")
            summary[dept] = summary.get(dept, 0) + 1

        # Store as single-element list to reuse the same cache type
        self._set_cache(cache_key, [summary])
        return summary

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _agent_to_dict(
        self, agent: RegisteredAgent
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Convert a RegisteredAgent ORM row to a plain dict.

        Handles both parsed dict (PostgreSQL JSONB) and raw JSON string
        (SQLite test environment) for the capabilities column.
        """
        raw_caps = agent.capabilities
        if isinstance(raw_caps, str):
            try:
                # TODO(TYPE): replace Any with concrete type
                capabilities: dict[str, Any] = (
                    json.loads(  # TODO(TYPE): replace Any with concrete type
                        raw_caps
                    )
                )  # TODO(TYPE): replace Any with concrete type
            except (json.JSONDecodeError, TypeError):
                logger.error(
                    "_agent_to_dict: failed to parse capabilities JSON for agent_id=%s",
                    agent.agent_id,
                    exc_info=True,
                )
                capabilities = {}
        elif isinstance(raw_caps, dict):
            capabilities = raw_caps
        else:
            capabilities = {}

        return {
            "agent_id": agent.agent_id,
            "name": agent.name or agent.agent_id,
            "description": agent.description or "",
            "capabilities": capabilities,
            "department": capabilities.get("department", "UNKNOWN"),
            "functions": capabilities.get("functions", []),
            "is_service": capabilities.get("is_service", False),
            "agent_type": capabilities.get("agent_type", "SPECIALIST"),
        }

    def _get_cached(
        self, key: str
    ) -> list[dict[str, Any]] | None:  # TODO(TYPE): replace Any with concrete type
        """Return the cached value if it has not yet expired, else None."""
        if key in self._cache:
            value, expires_at = self._cache[key]
            if datetime.now(timezone.utc) < expires_at:
                return value
            del self._cache[key]
        return None

    def _set_cache(
        self,
        key: str,
        value: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Store *value* in the in-memory cache with a TTL of self._ttl seconds."""
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self._ttl)
        self._cache[key] = (value, expires_at)

    def invalidate_cache(self) -> int:
        """
        Clear all cached entries.

        Returns:
            Number of cache entries removed.
        """
        count = len(self._cache)
        self._cache.clear()
        logger.debug(
            "invalidate_cache: cleared %d entries for tenant_id=%s",
            count,
            self._tenant_id,
        )
        return count
