"""Bonlezer dag 3: een bon uploaden en laten lezen, met de echte rechtencontrole (ADR-039).

Echte app-stack, echte Postgres op netwerkpoort 5455, de echte rolzaaier en de echte rechtencontrole.
Vervangen zijn alleen `get_current_user`, de databasesessie, de CSRF-controle en de wachtrij: de
"worker" is hier de ECHTE `verwerk_opdracht` van de bonlezer-worker met een nagemaakte lezer (geen
Docling), die direct bij het versturen draait. Zo toetst de backend een resultaat dat de echte
producent oplevert, niet een dict die de test zelf verzon.

Wat dit vaststelt:

1. Een gebruiker met rol `user` of `editor` mag uploaden en lezen (`receipts:write`, `receipts:read`);
   wie dat recht niet heeft (ook met `*:read`) krijgt 403.
2. De uploader ziet de uitkomst van de worker met de velden.
3. Tenant B ziet de bon van tenant A niet (404).

Wat NIET gemeten is: een draaiende worker in zijn container (dat doet `scripts/bonlezer/meet_upload.sh`),
Redis, en een echte JWT-controle.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from dramatiq.results import ResultMissing
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.als.bonlezer.upload import BonDienst
from src.core.als.bonlezer.worker import verwerk_opdracht
from src.core.models.rbac_models import Role, RolePermission, User, user_roles
from src.core.services.rbac_service import RBACService

TENANT = 1
ANDERE_TENANT = 2
BONNEN = "/api/v1/bonnen"
PDF = b"%PDF-1.4\n% een proefbestand\n"


class _Lezer:
    def lees(self, pad: Path) -> str:
        return "TOTAAL 12,10\nBTW 21%  2,10\n"


class _NagemaakteWorker:
    """Verstuurt niet naar Redis maar laat de echte `verwerk_opdracht` meteen lopen."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.resultaten: dict[str, dict[str, object]] = {}

    def verstuur(self, tenant_id: int, bestand_id: str) -> str:
        bericht_id = f"bericht-{len(self.resultaten) + 1}"
        self.resultaten[bericht_id] = verwerk_opdracht(
            self.root, tenant_id, bestand_id, lezer=_Lezer()
        )
        return bericht_id

    def haal(self, bericht_id: str) -> dict[str, object]:
        if bericht_id not in self.resultaten:
            raise ResultMissing(bericht_id)  # type: ignore[call-arg]
        return self.resultaten[bericht_id]


async def _gebruiker(session: AsyncSession, email: str, tenant_id: int, rollen: list[str]) -> int:
    gebruiker = User(
        email=email, hashed_password="x", tenant_id=tenant_id, is_active=True, is_superuser=False
    )
    session.add(gebruiker)
    await session.flush()
    for naam in rollen:
        rol = (
            await session.execute(
                select(Role).where(Role.name == naam, Role.tenant_id == tenant_id)
            )
        ).scalar_one()
        await session.execute(
            user_roles.insert().values(user_id=gebruiker.id, role_id=rol.id, tenant_id=tenant_id)
        )
    await session.commit()
    return int(gebruiker.id)


async def _client(
    app: Any,
    session: AsyncSession,
    worker: _NagemaakteWorker,
    *,
    user_id: int,
    email: str,
    tenant_id: int,
) -> AsyncGenerator[AsyncClient, None]:
    from tests.integration.conftest import _build_test_token

    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.api.v1.bonnen.dependencies import get_bon_dienst
    from src.core.auth.auth_service import UserResponse
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_db

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _geen_csrf() -> None:
        return None

    gebruiker = UserResponse(id=user_id, email=email, tenant_id=tenant_id, roles=["user"])
    dienst = BonDienst(worker.root, verstuur=worker.verstuur, haal=worker.haal)
    overrides: dict[Any, Any] = {
        get_db: _db,
        api_get_db: _db,
        get_current_user: lambda: gebruiker,
        validate_csrf_token: _geen_csrf,
        get_bon_dienst: lambda: dienst,
    }
    app.dependency_overrides.update(overrides)
    token = _build_test_token(user_id=user_id, email=email, tenant_id=tenant_id)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client
    finally:
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)


