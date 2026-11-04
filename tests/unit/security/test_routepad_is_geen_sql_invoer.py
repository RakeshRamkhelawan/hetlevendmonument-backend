"""Het routepad zelf is geen SQL-invoer (Keten B nazorg, punt 1).

**Het defect.** `ProductionSecurityManager.detect_suspicious_activity` scande het volledige
verzoekpad met een woordpatroon (SELECT, INSERT, UPDATE, DELETE, DROP, UNION, CREATE, ALTER).
Het pad `/api/v1/autonomous/agents/create` bevat het woord `create` als vast padsegment; dat
gaf een CRITICAL-melding en zette het IP in `blocked_ips` -- tot de backend herstart.

**De fix.** Alleen door de gebruiker geleverde waarden worden gescand: queryparameters en
padparameters (waarden van de gematchte route). Het vaste deel van het routesjabloon niet.

Patroon: `test_system_en_autonomous_door_de_middlewareketen.py` -- echte `create_app` plus
`register_all_routers`, ENABLE_SECURITY_MIDDLEWARE aan, een echt `jwt_handler`-token.
Alleen gebruiker-dependencies en de databasesessie zijn vervangen.

Wat dit NIET meet: de body. De middleware heeft de body nooit gescand en doet dat nog steeds niet.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.auth.api_deps import get_current_user_dependency
from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user, get_current_user_id
from src.core.auth.jwt_handler import jwt_handler
from src.core.database.database import get_db
from src.core.security.security_manager import get_security_manager

AGENT_CREATE = "/api/v1/autonomous/agents/create"
CLIENT_IP = "127.0.0.1"
AGENT_BODY = {
    "archetype": "analyst",
    "name": "a",
    "description": "d",
    "capabilities": [],
    "tools": [],
}


class _LegeResultaten:
    def scalars(self) -> _LegeResultaten:
        return self

    def all(self) -> list[Any]:
        return []

    def scalar_one_or_none(self) -> None:
        return None


class _LegeSessie:
    async def execute(self, *_args: Any, **_kwargs: Any) -> _LegeResultaten:
        return _LegeResultaten()


async def _lege_db() -> AsyncIterator[_LegeSessie]:
    yield _LegeSessie()


@pytest.fixture(scope="module")
def app() -> Iterator[Any]:
    vorige = os.environ.get("ENABLE_SECURITY_MIDDLEWARE")
    os.environ["ENABLE_SECURITY_MIDDLEWARE"] = "true"
    try:
        import src.core.database.import_all_models  # noqa: F401
        from src.core.api.router_registry import register_all_routers
        from src.main import create_app

        app = create_app(testing=True)
        register_all_routers(app)
        yield app
    finally:
        if vorige is None:
            os.environ.pop("ENABLE_SECURITY_MIDDLEWARE", None)
        else:
            os.environ["ENABLE_SECURITY_MIDDLEWARE"] = vorige


@pytest.fixture(autouse=True)
def _geen_beheerdersopzoeking(monkeypatch: pytest.MonkeyPatch) -> None:
    """De vrijstelling van de IP-blokkade zoekt de gebruiker in de database op (acceptant
    ronde 3, N3); een SQL-signaal vraagt die nu op. Geen database in een unittest: hier is
    niemand vrijgesteld. Het echte pad meet
    `tests/integration/security/test_beheerder_ontsnapt_aan_de_ip_blokkade.py`."""
    from src.core.security.security_middleware import SecurityMiddleware

    async def _nooit(self: Any, request: Any) -> bool:
        return False

    monkeypatch.setattr(SecurityMiddleware, "_is_admin_token", _nooit)


@pytest.fixture(autouse=True)
def _schone_blokkadelijst() -> Iterator[None]:
    manager = get_security_manager()
    manager.blocked_ips.clear()
    manager.security_events.clear()
    yield
    manager.blocked_ips.clear()
    manager.security_events.clear()


async def _vraag(
    app: Any, methode: str, pad: str, rollen: list[str], json: Any = None
) -> tuple[int, str]:
    email = "beheer@x.example" if "admin" in rollen else "gewoon@x.example"
    gebruiker = UserResponse(id=7, email=email, tenant_id=1, roles=rollen)
    app.dependency_overrides[get_current_user_dependency] = lambda: gebruiker
    app.dependency_overrides[get_current_user] = lambda: gebruiker
    app.dependency_overrides[get_db] = _lege_db
    app.dependency_overrides[get_current_user_id] = lambda: gebruiker.id
    token = jwt_handler.create_access_token({"sub": email, "tenant_id": 1, "roles": rollen})
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={"access_token": token},
        ) as client:
            antwoord = await client.request(methode, pad, json=json)
            try:
                detail = antwoord.json()
            except ValueError:
                detail = antwoord.text
            return antwoord.status_code, str(detail)
    finally:
        app.dependency_overrides.clear()


def _sql_meldingen() -> list[Any]:
    return [
        e for e in get_security_manager().security_events if e.event_type == "sql_injection_signal"
    ]


async def test_beheerder_op_agents_create_wordt_niet_geblokkeerd(app: Any) -> None:
    status, detail = await _vraag(app, "POST", AGENT_CREATE, ["admin"], AGENT_BODY)

    assert "Security violation" not in detail and "IP blocked" not in detail, detail
    assert CLIENT_IP not in get_security_manager().blocked_ips
    assert _sql_meldingen() == []

    # Een tweede aanvraag van hetzelfde IP komt ook gewoon binnen (geen 429 IP blocked).
    status2, detail2 = await _vraag(app, "POST", AGENT_CREATE, ["admin"], AGENT_BODY)
    assert "IP blocked" not in detail2, f"tweede aanvraag kreeg {status2}: {detail2}"
    assert status == status2


async def test_medewerker_op_agents_create_krijgt_403_van_de_rolcontrole(app: Any) -> None:
    status, detail = await _vraag(app, "POST", AGENT_CREATE, ["user"], AGENT_BODY)

    assert status == 403, f"{status}: {detail}"
    assert "Admin privileges required" in detail, f"403 komt niet uit de rolcontrole: {detail}"
    assert CLIENT_IP not in get_security_manager().blocked_ips


async def test_sql_injectie_in_een_queryparameter_wordt_nog_herkend(app: Any) -> None:
    await _vraag(app, "GET", "/api/v1/autonomous/status?filter=1%20UNION%20SELECT%20password", ["admin"])

    assert len(_sql_meldingen()) == 1
    # Sinds 2026-10-08 een signaal, geen blokkade in het geheugen (plan nazorg, punt a); de
    # blokkade zelf staat in tests/unit/security/test_ip_blokkade_middleware.py.
    assert CLIENT_IP not in get_security_manager().blocked_ips


def test_detectie_scant_alleen_de_query_van_een_kaal_pad() -> None:
    manager = get_security_manager()

    manager.sql_injection_signal("10.0.0.1", None, "/api/v1/x/delete/update/select/drop")
    assert _sql_meldingen() == []

    manager.sql_injection_signal("10.0.0.2", None, "/api/v1/x?id=1 OR 1=1")
    assert len(_sql_meldingen()) == 1


def test_door_de_gebruiker_geleverde_waarden_worden_gescand() -> None:
    manager = get_security_manager()

    manager.sql_injection_signal(
        "10.0.0.3", None, "/api/v1/receivables/x", ["1; DROP TABLE users"]
    )
    assert len(_sql_meldingen()) == 1


@pytest.fixture(autouse=True)
def _account_is_actief_buiten_deze_test():
    """Deze tests gaan over rollen en de middlewareketen, niet over de accountstatus, en hebben geen database.

    De controle zelf (uitgezet = 401 ACCOUNT_DISABLED, database weg = 503) wordt gemeten in
    `tests/integration/test_uitgeschakeld_is_uitgeschakeld.py`, tegen een echte database.
    """
    from unittest.mock import AsyncMock, patch

    from src.core.auth import account_status

    with patch.object(
        account_status,
        "haal_account_status",
        AsyncMock(return_value=account_status.AccountStatus.ACTIEF),
    ):
        yield
