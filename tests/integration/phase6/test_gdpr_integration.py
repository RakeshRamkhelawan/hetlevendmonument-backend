from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.learning_loop import LearningSource, LearningType
from src.core.governance.models import AuditLog
from src.core.learning.cross_agent_service import CrossAgentLearningService
from src.core.learning.gdpr_service import LearningGDPRService
from src.core.learning.learning_repository import LearningRepository
from src.core.learning.metrics import record_learning_adaptation_applied
from src.core.learning.models import LearningExperience
from src.core.learning.persistence_models import (
    AdaptationRuleModel,
    LearningInsightModel,
    LearningPatternModel,
)
from src.core.learning.services.adaptation_service import AdaptationService
from src.core.learning.services.observation_service import ObservationService
from src.core.learning.services.pattern_service import PatternService
from src.core.models.rbac_models import Tenant
from src.core.monitoring.prometheus_metrics import (
    get_metrics,
    learning_adaptation_applied,
    learning_cross_agent_shares,
    learning_observations_total,
    learning_patterns_active,
)


def _counter_value(metric, **labels):
    return metric.labels(**labels)._value.get()


async def _seed_learning_records(
    session_factory, tenant_id: int = 17, user_id: str = "user-1"
) -> None:
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=45)
    async with session_factory() as session:
        session.add_all(
            [
                Tenant(
                    id=tenant_id,
                    name=f"Tenant {tenant_id}",
                    slug=f"tenant-{tenant_id}",
                    is_active=True,
                ),
                Tenant(
                    id=tenant_id + 1,
                    name=f"Tenant {tenant_id + 1}",
                    slug=f"tenant-{tenant_id + 1}",
                    is_active=True,
                ),
                LearningExperience(
                    tenant_id=tenant_id,
                    event_id="obs-user-1",
                    event_type="tool_execution",
                    user_id=user_id,
                    agent_id="agent-a",
                    context={"user_id": user_id, "agent_type": "python_pro"},
                    metrics={"success": 1.0},
                    created_at=old,
                ),
                LearningExperience(
                    tenant_id=tenant_id,
                    event_id="obs-user-2",
                    event_type="tool_execution",
                    user_id="user-2",
                    agent_id="agent-b",
                    context={"user_id": "user-2", "agent_type": "ai_engineer"},
                    metrics={"success": 1.0},
                    created_at=now,
                ),
                LearningExperience(
                    tenant_id=tenant_id + 1,
                    event_id="obs-other-tenant",
                    event_type="tool_execution",
                    user_id=user_id,
                    agent_id="agent-z",
                    context={"user_id": user_id},
                    metrics={"success": 1.0},
                    created_at=now,
                ),
                LearningPatternModel(
                    tenant_id=str(tenant_id),
                    pattern_id="pattern-user-1",
                    pattern_type="pattern_recognition",
                    trigger_conditions={"user_id": user_id, "agent_type": "python_pro"},
                    learned_behavior={"action": "optimize"},
                    confidence_score=0.9,
                    occurrence_count=3,
                    success_rate=0.8,
                    created_at=old,
                ),
                LearningPatternModel(
                    tenant_id=str(tenant_id),
                    pattern_id="pattern-shared-user-1",
                    pattern_type="pattern_recognition",
                    trigger_conditions={"user_id": user_id, "shared_pattern": True},
                    learned_behavior={"action": "share", "shared_pattern": True},
                    confidence_score=0.9,
                    occurrence_count=3,
                    success_rate=0.8,
                    created_at=old,
                ),
                LearningPatternModel(
                    tenant_id=str(tenant_id),
                    pattern_id="pattern-user-2",
                    pattern_type="pattern_recognition",
                    trigger_conditions={"user_id": "user-2", "agent_type": "ai_engineer"},
                    learned_behavior={"action": "keep"},
                    confidence_score=0.7,
                    occurrence_count=1,
                    success_rate=0.5,
                    created_at=now,
                ),
                AdaptationRuleModel(
                    id="rule-user-1",
                    rule_id="rule-user-1",
                    tenant_id=str(tenant_id),
                    condition={"user_id": user_id},
                    action={"route": "x"},
                    parameters={"user_id": user_id},
                    is_active=True,
                    created_at=old,
                ),
                AdaptationRuleModel(
                    id="rule-user-2",
                    rule_id="rule-user-2",
                    tenant_id=str(tenant_id),
                    condition={"user_id": "user-2"},
                    action={"route": "y"},
                    parameters={"user_id": "user-2"},
                    is_active=True,
                    created_at=now,
                ),
                LearningInsightModel(
                    id="insight-user-1",
                    insight_id="insight-user-1",
                    tenant_id=str(tenant_id),
                    conversation_id="system",
                    insight_type="pattern_recognition",
                    context={"user_id": user_id},
                    evidence={"subject": user_id},
                    confidence=0.8,
                    confidence_score=0.8,
                    created_at=old,
                ),
                LearningInsightModel(
                    id="insight-user-2",
                    insight_id="insight-user-2",
                    tenant_id=str(tenant_id),
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
@pytest.mark.integration
async def test_gdpr_delete_user_cascades_persisted_learning_records(
    phase6_learning_env,
    phase6_session_factory,
) -> None:
    await _seed_learning_records(phase6_session_factory)

    async with phase6_session_factory() as session:
        service = LearningGDPRService(session)
        report = await service.delete_user_data(
            user_id="user-1", tenant_id=17, requested_by_user_id=9
        )

    assert report.total_deleted == 5

    async with phase6_session_factory() as session:
        observations = (await session.execute(select(LearningExperience))).scalars().all()
        patterns = (await session.execute(select(LearningPatternModel))).scalars().all()
        rules = (await session.execute(select(AdaptationRuleModel))).scalars().all()
        insights = (await session.execute(select(LearningInsightModel))).scalars().all()

    assert {row.event_id for row in observations} == {"obs-user-2", "obs-other-tenant"}
    assert {row.pattern_id for row in patterns} == {"pattern-user-2"}
    assert {row.rule_id for row in rules} == {"rule-user-2"}
    assert {row.insight_id for row in insights} == {"insight-user-2"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_gdpr_export_returns_json_serializable_learning_payload(
    phase6_learning_env,
    phase6_session_factory,
) -> None:
    await _seed_learning_records(phase6_session_factory)

    async with phase6_session_factory() as session:
        service = LearningGDPRService(session)
        export = await service.export_user_data(
            user_id="user-1", tenant_id=17, requested_by_user_id=9
        )

    payload = export.model_dump(mode="json")

    assert export.total_records == 5
    assert len(payload["data"]["observations"]) == 1
    assert len(payload["data"]["patterns"]) == 2
    assert len(payload["data"]["adaptations"]) == 1
    assert len(payload["data"]["insights"]) == 1
    assert json.loads(json.dumps(payload))["user_id"] == "user-1"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_retention_policy_deletes_expired_learning_rows_only(
    phase6_learning_env,
    phase6_session_factory,
) -> None:
    await _seed_learning_records(phase6_session_factory)

    async with phase6_session_factory() as session:
        service = LearningGDPRService(session)
        report = await service.apply_retention_policy(
            max_age_days=30, tenant_id=17, requested_by_user_id=9
        )

    assert report.total_deleted == 5

    async with phase6_session_factory() as session:
        remaining_patterns = (await session.execute(select(LearningPatternModel))).scalars().all()
        remaining_observations = (await session.execute(select(LearningExperience))).scalars().all()

    assert {row.pattern_id for row in remaining_patterns} == {"pattern-user-2"}
    assert {row.event_id for row in remaining_observations} == {"obs-user-2", "obs-other-tenant"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_learning_metrics_increment_through_phase6_services(
    phase6_learning_env,
    phase6_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop_audit(**kwargs):
        return None

    monkeypatch.setattr(
        "src.core.learning.services.observation_service.log_learning_audit_event", _noop_audit
    )
    monkeypatch.setattr(
        "src.core.learning.services.pattern_service.log_learning_audit_event", _noop_audit
    )
    monkeypatch.setattr(
        "src.core.learning.services.adaptation_service.log_learning_audit_event", _noop_audit
    )
    monkeypatch.setattr(
        "src.core.learning.cross_agent_service.log_learning_audit_event", _noop_audit
    )

    repo = LearningRepository(phase6_session_factory)
    observation_service = ObservationService(
        tenant_id=21, repository=repo, observation_threshold=999
    )
    pattern_service = PatternService(tenant_id=21, repository=repo)
    adaptation_service = AdaptationService(tenant_id=21, repository=repo)
    cross_agent_service = CrossAgentLearningService(tenant_id=21, pattern_service=pattern_service)

    obs_before = _counter_value(
        learning_observations_total,
        tenant_id="21",
        learning_type="pattern_recognition",
    )
    pattern_before = learning_patterns_active.labels(tenant_id="21")._value.get()
    adaptation_before = _counter_value(
        learning_adaptation_applied,
        tenant_id="21",
        outcome="success",
    )
    share_before = _counter_value(
        learning_cross_agent_shares,
        tenant_id="21",
        source_agent_type="python_pro",
        target_agent_type="ai_engineer",
    )

    await observation_service.record(
        source=LearningSource.TASK_EXECUTION,
        learning_type=LearningType.PATTERN_RECOGNITION,
        context={"agent_id": "python-agent", "agent_type": "python_pro", "task_type": "analysis"},
        observation_data={"result": "ok"},
        outcome_metrics={"success_rate": 1.0, "execution_time": 0.3},
    )
    pattern = await pattern_service.register(
        pattern_type=LearningType.PATTERN_RECOGNITION,
        trigger_conditions={
            "agent_id": "python-agent",
            "agent_type": "python_pro",
            "task_type": "analysis",
        },
        learned_behavior={"recommended_action": "reuse"},
        observation_count=3,
        success_rate=0.95,
        confidence_score=0.9,
    )
    rule = await adaptation_service.create_from_pattern(pattern)
    await adaptation_service.apply(
        rule.id, {"agent_id": "python-agent", "agent_type": "python_pro", "task_type": "analysis"}
    )
    await cross_agent_service.share_pattern(pattern, source_agent_type="python_pro")

    assert (
        _counter_value(
            learning_observations_total,
            tenant_id="21",
            learning_type="pattern_recognition",
        )
        == obs_before + 1
    )
    assert learning_patterns_active.labels(tenant_id="21")._value.get() >= pattern_before + 1
    assert (
        _counter_value(
            learning_adaptation_applied,
            tenant_id="21",
            outcome="success",
        )
        == adaptation_before + 1
    )
    assert (
        _counter_value(
            learning_cross_agent_shares,
            tenant_id="21",
            source_agent_type="python_pro",
            target_agent_type="ai_engineer",
        )
        == share_before + 1
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_gdpr_audit_log_and_status_surface_recent_learning_governance_actions(
    phase6_learning_env,
    phase6_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_learning_records(phase6_session_factory)

    # The governance event bus handler writes to PostgreSQL via db_manager, which is
    # unavailable in SQLite phase6 tests. Intercept log_learning_audit_event to capture
    # events, then write them directly as AuditLog rows into the SQLite session.
    captured: list[dict[str, Any]] = []

    async def _capture_audit(
        *,
        action: str,
        resource: str,
        details: dict | None = None,
        tenant_id: int | None = None,
        user_id: int | None = None,
        session: Any = None,
    ) -> None:
        if tenant_id is None:
            return
        captured.append(
            {
                "action": action,
                "resource": resource,
                "details": details or {},
                "tenant_id": tenant_id,
            }
        )

    monkeypatch.setattr("src.core.learning.gdpr_service.log_learning_audit_event", _capture_audit)

    async with phase6_session_factory() as session:
        service = LearningGDPRService(session)
        await service.export_user_data(user_id="user-1", tenant_id=17, requested_by_user_id=9)
        await service.apply_retention_policy(max_age_days=30, tenant_id=17, requested_by_user_id=9)

    # Write captured events as AuditLog rows directly into the SQLite DB
    async with phase6_session_factory() as session:
        for evt in captured:
            session.add(
                AuditLog(
                    tenant_id=evt["tenant_id"],
                    action=evt["action"],
                    resource=evt["resource"],
                    details=evt["details"],
                    event_type=evt["action"],
                    threat_level="LOW",
                    client_ip="internal",
                    endpoint="LEARNING",
                    description=f"{evt['action']} on {evt['resource']}",
                    event_metadata=evt["details"],
                )
            )
        await session.commit()

    async def _reader(tenant_id: int, limit: int, offset: int, session: AsyncSession) -> list[Any]:
        result = await session.execute(
            select(AuditLog).where(AuditLog.tenant_id == tenant_id).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async with phase6_session_factory() as session:
        service = LearningGDPRService(session, audit_log_reader=_reader)
        audit_entries = await service.get_audit_log(tenant_id=17, limit=10)
        status = await service.get_status(tenant_id=17)

    actions = {entry.action for entry in audit_entries}

    assert "gdpr.export_executed" in actions
    assert "gdpr.retention_applied" in actions
    assert "gdpr.export_executed" in status.recent_audit_actions
    assert "gdpr.retention_applied" in status.recent_audit_actions
    assert status.counts["observations"] == 1

    async with phase6_session_factory() as session:
        audit_rows = (
            (await session.execute(select(AuditLog).where(AuditLog.tenant_id == 17)))
            .scalars()
            .all()
        )

    assert {row.action for row in audit_rows} >= {"gdpr.export_executed", "gdpr.retention_applied"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_admin_learning_endpoints_surface_real_phase6_data(
    async_client,
    postgres_session,
    admin_auth_headers,
) -> None:
    postgres_session.add(
        LearningExperience(
            tenant_id=1,
            event_id="phase6-admin-status-observation",
            event_type="pattern_recognition",
            user_id="phase6-user",
            agent_id="phase6-agent",
            context={"agent_type": "python_pro"},
            metrics={"success": 1.0},
        )
    )
    postgres_session.add(
        AuditLog(
            tenant_id=1,
            action="learning.phase6_probe",
            resource="learning:phase6",
            event_type="learning.phase6_probe",
            threat_level="INFO",
            client_ip="SYSTEM",
            endpoint="LEARNING",
            description="learning.phase6_probe",
            event_metadata={"source": "phase6-test"},
        )
    )
    await postgres_session.commit()

    status_response = await async_client.get(
        "/admin/learning/status",
        headers=admin_auth_headers,
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["tenant_id"] == 1
    assert status_payload["counts"]["observations"] >= 1

    audit_response = await async_client.get(
        "/admin/learning/audit-log?limit=20",
        headers=admin_auth_headers,
    )
    assert audit_response.status_code == 200
    audit_payload = audit_response.json()
    assert audit_payload["tenant_id"] == 1
    assert audit_payload["total"] >= 1
    assert any(item["action"] == "learning.phase6_probe" for item in audit_payload["items"])


@pytest.mark.asyncio
@pytest.mark.integration
async def test_admin_learning_export_user_over_real_http(
    async_client,
    postgres_session,
    admin_auth_headers,
) -> None:
    user_id = "phase6-export-user"
    postgres_session.add(
        LearningExperience(
            tenant_id=1,
            event_id="phase6-export-observation",
            event_type="tool_execution",
            user_id=user_id,
            agent_id="phase6-export-agent",
            context={"user_id": user_id, "agent_type": "python_pro"},
            metrics={"success": 1.0},
        )
    )
    postgres_session.add(
        LearningPatternModel(
            tenant_id="1",
            pattern_id="phase6-export-pattern",
            pattern_type="pattern_recognition",
            trigger_conditions={"user_id": user_id, "agent_type": "python_pro"},
            learned_behavior={"recommended_action": "reuse", "subject_user_id": user_id},
            confidence_score=0.91,
            occurrence_count=2,
            success_rate=0.85,
        )
    )
    postgres_session.add(
        AdaptationRuleModel(
            id="phase6-export-rule",
            rule_id="phase6-export-rule",
            tenant_id="1",
            condition={"user_id": user_id},
            action={"route": "analysis"},
            parameters={"user_id": user_id},
            is_active=True,
        )
    )
    postgres_session.add(
        LearningInsightModel(
            id="phase6-export-insight",
            insight_id="phase6-export-insight",
            tenant_id="1",
            conversation_id="system",
            insight_type="pattern_recognition",
            context={"user_id": user_id},
            evidence={"subject_user_id": user_id},
            confidence=0.84,
            confidence_score=0.84,
        )
    )
    await postgres_session.commit()

    response = await async_client.post(
        "/admin/learning/gdpr/export-user",
        headers=admin_auth_headers,
        json={"user_id": user_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == 1
    assert payload["user_id"] == user_id
    assert payload["total_records"] == 4
    assert len(payload["data"]["observations"]) == 1
    assert len(payload["data"]["patterns"]) == 1
    assert len(payload["data"]["adaptations"]) == 1
    assert len(payload["data"]["insights"]) == 1

    audit_rows = (
        (
            await postgres_session.execute(
                select(AuditLog).where(AuditLog.action == "gdpr.export_executed")
            )
        )
        .scalars()
        .all()
    )
    assert any((row.details or {}).get("subject_user_id") == user_id for row in audit_rows)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_admin_learning_retention_over_real_http(
    async_client,
    postgres_session,
    admin_auth_headers,
) -> None:
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=45)
    postgres_session.add_all(
        [
            LearningExperience(
                tenant_id=1,
                event_id="phase6-retention-old-observation",
                event_type="tool_execution",
                user_id="phase6-old-user",
                agent_id="phase6-retention-agent",
                context={"user_id": "phase6-old-user"},
                metrics={"success": 1.0},
                created_at=old,
            ),
            LearningExperience(
                tenant_id=1,
                event_id="phase6-retention-new-observation",
                event_type="tool_execution",
                user_id="phase6-new-user",
                agent_id="phase6-retention-agent",
                context={"user_id": "phase6-new-user"},
                metrics={"success": 1.0},
                created_at=now,
            ),
            LearningPatternModel(
                tenant_id="1",
                pattern_id="phase6-retention-old-pattern",
                pattern_type="pattern_recognition",
                trigger_conditions={"user_id": "phase6-old-user"},
                learned_behavior={"action": "cleanup"},
                confidence_score=0.9,
                occurrence_count=1,
                success_rate=0.8,
                created_at=old,
            ),
            LearningPatternModel(
                tenant_id="1",
                pattern_id="phase6-retention-new-pattern",
                pattern_type="pattern_recognition",
                trigger_conditions={"user_id": "phase6-new-user"},
                learned_behavior={"action": "keep"},
                confidence_score=0.9,
                occurrence_count=1,
                success_rate=0.8,
                created_at=now,
            ),
            AdaptationRuleModel(
                id="phase6-retention-old-rule",
                rule_id="phase6-retention-old-rule",
                tenant_id="1",
                condition={"user_id": "phase6-old-user"},
                action={"route": "cleanup"},
                parameters={"user_id": "phase6-old-user"},
                is_active=True,
                created_at=old,
            ),
            AdaptationRuleModel(
                id="phase6-retention-new-rule",
                rule_id="phase6-retention-new-rule",
                tenant_id="1",
                condition={"user_id": "phase6-new-user"},
                action={"route": "keep"},
                parameters={"user_id": "phase6-new-user"},
                is_active=True,
                created_at=now,
            ),
            LearningInsightModel(
                id="phase6-retention-old-insight",
                insight_id="phase6-retention-old-insight",
                tenant_id="1",
                conversation_id="system",
                insight_type="pattern_recognition",
                context={"user_id": "phase6-old-user"},
                evidence={"subject_user_id": "phase6-old-user"},
                confidence=0.8,
                confidence_score=0.8,
                created_at=old,
            ),
            LearningInsightModel(
                id="phase6-retention-new-insight",
                insight_id="phase6-retention-new-insight",
                tenant_id="1",
                conversation_id="system",
                insight_type="pattern_recognition",
                context={"user_id": "phase6-new-user"},
                evidence={"subject_user_id": "phase6-new-user"},
                confidence=0.8,
                confidence_score=0.8,
                created_at=now,
            ),
        ]
    )
    await postgres_session.commit()

    response = await async_client.post(
        "/admin/learning/gdpr/retention",
        headers=admin_auth_headers,
        json={"max_age_days": 30},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == 1
    assert payload["total_deleted"] == 4
    assert payload["deleted_counts"]["observations"] == 1
    assert payload["deleted_counts"]["patterns"] == 1
    assert payload["deleted_counts"]["adaptations"] == 1
    assert payload["deleted_counts"]["insights"] == 1

    remaining_observations = (
        (
            await postgres_session.execute(
                select(LearningExperience).where(
                    LearningExperience.event_id.in_(
                        [
                            "phase6-retention-old-observation",
                            "phase6-retention-new-observation",
                        ]
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    remaining_patterns = (
        (
            await postgres_session.execute(
                select(LearningPatternModel).where(
                    LearningPatternModel.pattern_id.in_(
                        [
                            "phase6-retention-old-pattern",
                            "phase6-retention-new-pattern",
                        ]
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    remaining_rules = (
        (
            await postgres_session.execute(
                select(AdaptationRuleModel).where(
                    AdaptationRuleModel.rule_id.in_(
                        [
                            "phase6-retention-old-rule",
                            "phase6-retention-new-rule",
                        ]
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    remaining_insights = (
        (
            await postgres_session.execute(
                select(LearningInsightModel).where(
                    LearningInsightModel.insight_id.in_(
                        [
                            "phase6-retention-old-insight",
                            "phase6-retention-new-insight",
                        ]
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    audit_rows = (
        (
            await postgres_session.execute(
                select(AuditLog).where(AuditLog.action == "gdpr.retention_applied")
            )
        )
        .scalars()
        .all()
    )

    assert {row.event_id for row in remaining_observations} == {"phase6-retention-new-observation"}
    assert {row.pattern_id for row in remaining_patterns} == {"phase6-retention-new-pattern"}
    assert {row.rule_id for row in remaining_rules} == {"phase6-retention-new-rule"}
    assert {row.insight_id for row in remaining_insights} == {"phase6-retention-new-insight"}
    assert any((row.details or {}).get("max_age_days") == 30 for row in audit_rows)


@pytest.mark.skip(
    reason="Prometheus registry interaction broken by _do_global_reset(): "
    "autouse fixture unregisters all custom metrics from REGISTRY between tests, "
    "but module-level metric objects in prometheus_metrics.py retain references to "
    "the unregistered collectors. Metrics ARE incremented correctly (verified by "
    "test_learning_metrics_increment_through_phase6_services), but generate_latest(REGISTRY) "
    "cannot see them. Fixing this requires either re-executing prometheus_metrics.py on every "
    "test or removing registry cleanup from _do_global_reset(). Both have broad side effects."
)
@pytest.mark.asyncio
@pytest.mark.integration
async def test_learning_metrics_are_exported_in_prometheus_scrape(
    phase6_learning_env,
    phase6_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop_audit(**kwargs):
        return None

    monkeypatch.setattr(
        "src.core.learning.services.observation_service.log_learning_audit_event", _noop_audit
    )
    monkeypatch.setattr(
        "src.core.learning.services.pattern_service.log_learning_audit_event", _noop_audit
    )
    monkeypatch.setattr(
        "src.core.learning.services.adaptation_service.log_learning_audit_event", _noop_audit
    )
    monkeypatch.setattr(
        "src.core.learning.cross_agent_service.log_learning_audit_event", _noop_audit
    )

    repo = LearningRepository(phase6_session_factory)
    observation_service = ObservationService(
        tenant_id=41, repository=repo, observation_threshold=999
    )
    pattern_service = PatternService(tenant_id=41, repository=repo)
    adaptation_service = AdaptationService(tenant_id=41, repository=repo)
    cross_agent_service = CrossAgentLearningService(tenant_id=41, pattern_service=pattern_service)

    await observation_service.record(
        source=LearningSource.TASK_EXECUTION,
        learning_type=LearningType.PATTERN_RECOGNITION,
        context={
            "agent_id": "phase6-metrics-agent",
            "agent_type": "python_pro",
            "task_type": "analysis",
        },
        observation_data={"result": "ok"},
        outcome_metrics={"success_rate": 1.0, "execution_time": 0.2},
    )
    pattern = await pattern_service.register(
        pattern_type=LearningType.PATTERN_RECOGNITION,
        trigger_conditions={
            "agent_id": "phase6-metrics-agent",
            "agent_type": "python_pro",
            "task_type": "analysis",
        },
        learned_behavior={"recommended_action": "reuse"},
        observation_count=2,
        success_rate=0.95,
        confidence_score=0.9,
    )
    rule = await adaptation_service.create_from_pattern(pattern)
    await adaptation_service.apply(
        rule.id,
        {"agent_id": "phase6-metrics-agent", "agent_type": "python_pro", "task_type": "analysis"},
    )
    await cross_agent_service.share_pattern(pattern, source_agent_type="python_pro")

    metrics_payload = get_metrics().decode("utf-8")
    assert "learning_observations_total" in metrics_payload
    assert "learning_patterns_active" in metrics_payload
    assert "learning_adaptation_applied" in metrics_payload
    assert "learning_cross_agent_shares" in metrics_payload
    assert 'tenant_id="41"' in metrics_payload
