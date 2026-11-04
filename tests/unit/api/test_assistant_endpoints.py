import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.api.assistant_endpoints import (
    router,
    ask_assistant,
    AssistantRequest,
    ClientContext,
    AssistantResponse,
)
from src.core.auth.api_deps import UserResponse


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/assistant/ask" in paths


@pytest.mark.asyncio
async def test_ask_assistant_success() -> None:
    user = UserResponse(id=1, email="alice@example.com", tenant_id="42", role="user")
    req = AssistantRequest(
        query="What is the active sprint?",
        client_context=ClientContext(route="/dashboard", language="nl"),
        model="gemini",
    )

    mock_memory = AsyncMock()
    mock_memory.get_history.return_value = []

    mock_agent = AsyncMock()
    mock_result = MagicMock()
    mock_result.response = {"message": "Active sprint is Sprint 2", "actions": [{"type": "navigate"}]}
    mock_result.suggestions = ["Show backlog"]
    mock_result.confidence = 0.95
    mock_result.data = {"plan": ["step 1"]}
    mock_agent.process_command.return_value = mock_result

    with patch("src.core.api.assistant_endpoints.get_redis_client", new_callable=AsyncMock):
        with patch("src.core.api.assistant_endpoints.ConversationMemory", return_value=mock_memory):
            with patch("src.core.api.assistant_endpoints_dependencies.create_ultimate_cva_agent", return_value=mock_agent):
                resp = await ask_assistant(request=req, current_user=user)
                assert isinstance(resp, AssistantResponse)
                assert resp.message == "Active sprint is Sprint 2"
                assert resp.confidence == 0.95
                assert resp.suggestions == ["Show backlog"]
                assert resp.actions == [{"type": "navigate"}]
                assert resp.plan == ["step 1"]
