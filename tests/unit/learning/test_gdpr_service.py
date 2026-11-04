from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.database.database import Base
from src.core.learning.gdpr_service import LearningGDPRService
from src.core.learning.models import LearningExperience
from src.core.learning.persistence_models import (
    AdaptationRuleModel,
    LearningInsightModel,
    LearningPatternModel,
)
from src.core.models.rbac_models import Tenant


@pytest_asyncio.fixture
async def gdpr_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add_all(
            [
                Tenant(id=41, name="Tenant A", slug="tenant-a", is_active=True),
                Tenant(id=42, name="Tenant B", slug="tenant-b", is_active=True),
            ]
        )
        await session.commit()
        yield session

    await engine.dispose()


async def _seed_learning_rows(session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=45)
    session.add_all(
        [
            LearningExperience(
                tenant_id=41,
                event_id="obs-user-1",
                event_type="tool_execution",
                user_id="user-1",
                agent_id="agent-a",
                context={"user_id": "user-1"},
                metrics={"success": 1.0},
                created_at=old,
            ),
            LearningExperience(
                tenant_id=41,
                event_id="obs-user-2",
                event_type="tool_execution",
                user_id="user-2",
                agent_id="agent-b",
                context={"user_id": "user-2"},
                metrics={"success": 1.0},
                created_at=now,
            ),
            LearningExperience(
                tenant_id=42,
                event_id="obs-other-tenant",
                event_type="tool_execution",
                user_id="user-1",
                agent_id="agent-z",
                context={"user_id": "user-1"},
                metrics={"success": 1.0},
                created_at=now,
            ),
            LearningPatternModel(
                tenant_id="41",
                pattern_id="pattern-user-1",
                pattern_type="pattern_recognition",
                trigger_conditions={"user_id": "user-1"},
                learned_behavior={"action": "optimize"},
                confidence_score=0.9,
                occurrence_count=3,
                success_rate=0.8,
                created_at=old,
            ),
            LearningPatternModel(
                tenant_id="41",
                pattern_id="pattern-shared-user-1",
                pattern_type="pattern_recognition",
                trigger_conditions={"user_id": "user-1", "shared_pattern": True},
                learned_behavior={"action": "share"},
                confidence_score=0.9,
                occurrence_count=3,
                success_rate=0.8,
                created_at=old,
            ),
            LearningPatternModel(
                tenant_id="41",
                pattern_id="pattern-user-2",
                pattern_type="pattern_recognition",
                trigger_conditions={"user_id": "user-2"},
                learned_behavior={"action": "keep"},
                confidence_score=0.7,
                occurrence_count=1,
                success_rate=0.5,
                created_at=now,
            ),
            AdaptationRuleModel(
                id="rule-user-1",
                rule_id="rule-user-1",
                tenant_id="41",
                condition={"user_id": "user-1"},
                action={"route": "x"},
                parameters={"user_id": "user-1"},
                is_active=True,
                created_at=old,
            ),
            AdaptationRuleModel(
                id="rule-user-2",
                rule_id="rule-user-2",
                tenant_id="41",
                condition={"user_id": "user-2"},
                action={"route": "y"},
                parameters={"user_id": "user-2"},
                is_active=True,
                created_at=now,
            ),
            LearningInsightModel(
                id="insight-user-1",
                insight_id="insight-user-1",
                tenant_id="41",
                conversation_id="system",
                insight_type="pattern_recognition",
                context={"user_id": "user-1"},
                evidence={"subject": "user-1"},
                confidence=0.8,
                confidence_score=0.8,
                created_at=old,
            ),
            LearningInsightModel(
                id="insight-user-2",
                insight_id="insight-user-2",
                tenant_id="41",
                conversation_id="system",
                insight_type="pattern_recognition",
                context={"user_id": "user-2"},
                evidence={"subject": "user-2"},
                confidence=0.8,
                confidence_score=0.8,
                created_at=now,
            ),
        ]
    )
    await session.commit()


