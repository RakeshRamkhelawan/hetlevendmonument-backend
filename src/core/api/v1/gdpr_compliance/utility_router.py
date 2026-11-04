# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""GDPR utility endpoints: compliance status and checklist.

Routes:
  GET /api/gdpr/status
  GET /api/gdpr/checklist
  PUT /api/gdpr/checklist/{requirement_id}
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import User

from .dependencies import (
    get_current_tenant_id,
    get_current_user,
    get_db,
    standaard_bewaartermijnen_dagen,
)
from .schemas import (
    ComplianceChecklist,
    ComplianceChecklistResponse,
    ComplianceRequirement,
    ComplianceStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gdpr", tags=["GDPR Compliance"])

# In-memory checklist storage (per-process cache; replace with DB in post-MVP)
_tenant_checklists: dict[str, ComplianceChecklist] = {}


def _get_default_requirements() -> list[ComplianceRequirement]:
    """Return the default 10 GDPR compliance requirements."""
    from .schemas import ComplianceCategory

    now_utc = datetime.now(timezone.utc)
    return [
        ComplianceRequirement(
            id="gdpr_1",
            category=ComplianceCategory.DATA_COLLECTION,
            title="Lawful basis for processing",
            description="Ensure there is a lawful basis for all personal data processing",
            regulation="GDPR Article 6",
            mandatory=True,
            status=ComplianceStatus.NOT_STARTED,
            due_date=(now_utc + timedelta(days=30)).isoformat(),
        ),
        ComplianceRequirement(
            id="gdpr_2",
            category=ComplianceCategory.CONSENT_MANAGEMENT,
            title="Valid consent mechanism",
            description="Implement clear, specific, and unambiguous consent mechanisms",
            regulation="GDPR Article 7",
            mandatory=True,
            status=ComplianceStatus.NOT_STARTED,
            due_date=(now_utc + timedelta(days=45)).isoformat(),
        ),
        ComplianceRequirement(
            id="gdpr_3",
            category=ComplianceCategory.ACCESS_RIGHTS,
            title="Right of access (Subject Access Requests)",
            description="Provide mechanisms for data subjects to access their personal data",
            regulation="GDPR Article 15",
            mandatory=True,
            status=ComplianceStatus.NOT_STARTED,
            due_date=(now_utc + timedelta(days=60)).isoformat(),
        ),
        ComplianceRequirement(
            id="gdpr_4",
            category=ComplianceCategory.DELETION_RIGHTS,
            title="Right to erasure ('right to be forgotten')",
            description="Allow data subjects to request deletion of their personal data",
            regulation="GDPR Article 17",
            mandatory=True,
            status=ComplianceStatus.NOT_STARTED,
            due_date=(now_utc + timedelta(days=60)).isoformat(),
        ),
        ComplianceRequirement(
            id="gdpr_5",
            category=ComplianceCategory.DATA_PROCESSING,
            title="Data processing limitation",
            description="Allow data subjects to request restriction of processing",
            regulation="GDPR Article 18",
            mandatory=True,
            status=ComplianceStatus.NOT_STARTED,
            due_date=(now_utc + timedelta(days=75)).isoformat(),
        ),
        ComplianceRequirement(
            id="gdpr_6",
            category=ComplianceCategory.DATA_TRANSFER,
            title="Data portability",
            description="Allow data subjects to receive and transfer their personal data",
            regulation="GDPR Article 20",
            mandatory=True,
            status=ComplianceStatus.NOT_STARTED,
            due_date=(now_utc + timedelta(days=90)).isoformat(),
        ),
        ComplianceRequirement(
            id="gdpr_7",
            category=ComplianceCategory.SECURITY_MEASURES,
            title="Security of processing",
            description="Implement appropriate technical and organizational measures",
            regulation="GDPR Article 32",
            mandatory=True,
            status=ComplianceStatus.NOT_STARTED,
            due_date=(now_utc + timedelta(days=30)).isoformat(),
        ),
        ComplianceRequirement(
            id="gdpr_8",
            category=ComplianceCategory.DATA_BREACH,
            title="Personal data breach notification",
            description="Notify authorities of breaches within 72 hours where feasible",
            regulation="GDPR Article 33",
            mandatory=True,
            status=ComplianceStatus.NOT_STARTED,
            due_date=(now_utc + timedelta(days=45)).isoformat(),
        ),
        ComplianceRequirement(
            id="gdpr_9",
            category=ComplianceCategory.DATA_PROCESSING,
            title="Privacy by design and default",
            description="Implement privacy by design measures",
            regulation="GDPR Article 25",
            mandatory=True,
            status=ComplianceStatus.NOT_STARTED,
            due_date=(now_utc + timedelta(days=120)).isoformat(),
        ),
        ComplianceRequirement(
            id="gdpr_10",
            category=ComplianceCategory.DATA_TRANSFER,
            title="International data transfers",
            description="Ensure adequate protection for international data transfers",
            regulation="GDPR Article 44-49",
            mandatory=True,
            status=ComplianceStatus.NOT_STARTED,
            due_date=(now_utc + timedelta(days=180)).isoformat(),
        ),
    ]


def _get_or_create_checklist(tenant_id: str) -> ComplianceChecklist:
    """Get or create tenant compliance checklist."""
    if tenant_id not in _tenant_checklists:
        now = datetime.now(timezone.utc).isoformat()
        requirements = _get_default_requirements()
        _tenant_checklists[tenant_id] = ComplianceChecklist(
            tenant_id=tenant_id,
            checklist_id="checklist_" + tenant_id + "_" + now.replace(":", "-").replace(".", "-"),
            requirements=requirements,
            overall_status=ComplianceStatus.NOT_STARTED,
            last_assessment=now,
            next_review=(datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
            score=0.0,
        )
    return _tenant_checklists[tenant_id]


def _calculate_score(checklist: ComplianceChecklist) -> float:
    """Calculate compliance score based on completed requirements."""
    if not checklist.requirements:
        return 0.0
    completed = sum(1 for req in checklist.requirements if req.status == ComplianceStatus.COMPLETED)
    return round((completed / len(checklist.requirements)) * 100, 2)


def _overall_status(checklist: ComplianceChecklist) -> ComplianceStatus:
    """Derive overall status from individual requirement statuses."""
    if not checklist.requirements:
        return ComplianceStatus.N_A

    all_completed = all(req.status == ComplianceStatus.COMPLETED for req in checklist.requirements)
    any_in_progress = any(
        req.status == ComplianceStatus.IN_PROGRESS for req in checklist.requirements
    )

    if all_completed:
        return ComplianceStatus.COMPLETED
    if any_in_progress:
        return ComplianceStatus.IN_PROGRESS
    if any(req.status == ComplianceStatus.NOT_STARTED for req in checklist.requirements):
        return ComplianceStatus.NOT_STARTED
    # All remaining are EXEMPT or N_A
    return (
        ComplianceStatus.COMPLETED
        if all(
            req.status
            in (ComplianceStatus.COMPLETED, ComplianceStatus.EXEMPT, ComplianceStatus.N_A)
            for req in checklist.requirements
        )
        else ComplianceStatus.IN_PROGRESS
    )


@router.get(
    "/status",
    summary="GDPR Compliance Status",
    description="Check GDPR compliance status for current tenant",
)
async def gdpr_compliance_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get GDPR compliance status for the current tenant."""
    logger.info("GDPR status check by user %s for tenant %s", current_user.id, tenant_id)
    data_dagen, audit_dagen = standaard_bewaartermijnen_dagen()

    return {
        "tenant_id": tenant_id,
        "compliance_status": "active",
        "last_export_date": None,
        "pending_deletion": False,
        "data_retention_days": data_dagen,
        "audit_retention_days": audit_dagen,
        # Beleidstermijnen uit de EU-standaardtabel. De nachtelijke taak verwijdert persoonsgegevens
        # en auditlog NIET zelf (`retention_cleanup_job._NIET_AUTOMATISCH`); daarom hieronder False.
        "data_retention_automatic_deletion": False,
        "audit_retention_automatic_deletion": False,
        "gdpr_articles_implemented": [15, 17, 20],
    }


@router.get(
    "/checklist",
    response_model=ComplianceChecklistResponse,
    summary="Get GDPR compliance checklist",
    description="Retrieves the GDPR compliance checklist for the tenant.",
)
async def get_compliance_checklist(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> ComplianceChecklistResponse:
    """Get GDPR compliance checklist for the current tenant."""
    logger.info("Getting compliance checklist for tenant %s", tenant_id)

    checklist = _get_or_create_checklist(tenant_id)

    total_requirements = len(checklist.requirements)
    completed_requirements = sum(
        1 for req in checklist.requirements if req.status == ComplianceStatus.COMPLETED
    )

    checklist.score = _calculate_score(checklist)
    checklist.overall_status = _overall_status(checklist)
    checklist.last_assessment = datetime.now(timezone.utc).isoformat()

    return ComplianceChecklistResponse(
        checklist=checklist,
        message=(
            "Compliance checklist retrieved. "
            + str(completed_requirements)
            + "/"
            + str(total_requirements)
            + " requirements completed"
        ),
        completed_requirements=completed_requirements,
        total_requirements=total_requirements,
    )


@router.put(
    "/checklist/{requirement_id}",
    response_model=ComplianceRequirement,
    summary="Update compliance requirement status",
    description="Updates the status of a specific compliance requirement.",
)
async def update_requirement_status(
    requirement_id: str,
    status: ComplianceStatus = Query(..., description="New status for the requirement"),
    evidence: str | None = Query(None, description="Evidence of compliance"),
    notes: str | None = Query(None, description="Additional notes"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> ComplianceRequirement:
    """Update the status of a specific GDPR compliance requirement."""
    logger.info(
        "Updating compliance requirement status for tenant %s, requirement %s, new status %s",
        tenant_id,
        requirement_id,
        status,
    )

    checklist = _get_or_create_checklist(tenant_id)

    target_requirement = None
    for req in checklist.requirements:
        if req.id == requirement_id:
            target_requirement = req
            break

    if not target_requirement:
        raise HTTPException(
            status_code=404, detail="Requirement '" + requirement_id + "' not found"
        )

    target_requirement.status = status
    if evidence:
        target_requirement.evidence = evidence
    if notes:
        target_requirement.notes = notes
    target_requirement.last_updated = datetime.now(timezone.utc).isoformat()

    checklist.score = _calculate_score(checklist)
    checklist.overall_status = _overall_status(checklist)
    checklist.last_assessment = datetime.now(timezone.utc).isoformat()

    _tenant_checklists[tenant_id] = checklist

    return target_requirement
