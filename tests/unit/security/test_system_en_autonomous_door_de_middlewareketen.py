"""`/system` en `/autonomous` bereiken een beheerder door de ECHTE middlewareketen (Keten B nazorg, A).

**Het defect.** `SecurityMiddleware._determine_security_level` geeft ADMIN voor elk pad met
`/system`, `/config` of `/autonomous` erin. Een token uit `jwt_handler` draagt geen
`security_level`-claim en valt dus op AUTHENTICATED; de vergelijking weigert daarmee ELKE
gebruiker met 401, ook een beheerder. Zelfde fout als `/admin` had (opgelost met
`_is_admin_route`); dat is voor deze twee prefixen nog niet gedaan.

Patroon: `tests/unit/debiteuren/test_logboek_door_de_middlewareketen.py` en
`test_admin_herkenning_is_routegebonden.py`: `create_app(testing=True)` plus
`register_all_routers`, ENABLE_SECURITY_MIDDLEWARE aan, een echt `jwt_handler`-token als
cookie. Alleen de gebruiker-dependency en de databasesessie zijn vervangen.

Wat gemeten wordt (EP, twee klassen aanroeper x twee representatieve routes):
  1. Beheerder -> NIET 401 (rood nu: 401 uit de middleware).
  2. Gewone ingelogde gebruiker -> 403 en geen 401 (rood nu: 401). Dit eist een rolcontrole
     per route: `/api/v1/system/llm-status` heeft nu alleen `Depends(get_current_user)`; zonder
     rolcontrole zou de gewone gebruiker na de middlewarefix een 200 krijgen en blijft dit rood.

Wat dit NIET meet: de scopecontrole (`require_scopes`, RBAC in de database, hier een lege nepsessie).
`get_current_user_id` is overschreven: zonder die override geeft hij 401 uit de database-opzoeking
("Invalid token or user not found"), niet uit de middleware. De 403 van een gewone gebruiker wordt
aan de detailtekst "Admin privileges required" herkend (rolcontrole, `require_admin_user`).

Autouse-fixtures nagelopen: `tests/conftest.py` (`enforce_testing_env`, `_reset_global_state`,
`ensure_main_thread_event_loop`, `_seed_module_snapshot`) raakt de niveaubepaling niet; er is
geen conftest in `tests/unit/security/`. `ENABLE_SECURITY_MIDDLEWARE` staat expliciet aan.
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

LLM_STATUS = "/api/v1/system/llm-status"
AUTONOMOUS_STATUS = "/api/v1/autonomous/status"
PADEN = [LLM_STATUS, AUTONOMOUS_STATUS]


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


async def _haal(app: Any, pad: str, rollen: list[str]) -> tuple[int, str]:
    email = "beheer@x.example" if "admin" in rollen else "gewoon@x.example"
    gebruiker = UserResponse(id=7, email=email, tenant_id=1, roles=rollen)
    app.dependency_overrides[get_current_user_dependency] = lambda: gebruiker
    app.dependency_overrides[get_current_user] = lambda: gebruiker
    app.dependency_overrides[get_db] = _lege_db
    # `get_current_user_id` (binnen `require_scopes`) zoekt de gebruiker in de database; de nepsessie
    # is leeg en het token draagt een e-mail als `sub`, dus zonder deze override geeft HIJ 401
    # ("Invalid token or user not found"), niet de middleware. Zo meet de beheerdertest weer
    # uitsluitend de middleware.
    app.dependency_overrides[get_current_user_id] = lambda: gebruiker.id
    token = jwt_handler.create_access_token({"sub": email, "tenant_id": 1, "roles": rollen})
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={"access_token": token},
        ) as client:
            antwoord = await client.get(pad)
            return antwoord.status_code, str(antwoord.json().get("detail", ""))
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("pad", PADEN)
async def test_beheerder_wordt_niet_door_de_middleware_geweigerd(app: Any, pad: str) -> None:
    status, detail = await _haal(app, pad, ["admin"])

    assert status != 401, f"beheerder op {pad} kreeg {status} ({detail}); middleware weigert"


@pytest.mark.parametrize("pad", PADEN)
async def test_ingelogde_niet_beheerder_krijgt_403_en_geen_401(app: Any, pad: str) -> None:
    status, _detail = await _haal(app, pad, ["user"])

    assert status == 403, f"gewone gebruiker op {pad} kreeg {status}, verwacht 403"


@pytest.mark.parametrize("pad", PADEN)
async def test_403_voor_niet_beheerder_komt_uit_de_rolcontrole(app: Any, pad: str) -> None:
    _status, detail = await _haal(app, pad, ["user"])

    assert detail == "Admin privileges required", f"403 op {pad} komt niet uit de rolcontrole: {detail}"


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
