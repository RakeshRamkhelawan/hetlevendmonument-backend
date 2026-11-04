"""
Test: OP-188 -- token moet na POST /auth/logout worden geweigerd.

Gerepareerd 2026-09-30: logout_endpoint() roept nu oauth2_service.revoke_token() aan,
die naar de PostgreSQL-tabel TokenBlacklist schrijft. is_jti_revoked() leest uit
dezelfde tabel. Een bron van waarheid.

Wat het defect was (gemeten 2026-09-30, commit 4baee486):

  logout_endpoint() schreef de jti naar Redis ("token_blacklist:{jti}").
  is_jti_revoked() (src/core/auth/oauth2_service.py:367-370) las alleen PostgreSQL.
  De twee winkels waren ontkoppeld; uitloggen had geen effect op de auth-controle.

Waarom het gemist was:

  OP-188 en OP-260 waren "gesloten" op basis van een integratietest die /revoke
  gebruikte -- niet /logout. De frontend roept /logout aan (AuthContext.tsx:106).
  Het register klopte over wat gemeten was; het gemetene was niet wat de klant doet.

Derde mechanisme (verify_token_with_blacklist): dood hout.
  git grep -n "verify_token_with_blacklist" -- src/
  -> src/core/auth/jwt_handler.py:309: async def verify_token_with_blacklist(
  Alleen de definitie. Nul productie-aanroepers. Geen actief mechanisme.
"""

from __future__ import annotations

import os
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

from src.core.api.auth.router_token import logout_endpoint
from src.core.api.auth.schemas import UserResponse


def _make_jwt(jti: str, exp: int = 9_999_999_999) -> str:
    """Maak een gesigneerde JWT met de opgegeven jti."""
    from jose import jwt as _jose_jwt

    secret = os.environ.get(
        "JWT_SECRET_KEY",
        "pytest-jwt-secret-key-for-local-hooks-0123456789",
    )
    return _jose_jwt.encode(
        {
            "sub": "1",
            "email": "test@example.com",
            "tenant_id": 1,
            "jti": jti,
            "exp": exp,
        },
        secret,
        algorithm="HS256",
    )


def _make_request(token: str) -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/auth/logout",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "client": ("127.0.0.1", 8080),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_geldig_niet_uitgelogd_token_wordt_nog_toegestaan() -> None:
    """
    Een token dat NIET is uitgelogd moet door is_jti_revoked() als geldig worden gezien.

    Dit is de tegenkant van test_token_wordt_geweigerd_na_logout: zonder dit bewijs
    is 'weiger alles na logout' een geldige implementatie en kan niemand meer inloggen.

    GROEN voor EN na de fix: toets dat is_jti_revoked() een leeg PostgreSQL-resultaat
    als False interpreteert.

    Mutatiebewijs:
    - Zet scalar_one_or_none.return_value op een niet-None waarde: de test wordt rood.
    """
    jti = str(uuid.uuid4())

    mock_db = AsyncMock()
    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_db_result)

    from src.core.auth.oauth2_service import oauth2_service

    is_revoked = await oauth2_service.is_jti_revoked(jti, mock_db)

    assert is_revoked is False, (
        "Een token dat niet is uitgelogd moet als geldig worden gezien. "
        "Faalt dit na de fix: dan weigert is_jti_revoked() alles -- ook geldige tokens."
    )


@pytest.mark.asyncio
async def test_token_wordt_geweigerd_na_logout() -> None:
    """
    Na POST /auth/logout moet is_jti_revoked() True teruggeven voor het uitgelogde token.

    Reparatie OP-188 (2026-09-30): logout_endpoint() roept nu oauth2_service.revoke_token()
    aan, die naar PostgreSQL-tabel TokenBlacklist schrijft. De eerdere Redis-schrijfactie
    is vervangen -- twee stores waren ontkoppeld en dat was het defect.

    Mutatiebewijs (twee kanten):
    - Verwijder de revoke_token()-aanroep uit logout_endpoint: mock_revoke wordt niet
      aangeroepen en de eerste assert mislukt.
    - Zet mock_db2_result.scalar_one_or_none op None: is_jti_revoked() geeft False
      en de tweede assert mislukt.
    """
    jti = str(uuid.uuid4())
    token = _make_jwt(jti)
    req = _make_request(token)
    res = Response()
    user = UserResponse(id=1, email="test@example.com", tenant_id=1, roles=["user"])
    mock_db = AsyncMock()

    from src.core.auth.oauth2_service import oauth2_service

    # Stap 1: voer de uitlog uit -- revoke_token() moet worden aangeroepen.
    with patch.object(
        oauth2_service, "revoke_token", new_callable=AsyncMock, return_value=True
    ) as mock_revoke:
        result = await logout_endpoint(
            request=req,
            response=res,
            current_user=user,
            db=mock_db,
            _csrf=None,
        )

    assert result["message"] == "Logged out successfully"
    mock_revoke.assert_awaited_once()
    assert mock_revoke.await_args is not None
    revoke_args = mock_revoke.await_args[0]
    assert revoke_args[0] == token, (
        "logout_endpoint() moet het JWT-token doorgeven aan revoke_token()"
    )
    assert revoke_args[1] == user.id, (
        "logout_endpoint() moet current_user.id doorgeven aan revoke_token()"
    )

    # Stap 2: na de uitlog staat het token in PostgreSQL-tabel TokenBlacklist.
    # Verificatie: is_jti_revoked() geeft True als de tabel een rij heeft.
    mock_db2 = AsyncMock()
    mock_db2_result = MagicMock()
    mock_db2_result.scalar_one_or_none.return_value = MagicMock()  # Rij gevonden
    mock_db2.execute = AsyncMock(return_value=mock_db2_result)

    is_revoked = await oauth2_service.is_jti_revoked(jti, mock_db2)

    assert is_revoked is True, (
        "is_jti_revoked() moet True teruggeven als het token in de "
        "PostgreSQL-tabel TokenBlacklist staat. "
        "Faalt dit: controleer of de TokenBlacklist-query correct is."
    )
