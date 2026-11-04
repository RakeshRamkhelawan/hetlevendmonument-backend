"""
OODA Persistence Integration Tests (IT-1 through IT-8)

These tests verify that OODA agent state survives process restarts,
tenant data is properly isolated, and the end-to-end cycle works.

Uses in-memory SQLite for speed and test isolation.
"""

import os
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import event, pool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

os.environ.setdefault("TESTING", "1")

from src.core.agents.strategy_models import StrategicInsightModel as _SIM  # noqa: F401
from src.core.agents.strategy_models import StrategicObjectiveModel as _SOM
from src.core.agents.strategy_models import StrategyModel as _SM
from src.core.database.database import Base

# Ensure OODA models are registered with Base.metadata before create_all
from src.core.learning.persistence_models import (  # noqa: F401
    AdaptationRuleModel,
    LearningInsightModel,
    LearningPatternModel,
)
from src.core.models.rbac_models import (  # noqa: F401  (FK target for tenant_custom_data)
    Tenant as _Tenant,
)
from src.core.models.tenant_custom_data import TenantCustomData as _TCD  # noqa: F401

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def engine(postgres_engine: AsyncEngine) -> AsyncGenerator[AsyncEngine, None]:
    """Use shared PostgreSQL engine from conftest."""
    yield postgres_engine


@pytest_asyncio.fixture(scope="function")
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function")
async def session(
    postgres_session: AsyncSession,
) -> AsyncGenerator[AsyncSession, None]:
    """Use shared PostgreSQL session from conftest."""
    yield postgres_session


