"""Het logboekscherm krijgt zijn regels: `GET /api/v1/admin/logs` -- Keten B dag 4, defect 2.

Het scherm (`frontend/src/pages/AuditLogs.tsx`) vroeg `/admin/logs`; de Vite-proxy stuurt alleen
`/api` door en het scherm bleef dus leeg. Gemeten op 455e400b met `register_all_routers` op een
verse app: de route staat op `/admin/logs` (de adminrouter wordt zonder `/api/v1` aangehaakt,
`src/core/api/registries/auth_admin.py`), en `/api/v1/admin/logs` bestaat niet. Een scherm dat het
juiste pad vraagt, krijgt dus een 404 zolang de backend dat pad niet aanbiedt.

Wat hier gemeten wordt, per vraag (techniek tussen haakjes):

1. De route `GET /api/v1/admin/logs` bestaat in de echte routerregistratie (structuur, geen tekst).
2. Een beheerder krijgt via dat pad de debiteurenregels van zijn EIGEN tenant: de regel van een
   statuswijziging (`receivable_status_changed`) EN die van de escalatie
   (`debiteuren_dossier_geescaleerd`) (EP: twee soorten producent).
3. De regels van een andere tenant staan er NIET in (tenantisolatie, andere kant op).
4. Een niet-beheerder krijgt 403 (EP: gebruiker zonder adminrol) -- "iedereen mag alles lezen"
   is geen geldige oplossing voor 2.
5. Het filter `event_type` werkt over de echte regels.

**De regels komen van de ECHTE producenten**, niet uit eigen invoer: `schrijf_debiteur_audit`
(de schrijver van de router bij een statuswijziging, `log_event`) en `_log_escalatie` (de schrijver
van de actor, `log_action`). Zo toetst de test ook dat de leeskant overweg kan met wat de
schrijfkant werkelijk opslaat.

**Systeemgrens.** Echte app-routering en echte afhankelijkheid `require_admin_role` (de rol wordt
echt gecontroleerd: alleen `get_current_user` is vervangen door een vaste gebruiker), echte
SQLite-sessie met `create_all`. De tenant komt uit de gebruiker (`_resolve_tenant_id`).

**Wat de opstelling uitzet, nagelopen.** Autouse in `tests/conftest.py`: `enforce_testing_env`
(TESTING=1), `_reset_global_state`, `ensure_main_thread_event_loop`, `_seed_module_snapshot`.
Geen daarvan raakt routering, de rolcontrole of de auditregels. Geen conftest in
`tests/unit/debiteuren/`. Er is niets gepatcht op de auditdienst of de router.

**Wat dit NIET meet.** (1) `_resolve_tenant_id` heeft een `if TESTING`-tak (haalt de tenant uit
de gebruiker in plaats van uit de ContextVar van de middleware): het ContextVar-pad van
productie is hier dus niet bewaakt. (2) De JWT-middleware en het cookie. (3) PostgreSQL/RLS.

**Contract met de bouwer** (nog niet bestaand, dus rood): `GET /api/v1/admin/logs` met dezelfde
parameters en hetzelfde antwoord als `GET /admin/logs` (`recent_logs` met `event_type`, `message`,
`severity`, `timestamp`; `count`). Het oude pad mag blijven bestaan.
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
from src.core.database.database import get_db
from src.core.models.rbac_models import Tenant

PAD = "/api/v1/admin/logs"
EIGEN, ANDER = 1, 2


def _gebruiker(tenant_id: int, rollen: list[str]) -> UserResponse:
    return UserResponse(id=7, email="beheer@klant.example", tenant_id=tenant_id, roles=rollen)


def _app(db: AsyncSession, gebruiker: UserResponse) -> FastAPI:
    app = FastAPI()
    register_all_routers(app)

    async def _db() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user_dependency] = lambda: gebruiker
    return app


async def _haal(app: FastAPI, pad: str = PAD, **params: object) -> tuple[int, dict[str, object]]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        antwoord = await client.get(pad, params={k: str(v) for k, v in params.items()})
    try:
        return antwoord.status_code, antwoord.json()
    except ValueError:
        return antwoord.status_code, {}


def _soorten(inhoud: dict[str, object]) -> list[str]:
    regels = inhoud.get("recent_logs")
    assert isinstance(regels, list), f"geen recent_logs in het antwoord: {inhoud!r}"
    return sorted(str(r["event_type"]) for r in regels)


@pytest_asyncio.fixture
async def stand(db_session: AsyncSession) -> AsyncSession:
    """Twee tenants met elk een statuswijziging en een escalatie, geschreven door de producenten."""
    from src.core.tasks.debiteuren_tasks import _log_escalatie

    db_session.add(Tenant(id=EIGEN, name="T1", slug="deb-logboek-1"))
    db_session.add(Tenant(id=ANDER, name="T2", slug="deb-logboek-2"))
    await db_session.commit()
    repo = ReceivableRepository(db_session)
    for tenant_id, rij_id in ((EIGEN, 11), (ANDER, 22)):
        await schrijf_debiteur_audit(
            repo,
            event_type="receivable_status_changed",
            user_id=7,
            tenant_id=tenant_id,
            receivable_id=rij_id,
            details={"old_status": "open", "new_status": "herinnerd", "reden": None},
        )
        await _log_escalatie(db_session, rij_id, tenant_id)
    return db_session


@pytest.mark.unit
@pytest.mark.asyncio
class TestLogboekEndpoint:
    async def test_de_route_staat_onder_api_v1(self) -> None:
        app = FastAPI()
        register_all_routers(app)

        routes = {
            (getattr(r, "path", ""), m)
            for r in app.routes
            for m in (getattr(r, "methods", None) or [])
        }
        assert (PAD, "GET") in routes

    async def test_een_beheerder_krijgt_de_statuswijziging_en_de_escalatie_van_de_eigen_tenant(
        self, stand: AsyncSession
    ) -> None:
        status, inhoud = await _haal(_app(stand, _gebruiker(EIGEN, ["admin"])))

        assert (status, _soorten(inhoud)) == (
            200,
            ["debiteuren_dossier_geescaleerd", "receivable_status_changed"],
        )

    async def test_de_regels_van_een_andere_tenant_staan_er_niet_in(
        self, stand: AsyncSession
    ) -> None:
        _, inhoud = await _haal(_app(stand, _gebruiker(EIGEN, ["admin"])))

        regels = inhoud["recent_logs"]
        assert isinstance(regels, list)
        assert [r["message"] for r in regels if "22" in str(r["message"])] == []

    async def test_de_andere_tenant_ziet_zijn_eigen_regels_en_niet_die_van_de_eerste(
        self, stand: AsyncSession
    ) -> None:
        """Andere kant op: "geef niets terug" is geen geldige manier om te isoleren."""
        _, inhoud = await _haal(_app(stand, _gebruiker(ANDER, ["admin"])))

        regels = inhoud["recent_logs"]
        assert isinstance(regels, list)
        assert (
            len(regels),
            [r["message"] for r in regels if "debiteur 11" in str(r["message"])],
        ) == (2, [])

    async def test_een_gebruiker_zonder_adminrol_krijgt_403(self, stand: AsyncSession) -> None:
        status, _ = await _haal(_app(stand, _gebruiker(EIGEN, ["user"])))

        assert status == 403

    async def test_het_filter_op_soort_geeft_alleen_die_soort(self, stand: AsyncSession) -> None:
        _, inhoud = await _haal(
            _app(stand, _gebruiker(EIGEN, ["admin"])), event_type="debiteuren_dossier_geescaleerd"
        )

        assert _soorten(inhoud) == ["debiteuren_dossier_geescaleerd"]
