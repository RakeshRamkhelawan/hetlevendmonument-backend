from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.database.database import Base
from src.core.learning.learning_repository import LearningRepository
from src.core.learning.models import LearningExperience
from src.core.learning.persistence_models import (
    AdaptationRuleModel,
    LearningInsightModel,
    LearningPatternModel,
)
from src.core.learning.repository import AdaptationRuleRepository, LearningInsightRepository
from src.core.learning.services.adaptation_service import AdaptationService
from src.core.learning.services.insight_service import InsightService
from src.core.learning.services.observation_service import ObservationService
from src.core.learning.services.pattern_service import PatternService
from src.core.models.rbac_models import Tenant
from src.core.shared.config import reload_settings
from src.core.shared.interfaces import ExecutionResult, TaskData
from src.core.types import AgentType


class _PersistenceLearningAgent(EnhancedBaseAgent):
    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        return ExecutionResult(task_id=task.id, success=True, result_data={"task": task.title})


def _make_task(task_id: str) -> TaskData:
    return TaskData(
        id=task_id,
        title="Persistence rollout",
        description="Validate DB-backed learning rollout",
        metadata={"type": "text"},
    )


def _build_agent(tenant_id: int, agent_id: str) -> EnhancedBaseAgent:
    with (
        patch("src.core.agents.base_agent.get_settings") as mock_settings,
        patch("src.core.ai.router.AIRouter"),
        patch("src.core.ai.explainability.ReasoningTrace"),
    ):
        mock_settings.return_value.max_concurrent_tasks = 3
        return _PersistenceLearningAgent(
            agent_id=agent_id,
            agent_type=AgentType.SPECIALIST,
            tenant_id=tenant_id,
        )


def _make_learning_repository(session: AsyncSession) -> LearningRepository:
    @asynccontextmanager
    async def session_factory():
        yield session

    return LearningRepository(session_factory)


def _attach_db_backed_observation_service(agent: EnhancedBaseAgent, session: AsyncSession) -> None:
    agent._observation_service_instance = ObservationService(
        tenant_id=agent.tenant_id,
        repository=_make_learning_repository(session),
        observation_threshold=9999,
    )


async def _count_learning_records(session: AsyncSession, tenant_id: int) -> int:
    result = await session.execute(
        select(func.count(LearningExperience.id)).where(LearningExperience.tenant_id == tenant_id)
    )
    return int(result.scalar_one())


async def _count_pattern_records(session: AsyncSession, tenant_id: int) -> int:
    result = await session.execute(
        select(func.count(LearningPatternModel.id)).where(
            LearningPatternModel.tenant_id == tenant_id
        )
    )
    return int(result.scalar_one())


async def _count_rule_records(session: AsyncSession, tenant_id: int) -> int:
    result = await session.execute(
        select(func.count(AdaptationRuleModel.id)).where(AdaptationRuleModel.tenant_id == tenant_id)
    )
    return int(result.scalar_one())


async def _count_insight_records(session: AsyncSession, tenant_id: int) -> int:
    result = await session.execute(
        select(func.count(LearningInsightModel.id)).where(
            LearningInsightModel.tenant_id == tenant_id
        )
    )
    return int(result.scalar_one())


async def _get_first_rule_row(session: AsyncSession, tenant_id: int) -> AdaptationRuleModel:
    result = await session.execute(
        select(AdaptationRuleModel)
        .where(AdaptationRuleModel.tenant_id == tenant_id)
        .order_by(AdaptationRuleModel.created_at.asc())
    )
    return result.scalar_one()


async def _get_first_pattern_row(session: AsyncSession, tenant_id: int) -> LearningPatternModel:
    result = await session.execute(
        select(LearningPatternModel)
        .where(LearningPatternModel.tenant_id == tenant_id)
        .order_by(LearningPatternModel.created_at.asc())
    )
    return result.scalar_one()


async def _get_first_insight_row(session: AsyncSession, tenant_id: int) -> LearningInsightModel:
    result = await session.execute(
        select(LearningInsightModel)
        .where(LearningInsightModel.tenant_id == tenant_id)
        .order_by(LearningInsightModel.created_at.asc())
    )
    return result.scalar_one()


