from __future__ import annotations

import pytest
from sqlalchemy import select

from src.core.governance.models import AuditLog
from src.core.learning.models import LearningExperience
from src.core.learning.persistence_models import (
    AdaptationRuleModel,
    LearningInsightModel,
    LearningPatternModel,
)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.no_mocks
async def test_admin_learning_status_and_audit_log_over_real_http(
    async_client,
    postgres_session,
    admin_auth_headers,
) -> None:
    postgres_session.add(
        LearningExperience(
            tenant_id=1,
            event_id="phase6-mandatory-status-observation",
            event_type="pattern_recognition",
            user_id="phase6-mandatory-user",
            agent_id="phase6-agent",
            task_type="governance_review",
            success=True,
            context={"agent_type": "python_pro", "source": "phase6-mandatory"},
            metrics={"success": 1.0},
        )
    )
    postgres_session.add(
        AuditLog(
            tenant_id=1,
            action="learning.mandatory_probe",
            resource="learning:phase6:mandatory",
            details={"source": "phase6-mandatory"},
            event_type="learning.mandatory_probe",
            threat_level="INFO",
            client_ip="SYSTEM",
            endpoint="LEARNING",
            description="learning.mandatory_probe",
            event_metadata={"source": "phase6-mandatory"},
        )
    )
    await postgres_session.commit()

    status_response = await async_client.get(
        "/admin/learning/status",
        headers=admin_auth_headers,
    )
    audit_response = await async_client.get(
        "/admin/learning/audit-log?limit=20",
        headers=admin_auth_headers,
    )

    assert status_response.status_code == 200
    assert audit_response.status_code == 200

    status_payload = status_response.json()
    audit_payload = audit_response.json()

    assert status_payload["tenant_id"] == 1
    assert status_payload["counts"]["observations"] >= 1
    assert "learning.mandatory_probe" in status_payload["recent_audit_actions"]
    assert audit_payload["tenant_id"] == 1
    assert audit_payload["total"] >= 1
    assert any(item["action"] == "learning.mandatory_probe" for item in audit_payload["items"])


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.no_mocks
async def test_gdpr_delete_user_cascades_and_audits_over_real_http(
    async_client,
    postgres_session,
    admin_auth_headers,
) -> None:
    user_id = "phase6-delete-user"
    postgres_session.add(
        LearningExperience(
            tenant_id=1,
            event_id="phase6-mandatory-delete-observation",
            event_type="tool_execution",
            user_id=user_id,
            agent_id="phase6-delete-agent",
            task_type="gdpr_cleanup",
            success=True,
            context={"user_id": user_id, "agent_type": "python_pro"},
            metrics={"success": 1.0},
        )
    )
    postgres_session.add(
        LearningPatternModel(
            tenant_id="1",
            pattern_id="phase6-delete-pattern",
            pattern_type="pattern_recognition",
            trigger_conditions={"user_id": user_id, "agent_type": "python_pro"},
            learned_behavior={"recommended_action": "delete", "subject_user_id": user_id},
            confidence_score=0.92,
            occurrence_count=4,
            success_rate=0.9,
        )
    )
    postgres_session.add(
        AdaptationRuleModel(
            id="phase6-delete-rule",
            rule_id="phase6-delete-rule",
            tenant_id="1",
            condition={"user_id": user_id},
            action={"route": "cleanup"},
            parameters={"user_id": user_id},
            is_active=True,
        )
    )
    postgres_session.add(
        LearningInsightModel(
            id="phase6-delete-insight",
            insight_id="phase6-delete-insight",
            tenant_id="1",
            conversation_id="system",
            insight_type="pattern_recognition",
            context={"user_id": user_id},
            evidence={"subject_user_id": user_id},
            confidence=0.85,
            confidence_score=0.85,
        )
    )
    await postgres_session.commit()

    delete_response = await async_client.post(
        "/admin/learning/gdpr/delete-user",
        headers=admin_auth_headers,
        json={"user_id": user_id, "reason": "phase6 mandatory proof"},
    )

    assert delete_response.status_code == 200
    payload = delete_response.json()
    assert payload["tenant_id"] == 1
    assert payload["user_id"] == user_id
    assert payload["total_deleted"] == 4
    assert payload["deleted_counts"]["observations"] == 1
    assert payload["deleted_counts"]["patterns"] == 1
    assert payload["deleted_counts"]["adaptations"] == 1
    assert payload["deleted_counts"]["insights"] == 1

    remaining_observations = (
        (
            await postgres_session.execute(
                select(LearningExperience).where(LearningExperience.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    remaining_patterns = (
        (
            await postgres_session.execute(
                select(LearningPatternModel).where(
                    LearningPatternModel.pattern_id == "phase6-delete-pattern"
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
                    AdaptationRuleModel.rule_id == "phase6-delete-rule"
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
                    LearningInsightModel.insight_id == "phase6-delete-insight"
                )
            )
        )
        .scalars()
        .all()
    )
    audit_rows = (
        (
            await postgres_session.execute(
                select(AuditLog).where(AuditLog.action == "gdpr.deletion_executed")
            )
        )
        .scalars()
        .all()
    )

    assert remaining_observations == []
    assert remaining_patterns == []
    assert remaining_rules == []
    assert remaining_insights == []
    assert any((row.details or {}).get("subject_user_id") == user_id for row in audit_rows)
