import os
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.workflow_builder_endpoints import InputType
from src.core.auth import UserResponse
from src.core.auth.dependencies import get_current_user_dependency, get_current_user_id
from src.core.database.database import get_async_session, get_db


@pytest_asyncio.fixture
async def db_session(postgres_session: AsyncSession):
    """Use shared PostgreSQL fixture from conftest."""
    yield postgres_session


@pytest.fixture
def client(
    db_session: AsyncSession, integration_app, admin_token: str, account_actief_zonder_database
):
    """Use integration_app from conftest with PostgreSQL db_session.

    De synchrone `TestClient` draait zijn verzoek op een eigen event loop, terwijl de accountcontrole van de
    middleware (3fa4f2d2) via `postgres_session` (97bb164f) een verbinding op de loop van pytest gebruikt:
    "attached to a different loop", dus 503 (gemeten 2026-10-26). Deze test meet de toolschema's, niet het
    account, dus de controle staat uit.
    """
    from src.core.middleware.tenant_context import require_tenant_id

    async def override_get_db():
        yield db_session

    integration_app.dependency_overrides[get_db] = override_get_db
    integration_app.dependency_overrides[get_async_session] = override_get_db
    integration_app.dependency_overrides[require_tenant_id] = lambda: 1
    integration_app.dependency_overrides[get_current_user_dependency] = lambda: UserResponse(
        id=1, email="admin@test.com", tenant_id=1, is_active=True
    )

    with TestClient(
        integration_app,
        headers={
            "X-Tenant-ID": "1",
            "Authorization": f"Bearer {admin_token}",
        },
    ) as test_client:
        yield test_client

    integration_app.dependency_overrides.pop(get_current_user_dependency, None)


@pytest_asyncio.fixture
async def seed_data(db_session: AsyncSession):
    """Seed data — already exists in PostgreSQL from conftest, just return IDs."""
    # Conftest postgres_engine already seeds tenant_id=1 and user_id=1
    return {"tenant_id": 1, "user_id": 1}


async def test_get_tool_schema_email(client: TestClient, seed_data):
    """
    Verify 'tool_email_send' returns rich schema with 'inputs'.
    """
    tool_id = "tool_email_send"
    res = client.get(f"/api/v1/builder/tools/{tool_id}")

    assert res.status_code == status.HTTP_200_OK
    data = res.json()

    # Top level checks
    assert data["id"] == tool_id
    assert data["name"] == "Send Email"
    assert "inputs" in data

    # Input Validation (Smart Resolver Logic)
    inputs = data["inputs"]
    assert len(inputs) == 3

    # Check 'to' field
    to_field = next((i for i in inputs if i["name"] == "to"), None)
    assert to_field is not None
    assert to_field["type"] == InputType.STRING
    assert to_field["required"] is True

    # Check 'body' field (Textarea)
    body_field = next((i for i in inputs if i["name"] == "body"), None)
    assert body_field is not None
    assert body_field["type"] == InputType.TEXT  # Multiline

    print(" Verified Smart Resolver Schema: Send Email inputs correct.")


async def test_get_tool_schema_ai_select(client: TestClient, seed_data):
    """
    Verify 'tool_llm_generate' returns SELECT options correctly.
    """
    tool_id = "tool_llm_generate"
    res = client.get(f"/api/v1/builder/tools/{tool_id}")

    assert res.status_code == status.HTTP_200_OK
    data = res.json()

    # Check 'model' field (Select)
    inputs = data["inputs"]
    model_field = next((i for i in inputs if i["name"] == "model"), None)

    assert model_field is not None
    assert model_field["type"] == InputType.SELECT
    assert len(model_field["options"]) >= 3
    assert model_field["options"][0]["label"] == "GPT-4o"

    print(" Verified Smart Resolver Schema: AI Generate options correct.")


async def test_get_tool_schema_not_found(client: TestClient, seed_data):
    """Verify 404 for invalid tool."""
    res = client.get("/api/v1/builder/tools/invalid_tool_id")
    assert res.status_code == status.HTTP_404_NOT_FOUND
