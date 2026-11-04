"""Een uitgeschakelde gebruiker kan met een oud token niets meer (OWASP A01, ADR-039).

**Stap 0 van de brief is deze test, tegen de ECHTE tokenafhandeling.** Er is NIETS overschreven
van `get_current_user`, `get_current_user_ws` of de refresh-route: alleen de databasesessie wijst
naar de testdatabase. Een echte gebruiker met een echt token, daarna `users.is_active = false`
(precies wat de deactiveer-route, de AVG-wissing en een beheerder zetten: dezelfde kolom), daarna
met HETZELFDE token:

(a) een leesroute (`GET /api/v1/receivables`),
(b) een schrijfroute (`POST /api/v1/receivables`),
(c) de WebSocket-ingangen: `get_current_user_ws` (copilot) en `WebSocketAuthenticator` (de
    tweede implementatie, zonder databasetoegang),
(d) een token vernieuwen (`POST /api/v1/auth/refresh`).

Elk pad heeft een tegenproef: dezelfde gebruiker, ACTIEF, werkt gewoon (anders bewijst een 401
niets). En: weer aanzetten laat hetzelfde token weer werken (bewuste keuze, de token bevat geen
status).

Wat NIET gemeten is: een draaiende applicatie met scherm; het uitzetten via de deactiveer-route of
de DSAR-service zelf (die zetten dezelfde kolom; hier wordt de kolom gezet).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.jwt_handler import jwt_handler
from src.core.models.rbac_models import Role, User, user_roles
from src.core.services.rbac_service import RBACService

TENANT = 1
EMAIL = "uitgezet-d1@integration.test"
RECEIVABLES = "/api/v1/receivables"
REFRESH = "/api/v1/auth/refresh"


async def _maak_gebruiker(sessie: AsyncSession, *, superuser: bool = False) -> int:
    await RBACService(sessie).ensure_default_roles(TENANT)
    gebruiker = User(
        email=EMAIL,
        hashed_password="x",
        tenant_id=TENANT,
        is_active=True,
        is_superuser=superuser,
    )
    sessie.add(gebruiker)
    await sessie.flush()
    rol = (
        await sessie.execute(
            select(Role).where(Role.name == "debiteuren", Role.tenant_id == TENANT)
        )
    ).scalar_one()
    await sessie.execute(
        user_roles.insert().values(user_id=gebruiker.id, role_id=rol.id, tenant_id=TENANT)
    )
    await sessie.commit()
    return int(gebruiker.id)


async def _zet_actief(sessie: AsyncSession, user_id: int, actief: bool) -> None:
    await sessie.execute(
        text("UPDATE users SET is_active = :a WHERE id = :u"), {"a": actief, "u": user_id}
    )
    await sessie.commit()


def _tokens(user_id: int) -> tuple[str, str]:
    data: dict[str, Any] = {
        "sub": str(user_id),
        "user_id": user_id,
        "email": EMAIL,
        "tenant_id": TENANT,
    }
    return jwt_handler.create_access_token(data=data), jwt_handler.create_refresh_token(data=data)


def _nep_websocket(token: str) -> Any:
    """Genoeg van een WebSocket voor de twee ingangen: cookies, headers en een sluit-methode."""
    ws = AsyncMock()
    ws.cookies = {"access_token": token}
    ws.headers = {}
    ws.query_params = {}
    ws.client = SimpleNamespace(host="127.0.0.1")
    return ws


@pytest_asyncio.fixture
async def gebruiker(postgres_session: AsyncSession) -> AsyncGenerator[dict[str, Any], None]:
    user_id = await _maak_gebruiker(postgres_session)
    access, refresh = _tokens(user_id)
    yield {"id": user_id, "access": access, "refresh": refresh}


@pytest.fixture
def csrf_uit(integration_app: Any) -> Any:
    """Alleen de CSRF-controle (Redis-gebonden, eigen tests) staat uit; de authenticatie NIET."""
    from src.core.api.auth.dependencies import validate_csrf_token

    integration_app.dependency_overrides[validate_csrf_token] = lambda: None
    yield
    integration_app.dependency_overrides.pop(validate_csrf_token, None)


def _koppen(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


NIEUWE_FACTUUR = {
    "customer_name": "Uitgezet BV",
    "customer_email": "uitgezet@example.com",
    "invoice_number": "UIT-1",
    "amount": "10.00",
    "currency": "EUR",
    "due_date": "2026-09-01",
}


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeTegenproef:
    """Een ACTIEVE gebruiker werkt gewoon: anders bewijst een 401 hieronder niets."""

    async def test_een_actieve_gebruiker_mag_lezen(
        self, integration_client: Any, gebruiker: dict[str, Any]
    ) -> None:
        antwoord = await integration_client.get(RECEIVABLES, headers=_koppen(gebruiker["access"]))

        assert antwoord.status_code == 200, antwoord.text

    async def test_een_actieve_gebruiker_mag_schrijven(
        self, csrf_uit: Any, integration_client: Any, gebruiker: dict[str, Any]
    ) -> None:
        antwoord = await integration_client.post(
            RECEIVABLES, json=NIEUWE_FACTUUR, headers=_koppen(gebruiker["access"])
        )

        assert antwoord.status_code in (200, 201), antwoord.text

    async def test_een_actieve_gebruiker_mag_verversen(
        self, integration_client: Any, gebruiker: dict[str, Any]
    ) -> None:
        antwoord = await integration_client.post(
            REFRESH, json={"refresh_token": gebruiker["refresh"]}
        )

        assert antwoord.status_code == 200, antwoord.text

    async def test_een_actieve_gebruiker_mag_de_websocket_gebruiken(
        self, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        from src.core.auth.dependencies import get_current_user_ws

        user = await get_current_user_ws(_nep_websocket(gebruiker["access"]), db=postgres_session)

        assert user.id == gebruiker["id"]

    async def test_een_actieve_gebruiker_komt_door_de_tweede_websocketingang(
        self, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        from src.core.auth.websocket_auth import WebSocketAuthenticator

        user = await WebSocketAuthenticator().authenticate(_nep_websocket(gebruiker["access"]))

        assert user is not None


@pytest.mark.integration
@pytest.mark.asyncio
class TestUitgezetMetEenOudToken:
    async def test_lezen_geeft_401_account_disabled(
        self, integration_client: Any, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        await _zet_actief(postgres_session, gebruiker["id"], False)

        antwoord = await integration_client.get(RECEIVABLES, headers=_koppen(gebruiker["access"]))

        assert (antwoord.status_code, "ACCOUNT_DISABLED" in antwoord.text) == (401, True), (
            f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"
        )

    async def test_schrijven_geeft_401_account_disabled(
        self, csrf_uit: Any, integration_client: Any, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        await _zet_actief(postgres_session, gebruiker["id"], False)

        antwoord = await integration_client.post(
            RECEIVABLES, json=NIEUWE_FACTUUR, headers=_koppen(gebruiker["access"])
        )

        assert (antwoord.status_code, "ACCOUNT_DISABLED" in antwoord.text) == (401, True), (
            f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"
        )

    async def test_schrijven_maakt_geen_rij_aan(
        self, csrf_uit: Any, integration_client: Any, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        await _zet_actief(postgres_session, gebruiker["id"], False)

        await integration_client.post(
            RECEIVABLES, json=NIEUWE_FACTUUR, headers=_koppen(gebruiker["access"])
        )

        aantal = (
            await postgres_session.execute(
                text("SELECT count(*) FROM receivables WHERE invoice_number = 'UIT-1'")
            )
        ).scalar_one()
        assert aantal == 0

    async def test_verversen_wordt_geweigerd(
        self, integration_client: Any, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        await _zet_actief(postgres_session, gebruiker["id"], False)

        antwoord = await integration_client.post(
            REFRESH, json={"refresh_token": gebruiker["refresh"]}
        )

        assert antwoord.status_code == 401, f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"

    async def test_de_websocket_get_current_user_ws_wordt_geweigerd(
        self, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        from src.core.auth.dependencies import get_current_user_ws

        await _zet_actief(postgres_session, gebruiker["id"], False)

        with pytest.raises(HTTPException) as fout:
            await get_current_user_ws(_nep_websocket(gebruiker["access"]), db=postgres_session)

        assert (fout.value.status_code, "ACCOUNT_DISABLED" in str(fout.value.detail)) == (401, True)

    async def test_de_tweede_websocketingang_wordt_geweigerd(
        self, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        from src.core.auth.websocket_auth import WebSocketAuthenticator

        await _zet_actief(postgres_session, gebruiker["id"], False)

        user = await WebSocketAuthenticator().authenticate(_nep_websocket(gebruiker["access"]))

        assert user is None, "WebSocketAuthenticator liet een uitgeschakelde gebruiker binnen"

    async def test_een_inactieve_platformbeheerder_valt_er_ook_onder(
        self, integration_client: Any, postgres_session: AsyncSession
    ) -> None:
        await postgres_session.execute(text("DELETE FROM users WHERE email = :e"), {"e": EMAIL})
        await postgres_session.commit()
        user_id = await _maak_gebruiker(postgres_session, superuser=True)
        access, _ = _tokens(user_id)
        await _zet_actief(postgres_session, user_id, False)

        antwoord = await integration_client.get(RECEIVABLES, headers=_koppen(access))

        assert antwoord.status_code == 401, f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"


@pytest.mark.integration
@pytest.mark.asyncio
class TestWeerAanzetten:
    async def test_na_weer_aanzetten_werkt_hetzelfde_token_weer(
        self, integration_client: Any, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        await _zet_actief(postgres_session, gebruiker["id"], False)
        await integration_client.get(RECEIVABLES, headers=_koppen(gebruiker["access"]))
        await _zet_actief(postgres_session, gebruiker["id"], True)

        antwoord = await integration_client.get(RECEIVABLES, headers=_koppen(gebruiker["access"]))

        assert antwoord.status_code == 200, antwoord.text


def _token_met_claims(claims: dict[str, Any]) -> str:
    return jwt_handler.create_access_token(data=claims)


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeRechtenketenEnDeOverigeIngangen:
    """Gate 2-bevinding 2026-10-12: `get_current_user_id` (364 plekken via `require_permission`),
    `/verify-token` en drie WebSocket-ingangen lazen alleen het token."""

    @pytest.mark.parametrize("variant", ["user_id", "sub_numeriek", "sub_email"])
    async def test_get_current_user_id_weigert_een_uitgezet_account(
        self, postgres_session: AsyncSession, gebruiker: dict[str, Any], variant: str
    ) -> None:
        from src.core.auth.dependencies import get_current_user_id

        claims: dict[str, Any] = {"tenant_id": TENANT}
        if variant == "user_id":
            claims.update({"sub": str(gebruiker["id"]), "user_id": gebruiker["id"]})
        elif variant == "sub_numeriek":
            claims.update({"sub": str(gebruiker["id"])})
        else:
            claims.update({"sub": EMAIL})
        token = _token_met_claims(claims)
        await _zet_actief(postgres_session, gebruiker["id"], False)

        with pytest.raises(HTTPException) as fout:
            await get_current_user_id(token=token, session=postgres_session)

        assert (fout.value.status_code, fout.value.detail) == (401, "ACCOUNT_DISABLED")

    @pytest.mark.parametrize("variant", ["user_id", "sub_numeriek", "sub_email"])
    async def test_get_current_user_id_laat_een_actief_account_door(
        self, postgres_session: AsyncSession, gebruiker: dict[str, Any], variant: str
    ) -> None:
        from src.core.auth.dependencies import get_current_user_id

        claims: dict[str, Any] = {"tenant_id": TENANT}
        if variant == "user_id":
            claims.update({"sub": str(gebruiker["id"]), "user_id": gebruiker["id"]})
        elif variant == "sub_numeriek":
            claims.update({"sub": str(gebruiker["id"])})
        else:
            claims.update({"sub": EMAIL})

        uitkomst = await get_current_user_id(
            token=_token_met_claims(claims), session=postgres_session
        )

        assert uitkomst == gebruiker["id"]

    async def test_verify_token_geeft_401_voor_een_uitgezet_account(
        self, integration_client: Any, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        await _zet_actief(postgres_session, gebruiker["id"], False)

        antwoord = await integration_client.post(
            "/api/v1/auth/verify-token",
            json={"token": gebruiker["access"]},
            headers=_koppen(gebruiker["access"]),
        )

        assert (antwoord.status_code, "ACCOUNT_DISABLED" in antwoord.text) == (401, True), (
            f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"
        )

    async def test_verify_token_laat_een_actief_account_door(
        self, integration_client: Any, gebruiker: dict[str, Any]
    ) -> None:
        antwoord = await integration_client.post(
            "/api/v1/auth/verify-token",
            json={"token": gebruiker["access"]},
            headers=_koppen(gebruiker["access"]),
        )

        assert antwoord.status_code == 200, antwoord.text

    async def test_de_kanaalmanager_weigert_een_uitgezet_account(
        self, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        from starlette.websockets import WebSocketState

        from src.core.websocket.manager import ConnectionManager

        await _zet_actief(postgres_session, gebruiker["id"], False)
        ws = _nep_websocket(gebruiker["access"])
        ws.client_state = WebSocketState.CONNECTING

        verbinding = await ConnectionManager().connect(ws, "kanaal", token=gebruiker["access"])

        assert verbinding is None

    async def test_de_kanaalmanager_laat_een_actief_account_door(
        self, gebruiker: dict[str, Any]
    ) -> None:
        from starlette.websockets import WebSocketState

        from src.core.websocket.manager import ConnectionManager

        ws = _nep_websocket(gebruiker["access"])
        ws.client_state = WebSocketState.CONNECTING

        verbinding = await ConnectionManager().connect(ws, "kanaal", token=gebruiker["access"])

        assert verbinding is not None

    async def test_focus_builder_ws_token_weigert_een_uitgezet_account(
        self, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        from src.core.api.v1.focus_builder.shared import validate_ws_token

        await _zet_actief(postgres_session, gebruiker["id"], False)

        with pytest.raises(ValueError):
            await validate_ws_token(gebruiker["access"])

    async def test_focus_builder_ws_token_laat_een_actief_account_door(
        self, gebruiker: dict[str, Any]
    ) -> None:
        from src.core.api.v1.focus_builder.shared import validate_ws_token

        user = await validate_ws_token(gebruiker["access"])

        assert user.tenant_id == TENANT

    async def test_focus_builder_auth_handler_weigert_een_uitgezet_account(
        self, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        from src.core.api.v1.focus_builder.ws_dependencies import WebSocketAuthHandler

        await _zet_actief(postgres_session, gebruiker["id"], False)

        with pytest.raises(ValueError):
            await WebSocketAuthHandler().validate_token(gebruiker["access"])

    async def test_focus_builder_auth_handler_laat_een_actief_account_door(
        self, gebruiker: dict[str, Any]
    ) -> None:
        from src.core.api.v1.focus_builder.ws_dependencies import WebSocketAuthHandler

        user = await WebSocketAuthHandler().validate_token(gebruiker["access"])

        assert user.id == gebruiker["id"]

    async def test_validate_geeft_401_voor_een_uitgezet_account(
        self, integration_client: Any, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        await _zet_actief(postgres_session, gebruiker["id"], False)

        antwoord = await integration_client.get(
            "/api/v1/auth/validate",
            params={"token": gebruiker["access"]},
            headers=_koppen(gebruiker["access"]),
        )

        assert (antwoord.status_code, "ACCOUNT_DISABLED" in antwoord.text) == (401, True), (
            f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"
        )

    async def test_validate_laat_een_actief_account_door(
        self, integration_client: Any, gebruiker: dict[str, Any]
    ) -> None:
        antwoord = await integration_client.get(
            "/api/v1/auth/validate",
            params={"token": gebruiker["access"]},
            headers=_koppen(gebruiker["access"]),
        )

        assert antwoord.status_code == 200, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestRoutesDieAlleenOpDeMiddlewareLeunen:
    """Gate 2 ronde 2: routes zonder gebruikersafhankelijkheid (alleen `get_current_tenant_id`
    of `require_tenant_id`) lazen het token alleen in `tenant_middleware`."""

    PADEN = [
        ("GET", "/api/v1/search/hybrid", {"params": {"query": "test"}}),
        ("POST", "/api/v1/crag/chat", {"json": {"query": "test"}}),
    ]

    @pytest.mark.parametrize("methode,pad,extra", PADEN)
    async def test_een_uitgezet_account_wordt_in_de_middleware_geweigerd(
        self,
        csrf_uit: Any,
        integration_client: Any,
        postgres_session: AsyncSession,
        gebruiker: dict[str, Any],
        methode: str,
        pad: str,
        extra: dict[str, Any],
    ) -> None:
        await _zet_actief(postgres_session, gebruiker["id"], False)

        antwoord = await integration_client.request(
            methode, pad, headers=_koppen(gebruiker["access"]), **extra
        )

        assert (antwoord.status_code, "ACCOUNT_DISABLED" in antwoord.text) == (401, True), (
            f"{methode} {pad}: HTTP {antwoord.status_code}: {antwoord.text[:200]}"
        )

    @pytest.mark.parametrize("methode,pad,extra", PADEN)
    async def test_een_actief_account_komt_langs_de_middleware(
        self,
        csrf_uit: Any,
        integration_client: Any,
        gebruiker: dict[str, Any],
        methode: str,
        pad: str,
        extra: dict[str, Any],
    ) -> None:
        antwoord = await integration_client.request(
            methode, pad, headers=_koppen(gebruiker["access"]), **extra
        )

        assert antwoord.status_code != 401, (
            f"{methode} {pad}: HTTP {antwoord.status_code}: {antwoord.text[:200]}"
        )


class _KapotteSessieMaker:
    """Een sessiemaker die bij het aanmaken van een sessie een verbindingsfout geeft."""

    def __init__(self, fout: BaseException) -> None:
        self._fout = fout

    def __call__(self) -> Any:
        raise self._fout


@contextmanager
def _kapotte_database(fout: BaseException) -> Iterator[None]:
    """Laat `account_status._sessiemaker` tijdelijk een verbindingsfout geven en zet hem BINNEN de test terug.

    Waarom niet `monkeypatch.setattr`: de fixture `postgres_session` (tests/integration/conftest.py) wijst dezelfde
    variabele naar zijn eigen transactie en zet hem bij het opruimen terug naar het origineel. Gemeten 2026-10-28
    met een pytest-plugin die na elke test de variabele vergeleek: na elk van de zes tests die hier eerst
    `monkeypatch.setattr` gebruikten bleef `_sessiemaker` op een andere waarde staan dan voor de test, en daarna
    kreeg het volgende bestand dat de tenant-middleware gebruikt 'Authentication unavailable' (27 tests in
    test_wachtwoord_kiezen_via_het_scherm.py). Wat `monkeypatch` bij het opruimen precies terugzet is NIET apart
    nagemeten; het bewijs is dat met deze `finally` de plugin geen lek meer meldt en de paren groen zijn.
    """
    from src.core.auth import account_status

    voorheen = account_status._sessiemaker
    account_status._sessiemaker = lambda: _KapotteSessieMaker(fout)  # type: ignore[assignment]
    try:
        yield
    finally:
        account_status._sessiemaker = voorheen


@pytest.mark.integration
@pytest.mark.asyncio
class TestFailClosed:
    async def test_de_middleware_geeft_503_en_geen_logout_als_de_database_weg_is(
        self,
        integration_client: Any,
        gebruiker: dict[str, Any],
    ) -> None:
        with _kapotte_database(OSError("weg")):
            antwoord = await integration_client.get(RECEIVABLES, headers=_koppen(gebruiker["access"]))

        assert (antwoord.status_code, "ACCOUNT_DISABLED" in antwoord.text) == (503, False), (
            f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"
        )

    @pytest.mark.parametrize("fout", [OSError("weg"), TimeoutError("traag"), RuntimeError("x")])
    async def test_een_onbereikbare_database_is_onbekend_en_niet_actief(
        self, gebruiker: dict[str, Any], fout: BaseException
    ) -> None:
        from src.core.auth.account_status import AccountStatus, haal_account_status

        with _kapotte_database(fout):
            status = await haal_account_status(str(gebruiker["id"]), TENANT)

        assert status is AccountStatus.ONBEKEND

    async def test_de_websocketfunctie_weigert_bij_een_onbereikbare_database(
        self, gebruiker: dict[str, Any]
    ) -> None:
        from src.core.auth.websocket_auth import account_is_active_for_ws

        with _kapotte_database(TimeoutError("traag")):
            actief = await account_is_active_for_ws(str(gebruiker["id"]), TENANT)

        assert actief is False


CSRF_PUBLIEK = "/api/v1/auth/csrf-token"


async def _maak_portaalgebruiker(
    sessie: AsyncSession, portal_id: int, *, geblokkeerd: bool
) -> str:
    from src.core.models.foundation_content import PortalRole, PortalUser

    sessie.add(
        PortalUser(
            id=portal_id,
            tenant_id=TENANT,
            email=f"portaal-{portal_id}@integration.test",
            is_blocked=geblokkeerd,
            role=PortalRole.VISITOR,
        )
    )
    await sessie.commit()
    return jwt_handler.create_access_token(
        data={
            "sub": str(portal_id),
            "user_id": portal_id,
            "tenant_id": TENANT,
            "aud": "portal",
            "scope": "portal_uploader",
        }
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestPubliekeEnPortaalPaden:
    """Gate 2 ronde 3: de publieke tak en het tweede accounttype van de middleware."""

    async def test_een_uitgezet_account_op_een_publiek_pad_wordt_anoniem_doorgelaten(
        self, integration_client: Any, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        await _zet_actief(postgres_session, gebruiker["id"], False)

        antwoord = await integration_client.get(CSRF_PUBLIEK, headers=_koppen(gebruiker["access"]))

        assert (antwoord.status_code, "ACCOUNT_DISABLED" in antwoord.text) == (200, False), (
            f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"
        )

    async def test_een_publiek_pad_geeft_geen_503_als_de_database_weg_is(
        self,
        integration_client: Any,
        gebruiker: dict[str, Any],
    ) -> None:
        with _kapotte_database(OSError("weg")):
            antwoord = await integration_client.get(CSRF_PUBLIEK, headers=_koppen(gebruiker["access"]))

        assert antwoord.status_code == 200, f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"

    async def test_een_actieve_portaalgebruiker_komt_langs_de_middleware(
        self, integration_client: Any, postgres_session: AsyncSession
    ) -> None:
        token = await _maak_portaalgebruiker(postgres_session, 880001, geblokkeerd=False)

        antwoord = await integration_client.get(
            "/api/v1/search/hybrid", params={"query": "x"}, headers=_koppen(token)
        )

        assert antwoord.status_code != 401, f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"

    async def test_een_geblokkeerde_portaalgebruiker_wordt_geweigerd(
        self, integration_client: Any, postgres_session: AsyncSession
    ) -> None:
        token = await _maak_portaalgebruiker(postgres_session, 880002, geblokkeerd=True)

        antwoord = await integration_client.get(
            "/api/v1/search/hybrid", params={"query": "x"}, headers=_koppen(token)
        )

        assert (antwoord.status_code, "ACCOUNT_DISABLED" in antwoord.text) == (401, True), (
            f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"
        )

    async def test_een_portaalgebruiker_wordt_niet_op_een_medewerker_met_hetzelfde_nummer_getoetst(
        self, integration_client: Any, postgres_session: AsyncSession, gebruiker: dict[str, Any]
    ) -> None:
        # Medewerker met dit nummer staat UIT; de portaalgebruiker met hetzelfde nummer is actief.
        await _zet_actief(postgres_session, gebruiker["id"], False)
        token = await _maak_portaalgebruiker(postgres_session, gebruiker["id"], geblokkeerd=False)

        antwoord = await integration_client.get(
            "/api/v1/search/hybrid", params={"query": "x"}, headers=_koppen(token)
        )

        assert antwoord.status_code != 401, f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"

    async def test_een_te_lange_sub_geeft_een_nette_weigering_geen_crash(
        self, integration_client: Any
    ) -> None:
        token = _token_met_claims({"sub": "9" * 5000, "tenant_id": TENANT})

        antwoord = await integration_client.get(
            "/api/v1/search/hybrid", params={"query": "x"}, headers=_koppen(token)
        )

        assert antwoord.status_code == 401, f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"

    async def test_een_tenant_claim_die_geen_geheel_getal_is_wordt_geweigerd(
        self, integration_client: Any, gebruiker: dict[str, Any]
    ) -> None:
        token = _token_met_claims({"sub": str(gebruiker["id"]), "tenant_id": 1.5})

        antwoord = await integration_client.get(
            "/api/v1/search/hybrid", params={"query": "x"}, headers=_koppen(token)
        )

        assert antwoord.status_code == 401, f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"

    async def test_een_pad_dat_alleen_met_docs_begint_slaat_de_middleware_niet_over(
        self, integration_client: Any, gebruiker: dict[str, Any], postgres_session: AsyncSession
    ) -> None:
        await _zet_actief(postgres_session, gebruiker["id"], False)

        antwoord = await integration_client.get(
            "/docsXYZ", headers=_koppen(gebruiker["access"])
        )

        assert (antwoord.status_code, "ACCOUNT_DISABLED" in antwoord.text) == (401, True), (
            f"HTTP {antwoord.status_code}: {antwoord.text[:200]}"
        )
