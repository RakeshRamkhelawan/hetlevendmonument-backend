"""
Repository for StrategyEngine persistence.

Handles CRUD for strategic_objectives, strategic_insights, and strategies.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.agents.strategy_engine import (
    StrategicInsight,
    StrategicObjective,
    StrategicPriority,
    StrategyType,
)
from src.core.agents.strategy_models import (
    StrategicInsightModel,
    StrategicObjectiveModel,
    StrategyModel,
)

logger = logging.getLogger(__name__)


class StrategyRepository:
    """Persistence layer for the StrategyEngine's strategic knowledge."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Objectives  (-> strategic_objectives table)
    # ------------------------------------------------------------------

    async def save_objective(self, tenant_id: int, obj: StrategicObjective) -> None:
        """Upsert a StrategicObjective."""
        data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "tenant_id": tenant_id,
            "objective_id": obj.id,
            "title": obj.title,
            "description": obj.description,
            "priority": (
                obj.priority.value
                if isinstance(obj.priority, StrategicPriority)
                else int(obj.priority)
                if str(obj.priority).isdigit()
                else 5
            ),
            "status": obj.status,
            "progress": obj.progress,
            "success_criteria": obj.success_metrics,
            "key_results": {
                "dependencies": obj.dependencies,
                "stakeholders": obj.stakeholders,
                "target_date": obj.target_date.isoformat() if obj.target_date else None,
            },
            "updated_at": datetime.now(timezone.utc),
        }
        async with self._session_factory() as session:
            stmt = pg_insert(StrategicObjectiveModel).values(**data)
            stmt = stmt.on_conflict_do_update(
                index_elements=["objective_id"],
                set_={
                    "title": data["title"],
                    "description": data["description"],
                    "priority": data["priority"],
                    "status": data["status"],
                    "progress": data["progress"],
                    "success_criteria": data["success_criteria"],
                    "key_results": data["key_results"],
                    "updated_at": data["updated_at"],
                },
            )
            await session.execute(stmt)
            await session.commit()
            logger.debug("Saved objective %s for tenant %d", obj.id, tenant_id)

    async def get_active_objectives(self, tenant_id: int) -> list[StrategicObjective]:
        """Load all active objectives for a tenant."""
        async with self._session_factory() as session:
            stmt = (
                select(StrategicObjectiveModel)
                .where(
                    StrategicObjectiveModel.tenant_id == tenant_id,
                    StrategicObjectiveModel.status == "active",
                )
                .order_by(StrategicObjectiveModel.priority.asc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        objectives: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for r in rows:
            key_results = r.key_results or {}
            target_date_str = key_results.get("target_date")
            target_date = (
                datetime.fromisoformat(target_date_str)
                if target_date_str
                else datetime.now(timezone.utc)
            )
            # Map integer priority back to enum
            priority_map = {
                1: StrategicPriority.CRITICAL,
                2: StrategicPriority.HIGH,
                3: StrategicPriority.MEDIUM,
                4: StrategicPriority.LOW,
                5: StrategicPriority.EXPLORATORY,
            }
            priority = priority_map.get(r.priority, StrategicPriority.MEDIUM)
            objectives.append(
                StrategicObjective(
                    id=r.objective_id,
                    title=r.title,
                    description=r.description or "",
                    priority=priority,
                    target_date=target_date,
                    success_metrics=r.success_criteria or [],
                    dependencies=key_results.get("dependencies", []),
                    progress=r.progress,
                    status=r.status,
                    stakeholders=key_results.get("stakeholders", []),
                )
            )
        return objectives

    # ------------------------------------------------------------------
    # Insights  (-> strategic_insights table)
    # ------------------------------------------------------------------

    async def save_insight(self, tenant_id: int, insight: StrategicInsight) -> None:
        """Upsert a StrategicInsight."""
        data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "tenant_id": tenant_id,
            "insight_id": insight.id,
            "strategy_type": (
                insight.type.value if isinstance(insight.type, StrategyType) else str(insight.type)
            ),
            "title": insight.title,
            "description": insight.description,
            "confidence": insight.confidence,
            "impact_score": insight.impact_score,
            "urgency_score": insight.urgency_score,
            "supporting_evidence": insight.supporting_evidence,
            "recommended_actions": insight.recommended_actions,
            "risks": insight.risks,
            "opportunities": insight.opportunities,
            "updated_at": datetime.now(timezone.utc),
        }
        async with self._session_factory() as session:
            stmt = pg_insert(StrategicInsightModel).values(**data)
            stmt = stmt.on_conflict_do_update(
                index_elements=["insight_id"],
                set_={
                    "confidence": data["confidence"],
                    "impact_score": data["impact_score"],
                    "urgency_score": data["urgency_score"],
                    "supporting_evidence": data["supporting_evidence"],
                    "recommended_actions": data["recommended_actions"],
                    "risks": data["risks"],
                    "opportunities": data["opportunities"],
                    "updated_at": data["updated_at"],
                },
            )
            await session.execute(stmt)
            await session.commit()
            logger.debug("Saved insight %s for tenant %d", insight.id, tenant_id)

    async def get_insights(
        self,
        tenant_id: int,
        strategy_type: str | None = None,
        limit: int = 50,
    ) -> list[StrategicInsight]:
        """Load insights for a tenant."""
        async with self._session_factory() as session:
            stmt = (
                select(StrategicInsightModel)
                .where(StrategicInsightModel.tenant_id == tenant_id)
                .order_by(StrategicInsightModel.impact_score.desc())
                .limit(limit)
            )
            if strategy_type:
                stmt = stmt.where(StrategicInsightModel.strategy_type == strategy_type)
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [
            StrategicInsight(
                id=r.insight_id,
                type=(
                    StrategyType(r.strategy_type)
                    if r.strategy_type in {t.value for t in StrategyType}
                    else StrategyType.BUSINESS_DEVELOPMENT
                ),
                title=r.title,
                description=r.description,
                confidence=r.confidence,
                impact_score=r.impact_score,
                urgency_score=r.urgency_score,
                supporting_evidence=r.supporting_evidence or [],
                recommended_actions=r.recommended_actions or [],
                risks=r.risks or [],
                opportunities=r.opportunities or [],
                created_at=r.created_at,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Strategies  (-> strategies table)
    # ------------------------------------------------------------------

    async def save_strategy(self, tenant_id: int, strategy: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Upsert a strategy result dict."""
        strategy_id = strategy.get("id", "")
        data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "tenant_id": tenant_id,
            "strategy_id": strategy_id,
            "strategy_type": strategy.get("type", "unknown"),
            "status": strategy.get("status", "draft"),
            "analysis": strategy.get("analysis"),
            "recommendations": strategy.get("recommendations"),
            "implementation_plan": strategy.get("implementation_plan"),
            "success_metrics": strategy.get("success_metrics"),
            "confidence_score": strategy.get("confidence_score", 0.0),
            "context_data": strategy.get("context_data"),
            "updated_at": datetime.now(timezone.utc),
        }
        async with self._session_factory() as session:
            stmt = pg_insert(StrategyModel).values(**data)
            stmt = stmt.on_conflict_do_update(
                index_elements=["strategy_id"],
                set_={
                    "status": data["status"],
                    "analysis": data["analysis"],
                    "recommendations": data["recommendations"],
                    "implementation_plan": data["implementation_plan"],
                    "success_metrics": data["success_metrics"],
                    "confidence_score": data["confidence_score"],
                    "context_data": data["context_data"],
                    "updated_at": data["updated_at"],
                },
            )
            await session.execute(stmt)
            await session.commit()
            logger.debug("Saved strategy %s for tenant %d", strategy_id, tenant_id)

    async def get_strategies(
        self,
        tenant_id: int,
        strategy_type: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Load strategies for a tenant."""
        async with self._session_factory() as session:
            stmt = (
                select(StrategyModel)
                .where(StrategyModel.tenant_id == tenant_id)
                .order_by(StrategyModel.created_at.desc())
            )
            if strategy_type:
                stmt = stmt.where(StrategyModel.strategy_type == strategy_type)
            if status:
                stmt = stmt.where(StrategyModel.status == status)
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [
            {
                "id": r.strategy_id,
                "type": r.strategy_type,
                "status": r.status,
                "analysis": r.analysis,
                "recommendations": r.recommendations,
                "implementation_plan": r.implementation_plan,
                "success_metrics": r.success_metrics,
                "confidence_score": r.confidence_score,
                "context_data": r.context_data,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]


__all__ = ["StrategyRepository"]
