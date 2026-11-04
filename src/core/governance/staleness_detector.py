"""
Staleness Detector - Slice 7

Detects inactive procedures and sends compliance alerts.
Helps organizations maintain clean procedure inventory per GDPR/ISO requirements.

Sprint 4 - S4.7: Compliance alerts for unused procedures
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class StalenessDetector:
    """Detects and reports on stale/inactive procedures."""

    def __init__(self, db_session: AsyncSession, webhook_service: Any = None) -> None:
        """Initialize staleness detector.

        Args:
            db_session: Async database session
            webhook_service: Optional webhook service for compliance alerts
        """
        self.db_session = db_session
        self.webhook_service = webhook_service

    async def detect_inactive_procedures(
        self, tenant_id: int, threshold_days: int = 90
    ) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Detect procedures inactive for threshold_days.

        Args:
            tenant_id: Tenant to scan
            threshold_days: Days of inactivity threshold (default: 90)

        Returns: List[Any] of inactive procedure metadata objects  # TODO(TYPE): replace Any with concrete type
        """
        # Import here to avoid circular dependency
        from src.core.procedures.models import ProcedureExecution, ProcedureMetadata

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=threshold_days)

        # Query procedures by checking their last execution time
        # Find all procedure_metadata that have NO executions OR last execution > cutoff_date
        stmt = select(ProcedureMetadata).where(ProcedureMetadata.tenant_id == tenant_id)

        result = await self.db_session.execute(stmt)
        all_procedures = result.scalars().all()

        inactive_procedures: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for proc in all_procedures:
            # Get last execution for this procedure
            exec_stmt = (
                select(ProcedureExecution)
                .where(ProcedureExecution.procedure_id == proc.id)
                .order_by(ProcedureExecution.created_at.desc())
                .limit(1)
            )
            exec_result = await self.db_session.execute(exec_stmt)
            last_execution = exec_result.scalar_one_or_none()

            # Check if inactive
            if last_execution is None:
                # Never executed - treat as inactive
                proc.last_used = None
                inactive_procedures.append(proc)
            elif last_execution.created_at < cutoff_date:
                # Last execution too old
                proc.last_used = last_execution.created_at
                inactive_procedures.append(proc)

        return inactive_procedures

    async def scan_tenant(self, tenant_id: int, threshold_days: int = 90) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Scan tenant for inactive procedures and generate report.

        Args:
            tenant_id: Tenant to scan
            threshold_days: Days of inactivity threshold

        Returns:
            Scan report with metadata and inactive procedures
        """
        from src.core.procedures.models import ProcedureMetadata

        # Get all procedures for tenant
        stmt = select(ProcedureMetadata).where(ProcedureMetadata.tenant_id == tenant_id)
        result = await self.db_session.execute(stmt)
        all_procedures = result.scalars().all()

        # Detect inactive
        inactive = await self.detect_inactive_procedures(
            tenant_id=tenant_id, threshold_days=threshold_days
        )

        # Build report
        report = {
            "tenant_id": tenant_id,
            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
            "threshold_days": threshold_days,
            "total_procedures": len(all_procedures),
            "inactive_count": len(inactive),
            "inactive_procedures": [
                {
                    "id": str(proc.id),
                    "category": proc.category,
                    "last_used": (
                        proc.last_used.isoformat()
                        if hasattr(proc, "last_used") and proc.last_used
                        else None
                    ),
                }
                for proc in inactive
            ],
        }

        # Send compliance alert if any inactive found
        if inactive and self.webhook_service:
            await self.webhook_service.send_compliance_alert(
                alert_type="staleness",
                tenant_id=tenant_id,
                inactive_procedures=report["inactive_procedures"],
                threshold_days=threshold_days,
            )

        return report
