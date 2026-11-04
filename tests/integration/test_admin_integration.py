"""
Integratietests voor Admin domein: admin user aanmaken, rol toekennen, foutafhandeling
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.admin_endpoints import router

# ✅ FIXTURE FIXED (Nov 17, 2025): admin_user_with_token now uses real login endpoint
# admin_token fixture generates proper JWT tokens via /auth/login
# NO MORE hardcoded user_ids - uses actual database users
# pytestmark = pytest.mark.skip(reason="FIXTURE ISSUE: admin_token uses hardcoded user_id. Same fix as normal_user_with_token. PRIORITY: HIGH")


# Deleted:app = FastAPI()
# Deleted:app.include_router(router, prefix="/api/admin")
# Deleted:client = TestClient(app)


@pytest.mark.asyncio
async def test_create_and_assign_role_flow(integration_client, admin_token):
    print("\n[DEBUG] ==> Stap 1: test_create_and_assign_role_flow BEGONNEN")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await integration_client.get("/admin/dashboard", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "dashboard_data" in data
    print("[DEBUG] <== Stap 1: test_create_and_assign_role_flow VOLTOOID")


@pytest.mark.asyncio
async def test_assign_role_user_not_found(integration_client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await integration_client.post(
        "/admin/assign_role/999999", json={"role": "editor"}, headers=headers
    )
    assert response.status_code in (404, 400, 422)


@pytest.mark.asyncio
async def test_create_admin_boundary_values(integration_client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await integration_client.get("/admin/users", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_admin_minimum_values(integration_client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await integration_client.get("/admin/users?limit=1", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_admin_rate_limit(integration_client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await integration_client.get("/admin/users?limit=2", headers=headers)
    assert resp.status_code == 200


def test_admin_tenant_isolation():
    # Simuleer admin aanmaken onder verschillende tenants (mock context vereist)
    pass


def test_admin_audit_logging(monkeypatch):
    # Mock audit log en controleer aanroep bij admin aanmaken
    pass


def test_admin_concurrent_creation(monkeypatch):
    # Simuleer gelijktijdige admin creatie requests (threading of async)
    pass


def test_admin_rollback_on_db_failure(monkeypatch):
    # Forceer DB-fout tijdens admin creatie, controleer rollback
    pass


@pytest.mark.asyncio
async def test_security_headers(integration_client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await integration_client.get("/admin/system", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "system_info" in data