@pytest_asyncio.fixture(scope="function")
async def learning_db_session(monkeypatch: pytest.MonkeyPatch) -> AsyncSession:
    """Database session fixture with TESTING env var set to skip env file parsing."""
    # Set TESTING before any imports that load Settings
    monkeypatch.setenv("TESTING", "1")
    reload_settings()

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(
            Tenant(
                id=17,
                name="Phase 4 Learning Tenant",
                slug="phase4-learning-tenant",
                is_active=True,
            )
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest.fixture(scope="function")
def learning_env(monkeypatch: pytest.MonkeyPatch):
    """Function-scoped fixture to avoid global state leakage with session-scoped asyncio loop."""
    tracked_keys = ["FEATURE_LEARNING_ENABLED"]
    for key in tracked_keys:
        monkeypatch.delenv(key, raising=False)
    # TESTING env var is set by learning_db_session fixture
    reload_settings()
    yield monkeypatch
    for key in tracked_keys:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("TESTING", raising=False)
    reload_settings()


@pytest.mark.asyncio
async def test_learning_enablement_persists_real_observation_record(
    learning_env: pytest.MonkeyPatch,
    learning_db_session: AsyncSession,
) -> None:
    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    tenant_id = 17
    before_count = await _count_learning_records(learning_db_session, tenant_id)

    enabled_agent = _build_agent(tenant_id=tenant_id, agent_id="db-persist-agent")
    _attach_db_backed_observation_service(enabled_agent, learning_db_session)

    result = await enabled_agent.process_task(_make_task("db-persist-enable"))
    after_count = await _count_learning_records(learning_db_session, tenant_id)

    assert result.success is True
    assert enabled_agent._learning_enabled is True
    assert after_count == before_count + 1


@pytest.mark.asyncio
async def test_learning_rollback_prevents_new_db_observation_records(
    learning_env: pytest.MonkeyPatch,
    learning_db_session: AsyncSession,
) -> None:
    tenant_id = 17

    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    enabled_agent = _build_agent(tenant_id=tenant_id, agent_id="db-rollback-agent")
    _attach_db_backed_observation_service(enabled_agent, learning_db_session)

    initial_count = await _count_learning_records(learning_db_session, tenant_id)
    enabled_result = await enabled_agent.process_task(_make_task("db-before-rollback"))
    count_after_enable = await _count_learning_records(learning_db_session, tenant_id)

    learning_env.setenv("FEATURE_LEARNING_ENABLED", "false")
    reload_settings()

    disabled_agent = _build_agent(tenant_id=tenant_id, agent_id="db-rollback-agent")
    _attach_db_backed_observation_service(disabled_agent, learning_db_session)
    disabled_result = await disabled_agent.process_task(_make_task("db-after-rollback"))
    count_after_rollback = await _count_learning_records(learning_db_session, tenant_id)

    assert enabled_result.success is True
    assert disabled_result.success is True
    assert count_after_enable == initial_count + 1
    assert disabled_agent._learning_enabled is False
    assert count_after_rollback == count_after_enable


@pytest.mark.asyncio
async def test_learning_enablement_persists_pattern_rule_and_insight_artifacts(
    learning_env: pytest.MonkeyPatch,
    learning_db_session: AsyncSession,
) -> None:
    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    tenant_id = 17
    agent = _build_agent(tenant_id=tenant_id, agent_id="artifact-agent")
    agent._observation_service_instance = ObservationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
        observation_threshold=2,
    )

    patterns_before = await _count_pattern_records(learning_db_session, tenant_id)
    rules_before = await _count_rule_records(learning_db_session, tenant_id)
    insights_before = await _count_insight_records(learning_db_session, tenant_id)

    first = await agent.process_task(_make_task("artifact-enable-1"))
    second = await agent.process_task(_make_task("artifact-enable-2"))

    patterns_after = await _count_pattern_records(learning_db_session, tenant_id)
    rules_after = await _count_rule_records(learning_db_session, tenant_id)
    insights_after = await _count_insight_records(learning_db_session, tenant_id)

    assert first.success is True
    assert second.success is True
    assert patterns_after == patterns_before + 1
    assert rules_after == rules_before + 1
    assert insights_after == insights_before + 1


