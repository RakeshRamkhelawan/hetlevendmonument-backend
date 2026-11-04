"""HR-pilot dag 1: een klant uploadt vaardigheden en ziet de kloof (ADR-039, OP-09-nazorg).

Echte app-stack, echte Postgres op netwerkpoort 5455, de echte rolzaaier
`RBACService.ensure_default_roles` en de echte rechtencontroles (`require_resource_permission` voor
de HTTP-routes, `RBACService.user_has_scope_for` voor de agent-tools). Vervangen zijn alleen
`get_current_user`, de databasesessie, de CSRF-controle en -- voor de pakketrun -- de uitvoering
van EEN stap (de taalmodel-grens).

Wat dit vaststelt:

1. De rol `hr_medewerker` (hr:read, hr:write, packs:execute, tools:read) mag de kloofanalyse en de
   personeelsvraag via een agent laten draaien; de rol `user` zonder hr-rechten niet.
2. De import vraagt `hr:write`: met het recht 200, zonder 403 (tot nu toe: alleen beheerder).
3. De beheerder heeft `hr:read` en `hr:write` via `*:*`, maar NIET `hr:approve` (expliciete actie).
4. Het pakket `hr.reskilling_engine` heeft voor de pilot precies een stap en een run slaagt.

Wat NIET gemeten is: een draaiende applicatie met scherm en een echt taalmodel.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import Role, User, user_roles
from src.core.services.rbac_service import RBACService
from src.core.shared.interfaces import ExecutionResult
from src.core.types import ExecutionStatusContract

TENANT = 1
MEDEWERKER = 101
PACK = "hr.reskilling_engine"
EXECUTE_URL = "/api/v1/agentic/packs/execute"
IMPORT_URL = "/api/v1/hr/skills/import"
GAP_URL = "/api/v1/hr/skills/gap"
RIJEINDE = chr(10)
CSV_VAARDIGHEDEN = "name,category\nExcel,kantoor\nSQL,data\n"


def _csv(*regels: str) -> str:
    return RIJEINDE.join(regels) + RIJEINDE


async def _sql(query: str, **params: Any) -> Any:
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        result = await session.execute(text(query), params)
        await session.commit()
        return result


async def _zet_rol(user_id: int, rol: str) -> None:
    """Geef de gebruiker precies deze ene rol, GECOMMIT: de broker opent een eigen sessie."""
    await _sql("DELETE FROM user_roles WHERE user_id = :u AND tenant_id = :t", u=user_id, t=TENANT)
    await _sql(
        "INSERT INTO user_roles (user_id, role_id, tenant_id) "
        "SELECT :u, id, :t FROM roles WHERE tenant_id = :t AND name = :n",
        u=user_id,
        t=TENANT,
        n=rol,
    )


@pytest_asyncio.fixture
async def echte_rollen() -> AsyncGenerator[None, None]:
    """Zaai de standaardrollen echt (gecommit) en zet de rollen van de testgebruiker terug."""
    from src.core.database.bypass_session import adopt_tenant
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        async with adopt_tenant(session, TENANT):
            await RBACService(session).ensure_default_roles(TENANT)
        await session.commit()
    oud = list(
        (
            await _sql(
                "SELECT role_id FROM user_roles WHERE tenant_id = :t AND user_id = :u",
                t=TENANT,
                u=MEDEWERKER,
            )
        ).all()
    )
    yield
    await _sql(
        "DELETE FROM user_roles WHERE tenant_id = :t AND user_id = :u", t=TENANT, u=MEDEWERKER
    )
    for (role_id,) in oud:
        await _sql(
            "INSERT INTO user_roles (user_id, role_id, tenant_id) VALUES (:u, :r, :t)",
            u=MEDEWERKER,
            r=role_id,
            t=TENANT,
        )


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
    app: Any, session: AsyncSession, *, user_id: int, email: str, rollen: list[str]
) -> AsyncGenerator[AsyncClient, None]:
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

    gebruiker = UserResponse(id=user_id, email=email, tenant_id=TENANT, roles=rollen)
    overrides: dict[Any, Any] = {
        get_db: _db,
        api_get_db: _db,
        get_current_user: lambda: gebruiker,
        validate_csrf_token: _geen_csrf,
    }
    app.dependency_overrides.update(overrides)
    token = _build_test_token(user_id=user_id, email=email, tenant_id=TENANT)
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
    await RBACService(postgres_session).ensure_default_roles(TENANT)
    return postgres_session


@pytest_asyncio.fixture
async def gebruikers(standaardrollen: AsyncSession) -> dict[str, int]:
    """Per rolnaam een gebruiker met precies die ene rol."""
    return {
        rol: await _gebruiker_met_rol(standaardrollen, rol, f"hr-dag1-{rol}@integration.test")
        for rol in ("hr_medewerker", "user", "admin")
    }


async def _client_voor(
    rol: str, app: Any, sessie: AsyncSession, gebruikers: dict[str, int]
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _client(
        app,
        sessie,
        user_id=gebruikers[rol],
        email=f"hr-dag1-{rol}@integration.test",
        rollen=[rol],
    ):
        yield client


@pytest_asyncio.fixture
async def hr_medewerker(
    integration_app: Any, standaardrollen: AsyncSession, gebruikers: dict[str, int]
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _client_voor("hr_medewerker", integration_app, standaardrollen, gebruikers):
        yield client


@pytest_asyncio.fixture
async def gewone_gebruiker(
    integration_app: Any, standaardrollen: AsyncSession, gebruikers: dict[str, int]
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _client_voor("user", integration_app, standaardrollen, gebruikers):
        yield client


@pytest_asyncio.fixture
async def beheerder(
    integration_app: Any, standaardrollen: AsyncSession, gebruikers: dict[str, int]
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _client_voor("admin", integration_app, standaardrollen, gebruikers):
        yield client


@pytest.fixture
def stappen(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Vervangt de uitvoering van EEN stap (LLM-grens) en legt vast welke agents liepen."""
    from src.core.als.enterprise.packs import DomainPackOrchestrator

    gelopen: list[str] = []

    async def _stap(
        self: Any,
        agent_id: str,
        tenant_id: int,
        params: dict[str, Any],
        *,
        initiated_by_user_id: int | None = None,
    ) -> ExecutionResult:
        gelopen.append(agent_id)
        return ExecutionResult(
            task_id=f"taak-{agent_id}",
            success=True,
            tenant_id=tenant_id,
            agent_id=agent_id,
            status=ExecutionStatusContract.KLAAR,
        )

    monkeypatch.setattr(DomainPackOrchestrator, "_execute_step", _stap)
    return gelopen