@pytest.mark.asyncio
async def test_delete_user_data_cascades_across_learning_tables(gdpr_session: AsyncSession) -> None:
    await _seed_learning_rows(gdpr_session)
    service = LearningGDPRService(gdpr_session)

    report = await service.delete_user_data(user_id="user-1", tenant_id=41)

    assert report.total_deleted == 5
    assert report.deleted_counts["observations"] == 1
    assert report.deleted_counts["patterns"] == 1
    assert report.deleted_counts["shared_patterns"] == 1
    assert report.deleted_counts["adaptations"] == 1
    assert report.deleted_counts["insights"] == 1


@pytest.mark.asyncio
async def test_delete_user_data_reaches_rule_matched_only_by_trigger_keywords(
    gdpr_session: AsyncSession,
) -> None:
    """ADR-036 OP-32: een rij die de gebruiker UITSLUITEND via trigger_keywords koppelt.

    `condition`/`action`/`parameters` bevatten hier bewust geen verwijzing naar de gebruiker --
    anders bewijst deze test niets over `trigger_keywords`/`trigger_patterns` specifiek.
    """
    gdpr_session.add(
        AdaptationRuleModel(
            id="rule-keyword-only",
            rule_id="rule-keyword-only",
            tenant_id="41",
            condition={"topic": "billing"},
            action={"route": "z"},
            parameters={"threshold": 3},
            trigger_keywords=["user-1"],
            trigger_patterns=["fallback-pattern"],
            is_active=True,
        )
    )
    await gdpr_session.commit()
    service = LearningGDPRService(gdpr_session)

    report = await service.delete_user_data(user_id="user-1", tenant_id=41)

    assert report.deleted_counts["adaptations"] == 1
    remaining = (await gdpr_session.execute(select(AdaptationRuleModel))).scalars().all()
    assert "rule-keyword-only" not in {row.id for row in remaining}


@pytest.mark.asyncio
async def test_delete_user_data_reaches_observation_matched_only_by_dict_key(
    gdpr_session: AsyncSession,
) -> None:
    """ADR-036 OP-32: een gebruikersverwijzing die uitsluitend als dict-SLEUTEL voorkomt.

    `user_id` op de rij zelf is bewust anders, en de sleutel zit in `context`, nooit in een
    WAARDE -- anders bewijst deze test niets over de sleutel-recursie specifiek.
    """
    gdpr_session.add(
        LearningExperience(
            tenant_id=41,
            event_id="obs-key-only",
            event_type="tool_execution",
            user_id="system",
            agent_id="agent-a",
            context={"user-1": {"tool": "noop"}},
            metrics={"success": 1.0},
        )
    )
    await gdpr_session.commit()
    service = LearningGDPRService(gdpr_session)

    report = await service.delete_user_data(user_id="user-1", tenant_id=41)

    assert report.deleted_counts["observations"] == 1
    remaining = (await gdpr_session.execute(select(LearningExperience))).scalars().all()
    assert "obs-key-only" not in {row.event_id for row in remaining}


@pytest.mark.asyncio
async def test_delete_user_data_preserves_other_users(gdpr_session: AsyncSession) -> None:
    await _seed_learning_rows(gdpr_session)
    service = LearningGDPRService(gdpr_session)

    await service.delete_user_data(user_id="user-1", tenant_id=41)

    remaining = (await gdpr_session.execute(select(LearningExperience))).scalars().all()
    assert {row.event_id for row in remaining} == {"obs-user-2", "obs-other-tenant"}


@pytest.mark.asyncio
async def test_export_user_data_includes_all_learning_record_types(
    gdpr_session: AsyncSession,
) -> None:
    await _seed_learning_rows(gdpr_session)
    service = LearningGDPRService(gdpr_session)

    exported = await service.export_user_data(user_id="user-1", tenant_id=41)

    assert exported.total_records == 5
    assert len(exported.data["observations"]) == 1
    assert len(exported.data["patterns"]) == 2
    assert len(exported.data["adaptations"]) == 1
    assert len(exported.data["insights"]) == 1
    assert "conversations" in exported.data


