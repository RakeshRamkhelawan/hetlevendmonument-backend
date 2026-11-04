import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_debug_flow(integration_client: AsyncClient, db_session: AsyncSession):
    unique_suffix = str(uuid.uuid4())[:8]
    email = f"debug_{unique_suffix}@example.com"
    username = f"user_{unique_suffix}"
    password = "SecurePassword123!"

    print(f"\n[STEP 1] Creating {email} directly in DB...")
    from src.core.auth.auth_service import UserCreate, auth_service
    from src.core.database.tenant_query_filter import TenantFilterBypass

    with TenantFilterBypass():
        created_user = await auth_service.create_user(
            db_session,
            UserCreate(email=email, password=password),
            tenant_id=1,
            request_path="/test",
        )
    assert created_user is not None, "Direct user creation in DB failed"
    await db_session.commit()
    print(f"[STEP 1] User created: {created_user.email}")

    print("\n[STEP 2] Logging in...")
    login_data = {"username": email, "password": password, "grant_type": "password"}
    login_resp = await integration_client.post("/api/v1/auth/token", data=login_data)
    print(f"Login Status: {login_resp.status_code}")
    print(f"Login Body: {login_resp.text}")
    assert login_resp.status_code == 200

    token = login_resp.json()["access_token"]

    print("\n[STEP 3] Accessing /me...")
    headers = {"Authorization": f"Bearer {token}"}
    me_resp = await integration_client.get("/api/v1/auth/me", headers=headers)
    print(f"Me Status: {me_resp.status_code}")
    print(f"Me Body: {me_resp.text}")
    assert me_resp.status_code == 200