@pytest_asyncio.fixture
async def sessie(postgres_session: AsyncSession) -> AsyncSession:
    await RBACService(postgres_session).ensure_default_roles(TENANT)
    await RBACService(postgres_session).ensure_default_roles(ANDERE_TENANT)
    return postgres_session


@pytest.fixture
def worker(tmp_path: Path) -> _NagemaakteWorker:
    return _NagemaakteWorker(tmp_path)


def _fixture_voor(rollen: list[str], naam: str, tenant_id: int = TENANT) -> Any:
    @pytest_asyncio.fixture
    async def _f(
        integration_app: Any, sessie: AsyncSession, worker: _NagemaakteWorker
    ) -> AsyncGenerator[AsyncClient, None]:
        email = f"{naam}-bon@integration.test"
        user_id = await _gebruiker(sessie, email, tenant_id, rollen)
        async for client in _client(
            integration_app, sessie, worker, user_id=user_id, email=email, tenant_id=tenant_id
        ):
            yield client

    return _f


medewerker = _fixture_voor(["user"], "usr")
redacteur = _fixture_voor(["editor"], "edt")
beheerder = _fixture_voor(["admin"], "adm")


@pytest_asyncio.fixture
async def alles_lezen(
    integration_app: Any, sessie: AsyncSession, worker: _NagemaakteWorker
) -> AsyncGenerator[AsyncClient, None]:
    rol = Role(tenant_id=TENANT, name="alles-lezen-bon", description="test", is_active=True)
    sessie.add(rol)
    await sessie.flush()
    sessie.add(RolePermission(role_id=rol.id, tenant_id=TENANT, resource="*", action="read"))
    await sessie.commit()
    email = "alles-lezen-bon@integration.test"
    user_id = await _gebruiker(sessie, email, TENANT, ["alles-lezen-bon"])
    async for client in _client(
        integration_app, sessie, worker, user_id=user_id, email=email, tenant_id=TENANT
    ):
        yield client


@pytest_asyncio.fixture
async def zonder_recht(
    integration_app: Any, sessie: AsyncSession, worker: _NagemaakteWorker
) -> AsyncGenerator[AsyncClient, None]:
    rol = Role(tenant_id=TENANT, name="zonder-bon", description="test", is_active=True)
    sessie.add(rol)
    await sessie.flush()
    sessie.add(RolePermission(role_id=rol.id, tenant_id=TENANT, resource="agents", action="read"))
    await sessie.commit()
    email = "zonder-bon@integration.test"
    user_id = await _gebruiker(sessie, email, TENANT, ["zonder-bon"])
    async for client in _client(
        integration_app, sessie, worker, user_id=user_id, email=email, tenant_id=TENANT
    ):
        yield client


def _pdf() -> dict[str, Any]:
    return {"files": {"file": ("bon.pdf", BytesIO(PDF), "application/pdf")}}


