import pytest
from fastapi import status
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_oauth2_login_success(client: AsyncClient):
    """Test successful login via real OAuth2 flow against seeded integration user."""
    response = await client.post(
        "/api/v1/auth/login",
        data={
            "username": "admin@example.com",
            "password": "AdminPass123!",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["token_type"].lower() == "bearer"
    assert data.get("access_token")


@pytest.mark.asyncio
async def test_oauth2_me_endpoint(client: AsyncClient):
    """Test GET /me endpoint with a real JWT from login."""
    login = await client.post(
        "/api/v1/auth/login",
        data={
            "username": "admin@example.com",
            "password": "AdminPass123!",
        },
    )
    assert login.status_code == status.HTTP_200_OK
    token = login.json()["access_token"]

    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["email"] == "admin@example.com"


@pytest.mark.asyncio
async def test_oauth2_validate_token(client: AsyncClient):
    """Test /validate introspection endpoint with a real token."""
    login = await client.post(
        "/api/v1/auth/login",
        data={
            "username": "admin@example.com",
            "password": "AdminPass123!",
        },
    )
    assert login.status_code == status.HTTP_200_OK
    token = login.json()["access_token"]

    response = await client.get("/api/v1/auth/validate", params={"token": token})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["active"] is True
