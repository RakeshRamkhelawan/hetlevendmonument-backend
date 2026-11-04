import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.core.api.v1.gdpr_compliance.access_router import router, audit_trail
from src.core.api.v1.gdpr_compliance.schemas import AuditTrailRequest, AuditTrailResponse
from src.core.models.rbac_models import User


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/api/gdpr/audit-trail" in paths


@pytest.mark.asyncio
async def test_audit_trail_success() -> None:
    user = MagicMock(spec=User)
    user.id = 1
    user.tenant_id = "tenant-42"

    req = AuditTrailRequest(page=1, page_size=50)

    registry = AsyncMock()
    registry.validate_endpoint_access.return_value = None

    session = AsyncMock()
    # First execute: count query
    count_res = MagicMock()
    count_res.scalar.return_value = 1

    # Second execute: audit logs query
    mock_log = MagicMock()
    mock_log.id = 777
    mock_log.timestamp = datetime.now(timezone.utc)
    mock_log.action = "data_export"
    mock_log.resource = "user_profile"
    mock_log.user_id = 1
    mock_log.client_ip = "127.0.0.1"
    mock_log.details = {"format": "json"}

    logs_res = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [mock_log]
    logs_res.scalars.return_value = scalars_mock

    session.execute.side_effect = [count_res, logs_res]

    resp = await audit_trail(
        request=req,
        db=session,
        current_user=user,
        tenant_id="tenant-42",
        registry=registry,
    )

    assert isinstance(resp, AuditTrailResponse)
    assert resp.tenant_id == "tenant-42"
    assert resp.total_logs == 1
    assert resp.page == 1
    assert len(resp.logs) == 1
    assert resp.logs[0].id == "777"
    assert resp.logs[0].action == "data_export"
