"""
Integration tests for AgentDiscoveryService + RegisteredAgent + seed_agent_registry.

Tests cover:
  - Functional: discover_all_agents, find_best_agent_for_task, find_agent_by_id, seeding
  - Tenant isolation: queries scoped exclusively to one tenant
  - Cache effectiveness: hit detection, invalidation, tenant scoping

Database: in-memory SQLite via aiosqlite (no PostgreSQL required).
The TESTING=1 env var is set before imports so RegisteredAgent uses SQLiteJSON.

NOTE: find_agents_by_department() and find_agents_by_function() use JSONB .contains()
which is not supported on SQLite. Those methods are NOT tested here.
"""

from __future__ import annotations

import os

# MUST be set before importing models (switches JSONB -> SQLiteJSON)
os.environ["TESTING"] = "1"

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Import Base + models AFTER env var is set
from src.core.database.database import Base
from src.core.agents.models import RegisteredAgent
from src.core.agents.agent_discovery import AgentDiscoveryService
from src.core.agents.seed_agent_registry import seed_agent_registry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite async session with tenants + registered_agents schema."""
    # Import Tenant model so its table is included in Base.metadata
    from src.core.models.rbac_models import Tenant  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        # Disable FK checks so we can insert registered_agents without full schema
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        await conn.run_sync(Base.metadata.create_all)
        # Seed minimal tenants so FK constraints pass when FK checks are re-enabled
        await conn.execute(
            text(
                "INSERT OR IGNORE INTO tenants (id, name, slug, is_active, max_users, max_agents, max_storage_gb) "
                "VALUES (1, 'Tenant One', 'tenant-one', 1, 10, 50, 5), "
                "(2, 'Tenant Two', 'tenant-two', 1, 10, 50, 5)"
            )
        )

    async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _make_agent(
    agent_id: str,
    name: str,
    description: str,
    tenant_id: int,
    functions: List[str],
    department: str = "OPERATIONS",
) -> RegisteredAgent:
    """Build a RegisteredAgent ORM object (not yet added to session)."""
    return RegisteredAgent(
        agent_id=agent_id,
        name=name,
        description=description,
        address="",
        capabilities={
            "department": department,
            "agent_type": "SPECIALIST",
            "specialization": "general",
            "functions": functions,
            "is_service": False,
        },
        last_heartbeat=datetime.now(timezone.utc),
        tenant_id=tenant_id,
    )


# ---------------------------------------------------------------------------
# Functional tests - happy paths
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_all_agents_returns_seeded_agents(db_session: AsyncSession) -> None:
    """discover_all_agents returns all agents seeded for the tenant."""
    db_session.add(_make_agent("agent_a", "Agent A", "desc A", 1, ["task_a"]))
    db_session.add(_make_agent("agent_b", "Agent B", "desc B", 1, ["task_b"]))
    db_session.add(_make_agent("agent_c", "Agent C", "desc C", 1, ["task_c"]))
    await db_session.commit()

    svc = AgentDiscoveryService(tenant_id=1, db_session=db_session)
    agents = await svc.discover_all_agents()

    assert len(agents) == 3
    agent_ids = {a["agent_id"] for a in agents}
    assert agent_ids == {"agent_a", "agent_b", "agent_c"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_best_agent_for_task_keyword_match(db_session: AsyncSession) -> None:
    """find_best_agent_for_task returns the agent whose functions best match the task."""
    # Use single-word functions so the keyword scorer can match individual words.
    # "legal" and "contracts" will overlap with the task description words.
    db_session.add(
        _make_agent(
            "legal_001",
            "Legal Agent",
            "Handles legal tasks",
            1,
            ["legal", "contracts"],
            department="LEGAL_COMPLIANCE",
        )
    )
    db_session.add(
        _make_agent(
            "finance_001",
            "Finance Agent",
            "Handles finance tasks",
            1,
            ["budget", "invoices"],
            department="FINANCE",
        )
    )
    await db_session.commit()

    svc = AgentDiscoveryService(tenant_id=1, db_session=db_session)
    # "legal" and "contracts" are in the task description and match the legal agent's functions
    result = await svc.find_best_agent_for_task("legal contracts review")

    assert result is not None
    assert result["agent_id"] == "legal_001"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_best_agent_for_task_returns_none_when_no_agents(
    db_session: AsyncSession,
) -> None:
    """find_best_agent_for_task returns None when no agents are registered."""
    svc = AgentDiscoveryService(tenant_id=1, db_session=db_session)
    result = await svc.find_best_agent_for_task("any task description")

    assert result is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_agent_by_id_returns_correct_agent(db_session: AsyncSession) -> None:
    """find_agent_by_id returns the matching agent dict for a known agent_id."""
    db_session.add(_make_agent("legal_agent_001", "Legal Agent", "Legal tasks", 1, ["contracts"]))
    await db_session.commit()

    svc = AgentDiscoveryService(tenant_id=1, db_session=db_session)
    result = await svc.find_agent_by_id("legal_agent_001")

    assert result is not None
    assert result["agent_id"] == "legal_agent_001"
    assert result["name"] == "Legal Agent"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_agent_by_id_returns_none_for_unknown(db_session: AsyncSession) -> None:
    """find_agent_by_id returns None for an agent_id that does not exist."""
    svc = AgentDiscoveryService(tenant_id=1, db_session=db_session)
    result = await svc.find_agent_by_id("nonexistent_agent_xyz")

    assert result is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_agent_registry_inserts_agents(db_session: AsyncSession) -> None:
    """seed_agent_registry inserts agents and reports correct counts."""
    agents: List[Dict[str, Any]] = [
        {"agent_id": "seed_a", "name": "Seed A", "functions": ["fn_a"]},
        {"agent_id": "seed_b", "name": "Seed B", "functions": ["fn_b"]},
        {"agent_id": "seed_c", "name": "Seed C", "functions": ["fn_c"]},
    ]

    result = await seed_agent_registry(db_session, agents, tenant_id=1)

    assert result["inserted"] == 3
    assert result["skipped"] == 0
    assert result["total"] == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_agent_registry_idempotent(db_session: AsyncSession) -> None:
    """Seeding the same agents twice skips duplicates on the second run."""
    agents: List[Dict[str, Any]] = [
        {"agent_id": "idem_a", "name": "Idem A", "functions": ["fn_a"]},
        {"agent_id": "idem_b", "name": "Idem B", "functions": ["fn_b"]},
    ]

    first = await seed_agent_registry(db_session, agents, tenant_id=1)
    second = await seed_agent_registry(db_session, agents, tenant_id=1)

    assert first == {"inserted": 2, "skipped": 0, "total": 2}
    assert second == {"inserted": 0, "skipped": 2, "total": 2}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_agent_registry_clear_existing(db_session: AsyncSession) -> None:
    """clear_existing=True replaces existing agents for the tenant."""
    initial_agents: List[Dict[str, Any]] = [
        {"agent_id": "old_a", "name": "Old A", "functions": []},
        {"agent_id": "old_b", "name": "Old B", "functions": []},
        {"agent_id": "old_c", "name": "Old C", "functions": []},
    ]
    await seed_agent_registry(db_session, initial_agents, tenant_id=1)

    new_agents: List[Dict[str, Any]] = [
        {"agent_id": "new_x", "name": "New X", "functions": []},
        {"agent_id": "new_y", "name": "New Y", "functions": []},
    ]
    result = await seed_agent_registry(db_session, new_agents, tenant_id=1, clear_existing=True)

    assert result["inserted"] == 2
    assert result["skipped"] == 0
    assert result["total"] == 2

    # Verify only the new agents exist for tenant 1
    svc = AgentDiscoveryService(tenant_id=1, db_session=db_session)
    agents_in_db = await svc.discover_all_agents()

    agent_ids = {a["agent_id"] for a in agents_in_db}
    assert "old_a" not in agent_ids
    assert "new_x" in agent_ids
    assert "new_y" in agent_ids


# ---------------------------------------------------------------------------
# Tenant isolation / security tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.asyncio
async def test_discover_all_agents_tenant_isolation(db_session: AsyncSession) -> None:
    """discover_all_agents only returns agents belonging to the requested tenant."""
    db_session.add(_make_agent("shared_id_t1", "T1 Legal", "tenant 1 agent", 1, ["contracts"]))
    db_session.add(_make_agent("shared_id_t2", "T2 Legal", "tenant 2 agent", 2, ["contracts"]))
    await db_session.commit()

    svc1 = AgentDiscoveryService(tenant_id=1, db_session=db_session)
    agents_t1 = await svc1.discover_all_agents()

    assert len(agents_t1) == 1
    assert agents_t1[0]["agent_id"] == "shared_id_t1"


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.asyncio
async def test_find_agent_by_id_tenant_isolation(db_session: AsyncSession) -> None:
    """find_agent_by_id does not return an agent that belongs to a different tenant."""
    db_session.add(_make_agent("agent_001", "T1 Agent", "tenant 1 only", 1, ["task_t1"]))
    db_session.add(_make_agent("agent_002", "T2 Agent", "tenant 2 only", 2, ["task_t2"]))
    await db_session.commit()

    # Tenant 2 service should NOT see agent_001 (owned by tenant 1)
    svc2 = AgentDiscoveryService(tenant_id=2, db_session=db_session)
    result = await svc2.find_agent_by_id("agent_001")

    assert result is None


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.asyncio
async def test_find_best_agent_cross_tenant_keyword_match_isolation(
    db_session: AsyncSession,
) -> None:
    """find_best_agent_for_task does not return agents from a different tenant."""
    db_session.add(
        _make_agent(
            "legal_t1",
            "Legal T1",
            "Legal agent tenant 1",
            1,
            ["legal", "contract"],
            department="LEGAL_COMPLIANCE",
        )
    )
    await db_session.commit()

    # Tenant 2 has no agents - should get None even though keywords match tenant 1's agent
    svc2 = AgentDiscoveryService(tenant_id=2, db_session=db_session)
    result = await svc2.find_best_agent_for_task("legal contract review")

    assert result is None


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.asyncio
async def test_seed_registry_clear_existing_does_not_affect_other_tenants(
    db_session: AsyncSession,
) -> None:
    """clear_existing=True for tenant 1 must not delete tenant 2's agents."""
    agents_t1: List[Dict[str, Any]] = [
        {"agent_id": "t1_agent_a", "name": "T1 A", "functions": []},
    ]
    agents_t2: List[Dict[str, Any]] = [
        {"agent_id": "t2_agent_b", "name": "T2 B", "functions": []},
        {"agent_id": "t2_agent_c", "name": "T2 C", "functions": []},
    ]

    await seed_agent_registry(db_session, agents_t1, tenant_id=1)
    await seed_agent_registry(db_session, agents_t2, tenant_id=2)

    # Clear and re-seed only tenant 1
    new_t1_agents: List[Dict[str, Any]] = [
        {"agent_id": "t1_agent_new", "name": "T1 New", "functions": []},
    ]
    await seed_agent_registry(db_session, new_t1_agents, tenant_id=1, clear_existing=True)

    # Tenant 2 agents must be unaffected
    svc2 = AgentDiscoveryService(tenant_id=2, db_session=db_session)
    agents_in_t2 = await svc2.discover_all_agents()

    t2_ids = {a["agent_id"] for a in agents_in_t2}
    assert "t2_agent_b" in t2_ids
    assert "t2_agent_c" in t2_ids
    assert "t1_agent_new" not in t2_ids


