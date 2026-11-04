import pytest
from unittest.mock import patch

from src.core.api.v1.governance_admin.router_anomalies import router, get_anomalies
from src.core.api.v1.governance_admin.schemas import AnomaliesResponse


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/anomalies" in paths


@pytest.mark.asyncio
async def test_get_anomalies_success() -> None:
    current_user = {"id": "admin-1", "roles": ["audit:read"]}

    resp = await get_anomalies(
        anomaly_type=None,
        severity=None,
        days=7,
        limit=10,
        tenant_id=42,
        current_user=current_user,
    )

    assert isinstance(resp, AnomaliesResponse)
    assert resp.tenant_id == 42
    assert len(resp.anomalies) > 0
    assert resp.stats.total == len(resp.anomalies)
