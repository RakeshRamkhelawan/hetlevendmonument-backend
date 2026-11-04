"""Art. 15 Accuracy Monitor.

EU AI Act Compliance - Article 15: Accuracy, robustness, and cybersecurity.
Persistent accuracy tracking per agent per tenant with drift detection.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import Base


class AccuracyMetric(Base):
    """Persistent accuracy tracking per agent per tenant."""

    __tablename__ = "governance_accuracy_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    agent_name = Column(String(200), nullable=False, index=True)
    success = Column(Integer, nullable=False)  # 1 = success, 0 = failure
    confidence_score = Column(Float, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    recorded_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )


class AccuracyMonitor:
    """Art. 15: Monitors agent accuracy per tenant.

    Baselines stored in PostgreSQL (not in-memory).
    Detects accuracy drift and emits actionable recommendations.
    """

    DRIFT_THRESHOLD = 0.10  # 10% drop triggers an alert
    BASELINE_WINDOW_DAYS = 30
    RECENT_WINDOW_DAYS = 7
    MIN_SAMPLES = 20

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def track_result(
        self,
        tenant_id: int,
        agent_name: str,
        success: bool,
        confidence_score: float | None = None,
        execution_time_ms: int | None = None,
    ) -> None:
        """Store an execution result for later drift analysis."""
        metric = AccuracyMetric(
            tenant_id=tenant_id,
            agent_name=agent_name,
            success=1 if success else 0,
            confidence_score=confidence_score,
            execution_time_ms=execution_time_ms,
        )
        self._db.add(metric)
        await self._db.flush()

    async def check_drift(
        self,
        tenant_id: int,
        agent_name: str,
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Check accuracy drift. Returns alert dict or None if no drift."""
        now = datetime.now(timezone.utc)

        baseline_accuracy = await self._get_accuracy(
            tenant_id,
            agent_name,
            since=now - timedelta(days=self.BASELINE_WINDOW_DAYS),
            until=now - timedelta(days=self.RECENT_WINDOW_DAYS),
        )
        recent_accuracy = await self._get_accuracy(
            tenant_id,
            agent_name,
            since=now - timedelta(days=self.RECENT_WINDOW_DAYS),
            until=now,
        )

        if baseline_accuracy is None or recent_accuracy is None:
            return None  # Insufficient data

        drop = baseline_accuracy - recent_accuracy
        if drop > self.DRIFT_THRESHOLD:
            return {
                "agent_name": agent_name,
                "tenant_id": tenant_id,
                "baseline": round(baseline_accuracy, 4),
                "current": round(recent_accuracy, 4),
                "drop_pct": round(drop * 100, 2),
                "recommendation": self._recommendation(recent_accuracy),
            }
        return None

    async def _get_accuracy(
        self,
        tenant_id: int,
        agent_name: str,
        since: datetime,
        until: datetime,
    ) -> float | None:
        stmt = (
            select(
                func.count().label("total"),
                func.sum(AccuracyMetric.success).label("successes"),
            )
            .where(AccuracyMetric.tenant_id == tenant_id)
            .where(AccuracyMetric.agent_name == agent_name)
            .where(AccuracyMetric.recorded_at >= since)
            .where(AccuracyMetric.recorded_at < until)
        )
        result = await self._db.execute(stmt)
        row = result.one()
        if row.total < self.MIN_SAMPLES:
            return None
        return row.successes / row.total

    @staticmethod
    def _recommendation(accuracy: float) -> str:
        if accuracy < 0.70:
            return "CRITICAL: Immediate retraining. Quarantine agent."
        if accuracy < 0.80:
            return "HIGH: Schedule retraining within 48 hours."
        return "MEDIUM: Monitor closely, plan retraining."