# ---------------------------------------------------------------------------
# Cache effectiveness tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discovery_cache_hit_avoids_repeated_db_query(db_session: AsyncSession) -> None:
    """Second call to discover_all_agents is served from cache (no additional DB query)."""
    db_session.add(_make_agent("cache_agent_1", "Cache Agent", "for cache test", 1, ["fn"]))
    await db_session.commit()

    original_execute = db_session.execute
    call_count = 0

    async def counting_execute(*args: Any, **kwargs: Any):  # type: ignore[override]
        nonlocal call_count
        call_count += 1
        return await original_execute(*args, **kwargs)

    db_session.execute = counting_execute  # type: ignore[method-assign]
    svc = AgentDiscoveryService(tenant_id=1, db_session=db_session)
    try:
        first = await svc.discover_all_agents()
        second = await svc.discover_all_agents()
    finally:
        db_session.execute = original_execute  # type: ignore[method-assign]

    # DB was hit exactly once; second call served from cache
    assert call_count == 1
    assert len(first) == 1
    assert second == first


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discovery_cache_invalidation_clears_cache(db_session: AsyncSession) -> None:
    """invalidate_cache() empties the internal cache dict."""
    db_session.add(_make_agent("inval_agent", "Invalidation Agent", "desc", 1, ["fn"]))
    await db_session.commit()

    svc = AgentDiscoveryService(tenant_id=1, db_session=db_session)
    await svc.discover_all_agents()

    assert len(svc._cache) > 0

    removed = svc.invalidate_cache()
    assert removed > 0
    assert len(svc._cache) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discovery_cache_tenant_scoped(db_session: AsyncSession) -> None:
    """Each AgentDiscoveryService instance maintains its own isolated cache."""
    db_session.add(_make_agent("t1_only", "T1 Only Agent", "tenant 1", 1, ["fn_t1"]))
    db_session.add(_make_agent("t2_only", "T2 Only Agent", "tenant 2", 2, ["fn_t2"]))
    await db_session.commit()

    svc1 = AgentDiscoveryService(tenant_id=1, db_session=db_session)
    svc2 = AgentDiscoveryService(tenant_id=2, db_session=db_session)

    # Limit expliciet meegeven: de cache-key is f"all:{limit}:{tenant_id}"
    # (agent_discovery.py:374). De test hardcodeerde "all:1" -- een oudere key-vorm
    # zonder limit-segment -- en stond daardoor rood na de paginering-wijziging
    # (OP-11 cluster F). Door de limit hier te bepalen kan de key niet opnieuw
    # verouderen zonder dat deze test het merkt.
    limit = 50
    await svc1.discover_all_agents(limit=limit)
    await svc2.discover_all_agents(limit=limit)

    # Each service has its own cache key scoped to its tenant
    cache_key_t1 = f"all:{limit}:1"
    cache_key_t2 = f"all:{limit}:2"
    assert cache_key_t1 in svc1._cache
    assert cache_key_t2 in svc2._cache
    # Cross-check: tenant 1 cache does not hold tenant 2 data
    assert cache_key_t2 not in svc1._cache
    assert cache_key_t1 not in svc2._cache
    # And the actual data is correct per tenant (agents are AgentDiscoveryItem dicts, no tenant_id key)
    agents_t1, _ = svc1._cache[cache_key_t1]
    agents_t2, _ = svc2._cache[cache_key_t2]
    ids_t1 = {a["agent_id"] for a in agents_t1}
    ids_t2 = {a["agent_id"] for a in agents_t2}
    assert "t1_only" in ids_t1
    assert "t2_only" not in ids_t1
    assert "t2_only" in ids_t2
    assert "t1_only" not in ids_t2
