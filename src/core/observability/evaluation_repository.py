"""
EvaluationRepository - Stats aggregation for domain packs
Consolidates data from procedure_executions and aiqualityevents tables
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.procedures.models import (
    DomainPack,
    ProcedureExecution,
    ProcedureMetadata,
)


class EvaluationRepository:
    """
    Repository for aggregating evaluation and execution statistics
    Used by Domain Packs API and Governance Dashboard
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_overall_stats(self, tenant_id: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get overall statistics for all domain packs in a tenant

        Args:
            tenant_id: Tenant identifier

        Returns: Dict[str, Any] with total_packs, active_packs, total_procedures  # TODO(TYPE): replace Any with concrete type
        """
        # Count total packs
        total_packs_stmt = select(func.count(DomainPack.id)).where(
            DomainPack.tenant_id == tenant_id
        )
        total_packs_result = await self.db.execute(total_packs_stmt)
        total_packs = total_packs_result.scalar() or 0

        # Count active packs (exclude deprecated)
        active_packs_stmt = select(func.count(DomainPack.id)).where(
            and_(DomainPack.tenant_id == tenant_id, DomainPack.status == "active")
        )
        active_packs_result = await self.db.execute(active_packs_stmt)
        active_packs = active_packs_result.scalar() or 0

        # Count total procedures
        total_procedures_stmt = select(func.count(ProcedureMetadata.id)).where(
            ProcedureMetadata.tenant_id == tenant_id
        )
        total_procedures_result = await self.db.execute(total_procedures_stmt)
        total_procedures = total_procedures_result.scalar() or 0

        return {
            "total_packs": total_packs,
            "active_packs": active_packs,
            "total_procedures": total_procedures,
        }

    async def get_pack_stats(self, pack_id: UUID, tenant_id: int, days: int = 30) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get statistics for a specific domain pack

        Args:
            pack_id: Domain pack identifier
            tenant_id: Tenant identifier
            days: Number of days to look back (default 30)

        Returns: Dict[str, Any] with procedure_count, executions_30d, failure_rate  # TODO(TYPE): replace Any with concrete type
        """
        # Count procedures in this pack
        procedure_count_stmt = select(func.count(ProcedureMetadata.id)).where(
            and_(
                ProcedureMetadata.domain_pack_id == pack_id,
                ProcedureMetadata.tenant_id == tenant_id,
            )
        )
        procedure_count_result = await self.db.execute(procedure_count_stmt)
        procedure_count = procedure_count_result.scalar() or 0

        # Count executions in last N days
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        executions_stmt = (
            select(func.count(ProcedureExecution.id))
            .where(
                and_(
                    ProcedureExecution.tenant_id == tenant_id,
                    ProcedureExecution.started_at >= cutoff_date,
                )
            )
            .join(
                ProcedureMetadata,
                ProcedureExecution.procedure_id == ProcedureMetadata.id,
            )
            .where(ProcedureMetadata.domain_pack_id == pack_id)
        )
        executions_result = await self.db.execute(executions_stmt)
        executions_count = executions_result.scalar() or 0

        # Count failed executions
        failed_stmt = (
            select(func.count(ProcedureExecution.id))
            .where(
                and_(
                    ProcedureExecution.tenant_id == tenant_id,
                    ProcedureExecution.started_at >= cutoff_date,
                    ProcedureExecution.status.in_(["failed", "error"]),
                )
            )
            .join(
                ProcedureMetadata,
                ProcedureExecution.procedure_id == ProcedureMetadata.id,
            )
            .where(ProcedureMetadata.domain_pack_id == pack_id)
        )
        failed_result = await self.db.execute(failed_stmt)
        failed_count = failed_result.scalar() or 0

        # Calculate failure rate
        failure_rate = (failed_count / executions_count * 100) if executions_count > 0 else 0.0

        return {
            "procedure_count": procedure_count,
            f"executions_{days}d": executions_count,
            "failure_rate": round(failure_rate, 2),
        }

    async def get_pack_health(self, pack_id: UUID, tenant_id: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Assess health status of a domain pack

        Args:
            pack_id: Domain pack identifier
            tenant_id: Tenant identifier

        Returns: Dict[str, Any] with status (healthy/degraded/unhealthy) and violations list  # TODO(TYPE): replace Any with concrete type
        """
        violations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Get failure rate
        stats = await self.get_pack_stats(pack_id, tenant_id, days=30)
        failure_rate = stats["failure_rate"]

        # Check failure rate thresholds
        if failure_rate > 50:
            violations.append(
                {
                    "type": "high_failure_rate",
                    "severity": "critical",
                    "message": f"Failure rate is {failure_rate}% (threshold: 50%)",
                }
            )
        elif failure_rate > 20:
            violations.append(
                {
                    "type": "elevated_failure_rate",
                    "severity": "warning",
                    "message": f"Failure rate is {failure_rate}% (threshold: 20%)",
                }
            )

        # Check if pack has no procedures
        if stats["procedure_count"] == 0:
            violations.append(
                {
                    "type": "no_procedures",
                    "severity": "warning",
                    "message": "Domain pack has no procedures defined",
                }
            )

        # Check if pack has no recent executions (stale)
        if stats["executions_30d"] == 0 and stats["procedure_count"] > 0:
            violations.append(
                {
                    "type": "no_recent_usage",
                    "severity": "info",
                    "message": "No executions in the last 30 days",
                }
            )

        # Determine overall status
        if any(v["severity"] == "critical" for v in violations):
            status = "unhealthy"
        elif any(v["severity"] == "warning" for v in violations):
            status = "degraded"
        else:
            status = "healthy"

        return {"status": status, "violations": violations, "stats": stats}