# ---------------------------------------------------------------------------
# IT-1: LearningLoop Survives Restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_learning_loop_survives_restart(session_factory):
    """IT-1: Learning patterns persisted and reloaded after 'restart'."""
    from src.core.agents.learning_loop import LearningLoop, LearningSource, LearningType
    from src.core.learning.learning_repository import LearningRepository
    from src.core.shared.config import set_feature_flag

    tenant_id = 1
    repo = LearningRepository(session_factory)

    set_feature_flag("learning_enabled", True)
    try:
        # --- First lifecycle ---
        loop1 = LearningLoop(tenant_id=tenant_id, repository=repo)

        # Simulate observing an event (this writes to DB via write-through)
        await loop1.observe(
            source=LearningSource.TASK_EXECUTION,
            learning_type=LearningType.PERFORMANCE_OPTIMIZATION,
            context={"task": "test-task"},
            observation_data={"success": True, "duration": 1.5},
        )

        # Verify in-memory state has the observation
        assert loop1.learning_metrics["total_observations"] > 0

        # --- "Restart" — new instance, same repo ---
        loop2 = LearningLoop(tenant_id=tenant_id, repository=repo)
        await loop2.load_persisted_state()

        # The observation should have been persisted through the repository
        # (patterns/rules/insights come from DB if any were created)
        # At minimum, the repository should have the observation stored
        async with session_factory() as session:
            from sqlalchemy import text

            result = await session.execute(
                text("SELECT count(*) FROM learning_experiences WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
            count = result.scalar()
        assert count >= 1, "Observation was not persisted to learning_experiences"
    finally:
        set_feature_flag("learning_enabled", False)


# ---------------------------------------------------------------------------
# IT-2: StrategyEngine Survives Restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strategy_engine_survives_restart(session_factory):
    """IT-2: Strategic insights are persisted and reloaded."""
    from src.core.agents.strategy_engine import StrategyEngine
    from src.core.agents.strategy_repository import StrategyRepository

    tenant_id = 1
    repo = StrategyRepository(session_factory)

    engine1 = StrategyEngine(tenant_id=tenant_id, repository=repo)

    # Create a strategic insight directly (bypass LLM)
    from src.core.agents.strategy_engine import StrategicInsight, StrategyType
    from src.core.agents.strategy_models import StrategicInsightModel

    insight = StrategicInsight(
        id=f"insight_{uuid.uuid4().hex[:8]}",
        type=StrategyType.MARKET_ANALYSIS,
        title="Test Market Insight",
        description="Integration test insight",
        confidence=0.9,
        impact_score=0.85,
        urgency_score=0.7,
        supporting_evidence=["data-1"],
        recommended_actions=["Expand market"],
        risks=["competition"],
        opportunities=["growth"],
    )
    engine1.insights[insight.id] = insight

    # Persist through ORM directly (pg_insert not available on SQLite)
    async with session_factory() as s:
        model = StrategicInsightModel(
            tenant_id=tenant_id,
            insight_id=insight.id,
            strategy_type=insight.type.value,
            title=insight.title,
            description=insight.description,
            confidence=insight.confidence,
            impact_score=insight.impact_score,
            urgency_score=insight.urgency_score,
            supporting_evidence=insight.supporting_evidence,
            recommended_actions=insight.recommended_actions,
            risks=insight.risks,
            opportunities=insight.opportunities,
        )
        s.add(model)
        await s.commit()

    # --- "Restart" ---
    engine2 = StrategyEngine(tenant_id=tenant_id, repository=repo)
    assert len(engine2.insights) == 0, "Fresh engine should start empty"

    await engine2.load_persisted_state()
    assert len(engine2.insights) >= 1, "Insight should be loaded from DB"
    assert insight.id in engine2.insights


# ---------------------------------------------------------------------------
# IT-3: Cross-Tenant Learning Isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_tenant_learning_isolation(session_factory):
    """IT-3: Tenant A's learning data is invisible to tenant B."""
    from src.core.agents.learning_loop import LearningLoop, LearningSource, LearningType
    from src.core.learning.learning_repository import LearningRepository
    from src.core.models.rbac_models import Tenant
    from src.core.shared.config import set_feature_flag

    # Create test tenants
    async with session_factory() as s:
        tenant_a = Tenant(name="learning_tenant_a", domain="learning-a.test")
        tenant_b = Tenant(name="learning_tenant_b", domain="learning-b.test")
        s.add(tenant_a)
        s.add(tenant_b)
        await s.commit()
        await s.refresh(tenant_a)
        await s.refresh(tenant_b)
        tenant_a_id = tenant_a.id
        tenant_b_id = tenant_b.id

    repo = LearningRepository(session_factory)

    set_feature_flag("learning_enabled", True)
    try:
        loop_a = LearningLoop(tenant_id=tenant_a_id, repository=repo)
        loop_b = LearningLoop(tenant_id=tenant_b_id, repository=repo)

        await loop_a.observe(
            source=LearningSource.TASK_EXECUTION,
            learning_type=LearningType.PATTERN_RECOGNITION,
            context={"task": "tenant-A-only"},
            observation_data={"success": True},
        )

        # Verify tenant A has data
        async with session_factory() as session:
            from sqlalchemy import text

            r_a = await session.execute(
                text("SELECT count(*) FROM learning_experiences WHERE tenant_id = :tenant_a_id"),
                {"tenant_a_id": tenant_a_id},
            )
            r_b = await session.execute(
                text("SELECT count(*) FROM learning_experiences WHERE tenant_id = :tenant_b_id"),
                {"tenant_b_id": tenant_b_id},
            )
            count_a = r_a.scalar()
            count_b = r_b.scalar()

        assert count_a >= 1, "Tenant A should have observations"
        assert count_b == 0, "Tenant B should have zero observations"

        # Load persisted state for B — should be empty
        await loop_b.load_persisted_state()
        # No crashed, no cross-leakage
    finally:
        set_feature_flag("learning_enabled", False)


# ---------------------------------------------------------------------------
# IT-4: Redis Memory Cross-Tenant Isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_memory_tenant_key_isolation():
    """IT-4: MemoryManager generates distinct Redis keys per tenant."""
    from src.core.memory.memory_manager import MemoryManager

    mm_1 = MemoryManager(tenant_id=1)
    mm_2 = MemoryManager(tenant_id=2)
    mm_global = MemoryManager()  # legacy, no tenant

    assert mm_1._redis_key("strategic") == "memory:1:strategic"
    assert mm_2._redis_key("strategic") == "memory:2:strategic"
    assert mm_global._redis_key("strategic") == "memory:strategic"

    # Ensure they are different
    assert mm_1._redis_key("strategic") != mm_2._redis_key("strategic")
    assert mm_1._redis_key("tactical") != mm_global._redis_key("tactical")


# ---------------------------------------------------------------------------
# IT-5: EventBus → Tenant-Scoped Memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_bus_routes_to_tenant_memory():
    """IT-5: EventBus.publish() uses tenant-scoped MemoryManager."""
    from src.core.memory.event_bus import Event, EventBus
    from src.core.memory.memory_manager import get_memory_manager_for_tenant

    bus = EventBus.__new__(EventBus)
    bus._subscribers = {}
    bus._recent_events = []
    bus._max_recent_events = 100
    bus._initialized = True

    tenant_id = 42
    captured_mm = {}

    async def mock_store_memory(**kwargs):
        return "mock-vector-id"

    # Patch the tenant context to return our tenant_id
    with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=tenant_id):
        # Patch the tenant-specific MemoryManager
        mock_mm = MagicMock()
        mock_mm.store_memory = AsyncMock(side_effect=mock_store_memory)

        with patch(
            "src.core.memory.event_bus.get_memory_manager_for_tenant",
            return_value=mock_mm,
        ) as patched_factory:
            event = Event(
                agent_id="test-agent",
                phase="OBSERVE",
                type="TEST_EVENT",
                content={"test": True},
            )
            await bus.publish(event)

            patched_factory.assert_called_once_with(tenant_id)
            mock_mm.store_memory.assert_called_once()


# ---------------------------------------------------------------------------
# IT-6: Tenant Custom Data CRUD API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_custom_data_crud(session_factory):
    """IT-6: TenantCustomData CRUD lifecycle via direct ORM (SQLite-compatible)."""
    from sqlalchemy import delete, select

    from src.core.models.tenant_custom_data import TenantCustomData

    tid = 1

    # INSERT
    async with session_factory() as s:
        row = TenantCustomData(
            tenant_id=tid,
            namespace="config",
            key="theme",
            value={"color": "blue"},
        )
        s.add(row)
        await s.commit()

    # GET
    async with session_factory() as s:
        stmt = select(TenantCustomData.value).where(
            TenantCustomData.tenant_id == tid,
            TenantCustomData.namespace == "config",
            TenantCustomData.key == "theme",
        )
        result = await s.execute(stmt)
        val = result.scalar_one_or_none()
    assert val == {"color": "blue"}

    # UPDATE
    async with session_factory() as s:
        stmt = select(TenantCustomData).where(
            TenantCustomData.tenant_id == tid,
            TenantCustomData.namespace == "config",
            TenantCustomData.key == "theme",
        )
        result = await s.execute(stmt)
        row = result.scalar_one()
        row.value = {"color": "red"}
        await s.commit()

    async with session_factory() as s:
        stmt = select(TenantCustomData.value).where(
            TenantCustomData.tenant_id == tid,
            TenantCustomData.namespace == "config",
            TenantCustomData.key == "theme",
        )
        result = await s.execute(stmt)
        val2 = result.scalar_one_or_none()
    assert val2 == {"color": "red"}

    # DELETE
    async with session_factory() as s:
        stmt = delete(TenantCustomData).where(
            TenantCustomData.tenant_id == tid,
            TenantCustomData.namespace == "config",
            TenantCustomData.key == "theme",
        )
        await s.execute(stmt)
        await s.commit()

    async with session_factory() as s:
        stmt = select(TenantCustomData.value).where(
            TenantCustomData.tenant_id == tid,
            TenantCustomData.namespace == "config",
            TenantCustomData.key == "theme",
        )
        result = await s.execute(stmt)
        val3 = result.scalar_one_or_none()
    assert val3 is None


# ---------------------------------------------------------------------------
# IT-7: Tenant Custom Data Cross-Tenant Isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_custom_data_cross_tenant_isolation(session_factory):
    """IT-7: Tenant A's custom data is invisible to tenant B."""
    from sqlalchemy import select

    from src.core.models.rbac_models import Tenant
    from src.core.models.tenant_custom_data import TenantCustomData

    # Create test tenants first
    async with session_factory() as s:
        tenant_a = Tenant(name="test_tenant_a", domain="a.test")
        tenant_b = Tenant(name="test_tenant_b", domain="b.test")
        s.add(tenant_a)
        s.add(tenant_b)
        await s.commit()
        await s.refresh(tenant_a)
        await s.refresh(tenant_b)
        tenant_a_id = tenant_a.id
        tenant_b_id = tenant_b.id

    # Tenant 100 sets a value
    async with session_factory() as s:
        s.add(
            TenantCustomData(
                tenant_id=tenant_a_id,
                namespace="secrets",
                key="api_key",
                value="tenant-100-key",
            )
        )
        await s.commit()

    # Tenant B cannot see it
    async with session_factory() as s:
        stmt = select(TenantCustomData.value).where(
            TenantCustomData.tenant_id == tenant_b_id,
            TenantCustomData.namespace == "secrets",
            TenantCustomData.key == "api_key",
        )
        result = await s.execute(stmt)
        val = result.scalar_one_or_none()
    assert val is None, "Tenant B should NOT see Tenant A's data"

    # Tenant B sets same namespace/key — should not overwrite Tenant A
    async with session_factory() as s:
        s.add(
            TenantCustomData(
                tenant_id=tenant_b_id,
                namespace="secrets",
                key="api_key",
                value="tenant-b-key",
            )
        )
        await s.commit()

    async with session_factory() as s:
        stmt_a = select(TenantCustomData.value).where(
            TenantCustomData.tenant_id == tenant_a_id,
            TenantCustomData.namespace == "secrets",
            TenantCustomData.key == "api_key",
        )
        stmt_b = select(TenantCustomData.value).where(
            TenantCustomData.tenant_id == tenant_b_id,
            TenantCustomData.namespace == "secrets",
            TenantCustomData.key == "api_key",
        )
        val_a = (await s.execute(stmt_a)).scalar_one_or_none()
        val_b = (await s.execute(stmt_b)).scalar_one_or_none()

    assert val_a == "tenant-100-key"
    assert val_b == "tenant-b-key"


# ---------------------------------------------------------------------------
# IT-8: End-to-End OODA Cycle with Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_end_to_end_ooda_cycle(session_factory):
    """IT-8: Full OODA observe → learn → persist → reload cycle."""
    from src.core.agents.learning_loop import LearningLoop, LearningSource, LearningType
    from src.core.agents.strategy_engine import StrategicInsight, StrategyEngine, StrategyType
    from src.core.agents.strategy_repository import StrategyRepository
    from src.core.learning.learning_repository import LearningRepository
    from src.core.shared.config import set_feature_flag

    from src.core.models.rbac_models import Tenant as _TenantModel

    async with session_factory() as _s:
        _t = _TenantModel(
            name=f"ooda_e2e_{uuid.uuid4().hex[:8]}", domain=f"e2e-{uuid.uuid4().hex[:8]}.test"
        )
        _s.add(_t)
        await _s.commit()
        await _s.refresh(_t)
        tenant_id = _t.id

    learning_repo = LearningRepository(session_factory)
    strategy_repo = StrategyRepository(session_factory)

    set_feature_flag("learning_enabled", True)
    try:
        # --- OBSERVE phase ---
        loop = LearningLoop(tenant_id=tenant_id, repository=learning_repo)
        for i in range(3):
            await loop.observe(
                source=LearningSource.TASK_EXECUTION,
                learning_type=LearningType.PERFORMANCE_OPTIMIZATION,
                context={"task": f"ooda-task-{i}"},
                observation_data={"success": i < 2, "duration": float(i)},
            )

        # --- ORIENT phase (strategy insight) ---
        engine = StrategyEngine(tenant_id=tenant_id, repository=strategy_repo)
        insight = StrategicInsight(
            id=f"ooda_insight_{uuid.uuid4().hex[:8]}",
            type=StrategyType.RISK_ASSESSMENT,
            title="Task failure rate rising",
            description="1 out of 3 tasks failed recently",
            confidence=0.8,
            impact_score=0.7,
            urgency_score=0.6,
            supporting_evidence=["learning_loop"],
            recommended_actions=["Increase monitoring"],
            risks=["downtime"],
            opportunities=["improve reliability"],
        )
        engine.insights[insight.id] = insight
        # Persist through ORM directly (pg_insert not available on SQLite)
        from src.core.agents.strategy_models import StrategicInsightModel

        async with session_factory() as s:
            model = StrategicInsightModel(
                tenant_id=tenant_id,
                insight_id=insight.id,
                strategy_type=insight.type.value,
                title=insight.title,
                description=insight.description,
                confidence=insight.confidence,
                impact_score=insight.impact_score,
                urgency_score=insight.urgency_score,
                supporting_evidence=insight.supporting_evidence,
                recommended_actions=insight.recommended_actions,
                risks=insight.risks,
                opportunities=insight.opportunities,
            )
            s.add(model)
            await s.commit()

        # --- Simulate restart ---
        loop2 = LearningLoop(tenant_id=tenant_id, repository=learning_repo)
        engine2 = StrategyEngine(tenant_id=tenant_id, repository=strategy_repo)

        await loop2.load_persisted_state()
        await engine2.load_persisted_state()

        # Verify observations survived
        async with session_factory() as session:
            from sqlalchemy import text

            result = await session.execute(
                text("SELECT count(*) FROM learning_experiences WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
            obs_count = result.scalar()
        assert obs_count == 3, f"Expected 3 observations, got {obs_count}"

        # Verify insight survived
        assert len(engine2.insights) >= 1
        assert insight.id in engine2.insights

        reloaded = engine2.insights[insight.id]
        assert reloaded.title == "Task failure rate rising"
        assert reloaded.impact_score == pytest.approx(0.7, abs=0.01)
    finally:
        set_feature_flag("learning_enabled", False)