@pytest.mark.asyncio
async def test_learning_rollback_prevents_new_pattern_rule_and_insight_artifacts(
    learning_env: pytest.MonkeyPatch,
    learning_db_session: AsyncSession,
) -> None:
    tenant_id = 17
    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    enabled_agent = _build_agent(tenant_id=tenant_id, agent_id="artifact-rollback-agent")
    enabled_agent._observation_service_instance = ObservationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
        observation_threshold=2,
    )

    await enabled_agent.process_task(_make_task("artifact-rollback-1"))
    await enabled_agent.process_task(_make_task("artifact-rollback-2"))

    patterns_after_enable = await _count_pattern_records(learning_db_session, tenant_id)
    rules_after_enable = await _count_rule_records(learning_db_session, tenant_id)
    insights_after_enable = await _count_insight_records(learning_db_session, tenant_id)

    learning_env.setenv("FEATURE_LEARNING_ENABLED", "false")
    reload_settings()

    disabled_agent = _build_agent(tenant_id=tenant_id, agent_id="artifact-rollback-agent")
    disabled_agent._observation_service_instance = ObservationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
        observation_threshold=2,
    )

    await disabled_agent.process_task(_make_task("artifact-rollback-3"))
    await disabled_agent.process_task(_make_task("artifact-rollback-4"))

    patterns_after_rollback = await _count_pattern_records(learning_db_session, tenant_id)
    rules_after_rollback = await _count_rule_records(learning_db_session, tenant_id)
    insights_after_rollback = await _count_insight_records(learning_db_session, tenant_id)

    assert disabled_agent._learning_enabled is False
    assert patterns_after_rollback == patterns_after_enable
    assert rules_after_rollback == rules_after_enable
    assert insights_after_rollback == insights_after_enable


@pytest.mark.asyncio
async def test_learning_rollback_prevents_pattern_upsert_mutation(
    learning_env: pytest.MonkeyPatch,
    learning_db_session: AsyncSession,
) -> None:
    tenant_id = 17
    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    agent = _build_agent(tenant_id=tenant_id, agent_id="pattern-upsert-agent")
    agent._observation_service_instance = ObservationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
        observation_threshold=2,
    )
    await agent.process_task(_make_task("pattern-upsert-1"))
    await agent.process_task(_make_task("pattern-upsert-2"))

    learning_env.setenv("FEATURE_LEARNING_ENABLED", "false")
    reload_settings()

    repository = _make_learning_repository(learning_db_session)
    pattern = (await repository.get_active_patterns(tenant_id))[0]
    before_row = await _get_first_pattern_row(learning_db_session, tenant_id)

    pattern.observation_count = 99
    pattern.success_rate = 0.99
    pattern.confidence_score = 0.99
    await repository.save_pattern(tenant_id, pattern)

    after_row = await _get_first_pattern_row(learning_db_session, tenant_id)
    assert after_row.occurrence_count == before_row.occurrence_count
    assert after_row.success_rate == before_row.success_rate
    assert after_row.confidence_score == before_row.confidence_score


@pytest.mark.asyncio
async def test_learning_rollback_prevents_pattern_stats_mutation(
    learning_env: pytest.MonkeyPatch,
    learning_db_session: AsyncSession,
) -> None:
    tenant_id = 17
    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    agent = _build_agent(tenant_id=tenant_id, agent_id="pattern-stats-agent")
    agent._observation_service_instance = ObservationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
        observation_threshold=2,
    )
    await agent.process_task(_make_task("pattern-stats-1"))
    await agent.process_task(_make_task("pattern-stats-2"))

    learning_env.setenv("FEATURE_LEARNING_ENABLED", "false")
    reload_settings()

    pattern_service = PatternService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
    )
    await pattern_service.load_from_db()
    pattern = next(iter(pattern_service.patterns.values()))
    before_row = await _get_first_pattern_row(learning_db_session, tenant_id)

    await pattern_service.update_stats(pattern.id, 123, 0.12)

    after_row = await _get_first_pattern_row(learning_db_session, tenant_id)
    assert after_row.occurrence_count == before_row.occurrence_count
    assert after_row.success_rate == before_row.success_rate
    assert pattern_service.patterns[pattern.id].observation_count == before_row.occurrence_count
    assert pattern_service.patterns[pattern.id].success_rate == before_row.success_rate


@pytest.mark.asyncio
async def test_learning_enablement_updates_rule_application_stats(
    learning_env: pytest.MonkeyPatch,
    learning_db_session: AsyncSession,
) -> None:
    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    tenant_id = 17
    agent = _build_agent(tenant_id=tenant_id, agent_id="rule-stats-agent")
    agent._observation_service_instance = ObservationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
        observation_threshold=2,
    )

    await agent.process_task(_make_task("rule-stats-1"))
    await agent.process_task(_make_task("rule-stats-2"))

    rule_service = AdaptationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
    )
    await rule_service.load_from_db()
    rule = next(iter(rule_service.rules.values()))

    result = await rule_service.apply(
        rule.id,
        {
            "agent_id": "rule-stats-agent",
            "agent_type": "specialist",
            "task_type": "text",
            "source": "task_execution",
        },
    )
    updated_rule = await _get_first_rule_row(learning_db_session, tenant_id)

    assert result["success"] is True
    assert updated_rule.application_count == 1
    assert updated_rule.times_applied == 1
    assert updated_rule.success_count == 1
    assert updated_rule.success_rate == 1.0


