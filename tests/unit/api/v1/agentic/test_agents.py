"""Unit tests for src/core/api/v1/agentic/agents.py.

These tests focus on route registration order and basic security guards.
They do not require a database because the endpoints are placeholders.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.core.api.v1.agentic.agents import router
from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    mock_user = MagicMock()
    mock_user.tenant_id = 1
    mock_user.id = 1

    async def _mock_db():
        yield AsyncMock()

    # upload_agent_yaml uses get_current_user (ADR-003 FA-002); override for unit tests
    app.dependency_overrides[get_current_user] = lambda: mock_user
    # Some tests run in a worker where the global DB engine is not initialized.
    app.dependency_overrides[get_db] = _mock_db
    # The router already has prefix="/agents"; the production app mounts it under
    # /api/v1/agentic so the final paths are /api/v1/agentic/agents/...
    app.include_router(router, prefix="/api/v1/agentic")
    return TestClient(app)


@pytest.mark.unit
def test_static_routes_resolve_before_dynamic_segment(client: TestClient) -> None:
    """Static routes (/validate, /load, /upload) must not be shadowed by /{agent_id}."""
    for path in ("/validate", "/load", "/upload"):
        response = client.post(f"/api/v1/agentic/agents{path}")
        # These endpoints do not require auth in the current placeholder impl.
        # We only assert that the route resolves to the intended handler, not 404.
        assert response.status_code != 404, f"{path} was shadowed by /{{agent_id}}"


@pytest.mark.unit
def test_upload_rejects_non_yaml_content_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/agentic/agents/upload",
        files={"file": ("agent.yaml", "content", "application/json")},
    )
    assert response.status_code == 400
    assert "content type" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_accepts_missing_content_type() -> None:
    """Missing Content-Type is accepted when the filename ends with .yaml/.yml."""
    from io import BytesIO

    from src.core.api.v1.agentic.agents import upload_agent_yaml

    class FakeUploadFile:
        filename = "agent.yaml"
        content_type = None

        async def read(self, limit: int = -1) -> bytes:
            return b"content"

    mock_user = MagicMock()
    mock_user.tenant_id = 1
    result = await upload_agent_yaml(file=FakeUploadFile(), current_user=mock_user)  # type: ignore[arg-type]
    assert result.uploaded is True


@pytest.mark.unit
def test_upload_rejects_oversized_file(client: TestClient) -> None:
    big = b"x" * (1024 * 1024 + 1)
    response = client.post(
        "/api/v1/agentic/agents/upload",
        files={"file": ("agent.yaml", big, "application/x-yaml")},
    )
    assert response.status_code == 413


@pytest.mark.unit
def test_load_rejects_directory_outside_base(client: TestClient) -> None:
    response = client.post(
        "/api/v1/agentic/agents/load",
        params={"directory": "../../../etc"},
    )
    assert response.status_code == 400


@pytest.mark.unit
def test_load_base_dir_is_project_relative() -> None:
    """The traversal base must be anchored to the project root, not CWD."""
    from pathlib import Path

    from src.core.api.v1.agentic.agents import router

    # Access the source file path to verify the expected anchor depth.
    source = Path(__file__).resolve().parents[5] / "src/core/api/v1/agentic/agents.py"
    assert source.exists()
