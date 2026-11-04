"""Unit tests voor critic router GET endpoints (SP-AGT-005 Dag 2).

Alle 5 tests zijn ROOD totdat de endpoints geimplementeerd zijn in critic_router.py:
  GET /critics/health
  GET /critics/{agent_name}/report
  GET /critics/{agent_name}/common-issues
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.agents.critic_agent import CriticAgent
from src.core.api.v1.orchestration.critic_router import critic_router
from src.core.api.v1.orchestration.dependencies import get_critic_agent
from src.core.middleware.tenant_context import get_current_tenant_id

TENANT_ID = 42

_HEALTH_RESPONSE = {
    "health_score": 0.85,
    "status": "healthy",
    "critique_stats": {
        "total_critiques": 10,
        "agents_tracked": 2,
        "critiques_per_agent": {},
        "storage_limit": 10000,
    },
    "tenant_id": TENANT_ID,
}

_REPORT_RESPONSE = {
    "agent_name": "test_agent",
    "window_hours": 24,
    "average_score": 0.75,
    "score_distribution": {},
    "common_issues": [["issue_a", 3], ["issue_b", 1]],
    "generated_at": "2026-06-19T00:00:00+00:00",
}

_COMMON_ISSUES_RESPONSE = [
    {"issue": "issue_a", "count": 3},
    {"issue": "issue_b", "count": 1},
]


@pytest.fixture
def mock_critic():
    agent = MagicMock(spec=CriticAgent)
    agent.get_system_health = AsyncMock(return_value=_HEALTH_RESPONSE)
    agent.get_agent_report = AsyncMock(return_value=_REPORT_RESPONSE)
    agent.get_common_issues = AsyncMock(return_value=_COMMON_ISSUES_RESPONSE)
    return agent


@pytest.fixture
def client_with_tenant(mock_critic):
    app = FastAPI()
    app.include_router(critic_router, prefix="/critics")
    app.dependency_overrides[get_critic_agent] = lambda: mock_critic
    return TestClient(app)


@pytest.fixture
def client_no_tenant():
    app = FastAPI()
    app.include_router(critic_router, prefix="/critics")
    app.dependency_overrides[get_current_tenant_id] = lambda: None
    return TestClient(app)


@pytest.mark.unit
def test_health_endpoint_returns_200_with_health_data(client_with_tenant, mock_critic):
    """GET /critics/critic-health geeft gezondheidsdata terug in het standaard response-formaat."""
    response = client_with_tenant.get("/critics/critic-health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "health_score" in body["data"]
    assert body["data"]["status"] in ("healthy", "degraded", "critical")
    mock_critic.get_system_health.assert_called_once()


@pytest.mark.unit
def test_report_endpoint_returns_200_with_agent_report(client_with_tenant, mock_critic):
    """GET /critics/{agent_name}/report geeft een agentrapport terug."""
    response = client_with_tenant.get("/critics/test_agent/report")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["agent_name"] == "test_agent"
    assert "average_score" in body["data"]
    mock_critic.get_agent_report.assert_called_once_with("test_agent")


@pytest.mark.unit
def test_common_issues_endpoint_returns_list_of_dicts(client_with_tenant, mock_critic):
    """GET /critics/{agent_name}/common-issues geeft een lijst met issue+count terug."""
    response = client_with_tenant.get("/critics/test_agent/common-issues")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    issues = body["data"]
    assert isinstance(issues, list)
    assert all("issue" in item and "count" in item for item in issues)
    mock_critic.get_common_issues.assert_called_once_with("test_agent")


@pytest.mark.unit
def test_health_endpoint_returns_401_without_tenant(client_no_tenant):
    """GET /critics/critic-health zonder tenantcontext geeft 401 terug."""
    response = client_no_tenant.get("/critics/critic-health")
    assert response.status_code == 401


@pytest.mark.unit
def test_report_endpoint_returns_401_without_tenant(client_no_tenant):
    """GET /critics/{agent_name}/report zonder tenantcontext geeft 401 terug."""
    response = client_no_tenant.get("/critics/test_agent/report")
    assert response.status_code == 401
