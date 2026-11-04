"""Een portaaltoken krijgt nooit een medewerkersidentiteit (OWASP A01, ADR-039).

Gate 2 (security-reviewer, 2026-10-13): `get_current_user_ws` en `get_current_user` lopen via
`_get_user_from_token`. Die zocht een portaaltoken (`aud == "portal"`, `sub` = PortalUser.id) op in
`users`: via de e-mailclaim (`get_user_by_email`) of, zonder e-mail, via `sub` als gebruikersnummer
(`get_user_by_id`, dat de tenant uit de GEVONDEN rij haalt en niet uit het token). Een portaaltoken
werd zo een medewerker, ook van een andere tenant. Gemeten via:

(a) `get_current_user_ws` (de WebSocket `/ws/copilot/signals`), direct aangeroepen,
(b) `GET /api/v1/auth/me` (`get_current_user`), met het e-mailadres van een medewerker in het token,
(c) `GET /api/v1/auth/me` zonder e-mailclaim maar met een botsend nummer (het `get_user_by_id`-pad),
(d) `get_current_user_id` (de keten achter `require_permission`), direct aangeroepen.

Elk pad heeft een tegenproef: hetzelfde als MEDEWERKERSTOKEN werkt gewoon.

Wat NIET gemeten is: een portaalroute met `require_portal_user` (die gebruikt `get_current_user` niet:
`git grep get_current_user src/core/api/v1/foundation` geeft niets) en de WebSocket
`/ws/{canvas_id}` (verwacht 401 omdat `request` daar `None` is; niet gedraaid).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.jwt_handler import jwt_handler
from src.core.models.foundation_content import PortalRole, PortalUser
from src.core.models.rbac_models import User

TENANT = 1
EMAIL = "portaal-is-geen-medewerker@integration.test"
ME = "/api/v1/auth/me"


def _nep_websocket(token: str) -> Any:
    ws = AsyncMock()
    ws.cookies = {"access_token": token}
    ws.headers = {}
    ws.query_params = {}
    ws.client = SimpleNamespace(host="127.0.0.1")
    return ws


@pytest_asyncio.fixture
async def medewerker_id(postgres_session: AsyncSession) -> AsyncGenerator[int, None]:
    gebruiker = User(
        email=EMAIL, hashed_password="x", tenant_id=TENANT, is_active=True, is_superuser=False
    )
    postgres_session.add(gebruiker)
    await postgres_session.flush()
    await postgres_session.commit()
    yield int(gebruiker.id)


async def _portaalgebruiker(sessie: AsyncSession, nummer: int, email: str) -> None:
    sessie.add(
        PortalUser(
            id=nummer, tenant_id=TENANT, email=email, is_blocked=False, role=PortalRole.VISITOR
        )
    )
    await sessie.commit()


def _portaaltoken(nummer: int, *, email: str | None) -> str:
    data: dict[str, Any] = {
        "sub": str(nummer),
        "user_id": nummer,
        "tenant_id": TENANT,
        "aud": "portal",
        "scope": "portal_uploader",
    }
    if email is not None:
        data["email"] = email
    return jwt_handler.create_access_token(data=data)


def _medewerkerstoken(nummer: int) -> str:
    return jwt_handler.create_access_token(
        data={"sub": str(nummer), "user_id": nummer, "email": EMAIL, "tenant_id": TENANT}
    )


def _koppen(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeTegenproef:
    async def test_een_medewerkerstoken_werkt_op_get_current_user(
        self, integration_client: Any, medewerker_id: int
    ) -> None:
        antwoord = await integration_client.get(
            ME, headers=_koppen(_medewerkerstoken(medewerker_id))
        )

        assert antwoord.status_code == 200, antwoord.text

    async def test_een_medewerkerstoken_werkt_op_de_websocketafhankelijkheid(
        self, postgres_session: AsyncSession, medewerker_id: int
    ) -> None:
        from src.core.auth.dependencies import get_current_user_ws

        user = await get_current_user_ws(
            _nep_websocket(_medewerkerstoken(medewerker_id)), db=postgres_session
        )

        assert user.id == medewerker_id

    async def test_een_medewerkerstoken_werkt_op_get_current_user_id(
        self, postgres_session: AsyncSession, medewerker_id: int
    ) -> None:
        from src.core.auth.dependencies import get_current_user_id

        uitkomst = await get_current_user_id(
            token=_medewerkerstoken(medewerker_id), session=postgres_session
        )

        assert uitkomst == medewerker_id


@pytest.mark.integration
@pytest.mark.asyncio
class TestPortaaltokenIsGeenMedewerker:
    async def test_get_current_user_ws_weigert_een_portaaltoken_met_het_nummer_van_een_medewerker(
        self, postgres_session: AsyncSession, medewerker_id: int
    ) -> None:
        from src.core.auth.dependencies import get_current_user_ws

        await _portaalgebruiker(postgres_session, medewerker_id, "ander@integration.test")

        with pytest.raises(HTTPException) as fout:
            await get_current_user_ws(
                _nep_websocket(_portaaltoken(medewerker_id, email=None)), db=postgres_session
            )

        assert fout.value.status_code == 401

    async def test_get_current_user_weigert_een_portaaltoken_met_het_emailadres_van_een_medewerker(
        self, integration_client: Any, postgres_session: AsyncSession, medewerker_id: int
    ) -> None:
        await _portaalgebruiker(postgres_session, 880401, EMAIL)

        antwoord = await integration_client.get(
            ME, headers=_koppen(_portaaltoken(880401, email=EMAIL))
        )

        assert antwoord.status_code == 401, f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"

    async def test_get_current_user_weigert_een_portaaltoken_zonder_email_met_het_nummer_van_een_medewerker(
        self, integration_client: Any, postgres_session: AsyncSession, medewerker_id: int
    ) -> None:
        await _portaalgebruiker(postgres_session, medewerker_id, "ander2@integration.test")

        antwoord = await integration_client.get(
            ME, headers=_koppen(_portaaltoken(medewerker_id, email=None))
        )

        assert antwoord.status_code == 401, f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"

    @pytest.mark.parametrize("variant", ["user_id", "sub_numeriek", "sub_email"])
    async def test_get_current_user_id_weigert_een_portaaltoken(
        self, postgres_session: AsyncSession, medewerker_id: int, variant: str
    ) -> None:
        from src.core.auth.dependencies import get_current_user_id

        claims: dict[str, Any] = {"tenant_id": TENANT, "aud": "portal", "scope": "portal_uploader"}
        if variant == "user_id":
            claims.update({"sub": str(medewerker_id), "user_id": medewerker_id})
        elif variant == "sub_numeriek":
            claims.update({"sub": str(medewerker_id)})
        else:
            claims.update({"sub": EMAIL})
        token = jwt_handler.create_access_token(data=claims)

        with pytest.raises(HTTPException) as fout:
            await get_current_user_id(token=token, session=postgres_session)

        assert fout.value.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
class TestVerifyTokenEnValidate:
    """Gate 2 ronde 2 (security-reviewer): `/api/v1/auth/verify-token` en `/api/v1/auth/validate`
    deden `int(sub)` als `User.id` en gaven de identiteit van de medewerker met dat nummer terug
    (`tenantId` en `userId` voor de sync-server, resp. `username` = e-mailadres)."""

    async def test_verify_token_weigert_een_portaaltoken_met_het_nummer_van_een_medewerker(
        self, integration_client: Any, postgres_session: AsyncSession, medewerker_id: int
    ) -> None:
        await _portaalgebruiker(postgres_session, medewerker_id, "ander3@integration.test")
        token = _portaaltoken(medewerker_id, email=None)

        antwoord = await integration_client.post(
            "/api/v1/auth/verify-token", json={"token": token}, headers=_koppen(token)
        )

        assert antwoord.status_code == 401, f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"

    async def test_validate_weigert_een_portaaltoken_met_het_nummer_van_een_medewerker(
        self, integration_client: Any, postgres_session: AsyncSession, medewerker_id: int
    ) -> None:
        await _portaalgebruiker(postgres_session, medewerker_id, "ander4@integration.test")
        token = _portaaltoken(medewerker_id, email=None)

        antwoord = await integration_client.get(
            "/api/v1/auth/validate", params={"token": token}, headers=_koppen(token)
        )

        assert antwoord.status_code == 401, f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"

    async def test_verify_token_geeft_een_medewerker_zijn_eigen_identiteit(
        self, integration_client: Any, medewerker_id: int
    ) -> None:
        token = _medewerkerstoken(medewerker_id)

        antwoord = await integration_client.post(
            "/api/v1/auth/verify-token", json={"token": token}, headers=_koppen(token)
        )

        assert (antwoord.status_code, antwoord.json().get("userId")) == (200, str(medewerker_id))

    async def test_validate_geeft_een_medewerker_zijn_eigen_gegevens(
        self, integration_client: Any, medewerker_id: int
    ) -> None:
        token = _medewerkerstoken(medewerker_id)

        antwoord = await integration_client.get(
            "/api/v1/auth/validate", params={"token": token}, headers=_koppen(token)
        )

        assert (antwoord.status_code, antwoord.json().get("username")) == (200, EMAIL)
