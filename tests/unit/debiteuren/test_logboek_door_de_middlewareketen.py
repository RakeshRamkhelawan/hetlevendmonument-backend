"""Het logboek bereikt een beheerder ook door de ECHTE middlewareketen -- Keten B dag 5.

**Het defect (gemeten in de draaiende stack, 2026-10-07).** `GET /api/v1/admin/logs?limit=100`
geeft 401 met de body `{"error":"Authentication required","message":"Insufficient permissions.
Required: admin"}`, terwijl dezelfde sessie op `/api/v1/receivables` 200 krijgt. De afwijzing komt
uit `SecurityMiddleware` (`src/core/security/security_middleware.py`): `_determine_security_level`
geeft ADMIN voor elk pad met `/admin` erin, en `_check_authentication` vergelijkt dat met het
niveau van het token. Een token uit `jwt_handler` draagt geen `security_level`-claim en valt dus
altijd op AUTHENTICATED; de vergelijking weigert daarmee ELKE gebruiker, ook een beheerder. De
code zegt zelf dat "ADMIN gating happens in dependencies" -- die controle (`require_admin_role`,
403) komt er dus nooit aan toe.

**Waarom `test_logboek_endpoint.py` dit niet zag.** Die test bouwt `FastAPI()` zonder
middleware en vervangt `get_current_user`; de laag die afwijst bestaat daar niet. Deze module
gebruikt `create_app(testing=True)`: dezelfde `setup_middleware` als de draaiende app.

Wat hier gemeten wordt (EP, drie klassen aanroeper, en beide paden waarop de adminrouter hangt):

1. Een beheerder met een geldige sessie krijgt 200 met `recent_logs` (rood op het defect: 401).
2. Een niet-beheerder met een geldige sessie krijgt 403, niet 401: hij IS ingelogd, hij mag er
   alleen niet bij (rood op het defect: 401).
3. Zonder sessie 401 (andere kant op: "laat iedereen door" is geen geldige oplossing van 1).
4. Met een ongeldig token 401 (idem).

**Het token is echt**: `jwt_handler.create_access_token`, dezelfde fabriek als de loginroute,
meegestuurd als `access_token`-cookie zoals de browser doet. Alleen `get_db` en
`get_current_user_dependency` zijn vervangen (de gebruikersrij komt anders uit de database); de
JWT-controle van de middleware loopt dus ongemoeid.

**Wat de opstelling uitzet, nagelopen.** Autouse in `tests/conftest.py`: `enforce_testing_env`
(TESTING=1), `_reset_global_state`, `ensure_main_thread_event_loop`, `_seed_module_snapshot`.
Geen daarvan raakt de SecurityMiddleware of zijn niveaubepaling. `ENVIRONMENT=test` is door
`tests/conftest.py` gezet; dat zet de IP-allowlist uit (`_is_development_mode`) maar NIET de
niveaucontrole die hier faalt (de draaiende stack staat op `development` en geeft dezelfde 401).
Geen conftest in `tests/unit/debiteuren/`. `ENABLE_SECURITY_MIDDLEWARE` wordt expliciet op `true`
gezet, zodat een shellwaarde de meting niet uitzet.

**Wat dit NIET meet.** (1) De gebruikersrij/rollen uit de database (de gebruiker is vervangen).
(2) `_resolve_tenant_id` heeft een `if TESTING`-tak. (3) PostgreSQL/RLS.

**Contract met de bouwer**: `SecurityMiddleware` mag een `/admin`-pad niet op tokenniveau
weigeren; de rolcontrole is van `require_admin_role` (403). Zonder token of met een ongeldig
token blijft 401.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from src.core.api.router_registry import register_all_routers
from src.core.api.v1.receivables.dependencies import ReceivableRepository, schrijf_debiteur_audit
from src.core.auth.api_deps import get_current_user_dependency
from src.core.auth.auth_service import UserResponse
from src.core.auth.jwt_handler import jwt_handler
from src.core.database.database import get_db
from src.core.models.rbac_models import Tenant

TENANT = 1
PADEN = ["/api/v1/admin/logs", "/admin/logs"]


def _token(rollen: list[str]) -> str:
    return jwt_handler.create_access_token(
        {"sub": "beheer@klant.example", "tenant_id": TENANT, "roles": rollen}
    )


def _app(db: AsyncSession, rollen: list[str]) -> FastAPI:
    from src.main import create_app

    app = create_app(testing=True)
    register_all_routers(app)
    gebruiker = UserResponse(id=7, email="beheer@klant.example", tenant_id=TENANT, roles=rollen)

    async def _db() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user_dependency] = lambda: gebruiker
    return app


async def _haal(app: FastAPI, pad: str, cookie: str | None) -> tuple[int, dict[str, object]]:
    cookies = {"access_token": cookie} if cookie is not None else None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", cookies=cookies
    ) as client:
        antwoord = await client.get(pad, params={"limit": "100"})
    try:
        return antwoord.status_code, antwoord.json()
    except ValueError:
        return antwoord.status_code, {}


@pytest_asyncio.fixture
async def stand(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncSession:
    monkeypatch.setenv("ENABLE_SECURITY_MIDDLEWARE", "true")
    db_session.add(Tenant(id=TENANT, name="T1", slug="deb-mw-1"))
    await db_session.commit()
    await schrijf_debiteur_audit(
        ReceivableRepository(db_session),
        event_type="receivable_status_changed",
        user_id=7,
        tenant_id=TENANT,
        receivable_id=11,
        details={"old_status": "open", "new_status": "herinnerd", "reden": None},
    )
    return db_session


@pytest.mark.unit
@pytest.mark.asyncio
class TestLogboekDoorDeMiddlewareketen:
    @pytest.mark.parametrize("pad", PADEN)
    async def test_een_beheerder_met_een_geldige_sessie_krijgt_de_regels(
        self, stand: AsyncSession, pad: str
    ) -> None:
        status, inhoud = await _haal(_app(stand, ["admin"]), pad, _token(["admin"]))

        assert (status, [r["event_type"] for r in inhoud.get("recent_logs", [])]) == (  # type: ignore[attr-defined]
            200,
            ["receivable_status_changed"],
        )

    @pytest.mark.parametrize("pad", PADEN)
    async def test_een_ingelogde_niet_beheerder_krijgt_403_en_geen_401(
        self, stand: AsyncSession, pad: str
    ) -> None:
        status, _ = await _haal(_app(stand, ["user"]), pad, _token(["user"]))

        assert status == 403

    @pytest.mark.parametrize("pad", PADEN)
    async def test_zonder_sessie_is_het_401(self, stand: AsyncSession, pad: str) -> None:
        status, _ = await _haal(_app(stand, ["admin"]), pad, None)

        assert status == 401

    @pytest.mark.parametrize("pad", PADEN)
    async def test_met_een_ongeldig_token_is_het_401(self, stand: AsyncSession, pad: str) -> None:
        status, _ = await _haal(_app(stand, ["admin"]), pad, "geen.echt.token")

        assert status == 401


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
