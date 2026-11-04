import pytest
from unittest.mock import patch

from src.core.api.v1.governance_admin.router_risk import router, get_risk_assessment
from src.core.api.v1.governance_admin.schemas import RiskResponse, RiskLevel


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/risks/{mission_id}" in paths


@pytest.mark.asyncio
async def test_get_risk_assessment_success() -> None:
    current_user = {"id": "admin-1", "roles": ["audit:read"]}

    resp = await get_risk_assessment(
        mission_id="mission-alpha-1",
        tenant_id=42,
        current_user=current_user,
    )

    assert isinstance(resp, RiskResponse)
    assert resp.assessment.mission_id == "mission-alpha-1"
    assert resp.assessment.tenant_id == 42
    assert len(resp.assessment.risk_factors) == 6
    assert resp.assessment.overall_level in [
        RiskLevel.MINIMAL,
        RiskLevel.LOW,
        RiskLevel.MODERATE,
        RiskLevel.HIGH,
        RiskLevel.CRITICAL,
    ]
    assert "Risk assessment for mission mission-alpha-1" in resp.message
