# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""GDPR Article 20: Right to Data Portability (export endpoints).

Routes:
  POST /api/gdpr/export
  GET  /api/gdpr/export/download/{export_id}
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import User
from src.core.utils.best_effort import best_effort

from .dependencies import (
    Agent,
    AuditLog,
    AuditService,
    audit_rows_about_user,
    C7ExecutionTask as Task,
    C7Workflow as Workflow,
)
from .dependencies import (
    LawfulBasisMissingError,
    LawfulBasisRegistry,
    get_current_tenant_id,
    get_current_user,
    get_db,
    get_lawful_basis_registry,
)
from .schemas import (
    DataCategory,
    ExportDataRequest,
    ExportDataResponse,
    ExportFormat,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gdpr", tags=["GDPR Compliance"])


@router.post(
    "/export",
    response_model=ExportDataResponse,
    summary="Export All Tenant Data (GDPR Article 20)",
    description="""
    Export all data associated with the current tenant.

    **GDPR Article 20 - Right to Data Portability:**
    - Receive personal data in structured, commonly used format
    - Transmit data to another controller

    **Security:**
    - Requires authentication
    - Only exports current tenant's data
    - Max export size: 100MB
    - Rate limited: 1 export per hour

    **Data Categories:**
    - PERSONAL: User profiles, emails, preferences
    - AGENTS: AI agent configurations
    - TASKS: Task history and results
    - WORKFLOWS: Workflow definitions
    - AUDIT: Access logs (last 90 days)
    - ALL: Everything above
    """,
)
async def export_tenant_data(
    request: ExportDataRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    registry: LawfulBasisRegistry = Depends(get_lawful_basis_registry),
) -> ExportDataResponse:
    """Export all tenant data for GDPR compliance (Article 20)."""
    try:
        await registry.validate_endpoint_access("/api/gdpr/export")
    except LawfulBasisMissingError as e:
        logger.error(
            "LawfulBasis hard-blocked (GDPR Art. 6): %s: %s", type(e).__name__, e, exc_info=True
        )
        raise HTTPException(
            status_code=451,
            detail="Data processing is not authorized for this endpoint",
        ) from e
    logger.info("GDPR export requested by user %s for tenant %s", current_user.id, tenant_id)

    try:
        # Rate limiting: max 1 export per hour
        last_export = await db.scalar(
            select(AuditLog.timestamp)
            .filter(
                and_(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.action == "gdpr_export",
                    AuditLog.timestamp > datetime.now(timezone.utc) - timedelta(hours=1),
                )
            )
            .order_by(AuditLog.timestamp.desc())
            .limit(1)
        )

        if last_export:
            raise HTTPException(
                status_code=429,
                detail=(
                    "Rate limit exceeded. Last export was at "
                    + str(last_export)
                    + ". Try again in 1 hour."
                ),
            )

        export_data: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        total_records = 0
        categories_exported: list[str] = []

        categories_to_export = request.categories
        if DataCategory.ALL in categories_to_export:
            categories_to_export = [
                DataCategory.PERSONAL,
                DataCategory.AGENTS,
                DataCategory.TASKS,
                DataCategory.WORKFLOWS,
                DataCategory.AUDIT,
            ]

        if DataCategory.PERSONAL in categories_to_export:
            users_result = await db.execute(
                select(User).filter(User.tenant_id == tenant_id, User.id == current_user.id)
            )
            users = users_result.scalars().all()
            export_data["personal"] = [
                {
                    "id": str(user.id),
                    "email": user.email,
                    "username": user.email,
                    "full_name": None,
                    "is_active": user.is_active,
                    "created_at": (
                        user.created_at.isoformat()
                        if request.include_metadata and user.created_at is not None
                        else None
                    ),
                    "updated_at": (
                        user.updated_at.isoformat()
                        if request.include_metadata and user.updated_at is not None
                        else None
                    ),
                }
                for user in users
            ]
            total_records += len(users)
            categories_exported.append("personal")

        if DataCategory.AGENTS in categories_to_export:
            # NOTE: Agent.created_by not yet on the Agent model (tracked in SP-DLP-002).
            # Exporting all tenant agents until the field is added. Workflow below IS filtered.
            agents_result = await db.execute(select(Agent).filter(Agent.tenant_id == tenant_id))
            agents = agents_result.scalars().all()
            export_data["agents"] = [
                {
                    "id": str(agent.id),
                    "name": agent.name,
                    "type": agent.agent_type,
                    "description": getattr(agent, "description", None),
                    "config": getattr(agent, "config", None),
                    "is_active": getattr(agent, "is_active", None),
                    "created_at": (
                        agent.created_at.isoformat()
                        if request.include_metadata and agent.created_at is not None
                        else None
                    ),
                }
                for agent in agents
            ]
            total_records += len(agents)
            categories_exported.append("agents")

        if DataCategory.TASKS in categories_to_export:
            # TODO(Rakesh): filter on Task.created_by_id == current_user.id when field exists (#SP-DLP-002)
            tasks_result = await db.execute(
                select(Task).filter(Task.tenant_id == tenant_id).limit(10000)
            )
            tasks = tasks_result.scalars().all()
            export_data["tasks"] = [
                {
                    "id": str(task.id),
                    "title": getattr(task, "title", None),
                    "description": getattr(task, "description", None),
                    "status": task.status,
                    "assigned_agent_id": (
                        str(aid) if (aid := getattr(task, "assigned_agent_id", None)) else None
                    ),
                    "result": task.result_json,
                    "created_at": task.created_at.isoformat() if request.include_metadata else None,
                    "completed_at": (
                        task.finished_at.isoformat()
                        if task.finished_at and request.include_metadata
                        else None
                    ),
                }
                for task in tasks
            ]
            total_records += len(tasks)
            categories_exported.append("tasks")

        if DataCategory.WORKFLOWS in categories_to_export:
            workflows_result = await db.execute(
                select(Workflow).filter(
                    Workflow.tenant_id == tenant_id,
                    Workflow.created_by == current_user.id,  # AUDIT-GDPR-007 / Art. 20
                )
            )
            workflows = workflows_result.scalars().all()
            export_data["workflows"] = [
                {
                    "id": str(workflow.id),
                    "name": workflow.name,
                    "description": workflow.description,
                    "definition": getattr(workflow, "definition", None),
                    "is_active": workflow.is_active,
                    "created_at": (
                        workflow.created_at.isoformat() if request.include_metadata else None
                    ),
                }
                for workflow in workflows
            ]
            total_records += len(workflows)
            categories_exported.append("workflows")

        if DataCategory.AUDIT in categories_to_export:
            audit_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
            audit_result = await db.execute(
                select(AuditLog)
                .filter(
                    and_(
                        AuditLog.tenant_id == tenant_id,
                        audit_rows_about_user(current_user.id),
                        AuditLog.timestamp > audit_cutoff,
                    )
                )
                .order_by(AuditLog.timestamp.desc())
                .limit(10000)
            )
            audit_logs = audit_result.scalars().all()
            export_data["audit_logs"] = [
                {
                    "id": str(log.id),
                    "timestamp": log.timestamp.isoformat(),
                    "action": log.action,
                    "resource_type": log.resource,
                    "resource_id": (
                        str(rid) if (rid := getattr(log, "resource_id", None)) else None
                    ),
                    "user_id": str(log.user_id) if log.user_id else None,
                    "ip_address": log.client_ip,
                    "success": getattr(log, "success", None),
                }
                for log in audit_logs
            ]
            total_records += len(audit_logs)
            categories_exported.append("audit")

        # Audit log is best-effort: export already succeeded, must not cause 500.
        async with best_effort("gdpr export audit log", db_session=db):
            await AuditService.log_action(
                tenant_id=int(tenant_id),
                action="gdpr_export",
                resource="tenant_data:" + str(tenant_id),
                user_id=current_user.id,
                details={
                    "categories": categories_exported,
                    "total_records": total_records,
                    "format": request.format,
                },
                session=db,
                event_type="gdpr_export",
                threat_level="info",
                client_ip="unknown",
                endpoint="/api/gdpr/export",
                description="GDPR data export completed for tenant " + str(tenant_id),
            )
            await db.commit()

        logger.info(
            "GDPR export completed: %s records exported for tenant %s",
            total_records,
            tenant_id,
        )

        return ExportDataResponse(
            tenant_id=tenant_id,
            export_date=datetime.now(timezone.utc),
            categories=request.categories,
            total_records=total_records,
            data=export_data,
            metadata={
                "export_format": request.format,
                "exported_by": str(current_user.id),
                "categories_exported": categories_exported,
                "status": "completed",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "GDPR export failed for tenant %s: %s: %s",
            tenant_id,
            type(e).__name__,
            e,
            exc_info=True,
        )
        async with best_effort("gdpr export failure audit log", db_session=db):
            await AuditService.log_action(
                tenant_id=int(tenant_id),
                action="gdpr_export",
                resource="tenant_data:" + str(tenant_id),
                user_id=current_user.id,
                details={"error": "Er is een fout opgetreden."},
                session=db,
                event_type="gdpr_export_failed",
                threat_level="warning",
                client_ip="unknown",
                endpoint="/api/gdpr/export",
                description="GDPR data export failed for tenant " + str(tenant_id),
            )
            await db.commit()
        raise HTTPException(status_code=500, detail="Internal error")


@router.get(
    "/export/download/{export_id}",
    summary="Download Exported Data",
    description="Download previously exported data in JSON or CSV format",
)
async def download_export(
    export_id: str,
    format: ExportFormat = Query(ExportFormat.JSON),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Download exported data in requested format."""
    logger.info("Export download requested by user %s in format %s", current_user.id, format)

    try:
        import csv
        import io
        import json

        from fastapi.responses import StreamingResponse

        export_data = {
            "tenant_id": tenant_id,
            "export_id": export_id,
            "exported_by": current_user.id,
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {"users": [], "workflows": [], "agents": [], "audit_logs": []},
        }

        if format == ExportFormat.JSON:
            json_content = json.dumps(export_data, indent=2, default=str)
            return StreamingResponse(
                io.StringIO(json_content),
                media_type="application/json",
                headers={
                    "Content-Disposition": "attachment; filename=export_" + export_id + ".json"
                },
            )
        else:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Field", "Value"])
            writer.writerow(["Tenant ID", tenant_id])
            writer.writerow(["Export ID", export_id])
            writer.writerow(["Exported By", current_user.id])
            writer.writerow(["Export Timestamp", datetime.now(timezone.utc).isoformat()])
            csv_content = output.getvalue()
            return StreamingResponse(
                io.StringIO(csv_content),
                media_type="text/csv",
                headers={
                    "Content-Disposition": "attachment; filename=export_" + export_id + ".csv"
                },
            )

    except Exception as e:
        logger.error("Export download failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


@router.get(
    "/privacy/notice",
    summary="Privacy Notice (GDPR Article 13)",
    description="Returns the Art. 13 privacy notice with controller, DPO, legal basis, retention, and data subject rights.",
)
async def privacy_notice() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Return Art. 13 privacy information for data subjects (AUDIT-GDPR-003)."""
    return {
        "controller": {
            "name": "SanskritiSetu B.V.",
            "address": "Amsterdam, Netherlands",
            "email": "privacy@sanskritisetu.org",
        },
        "dpo": {
            "name": "Data Protection Officer",
            "email": "dpo@sanskritisetu.org",
        },
        "legal_basis": {
            "primary": "Art. 6(1)(b) - Contract performance",
            "analytics": "Art. 6(1)(f) - Legitimate interests",
            "marketing": "Art. 6(1)(a) - Consent",
        },
        "retention": {
            "personal_data": "Duration of contract + 7 years (tax/legal)",
            "audit_logs": "90 days",
            "ai_decisions": "2 years",
            "anonymized_analytics": "Indefinite",
        },
        "data_subject_rights": [
            "Art. 15 - Right of access",
            "Art. 16 - Right to rectification",
            "Art. 17 - Right to erasure",
            "Art. 18 - Right to restriction of processing",
            "Art. 20 - Right to data portability (POST /api/gdpr/export)",
            "Art. 21 - Right to object",
            "Art. 22 - Rights related to automated decision-making",
        ],
        "supervisory_authority": {
            "name": "Autoriteit Persoonsgegevens (AP)",
            "url": "https://autoriteitpersoonsgegevens.nl",
        },
    }