def _csv_upload() -> dict[str, Any]:
    return {
        "data": {"entity_type": "skill"},
        "files": {"file": ("vaardigheden.csv", CSV_VAARDIGHEDEN.encode("utf-8"), "text/csv")},
    }


@pytest.mark.integration
@pytest.mark.asyncio
class TestToolrechtenPerTaak:
    @pytest.mark.parametrize(
        ("rol", "tool", "verwacht"),
        [
            ("hr_medewerker", "analyze_skill_gap", True),
            ("hr_medewerker", "query_hr_database", True),
            ("user", "analyze_skill_gap", False),
            ("user", "query_hr_database", False),
            ("hr_medewerker", "schedule_training", False),
        ],
    )
    async def test_toolrecht_per_rol(
        self, echte_rollen: None, rol: str, tool: str, verwacht: bool
    ) -> None:
        from src.core.auth.rbac import rbac_service

        await _zet_rol(MEDEWERKER, rol)

        toegestaan = await rbac_service.user_has_scope_for(MEDEWERKER, tool, tenant_id=TENANT)

        assert toegestaan is verwacht

    async def test_de_beheerder_heeft_hr_read_en_write_maar_niet_hr_approve(
        self, standaardrollen: AsyncSession, gebruikers: dict[str, int]
    ) -> None:
        service = RBACService(standaardrollen)
        admin = gebruikers["admin"]

        antwoorden = {
            actie: await service.user_has_permission(admin, f"hr:{actie}", TENANT)
            for actie in ("read", "write", "approve")
        }

        assert antwoorden == {"read": True, "write": True, "approve": False}