@pytest.mark.asyncio
async def test_export_user_data_includes_trigger_keywords_and_patterns(
    gdpr_session: AsyncSession,
) -> None:
    """Gate-2-vervolg op OP-32: de wisroute matcht nu op deze velden, de export moet ze tonen.

    Anders vindt een art.-15/20-exportverzoek de rij wel (via trigger_keywords), maar toont de
    export niet WAAROM -- een inconsistentie tussen wis- en exportroute.
    """
    gdpr_session.add(
        AdaptationRuleModel(
            id="rule-export-keywords",
            rule_id="rule-export-keywords",
            tenant_id="41",
            condition={},
            action={},
            parameters={},
            trigger_keywords=["user-1"],
            trigger_patterns=["fallback-pattern"],
            is_active=True,
        )
    )
    await gdpr_session.commit()
    service = LearningGDPRService(gdpr_session)

    exported = await service.export_user_data(user_id="user-1", tenant_id=41)

    exported_rule = next(
        row for row in exported.data["adaptations"] if row["rule_id"] == "rule-export-keywords"
    )
    assert exported_rule["trigger_keywords"] == ["user-1"]
    assert exported_rule["trigger_patterns"] == ["fallback-pattern"]


@pytest.mark.asyncio
async def test_export_user_data_returns_empty_payload_when_no_records(
    gdpr_session: AsyncSession,
) -> None:
    service = LearningGDPRService(gdpr_session)

    exported = await service.export_user_data(user_id="missing-user", tenant_id=41)

    assert exported.total_records == 0
    assert exported.data == {
        "observations": [],
        "patterns": [],
        "adaptations": [],
        "insights": [],
        "conversations": [],  # GDPR-002: CVA gesprekken in portability export
    }


@pytest.mark.asyncio
async def test_retention_policy_deletes_old_learning_records(gdpr_session: AsyncSession) -> None:
    await _seed_learning_rows(gdpr_session)
    service = LearningGDPRService(gdpr_session)

    report = await service.apply_retention_policy(max_age_days=30, tenant_id=41)

    assert report.total_deleted == 5
    assert report.deleted_counts["observations"] == 1
    assert report.deleted_counts["patterns"] == 2
    assert report.deleted_counts["adaptations"] == 1
    assert report.deleted_counts["insights"] == 1


@pytest.mark.asyncio
async def test_retention_policy_preserves_recent_records(gdpr_session: AsyncSession) -> None:
    await _seed_learning_rows(gdpr_session)
    service = LearningGDPRService(gdpr_session)

    await service.apply_retention_policy(max_age_days=30, tenant_id=41)

    remaining_patterns = (await gdpr_session.execute(select(LearningPatternModel))).scalars().all()
    assert {row.pattern_id for row in remaining_patterns} == {"pattern-user-2"}


@pytest.mark.asyncio
async def test_delete_user_data_writes_audit_log(gdpr_session: AsyncSession) -> None:
    from unittest.mock import AsyncMock, patch

    await _seed_learning_rows(gdpr_session)
    service = LearningGDPRService(gdpr_session)

    with patch(
        "src.core.learning.gdpr_service.log_learning_audit_event",
        new_callable=AsyncMock,
    ) as mock_audit:
        await service.delete_user_data(user_id="user-1", tenant_id=41, requested_by_user_id=None)

    mock_audit.assert_awaited_once()
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs["action"] == "gdpr.deletion_executed"


@pytest.mark.asyncio
async def test_gdpr_operations_remain_tenant_scoped(gdpr_session: AsyncSession) -> None:
    await _seed_learning_rows(gdpr_session)
    service = LearningGDPRService(gdpr_session)

    await service.delete_user_data(user_id="user-1", tenant_id=41)

    other_tenant = await gdpr_session.execute(
        select(LearningExperience).where(LearningExperience.tenant_id == 42)
    )
    assert other_tenant.scalar_one().event_id == "obs-other-tenant"
