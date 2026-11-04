"""Integration tests for JWT behavior aligned with current auth middleware contracts."""

from datetime import timedelta
from typing import Dict

import jwt
import pytest
from httpx import AsyncClient

from src.core.auth.jwt_handler import jwt_handler


def _version_payload() -> dict:
    return {
        "workflow_id": "jwt_probe",
        "name": "JWT Probe",
        "workflow": {"nodes": [], "edges": []},
        "change_description": "probe",
        "tags": ["probe"],
    }


@pytest.mark.integration
@pytest.mark.asyncio
class TestJWTValidation:
    """Current-contract JWT tests: middleware validation + handler semantics."""

    async def test_valid_jwt_token_accepted(
        self, async_client: AsyncClient, admin_user_with_token: Dict[str, str]
    ) -> None:
        headers = {"Authorization": f"Bearer {admin_user_with_token['token']}"}
        response = await async_client.post(
            "/api/v1/workflows/jwt_probe/versions",
            json=_version_payload(),
            headers=headers,
        )
        assert response.status_code != 401

    async def test_missing_token_rejected(self, async_client: AsyncClient) -> None:
        response = await async_client.post(
            "/api/v1/workflows/jwt_probe/versions", json=_version_payload()
        )
        assert response.status_code == 401

    async def test_malformed_token_rejected(self, async_client: AsyncClient) -> None:
        malformed = ["Bearer", "Bearer ", "notavalidtoken", "Bearer invalid.token"]
        for header in malformed:
            response = await async_client.post(
                "/api/v1/workflows/jwt_probe/versions",
                json=_version_payload(),
                headers={"Authorization": header},
            )
            assert response.status_code == 401

    async def test_expired_token_rejected(self, async_client: AsyncClient) -> None:
        expired = jwt_handler.create_access_token(
            data={"sub": "1", "tenant_id": 1, "email": "x@y.com"},
            expires_delta=timedelta(seconds=-60),
        )
        response = await async_client.post(
            "/api/v1/workflows/jwt_probe/versions",
            json=_version_payload(),
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert response.status_code == 401

    async def test_invalid_signature_rejected(self, async_client: AsyncClient) -> None:
        token = jwt.encode(
            {"sub": "1", "tenant_id": 1, "email": "x@y.com"},
            "wrong_secret",
            algorithm="HS256",
        )
        response = await async_client.post(
            "/api/v1/workflows/jwt_probe/versions",
            json=_version_payload(),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    async def test_verify_token_requires_sub_and_tenant(self) -> None:
        token_without_tenant = jwt_handler.create_access_token(data={"sub": "1"})
        token_without_sub = jwt_handler.create_access_token(data={"tenant_id": 1})
        assert jwt_handler.verify_token(token_without_tenant) is None
        assert jwt_handler.verify_token(token_without_sub) is None

    async def test_multiple_tokens_same_user_are_valid(
        self, async_client: AsyncClient, admin_user_with_token: Dict[str, str]
    ) -> None:
        token1 = admin_user_with_token["token"]
        token2 = jwt_handler.create_access_token(
            data={
                "sub": "1",
                "user_id": 1,
                "tenant_id": 1,
                "email": admin_user_with_token["email"],
                "roles": ["admin"],
                "scopes": ["admin:*", "*:*"],
            }
        )
        for token in (token1, token2):
            response = await async_client.post(
                "/api/v1/workflows/jwt_probe/versions",
                json=_version_payload(),
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code != 401
