"""
Integration Tests for Corrective RAG API
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient

from src.core.api.crag_endpoints import require_tenant_id
from src.core.auth.jwt_handler import jwt_handler


def create_test_token(user_id: str, tenant_id: int):
    # Via de handler zelf: sinds d4890b96 (OP-182) weigert de server een token zonder JOSE-header `typ=at+jwt`
    # (log: "Token geweigerd op soort: reden=typ_mismatch"). Een met de hand gebouwde `jwt.encode` kreeg 401.
    payload = {
        "sub": f"user_{user_id}",
        "user_id": user_id,
        "tenant_id": tenant_id,
        "security_level": "authenticated",
    }
    return jwt_handler.create_access_token(data=payload)


@pytest.fixture
def test_token():
    return create_test_token("crag_user", 1)


@pytest.fixture
async def setup_db(postgres_engine):
    # Schema is managed by shared integration setup/migrations.
    # Re-running create_all here can conflict with already-created objects.
    yield


# De tokens horen bij verzonnen gebruikers: de accountcontrole van de middleware (3fa4f2d2) staat uit.
@pytest.mark.usefixtures("account_actief_zonder_database")
class TestCRAGAPI:
    @pytest.mark.asyncio
    async def test_crag_chat_success(self, integration_client: AsyncClient, test_token, setup_db):
        """Verify successful CRAG chat request"""
        mock_response = {
            "answer": "The Taj Mahal is in Agra.",
            "sources": [{"id": "doc1", "content": "Taj info", "score": 0.9}],
            "web_search_triggered": False,
            "original_query": "Where is Taj Mahal?",
        }

        # Mock the agent execution
        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(return_value=mock_response)

        with patch(
            "src.core.agents.corrective_rag_agent.get_corrective_rag_agent",
            return_value=mock_agent,
        ):
            response = await integration_client.post(
                "/api/v1/crag/chat",
                json={"query": "Where is Taj Mahal?"},
                headers={"Authorization": f"Bearer {test_token}"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["answer"] == "The Taj Mahal is in Agra."
        assert len(data["sources"]) == 1
        assert data["web_search_triggered"] is False

    @pytest.mark.asyncio
    async def test_crag_chat_web_search_trigger(
        self, integration_client: AsyncClient, test_token, setup_db
    ):
        """Verify CRAG chat when web search is triggered"""
        mock_response = {
            "answer": "Current stock price is $150.",
            "sources": [{"id": "web_1", "metadata": {"source": "web"}}],
            "web_search_triggered": True,
            "original_query": "Apple stock price",
        }

        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(return_value=mock_response)

        with patch(
            "src.core.agents.corrective_rag_agent.get_corrective_rag_agent",
            return_value=mock_agent,
        ):
            response = await integration_client.post(
                "/api/v1/crag/chat",
                json={"query": "Apple stock price"},
                headers={"Authorization": f"Bearer {test_token}"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["web_search_triggered"] is True
        assert data["sources"][0]["metadata"]["source"] == "web"

    @pytest.mark.asyncio
    async def test_crag_validation_error(self, integration_client: AsyncClient, test_token):
        """Verify 422 for invalid request"""
        response = await integration_client.post(
            "/api/v1/crag/chat",
            json={"wrong_field": "test"},
            headers={"Authorization": f"Bearer {test_token}"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_crag_unauthorized(self, integration_client: AsyncClient):
        """Verify 401 without token"""
        response = await integration_client.post("/api/v1/crag/chat", json={"query": "test"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
