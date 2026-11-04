from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.models import AuditLog
from src.core.learning.models import LearningExperience
from src.core.learning.persistence_models import (
    AdaptationRuleModel,
    LearningInsightModel,
    LearningPatternModel,
)


async def count_observations(
    session: AsyncSession,
    tenant_id: int,
    agent_id: str | None = None,
) -> int:
    stmt = select(func.count(LearningExperience.id)).where(
        LearningExperience.tenant_id == tenant_id
    )
    if agent_id:
        stmt = stmt.where(LearningExperience.agent_id == agent_id)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def count_patterns(session: AsyncSession, tenant_id: int) -> int:
    result = await session.execute(
        select(func.count(LearningPatternModel.id)).where(
            LearningPatternModel.tenant_id == str(tenant_id)
        )
    )
    return int(result.scalar_one())


async def count_adaptations(session: AsyncSession, tenant_id: int) -> int:
    result = await session.execute(
        select(func.count(AdaptationRuleModel.id)).where(
            AdaptationRuleModel.tenant_id == str(tenant_id)
        )
    )
    return int(result.scalar_one())


async def count_insights(session: AsyncSession, tenant_id: int) -> int:
    result = await session.execute(
        select(func.count(LearningInsightModel.id)).where(
            LearningInsightModel.tenant_id == str(tenant_id)
        )
    )
    return int(result.scalar_one())


async def count_audit_entries(session: AsyncSession, tenant_id: int) -> int:
    result = await session.execute(
        select(func.count(AuditLog.id)).where(AuditLog.tenant_id == tenant_id)
    )
    return int(result.scalar_one())


async def count_all_learning_records(session: AsyncSession, tenant_id: int) -> dict[str, int]:
    return {
        "observations": await count_observations(session, tenant_id),
        "patterns": await count_patterns(session, tenant_id),
        "adaptations": await count_adaptations(session, tenant_id),
        "insights": await count_insights(session, tenant_id),
        "audit_entries": await count_audit_entries(session, tenant_id),
    }


def total_learning_records(counts: dict[str, Any]) -> int:
    return int(
        counts["observations"] + counts["patterns"] + counts["adaptations"] + counts["insights"]
    )
