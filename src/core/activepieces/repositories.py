"""
ActivePieces Repository Layer

Handles all database operations for ActivePieces entities:
- Flows
- Connections
- Flow Runs
- Sync Logs
"""

from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.activepieces.models import (
    ActivePiecesConnection,
    ActivePiecesFlow,
    ActivePiecesFlowRun,
    ActivePiecesSyncLog,
)


class ActivePiecesFlowRepository:
    """Repository for ActivePieces flow database operations"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        tenant_id: int,
        ap_flow_id: str,
        project_id: str,
        name: str,
        description: str | None = None,
        status: str = "DISABLED",
        flow_definition: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> ActivePiecesFlow:
        """Create a new flow record"""
        flow = ActivePiecesFlow(
            tenant_id=tenant_id,
            ap_flow_id=ap_flow_id,
            project_id=project_id,
            name=name,
            description=description,
            status=status,
            flow_definition=flow_definition or {},
        )
        self.db.add(flow)
        await self.db.flush()
        await self.db.refresh(flow)
        return flow

    async def get_by_id(self, tenant_id: int, flow_id: UUID) -> ActivePiecesFlow | None:
        """Get flow by ID with tenant filtering"""
        stmt = select(ActivePiecesFlow).where(
            and_(
                ActivePiecesFlow.id == flow_id,
                ActivePiecesFlow.tenant_id == tenant_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_ap_flow_id(
        self, tenant_id: int, ap_flow_id: str
    ) -> ActivePiecesFlow | None:
        """Get flow by ActivePieces flow ID"""
        stmt = select(ActivePiecesFlow).where(
            and_(
                ActivePiecesFlow.ap_flow_id == ap_flow_id,
                ActivePiecesFlow.tenant_id == tenant_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_ap_flow_reference(
        self, ap_flow_id: str, project_id: str
    ) -> ActivePiecesFlow | None:
        """Get flow by its ActivePieces identifiers without trusting caller tenant context."""
        stmt = select(ActivePiecesFlow).where(
            and_(
                ActivePiecesFlow.ap_flow_id == ap_flow_id,
                ActivePiecesFlow.project_id == project_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: int,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActivePiecesFlow]:
        """List all flows for a tenant"""
        stmt = select(ActivePiecesFlow).where(ActivePiecesFlow.tenant_id == tenant_id)

        if status:
            stmt = stmt.where(ActivePiecesFlow.status == status)

        stmt = stmt.order_by(desc(ActivePiecesFlow.created_at)).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        tenant_id: int,
        flow_id: UUID,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        flow_definition: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> ActivePiecesFlow | None:
        """Update a flow"""
        flow = await self.get_by_id(tenant_id, flow_id)
        if not flow:
            return None

        if name is not None:
            flow.name = name
        if description is not None:
            flow.description = description
        if status is not None:
            flow.status = status
        if flow_definition is not None:
            flow.flow_definition = flow_definition

        flow.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(flow)
        return flow

    async def delete(self, tenant_id: int, flow_id: UUID) -> bool:
        """Delete a flow"""
        flow = await self.get_by_id(tenant_id, flow_id)
        if not flow:
            return False

        await self.db.delete(flow)
        await self.db.flush()
        return True

    async def count_by_tenant(self, tenant_id: int) -> int:
        """Count flows for a tenant"""
        stmt = (
            select(func.count())
            .select_from(ActivePiecesFlow)
            .where(ActivePiecesFlow.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one())


class ActivePiecesConnectionRepository:
    """Repository for ActivePieces connection database operations"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        tenant_id: int,
        ap_connection_id: str,
        project_id: str,
        app_name: str,
        name: str,
        status: str = "ACTIVE",
        encrypted_credentials: str | None = None,
    ) -> ActivePiecesConnection:
        """Create a new connection record"""
        conn = ActivePiecesConnection(
            tenant_id=tenant_id,
            ap_connection_id=ap_connection_id,
            project_id=project_id,
            app_name=app_name,
            name=name,
            status=status,
            encrypted_credentials=encrypted_credentials,
        )
        self.db.add(conn)
        await self.db.flush()
        await self.db.refresh(conn)
        return conn

    async def get_by_id(
        self, tenant_id: int, connection_id: UUID
    ) -> ActivePiecesConnection | None:
        """Get connection by ID with tenant filtering"""
        stmt = select(ActivePiecesConnection).where(
            and_(
                ActivePiecesConnection.id == connection_id,
                ActivePiecesConnection.tenant_id == tenant_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_ap_connection_id(
        self, tenant_id: int, ap_connection_id: str
    ) -> ActivePiecesConnection | None:
        """Get connection by ActivePieces connection ID"""
        stmt = select(ActivePiecesConnection).where(
            and_(
                ActivePiecesConnection.ap_connection_id == ap_connection_id,
                ActivePiecesConnection.tenant_id == tenant_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_ap_connection_reference(
        self, ap_connection_id: str, project_id: str
    ) -> ActivePiecesConnection | None:
        """Get connection by its ActivePieces identifiers without trusting caller tenant context."""
        stmt = select(ActivePiecesConnection).where(
            and_(
                ActivePiecesConnection.ap_connection_id == ap_connection_id,
                ActivePiecesConnection.project_id == project_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: int,
        app_name: str | None = None,
        status: str | None = None,
    ) -> list[ActivePiecesConnection]:
        """List all connections for a tenant"""
        stmt = select(ActivePiecesConnection).where(ActivePiecesConnection.tenant_id == tenant_id)

        if app_name:
            stmt = stmt.where(ActivePiecesConnection.app_name == app_name)
        if status:
            stmt = stmt.where(ActivePiecesConnection.status == status)

        stmt = stmt.order_by(desc(ActivePiecesConnection.created_at))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        tenant_id: int,
        connection_id: UUID,
        name: str | None = None,
        status: str | None = None,
        encrypted_credentials: str | None = None,
    ) -> ActivePiecesConnection | None:
        """Update a connection"""
        conn = await self.get_by_id(tenant_id, connection_id)
        if not conn:
            return None

        if name is not None:
            conn.name = name
        if status is not None:
            conn.status = status
        if encrypted_credentials is not None:
            conn.encrypted_credentials = encrypted_credentials

        conn.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(conn)
        return conn

    async def delete(self, tenant_id: int, connection_id: UUID) -> bool:
        """Delete a connection"""
        conn = await self.get_by_id(tenant_id, connection_id)
        if not conn:
            return False

        await self.db.delete(conn)
        await self.db.flush()
        return True

    async def update_last_used(self, tenant_id: int, connection_id: UUID) -> bool:
        """Update last_used timestamp"""
        conn = await self.get_by_id(tenant_id, connection_id)
        if not conn:
            return False

        conn.last_used_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True


class ActivePiecesFlowRunRepository:
    """Repository for ActivePieces flow run database operations"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        tenant_id: int,
        flow_id: UUID,
        ap_run_id: str,
        project_id: str,
        status: str = "RUNNING",
        payload: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> ActivePiecesFlowRun:
        """Create a new flow run record"""
        run = ActivePiecesFlowRun(
            tenant_id=tenant_id,
            flow_id=flow_id,
            ap_run_id=ap_run_id,
            project_id=project_id,
            status=status,
            payload=payload or {},
        )
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def get_by_id(self, tenant_id: int, run_id: UUID) -> ActivePiecesFlowRun | None:
        """Get run by ID with tenant filtering"""
        stmt = select(ActivePiecesFlowRun).where(
            and_(
                ActivePiecesFlowRun.id == run_id,
                ActivePiecesFlowRun.tenant_id == tenant_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_ap_run_id(
        self, tenant_id: int, ap_run_id: str
    ) -> ActivePiecesFlowRun | None:
        """Get run by ActivePieces run ID"""
        stmt = select(ActivePiecesFlowRun).where(
            and_(
                ActivePiecesFlowRun.ap_run_id == ap_run_id,
                ActivePiecesFlowRun.tenant_id == tenant_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_flow(
        self,
        tenant_id: int,
        flow_id: UUID,
        limit: int = 10,
    ) -> list[ActivePiecesFlowRun]:
        """List runs for a specific flow"""
        stmt = (
            select(ActivePiecesFlowRun)
            .where(
                and_(
                    ActivePiecesFlowRun.flow_id == flow_id,
                    ActivePiecesFlowRun.tenant_id == tenant_id,
                )
            )
            .order_by(desc(ActivePiecesFlowRun.created_at))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_tenant(
        self,
        tenant_id: int,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ActivePiecesFlowRun]:
        """List all runs for a tenant"""
        stmt = select(ActivePiecesFlowRun).where(ActivePiecesFlowRun.tenant_id == tenant_id)

        if status:
            stmt = stmt.where(ActivePiecesFlowRun.status == status)

        stmt = stmt.order_by(desc(ActivePiecesFlowRun.created_at)).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        tenant_id: int,
        run_id: UUID,
        status: str,
        error_message: str | None = None,
        duration_ms: int | None = None,
        output: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> ActivePiecesFlowRun | None:
        """Update run status"""
        run = await self.get_by_id(tenant_id, run_id)
        if not run:
            return None

        run.status = status
        if error_message is not None:
            run.error_message = error_message
        if duration_ms is not None:
            run.duration_ms = duration_ms
        if output is not None:
            run.output = output

        run.completed_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def get_run_stats(self, tenant_id: int, flow_id: UUID | None = None) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get run statistics"""
        total_col = func.count().label("total")
        succeeded_col = func.count(case((ActivePiecesFlowRun.status == "SUCCEEDED", 1))).label(
            "succeeded"
        )
        failed_col = func.count(case((ActivePiecesFlowRun.status == "FAILED", 1))).label("failed")
        running_col = func.count(case((ActivePiecesFlowRun.status == "RUNNING", 1))).label(
            "running"
        )

        stmt = select(total_col, succeeded_col, failed_col, running_col).where(
            ActivePiecesFlowRun.tenant_id == tenant_id
        )

        if flow_id:
            stmt = stmt.where(ActivePiecesFlowRun.flow_id == flow_id)

        result = await self.db.execute(stmt)
        row = result.one()

        total = row.total
        return {
            "total": total,
            "succeeded": row.succeeded,
            "failed": row.failed,
            "running": row.running,
            "success_rate": (row.succeeded / total * 100) if total > 0 else 0,
        }


class ActivePiecesSyncLogRepository:
    """Repository for ActivePieces sync log operations"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        tenant_id: int,
        sync_type: str,  # 'pieces', 'flows', 'connections'
        status: str,  # 'success', 'partial', 'failed'
        items_synced: int = 0,
        items_failed: int = 0,
        error_message: str | None = None,
    ) -> ActivePiecesSyncLog:
        """Create a sync log entry"""
        log = ActivePiecesSyncLog(
            tenant_id=tenant_id,
            sync_type=sync_type,
            status=status,
            items_synced=items_synced,
            items_failed=items_failed,
            error_message=error_message,
        )
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return log

    async def list_by_tenant(self, tenant_id: int, limit: int = 10) -> list[ActivePiecesSyncLog]:
        """List sync logs for a tenant"""
        stmt = (
            select(ActivePiecesSyncLog)
            .where(ActivePiecesSyncLog.tenant_id == tenant_id)
            .order_by(desc(ActivePiecesSyncLog.created_at))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
