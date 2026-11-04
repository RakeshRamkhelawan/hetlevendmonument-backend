"""Alert Manager - Smart Alert Management (Phase 2: Alert Fatigue solution).

Provides deduplication (SHA-256), throttling per severity, and escalation
of CRITICAL alerts to the IncidentService.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import Base


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class GovernanceAlert(Base):
    """Persistent alert storage per tenant."""

    __tablename__ = "governance_alerts"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    agent_name = Column(String(200), nullable=False)
    severity = Column(String(20), nullable=False)
    violation_type = Column(String(100), nullable=False)
    dedup_key = Column(String(64), nullable=False, index=True)
    occurrence_count = Column(Integer, default=1)
    details = Column(JSONB, default=dict)
    acknowledged = Column(Integer, default=0)  # 0=open, 1=ack
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AlertManager:
    """Intelligent alert management per tenant.

    Features:
    - Deduplication via SHA-256 keyed by tenant+agent+violation+date
    - Throttling per severity to prevent alert fatigue
    - CRITICAL alerts escalated to IncidentService
    - Auto-remediation for MISSING_ATTRIBUTION (Art. 52/53)
    - Daily digest for alert fatigue reduction
    """

    THROTTLE: dict[AlertSeverity, timedelta] = {
        AlertSeverity.CRITICAL: timedelta(minutes=5),
        AlertSeverity.HIGH: timedelta(hours=1),
        AlertSeverity.MEDIUM: timedelta(hours=4),
        AlertSeverity.LOW: timedelta(days=1),
    }

    def __init__(
        self,
        db: AsyncSession,
        insight_repo: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        self._db = db
        self._insight_repo = insight_repo

    async def handle_violation(
        self,
        tenant_id: int,
        agent_name: str,
        violation_type: str,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> GovernanceAlert | None:
        """Process violation with dedup + throttle. Returns new alert or None."""
        severity = self._classify_severity(violation_type)
        dedup_key = self._dedup_key(tenant_id, agent_name, violation_type)

        existing = await self._find_existing(tenant_id, dedup_key)
        if existing:
            existing.occurrence_count += 1  # type: ignore[assignment]
            existing.last_seen_at = datetime.now(timezone.utc)  # type: ignore[assignment]
            await self._db.flush()
            return None  # Deduplicated

        last_alert_time = await self._last_alert_time(tenant_id, agent_name, severity)
        if last_alert_time:
            throttle_window = self.THROTTLE.get(severity, timedelta(hours=1))
            # DB returns naive datetime (DateTime column without timezone=True);
            # treat it as UTC for the comparison (.replace does not convert, only attaches).
            last_aware = last_alert_time.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - last_aware < throttle_window:
                return None  # Throttled

        alert = GovernanceAlert(
            tenant_id=tenant_id,
            agent_name=agent_name,
            severity=severity.value,
            violation_type=violation_type,
            dedup_key=dedup_key,
            details=details or {},
        )
        self._db.add(alert)
        await self._db.flush()

        if severity == AlertSeverity.CRITICAL:
            import logging as _log

            try:
                from src.core.governance.models import IncidentReportDB as _IncidentReportDB

                _row = _IncidentReportDB(
                    tenant_id=tenant_id,
                    incident_type="governance_violation",
                    severity="critical",
                    description=f"Agent {agent_name} triggered critical alert: {violation_type}",
                    agent_id=agent_name,
                    agent_name=agent_name,
                    eu_reporting_required=True,
                    resolution_status="reported",
                )
                self._db.add(_row)
                await self._db.flush()
            except Exception as _exc:
                _log.getLogger(__name__).warning(
                    "incident creation failed: %s: %s",
                    type(_exc).__name__,
                    _exc,
                )

        return alert

    @staticmethod
    def _classify_severity(violation_type: str) -> AlertSeverity:
        critical = {"pii_leakage", "cross_tenant_access", "safety_violation"}
        high = {"missing_approval", "high_risk_unauthorized", "art5_blocked"}
        if violation_type in critical:
            return AlertSeverity.CRITICAL
        if violation_type in high:
            return AlertSeverity.HIGH
        return AlertSeverity.MEDIUM

    @staticmethod
    def _dedup_key(tenant_id: int, agent_name: str, violation_type: str) -> str:
        """SHA-256 dedup key scoped to tenant+agent+violation+date."""
        raw = f"{tenant_id}:{agent_name}:{violation_type}:{datetime.now(timezone.utc).date()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:64]

    async def _find_existing(self, tenant_id: int, dedup_key: str) -> GovernanceAlert | None:
        stmt = (
            select(GovernanceAlert)
            .where(GovernanceAlert.tenant_id == tenant_id)
            .where(GovernanceAlert.dedup_key == dedup_key)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _last_alert_time(
        self,
        tenant_id: int,
        agent_name: str,
        severity: AlertSeverity,
    ) -> datetime | None:
        stmt = (
            select(func.max(GovernanceAlert.created_at))
            .where(GovernanceAlert.tenant_id == tenant_id)
            .where(GovernanceAlert.agent_name == agent_name)
            .where(GovernanceAlert.severity == severity.value)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def auto_remediate(
        self,
        tenant_id: int,
        agent_name: str,
        violation_type: str,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Art. 52/53: Auto-remediate known violation types.

        Currently handles:
        - missing_attribution -> creates AttributionLabel and records insight

        Returns the remedy object, or None if no strategy exists.
        """
        if violation_type != "missing_attribution":
            return None

        from src.core.governance.attribution import AttributionLabel

        d = details or {}
        label = AttributionLabel(
            provider=d.get("provider", ""),
            model=d.get("model", ""),
            model_version=d.get("model_version", ""),
        )

        if self._insight_repo:
            from src.core.learning.loop import LearningInsight

            insight = LearningInsight(
                tenant_id=tenant_id,
                source_agent=agent_name,
                category="auto_remediation",
                finding=f"Auto-remediated missing_attribution for {agent_name}",
                context={
                    "violation_type": violation_type,
                    "provider": d.get("provider"),
                },
                confidence=1.0,
                processed=False,
            )
            await self._insight_repo.save(insight)

        return label

    async def generate_daily_digest(
        self, tenant_id: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Aggregate open alerts for a tenant for today (alert fatigue reduction).

        Returns a digest dict with:
          tenant_id, date, total_alerts, by_severity
        """
        from collections import defaultdict

        today_start = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time())

        stmt = (
            select(GovernanceAlert)
            .where(GovernanceAlert.tenant_id == tenant_id)
            .where(GovernanceAlert.acknowledged == 0)
            .where(GovernanceAlert.created_at >= today_start)
        )
        result = await self._db.execute(stmt)
        alerts = result.scalars().all()

        by_severity: dict[str, int] = defaultdict(int)
        for alert in alerts:
            by_severity[str(alert.severity)] += 1

        return {
            "tenant_id": tenant_id,
            "date": datetime.now(timezone.utc).date().isoformat(),
            "total_alerts": len(alerts),
            "by_severity": dict(by_severity),
        }
