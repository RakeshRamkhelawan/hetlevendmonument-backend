# orphan:exempt reason: sub-router samengesteld door governance_admin/router.py (ADR-033 Laag 1)
"""Governance Admin -- risk assessment endpoints."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Path

from src.core.auth.api_deps import require_scopes, OAuth2Scope
from src.core.shared.production_logging import SafeLogger

from .dependencies import get_tenant, get_user_id
from .schemas import RiskAssessment, RiskCategory, RiskFactor, RiskLevel, RiskResponse

logger = SafeLogger(__name__)

router = APIRouter(tags=["governance"])


# ============================================================================
# Helper Functions
# ============================================================================


def calculate_risk_level(score: float) -> RiskLevel:
    if score < 20:
        return RiskLevel.MINIMAL
    elif score < 40:
        return RiskLevel.LOW
    elif score < 60:
        return RiskLevel.MODERATE
    elif score < 80:
        return RiskLevel.HIGH
    else:
        return RiskLevel.CRITICAL


def generate_risk_assessment(mission_id: str, tenant_id: int) -> RiskAssessment:
    now = datetime.now(timezone.utc)

    risk_factors = [
        RiskFactor(
            id="rf_{}".format(uuid.uuid4().hex[:8]),
            category=RiskCategory.OPERATIONAL,
            name="Agent availability",
            description="Risk of agent downtime affecting mission completion",
            score=25.0,
            level=RiskLevel.LOW,
            likelihood=0.2,
            impact=0.5,
            mitigations=["Implement failover agents", "Set up health monitoring"],
        ),
        RiskFactor(
            id="rf_{}".format(uuid.uuid4().hex[:8]),
            category=RiskCategory.FINANCIAL,
            name="Cost overrun",
            description="Risk of exceeding budget for LLM API calls",
            score=40.0,
            level=RiskLevel.MODERATE,
            likelihood=0.4,
            impact=0.6,
            mitigations=[
                "Set hard budget limits",
                "Enable cost alerts",
                "Use cheaper models for simple tasks",
            ],
        ),
        RiskFactor(
            id="rf_{}".format(uuid.uuid4().hex[:8]),
            category=RiskCategory.COMPLIANCE,
            name="Data privacy",
            description="Risk of processing PII without proper consent",
            score=55.0,
            level=RiskLevel.MODERATE,
            likelihood=0.3,
            impact=0.9,
            mitigations=[
                "Implement data anonymization",
                "Review consent flows",
                "Enable audit logging",
            ],
        ),
        RiskFactor(
            id="rf_{}".format(uuid.uuid4().hex[:8]),
            category=RiskCategory.TECHNICAL,
            name="Model drift",
            description="Risk of model performance degradation over time",
            score=30.0,
            level=RiskLevel.LOW,
            likelihood=0.5,
            impact=0.4,
            mitigations=[
                "Implement continuous monitoring",
                "Set up A/B testing",
                "Schedule regular retraining",
            ],
        ),
        RiskFactor(
            id="rf_{}".format(uuid.uuid4().hex[:8]),
            category=RiskCategory.SECURITY,
            name="Prompt injection",
            description="Risk of malicious inputs manipulating agent behavior",
            score=45.0,
            level=RiskLevel.MODERATE,
            likelihood=0.3,
            impact=0.7,
            mitigations=[
                "Implement input sanitization",
                "Add output validation",
                "Enable prompt shields",
            ],
        ),
        RiskFactor(
            id="rf_{}".format(uuid.uuid4().hex[:8]),
            category=RiskCategory.REPUTATIONAL,
            name="Output quality",
            description="Risk of generating low-quality or harmful content",
            score=35.0,
            level=RiskLevel.LOW,
            likelihood=0.25,
            impact=0.8,
            mitigations=[
                "Enable content moderation",
                "Add human review for high-risk outputs",
            ],
        ),
    ]

    total_score = sum(rf.score * (rf.likelihood + rf.impact) / 2 for rf in risk_factors)
    overall_score = total_score / len(risk_factors) if risk_factors else 0
    overall_level = calculate_risk_level(overall_score)

    recommendations = [
        "Review high-risk factors and implement mitigations",
        "Schedule regular risk assessments",
        "Monitor key metrics for early warning signs",
    ]

    if overall_score > 50:
        recommendations.insert(0, "PRIORITY: Address critical and high-risk factors immediately")

    return RiskAssessment(
        mission_id=mission_id,
        overall_score=round(overall_score, 1),
        overall_level=overall_level,
        risk_factors=risk_factors,
        assessed_at=now.isoformat(),
        valid_until=(now + timedelta(days=7)).isoformat(),
        recommendations=recommendations,
        tenant_id=tenant_id,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/risks/{mission_id}",
    response_model=RiskResponse,
    summary="Get risk assessment",
    description="Returns risk assessment for a specific mission",
)
async def get_risk_assessment(
    mission_id: str = Path(..., description="Mission ID to assess"),
    tenant_id: int = Depends(get_tenant),
    current_user: dict[str, Any] = Depends(require_scopes(OAuth2Scope.AUDIT_READ)),  # TODO(TYPE): replace Any with concrete type
) -> RiskResponse:
    """
    Get risk assessment for a mission.

    Security: Requires JWT with audit:read scope
    """
    user_id = get_user_id(current_user)

    logger.info(
        "Getting risk assessment",
        extra={"mission_id": mission_id, "tenant_id": tenant_id, "user_id": user_id},
    )

    assessment = generate_risk_assessment(mission_id, tenant_id)

    return RiskResponse(
        assessment=assessment,
        message="Risk assessment for mission {}: {} risk".format(
            mission_id, assessment.overall_level.value
        ),
    )
