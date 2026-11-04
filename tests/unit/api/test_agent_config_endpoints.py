"""Tests for AgentConfig API endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from src.core.api.v1.agent_configs.router import router
from src.core.auth.auth_service import UserResponse
from src.core.api.dependencies import get_db
from src.core.auth.dependencies import get_current_user

@pytest.fixture
def mock_user():
    return UserResponse(id=1, email="test@example.com", tenant_id=1, role="admin")

@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_agent_id = AsyncMock()
    repo.get_active_configs = AsyncMock(return_value=[])
    repo.update = AsyncMock()
    repo.delete = AsyncMock(return_value=True)
    return repo

@pytest.fixture
def client(mock_user, mock_repo):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: mock_user
    import src.core.api.v1.agent_configs.router as router_mod
    orig_repo = router_mod.AgentConfigRepository
    router_mod.AgentConfigRepository = lambda db: mock_repo
    yield TestClient(app)
    router_mod.AgentConfigRepository = orig_repo

def _make_cfg(**kwargs):
    cfg = MagicMock()
    defaults = dict(id=1, tenant_id=1, agent_type="email", agent_id="e1", department="hr",
                    department_user_id=None, subscribed_topics=[], is_active=True, config_json={}, created_at=None)
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(cfg, k, v)
    return cfg

def test_create_agent_config(client, mock_repo):
    mock_repo.create.return_value = _make_cfg(agent_id="e1")
    resp = client.post("/api/v1/agent-configs", json={"agent_type": "email", "agent_id": "e1", "department": "hr", "subscribed_topics": ["user.created"]})
    assert resp.status_code == 201
    assert resp.json()["agent_id"] == "e1"

def test_list_agent_configs(client, mock_repo):
    resp = client.get("/api/v1/agent-configs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["limit"] == 50
    assert body["offset"] == 0

def test_get_agent_config_not_found(client, mock_repo):
    mock_repo.get_by_agent_id.return_value = None
    resp = client.get("/api/v1/agent-configs/nonexistent")
    assert resp.status_code == 404

def test_update_agent_config_with_department_user_id(client, mock_repo):
    mock_repo.get_by_agent_id.return_value = _make_cfg(id=1, agent_id="e1", department_user_id=None)
    mock_repo.update.return_value = _make_cfg(id=1, agent_id="e1", department_user_id=42)
    resp = client.patch("/api/v1/agent-configs/e1", json={"department_user_id": 42})
    assert resp.status_code == 200
    assert resp.json()["department_user_id"] == 42

def test_delete_agent_config(client, mock_repo):
    mock_repo.get_by_agent_id.return_value = _make_cfg(id=1, agent_id="e1")
    resp = client.delete("/api/v1/agent-configs/e1")
    assert resp.status_code == 204

def test_get_circuit_status(client, mock_repo):
    mock_repo.get_by_agent_id.return_value = _make_cfg(id=1, agent_id="e1")
    resp = client.get("/api/v1/agent-configs/e1/circuit")
    assert resp.status_code == 200
    assert resp.json()["state"] == "closed"
