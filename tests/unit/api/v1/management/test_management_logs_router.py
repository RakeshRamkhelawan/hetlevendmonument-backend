import pytest
from unittest.mock import MagicMock, patch

from src.core.api.v1.management.logs_router import router, get_logs, get_log_broadcast_queue
from src.core.auth.api_deps import UserResponse


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/api/v1/logs" in paths
    assert "/api/v1/logs/broadcast-queue" in paths


@pytest.mark.asyncio
async def test_get_logs() -> None:
    user = UserResponse(id=1, email="admin@example.com", tenant_id="42", role="admin")
    with patch("src.core.api.v1.management.logs_router.log_entries", [{"message": "system started"}]):
        res = await get_logs(limit=10, current_user=user, _=1)
        assert "logs" in res
        assert len(res["logs"]) == 1
        assert res["logs"][0]["message"] == "system started"


@pytest.mark.asyncio
async def test_get_log_broadcast_queue() -> None:
    user = UserResponse(id=1, email="admin@example.com", tenant_id="42", role="admin")
    with patch("src.core.api.v1.management.logs_router.log_broadcast_queue", [{"id": "queue-1"}]):
        res = await get_log_broadcast_queue(current_user=user, _=1)
        assert "queue" in res
        assert len(res["queue"]) == 1
        assert res["queue"][0]["id"] == "queue-1"