@pytest.mark.integration
@pytest.mark.asyncio
class TestWieMagWat:
    async def test_een_medewerker_mag_een_bon_uploaden(self, medewerker: AsyncClient) -> None:
        antwoord = await medewerker.post(BONNEN, **_pdf())

        assert antwoord.status_code == 201, antwoord.text

    async def test_een_redacteur_mag_een_bon_uploaden(self, redacteur: AsyncClient) -> None:
        antwoord = await redacteur.post(BONNEN, **_pdf())

        assert antwoord.status_code == 201, antwoord.text

    async def test_een_beheerder_mag_een_bon_uploaden(self, beheerder: AsyncClient) -> None:
        antwoord = await beheerder.post(BONNEN, **_pdf())

        assert antwoord.status_code == 201, antwoord.text

    async def test_een_gebruiker_zonder_bonrecht_krijgt_403_bij_uploaden(
        self, zonder_recht: AsyncClient
    ) -> None:
        antwoord = await zonder_recht.post(BONNEN, **_pdf())

        assert antwoord.status_code == 403, antwoord.text

    async def test_een_gebruiker_zonder_bonrecht_krijgt_403_bij_opvragen(
        self, zonder_recht: AsyncClient
    ) -> None:
        antwoord = await zonder_recht.get(f"{BONNEN}/{'0' * 32}.pdf")

        assert antwoord.status_code == 403, antwoord.text

    async def test_een_jokerleesrecht_mag_niet_uploaden(self, alles_lezen: AsyncClient) -> None:
        antwoord = await alles_lezen.post(BONNEN, **_pdf())

        assert antwoord.status_code == 403, antwoord.text

    async def test_een_jokerleesrecht_mag_wel_opvragen(self, alles_lezen: AsyncClient) -> None:
        """Opvragen vraagt `receipts:read`, niet `receipts:write` (404: toegestaan, maar niets gevonden)."""
        antwoord = await alles_lezen.get(f"{BONNEN}/{'0' * 32}.pdf")

        assert antwoord.status_code == 404, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeBonWordtGelezen:
    async def test_de_uploader_ziet_de_uitkomst_van_de_worker(
        self, medewerker: AsyncClient
    ) -> None:
        bestand_id = (await medewerker.post(BONNEN, **_pdf())).json()["data"]["bestand_id"]

        antwoord = await medewerker.get(f"{BONNEN}/{bestand_id}")

        assert antwoord.json()["data"]["status"] == "gelezen", antwoord.text

    async def test_de_uitkomst_bevat_de_velden_die_de_worker_las(
        self, medewerker: AsyncClient
    ) -> None:
        bestand_id = (await medewerker.post(BONNEN, **_pdf())).json()["data"]["bestand_id"]

        data = (await medewerker.get(f"{BONNEN}/{bestand_id}")).json()["data"]

        assert data["velden"]["totaal"] == "12.10"

    async def test_een_onbekend_bestand_geeft_404(self, medewerker: AsyncClient) -> None:
        antwoord = await medewerker.get(f"{BONNEN}/{'0' * 32}.pdf")

        assert antwoord.status_code == 404, antwoord.text

    async def test_een_bestand_van_het_verkeerde_soort_wordt_geweigerd(
        self, medewerker: AsyncClient
    ) -> None:
        antwoord = await medewerker.post(
            BONNEN, files={"file": ("bon.exe", BytesIO(PDF), "application/octet-stream")}
        )

        assert antwoord.status_code == 415, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestTenantIsolatie:
    async def test_tenant_b_ziet_de_bon_van_tenant_a_niet(
        self,
        integration_app: Any,
        sessie: AsyncSession,
        worker: _NagemaakteWorker,
        medewerker: AsyncClient,
    ) -> None:
        bestand_id = (await medewerker.post(BONNEN, **_pdf())).json()["data"]["bestand_id"]
        email = "andere-tenant-bon@integration.test"
        user_id = await _gebruiker(sessie, email, ANDERE_TENANT, ["user"])

        statussen: list[int] = []
        async for client in _client(
            integration_app, sessie, worker, user_id=user_id, email=email, tenant_id=ANDERE_TENANT
        ):
            statussen.append((await client.get(f"{BONNEN}/{bestand_id}")).status_code)

        assert statussen == [404]

    async def test_de_bon_staat_in_de_map_van_de_tenant_van_de_gebruiker(
        self, medewerker: AsyncClient, worker: _NagemaakteWorker
    ) -> None:
        bestand_id = (await medewerker.post(BONNEN, **_pdf())).json()["data"]["bestand_id"]

        assert (worker.root / str(TENANT) / bestand_id).read_bytes() == PDF
