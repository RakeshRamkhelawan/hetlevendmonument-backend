# orphan:exempt reason: sub-router samengesteld door governance_admin/router.py (ADR-033 Laag 1)
"""Governance Admin -- anomaly detection endpoints."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

from fastapi import APIRouter, Depends, Query

from src.core.auth.api_deps import require_scopes, OAuth2Scope
from src.core.shared.production_logging import SafeLogger

from .dependencies import get_tenant, get_user_id
from .schemas import (
    AnomaliesResponse,
    AnomalyDetail,
    AnomalySeverity,
    AnomalyStats,
    AnomalyType,
)

logger = SafeLogger(__name__)

router = APIRouter(tags=["governance"])


# ============================================================================
# Helper Functions
# ============================================================================


def calculate_severity(actual: float, baseline: float) -> AnomalySeverity:
    """Calculate anomaly severity based on % deviation from baseline.

    <10% -> LOW, 10-25% -> MEDIUM, 25-50% -> HIGH, >50% -> CRITICAL.
    """
    if baseline == 0:
        return AnomalySeverity.CRITICAL
    deviation = abs(actual - baseline) / baseline
    if deviation < 0.10:
        return AnomalySeverity.LOW
    elif deviation < 0.25:
        return AnomalySeverity.MEDIUM
    elif deviation < 0.50:
        return AnomalySeverity.HIGH
    else:
        return AnomalySeverity.CRITICAL


def generate_sample_anomalies(
    tenant_id: int,
    anomaly_type: AnomalyType | None,
    severity: AnomalySeverity | None,
    limit: int,
) -> list[AnomalyDetail]:
    """Generate sample anomalies for demo."""
    now = datetime.now(timezone.utc)
    anomalies: list[AnomalyDetail] = []
    samples = [
        {
            "type": AnomalyType.BIAS,
            "severity": AnomalySeverity.HIGH,
            "title": "Gender bias detected in recommendations",
            "description": "Model outputs show 15% higher approval rate for male applicants",
            "source": "recommendation_agent",
            "metric_value": 0.15,
            "expected_range": "0.00-0.05",
            "recommendations": [
                "Review training data for gender balance",
                "Implement fairness constraints",
                "Add bias monitoring dashboard",
            ],
        },
        {
            "type": AnomalyType.COST,
            "severity": AnomalySeverity.MEDIUM,
            "title": "API cost spike detected",
            "description": "LLM API costs increased 45% over baseline",
            "source": "cost_monitor",
            "metric_value": 145.0,
            "expected_range": "90-110",
            "recommendations": [
                "Review prompt efficiency",
                "Enable response caching",
                "Consider model downgrade for simple tasks",
            ],
        },
        {
            "type": AnomalyType.PERFORMANCE,
            "severity": AnomalySeverity.LOW,
            "title": "Response latency increase",
            "description": "Average response time increased from 200ms to 280ms",
            "source": "performance_monitor",
            "metric_value": 280.0,
            "expected_range": "150-250",
            "recommendations": [
                "Check database query performance",
                "Review concurrent request handling",
            ],
        },
        {
            "type": AnomalyType.SECURITY,
            "severity": AnomalySeverity.CRITICAL,
            "title": "Unusual access pattern detected",
            "description": "Multiple failed authentication attempts from same IP",
            "source": "security_monitor",
            "metric_value": 50.0,
            "expected_range": "0-5",
            "recommendations": [
                "Block suspicious IP temporarily",
                "Enable rate limiting",
                "Review authentication logs",
            ],
        },
        {
            "type": AnomalyType.COMPLIANCE,
            "severity": AnomalySeverity.MEDIUM,
            "title": "Data retention policy violation",
            "description": "Some records exceed 90-day retention limit",
            "source": "compliance_checker",
            "metric_value": 120.0,
            "expected_range": "0-90",
            "recommendations": [
                "Run data cleanup job",
                "Review retention policies",
                "Set up automated purging",
            ],
        },
        {
            "type": AnomalyType.QUALITY,
            "severity": AnomalySeverity.LOW,
            "title": "Output quality score decline",
            "description": "Average user satisfaction dropped from 4.2 to 3.8",
            "source": "quality_monitor",
            "metric_value": 3.8,
            "expected_range": "4.0-5.0",
            "recommendations": [
                "Review recent model changes",
                "Analyze user feedback",
                "Consider A/B testing improvements",
            ],
        },
    ]

    for i, sample in enumerate(samples):
        if anomaly_type and sample["type"] != anomaly_type:
            continue
        if severity and sample["severity"] != severity:
            continue

        anomalies.append(
            AnomalyDetail(
                id="anomaly_{}".format(uuid.uuid4().hex[:8]),
                type=cast(AnomalyType, sample["type"]),
                severity=cast(AnomalySeverity, sample["severity"]),
                title=cast(str, sample["title"]),
                description=cast(str, sample["description"]),
                source=cast(str, sample["source"]),
                source_id="src_{}".format(i),
                metric_value=cast(Optional[float], sample["metric_value"]),
                expected_range=cast(Optional[str], sample["expected_range"]),
                detected_at=(now - timedelta(hours=i * 2)).isoformat(),
                recommendations=cast(list[str], sample["recommendations"]),
                metadata={"tenant_id": tenant_id, "index": i},
            )
        )

        if len(anomalies) >= limit:
            break

    return anomalies


def calculate_anomaly_stats(anomalies: list[AnomalyDetail]) -> AnomalyStats:
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}

    for anomaly in anomalies:
        type_key = anomaly.type.value
        by_type[type_key] = by_type.get(type_key, 0) + 1
        severity_key = anomaly.severity.value
        by_severity[severity_key] = by_severity.get(severity_key, 0) + 1

    critical_high = by_severity.get("critical", 0) + by_severity.get("high", 0)
    low_medium = by_severity.get("low", 0) + by_severity.get("medium", 0)

    if critical_high > low_medium:
        trend = "worsening"
    elif critical_high < low_medium:
        trend = "improving"
    else:
        trend = "stable"

    return AnomalyStats(total=len(anomalies), by_type=by_type, by_severity=by_severity, trend=trend)


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/anomalies",
    response_model=AnomaliesResponse,
    summary="Detect anomalies",
    description="Detects anomalies in AI operations (bias, cost, performance, etc.)",
)
async def get_anomalies(
    anomaly_type: AnomalyType | None = Query(None, description="Filter by anomaly type"),
    severity: AnomalySeverity | None = Query(None, description="Filter by severity"),
    days: int = Query(7, ge=1, le=90, description="Days to look back"),
    limit: int = Query(20, ge=1, le=100, description="Maximum anomalies to return"),
    tenant_id: int = Depends(get_tenant),
    current_user: dict[str, Any] = Depends(require_scopes(OAuth2Scope.AUDIT_READ)),  # TODO(TYPE): replace Any with concrete type
) -> AnomaliesResponse:
    """
    Get detected anomalies.

    Security: Requires JWT with audit:read scope
    """
    user_id = get_user_id(current_user)
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=days)

    logger.info(
        "Getting anomalies",
        extra={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "anomaly_type": anomaly_type,
            "severity": severity,
            "days": days,
        },
    )

    anomalies = generate_sample_anomalies(tenant_id, anomaly_type, severity, limit)
    stats = calculate_anomaly_stats(anomalies)

    return AnomaliesResponse(
        anomalies=anomalies,
        stats=stats,
        period_start=period_start.isoformat(),
        period_end=now.isoformat(),
        tenant_id=tenant_id,
    )
