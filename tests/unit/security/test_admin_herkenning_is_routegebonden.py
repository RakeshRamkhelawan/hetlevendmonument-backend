"""Een padparameter die toevallig `admin` heet, maakt een route geen beheerroute.

Waarom (commit aed84fa0, sprint-dag debiteuren Keten B dag 5): `_determine_security_level`
behandelt elk verzoekpad waarin de substring `/admin` voorkomt als `AUTHENTICATED`, en die tak
staat VOOR de `/system`-, `/config`- en `/autonomous`-takken die ADMIN eisen. Een gewone
ingelogde gebruiker kan daardoor een padparameter op `admin` zetten en komt langs de
middleware, terwijl het pad zonder die waarde 401 geeft. Gemeten met een echt
`jwt_handler`-cookie (rol alleen "user"): `POST /api/v1/autonomous/workflows/admin/execute`
gaf op cb1df6dd 401 en op aed84fa0 een 422 (de middleware laat hem door; de route heeft
alleen `Depends(get_current_user)`).

Deze module gebruikt de ECHTE middlewareketen (`create_app(testing=True)` plus
`register_all_routers`, ENABLE_SECURITY_MIDDLEWARE aan) en een echt token. Alleen de
gebruiker-dependency en de databasesessie zijn vervangen, en de Dramatiq-verzending, zodat
een doorgelaten verzoek geen wachtrij raakt.

Twee kanten:
  - bypass: gewone gebruiker op paden waar `admin` een parameterwaarde is -> 401/403.
  - behoud: een echte beheerder op `/api/v1/admin/logs` en `/admin/logs` -> 200 (dat was het
    oorspronkelijke defect dat aed84fa0 repareerde; "weiger alle /admin" is dus geen oplossing).

Er is geen echte route met een padparameter onder `/config`; dat geval wordt afgedekt door de
guard `tests/architecture/test_admin_routes_hebben_een_rolcontrole.py`, die over ELKE route met
padparameters loopt.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.auth.api_deps import get_current_user_dependency
from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.auth.jwt_handler import jwt_handler
from src.core.database.database import get_db

BEHEERDER_EMAIL = "beheerder@x.example"
GEBRUIKER_EMAIL = "gewone.gebruiker@x.example"


class _LegeResultaten:
    def scalars(self) -> _LegeResultaten:
        return self

    def all(self) -> list[Any]:
        return []


class _LegeSessie:
    async def execute(self, *_args: Any, **_kwargs: Any) -> _LegeResultaten:
        return _LegeResultaten()


async def _lege_db() -> AsyncIterator[_LegeSessie]:
    yield _LegeSessie()


@pytest.fixture(scope="module")
def app() -> Iterator[Any]:
    """De echte app, met de securitymiddleware aan en alle routers geregistreerd."""
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
def _geen_wachtrij(monkeypatch: pytest.MonkeyPatch) -> None:
    """Een doorgelaten workflow-verzoek mag niets in Redis zetten."""
    from src.core.tasks import workflow_tasks

    monkeypatch.setattr(workflow_tasks.execute_workflow_step, "send", lambda *_a, **_k: None)


def _token(email: str, rollen: list[str]) -> str:
    return jwt_handler.create_access_token({"sub": email, "tenant_id": 1, "roles": rollen})


async def _verzoek(
    app: Any, methode: str, pad: str, *, rollen: list[str] | None, json: Any = None
) -> int:
    """Stuur een verzoek met een echt token (of zonder, bij rollen=None); geef de statuscode."""
    cookies: dict[str, str] = {}
    if rollen is not None:
        email = BEHEERDER_EMAIL if "admin" in rollen else GEBRUIKER_EMAIL
        gebruiker = UserResponse(id=7, email=email, tenant_id=1, roles=rollen)
        app.dependency_overrides[get_current_user_dependency] = lambda: gebruiker
        app.dependency_overrides[get_current_user] = lambda: gebruiker
        cookies = {"access_token": _token(email, rollen)}
    app.dependency_overrides[get_db] = _lege_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", cookies=cookies
        ) as client:
            antwoord = await client.request(methode, pad, json=json)
        return antwoord.status_code
    finally:
        app.dependency_overrides.clear()


GELDIGE_BODY = {"workflow_id": "wf-1", "initial_data": {}}


@pytest.mark.parametrize("waarde", ["admin", "adminx", "x1"])
async def test_gewone_gebruiker_komt_niet_op_autonomous_execute(app: Any, waarde: str) -> None:
    """`admin` als workflow-id mag niet meer doorlaten dan een neutrale waarde (401)."""
    status = await _verzoek(
        app,
        "POST",
        f"/api/v1/autonomous/workflows/{waarde}/execute",
        rollen=["user"],
        json=GELDIGE_BODY,
    )

    assert status in (401, 403), f"/autonomous/.../{waarde}/execute gaf {status}"


@pytest.mark.parametrize("waarde", ["admin", "adminx", "x1"])
async def test_gewone_gebruiker_komt_niet_op_config_cache_reload(app: Any, waarde: str) -> None:
    """Gewone gebruiker -> 403 (rolcontrole in de route), voor elke waarde van de padparameter.

    Gedrag BEWUST gewijzigd (Keten B nazorg, A): dit eiste 401 uit de middleware. De middleware
    geeft voor /api/v1/system/* nu alleen AUTHENTICATED (de ADMIN-eis weigerde elke gebruiker,
    ook een beheerder); de weigering komt van `require_admin_user` in de route, en dat is 403.
    De scherpte blijft: `admin`, `adminx` en `x1` als padparameter geven dezelfde uitkomst, dus
    een padparameter kan de rolcontrole nog steeds niet omzeilen of vervangen.
    """
    status = await _verzoek(
        app,
        "POST",
        f"/api/v1/system/agents/config-cache/reload/{waarde}",
        rollen=["user"],
        json={},
    )

    assert status == 403, f"/system/.../reload/{waarde} gaf {status}, verwacht 403"


async def test_gewone_gebruiker_komt_niet_op_autonomous_repair_met_admin_als_id(
    app: Any,
) -> None:
    status = await _verzoek(
        app,
        "POST",
        "/api/v1/autonomous/healing/execute-repair/admin",
        rollen=["user"],
        json={},
    )

    assert status in (401, 403), f"/autonomous/healing/execute-repair/admin gaf {status}"


@pytest.mark.parametrize("pad", ["/api/v1/admin/logs", "/admin/logs"])
async def test_beheerder_krijgt_200_op_admin_logs(app: Any, pad: str) -> None:
    """Behoud: een echte beheerder mag erdoor (het defect dat aed84fa0 repareerde)."""
    status = await _verzoek(app, "GET", pad, rollen=["admin"])

    assert status == 200, f"beheerder op {pad} kreeg {status}"


@pytest.mark.parametrize("pad", ["/api/v1/admin/logs", "/admin/logs"])
async def test_gewone_gebruiker_krijgt_403_op_admin_logs(app: Any, pad: str) -> None:
    status = await _verzoek(app, "GET", pad, rollen=["user"])

    assert status == 403, f"gewone gebruiker op {pad} kreeg {status}"


@pytest.mark.parametrize("pad", ["/api/v1/admin/logs", "/admin/logs"])
async def test_zonder_token_krijgt_401_op_admin_logs(app: Any, pad: str) -> None:
    status = await _verzoek(app, "GET", pad, rollen=None)

    assert status == 401, f"zonder token op {pad} kreeg {status}"


# Een /admin-ROUTE waarvan het pad OOK `/system` bevat: de enige plek waar de routegebonden
# herkenning (`_is_admin_route`) nodig is. Zonder die herkenning valt het pad in de
# `/system`-tak (ADMIN, een claim die nooit gezet wordt) en krijgt ook een beheerder 401.
# `/admin/logs` bewijst dat niet: dat valt ook zonder helper in de standaardtak.
SYSTEEM_BEHEERPADEN = ["/api/v1/admin/system", "/admin/system"]


@pytest.mark.parametrize("pad", SYSTEEM_BEHEERPADEN)
async def test_beheerder_krijgt_200_op_admin_system(app: Any, pad: str) -> None:
    status = await _verzoek(app, "GET", pad, rollen=["admin"])

    assert status == 200, f"beheerder op {pad} kreeg {status}"


@pytest.mark.parametrize("pad", SYSTEEM_BEHEERPADEN)
async def test_gewone_gebruiker_krijgt_403_op_admin_system(app: Any, pad: str) -> None:
    status = await _verzoek(app, "GET", pad, rollen=["user"])

    assert status == 403, f"gewone gebruiker op {pad} kreeg {status}"


@pytest.mark.parametrize("pad", SYSTEEM_BEHEERPADEN)
async def test_zonder_token_krijgt_401_op_admin_system(app: Any, pad: str) -> None:
    status = await _verzoek(app, "GET", pad, rollen=None)

    assert status == 401, f"zonder token op {pad} kreeg {status}"


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
