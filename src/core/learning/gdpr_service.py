from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from src.core.conversations.models import CVAConversation

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.shared.learning_audit import log_learning_audit_event

from src.core.learning.gdpr_models import (
    GDPRDeletionReport,
    GDPRRetentionReport,
    LearningAuditEntry,
    LearningStatusReport,
    UserDataExport,
)
from src.core.learning.models import LearningExperience
from src.core.learning.persistence_models import (
    AdaptationRuleModel,
    LearningInsightModel,
    LearningPatternModel,
)
from src.core.shared.config import get_feature_flag

logger = logging.getLogger(__name__)


class _AuditRow(Protocol):
    id: int
    action: str | None
    resource: str | None
    user_id: int | None
    timestamp: datetime | None
    details: dict[str, object] | None


class LearningGDPRService:
    """GDPR and admin-governance operations for the learning subsystem."""

    def __init__(
        self,
        session: AsyncSession,
        audit_log_reader: Callable[
            [int, int, int, AsyncSession], Awaitable[Sequence[_AuditRow]]
        ]
        | None = None,
    ) -> None:
        self._session = session
        self._audit_log_reader = audit_log_reader

    async def delete_user_data(
        self,
        user_id: str,
        tenant_id: int,
        requested_by_user_id: int | None = None,
        reason: str | None = None,
    ) -> GDPRDeletionReport:
        """Delete learning data for a user within a tenant."""
        executed_at = datetime.now(timezone.utc)
        deleted_counts = {
            "observations": 0,
            "patterns": 0,
            "shared_patterns": 0,
            "adaptations": 0,
            "insights": 0,
        }

        observations = await self._load_observations(tenant_id=tenant_id, user_id=user_id)
        for record in observations:
            await self._session.delete(record)
        deleted_counts["observations"] = len(observations)

        patterns = await self._load_user_patterns(tenant_id=tenant_id, user_id=user_id)
        for record in patterns:
            if bool((record.trigger_conditions or {}).get("shared_pattern")):
                deleted_counts["shared_patterns"] += 1
            else:
                deleted_counts["patterns"] += 1
            await self._session.delete(record)

        rules = await self._load_user_rules(tenant_id=tenant_id, user_id=user_id)
        for record in rules:
            await self._session.delete(record)
        deleted_counts["adaptations"] = len(rules)

        insights = await self._load_user_insights(tenant_id=tenant_id, user_id=user_id)
        for record in insights:
            await self._session.delete(record)
        deleted_counts["insights"] = len(insights)

        await log_learning_audit_event(
            action="gdpr.deletion_executed",
            tenant_id=tenant_id,
            user_id=requested_by_user_id,
            resource=f"learning_user:{user_id}",
            details={
                "reason": reason,
                "deleted_counts": deleted_counts,
                "subject_user_id": user_id,
            },
            session=self._session,
        )
        await self._session.commit()

        return GDPRDeletionReport(
            tenant_id=tenant_id,
            user_id=user_id,
            deleted_counts=deleted_counts,
            total_deleted=sum(deleted_counts.values()),
            executed_at=executed_at,
        )

    async def export_user_data(
        self,
        user_id: str,
        tenant_id: int,
        requested_by_user_id: int | None = None,
    ) -> UserDataExport:
        """Export learning data for a user within a tenant."""
        observations = await self._load_observations(tenant_id=tenant_id, user_id=user_id)
        patterns = await self._load_user_patterns(tenant_id=tenant_id, user_id=user_id)
        rules = await self._load_user_rules(tenant_id=tenant_id, user_id=user_id)
        insights = await self._load_user_insights(tenant_id=tenant_id, user_id=user_id)
        conversations = await self._load_cva_conversations(tenant_id=tenant_id, user_id=user_id)

        export = UserDataExport(
            tenant_id=tenant_id,
            user_id=user_id,
            exported_at=datetime.now(timezone.utc),
            total_records=(
                len(observations) + len(patterns) + len(rules) + len(insights) + len(conversations)
            ),
            data={
                "observations": [self._serialize_observation(item) for item in observations],
                "patterns": [self._serialize_pattern(item) for item in patterns],
                "adaptations": [self._serialize_rule(item) for item in rules],
                "insights": [self._serialize_insight(item) for item in insights],
                "conversations": conversations,
            },
        )

        await log_learning_audit_event(
            action="gdpr.export_executed",
            tenant_id=tenant_id,
            user_id=requested_by_user_id,
            resource=f"learning_user:{user_id}",
            details={"subject_user_id": user_id, "total_records": export.total_records},
            session=self._session,
        )
        await self._session.commit()
        return export

    async def apply_retention_policy(
        self,
        max_age_days: int,
        tenant_id: int | None = None,
        requested_by_user_id: int | None = None,
    ) -> GDPRRetentionReport:
        """Delete learning records older than the configured threshold."""
        executed_at = datetime.now(timezone.utc)
        cutoff = executed_at - timedelta(days=max_age_days)
        tenant_pattern_id = str(tenant_id) if tenant_id is not None else None

        deleted_counts = {
            "observations": await self._delete_older_than(
                LearningExperience,
                LearningExperience.created_at,
                cutoff,
                tenant_field=LearningExperience.tenant_id,
                tenant_value=tenant_id,
            ),
            "patterns": await self._delete_older_than(
                LearningPatternModel,
                LearningPatternModel.created_at,
                cutoff,
                tenant_field=LearningPatternModel.tenant_id,
                tenant_value=tenant_pattern_id,
            ),
            "adaptations": await self._delete_older_than(
                AdaptationRuleModel,
                AdaptationRuleModel.created_at,
                cutoff,
                tenant_field=AdaptationRuleModel.tenant_id,
                tenant_value=tenant_pattern_id,
            ),
            "insights": await self._delete_older_than(
                LearningInsightModel,
                LearningInsightModel.created_at,
                cutoff,
                tenant_field=LearningInsightModel.tenant_id,
                tenant_value=tenant_pattern_id,
            ),
        }

        await log_learning_audit_event(
            action="gdpr.retention_applied",
            tenant_id=tenant_id,
            user_id=requested_by_user_id,
            resource="learning_retention",
            details={"max_age_days": max_age_days, "deleted_counts": deleted_counts},
            session=self._session,
        )
        await self._session.commit()

        return GDPRRetentionReport(
            tenant_id=tenant_id,
            max_age_days=max_age_days,
            deleted_counts=deleted_counts,
            total_deleted=sum(deleted_counts.values()),
            executed_at=executed_at,
        )

    async def get_status(self, tenant_id: int) -> LearningStatusReport:
        """Return an admin-friendly status overview for learning."""
        counts = {
            "observations": await self._count(
                LearningExperience, LearningExperience.tenant_id, tenant_id
            ),
            "patterns": await self._count(
                LearningPatternModel, LearningPatternModel.tenant_id, str(tenant_id)
            ),
            "adaptations": await self._count(
                AdaptationRuleModel, AdaptationRuleModel.tenant_id, str(tenant_id)
            ),
            "insights": await self._count(
                LearningInsightModel, LearningInsightModel.tenant_id, str(tenant_id)
            ),
        }
        audit_entries = await self.get_audit_log(tenant_id=tenant_id, limit=10)
        return LearningStatusReport(
            tenant_id=tenant_id,
            learning_enabled=get_feature_flag("learning_enabled"),
            counts=counts,
            recent_audit_actions=[entry.action or "unknown" for entry in audit_entries],
        )

    async def get_audit_log(
        self, tenant_id: int, limit: int = 50, offset: int = 0
    ) -> list[LearningAuditEntry]:
        """Return recent learning and GDPR audit entries for a tenant."""
        if self._audit_log_reader is None:
            return []
        rows = await self._audit_log_reader(tenant_id, limit, offset, self._session)
        return [
            LearningAuditEntry(
                id=row.id,
                action=row.action,
                resource=row.resource,
                user_id=row.user_id,
                timestamp=cast(datetime, row.timestamp),
                details=row.details or {},
            )
            for row in rows
        ]

    async def _load_observations(self, tenant_id: int, user_id: str) -> list[LearningExperience]:
        stmt = select(LearningExperience).where(LearningExperience.tenant_id == tenant_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [row for row in rows if self._observation_matches_user(row, user_id)]

    async def _load_user_patterns(self, tenant_id: int, user_id: str) -> list[LearningPatternModel]:
        stmt = select(LearningPatternModel).where(LearningPatternModel.tenant_id == str(tenant_id))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            row
            for row in rows
            if self._json_contains_user(row.trigger_conditions, user_id)
            or self._json_contains_user(row.learned_behavior, user_id)
        ]

    async def _load_user_rules(self, tenant_id: int, user_id: str) -> list[AdaptationRuleModel]:
        stmt = select(AdaptationRuleModel).where(AdaptationRuleModel.tenant_id == str(tenant_id))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            row
            for row in rows
            if self._json_contains_user(row.condition, user_id)
            or self._json_contains_user(row.action, user_id)
            or self._json_contains_user(row.parameters, user_id)
            or self._json_contains_user(row.trigger_keywords, user_id)
            or self._json_contains_user(row.trigger_patterns, user_id)
        ]

    async def _load_user_insights(self, tenant_id: int, user_id: str) -> list[LearningInsightModel]:
        stmt = select(LearningInsightModel).where(LearningInsightModel.tenant_id == str(tenant_id))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            row
            for row in rows
            if self._json_contains_user(row.context, user_id)
            or self._json_contains_user(row.evidence, user_id)
            or self._json_contains_user(row.impact_assessment, user_id)
            or self._json_contains_user(row.recommended_actions, user_id)
        ]

    async def _load_cva_conversations(
        self, tenant_id: int, user_id: str
    ) -> list[dict[str, object]]:
        """Load CVA conversation records for GDPR portability export (GDPR-002).

        Uses CVAConversation (denormalised flat table) which stores user_message +
        cva_response per turn. Only user-provided / user-facing fields are included
        (GDPR Art. 20: portability covers data the user actively provided).
        Internal fields (response_metadata, performance_data, attached_files,
        context_summary) are excluded to avoid leaking system telemetry.

        NOTE: conversations without a user_id match are excluded; pre-Phase-2 rows
        that were created with user_id=None (backwards-compat) are out of scope.
        TODO(GDPR-002-LIMIT): limit=1000 may produce incomplete exports for
        heavy users; cursor-based pagination needed before GA.
        """
        try:
            from src.core.conversations.models import CVAConversation

            result = await self._session.execute(
                select(CVAConversation)
                .where(
                    CVAConversation.tenant_id == tenant_id,
                    CVAConversation.user_id == user_id,
                )
                .order_by(CVAConversation.created_at.desc())
                .limit(1000)
            )
            return [self._serialize_cva_conversation(c) for c in result.scalars().all()]
        except Exception as exc:
            logger.warning(
                "gdpr_export: CVA conversation load failed, returning empty list: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return []

    def _serialize_cva_conversation(
        self, c: CVAConversation
    ) -> dict[str, object]:
        """Serialise a CVAConversation row for portability export (allowlisted fields only)."""
        return {
            "id": str(c.id),
            "session_id": c.session_id,
            "conversation_turn": c.conversation_turn,
            "user_message": c.user_message,
            "cva_response": c.cva_response,
            "user_feedback": c.user_feedback,
            "feedback_details": c.feedback_details,
            "conversation_topic": c.conversation_topic,
            "conversation_category": c.conversation_category,
            "keywords": c.keywords,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }

    async def _delete_older_than(
        self,
        model: Any,  # TODO(TYPE): replace Any with concrete type
        created_field: Any,  # TODO(TYPE): replace Any with concrete type
        cutoff: datetime,
        tenant_field: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        tenant_value: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> int:
        count_stmt = select(func.count()).select_from(model).where(created_field < cutoff)
        delete_stmt = delete(model).where(created_field < cutoff)
        if tenant_field is not None and tenant_value is not None:
            count_stmt = count_stmt.where(tenant_field == tenant_value)
            delete_stmt = delete_stmt.where(tenant_field == tenant_value)
        count = int((await self._session.execute(count_stmt)).scalar_one())
        if count:
            await self._session.execute(delete_stmt)
        return count

    async def _count(
        self,
        model: Any,  # TODO(TYPE): replace Any with concrete type
        tenant_field: Any,  # TODO(TYPE): replace Any with concrete type
        tenant_value: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> int:
        stmt = select(func.count()).select_from(model).where(tenant_field == tenant_value)
        return int((await self._session.execute(stmt)).scalar_one())

    def _observation_matches_user(self, record: LearningExperience, user_id: str) -> bool:
        if str(record.user_id or "") == user_id:
            return True
        return self._json_contains_user(record.context, user_id) or self._json_contains_user(
            record.metrics, user_id
        )

    def _json_contains_user(
        self,
        payload: Any,  # TODO(TYPE): replace Any with concrete type
        user_id: str,  # TODO(TYPE): Any -- JSON node: dict | list | str | int | None
    ) -> bool:
        if payload is None:
            return False
        if isinstance(payload, dict):
            return any(
                self._json_contains_user(key, user_id) or self._json_contains_user(value, user_id)
                for key, value in payload.items()
            )
        if isinstance(payload, (list, tuple, set)):
            return any(self._json_contains_user(value, user_id) for value in payload)
        return str(payload) == user_id

    def _serialize_observation(
        self, record: LearningExperience
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "event_id": record.event_id,
            "event_type": record.event_type,
            "agent_id": record.agent_id,
            "task_type": record.task_type,
            "user_id": record.user_id,
            "success": record.success,
            "duration": record.duration,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "context": record.context or {},
            "metrics": record.metrics or {},
        }

    def _serialize_pattern(
        self, record: LearningPatternModel
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "pattern_id": record.pattern_id,
            "pattern_type": record.pattern_type,
            "agent_id": record.agent_id,
            "source": record.source,
            "confidence_score": record.confidence_score,
            "occurrence_count": record.occurrence_count,
            "success_rate": record.success_rate,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "trigger_conditions": record.trigger_conditions or {},
            "learned_behavior": record.learned_behavior or {},
        }

    def _serialize_rule(
        self, record: AdaptationRuleModel
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "rule_id": record.rule_id,
            "rule_type": record.rule_type,
            "confidence": record.confidence,
            "priority": record.priority,
            "times_applied": record.times_applied,
            "success_rate": record.success_rate,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "condition": record.condition or {},
            "action": record.action or {},
            "parameters": record.parameters or {},
            "trigger_keywords": record.trigger_keywords or [],
            "trigger_patterns": record.trigger_patterns or [],
        }

    def _serialize_insight(
        self, record: LearningInsightModel
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "insight_id": record.insight_id,
            "insight_type": record.insight_type,
            "title": record.title,
            "description": record.description,
            "confidence_score": record.confidence_score,
            "adaptation_applied": record.adaptation_applied,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "context": record.context or {},
            "evidence": record.evidence or {},
            "impact_assessment": record.impact_assessment or {},
            "recommended_actions": record.recommended_actions or [],
        }
