"""
Repository for LearningLoop persistence.

Handles CRUD for learning_experiences (observations), learning_patterns,
adaptation_rules, and learning_insights.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.agents.learning_loop import (
    AdaptationRule,
    LearningInsight,
    LearningObservation,
    LearningPattern,
    LearningSource,
    LearningType,
)
from src.core.learning.models import LearningExperience
from src.core.learning.persistence_models import (
    AdaptationRuleModel,
    LearningInsightModel,
    LearningPatternModel,
)
from src.core.shared.config import get_feature_flag

logger = logging.getLogger(__name__)


class LearningRepository:
    """Persistence layer for the LearningLoop's learned knowledge."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _string_tenant_id(tenant_id: int) -> str:
        return str(tenant_id)

    # ------------------------------------------------------------------
    # Observations  (-> learning_experiences table)
    # ------------------------------------------------------------------

    async def save_observation(self, tenant_id: int, obs: LearningObservation) -> None:
        """Persist a LearningObservation to the learning_experiences table."""
        if not get_feature_flag("learning_enabled"):
            logger.debug("Skipping observation persistence because learning is disabled")
            return

        async with self._session_factory() as session:
            record = LearningExperience(
                tenant_id=tenant_id,
                event_id=obs.id,
                event_type=obs.learning_type.value,
                agent_id=obs.context.get("agent") or obs.context.get("agent_id"),
                task_type=obs.context.get("task_type"),
                success=obs.outcome_metrics.get("success_rate", 0) >= 0.5,
                duration=obs.outcome_metrics.get("execution_time"),
                context=obs.observation_data,
                metrics=obs.outcome_metrics,
                confidence=obs.confidence_score,
            )
            session.add(record)
            await session.commit()
            logger.debug("Saved observation %s for tenant %d", obs.id, tenant_id)

    async def get_recent_observations(
        self,
        tenant_id: int,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[LearningObservation]:
        """Load recent observations from the database, tenant-scoped."""
        async with self._session_factory() as session:
            stmt = (
                select(LearningExperience)
                .where(LearningExperience.tenant_id == tenant_id)
                .order_by(LearningExperience.created_at.desc())
                .limit(limit)
            )
            if agent_id:
                stmt = stmt.where(LearningExperience.agent_id == agent_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [
            LearningObservation(
                id=r.event_id,
                timestamp=r.created_at if r.created_at is not None else datetime.now(timezone.utc),
                source=LearningSource.TASK_EXECUTION,
                learning_type=(
                    LearningType(r.event_type)
                    if r.event_type in {t.value for t in LearningType}
                    else LearningType.PERFORMANCE_OPTIMIZATION
                ),
                context=r.context or {},
                observation_data=r.context or {},
                outcome_metrics=r.metrics or {},
                confidence_score=r.confidence or 0.0,
                importance_score=0.0,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Patterns  (-> learning_patterns table)
    # ------------------------------------------------------------------

    async def save_pattern(self, tenant_id: int, pattern: LearningPattern) -> None:
        """Upsert a LearningPattern into learning_patterns."""
        if not get_feature_flag("learning_enabled"):
            logger.debug("Skipping pattern persistence because learning is disabled")
            return

        data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "tenant_id": self._string_tenant_id(tenant_id),
            "pattern_id": pattern.id,
            "pattern_type": (
                pattern.pattern_type.value
                if isinstance(pattern.pattern_type, LearningType)
                else str(pattern.pattern_type)
            ),
            "trigger_conditions": pattern.trigger_conditions,
            "learned_behavior": pattern.learned_behavior,
            "confidence_score": pattern.confidence_score,
            "occurrence_count": pattern.observation_count,
            "success_rate": pattern.success_rate,
            "is_active": True,
            "source": pattern.learned_behavior.get("source"),
            "agent_id": pattern.trigger_conditions.get("agent_id"),
            "updated_at": datetime.now(timezone.utc),
        }
        async with self._session_factory() as session:
            stmt = pg_insert(LearningPatternModel).values(**data)
            stmt = stmt.on_conflict_do_update(
                index_elements=["pattern_id"],
                set_={
                    "trigger_conditions": data["trigger_conditions"],
                    "learned_behavior": data["learned_behavior"],
                    "confidence_score": data["confidence_score"],
                    "occurrence_count": data["occurrence_count"],
                    "success_rate": data["success_rate"],
                    "updated_at": data["updated_at"],
                },
            )
            await session.execute(stmt)
            await session.commit()
            logger.debug("Saved pattern %s for tenant %d", pattern.id, tenant_id)

    async def get_active_patterns(self, tenant_id: int) -> list[LearningPattern]:
        """Load all active patterns for a tenant."""
        async with self._session_factory() as session:
            stmt = (
                select(LearningPatternModel)
                .where(
                    LearningPatternModel.tenant_id == self._string_tenant_id(tenant_id),
                    LearningPatternModel.is_active.is_(True),
                )
                .order_by(LearningPatternModel.confidence_score.desc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [
            LearningPattern(
                id=r.pattern_id,
                pattern_type=(
                    LearningType(r.pattern_type)
                    if r.pattern_type in {t.value for t in LearningType}
                    else LearningType.PATTERN_RECOGNITION
                ),
                description=f"Pattern {r.pattern_id}",
                trigger_conditions=r.trigger_conditions or {},
                learned_behavior=r.learned_behavior or {},
                success_rate=r.success_rate,
                confidence_score=r.confidence_score,
                observation_count=r.occurrence_count,
                last_updated=r.updated_at or r.created_at,
            )
            for r in rows
        ]

    async def update_pattern_stats(
        self,
        pattern_id: str,
        occurrence_count: int,
        success_rate: float,
    ) -> None:
        """Update statistics of a pattern."""
        if not get_feature_flag("learning_enabled"):
            logger.debug("Skipping pattern stats update because learning is disabled")
            return

        async with self._session_factory() as session:
            stmt = (
                update(LearningPatternModel)
                .where(LearningPatternModel.pattern_id == pattern_id)
                .values(
                    occurrence_count=occurrence_count,
                    success_rate=success_rate,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(stmt)
            await session.commit()

    # ------------------------------------------------------------------
    # Adaptation Rules  (-> adaptation_rules table)
    # ------------------------------------------------------------------

    async def save_rule(self, tenant_id: int, rule: AdaptationRule) -> None:
        """Upsert an AdaptationRule into adaptation_rules."""
        if not get_feature_flag("learning_enabled"):
            logger.debug("Skipping rule persistence because learning is disabled")
            return

        data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "id": rule.id,
            "tenant_id": self._string_tenant_id(tenant_id),
            "rule_id": rule.id,
            "source_pattern_id": rule.parameters.get("source_pattern_id")
            or rule.parameters.get("pattern_id"),
            "condition": {"expression": rule.condition, "name": rule.name},
            "action": {"expression": rule.action},
            "parameters": rule.parameters,
            "priority": rule.parameters.get("priority", 0),
            "is_active": rule.active,
            "application_count": rule.trigger_count,
            "success_count": rule.success_count,
            "times_applied": rule.trigger_count,
            "success_rate": (
                float(rule.success_count) / float(rule.trigger_count) if rule.trigger_count else 0.0
            ),
            "updated_at": datetime.now(timezone.utc),
        }
        async with self._session_factory() as session:
            stmt = pg_insert(AdaptationRuleModel).values(**data)
            stmt = stmt.on_conflict_do_update(
                index_elements=["rule_id"],
                set_={
                    "source_pattern_id": data["source_pattern_id"],
                    "condition": data["condition"],
                    "action": data["action"],
                    "parameters": data["parameters"],
                    "is_active": data["is_active"],
                    "application_count": data["application_count"],
                    "success_count": data["success_count"],
                    "times_applied": data["times_applied"],
                    "success_rate": data["success_rate"],
                    "updated_at": data["updated_at"],
                },
            )
            await session.execute(stmt)
            await session.commit()
            logger.debug("Saved rule %s for tenant %d", rule.id, tenant_id)

    async def get_active_rules(self, tenant_id: int) -> list[AdaptationRule]:
        """Load all active adaptation rules for a tenant, ordered by priority."""
        async with self._session_factory() as session:
            stmt = (
                select(AdaptationRuleModel)
                .where(
                    AdaptationRuleModel.tenant_id == self._string_tenant_id(tenant_id),
                    AdaptationRuleModel.is_active.is_(True),
                )
                .order_by(AdaptationRuleModel.priority.desc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [
            AdaptationRule(
                id=r.rule_id,
                name=r.condition.get("name", "") if r.condition else "",
                condition=r.condition.get("expression", "") if r.condition else "",
                action=r.action.get("expression", "") if r.action else "",
                parameters=r.parameters or {},
                success_metrics=[],
                active=r.is_active,
                trigger_count=r.application_count,
                success_count=r.success_count,
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def increment_rule_stats(self, rule_id: str, applied_successfully: bool) -> None:
        """Increment application_count and optionally success_count."""
        if not get_feature_flag("learning_enabled"):
            logger.debug("Skipping rule stats update because learning is disabled")
            return

        async with self._session_factory() as session:
            stmt = (
                update(AdaptationRuleModel)
                .where(AdaptationRuleModel.rule_id == rule_id)
                .values(
                    application_count=AdaptationRuleModel.application_count + 1,
                    times_applied=AdaptationRuleModel.times_applied + 1,
                    success_count=AdaptationRuleModel.success_count
                    + (1 if applied_successfully else 0),
                    success_rate=(
                        (AdaptationRuleModel.success_count + (1 if applied_successfully else 0))
                        / (AdaptationRuleModel.application_count + 1)
                    ),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(stmt)
            await session.commit()

    # ------------------------------------------------------------------
    # Insights  (-> learning_insights table)
    # ------------------------------------------------------------------

    async def save_insight(self, tenant_id: int, insight: LearningInsight) -> None:
        """Persist a LearningInsight."""
        if not get_feature_flag("learning_enabled"):
            logger.debug("Skipping insight persistence because learning is disabled")
            return

        data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "id": insight.id,
            "tenant_id": self._string_tenant_id(tenant_id),
            "insight_id": insight.id,
            "conversation_id": "system",
            "insight_type": (
                insight.learning_type.value
                if isinstance(insight.learning_type, LearningType)
                else str(insight.learning_type)
            ),
            "title": insight.title,
            "description": insight.description,
            "evidence": {"observation_ids": insight.supporting_observations},
            "impact_assessment": insight.impact_assessment,
            "recommended_actions": insight.recommended_actions,
            "confidence": insight.confidence_score,
            "confidence_score": insight.confidence_score,
            "processed": bool(getattr(insight, "processed", False)),
            "adaptation_applied": bool(getattr(insight, "adaptation_applied", False)),
            "is_actionable": True,
            "updated_at": datetime.now(timezone.utc),
        }
        async with self._session_factory() as session:
            stmt = pg_insert(LearningInsightModel).values(**data)
            stmt = stmt.on_conflict_do_update(
                index_elements=["insight_id"],
                set_={
                    "evidence": data["evidence"],
                    "impact_assessment": data["impact_assessment"],
                    "recommended_actions": data["recommended_actions"],
                    "confidence": data["confidence"],
                    "confidence_score": data["confidence_score"],
                    "processed": data["processed"],
                    "adaptation_applied": data["adaptation_applied"],
                    "updated_at": data["updated_at"],
                },
            )
            await session.execute(stmt)
            await session.commit()
            logger.debug("Saved insight %s for tenant %d", insight.id, tenant_id)

    async def get_recent_insights(
        self,
        tenant_id: int,
        insight_type: str | None = None,
        limit: int = 50,
    ) -> list[LearningInsight]:
        """Load recent actionable insights for a tenant."""
        async with self._session_factory() as session:
            stmt = (
                select(LearningInsightModel)
                .where(
                    LearningInsightModel.tenant_id == self._string_tenant_id(tenant_id),
                    LearningInsightModel.is_actionable.is_(True),
                )
                .order_by(LearningInsightModel.created_at.desc())
                .limit(limit)
            )
            if insight_type:
                stmt = stmt.where(LearningInsightModel.insight_type == insight_type)
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [
            LearningInsight(
                id=r.insight_id,
                title=r.title if r.title is not None else "",
                description=r.description if r.description is not None else "",
                learning_type=(
                    LearningType(r.insight_type)
                    if r.insight_type in {t.value for t in LearningType}
                    else LearningType.PATTERN_RECOGNITION
                ),
                supporting_observations=(
                    r.evidence.get("observation_ids", []) if r.evidence else []
                ),
                confidence_score=r.confidence_score or r.confidence,
                impact_assessment=r.impact_assessment or {},
                recommended_actions=r.recommended_actions or [],
                created_at=r.created_at,
            )
            for r in rows
        ]


__all__ = ["LearningRepository"]
