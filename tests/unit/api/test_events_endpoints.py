import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.api.events_endpoints import router, get_latest_events, publish_manual_event


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/events/latest" in paths
    assert "/events/publish" in paths


@pytest.mark.asyncio
async def test_get_latest_events() -> None:
    mock_event = MagicMock()
    mock_event.model_dump.return_value = {"id": "ev-1", "type": "agent_action"}

    with patch("src.core.api.events_endpoints.event_bus.get_recent_events", return_value=[mock_event]):
        res = await get_latest_events(limit=10)
        assert len(res) == 1
        assert res[0]["id"] == "ev-1"


@pytest.mark.asyncio
async def test_publish_manual_event() -> None:
    event_data = {
        "agent_id": "agent-1",
        "phase": "act",
        "type": "USER_ACTION",
        "content": {"message": "hello"},
    }
    with patch("src.core.api.events_endpoints.event_bus.publish", new_callable=AsyncMock, return_value="ev-999"):
        res = await publish_manual_event(event_data)
        assert res["status"] == "published"
        assert res["event_id"] == "ev-999"
