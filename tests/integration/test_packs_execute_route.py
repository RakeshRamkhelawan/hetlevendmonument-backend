"""Meting: `POST /api/v1/agentic/packs/execute` -- waarborgen en echte catalogus (ADR-036 OP-09).

Echte app-stack (`register_all_routers`), echte Postgres op netwerkpoort 5455, de echte rolzaaier
`RBACService.ensure_default_roles` en de echte rolcontrole `require_resource_permission`. Vervangen
zijn alleen `get_current_user` (wijst naar de testgebruiker), de databasesessie (een sessie voor
test en route) en -- behalve in de CSRF-test -- `validate_csrf_token` (Redis-gebonden token).

De uitvoering van een stap (`DomainPackOrchestrator._execute_step`) is op de GRENS vervangen:
een gewired agent roept een LLM aan, en deze test meet de route en de orchestratie, niet het
model. Wat die stap als `params` binnenkrijgt wordt vastgelegd en getoetst.

Besluit Rakesh 2026-10-09: "een beheerder zet het pakket aan, een medewerker voert het uit". Dus
`packs:execute` zit in de standaardrollen `user` en `editor`; `admin` heeft het via `*:*`. Een rol
ZONDER dat recht (hier `alleen-lezen`, alleen `agents:read`) krijgt 403.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import Role, RolePermission, User, user_roles
from src.core.services.rbac_service import RBACService
from src.core.shared.interfaces import ExecutionResult
from src.core.types import ExecutionStatusContract

URL = "/api/v1/agentic/packs/execute"
PACK = "mkb.zero_admin"
STAPPEN_VAN_PACK = ["receiptscanner", "vatcompliance", "dunning"]
INVOER = {"factuur": "F-2026-1", "bedrag": 120}
TENANT = 1


@dataclass
class Opname:
    """Wat de vervangen stap-uitvoering heeft gezien, en welke agents hij laat mislukken."""

    aanroepen: list[dict[str, Any]] = field(default_factory=list)
    mislukt: set[str] = field(default_factory=set)


async def _gebruiker_met_rol(session: AsyncSession, rol_naam: str, email: str) -> int:
    rol = (
        await session.execute(select(Role).where(Role.name == rol_naam, Role.tenant_id == TENANT))
    ).scalar_one()
    gebruiker = User(
        email=email, hashed_password="x", tenant_id=TENANT, is_active=True, is_superuser=False
    )
    session.add(gebruiker)
    await session.flush()
    await session.execute(
        user_roles.insert().values(user_id=gebruiker.id, role_id=rol.id, tenant_id=TENANT)
    )
    await session.commit()
    return int(gebruiker.id)


async def _client(
    app: Any,
    session: AsyncSession,
    *,
    user_id: int,
    email: str,
    rollen: list[str],
    csrf: bool,
    tenant: int = TENANT,
) -> AsyncGenerator[AsyncClient, None]:
    """`csrf=True`: de echte CSRF-controle blijft staan; anders wordt hij vervangen.

    `tenant`: de klant van de gebruiker (token en `UserResponse`); standaard de eerste klant.
    """
    from tests.integration.conftest import _build_test_token

    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.auth.auth_service import UserResponse
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_db

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _geen_csrf() -> None:
        return None

    gebruiker = UserResponse(id=user_id, email=email, tenant_id=tenant, roles=rollen)
    overrides: dict[Any, Any] = {
        get_db: _db,
        api_get_db: _db,
        get_current_user: lambda: gebruiker,
    }
    if not csrf:
        overrides[validate_csrf_token] = _geen_csrf
    app.dependency_overrides.update(overrides)
    token = _build_test_token(user_id=user_id, email=email, tenant_id=tenant)
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
async def standaardrollen(postgres_session: AsyncSession) -> AsyncSession:
    """De ECHTE zaaier: dezelfde lijst die de applicatie bij de start voor elke tenant draait."""
    await RBACService(postgres_session).ensure_default_roles(TENANT)
    return postgres_session


@pytest.fixture
def stappen(monkeypatch: pytest.MonkeyPatch, postgres_session: AsyncSession) -> Opname:
    """Vervangt de uitvoering van EEN stap (LLM-grens) en legt vast wat hij binnenkrijgt."""
    from src.core.als.enterprise.packs import DomainPackOrchestrator

    opname = Opname()

    async def _stap(
        self: Any,
        agent_id: str,
        tenant_id: int,
        params: dict[str, Any],
        *,
        initiated_by_user_id: int | None = None,
    ) -> ExecutionResult:
        opname.aanroepen.append(
            {
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "params": params,
                "initiated_by_user_id": initiated_by_user_id,
                "transactie_open": postgres_session.in_transaction(),
            }
        )
        ok = agent_id not in opname.mislukt
        return ExecutionResult(
            task_id=f"taak-{agent_id}",
            success=ok,
            error_message=None if ok else "bewust mislukt",
            tenant_id=tenant_id,
            agent_id=agent_id,
            status=ExecutionStatusContract.KLAAR if ok else ExecutionStatusContract.MISLUKT,
        )

    monkeypatch.setattr(DomainPackOrchestrator, "_execute_step", _stap)
    return opname


@pytest_asyncio.fixture
async def medewerker(
    integration_app: Any, standaardrollen: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    email = "pack-medewerker@integration.test"
    user_id = await _gebruiker_met_rol(standaardrollen, "user", email)
    async for client in _client(
        integration_app, standaardrollen, user_id=user_id, email=email, rollen=["user"], csrf=False
    ):
        yield client


@pytest_asyncio.fixture
async def redacteur(
    integration_app: Any, standaardrollen: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    email = "pack-redacteur@integration.test"
    user_id = await _gebruiker_met_rol(standaardrollen, "editor", email)
    async for client in _client(
        integration_app,
        standaardrollen,
        user_id=user_id,
        email=email,
        rollen=["editor"],
        csrf=False,
    ):
        yield client


@pytest_asyncio.fixture
async def alleen_lezen(
    integration_app: Any, standaardrollen: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """Een rol met alleen `agents:read`: geen `packs:execute`."""
    rol = Role(tenant_id=TENANT, name="alleen-lezen", description="test", is_active=True)
    standaardrollen.add(rol)
    await standaardrollen.flush()
    standaardrollen.add(
        RolePermission(role_id=rol.id, tenant_id=TENANT, resource="agents", action="read")
    )
    await standaardrollen.commit()
    email = "pack-alleen-lezen@integration.test"
    user_id = await _gebruiker_met_rol(standaardrollen, "alleen-lezen", email)
    async for client in _client(
        integration_app,
        standaardrollen,
        user_id=user_id,
        email=email,
        rollen=["alleen-lezen"],
        csrf=False,
    ):
        yield client


@pytest_asyncio.fixture
async def beheerder(
    integration_app: Any, standaardrollen: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _client(
        integration_app,
        standaardrollen,
        user_id=1,
        email="admin@integration.test",
        rollen=["admin"],
        csrf=False,
    ):
        yield client


@pytest_asyncio.fixture
async def beheerder_met_echte_csrf(
    integration_app: Any, standaardrollen: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _client(
        integration_app,
        standaardrollen,
        user_id=1,
        email="admin@integration.test",
        rollen=["admin"],
        csrf=True,
    ):
        yield client


def _body(pack_id: str = PACK) -> dict[str, Any]:
    return {"pack_id": pack_id, "input_data": INVOER}


@pytest.mark.integration
@pytest.mark.asyncio
class TestWieMagUitvoeren:
    async def test_een_rol_zonder_het_recht_krijgt_403(
        self, alleen_lezen: AsyncClient, stappen: Opname
    ) -> None:
        antwoord = await alleen_lezen.post(URL, json=_body())

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json().get("detail") == "Missing permission: packs:execute", antwoord.text

    async def test_een_rol_zonder_het_recht_start_geen_enkele_stap(
        self, alleen_lezen: AsyncClient, stappen: Opname
    ) -> None:
        await alleen_lezen.post(URL, json=_body())

        assert stappen.aanroepen == []

    async def test_de_gewone_gebruiker_mag_uitvoeren(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        antwoord = await medewerker.post(URL, json=_body())

        assert antwoord.status_code == 200, antwoord.text

    async def test_de_editor_mag_uitvoeren(self, redacteur: AsyncClient, stappen: Opname) -> None:
        antwoord = await redacteur.post(URL, json=_body())

        assert antwoord.status_code == 200, antwoord.text

    async def test_de_beheerder_mag_uitvoeren(
        self, beheerder: AsyncClient, stappen: Opname
    ) -> None:
        antwoord = await beheerder.post(URL, json=_body())

        assert antwoord.status_code == 200, antwoord.text

    async def test_zonder_csrf_token_wordt_geweigerd(
        self, beheerder_met_echte_csrf: AsyncClient, stappen: Opname
    ) -> None:
        antwoord = await beheerder_met_echte_csrf.post(URL, json=_body())

        assert antwoord.status_code == 403, antwoord.text
        assert antwoord.json().get("detail") == "Missing CSRF token", antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestEchteCatalogus:
    async def test_een_onbestaand_pack_geeft_404_pack_not_found(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        antwoord = await medewerker.post(URL, json=_body("bestaat.niet.echt"))

        assert antwoord.status_code == 404, antwoord.text
        assert antwoord.json()["detail"]["code"] == "PACK_NOT_FOUND", antwoord.text

    async def test_een_onbestaand_pack_start_geen_enkele_stap(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        await medewerker.post(URL, json=_body("bestaat.niet.echt"))

        assert stappen.aanroepen == []

    async def test_de_stappen_komen_uit_de_catalogus_niet_uit_agent1_en_agent2(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        await medewerker.post(URL, json=_body())

        assert [a["agent_id"] for a in stappen.aanroepen] == STAPPEN_VAN_PACK

    async def test_de_invoer_komt_bij_elke_stap_aan(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        await medewerker.post(URL, json=_body())

        assert [a["params"].get("input") for a in stappen.aanroepen] == [INVOER] * 3

    async def test_de_klant_komt_uit_de_sessie_niet_uit_de_body(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        await medewerker.post(URL, json={**_body(), "tenant_id": 999})

        assert {a["tenant_id"] for a in stappen.aanroepen} == {TENANT}

    async def test_geen_transactie_open_tijdens_de_stappen(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        """Een run bestaat uit LLM-aanroepen; de rolcontrole mag geen verbinding vasthouden."""
        await medewerker.post(URL, json=_body())

        assert [a["transactie_open"] for a in stappen.aanroepen] == [False] * 3

    async def test_de_uitvoerende_gebruiker_komt_bij_elke_stap_aan(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        await medewerker.post(URL, json=_body())

        assert all(a["initiated_by_user_id"] is not None for a in stappen.aanroepen)


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeInvoerHeeftEenGrens:
    async def test_te_grote_invoer_geeft_422_en_start_geen_stap(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        """De invoer gaat als tekst de LLM-prompt in: een gewone gebruiker mag die niet opblazen."""
        antwoord = await medewerker.post(
            URL, json={"pack_id": PACK, "input_data": {"tekst": "x" * 60_000}}
        )

        assert antwoord.status_code == 422, antwoord.text
        assert stappen.aanroepen == []

    async def test_invoer_binnen_de_grens_wordt_aangenomen(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        antwoord = await medewerker.post(
            URL, json={"pack_id": PACK, "input_data": {"tekst": "x" * 20_000}}
        )

        assert antwoord.status_code == 200, antwoord.text


class TestLegePack:
    def test_een_run_zonder_enige_stap_is_geen_succes(self) -> None:
        from src.core.api.v1.agentic.agentic_domain_router import _naar_antwoord

        antwoord = _naar_antwoord("leeg.pack", [], sla_breached=False)

        assert (antwoord.status, antwoord.escalated_to_human) == ("failed", True)


@pytest.mark.integration
@pytest.mark.asyncio
class TestHetAntwoord:
    async def test_een_geslaagde_run_geeft_succeeded_met_de_stappen(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        antwoord = await medewerker.post(URL, json=_body())

        data = antwoord.json()
        assert data["pack_id"] == PACK
        assert data["status"] == "succeeded"
        assert [s["agent_id"] for s in data["steps"]] == STAPPEN_VAN_PACK
        assert data["steps"][0] == {
            "agent_id": "receiptscanner",
            "status": "succeeded",
            "task_id": "taak-receiptscanner",
            "error": None,
            # Sinds bonlezer dag 4: alleen de receiptscanner geeft een samenvatting vrij, en alleen als
            # het resultaat die vorm heeft (deze opname geeft geen `result_data`).
            "samenvatting": None,
        }
        assert data["sla_breached"] is False
        assert data["escalated_to_human"] is False

    async def test_een_deels_gelukte_run_blijft_200_met_partial(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        stappen.mislukt.add("vatcompliance")

        antwoord = await medewerker.post(URL, json=_body())

        data = antwoord.json()
        assert antwoord.status_code == 200, antwoord.text
        assert data["status"] == "partial"
        # Sinds het besluit van 2026-10-10 draait de stap NA een mislukte sequentiele stap niet.
        assert [s["status"] for s in data["steps"]] == ["succeeded", "failed", "skipped"]
        # Sinds 7b4e8a6e (2026-10-15) krijgt de klant bij een mislukte stap de vaste tekst en niet de technische
        # fout (`STAPFOUT_TEKST`, geen interne foutregel naar de klant); de oorzaak staat in het log.
        assert data["steps"][1]["error"] == "De stap kon niet worden uitgevoerd."
        assert data["escalated_to_human"] is False

    async def test_een_volledig_mislukte_run_blijft_200_met_failed_en_escalatie(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        stappen.mislukt.update(STAPPEN_VAN_PACK)

        antwoord = await medewerker.post(URL, json=_body())

        data = antwoord.json()
        assert antwoord.status_code == 200, antwoord.text
        assert data["status"] == "failed"
        assert data["escalated_to_human"] is True


@pytest.mark.integration
@pytest.mark.asyncio
class TestAfbrekenBijFalen:
    """Besluit regie 2026-10-10: een falende sequentiele stap breekt de keten af."""

    async def test_na_de_eerste_mislukte_stap_draait_er_niets_meer(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        stappen.mislukt.add("receiptscanner")

        antwoord = await medewerker.post(URL, json=_body())

        data = antwoord.json()
        assert [s["status"] for s in data["steps"]] == ["failed", "skipped", "skipped"]
        assert [a["agent_id"] for a in stappen.aanroepen] == ["receiptscanner"]
        assert data["status"] == "failed"
        assert data["escalated_to_human"] is True

    async def test_een_overgeslagen_stap_noemt_zijn_agent_en_welke_stap_mislukte(
        self, medewerker: AsyncClient, stappen: Opname
    ) -> None:
        stappen.mislukt.add("vatcompliance")

        antwoord = await medewerker.post(URL, json=_body())

        data = antwoord.json()
        assert [s["status"] for s in data["steps"]] == ["succeeded", "failed", "skipped"]
        overgeslagen = data["steps"][2]
        assert overgeslagen["agent_id"] == "dunning"
        # Sinds 5731019c (2026-10-15) noemt de reden het stapnummer en niet de interne agentnaam.
        assert overgeslagen["error"] == "Overgeslagen: stap 2 is mislukt"
        assert "vatcompliance" not in overgeslagen["error"]
        assert data["status"] == "partial"
        assert [a["agent_id"] for a in stappen.aanroepen] == ["receiptscanner", "vatcompliance"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestTimeOutVanDeHeleRun:
    """Bij `sla_seconds`-overschrijding toont het antwoord wat al gelopen is (regie 2026-10-10)."""

    @pytest.fixture
    def korte_sla(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`sla_seconds` heeft een ondergrens van 30; hier telt 31 als 0,3 s zodat de test snel is."""
        import asyncio

        echte_wait_for = asyncio.wait_for

        async def _wait_for(aanroep: Any, timeout: float | None) -> Any:
            return await echte_wait_for(aanroep, 0.3 if timeout == 31 else timeout)

        monkeypatch.setattr(asyncio, "wait_for", _wait_for)

    @pytest.fixture
    def trage_tweede_stap(self, monkeypatch: pytest.MonkeyPatch, stappen: Opname) -> None:
        import asyncio

        from src.core.als.enterprise.packs import DomainPackOrchestrator

        snelle_stap = DomainPackOrchestrator._execute_step

        async def _stap(self: Any, agent_id: str, *args: Any, **kwargs: Any) -> ExecutionResult:
            if agent_id == "vatcompliance":
                await asyncio.sleep(5)
            return await snelle_stap(self, agent_id, *args, **kwargs)

        monkeypatch.setattr(DomainPackOrchestrator, "_execute_step", _stap)

    async def test_de_afgeronde_stap_staat_erin_en_de_rest_is_overgeslagen(
        self, medewerker: AsyncClient, stappen: Opname, korte_sla: None, trage_tweede_stap: None
    ) -> None:
        antwoord = await medewerker.post(URL, json={**_body(), "sla_seconds": 31})

        data = antwoord.json()
        assert antwoord.status_code == 200, antwoord.text
        assert [(s["agent_id"], s["status"]) for s in data["steps"]] == [
            ("receiptscanner", "succeeded"),
            ("vatcompliance", "interrupted"),
            ("dunning", "skipped"),
        ]
        assert data["sla_breached"] is True
        assert data["status"] == "partial"

    async def test_de_onderbroken_stap_zegt_dat_hij_kan_zijn_begonnen(
        self, medewerker: AsyncClient, stappen: Opname, korte_sla: None, trage_tweede_stap: None
    ) -> None:
        antwoord = await medewerker.post(URL, json={**_body(), "sla_seconds": 31})

        onderbroken = antwoord.json()["steps"][1]
        assert onderbroken["status"] == "interrupted"
        assert "gedeeltelijk" in onderbroken["error"].lower()

    async def test_de_duur_is_de_echte_tijd(
        self, medewerker: AsyncClient, stappen: Opname, korte_sla: None, trage_tweede_stap: None
    ) -> None:
        antwoord = await medewerker.post(URL, json={**_body(), "sla_seconds": 31})

        assert 250 <= antwoord.json()["duration_ms"] < 3000

    async def test_al_het_werk_gedaan_en_alleen_het_roi_logboek_te_traag_is_geen_mislukte_run(
        self,
        medewerker: AsyncClient,
        stappen: Opname,
        korte_sla: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Elke stap is klaar en gelukt; de SLA loopt af tijdens het logboek van de laatste stap.

        Zo'n run mag niet 'failed' met een mens-escalatie heten: de klant draait hem dan
        opnieuw en doet het werk dubbel. De overschrijding blijft zichtbaar in `sla_breached`.
        """
        import asyncio

        from src.core.analytics.roi_service import ROIService

        async def _trage_roi(*_args: Any, **kwargs: Any) -> None:
            if kwargs.get("agent_id") == "dunning":  # de laatste stap van het pack
                await asyncio.sleep(5)

        monkeypatch.setattr(ROIService, "record_run", _trage_roi)

        antwoord = await medewerker.post(URL, json={**_body(), "sla_seconds": 31})

        data = antwoord.json()
        assert [s["status"] for s in data["steps"]] == ["succeeded", "succeeded", "succeeded"]
        assert (data["status"], data["sla_breached"], data["escalated_to_human"]) == (
            "succeeded",
            True,
            False,
        )

    async def test_een_gelukte_parallelle_stap_blijft_gelukt_als_zijn_buurman_wordt_afgebroken(
        self,
        medewerker: AsyncClient,
        stappen: Opname,
        korte_sla: None,
        monkeypatch: pytest.MonkeyPatch,
        standaardrollen: AsyncSession,
    ) -> None:
        """Het gat uit de review: een klaar stap uit een parallel blok ging verloren en heette
        'overgeslagen', waarna een klant het pack opnieuw draait en het werk dubbel doet."""
        import asyncio

        from src.core.als.enterprise.packs import DomainPackOrchestrator

        await _zet_pakket_aan(standaardrollen, "strategy.competitor_war_room")
        snelle_stap = DomainPackOrchestrator._execute_step

        async def _stap(self: Any, agent_id: str, *args: Any, **kwargs: Any) -> ExecutionResult:
            if agent_id == "marketintelligence":
                await asyncio.sleep(5)
            return await snelle_stap(self, agent_id, *args, **kwargs)

        monkeypatch.setattr(DomainPackOrchestrator, "_execute_step", _stap)

        antwoord = await medewerker.post(
            URL, json={"pack_id": "strategy.competitor_war_room", "input_data": {}, "sla_seconds": 31}
        )

        assert [(s["agent_id"], s["status"]) for s in antwoord.json()["steps"]] == [
            ("competitorshadow", "succeeded"),
            ("competitiveintelligence", "succeeded"),
            ("marketintelligence", "interrupted"),
        ]


@pytest.mark.integration
@pytest.mark.asyncio
class TestAuditregel:
    async def _aantal(self, sessie: AsyncSession) -> int:
        # In productie commit `get_db` aan het einde van het verzoek; hier delen route en test
        # een sessie zonder die commit, dus de wachtende auditregel moet eerst naar de database.
        await sessie.flush()
        rij = (
            await sessie.execute(
                text("SELECT count(*) FROM audit_logs WHERE action = 'pack.executed'")
            )
        ).scalar_one()
        return int(rij)

    async def test_elke_run_laat_een_auditregel_achter(
        self, medewerker: AsyncClient, standaardrollen: AsyncSession, stappen: Opname
    ) -> None:
        voor = await self._aantal(standaardrollen)

        await medewerker.post(URL, json=_body())
        await medewerker.post(URL, json=_body())

        assert await self._aantal(standaardrollen) - voor == 2

    async def test_een_geweigerde_aanvraag_laat_geen_auditregel_voor_een_run_achter(
        self, alleen_lezen: AsyncClient, standaardrollen: AsyncSession, stappen: Opname
    ) -> None:
        voor = await self._aantal(standaardrollen)

        await alleen_lezen.post(URL, json=_body())

        assert await self._aantal(standaardrollen) == voor


async def _zet_pakket_aan(sessie: AsyncSession, pack_id: str) -> None:
    """Pakket aanzetten (dag 1): een pakket draait pas nadat een beheerder het heeft aangezet."""
    await sessie.execute(
        text(
            "INSERT INTO tenant_pack_activations (tenant_id, pack_id, is_enabled) "
            "VALUES (:t, :p, true) "
            "ON CONFLICT (tenant_id, pack_id) DO UPDATE SET is_enabled = true"
        ),
        {"t": TENANT, "p": pack_id},
    )
    await sessie.commit()


@pytest_asyncio.fixture(autouse=True)
async def _pakket_staat_aan(standaardrollen: AsyncSession) -> None:
    """Deze tests meten de uitvoerroute zelf, dus het pakket staat hier aan voor de testklant.

    De controle blijft staan: dat het UIT staan werkt, meet `test_pakket_aanzetten_per_klant.py`.
    """
    await _zet_pakket_aan(standaardrollen, PACK)
