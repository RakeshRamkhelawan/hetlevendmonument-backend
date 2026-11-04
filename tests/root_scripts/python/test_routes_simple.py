"""
Simple standalone test to verify admin management endpoints work
This bypasses complex conftest.py fixture logic to isolate the issue
"""

import os
import sys

os.environ["TESTING"] = "1"
sys.path.insert(0, "src")

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api.document_endpoints import router as document_router
from src.core.api.rag_endpoints import router as rag_router

# Import routers
from src.core.api.tenant_management_endpoints import router as tenant_mgmt_router
from src.core.api.user_management_endpoints import router as user_mgmt_router

# Create simple test app
app = FastAPI(title="Dev Test")
app.include_router(tenant_mgmt_router, tags=["Tenant Management"])
app.include_router(user_mgmt_router, tags=["User Management"])
app.include_router(document_router, tags=["Documents"])
app.include_router(rag_router, tags=["RAG"])


@pytest.mark.asyncio
async def test_routes_are_registered():
    """Verify all our routes exist in the app"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Check tenant routes exist
        response = await client.get("/api/v1/tenants/")
        print(f"Tenant GET response: {response.status_code}")
        assert response.status_code != 404, "Tenant route not found!"

        # Check user routes exist
        response = await client.get("/api/v1/users/")
        print(f"User GET response: {response.status_code}")
        assert response.status_code != 404, "User route not found!"

        # Check document routes exist
        response = await client.get("/api/v1/documents/")
        print(f"Document GET response: {response.status_code}")
        assert response.status_code != 404, "Document route not found!"

        # Check RAG routes exist
        response = await client.post("/api/v1/rag/search", json={"query": "test"})
        print(f"RAG search POST response: {response.status_code}")
        assert response.status_code != 404, "RAG search route not found!"

        print("\n[SUCCESS] All routes found and accessible!")


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_routes_are_registered())
