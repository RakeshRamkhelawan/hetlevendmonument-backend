"""
NEO Audit Fix: Sprint 7 - JWT tokens MOETEN een jti claim bevatten

SECURITY ISSUE: Tokens zonder jti (JWT ID) kunnen niet individueel worden gerevoked
SOLUTION: Voeg unieke jti claim toe aan alle tokens

File affected:
- src/core/auth/jwt_handler.py
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest


class TestJWTContainsJTI:
    """Alle tokens moeten een uniek jti (JWT ID) bevatten voor individuele revocatie."""

    def test_access_token_has_jti(self):
        """CRITICAL: Token bevat jti claim."""
        from src.core.auth.jwt_handler import JWTHandler

        handler = JWTHandler()
        token = handler.create_access_token(data={"sub": "test@example.com"})

        # Decode zonder verificatie om claim te inspecteren
        payload = jwt.decode(token, options={"verify_signature": False})

        assert "jti" in payload, "Access token MOET een jti claim hebben voor token revocatie"
        assert payload["jti"] is not None, "jti mag niet None zijn"
        assert len(payload["jti"]) > 0, "jti mag niet leeg zijn"

    def test_jti_is_unique_per_token(self):
        """CRITICAL: Twee tokens hebben verschillende jti's."""
        from src.core.auth.jwt_handler import JWTHandler

        handler = JWTHandler()
        token1 = handler.create_access_token(data={"sub": "user1@example.com"})
        token2 = handler.create_access_token(data={"sub": "user1@example.com"})

        payload1 = jwt.decode(token1, options={"verify_signature": False})
        payload2 = jwt.decode(token2, options={"verify_signature": False})

        assert (
            payload1["jti"] != payload2["jti"]
        ), "Elke token MOET een uniek jti hebben, zelfs voor dezelfde gebruiker"

    def test_jti_is_valid_uuid(self):
        """HAPPY: jti is een geldig UUID formaat."""
        from src.core.auth.jwt_handler import JWTHandler

        handler = JWTHandler()
        token = handler.create_access_token(data={"sub": "test@example.com"})

        payload = jwt.decode(token, options={"verify_signature": False})

        # Moet kunnen worden geparsed als UUID
        try:
            parsed_uuid = uuid.UUID(payload["jti"])
            assert str(parsed_uuid) == payload["jti"], "jti moet een geldige UUID string zijn"
        except ValueError as e:
            pytest.fail(f"jti is geen geldige UUID: {payload['jti']} - {e}")

    def test_existing_jti_in_data_is_preserved(self):
        """HAPPY: Als caller al jti meegeeft, wordt die behouden (geen overschrijven)."""
        from src.core.auth.jwt_handler import JWTHandler

        handler = JWTHandler()
        custom_jti = "custom-jti-123"
        token = handler.create_access_token(data={"sub": "test@example.com", "jti": custom_jti})

        payload = jwt.decode(token, options={"verify_signature": False})

        assert (
            payload["jti"] == custom_jti
        ), "Als caller een jti meegeeft, moet die worden behouden (niet overschrijven)"

    def test_jti_persists_through_token_lifecycle(self):
        """HAPPY: jti blijft consistent bij decode → encode."""
        from src.core.auth.jwt_handler import JWTHandler

        handler = JWTHandler()
        original_data = {"sub": "test@example.com", "role": "admin"}
        token = handler.create_access_token(data=original_data)

        # Decode met volledige verificatie
        payload = jwt.decode(token, handler.secret_key, algorithms=[handler.algorithm])

        assert "jti" in payload, "jti moet aanwezig zijn in geverifieerde payload"
        assert isinstance(payload["jti"], str), "jti moet een string zijn"
