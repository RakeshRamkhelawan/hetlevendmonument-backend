"""Repository for batch-inserting digital twin observations."""

from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.learning.batching.batch_manager import PendingObservation
from src.core.learning.twin_models import UserBehaviorObservation


def _to_datetime(timestamp: float) -> datetime:
    """Convert Unix timestamp to timezone-aware datetime."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


async def insert_observation_batch(
    db: AsyncSession,
    observations: list[PendingObservation],
) -> None:
    """Batch INSERT observations into user_behavior_observations.

    Args:
        db: SQLAlchemy async session.
        observations: List of PendingObservation from the batch buffer.
            Each observation already carries tenant_id and a privacy-filtered
            human_user_id.

    Returns:
        None

    Raises:
        Exception: Re-raised so the batch manager retry logic can handle it.
    """
    if not observations:
        return

    values: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
    for obs in observations:
        created_at = _to_datetime(obs.timestamp)
        expires_at = created_at + timedelta(days=90)
        values.append(
            {
                "tenant_id": obs.tenant_id,
                "human_user_id": obs.human_user_id,
                "session_id": obs.session_id,
                "behavior_type": obs.behavior_type,
                "context": obs.context or {},
                "outcome_metrics": obs.outcome_metrics or {},
                "confidence_score": obs.confidence_score,
                "created_at": created_at,
                "expires_at": expires_at,
            }
        )

    await db.execute(insert(UserBehaviorObservation), values)
    await db.flush()

    logger.debug(
        "observation_batch_inserted",
        count=len(observations),
    )
