"""
Audit domain dependencies and helpers.

Migrated from src/core/api/audit_endpoints.py (SP-API-003 Dag 5).
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from src.core.middleware.tenant_context import get_current_tenant_id

from .schemas import (
    AuditEvent,
    AuditEventType,
    DataCategory,
    DataProcessingRecord,
    MissionAuditDetail,
    MissionAuditSummary,
    MissionStatus,
)


async def get_tenant() -> int:
    """Get tenant ID with error handling"""
    tenant_id = get_current_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required. Ensure JWT contains tenant_id.",
        )
    return tenant_id


def get_user_id(current_user: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
    """Extract user ID from current user"""
    if isinstance(current_user, dict):
        return str(current_user.get("user_id") or current_user.get("id") or "unknown")
    if hasattr(current_user, "id"):
        return str(current_user.id)
    return "unknown"


def get_user_email(current_user: dict[str, Any]) -> str | None:  # TODO(TYPE): replace Any with concrete type
    """Extract user email from current user"""
    if isinstance(current_user, dict):
        return current_user.get("email")
    if hasattr(current_user, "email"):
        return current_user.email
    return None


def generate_sample_audit_trail(mission_id: str, status: MissionStatus) -> list[AuditEvent]:
    """Generate sample audit trail for demonstration"""
    now = datetime.now(timezone.utc)
    events: list[AuditEvent] = []
    # Creation event
    events.append(
        AuditEvent(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            event_type=AuditEventType.CREATED,
            timestamp=(now - timedelta(days=7)).isoformat(),
            actor_id="user_creator",
            actor_email="creator@example.com",
            details={"action": "Mission created", "initial_status": "pending"},
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
        )
    )

    # Update event
    events.append(
        AuditEvent(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            event_type=AuditEventType.UPDATED,
            timestamp=(now - timedelta(days=5)).isoformat(),
            actor_id="user_editor",
            actor_email="editor@example.com",
            details={
                "action": "Mission updated",
                "fields_changed": ["description", "parameters"],
            },
            ip_address="192.168.1.101",
            user_agent=None,
        )
    )

    # Status-specific events
    if status in [
        MissionStatus.APPROVED,
        MissionStatus.COMPLETED,
        MissionStatus.IN_PROGRESS,
    ]:
        events.append(
            AuditEvent(
                id=f"evt_{uuid.uuid4().hex[:8]}",
                event_type=AuditEventType.APPROVED,
                timestamp=(now - timedelta(days=3)).isoformat(),
                actor_id="user_approver",
                actor_email="approver@example.com",
                details={
                    "action": "Mission approved",
                    "approval_notes": "Meets all criteria",
                },
                ip_address="192.168.1.102",
                user_agent=None,
            )
        )

    if status == MissionStatus.REJECTED:
        events.append(
            AuditEvent(
                id=f"evt_{uuid.uuid4().hex[:8]}",
                event_type=AuditEventType.REJECTED,
                timestamp=(now - timedelta(days=3)).isoformat(),
                actor_id="user_reviewer",
                actor_email="reviewer@example.com",
                details={
                    "action": "Mission rejected",
                    "rejection_reason": "Does not meet requirements",
                },
                ip_address="192.168.1.103",
                user_agent=None,
            )
        )

    if status in [MissionStatus.IN_PROGRESS, MissionStatus.COMPLETED]:
        events.append(
            AuditEvent(
                id=f"evt_{uuid.uuid4().hex[:8]}",
                event_type=AuditEventType.EXECUTED,
                timestamp=(now - timedelta(days=2)).isoformat(),
                actor_id="system",
                actor_email=None,
                details={
                    "action": "Mission execution started",
                    "executor": "agent_001",
                },
                ip_address=None,
                user_agent=None,
            )
        )

    if status == MissionStatus.COMPLETED:
        events.append(
            AuditEvent(
                id=f"evt_{uuid.uuid4().hex[:8]}",
                event_type=AuditEventType.COMPLETED,
                timestamp=(now - timedelta(days=1)).isoformat(),
                actor_id="system",
                actor_email=None,
                details={
                    "action": "Mission completed",
                    "result": "success",
                    "duration_ms": 45000,
                },
                ip_address=None,
                user_agent=None,
            )
        )

    if status == MissionStatus.FAILED:
        events.append(
            AuditEvent(
                id=f"evt_{uuid.uuid4().hex[:8]}",
                event_type=AuditEventType.FAILED,
                timestamp=(now - timedelta(days=1)).isoformat(),
                actor_id="system",
                actor_email=None,
                details={
                    "action": "Mission failed",
                    "error": "Timeout exceeded",
                    "retry_count": 3,
                },
                ip_address=None,
                user_agent=None,
            )
        )

    return events


def generate_data_processing_records() -> list[DataProcessingRecord]:
    """Generate sample data processing records for GDPR compliance"""
    return [
        DataProcessingRecord(
            category=DataCategory.TECHNICAL,
            purpose="Mission execution and monitoring",
            legal_basis="Legitimate interest - service provision",
            retention_period="90 days after mission completion",
            recipients=["Internal systems", "Authorized personnel"],
        ),
        DataProcessingRecord(
            category=DataCategory.BEHAVIORAL,
            purpose="Performance analytics and optimization",
            legal_basis="Legitimate interest - service improvement",
            retention_period="12 months",
            recipients=["Analytics team"],
        ),
        DataProcessingRecord(
            category=DataCategory.DERIVED,
            purpose="Audit trail and compliance",
            legal_basis="Legal obligation - audit requirements",
            retention_period="7 years",
            recipients=["Compliance team", "External auditors (upon request)"],
        ),
    ]


def generate_sample_missions(
    tenant_id: int, status_filter: MissionStatus | None = None
) -> list[MissionAuditSummary]:
    """Generate sample mission audit data for demonstration"""
    now = datetime.now(timezone.utc)

    sample_missions: list[dict[str, Any]] = [  # TODO(TYPE): replace Any with concrete type
        {
            "mission_id": "mission_001",
            "name": "Data Analysis Pipeline",
            "description": "Automated data analysis for quarterly report",
            "status": MissionStatus.COMPLETED,
            "created_by": "user_001",
            "approved_by": "user_002",
            "days_ago": 10,
        },
        {
            "mission_id": "mission_002",
            "name": "Customer Segmentation",
            "description": "ML-based customer segmentation analysis",
            "status": MissionStatus.IN_PROGRESS,
            "created_by": "user_003",
            "approved_by": "user_002",
            "days_ago": 5,
        },
        {
            "mission_id": "mission_003",
            "name": "Report Generation",
            "description": "Generate weekly performance reports",
            "status": MissionStatus.PENDING,
            "created_by": "user_001",
            "approved_by": None,
            "days_ago": 2,
        },
        {
            "mission_id": "mission_004",
            "name": "Data Migration",
            "description": "Migrate legacy data to new system",
            "status": MissionStatus.APPROVED,
            "created_by": "user_004",
            "approved_by": "user_002",
            "days_ago": 3,
        },
        {
            "mission_id": "mission_005",
            "name": "Compliance Check",
            "description": "Automated compliance verification",
            "status": MissionStatus.FAILED,
            "created_by": "user_002",
            "approved_by": "user_001",
            "days_ago": 7,
        },
        {
            "mission_id": "mission_006",
            "name": "Risk Assessment",
            "description": "Quarterly risk assessment automation",
            "status": MissionStatus.REJECTED,
            "created_by": "user_003",
            "approved_by": None,
            "days_ago": 4,
        },
    ]

    missions: list[MissionAuditSummary] = []
    for m in sample_missions:
        if status_filter and m["status"] != status_filter:
            continue

        created_at = now - timedelta(days=m["days_ago"])
        updated_at = now - timedelta(days=max(0, m["days_ago"] - 1))
        approved_at = (
            (now - timedelta(days=m["days_ago"] - 1)).isoformat() if m["approved_by"] else None
        )

        audit_trail = generate_sample_audit_trail(m["mission_id"], m["status"])

        missions.append(
            MissionAuditSummary(
                mission_id=m["mission_id"],
                name=m["name"],
                description=m["description"],
                status=m["status"],
                created_at=created_at.isoformat(),
                updated_at=updated_at.isoformat(),
                created_by=m["created_by"],
                approved_by=m["approved_by"],
                approved_at=approved_at,
                event_count=len(audit_trail),
                last_event_type=audit_trail[-1].event_type if audit_trail else None,
                data_categories=[DataCategory.TECHNICAL, DataCategory.BEHAVIORAL],
                tenant_id=tenant_id,
            )
        )

    return missions


def get_mission_detail(mission_id: str, tenant_id: int) -> MissionAuditDetail | None:
    """Get detailed mission audit data"""
    sample_missions: dict[str, dict[str, Any]] = {  # TODO(TYPE): replace Any with concrete type
        "mission_001": {
            "name": "Data Analysis Pipeline",
            "description": "Automated data analysis for quarterly report",
            "status": MissionStatus.COMPLETED,
            "created_by": "user_001",
            "approved_by": "user_002",
        },
        "mission_002": {
            "name": "Customer Segmentation",
            "description": "ML-based customer segmentation analysis",
            "status": MissionStatus.IN_PROGRESS,
            "created_by": "user_003",
            "approved_by": "user_002",
        },
        "mission_003": {
            "name": "Report Generation",
            "description": "Generate weekly performance reports",
            "status": MissionStatus.PENDING,
            "created_by": "user_001",
            "approved_by": None,
        },
    }

    if mission_id not in sample_missions:
        return None

    m = sample_missions[mission_id]
    now = datetime.now(timezone.utc)

    return MissionAuditDetail(
        mission_id=mission_id,
        name=m["name"],
        description=m["description"],
        status=m["status"],
        created_at=(now - timedelta(days=7)).isoformat(),
        updated_at=(now - timedelta(days=1)).isoformat(),
        created_by=m["created_by"],
        approved_by=m["approved_by"],
        approved_at=(now - timedelta(days=5)).isoformat() if m["approved_by"] else None,
        audit_trail=generate_sample_audit_trail(mission_id, m["status"]),
        data_processing=generate_data_processing_records(),
        metadata={"version": "1.0", "schema": "audit_v2", "export_compliant": True},
        tenant_id=tenant_id,
    )


def format_csv_export(mission: MissionAuditDetail) -> str:
    """Format mission audit data as CSV"""
    lines: list[str] = []
    # Header
    lines.append("# GDPR Data Export")
    lines.append("# Mission ID: %s" % mission.mission_id)
    lines.append("# Export Date: %s" % datetime.now(timezone.utc).isoformat())
    lines.append("")

    # Mission Summary
    lines.append("## Mission Summary")
    lines.append("Field,Value")
    lines.append("Mission ID,%s" % mission.mission_id)
    lines.append("Name,%s" % mission.name)
    lines.append("Status,%s" % mission.status.value)
    lines.append("Created At,%s" % mission.created_at)
    lines.append("Created By,%s" % mission.created_by)
    lines.append("")

    # Audit Trail
    lines.append("## Audit Trail")
    lines.append("Event ID,Event Type,Timestamp,Actor ID,Details")
    for event in mission.audit_trail:
        details = json.dumps(event.details).replace(",", ";")
        lines.append(
            "%s,%s,%s,%s,%s"
            % (event.id, event.event_type.value, event.timestamp, event.actor_id, details)
        )
    lines.append("")

    # Data Processing
    lines.append("## Data Processing Records")
    lines.append("Category,Purpose,Legal Basis,Retention Period")
    for record in mission.data_processing:
        lines.append(
            "%s,%s,%s,%s"
            % (record.category.value, record.purpose, record.legal_basis, record.retention_period)
        )

    return "\n".join(lines)
