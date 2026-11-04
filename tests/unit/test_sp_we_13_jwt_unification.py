"""Tests voor SP-WE-13: JWT verificatie unificatie (CG-007).

SecurityMiddleware moet dezelfde claims afdwingen als jwt_handler:
sub, tenant_id, exp, HS256-only. security_manager.verify_token() deed dit niet.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from jose import jwt as jose_jwt

from src.core.auth.jwt_handler import JWTHandler

_SECRET = "test-secret-key-minimum-32-characters"
_ALGO = "HS256"


def _make_token(payload: dict, secret: str = _SECRET, typ: str | None = "at+jwt") -> str:
    """Munt een token BUITEN de fabriek om, zoals deze toets altijd al deed.

    Sinds OP-182 draagt elk token dat de fabriek uitgeeft het soort in de JOSE-header
    `typ`, en weigert verify_token een token zonder die stempel. Een handgemaakt token
    moet die stempel dus ook zetten, anders toetst dit bestand niet meer wat het wil
    toetsen (de controle op `sub` en `tenant_id`) maar alleen nog de soortcontrole.

    `typ=None` levert bewust een token ZONDER stempel op, voor de toets die vastlegt
    dat zo'n token wordt geweigerd.
    """
    kop = {"typ": typ} if typ is not None else {"typ": None}
    return jose_jwt.encode(payload, secret, algorithm=_ALGO, headers=kop)


def _base_payload(extra: dict | None = None) -> dict:
    p: dict = {
        "sub": "user@test.com",
        "tenant_id": 42,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    if extra:
        p.update(extra)
    return p


def _handler() -> JWTHandler:
    h = JWTHandler.__new__(JWTHandler)
    h.algorithm = _ALGO
    h.secret_key = _SECRET
    return h


@pytest.mark.unit
@pytest.mark.security
class TestCG007JWTVerificationUnification:

    def test_token_missing_sub_rejected_by_jwt_handler(self) -> None:
        token = _make_token(
            {"tenant_id": 42, "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
        )
        assert _handler().verify_token(token) is None

    def test_token_missing_tenant_id_rejected_by_jwt_handler(self) -> None:
        token = _make_token(
            {"sub": "user@test.com", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
        )
        assert _handler().verify_token(token) is None

    def test_security_middleware_uses_jwt_handler_not_security_manager(self) -> None:
        from src.core.security.security_middleware import SecurityMiddleware
        source = inspect.getsource(SecurityMiddleware._check_authentication)
        assert "security_manager.verify_token" not in source

    def test_security_middleware_extract_user_uses_jwt_handler(self) -> None:
        from src.core.security.security_middleware import SecurityMiddleware
        source = inspect.getsource(SecurityMiddleware._extract_user_id)
        assert "security_manager.verify_token" not in source

    def test_token_with_wrong_secret_rejected(self) -> None:
        rogue = _make_token(_base_payload(), secret="different-secret-32-chars-minimum!")
        assert _handler().verify_token(rogue) is None

    def test_non_string_token_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="Token must be a string"):
            _handler().verify_token(None)  # type: ignore[arg-type]

    def test_security_middleware_returns_invalid_for_bad_token(self) -> None:
        from src.core.security.security_middleware import SecurityMiddleware
        from starlette.applications import Starlette
        from src.core.security.security_manager import SecurityLevel
        app = Starlette()
        middleware = SecurityMiddleware(app, enable_security=True)
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer not.a.real.jwt"}
        mock_request.cookies = {}
        result = middleware._check_authentication(mock_request, SecurityLevel.AUTHENTICATED)
        assert result["valid"] is False

    def test_een_token_zonder_soortstempel_wordt_geweigerd(self) -> None:
        """OP-182: een token dat buiten de fabriek om is gemunt, draagt geen soort en
        is daarmee ongeldig. Dat is het gedrag dat het gat dicht."""
        token = _make_token(_base_payload(), typ=None)
        assert _handler().verify_token(token) is None

    def test_valid_token_with_all_claims_accepted(self) -> None:
        token = _make_token(_base_payload())
        result = _handler().verify_token(token)
        assert result is not None
        assert result["sub"] == "user@test.com"
        assert result["tenant_id"] == 42
