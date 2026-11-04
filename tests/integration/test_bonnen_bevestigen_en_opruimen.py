"""Bonlezer dag 4: bevestigen, de auditregel, de 30-dagenopruiming en de stap in het pakket.

Echte app-stack, echte Postgres op netwerkpoort 5455, de echte rolzaaier en de echte rechtencontrole;
vervangen zijn alleen `get_current_user`, de databasesessie, de CSRF-controle en de wachtrij (de echte
`verwerk_opdracht` met een nagemaakte lezer, zoals in `test_bonlezer_upload.py`).

Wat dit vaststelt:

1. Wie `receipts:write` heeft mag bevestigen; een jokerleesrecht (`*:read`) en een gebruiker zonder
   bonrecht niet (403).
2. Bevestigen schrijft een auditregel `bon_bevestigd` met wie, welke tenant en welk bestand, en NIET de
   gegevens van de bon.
3. Alleen bevestigde bonnen komen in de export en in de samenvatting voor het pakket.
4. Tenant B kan de bon van tenant A niet bevestigen (404) en ziet hem niet in de lijst.
5. De opruiming haalt bonnen van 31 dagen weg en laat die van 29 dagen staan, per tenant geteld, en laat
   de bevestigde velden staan.
6. De receiptscanner-stap van het pakket telt wat de medewerker bevestigde, ook na de opruiming.

Wat NIET gemeten is: een draaiende worker of scheduler in een container, Redis, een echte JWT-controle en
de echte Dramatiq-wachtrij voor de opruiming (de actor zelf is in `tests/unit/tasks/` getoetst).
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from dramatiq.results import ResultMissing
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.als.bonlezer.bevestiging import BonBevestiging
from src.core.als.bonlezer.opruimen import ruim_op
from src.core.als.bonlezer.upload import BonDienst
from src.core.als.bonlezer.worker import verwerk_opdracht
from src.core.models.rbac_models import Role, RolePermission, User, user_roles
from src.core.services.rbac_service import RBACService

TENANT = 1
ANDERE_TENANT = 2
BONNEN = "/api/v1/bonnen"
PDF = b"%PDF-1.4\n% een proefbestand\n"
# Het kwartaal van de testbon (datum hieronder). Zonder dit kiest de pakketstap het VORIGE afgesloten kwartaal
# (f838542c, 2026-10-19), dus de uitslag hing van de kalender af: tot 2026-10-01 viel de bon in dat kwartaal en
# daarna niet meer (gemeten 2026-10-26: aantal 0 waar 1 verwacht). Een vast kwartaal haalt de klok eruit.
KWARTAAL_VAN_DE_BON = "2026-Q4"
VELDEN = {
    "leverancier": "Bakkerij De Korenaar B.V.",
    "datum": "2026-10-01",
    "totaal": "12.10",
    "factuurnummer": "F-2026-001",
    "btw": {"21": "2.10"},
    "btw_nummer": "NL123456789B01",
    "kvk_nummer": "12345678",
}


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
    from src.core.api.v1.bonnen.dependencies import get_bon_bevestiging, get_bon_dienst
    from src.core.auth.auth_service import UserResponse
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_db

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _geen_csrf() -> None:
        return None

    gebruiker = UserResponse(id=user_id, email=email, tenant_id=tenant_id, roles=["user"])
    dienst = BonDienst(worker.root, verstuur=worker.verstuur, haal=worker.haal)
    bevestiging = BonBevestiging(worker.root)
    overrides: dict[Any, Any] = {
        get_db: _db,
        api_get_db: _db,
        get_current_user: lambda: gebruiker,
        validate_csrf_token: _geen_csrf,
        get_bon_dienst: lambda: dienst,
        get_bon_bevestiging: lambda: bevestiging,
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
def worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _NagemaakteWorker:
    # De receiptscanner-stap leest dezelfde map als de routes.
    monkeypatch.setenv("BONLEZER_UPLOAD_ROOT", str(tmp_path))
    return _NagemaakteWorker(tmp_path)


def _fixture_voor(rollen: list[str], naam: str, tenant_id: int = TENANT) -> Any:
    @pytest_asyncio.fixture
    async def _f(
        integration_app: Any, sessie: AsyncSession, worker: _NagemaakteWorker
    ) -> AsyncGenerator[AsyncClient, None]:
        email = f"{naam}-bev@integration.test"
        user_id = await _gebruiker(sessie, email, tenant_id, rollen)
        async for client in _client(
            integration_app, sessie, worker, user_id=user_id, email=email, tenant_id=tenant_id
        ):
            yield client

    return _f


medewerker = _fixture_voor(["user"], "usr")


async def _met_recht(
    app: Any,
    sessie: AsyncSession,
    worker: _NagemaakteWorker,
    rolnaam: str,
    resource: str,
    actie: str,
) -> AsyncGenerator[AsyncClient, None]:
    rol = Role(tenant_id=TENANT, name=rolnaam, description="test", is_active=True)
    sessie.add(rol)
    await sessie.flush()
    sessie.add(RolePermission(role_id=rol.id, tenant_id=TENANT, resource=resource, action=actie))
    await sessie.commit()
    email = f"{rolnaam}@integration.test"
    user_id = await _gebruiker(sessie, email, TENANT, [rolnaam])
    async for client in _client(
        app, sessie, worker, user_id=user_id, email=email, tenant_id=TENANT
    ):
        yield client


@pytest_asyncio.fixture
async def alles_lezen(
    integration_app: Any, sessie: AsyncSession, worker: _NagemaakteWorker
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _met_recht(integration_app, sessie, worker, "alles-lezen-bev", "*", "read"):
        yield client


@pytest_asyncio.fixture
async def zonder_recht(
    integration_app: Any, sessie: AsyncSession, worker: _NagemaakteWorker
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _met_recht(integration_app, sessie, worker, "zonder-bev", "agents", "read"):
        yield client


def _pdf() -> dict[str, Any]:
    return {"files": {"file": ("bon.pdf", BytesIO(PDF), "application/pdf")}}


async def _upload(client: AsyncClient) -> str:
    return str((await client.post(BONNEN, **_pdf())).json()["data"]["bestand_id"])


async def _bevestig(
    client: AsyncClient, bestand_id: str, velden: dict[str, object] | None = None
) -> Any:
    return await client.put(
        f"{BONNEN}/{bestand_id}/bevestiging",
        json={"velden": velden if velden is not None else VELDEN},
    )


def _maak_oud(pad: Path, dagen: int) -> None:
    tijd = (datetime.now(timezone.utc) - timedelta(days=dagen)).timestamp()
    os.utime(pad, (tijd, tijd))


async def _upload_met_leeftijd(client: AsyncClient, root: Path, tenant: int, dagen: int) -> str:
    bestand_id = await _upload(client)
    for pad in (root / str(tenant)).glob(f"{bestand_id}*"):
        _maak_oud(pad, dagen)
    return bestand_id


@pytest.mark.integration
@pytest.mark.asyncio
class TestWieMagBevestigen:
    async def test_een_medewerker_mag_bevestigen(self, medewerker: AsyncClient) -> None:
        bestand_id = await _upload(medewerker)

        antwoord = await _bevestig(medewerker, bestand_id)

        assert antwoord.status_code == 200, antwoord.text

    async def test_een_gebruiker_zonder_bonrecht_krijgt_403(
        self, zonder_recht: AsyncClient
    ) -> None:
        antwoord = await _bevestig(zonder_recht, f"{'0' * 32}.pdf")

        assert antwoord.status_code == 403, antwoord.text

    async def test_een_jokerleesrecht_mag_niet_bevestigen(self, alles_lezen: AsyncClient) -> None:
        antwoord = await _bevestig(alles_lezen, f"{'0' * 32}.pdf")

        assert antwoord.status_code == 403, antwoord.text

    async def test_een_jokerleesrecht_mag_de_lijst_wel_zien(self, alles_lezen: AsyncClient) -> None:
        antwoord = await alles_lezen.get(BONNEN)

        assert antwoord.status_code == 200, antwoord.text

    async def test_velden_die_niet_kloppen_worden_niet_bevestigd(
        self, medewerker: AsyncClient
    ) -> None:
        bestand_id = await _upload(medewerker)

        antwoord = await _bevestig(medewerker, bestand_id, {**VELDEN, "btw_nummer": "NL12B01"})

        assert antwoord.status_code == 422, antwoord.text

    async def test_een_tenant_in_de_body_is_een_422(self, medewerker: AsyncClient) -> None:
        bestand_id = await _upload(medewerker)

        antwoord = await medewerker.put(
            f"{BONNEN}/{bestand_id}/bevestiging", json={"velden": VELDEN, "tenant_id": 2}
        )

        assert antwoord.status_code == 422, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeAuditregel:
    async def test_bevestigen_schrijft_een_regel_met_wie_en_welke_bon(
        self, medewerker: AsyncClient, sessie: AsyncSession
    ) -> None:
        from src.core.governance.models import AuditLog

        bestand_id = await _upload(medewerker)
        await _bevestig(medewerker, bestand_id)

        regel = (
            await sessie.execute(
                select(AuditLog).where(
                    AuditLog.event_type == "bon_bevestigd", AuditLog.tenant_id == TENANT
                )
            )
        ).scalar_one()

        assert (regel.user_id is not None, regel.event_metadata) == (
            True,
            {"bestand_id": bestand_id},
        )

    async def test_de_regel_bevat_de_gegevens_van_de_bon_niet(
        self, medewerker: AsyncClient, sessie: AsyncSession
    ) -> None:
        from src.core.governance.models import AuditLog

        bestand_id = await _upload(medewerker)
        await _bevestig(medewerker, bestand_id)

        regel = (
            await sessie.execute(select(AuditLog).where(AuditLog.event_type == "bon_bevestigd"))
        ).scalar_one()

        assert "Korenaar" not in str(regel.event_metadata) + str(regel.description)


@pytest.mark.integration
@pytest.mark.asyncio
class TestAlleenBevestigdGaatVerder:
    async def test_een_bon_die_niet_is_bevestigd_staat_niet_in_de_export(
        self, medewerker: AsyncClient
    ) -> None:
        await _upload(medewerker)

        antwoord = await medewerker.get(f"{BONNEN}/bevestigd.csv")

        assert len(antwoord.text.strip().splitlines()) == 1, antwoord.text

    async def test_een_bevestigde_bon_staat_in_de_export(self, medewerker: AsyncClient) -> None:
        bestand_id = await _upload(medewerker)
        await _bevestig(medewerker, bestand_id)

        antwoord = await medewerker.get(f"{BONNEN}/bevestigd.csv")

        assert "Bakkerij De Korenaar B.V." in antwoord.text

    async def test_de_lijst_toont_de_bon_als_bevestigd_na_bevestigen(
        self, medewerker: AsyncClient
    ) -> None:
        bestand_id = await _upload(medewerker)
        await _bevestig(medewerker, bestand_id)

        items = (await medewerker.get(BONNEN)).json()["data"]["items"]

        assert [(i["bestand_id"], i["bevestigd"]) for i in items] == [(bestand_id, True)]

    async def test_de_stap_van_het_pakket_telt_de_bevestigde_bon(
        self, medewerker: AsyncClient
    ) -> None:
        from src.core.als.agents.skills.receiptscanner import ReceiptScannerSkill

        bestand_id = await _upload(medewerker)
        await _bevestig(medewerker, bestand_id)

        resultaat = await ReceiptScannerSkill(tenant_id=TENANT).execute_with_manifest_prompt({"input": {"kwartaal": KWARTAAL_VAN_DE_BON}})

        assert resultaat.result_data == {
            "kwartaal": KWARTAAL_VAN_DE_BON,
            "aantal": 1,
            "totaal": "12.10",
            "btw": {"21": "2.10"},
        }

    async def test_de_stap_van_het_pakket_telt_een_niet_bevestigde_bon_niet(
        self, medewerker: AsyncClient
    ) -> None:
        from src.core.als.agents.skills.receiptscanner import ReceiptScannerSkill

        await _upload(medewerker)

        resultaat = await ReceiptScannerSkill(tenant_id=TENANT).execute_with_manifest_prompt({"input": {"kwartaal": KWARTAAL_VAN_DE_BON}})

        assert (resultaat.success, (resultaat.result_data or {}).get("aantal")) == (True, 0)


@pytest.mark.integration
@pytest.mark.asyncio
class TestTenantIsolatie:
    async def test_tenant_b_kan_de_bon_van_tenant_a_niet_bevestigen(
        self,
        integration_app: Any,
        sessie: AsyncSession,
        worker: _NagemaakteWorker,
        medewerker: AsyncClient,
    ) -> None:
        bestand_id = await _upload(medewerker)
        email = "andere-tenant-bev@integration.test"
        user_id = await _gebruiker(sessie, email, ANDERE_TENANT, ["user"])

        statussen: list[int] = []
        async for client in _client(
            integration_app, sessie, worker, user_id=user_id, email=email, tenant_id=ANDERE_TENANT
        ):
            statussen.append((await _bevestig(client, bestand_id)).status_code)
            statussen.append(len((await client.get(BONNEN)).json()["data"]["items"]))

        assert statussen == [404, 0]

    async def test_een_bevestiging_van_tenant_b_telt_niet_mee_voor_tenant_a(
        self,
        integration_app: Any,
        sessie: AsyncSession,
        worker: _NagemaakteWorker,
    ) -> None:
        from src.core.als.agents.skills.receiptscanner import ReceiptScannerSkill

        email = "andere-tenant-bev2@integration.test"
        user_id = await _gebruiker(sessie, email, ANDERE_TENANT, ["user"])
        async for client in _client(
            integration_app, sessie, worker, user_id=user_id, email=email, tenant_id=ANDERE_TENANT
        ):
            await _bevestig(client, await _upload(client))

        resultaat = await ReceiptScannerSkill(tenant_id=TENANT).execute_with_manifest_prompt({"input": {"kwartaal": KWARTAAL_VAN_DE_BON}})

        assert (resultaat.result_data or {}).get("aantal") == 0


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeOpruimingNaDertigDagen:
    async def test_een_bon_van_31_dagen_wordt_verwijderd(
        self, medewerker: AsyncClient, worker: _NagemaakteWorker
    ) -> None:
        bestand_id = await _upload_met_leeftijd(medewerker, worker.root, TENANT, 31)

        ruim_op(worker.root)

        assert (worker.root / str(TENANT) / bestand_id).exists() is False

    async def test_het_metabestand_van_een_bon_van_31_dagen_wordt_ook_verwijderd(
        self, medewerker: AsyncClient, worker: _NagemaakteWorker
    ) -> None:
        bestand_id = await _upload_met_leeftijd(medewerker, worker.root, TENANT, 31)

        ruim_op(worker.root)

        assert (worker.root / str(TENANT) / f"{bestand_id}.meta.json").exists() is False

    async def test_een_bon_van_29_dagen_blijft_staan(
        self, medewerker: AsyncClient, worker: _NagemaakteWorker
    ) -> None:
        bestand_id = await _upload_met_leeftijd(medewerker, worker.root, TENANT, 29)

        ruim_op(worker.root)

        assert (worker.root / str(TENANT) / bestand_id).exists() is True

    async def test_het_aantal_wordt_per_tenant_geteld(
        self,
        integration_app: Any,
        sessie: AsyncSession,
        worker: _NagemaakteWorker,
        medewerker: AsyncClient,
    ) -> None:
        await _upload_met_leeftijd(medewerker, worker.root, TENANT, 31)
        await _upload_met_leeftijd(medewerker, worker.root, TENANT, 40)
        email = "andere-tenant-opr@integration.test"
        user_id = await _gebruiker(sessie, email, ANDERE_TENANT, ["user"])
        async for client in _client(
            integration_app, sessie, worker, user_id=user_id, email=email, tenant_id=ANDERE_TENANT
        ):
            await _upload_met_leeftijd(client, worker.root, ANDERE_TENANT, 35)

        assert ruim_op(worker.root) == {TENANT: 2, ANDERE_TENANT: 1}

    async def test_de_bevestigde_velden_blijven_na_de_opruiming_bij_de_samenvatting(
        self, medewerker: AsyncClient, worker: _NagemaakteWorker
    ) -> None:
        from src.core.als.agents.skills.receiptscanner import ReceiptScannerSkill

        bestand_id = await _upload(medewerker)
        await _bevestig(medewerker, bestand_id)
        for pad in (worker.root / str(TENANT)).glob(f"{bestand_id}*"):
            if not pad.name.endswith(".bevestigd.json"):
                _maak_oud(pad, 31)

        ruim_op(worker.root)
        resultaat = await ReceiptScannerSkill(tenant_id=TENANT).execute_with_manifest_prompt({"input": {"kwartaal": KWARTAAL_VAN_DE_BON}})

        assert (worker.root / str(TENANT) / bestand_id).exists() is False
        assert (resultaat.result_data or {}).get("aantal") == 1