@pytest.mark.integration
@pytest.mark.asyncio
class TestImportVraagHrWrite:
    async def test_met_hr_write_slaagt_de_import(self, hr_medewerker: AsyncClient) -> None:
        antwoord = await hr_medewerker.post(IMPORT_URL, **_csv_upload())

        assert antwoord.status_code == 200, antwoord.text

    async def test_zonder_hr_write_is_de_import_verboden(
        self, gewone_gebruiker: AsyncClient
    ) -> None:
        antwoord = await gewone_gebruiker.post(IMPORT_URL, **_csv_upload())

        assert antwoord.status_code == 403, antwoord.text

    async def test_de_beheerder_mag_importeren(self, beheerder: AsyncClient) -> None:
        antwoord = await beheerder.post(IMPORT_URL, **_csv_upload())

        assert antwoord.status_code == 200, antwoord.text

    async def test_de_lijst_vraagt_hr_read(self, gewone_gebruiker: AsyncClient) -> None:
        antwoord = await gewone_gebruiker.get("/api/v1/hr/skills", params={"entity_type": "skill"})

        assert antwoord.status_code == 403, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestPakketVoorDePilot:
    async def test_het_pakket_heeft_precies_een_stap(self) -> None:
        from src.core.als.enterprise.packs import DomainPackOrchestrator

        pack = DomainPackOrchestrator().get_pack(PACK)

        assert pack is not None
        assert [s.agent_id for s in pack.steps] == ["skillsgaptraining"]

    async def test_een_run_slaagt_met_alleen_die_stap(
        self, hr_medewerker: AsyncClient, stappen: list[str], pakket_aan: None
    ) -> None:
        antwoord = await hr_medewerker.post(
            EXECUTE_URL,
            json={"pack_id": PACK, "input_data": {"task": "Welke vaardigheden missen?"}},
        )

        assert antwoord.status_code == 200, antwoord.text
        assert stappen == ["skillsgaptraining"]
        assert antwoord.json()["status"] == "succeeded", antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestKloofAnalyseLeesbaar:
    """Upload -> kloof: de medewerker ziet per functie en vaardigheid wie voldoet en wie niet."""

    async def _upload(self, client: AsyncClient, entity_type: str, inhoud: str) -> dict[str, Any]:
        antwoord = await client.post(
            IMPORT_URL,
            data={"entity_type": entity_type},
            files={"file": ("bestand.csv", inhoud.encode("utf-8"), "text/csv")},
        )
        assert antwoord.status_code == 200, antwoord.text
        assert antwoord.json()["data"]["errors"] == [], antwoord.text
        return dict(antwoord.json()["data"])

    async def test_de_kloof_komt_na_de_import_per_functie_en_vaardigheid_terug(
        self,
        hr_medewerker: AsyncClient,
        standaardrollen: AsyncSession,
    ) -> None:
        planner = Role(tenant_id=TENANT, name="Planner-dag1", description="test", is_active=True)
        standaardrollen.add(planner)
        await standaardrollen.flush()
        await _gebruiker_met_rol(standaardrollen, "Planner-dag1", "planner-dag1@integration.test")
        await self._upload(hr_medewerker, "skill", _csv("name,category", "Excel-dag1,kantoor"))
        await self._upload(
            hr_medewerker,
            "role_requirement",
            _csv("role_name,skill_name,required_level", "Planner-dag1,Excel-dag1,3"),
        )
        await self._upload(
            hr_medewerker,
            "employee_assessment",
            _csv("user_email,skill_name,level", "planner-dag1@integration.test,Excel-dag1,2"),
        )

        antwoord = await hr_medewerker.get(GAP_URL)

        assert antwoord.status_code == 200, antwoord.text
        rij = next(r for r in antwoord.json()["data"]["gaps"] if r["role"] == "Planner-dag1")
        assert (rij["role"], rij["skill"], rij["required_level"]) == (
            "Planner-dag1",
            "Excel-dag1",
            3,
        )
        assert (rij["holders"], rij["meeting_requirement"], rij["below_requirement"]) == (1, 0, 1)

    async def test_zonder_hr_read_is_de_kloof_verboden(self, gewone_gebruiker: AsyncClient) -> None:
        antwoord = await gewone_gebruiker.get(GAP_URL)

        assert antwoord.status_code == 403, antwoord.text

    async def test_de_kloof_toont_geen_gegevens_van_een_andere_klant(
        self, hr_medewerker: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        from src.core.models.hr_skills_models import RoleRequiredSkill, Skill

        andere = 2
        rol = Role(tenant_id=andere, name="Vreemd-dag1", description="test", is_active=True)
        vaardigheid = Skill(tenant_id=andere, name="Vreemd-skill-dag1")
        standaardrollen.add_all([rol, vaardigheid])
        await standaardrollen.flush()
        standaardrollen.add(
            RoleRequiredSkill(
                tenant_id=andere, role_id=rol.id, skill_id=vaardigheid.id, required_level=1
            )
        )
        await standaardrollen.commit()

        antwoord = await hr_medewerker.get(GAP_URL)

        assert antwoord.status_code == 200, antwoord.text
        assert "Vreemd-dag1" not in antwoord.text


@pytest_asyncio.fixture
async def pakket_aan(standaardrollen: AsyncSession) -> None:
    """Pakket aanzetten (dag 1): een pakket draait pas nadat een beheerder het heeft aangezet.

    Deze tests meten de uitvoerroute zelf, dus het pakket staat hier aan voor de testklant. De
    controle blijft staan: dat het UIT staan werkt, meet `test_pakket_aanzetten_per_klant.py`.
    """
    from sqlalchemy import text

    await standaardrollen.execute(
        text(
            "INSERT INTO tenant_pack_activations (tenant_id, pack_id, is_enabled) "
            "VALUES (:t, :p, true) "
            "ON CONFLICT (tenant_id, pack_id) DO UPDATE SET is_enabled = true"
        ),
        {"t": TENANT, "p": PACK},
    )
    await standaardrollen.commit()
