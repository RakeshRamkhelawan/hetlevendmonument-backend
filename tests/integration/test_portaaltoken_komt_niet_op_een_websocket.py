"""Een portaaltoken komt niet op een WebSocket (OWASP A01, ADR-039).

**Stap 0 van de brief is deze test, tegen de ECHTE WebSocket-ingangen.** Een portaaltoken
(Foundation magic link, `aud == "portal"`) heeft `sub = str(PortalUser.id)`. De WebSocket-ingangen
toetsten dat nummer tegen `users.is_active`: een portaalgebruiker met `id 5` kwam binnen zodra er
in dezelfde tenant een ACTIEVE medewerker met `id 5` was, en bleef binnen als de portaalgebruiker
geblokkeerd was. Gemeten per ingang met een medewerker en een portaalgebruiker met HETZELFDE nummer:

(a) `WebSocketAuthenticator.authenticate`,
(b) `WebSocketAuthenticator.authenticate_connected_user`,
(c) `ConnectionManager.connect`,
(d) `validate_ws_token` (focus-builder `ws/chat`),
(e) `WebSocketAuthHandler.validate_token` (focus-builder `ws/status`).

Elke ingang heeft een tegenproef: hetzelfde nummer als MEDEWERKERSTOKEN komt wel binnen (anders
bewijst een weigering niets).

Wat NIET gemeten is: wat een toegelaten portaalgebruiker op zo'n WebSocket daarna ziet; een
draaiende applicatie met scherm.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketState

from src.core.auth.jwt_handler import jwt_handler
from src.core.models.foundation_content import PortalRole, PortalUser
from src.core.models.rbac_models import User

TENANT = 1
EMAIL = "portaalws-d1@integration.test"


def _nep_websocket(token: str) -> Any:
    ws = AsyncMock()
    ws.cookies = {"access_token": token}
    ws.headers = {}
    ws.query_params = {}
    ws.scope = {"subprotocols": [], "headers": []}
    ws.client = SimpleNamespace(host="127.0.0.1")
    ws.client_state = WebSocketState.CONNECTING
    return ws


async def _authenticator(token: str) -> bool:
    from src.core.auth.websocket_auth import WebSocketAuthenticator

    return await WebSocketAuthenticator().authenticate(_nep_websocket(token)) is not None


async def _authenticator_na_accept(token: str) -> bool:
    from src.core.auth.websocket_auth import WebSocketAuthenticator

    gebruiker = await WebSocketAuthenticator().authenticate_connected_user(_nep_websocket(token))
    return gebruiker is not None


async def _kanaalmanager(token: str) -> bool:
    from src.core.websocket.manager import ConnectionManager

    verbinding = await ConnectionManager().connect(_nep_websocket(token), "kanaal", token=token)
    return verbinding is not None


async def _focus_builder_chat(token: str) -> bool:
    from src.core.api.v1.focus_builder.shared import validate_ws_token

    try:
        await validate_ws_token(token)
    except Exception:
        return False
    return True


async def _focus_builder_status(token: str) -> bool:
    from src.core.api.v1.focus_builder.ws_dependencies import WebSocketAuthHandler

    try:
        await WebSocketAuthHandler().validate_token(token)
    except Exception:
        return False
    return True


INGANGEN: list[tuple[str, Callable[[str], Awaitable[bool]]]] = [
    ("authenticator.authenticate", _authenticator),
    ("authenticator.authenticate_connected_user", _authenticator_na_accept),
    ("kanaalmanager.connect", _kanaalmanager),
    ("focus_builder.validate_ws_token", _focus_builder_chat),
    ("focus_builder.WebSocketAuthHandler", _focus_builder_status),
]
IDS = [naam for naam, _ in INGANGEN]


@pytest_asyncio.fixture
async def medewerker_id(postgres_session: AsyncSession) -> AsyncGenerator[int, None]:
    """Een ACTIEVE medewerker; zijn nummer wordt hieronder door een portaalgebruiker gebruikt."""
    gebruiker = User(
        email=EMAIL, hashed_password="x", tenant_id=TENANT, is_active=True, is_superuser=False
    )
    postgres_session.add(gebruiker)
    await postgres_session.flush()
    await postgres_session.commit()
    yield int(gebruiker.id)


async def _portaalgebruiker(sessie: AsyncSession, nummer: int, *, geblokkeerd: bool) -> None:
    sessie.add(
        PortalUser(
            id=nummer,
            tenant_id=TENANT,
            email=f"portaal-{nummer}@integration.test",
            is_blocked=geblokkeerd,
            role=PortalRole.VISITOR,
        )
    )
    await sessie.commit()


def _portaaltoken(nummer: int) -> str:
    return jwt_handler.create_access_token(
        data={
            "sub": str(nummer),
            "user_id": nummer,
            "tenant_id": TENANT,
            "aud": "portal",
            "scope": "portal_uploader",
        }
    )


def _medewerkerstoken(nummer: int) -> str:
    return jwt_handler.create_access_token(
        data={"sub": str(nummer), "user_id": nummer, "email": EMAIL, "tenant_id": TENANT}
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeTegenproef:
    """Een MEDEWERKERSTOKEN met dit nummer werkt gewoon op elke ingang."""

    @pytest.mark.parametrize("naam,ingang", INGANGEN, ids=IDS)
    async def test_een_medewerkerstoken_komt_binnen(
        self, postgres_session: AsyncSession, medewerker_id: int, naam: str, ingang: Any
    ) -> None:
        assert await ingang(_medewerkerstoken(medewerker_id)), naam


@pytest.mark.integration
@pytest.mark.asyncio
class TestPortaaltokenOpEenWebSocket:
    @pytest.mark.parametrize("naam,ingang", INGANGEN, ids=IDS)
    async def test_een_actieve_portaalgebruiker_met_het_nummer_van_een_medewerker_komt_er_niet_in(
        self, postgres_session: AsyncSession, medewerker_id: int, naam: str, ingang: Any
    ) -> None:
        await _portaalgebruiker(postgres_session, medewerker_id, geblokkeerd=False)

        toegelaten = await ingang(_portaaltoken(medewerker_id))

        assert toegelaten is False, f"{naam} liet een portaaltoken binnen"

    @pytest.mark.parametrize("naam,ingang", INGANGEN, ids=IDS)
    async def test_een_geblokkeerde_portaalgebruiker_komt_er_niet_in(
        self, postgres_session: AsyncSession, medewerker_id: int, naam: str, ingang: Any
    ) -> None:
        await _portaalgebruiker(postgres_session, medewerker_id, geblokkeerd=True)

        toegelaten = await ingang(_portaaltoken(medewerker_id))

        assert toegelaten is False, f"{naam} liet een geblokkeerd portaaltoken binnen"

    @pytest.mark.parametrize("naam,ingang", INGANGEN, ids=IDS)
    async def test_een_portaaltoken_zonder_medewerker_met_dat_nummer_komt_er_ook_niet_in(
        self, postgres_session: AsyncSession, naam: str, ingang: Any
    ) -> None:
        await _portaalgebruiker(postgres_session, 880101, geblokkeerd=False)

        toegelaten = await ingang(_portaaltoken(880101))

        assert toegelaten is False, f"{naam} liet een portaaltoken binnen"


@pytest.mark.integration
@pytest.mark.asyncio
class TestNazorg:
    """Nazorg uit dezelfde Gate 2-review (security-reviewer, 2026-10-13)."""

    async def test_een_sub_van_twaalf_cijfers_is_geen_actief_account_en_geen_storing(
        self,
    ) -> None:
        from src.core.auth.account_status import AccountStatus, haal_account_status

        status = await haal_account_status("123456789012", TENANT)

        assert status is AccountStatus.UITGESCHAKELD

    async def test_een_sub_van_twaalf_cijfers_geeft_401_en_geen_503_in_de_middleware(
        self, integration_client: Any
    ) -> None:
        token = jwt_handler.create_access_token(
            data={"sub": "123456789012", "tenant_id": TENANT, "email": EMAIL}
        )

        antwoord = await integration_client.get(
            "/api/v1/search/hybrid",
            params={"query": "x"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert antwoord.status_code == 401, f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"

    @pytest.mark.parametrize("tenant_claim", [True, 1.9, "1.5"], ids=["bool", "float", "tekst"])
    async def test_een_vreemde_tenantclaim_komt_niet_op_de_focus_builder_websocket(
        self, postgres_session: AsyncSession, medewerker_id: int, tenant_claim: Any
    ) -> None:
        token = jwt_handler.create_access_token(
            data={"sub": str(medewerker_id), "email": EMAIL, "tenant_id": tenant_claim}
        )

        assert await _focus_builder_status(token) is False

    async def test_een_portaal_sub_van_twaalf_cijfers_is_geen_actief_account_en_geen_storing(
        self,
    ) -> None:
        from src.core.auth.account_status import AccountStatus, haal_account_status

        status = await haal_account_status("123456789012", TENANT, portal=True)

        assert status is AccountStatus.UITGESCHAKELD
