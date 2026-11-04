"""
Integration tests for Prana economy and A2A Contracts REST API endpoints.

Uses a minimal FastAPI test app with dependency overrides to bypass auth
and inject controlled tenant context. ContractManager is mocked to avoid
asyncio.create_task complexity in test setup.
"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.dependencies import require_authenticated_user
from src.core.api.v1.contracts import router as contracts_router
from src.core.api.v1.prana import router as prana_router
from src.core.middleware.tenant_context import safe_get_tenant_id

TENANT_1 = 10
TENANT_2 = 20

# Valid Department enum values (lowercase, as defined in department_orchestrator.py)
DEPT_HR = "hr"
DEPT_IT = "it_security"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_app(tenant_id: int) -> FastAPI:
    """Minimal FastAPI app with auth bypassed for the given tenant."""
    app = FastAPI()
    app.include_router(prana_router, prefix="/api/v1")
    app.include_router(contracts_router, prefix="/api/v1")
    app.dependency_overrides[safe_get_tenant_id] = lambda: tenant_id
    app.dependency_overrides[require_authenticated_user] = lambda: {
        "user_id": 1,
        "tenant_id": tenant_id,
    }
    return app


def _make_mock_contract(
    contract_id: str = "ctr_abc123",
    producer: str = "agent_a",
    consumer: str = "agent_b",
) -> MagicMock:
    """Return a MagicMock that mimics an A2AContract instance."""
    now = datetime.now(timezone.utc)
    mock = MagicMock()
    mock.contract_id = contract_id
    mock.producer_agent = producer
    mock.consumer_agent = consumer
    mock.producer_department = MagicMock()
    mock.producer_department.value = "it_security"
    mock.consumer_department = MagicMock()
    mock.consumer_department.value = "hr"
    mock.prana_cost = 100
    mock.deadline_ms = 5000
    mock.status = MagicMock()
    mock.status.value = "proposed"
    mock.created_at = now
    mock.agreed_at = None
    mock.completed_at = None
    return mock


def _make_mock_manager(
    prana_ledger: dict[str, int] | None = None,
    contracts: dict[str, Any] | None = None,
) -> MagicMock:
    """Return a MagicMock mimicking ContractManager with pre-seeded state."""
    manager = MagicMock()
    manager._prana_ledger = prana_ledger if prana_ledger is not None else {}
    manager._contracts = contracts if contracts is not None else {}
    proposed_contract = _make_mock_contract()
    manager.propose_contract = AsyncMock(return_value=proposed_contract)
    return manager


# ---------------------------------------------------------------------------
# Test 1 — GET /api/v1/prana/balance (happy path)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_prana_balance_returns_tenant_agents() -> None:
    """
    GIVEN a tenant with two agents that have prana balances
    WHEN GET /api/v1/prana/balance is called
    THEN the response contains both agents and their balances
    """
    manager = _make_mock_manager(prana_ledger={"agent_a": 500, "agent_b": -50})
    app = _build_app(TENANT_1)
    with patch("src.core.api.v1.prana.get_contract_manager", return_value=manager):
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/api/v1/prana/balance")
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == TENANT_1
    assert data["total_agents"] == 2
    balances_by_agent = {b["agent_id"]: b["balance"] for b in data["balances"]}
    assert balances_by_agent["agent_a"] == 500
    assert balances_by_agent["agent_b"] == -50


# ---------------------------------------------------------------------------
# Test 2 — GET /api/v1/contracts (happy path)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_list_contracts_returns_tenant_contracts() -> None:
    """
    GIVEN a tenant with one active A2A contract
    WHEN GET /api/v1/contracts is called
    THEN the response lists that contract with correct fields
    """
    contract = _make_mock_contract("ctr_xyz", "agent_sales", "agent_hr")
    manager = _make_mock_manager(contracts={"ctr_xyz": contract})
    app = _build_app(TENANT_1)
    with patch("src.core.api.v1.contracts.get_contract_manager", return_value=manager):
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/api/v1/contracts")
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == TENANT_1
    assert data["total"] == 1
    assert data["contracts"][0]["contract_id"] == "ctr_xyz"
    assert data["contracts"][0]["producer_agent"] == "agent_sales"
    assert data["contracts"][0]["status"] == "proposed"


# ---------------------------------------------------------------------------
# Test 3 — POST /api/v1/contracts/propose (happy path)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_propose_contract_creates_new_contract() -> None:
    """
    GIVEN valid contract proposal payload with correct department values
    WHEN POST /api/v1/contracts/propose is called
    THEN a new contract is created and its contract_id returned
    """
    manager = _make_mock_manager()
    app = _build_app(TENANT_1)
    payload = {
        "consumer_agent": "agent_hr",
        "producer_agent": "agent_it",
        "consumer_department": DEPT_HR,
        "producer_department": DEPT_IT,
        "required_data": {"employee_count": "int"},
        "deadline_ms": 5000,
        "prana_cost": 50,
    }
    with patch("src.core.api.v1.contracts.get_contract_manager", return_value=manager):
        client = TestClient(app, raise_server_exceptions=True)
        response = client.post("/api/v1/contracts/propose", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["contract_id"] == "ctr_abc123"
    assert data["status"] == "proposed"
    manager.propose_contract.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4 — Tenant isolation: Tenant 2 cannot see Tenant 1 contracts
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tenant_isolation_contracts() -> None:
    """
    GIVEN Tenant 1 has contracts and Tenant 2 has none
    WHEN Tenant 2 queries GET /api/v1/contracts
    THEN Tenant 2 receives 0 contracts (no cross-tenant data leakage)
    """
    contract = _make_mock_contract("ctr_private")
    tenant1_manager = _make_mock_manager(contracts={"ctr_private": contract})
    tenant2_manager = _make_mock_manager(contracts={})

    app_t2 = _build_app(TENANT_2)
    managers_map = {TENANT_1: tenant1_manager, TENANT_2: tenant2_manager}

    # get_contract_manager for TENANT_2's app returns TENANT_2's empty manager
    with patch(
        "src.core.api.v1.contracts.get_contract_manager",
        side_effect=lambda tid: managers_map[tid],
    ):
        client = TestClient(app_t2, raise_server_exceptions=True)
        response = client.get("/api/v1/contracts")
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == TENANT_2
    assert data["total"] == 0
    assert data["contracts"] == []
