"""
Unit tests voor Learning domein: learning conversations, analytics, feedback
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Mock app_state for all tests
@pytest.fixture(autouse=True)
def mock_app_state():
    with patch("src.core.api.learning_endpoints.app_state", {"database_initialized": True}):
        yield


@pytest.mark.asyncio
async def test_get_learning_conversations_success(test_client):
    """Test GET /api/v1/learning/conversations"""
    with patch("src.core.api.learning_endpoints.ConversationService") as mock_service:
        # Use AsyncMock for async static method
        mock_service.get_learning_data = AsyncMock(
            return_value=[{"id": 1, "topic": "AI Ethics", "user_id": 1}]
        )

        response = await test_client.get("/api/v1/learning/conversations?limit=10")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data


@pytest.mark.asyncio
async def test_get_learning_conversations_db_not_available(test_client):
    """Test learning endpoint when DB is not available"""
    with patch("src.core.api.learning_endpoints.app_state", {"database_initialized": False}):
        response = await test_client.get("/api/v1/learning/conversations")

        assert response.status_code == 503


@pytest.mark.asyncio
async def test_get_learning_analytics_success(test_client):
    """Test GET /api/v1/learning/analytics"""
    with patch("src.core.api.learning_endpoints.ConversationService") as mock_service:
        # Use AsyncMock for async static method
        mock_service.get_conversation_analytics = AsyncMock(
            return_value={
                "total_conversations": 100,
                "average_rating": 4.5,
            }
        )

        response = await test_client.get("/api/v1/learning/analytics?days=30")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "analytics" in data


@pytest.mark.asyncio
async def test_add_learning_feedback_success(test_client):
    """Test POST /api/v1/learning/feedback"""
    with patch("src.core.api.learning_endpoints.ConversationService") as mock_service:
        # Use AsyncMock for async static method
        mock_service.add_feedback = AsyncMock(return_value=True)

        feedback_payload = {
            "conversation_id": "conv-123",
            "feedback": "positive",
            "details": "Very helpful response",
        }

        response = await test_client.post("/api/v1/learning/feedback", json=feedback_payload)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


@pytest.mark.asyncio
async def test_get_conversation_history_success(test_client):
    """Test GET /api/v1/conversations/{session_id}"""
    with patch("src.core.api.learning_endpoints.ConversationService") as mock_service:
        # Use AsyncMock for async static method
        mock_service.get_conversation_history = AsyncMock(
            return_value=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
        )

        response = await test_client.get("/api/v1/conversations/session-123?limit=50")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "history" in data


def test_learning_audit_logging(monkeypatch):
    """Mock audit log en controleer aanroep bij learning operatie"""
    # Placeholder voor audit logging test
    pass


def test_learning_concurrent_creation(monkeypatch):
    """Simuleer gelijktijdige learning creatie requests (threading of async)"""
    # Placeholder voor concurrentie test
    pass


def test_learning_rollback_on_db_failure(monkeypatch):
    """Forceer DB-fout tijdens learning operatie, controleer rollback"""
    # Placeholder voor rollback test
    pass
