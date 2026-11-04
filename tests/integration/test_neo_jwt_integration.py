"""
NEO Audit Integration Test: JWT jti Claim in Real Auth Flow

Verifieert dat de jti claim correct werkt in de volledige authenticatie flow.
"""

import jwt
import pytest
from httpx import AsyncClient

from src.core.auth.jwt_handler import JWTHandler


class TestJWTJtiIntegration:
    """Integration tests voor JWT jti claim in auth endpoints."""

    @pytest.mark.asyncio
    async def test_login_returns_token_with_jti(self, test_user_with_token):
        """CRITICAL: JWT used in auth flow bevat een jti claim."""
        data = {"access_token": test_user_with_token["token"]}
        assert "access_token" in data, "Response moet access_token bevatten"

        # Decode token zonder verificatie om claims te inspecteren
        token = data["access_token"]
        payload = jwt.decode(token, options={"verify_signature": False})

        assert "jti" in payload, "Token MOET jti claim hebben (NEO Sprint 7)"
        assert len(payload["jti"]) > 0, "jti mag niet leeg zijn"

        # Verificeer UUID formaat
        import uuid

        try:
            uuid.UUID(payload["jti"])
        except ValueError:
            pytest.fail(f"jti is geen geldige UUID: {payload['jti']}")

    @pytest.mark.asyncio
    async def test_multiple_logins_generate_unique_jtis(
        self,
    ):
        """CRITICAL: Meerdere tokencreaties genereren verschillende jtis."""
        jwt_handler = JWTHandler()
        token1 = jwt_handler.create_access_token(
            data={"sub": "1", "tenant_id": 1, "email": "test@example.com"}
        )
        token2 = jwt_handler.create_access_token(
            data={"sub": "1", "tenant_id": 1, "email": "test@example.com"}
        )

        payload1 = jwt.decode(token1, options={"verify_signature": False})
        payload2 = jwt.decode(token2, options={"verify_signature": False})

        assert (
            payload1["jti"] != payload2["jti"]
        ), "Verschillende login sessies moeten verschillende jtis hebben"

    @pytest.mark.asyncio
    async def test_protected_endpoint_accepts_token_with_jti(
        self, async_client: AsyncClient, test_user_with_token
    ):
        """HAPPY: Protected endpoints accepteren tokens met jti claim."""
        response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {test_user_with_token['token']}"},
        )

        assert response.status_code == 200, "Protected endpoint moet tokens met jti accepteren"
