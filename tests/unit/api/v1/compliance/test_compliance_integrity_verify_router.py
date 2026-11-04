"""Unit tests for compliance integrity verify router (src/core/api/v1/compliance/integrity_verify_router.py)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.v1.compliance.dependencies import (
    HashChainVerifier,
    get_current_user,
    get_hash_chain_verifier,
)
from src.core.api.v1.compliance.integrity_verify_router import integrity_verify_router
from src.core.models.rbac_models import User

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = 123
    user.email = "auditor@example.com"
    user.tenant_id = 1
    return user


@pytest.fixture
def mock_verifier() -> AsyncMock:
    ver = AsyncMock(spec=HashChainVerifier)

    chain_res = MagicMock()
    chain_res.is_valid = True
    chain_res.tampering_detected = False
    chain_res.unhashed_entries = 0
    chain_res.unhashed_before_watermark = 0
    chain_res.unhashed_after_watermark = 0
    chain_res.total_entries = 100
    chain_res.verified_entries = 100
    chain_res.broken_at_entry_id = None
    chain_res.broken_at_index = None
    chain_res.expected_hash = None
    chain_res.actual_hash = None
    chain_res.verification_time_ms = 12.3
    chain_res.tenant_id = 1
    chain_res.checked_at = datetime.now(timezone.utc)

    ver.verify_chain = AsyncMock(return_value=chain_res)

    entry_res = MagicMock()
    entry_res.entry_id = 42
    entry_res.is_valid = True
    entry_res.hash_matches = True
    entry_res.previous_hash_matches = True
    entry_res.computed_hash = "abc123hash"
    entry_res.stored_hash = "abc123hash"
    entry_res.tenant_id = 1

    ver.verify_entry = AsyncMock(return_value=entry_res)
    return ver


@pytest.fixture
def app(mock_user: MagicMock, mock_verifier: AsyncMock) -> FastAPI:
    application = FastAPI()
    application.include_router(integrity_verify_router)

    application.dependency_overrides[get_current_user] = lambda: mock_user
    application.dependency_overrides[get_hash_chain_verifier] = lambda: mock_verifier
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_verify_chain_integrity_success(client: TestClient, mock_verifier: AsyncMock) -> None:
    response = client.get("/integrity/verify")
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is True
    assert data["tampering_detected"] is False
    assert data["total_entries"] == 100
    assert data["tenant_id"] == 1
    assert mock_verifier.verify_chain.called


def test_verify_chain_integrity_error_raises_500(client: TestClient, mock_verifier: AsyncMock) -> None:
    mock_verifier.verify_chain.side_effect = RuntimeError("Hash chain calculation error")
    response = client.get("/integrity/verify")
    assert response.status_code == 500
    assert "Failed to verify hash chain" in response.json()["detail"]


def test_verify_entry_success(client: TestClient, mock_verifier: AsyncMock) -> None:
    payload = {"entry_id": 42}
    response = client.post("/integrity/verify-entry", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["entry_id"] == 42
    assert data["is_valid"] is True
    assert data["hash_matches"] is True
    assert data["computed_hash"] == "abc123hash"
    assert mock_verifier.verify_entry.called


def test_verify_entry_error_raises_500(client: TestClient, mock_verifier: AsyncMock) -> None:
    mock_verifier.verify_entry.side_effect = RuntimeError("Entry verify failed")
    payload = {"entry_id": 42}
    response = client.post("/integrity/verify-entry", json=payload)
    assert response.status_code == 500
    assert "Failed to verify entry" in response.json()["detail"]
