"""
Integration Tests for Search API

Tests endpoints with real HTTP requests and valid JWT tokens.
"""

import asyncio
import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from src.core.api.router_registry import register_all_routers
from src.core.api.search_endpoints import get_current_tenant_id
from src.core.auth.dependencies import get_current_user_id
from src.core.auth.jwt_handler import jwt_handler
from src.core.search.bm25_service import bm25_service
from src.main import app

register_all_routers(app)

# ============================================================================
# UTILITIES
# ============================================================================


def create_test_token(user_id: str, tenant_id: int):
    """Generate a truly valid JWT token for integration testing"""
    # This payload matches the expectations of ProductionSecurityManager
    # and the auth dependencies.
    # Via de handler zelf: sinds d4890b96 (OP-182) weigert de server een token zonder JOSE-header `typ=at+jwt`
    # (log: "Token geweigerd op soort: reden=typ_mismatch"). Een met de hand gebouwde `jwt.encode` kreeg 401.
    payload = {
        "sub": f"user_{user_id}",  # Used by get_current_user
        "user_id": user_id,  # Used by ProductionSecurityManager
        "tenant_id": tenant_id,
        "security_level": "authenticated",
    }
    return jwt_handler.create_access_token(data=payload)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def tenant1_token():
    """Valid JWT token for tenant 1"""
    return create_test_token("test_user_1", 1)


@pytest.fixture
def tenant2_token():
    """Valid JWT token for tenant 2"""
    return create_test_token("test_user_2", 2)


@pytest.fixture
async def setup_search_data():
    """Set up test data in BM25 for the API tests"""
    docs = [
        {
            "id": "api_doc_1",
            "content": "The history of Indian classical music is ancient.",
        },
        {
            "id": "api_doc_2",
            "content": "Varanasi is a sacred city on the banks of the Ganges.",
        },
    ]
    await bm25_service.build_index(tenant_id=1, documents=docs, persist=False)
    yield
    await bm25_service.delete_index(tenant_id=1)


# ============================================================================
# API TESTS
# ============================================================================


# De tokens horen bij verzonnen gebruikers: de accountcontrole van de middleware (3fa4f2d2) staat uit.
@pytest.mark.usefixtures("account_actief_zonder_database")
class TestHybridSearchAPI:
    """Tests for /api/v1/search/hybrid"""

    @pytest.mark.asyncio
    async def test_search_hybrid_post_success(self, tenant1_token, setup_search_data):
        """Verify successful POST search request with real token"""
        # We override dependencies to bypass DB lookups for users
        app.dependency_overrides[get_current_user_id] = lambda: 1
        app.dependency_overrides[get_current_tenant_id] = lambda: 1

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/search/hybrid",
                json={"query": "sacred city Varanasi Ganges", "top_k": 5},
                headers={"Authorization": f"Bearer {tenant1_token}"},
            )

        app.dependency_overrides.clear()

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["results"]) > 0
        # Check if Varanasi is found (might be 1st or 2nd depending on BM25)
        doc_ids = [r["document_id"] for r in data["results"]]
        assert "api_doc_2" in doc_ids

    @pytest.mark.asyncio
    async def test_search_hybrid_get_success(self, tenant1_token, setup_search_data):
        """Verify successful GET search request"""
        app.dependency_overrides[get_current_user_id] = lambda: 1
        app.dependency_overrides[get_current_tenant_id] = lambda: 1

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/search/hybrid",
                params={"query": "classical music", "top_k": 2},
                headers={"Authorization": f"Bearer {tenant1_token}"},
            )

        app.dependency_overrides.clear()
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["results"][0]["document_id"] == "api_doc_1"

    @pytest.mark.asyncio
    async def test_search_unauthorized(self):
        """Verify 401 for request without token"""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/v1/search/hybrid", json={"query": "test"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_tenant_isolation_via_api(self, tenant2_token):
        """Verify that a tenant cannot find another tenant's documents"""
        # Build index for Tenant 1
        await bm25_service.build_index(1, [{"id": "t1", "content": "secret content"}], False)

        # Search as Tenant 2
        app.dependency_overrides[get_current_user_id] = lambda: 2
        app.dependency_overrides[get_current_tenant_id] = lambda: 2

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/search/hybrid",
                json={"query": "secret"},
                headers={"Authorization": f"Bearer {tenant2_token}"},
            )

        app.dependency_overrides.clear()
        await bm25_service.delete_index(1)

        # Tenant 2 has no index, so it should return 400 Bad Request
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # De server geeft de interne foutregel niet meer terug (`search_endpoints.py`: een algemene
        # melding; de oorzaak staat alleen in het log). Wat deze test hoort te bewijzen is nu dat het
        # antwoord de vaste melding is en NIETS uit de index van tenant 1 bevat.
        antwoord = response.text
        assert response.json().get("detail") == "Ongeldig verzoek."
        assert "secret content" not in antwoord
