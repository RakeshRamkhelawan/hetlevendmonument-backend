"""Concrete SQLAlchemy implementation of ILearningExperienceReader.

Lives in agent_runtime layer (src.core.learning) so it can import the ORM model.
Also provides create_drift_detector() factory to wire reader + DriftDetector.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.learning.models import LearningExperience
from src.core.shared.learning_interfaces import LearningExperienceData

if TYPE_CHECKING:
    from src.core.monitoring.drift_detection import DriftDetector


class LearningExperienceRepository:
    """SQLAlchemy-backed reader for learning experience records."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_experiences(
        self,
        start_time: datetime,
        end_time: datetime,
        tenant_id: int | None = None,
        require_success_value: bool = False,
    ) -> list[LearningExperienceData]:
        """Return experiences in [start_time, end_time).

        When require_success_value=True, only records where success is not None
        are returned -- filtered at the database level.
        """
        filters = [
            LearningExperience.created_at >= start_time,
            LearningExperience.created_at < end_time,
        ]
        if tenant_id is not None:
            filters.append(LearningExperience.tenant_id == tenant_id)
        if require_success_value:
            filters.append(LearningExperience.success.isnot(None))

        stmt = (
            select(LearningExperience).where(and_(*filters)).order_by(LearningExperience.created_at)
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        return [
            LearningExperienceData(
                tenant_id=row.tenant_id,
                created_at=row.created_at or datetime.now(timezone.utc),
                success=row.success,
                duration=row.duration,
                confidence=row.confidence if row.confidence is not None else 1.0,
                event_type=row.event_type,
                task_type=row.task_type,
                agent_id=row.agent_id,
            )
            for row in rows
        ]


async def create_drift_detector(
    db_session: AsyncSession,
    tenant_id: int,
    baseline_window_days: int = 30,
) -> "DriftDetector":
    """Wire up LearningExperienceRepository and DriftDetector.

    Lives here (agent_runtime) so drift_detection.py stays import-clean.

    Args:
        db_session: Async session for LearningExperienceRepository
        tenant_id: Tenant to scope all queries to
        baseline_window_days: Days of history used for baseline calculation

    Returns:
        Initialized DriftDetector with established baseline
    """
    from src.core.monitoring.drift_detection import DriftDetector as _DriftDetector

    reader = LearningExperienceRepository(db_session)
    detector = _DriftDetector(reader, tenant_id, baseline_window_days)
    await detector.establish_baseline()
    return detector
