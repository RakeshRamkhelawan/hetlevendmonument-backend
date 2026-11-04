"""Deprecated compatibility repository for legacy learning flows.

New agent learning integrations should use ``src.core.learning.learning_repository``
through ``LearningMixin`` and the service-layer components. This module remains in
place for compatibility with older feedback-loop paths that still operate on the
legacy rule and insight models.
"""

from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.core.learning.loop import AdaptationRule, FeedbackRating, LearningInsight
from src.core.learning.persistence_models import AdaptationRuleModel, LearningInsightModel
from src.core.shared.config import get_feature_flag


class AdaptationRuleRepository:
    """
    Repository for adaptation rules with PostgreSQL persistence.

    Design decisions:
    - AsyncSession is injected (FastAPI Depends pattern)
    - All operations are tenant-scoped (security)
    - UPSERT for idempotent writes
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, rule: AdaptationRule, tenant_id: str) -> str:
        """
        Save rule with UPSERT (insert or update).

        Args:
            rule: Pydantic AdaptationRule model
            tenant_id: Multi-tenant isolation key

        Returns:
            rule_id: The saved rule ID
        """
        if not get_feature_flag("learning_enabled"):
            return str(rule.id)

        # Convert Pydantic model to dict, handling datetime
        rule_data = {
            "id": rule.id,
            "tenant_id": tenant_id,
            "rule_type": rule.rule_type,
            "trigger_keywords": rule.trigger_keywords or [],
            "trigger_patterns": rule.trigger_patterns or [],
            "target_supervisor": rule.target_supervisor,
            "target_agent": rule.target_agent,
            "confidence": rule.confidence,
            "priority": rule.priority,
            "times_applied": rule.times_applied,
            "success_rate": rule.success_rate,
            "is_active": rule.active,
            "updated_at": datetime.now(timezone.utc),
        }

        stmt = (
            pg_insert(AdaptationRuleModel)
            .values(**rule_data)
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "trigger_keywords": rule_data["trigger_keywords"],
                    "trigger_patterns": rule_data["trigger_patterns"],
                    "target_supervisor": rule_data["target_supervisor"],
                    "target_agent": rule_data["target_agent"],
                    "confidence": rule_data["confidence"],
                    "priority": rule_data["priority"],
                    "is_active": rule_data["is_active"],
                    "updated_at": rule_data["updated_at"],
                },
            )
        )

        await self._session.execute(stmt)
        await self._session.commit()
        return str(rule.id)

    async def get_by_id(self, rule_id: str, tenant_id: str) -> AdaptationRule | None:
        """Get a specific rule by ID."""
        result = await self._session.execute(
            select(AdaptationRuleModel).where(
                AdaptationRuleModel.id == rule_id, AdaptationRuleModel.tenant_id == tenant_id
            )
        )
        row = result.scalar_one_or_none()
        return self._to_pydantic(row) if row else None

    async def get_active_rules(self, tenant_id: str, limit: int = 100) -> list[AdaptationRule]:
        """
        Get active rules for a tenant, sorted by priority (highest first).
        """
        result = await self._session.execute(
            select(AdaptationRuleModel)
            .where(
                AdaptationRuleModel.tenant_id == tenant_id, AdaptationRuleModel.is_active.is_(True)
            )
            .order_by(AdaptationRuleModel.priority.desc())
            .limit(limit)
        )

        rows = result.scalars().all()
        return [self._to_pydantic(row) for row in rows]

    async def get_all_rules(
        self, tenant_id: str, active_only: bool = True, limit: int = 100
    ) -> list[AdaptationRule]:
        """Get rules with optional filtering."""
        query = select(AdaptationRuleModel).where(AdaptationRuleModel.tenant_id == tenant_id)

        if active_only:
            query = query.where(AdaptationRuleModel.is_active.is_(True))

        query = query.order_by(AdaptationRuleModel.priority.desc()).limit(limit)

        result = await self._session.execute(query)
        rows = result.scalars().all()
        return [self._to_pydantic(row) for row in rows]

    async def increment_usage(self, rule_id: str, success: bool = True) -> None:
        """
        Atomic increment of times_applied and success_rate.
        """
        if not get_feature_flag("learning_enabled"):
            return

        # Get current values
        result = await self._session.execute(
            select(AdaptationRuleModel.times_applied, AdaptationRuleModel.success_rate).where(
                AdaptationRuleModel.id == rule_id
            )
        )
        row = result.one_or_none()

        if not row:
            return

        times_applied, success_rate = row
        new_times = (times_applied or 0) + 1

        # Calculate new success rate
        if success:
            new_success_rate = (((success_rate or 0) * (times_applied or 0)) + 1) / new_times
        else:
            new_success_rate = ((success_rate or 0) * (times_applied or 0)) / new_times

        await self._session.execute(
            update(AdaptationRuleModel)
            .where(AdaptationRuleModel.id == rule_id)
            .values(times_applied=new_times, success_rate=new_success_rate)
        )
        await self._session.commit()

    async def activate(self, rule_id: str, tenant_id: str) -> bool:
        """Activate a rule. Returns True if successful."""
        result = await self._session.execute(
            update(AdaptationRuleModel)
            .where(AdaptationRuleModel.id == rule_id, AdaptationRuleModel.tenant_id == tenant_id)
            .values(is_active=True, updated_at=datetime.now(timezone.utc))
        )
        await self._session.commit()
        return getattr(result, "rowcount", 0) > 0

    async def deactivate(self, rule_id: str, tenant_id: str) -> bool:
        """Deactivate a rule. Returns True if successful."""
        result = await self._session.execute(
            update(AdaptationRuleModel)
            .where(AdaptationRuleModel.id == rule_id, AdaptationRuleModel.tenant_id == tenant_id)
            .values(is_active=False, updated_at=datetime.now(timezone.utc))
        )
        await self._session.commit()
        return getattr(result, "rowcount", 0) > 0

    async def delete(self, rule_id: str, tenant_id: str) -> bool:
        """Delete a rule permanently."""
        result = await self._session.execute(
            delete(AdaptationRuleModel).where(
                AdaptationRuleModel.id == rule_id, AdaptationRuleModel.tenant_id == tenant_id
            )
        )
        await self._session.commit()
        return getattr(result, "rowcount", 0) > 0

    async def count_recent(self, tenant_id: int, agent: str, hours: int = 24) -> int:
        """Count governance blocks for a specific agent in the last N hours.

        Used by ComplianceGuardianAgent to detect repeated block patterns (Art. 17).

        Args:
            tenant_id: Tenant scope.
            agent: Target agent name.
            hours: Look-back window in hours (default 24).

        Returns:
            Number of matching adaptation rules created within the window.
        """
        from datetime import datetime, timedelta, timezone

        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(func.count())
            .select_from(AdaptationRuleModel)
            .where(AdaptationRuleModel.tenant_id == str(tenant_id))
            .where(AdaptationRuleModel.target_agent == agent)
            .where(AdaptationRuleModel.created_at >= since)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() or 0

    def _to_pydantic(self, row: AdaptationRuleModel) -> AdaptationRule:
        """Convert SQLAlchemy model to Pydantic."""
        return AdaptationRule(
            id=row.id,
            rule_type=row.rule_type,
            trigger_keywords=list(row.trigger_keywords) if row.trigger_keywords else [],
            trigger_patterns=list(row.trigger_patterns) if row.trigger_patterns else [],
            target_supervisor=row.target_supervisor,
            target_agent=row.target_agent,
            confidence=row.confidence,
            priority=row.priority,
            times_applied=row.times_applied,
            success_rate=row.success_rate,
            active=row.is_active,
        )


class LearningInsightRepository:
    """Repository for learning insights."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, insight: LearningInsight, tenant_id: str) -> str:
        """Save insight to database."""
        if not get_feature_flag("learning_enabled"):
            return insight.id

        insight_data = {
            "id": insight.id,
            "tenant_id": tenant_id,
            "conversation_id": insight.conversation_id,
            "insight_type": insight.category or "general_feedback",
            "category": insight.category,
            "rating": insight.rating.value if insight.rating else None,
            "comment": insight.comment,
            "confidence": insight.confidence,
            "context": insight.context,
            "processed": insight.processed,
            "adaptation_applied": insight.adaptation_applied,
            "is_actionable": True,
            "created_at": insight.created_at or datetime.now(timezone.utc),
        }

        stmt = (
            pg_insert(LearningInsightModel)
            .values(**insight_data)
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "processed": insight_data["processed"],
                    "adaptation_applied": insight_data["adaptation_applied"],
                    "updated_at": datetime.now(timezone.utc),
                },
            )
        )

        await self._session.execute(stmt)
        await self._session.commit()
        return insight.id

    async def get_by_id(self, insight_id: str, tenant_id: str) -> LearningInsight | None:
        """Get insight by ID."""
        result = await self._session.execute(
            select(LearningInsightModel).where(
                LearningInsightModel.id == insight_id, LearningInsightModel.tenant_id == tenant_id
            )
        )
        row = result.scalar_one_or_none()
        return self._to_pydantic(row) if row else None

    async def get_by_conversation(
        self, conversation_id: str, tenant_id: str
    ) -> LearningInsight | None:
        """Get insight by conversation ID."""
        result = await self._session.execute(
            select(LearningInsightModel).where(
                LearningInsightModel.conversation_id == conversation_id,
                LearningInsightModel.tenant_id == tenant_id,
            )
        )
        row = result.scalar_one_or_none()
        return self._to_pydantic(row) if row else None

    async def get_unprocessed(self, tenant_id: str, limit: int = 100) -> list[LearningInsight]:
        """Get unprocessed insights for batch processing."""
        result = await self._session.execute(
            select(LearningInsightModel)
            .where(
                LearningInsightModel.tenant_id == tenant_id,
                LearningInsightModel.processed.is_(False),
            )
            .limit(limit)
        )
        rows = result.scalars().all()
        return [self._to_pydantic(row) for row in rows]

    async def mark_processed(self, insight_id: str, tenant_id: str) -> bool:
        """Mark insight as processed."""
        if not get_feature_flag("learning_enabled"):
            return False

        result = await self._session.execute(
            update(LearningInsightModel)
            .where(
                LearningInsightModel.id == insight_id, LearningInsightModel.tenant_id == tenant_id
            )
            .values(processed=True, updated_at=datetime.now(timezone.utc))
        )
        await self._session.commit()
        return getattr(result, "rowcount", 0) > 0

    def _to_pydantic(self, row: LearningInsightModel) -> LearningInsight:
        """Convert SQLAlchemy to Pydantic."""
        return LearningInsight(
            id=row.id,
            conversation_id=row.conversation_id,
            tenant_id=row.tenant_id,
            rating=FeedbackRating(row.rating) if row.rating else None,
            context=row.context or {},
            comment=row.comment,
            category=row.category,
            confidence=row.confidence,
            created_at=row.created_at,
            processed=row.processed,
            adaptation_applied=row.adaptation_applied,
        )
