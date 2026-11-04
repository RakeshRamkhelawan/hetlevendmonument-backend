from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import src.core.api.assistant_endpoints as ae
from src.core.agents.ultimate_cva.models import UltimateExecutionResult
from src.core.auth.dependencies import get_current_user, oauth2_scheme


@pytest.fixture
def test_app():
    app = FastAPI()
    # Explicitly override before including router if possible,
    # but normally after is fine too.
    app.include_router(ae.router)
    return app


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = 1
    user.tenant_id = 1
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_agent():
    agent_instance = MagicMock()
    agent_instance.process_command = AsyncMock()
    with patch("src.core.api.assistant_endpoints.UltimateCVAAgent", return_value=agent_instance):
        with patch(
            "src.core.api.assistant_endpoints_dependencies.create_ultimate_cva_agent",
            new=AsyncMock(return_value=agent_instance),
        ):
            yield agent_instance


@pytest.fixture
def mock_memory():
    with patch("src.core.api.assistant_endpoints.ConversationMemory") as mock:
        memory_instance = mock.return_value
        memory_instance.get_history = AsyncMock(return_value=[])
        memory_instance.add_message = AsyncMock()
        yield memory_instance


@pytest.fixture
def mock_redis():
    with patch("src.core.api.assistant_endpoints.get_redis_client") as mock:
        client = AsyncMock()
        mock.return_value = client
        yield client


class TestAssistantEndpoints:
    """Tests for assistant API endpoints"""

    def test_ask_assistant_success(self, test_app, mock_user, mock_agent, mock_memory, mock_redis):
        """Test successful assistant query"""

        # Arrange
        async def override_get_current_user():
            return mock_user

        # Override both to be safe
        test_app.dependency_overrides[get_current_user] = override_get_current_user
        test_app.dependency_overrides[oauth2_scheme] = lambda: "fake-token"

        mock_agent.process_command.return_value = UltimateExecutionResult(
            success=True,
            response={
                "message": "Hello! I am your assistant.",
                "actions": [{"type": "navigate", "route": "/vibe"}],
            },
            confidence=0.9,
            execution_time=0.1,
            suggestions=["Ask about workflows"],
            performance_metrics={},
        )

        payload = {
            "query": "Help me build a workflow",
            "client_context": {"route": "/dashboard", "language": "en"},
            "model": "gemini",
        }

        # Act
        client = TestClient(test_app)
        response = client.post(
            "/assistant/ask", json=payload, headers={"Authorization": "Bearer fake"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Hello! I am your assistant."

        # Verify memory interaction (user + assistant)
        assert mock_memory.add_message.call_count == 2

        # Cleanup
        test_app.dependency_overrides.clear()

    def test_ask_assistant_error(self, test_app, mock_user, mock_agent, mock_memory, mock_redis):
        """Test assistant query returns 500 on agent failure"""
        # Arrange
        test_app.dependency_overrides[get_current_user] = lambda: mock_user
        test_app.dependency_overrides[oauth2_scheme] = lambda: "fake-token"

        mock_agent.process_command.side_effect = Exception("Agent crashed")

        payload = {"query": "test", "client_context": {"route": "/"}}

        # Act
        client = TestClient(test_app)
        response = client.post(
            "/assistant/ask", json=payload, headers={"Authorization": "Bearer fake"}
        )

        # Assert
        assert response.status_code == 500
        assert response.json()["detail"] == "Er is een interne fout opgetreden."

        # Cleanup
        test_app.dependency_overrides.clear()

    def test_ask_assistant_unauthorized(self, test_app):
        """Test that the endpoint requires authentication"""
        # Arrange - mock oauth2_scheme to raise 401 when no token provided
        from fastapi import HTTPException

        from src.core.database.database import get_db

        async def mock_oauth2_no_token():
            raise HTTPException(status_code=401, detail="Not authenticated")

        async def mock_get_db():
            raise HTTPException(status_code=401, detail="Not authenticated")

        test_app.dependency_overrides[oauth2_scheme] = mock_oauth2_no_token
        test_app.dependency_overrides[get_db] = mock_get_db

        # Act
        client = TestClient(test_app)
        response = client.post(
            "/assistant/ask", json={"query": "test", "client_context": {"route": "/"}}
        )

        # Cleanup
        test_app.dependency_overrides.clear()

        # Assert
        assert response.status_code == 401
