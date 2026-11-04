# orphan:exempt reason: Laag 1 composiet, geladen via governance_admin/__init__.py (ADR-033)
"""Governance Admin composite router (ADR-033 Laag 1)."""

from fastapi import APIRouter

from .dependencies import get_tenant, get_user_id  # noqa: F401 (re-export for legacy shim)
from .router_anomalies import (  # noqa: F401 (re-export for legacy shim)
    calculate_anomaly_stats,
    calculate_severity,
    generate_sample_anomalies,
    get_anomalies,
)
from .router_anomalies import router as anomalies_router
from .router_risk import (  # noqa: F401 (re-export for legacy shim)
    calculate_risk_level,
    generate_risk_assessment,
    get_risk_assessment,
)
from .router_risk import router as risk_router
from .schemas import (  # noqa: F401 (re-export for legacy shim)
    AnomaliesResponse,
    AnomalyDetail,
    AnomalySeverity,
    AnomalyStats,
    AnomalyType,
    RiskAssessment,
    RiskCategory,
    RiskFactor,
    RiskLevel,
    RiskResponse,
)

__all__ = [
    "router",
    "AnomaliesResponse",
    "AnomalyDetail",
    "AnomalySeverity",
    "AnomalyStats",
    "AnomalyType",
    "RiskAssessment",
    "RiskCategory",
    "RiskFactor",
    "RiskLevel",
    "RiskResponse",
    "calculate_anomaly_stats",
    "calculate_risk_level",
    "calculate_severity",
    "generate_risk_assessment",
    "generate_sample_anomalies",
    "get_anomalies",
    "get_risk_assessment",
    "get_tenant",
    "get_user_id",
]

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])
router.include_router(anomalies_router)
router.include_router(risk_router)