@pytest.mark.asyncio
async def test_learning_rollback_prevents_rule_stats_mutation(
    learning_env: pytest.MonkeyPatch,
    learning_db_session: AsyncSession,
) -> None:
    tenant_id = 17
    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    agent = _build_agent(tenant_id=tenant_id, agent_id="rule-rollback-agent")
    agent._observation_service_instance = ObservationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
        observation_threshold=2,
    )
    await agent.process_task(_make_task("rule-rollback-1"))
    await agent.process_task(_make_task("rule-rollback-2"))

    learning_env.setenv("FEATURE_LEARNING_ENABLED", "false")
    reload_settings()

    rule_service = AdaptationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
    )
    await rule_service.load_from_db()
    rule = next(iter(rule_service.rules.values()))
    before_row = await _get_first_rule_row(learning_db_session, tenant_id)

    result = await rule_service.apply(
        rule.id,
        {
            "agent_id": "rule-rollback-agent",
            "agent_type": "specialist",
            "task_type": "text",
            "source": "task_execution",
        },
    )
    after_row = await _get_first_rule_row(learning_db_session, tenant_id)

    assert result["success"] is False
    assert result["reason"] == "Learning disabled"
    assert after_row.application_count == before_row.application_count
    assert after_row.times_applied == before_row.times_applied
    assert after_row.success_count == before_row.success_count
    assert after_row.success_rate == before_row.success_rate


@pytest.mark.asyncio
async def test_learning_rollback_prevents_rule_upsert_mutation(
    learning_env: pytest.MonkeyPatch,
    learning_db_session: AsyncSession,
) -> None:
    tenant_id = 17
    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    agent = _build_agent(tenant_id=tenant_id, agent_id="rule-upsert-agent")
    agent._observation_service_instance = ObservationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
        observation_threshold=2,
    )
    await agent.process_task(_make_task("rule-upsert-1"))
    await agent.process_task(_make_task("rule-upsert-2"))

    learning_env.setenv("FEATURE_LEARNING_ENABLED", "false")
    reload_settings()

    repository = _make_learning_repository(learning_db_session)
    rule = (await repository.get_active_rules(tenant_id))[0]
    before_row = await _get_first_rule_row(learning_db_session, tenant_id)

    rule.trigger_count = 99
    rule.success_count = 88
    rule.parameters["priority"] = 7
    await repository.save_rule(tenant_id, rule)

    after_row = await _get_first_rule_row(learning_db_session, tenant_id)
    assert after_row.application_count == before_row.application_count
    assert after_row.success_count == before_row.success_count
    assert after_row.times_applied == before_row.times_applied
    assert after_row.success_rate == before_row.success_rate


@pytest.mark.asyncio
async def test_learning_rollback_prevents_legacy_rule_usage_mutation(
    learning_env: pytest.MonkeyPatch,
    learning_db_session: AsyncSession,
) -> None:
    tenant_id = 17
    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    agent = _build_agent(tenant_id=tenant_id, agent_id="legacy-rule-agent")
    agent._observation_service_instance = ObservationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
        observation_threshold=2,
    )
    await agent.process_task(_make_task("legacy-rule-1"))
    await agent.process_task(_make_task("legacy-rule-2"))

    learning_env.setenv("FEATURE_LEARNING_ENABLED", "false")
    reload_settings()

    rule_row = await _get_first_rule_row(learning_db_session, tenant_id)
    legacy_rule_repo = AdaptationRuleRepository(learning_db_session)
    await legacy_rule_repo.increment_usage(rule_row.rule_id, success=True)
    after_row = await _get_first_rule_row(learning_db_session, tenant_id)

    assert after_row.application_count == rule_row.application_count
    assert after_row.success_count == rule_row.success_count
    assert after_row.times_applied == rule_row.times_applied
    assert after_row.success_rate == rule_row.success_rate


@pytest.mark.asyncio
async def test_learning_enablement_persists_insight_applied_update(
    learning_env: pytest.MonkeyPatch,
    learning_db_session: AsyncSession,
) -> None:
    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    tenant_id = 17
    agent = _build_agent(tenant_id=tenant_id, agent_id="insight-update-agent")
    agent._observation_service_instance = ObservationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
        observation_threshold=2,
    )
    await agent.process_task(_make_task("insight-update-1"))
    await agent.process_task(_make_task("insight-update-2"))

    insight_service = InsightService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
    )
    await insight_service.load_from_db()
    insight = next(iter(insight_service.insights.values()))

    updated = await insight_service.mark_applied(insight.id)
    updated_insight = await _get_first_insight_row(learning_db_session, tenant_id)

    assert updated is True
    assert updated_insight.processed is True
    assert updated_insight.adaptation_applied is True


@pytest.mark.asyncio
async def test_learning_rollback_prevents_insight_upsert_mutation(
    learning_env: pytest.MonkeyPatch,
    learning_db_session: AsyncSession,
) -> None:
    tenant_id = 17
    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    agent = _build_agent(tenant_id=tenant_id, agent_id="insight-upsert-agent")
    agent._observation_service_instance = ObservationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
        observation_threshold=2,
    )
    await agent.process_task(_make_task("insight-upsert-1"))
    await agent.process_task(_make_task("insight-upsert-2"))

    learning_env.setenv("FEATURE_LEARNING_ENABLED", "false")
    reload_settings()

    repository = _make_learning_repository(learning_db_session)
    insight = (await repository.get_recent_insights(tenant_id, limit=1))[0]
    before_row = await _get_first_insight_row(learning_db_session, tenant_id)

    object.__setattr__(insight, "processed", True)
    object.__setattr__(insight, "adaptation_applied", True)
    object.__setattr__(insight, "confidence_score", 0.95)
    await repository.save_insight(tenant_id, insight)

    after_row = await _get_first_insight_row(learning_db_session, tenant_id)
    assert after_row.processed == before_row.processed
    assert after_row.adaptation_applied == before_row.adaptation_applied
    assert after_row.confidence_score == before_row.confidence_score


@pytest.mark.asyncio
async def test_learning_rollback_prevents_insight_update_mutation(
    learning_env: pytest.MonkeyPatch,
    learning_db_session: AsyncSession,
) -> None:
    tenant_id = 17
    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    agent = _build_agent(tenant_id=tenant_id, agent_id="insight-rollback-agent")
    agent._observation_service_instance = ObservationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
        observation_threshold=2,
    )
    await agent.process_task(_make_task("insight-rollback-1"))
    await agent.process_task(_make_task("insight-rollback-2"))

    learning_env.setenv("FEATURE_LEARNING_ENABLED", "false")
    reload_settings()

    insight_service = InsightService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
    )
    await insight_service.load_from_db()
    insight = next(iter(insight_service.insights.values()))
    before_row = await _get_first_insight_row(learning_db_session, tenant_id)

    updated = await insight_service.mark_applied(insight.id)
    after_row = await _get_first_insight_row(learning_db_session, tenant_id)

    assert updated is False
    assert after_row.processed == before_row.processed
    assert after_row.adaptation_applied == before_row.adaptation_applied


@pytest.mark.asyncio
async def test_learning_rollback_prevents_legacy_insight_mark_processed_mutation(
    learning_env: pytest.MonkeyPatch,
    learning_db_session: AsyncSession,
) -> None:
    tenant_id = 17
    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    agent = _build_agent(tenant_id=tenant_id, agent_id="legacy-insight-agent")
    agent._observation_service_instance = ObservationService(
        tenant_id=tenant_id,
        repository=_make_learning_repository(learning_db_session),
        observation_threshold=2,
    )
    await agent.process_task(_make_task("legacy-insight-1"))
    await agent.process_task(_make_task("legacy-insight-2"))

    learning_env.setenv("FEATURE_LEARNING_ENABLED", "false")
    reload_settings()

    insight_row = await _get_first_insight_row(learning_db_session, tenant_id)
    legacy_insight_repo = LearningInsightRepository(learning_db_session)
    updated = await legacy_insight_repo.mark_processed(insight_row.id, str(tenant_id))
    after_row = await _get_first_insight_row(learning_db_session, tenant_id)

    assert updated is False
    assert after_row.processed == insight_row.processed
    assert after_row.adaptation_applied == insight_row.adaptation_applied
