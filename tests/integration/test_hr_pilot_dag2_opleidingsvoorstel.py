"""HR-pilot dag 2: een opleidingsvoorstel dat de HR-goedkeurder goedkeurt (ADR-039, ADR-005).

Echte app-stack, echte Postgres op netwerkpoort 5455, de echte rolzaaier en de echte rechtencontrole
(`require_resource_permission`). Vervangen zijn alleen `get_current_user`, de databasesessie en de
CSRF-controle. Er is GEEN taalmodel in dit pad: een voorstel is een rij, geen vrije tekst.

Wat dit vaststelt:

1. De kloof en de voorstellen vragen `hr:read`; een jokerrecht `*:read` telt NIET voor de
   resource `hr` (personeelsgegevens), alleen `*:*` van de beheerder.
2. `hr:write` maakt per medewerker die niet voldoet een voorstel (status `voorgesteld`); een
   tweede aanroep maakt geen dubbele rij.
3. Goedkeuren vraagt `hr:approve` (rol `goedkeurder_hr`, niet via `*:*`), zet de training op
   `assigned` via het bestaande pad van `schedule_training` en schrijft een auditregel.
4. Vier ogen volgt de tenantinstelling voor `schedule_training`.
5. Tenant B ziet de voorstellen van tenant A niet en kan ze niet beslissen.

Wat NIET gemeten is: een draaiende applicatie met scherm.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import Role, RolePermission, User, user_roles
from src.core.services.rbac_service import RBACService

TENANT = 1
ANDERE_TENANT = 2
PROPOSALS = "/api/v1/hr/training-proposals"
GAP = "/api/v1/hr/skills/gap"
FUNCTIE = "Planner-d2"
SKILL = "Excel-d2"
TRAINING = "Excel basis d2"
LAAG = "laag-d2@integration.test"
HOOG = "hoog-d2@integration.test"
ONBEOORDEELD = "onbeoordeeld-d2@integration.test"


async def _gebruiker(session: AsyncSession, email: str, rollen: list[str]) -> int:
    gebruiker = User(
        email=email, hashed_password="x", tenant_id=TENANT, is_active=True, is_superuser=False
    )
    session.add(gebruiker)
    await session.flush()
    for naam in rollen:
        rol = (
            await session.execute(select(Role).where(Role.name == naam, Role.tenant_id == TENANT))
        ).scalar_one()
        await session.execute(
            user_roles.insert().values(user_id=gebruiker.id, role_id=rol.id, tenant_id=TENANT)
        )
    await session.commit()
    return int(gebruiker.id)


async def _client(
    app: Any, session: AsyncSession, *, user_id: int, email: str, tenant: int = TENANT
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

    gebruiker = UserResponse(id=user_id, email=email, tenant_id=tenant, roles=["user"])
    overrides: dict[Any, Any] = {
        get_db: _db,
        api_get_db: _db,
        get_current_user: lambda: gebruiker,
        validate_csrf_token: _geen_csrf,
    }
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
async def sessie(postgres_session: AsyncSession) -> AsyncSession:
    await RBACService(postgres_session).ensure_default_roles(TENANT)
    return postgres_session


@pytest_asyncio.fixture
async def wereld(sessie: AsyncSession) -> dict[str, int]:
    """Een functie met een eis (niveau 3), een training bij die vaardigheid en drie mensen."""
    functie = Role(tenant_id=TENANT, name=FUNCTIE, description="test", is_active=True)
    sessie.add(functie)
    await sessie.flush()
    ids: dict[str, int] = {}
    for sleutel, email in (("laag", LAAG), ("hoog", HOOG), ("onbeoordeeld", ONBEOORDEELD)):
        ids[sleutel] = await _gebruiker(sessie, email, [FUNCTIE])
    skill_id = (
        await sessie.execute(
            text("INSERT INTO skills (tenant_id, name) VALUES (:t, :n) RETURNING id"),
            {"t": TENANT, "n": SKILL},
        )
    ).scalar_one()
    await sessie.execute(
        text("INSERT INTO trainings (tenant_id, name, skill_id) VALUES (:t, :n, :s)"),
        {"t": TENANT, "n": TRAINING, "s": skill_id},
    )
    await sessie.execute(
        text(
            "INSERT INTO role_required_skills (tenant_id, role_id, skill_id, required_level) "
            "VALUES (:t, :r, :s, 3)"
        ),
        {"t": TENANT, "r": functie.id, "s": skill_id},
    )
    for sleutel, niveau in (("laag", 2), ("hoog", 4)):
        await sessie.execute(
            text(
                "INSERT INTO employee_skills (tenant_id, user_id, skill_id, level) "
                "VALUES (:t, :u, :s, :l)"
            ),
            {"t": TENANT, "u": ids[sleutel], "s": skill_id, "l": niveau},
        )
    await sessie.commit()
    return ids


def _fixture_voor(rollen: list[str], naam: str) -> Any:
    @pytest_asyncio.fixture
    async def _f(
        integration_app: Any, sessie: AsyncSession, wereld: dict[str, int]
    ) -> AsyncGenerator[AsyncClient, None]:
        email = f"{naam}-d2@integration.test"
        user_id = await _gebruiker(sessie, email, rollen)
        async for client in _client(integration_app, sessie, user_id=user_id, email=email):
            yield client

    return _f


hr_medewerker = _fixture_voor(["hr_medewerker"], "hrm")
goedkeurder = _fixture_voor(["goedkeurder_hr"], "gk")
beheerder = _fixture_voor(["admin"], "adm")
kleine_baas = _fixture_voor(["hr_medewerker", "goedkeurder_hr"], "baas")


@pytest_asyncio.fixture
async def alles_lezen(
    integration_app: Any, sessie: AsyncSession, wereld: dict[str, int]
) -> AsyncGenerator[AsyncClient, None]:
    """Een rol met het jokerrecht `*:read` (zo staat `user` in een bestaande omgeving)."""
    rol = Role(tenant_id=TENANT, name="alles-lezen-d2", description="test", is_active=True)
    sessie.add(rol)
    await sessie.flush()
    sessie.add(RolePermission(role_id=rol.id, tenant_id=TENANT, resource="*", action="read"))
    await sessie.commit()
    email = "alles-lezen-d2@integration.test"
    user_id = await _gebruiker(sessie, email, ["alles-lezen-d2"])
    async for client in _client(integration_app, sessie, user_id=user_id, email=email):
        yield client


def _maak(**extra: Any) -> dict[str, Any]:
    return {"role_name": FUNCTIE, "skill_name": SKILL, "training_name": TRAINING, **extra}


async def _voorstel_id(client: AsyncClient) -> int:
    lijst = await client.get(PROPOSALS)
    assert lijst.status_code == 200, lijst.text
    return int(lijst.json()["data"][0]["id"])


@pytest.mark.integration
@pytest.mark.asyncio
class TestWieMagDeKloofZien:
    async def test_een_jokerleesrecht_geeft_geen_toegang_tot_de_kloof(
        self, alles_lezen: AsyncClient
    ) -> None:
        antwoord = await alles_lezen.get(GAP)

        assert antwoord.status_code == 403, antwoord.text

    async def test_een_jokerleesrecht_geeft_geen_toegang_tot_de_voorstellen(
        self, alles_lezen: AsyncClient
    ) -> None:
        antwoord = await alles_lezen.get(PROPOSALS)

        assert antwoord.status_code == 403, antwoord.text

    async def test_de_beheerder_ziet_de_kloof_wel(self, beheerder: AsyncClient) -> None:
        antwoord = await beheerder.get(GAP)

        assert antwoord.status_code == 200, antwoord.text

    async def test_de_goedkeurder_hr_ziet_de_voorstellen(self, goedkeurder: AsyncClient) -> None:
        antwoord = await goedkeurder.get(PROPOSALS)

        assert antwoord.status_code == 200, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestVoorstellenMaken:
    async def test_alleen_wie_niet_voldoet_krijgt_een_voorstel(
        self, hr_medewerker: AsyncClient
    ) -> None:
        antwoord = await hr_medewerker.post(PROPOSALS, json=_maak())

        assert antwoord.status_code == 200, antwoord.text
        assert antwoord.json()["data"] == {"created": 1, "skipped": 0}

    async def test_het_voorstel_is_een_rij_met_status_voorgesteld(
        self, hr_medewerker: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())

        lijst = await hr_medewerker.get(PROPOSALS)

        rijen = lijst.json()["data"]
        assert [(r["employee_email"], r["status"], r["training_name"]) for r in rijen] == [
            (LAAG, "voorgesteld", TRAINING)
        ]

    async def test_een_tweede_aanroep_maakt_geen_dubbel_voorstel(
        self, hr_medewerker: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())

        tweede = await hr_medewerker.post(PROPOSALS, json=_maak())

        assert tweede.json()["data"] == {"created": 0, "skipped": 1}

    async def test_zonder_hr_write_kan_niemand_voorstellen_maken(
        self, goedkeurder: AsyncClient
    ) -> None:
        antwoord = await goedkeurder.post(PROPOSALS, json=_maak())

        assert antwoord.status_code == 403, antwoord.text

    async def test_een_onbekende_training_geeft_404(self, hr_medewerker: AsyncClient) -> None:
        antwoord = await hr_medewerker.post(PROPOSALS, json=_maak(training_name="Bestaat niet"))

        assert antwoord.status_code == 404, antwoord.text

    async def test_de_tenant_in_het_verzoek_wordt_geweigerd(
        self, hr_medewerker: AsyncClient
    ) -> None:
        antwoord = await hr_medewerker.post(PROPOSALS, json=_maak(tenant_id=ANDERE_TENANT))

        assert antwoord.status_code == 422, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestGoedkeuren:
    async def _klaarzetten(self, hr_medewerker: AsyncClient) -> int:
        await hr_medewerker.post(PROPOSALS, json=_maak())
        return await _voorstel_id(hr_medewerker)

    async def test_de_goedkeurder_keurt_goed_en_de_training_wordt_toegewezen(
        self, hr_medewerker: AsyncClient, goedkeurder: AsyncClient, sessie: AsyncSession
    ) -> None:
        voorstel = await self._klaarzetten(hr_medewerker)

        antwoord = await goedkeurder.post(f"{PROPOSALS}/{voorstel}/approve")

        assert antwoord.status_code == 200, antwoord.text
        rij = (
            await sessie.execute(
                text(
                    "SELECT et.status FROM employee_trainings et "
                    "JOIN users u ON u.id = et.user_id JOIN trainings t ON t.id = et.training_id "
                    "WHERE u.email = :e AND t.name = :t"
                ),
                {"e": LAAG, "t": TRAINING},
            )
        ).first()
        assert rij is not None and rij[0] == "assigned"

    async def test_het_voorstel_krijgt_status_goedgekeurd_met_besluiter(
        self, hr_medewerker: AsyncClient, goedkeurder: AsyncClient
    ) -> None:
        voorstel = await self._klaarzetten(hr_medewerker)

        await goedkeurder.post(f"{PROPOSALS}/{voorstel}/approve")

        rij = (await goedkeurder.get(PROPOSALS)).json()["data"][0]
        assert rij["status"] == "goedgekeurd"
        assert rij["decided_by_email"].startswith("gk-d2@")

    async def test_er_komt_een_auditregel_per_besluit(
        self, hr_medewerker: AsyncClient, goedkeurder: AsyncClient, sessie: AsyncSession
    ) -> None:
        voorstel = await self._klaarzetten(hr_medewerker)

        await goedkeurder.post(f"{PROPOSALS}/{voorstel}/approve")

        aantal = (
            await sessie.execute(
                text(
                    "SELECT count(*) FROM audit_logs WHERE tenant_id = :t "
                    "AND event_type = 'hr_training_proposal_approved'"
                ),
                {"t": TENANT},
            )
        ).scalar_one()
        assert aantal == 1

    async def test_afwijzen_wijst_geen_training_toe(
        self, hr_medewerker: AsyncClient, goedkeurder: AsyncClient, sessie: AsyncSession
    ) -> None:
        voorstel = await self._klaarzetten(hr_medewerker)

        antwoord = await goedkeurder.post(f"{PROPOSALS}/{voorstel}/reject")

        assert antwoord.status_code == 200, antwoord.text
        aantal = (
            await sessie.execute(
                text(
                    "SELECT count(*) FROM employee_trainings et JOIN trainings t "
                    "ON t.id = et.training_id WHERE t.name = :t"
                ),
                {"t": TRAINING},
            )
        ).scalar_one()
        assert aantal == 0
        assert (await goedkeurder.get(PROPOSALS)).json()["data"][0]["status"] == "afgewezen"

    async def test_een_besloten_voorstel_kan_niet_opnieuw_worden_beslist(
        self, hr_medewerker: AsyncClient, goedkeurder: AsyncClient
    ) -> None:
        voorstel = await self._klaarzetten(hr_medewerker)
        await goedkeurder.post(f"{PROPOSALS}/{voorstel}/approve")

        opnieuw = await goedkeurder.post(f"{PROPOSALS}/{voorstel}/approve")

        assert opnieuw.status_code == 409, opnieuw.text

    async def test_een_mislukte_toewijzing_laat_het_voorstel_op_voorgesteld_staan(
        self,
        hr_medewerker: AsyncClient,
        goedkeurder: AsyncClient,
        sessie: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from src.core.tool_broker.hr_registry import HRToolRegistry

        async def _faalt(self: Any, tool_name: str, payload: Any, *, tenant_id: int) -> Any:
            return {"success": False, "error": "de toewijzing is niet uitgevoerd"}

        monkeypatch.setattr(HRToolRegistry, "execute_hr_tool", _faalt)
        voorstel = await self._klaarzetten(hr_medewerker)

        antwoord = await goedkeurder.post(f"{PROPOSALS}/{voorstel}/approve")

        assert antwoord.status_code == 409, antwoord.text
        assert (await goedkeurder.get(PROPOSALS)).json()["data"][0]["status"] == "voorgesteld"
        aantal = (
            await sessie.execute(
                text(
                    "SELECT count(*) FROM employee_trainings et JOIN trainings t "
                    "ON t.id = et.training_id WHERE t.name = :t"
                ),
                {"t": TRAINING},
            )
        ).scalar_one()
        assert aantal == 0

    async def test_de_beheerder_zonder_goedkeurder_hr_mag_niet_goedkeuren(
        self, hr_medewerker: AsyncClient, beheerder: AsyncClient
    ) -> None:
        voorstel = await self._klaarzetten(hr_medewerker)

        antwoord = await beheerder.post(f"{PROPOSALS}/{voorstel}/approve")

        assert antwoord.status_code == 403, antwoord.text

    async def test_de_hr_medewerker_mag_niet_goedkeuren(self, hr_medewerker: AsyncClient) -> None:
        voorstel = await self._klaarzetten(hr_medewerker)

        antwoord = await hr_medewerker.post(f"{PROPOSALS}/{voorstel}/approve")

        assert antwoord.status_code == 403, antwoord.text

    async def test_een_geweigerde_goedkeuring_laat_de_status_staan(
        self, hr_medewerker: AsyncClient, beheerder: AsyncClient
    ) -> None:
        voorstel = await self._klaarzetten(hr_medewerker)

        await beheerder.post(f"{PROPOSALS}/{voorstel}/approve")

        assert (await hr_medewerker.get(PROPOSALS)).json()["data"][0]["status"] == "voorgesteld"


@pytest.mark.integration
@pytest.mark.asyncio
class TestVierOgen:
    async def _zet(self, sessie: AsyncSession, aan: bool) -> None:
        waarde = '{"four_eyes_actions": ["schedule_training"]}' if aan else "{}"
        await sessie.execute(
            text("UPDATE tenants SET settings = CAST(:s AS JSON) WHERE id = :t"),
            {"s": waarde, "t": TENANT},
        )
        await sessie.commit()

    async def test_met_vier_ogen_aan_keurt_de_voorsteller_zijn_eigen_voorstel_niet_goed(
        self, kleine_baas: AsyncClient, sessie: AsyncSession
    ) -> None:
        await self._zet(sessie, True)
        await kleine_baas.post(PROPOSALS, json=_maak())
        voorstel = await _voorstel_id(kleine_baas)

        antwoord = await kleine_baas.post(f"{PROPOSALS}/{voorstel}/approve")

        assert antwoord.status_code == 403, antwoord.text

    async def test_met_vier_ogen_uit_mag_de_voorsteller_zelf_goedkeuren(
        self, kleine_baas: AsyncClient, sessie: AsyncSession
    ) -> None:
        await self._zet(sessie, False)
        await kleine_baas.post(PROPOSALS, json=_maak())
        voorstel = await _voorstel_id(kleine_baas)

        antwoord = await kleine_baas.post(f"{PROPOSALS}/{voorstel}/approve")

        assert antwoord.status_code == 200, antwoord.text

    async def test_met_vier_ogen_aan_mag_een_ander_wel_goedkeuren(
        self, hr_medewerker: AsyncClient, goedkeurder: AsyncClient, sessie: AsyncSession
    ) -> None:
        await self._zet(sessie, True)
        await hr_medewerker.post(PROPOSALS, json=_maak())
        voorstel = await _voorstel_id(hr_medewerker)

        antwoord = await goedkeurder.post(f"{PROPOSALS}/{voorstel}/approve")

        assert antwoord.status_code == 200, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestTenantIsolatie:
    async def _vreemd_voorstel(self, sessie: AsyncSession) -> int:
        """Een voorstel van tenant B, rechtstreeks in de database gezet."""
        gebruiker = (
            await sessie.execute(
                text(
                    "INSERT INTO users (email, hashed_password, tenant_id, is_active, is_superuser) "
                    "VALUES ('vreemd-d2@integration.test', 'x', :t, true, false) RETURNING id"
                ),
                {"t": ANDERE_TENANT},
            )
        ).scalar_one()
        skill = (
            await sessie.execute(
                text("INSERT INTO skills (tenant_id, name) VALUES (:t, 'Vreemd-d2') RETURNING id"),
                {"t": ANDERE_TENANT},
            )
        ).scalar_one()
        training = (
            await sessie.execute(
                text(
                    "INSERT INTO trainings (tenant_id, name, skill_id) "
                    "VALUES (:t, 'Vreemd-training-d2', :s) RETURNING id"
                ),
                {"t": ANDERE_TENANT, "s": skill},
            )
        ).scalar_one()
        voorstel = (
            await sessie.execute(
                text(
                    "INSERT INTO training_proposals "
                    "(tenant_id, user_id, skill_id, training_id, reason, status) "
                    "VALUES (:t, :u, :s, :tr, 'test', 'voorgesteld') RETURNING id"
                ),
                {"t": ANDERE_TENANT, "u": gebruiker, "s": skill, "tr": training},
            )
        ).scalar_one()
        await sessie.commit()
        return int(voorstel)

    async def test_tenant_a_ziet_het_voorstel_van_tenant_b_niet(
        self, hr_medewerker: AsyncClient, sessie: AsyncSession
    ) -> None:
        await self._vreemd_voorstel(sessie)

        lijst = await hr_medewerker.get(PROPOSALS)

        assert "vreemd-d2@integration.test" not in lijst.text

    async def test_tenant_a_kan_het_voorstel_van_tenant_b_niet_goedkeuren(
        self, goedkeurder: AsyncClient, sessie: AsyncSession
    ) -> None:
        vreemd = await self._vreemd_voorstel(sessie)

        antwoord = await goedkeurder.post(f"{PROPOSALS}/{vreemd}/approve")

        assert antwoord.status_code == 404, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestGeenDubbeleVoorstellen:
    """Gemeten bij de acceptatie: een goedgekeurd voorstel liet een tweede toe (en dat werd later
    afgewezen). De unieke index dekt alleen OPEN voorstellen; de controle moet ook een
    GOEDGEKEURD voorstel voor dezelfde medewerker, vaardigheid en opleiding meenemen."""

    async def test_na_goedkeuren_maakt_een_tweede_aanroep_geen_nieuw_voorstel(
        self, hr_medewerker: AsyncClient, goedkeurder: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())
        voorstel = await _voorstel_id(hr_medewerker)
        await goedkeurder.post(f"{PROPOSALS}/{voorstel}/approve")

        tweede = await hr_medewerker.post(PROPOSALS, json=_maak())

        assert tweede.json()["data"] == {"created": 0, "skipped": 1}

    async def test_na_goedkeuren_staat_er_nog_maar_een_voorstel_in_de_lijst(
        self, hr_medewerker: AsyncClient, goedkeurder: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())
        voorstel = await _voorstel_id(hr_medewerker)
        await goedkeurder.post(f"{PROPOSALS}/{voorstel}/approve")
        await hr_medewerker.post(PROPOSALS, json=_maak())

        lijst = await hr_medewerker.get(PROPOSALS)

        assert len(lijst.json()["data"]) == 1

    async def test_na_afwijzen_mag_hetzelfde_voorstel_opnieuw(
        self, hr_medewerker: AsyncClient, goedkeurder: AsyncClient
    ) -> None:
        await hr_medewerker.post(PROPOSALS, json=_maak())
        voorstel = await _voorstel_id(hr_medewerker)
        await goedkeurder.post(f"{PROPOSALS}/{voorstel}/reject")

        opnieuw = await hr_medewerker.post(PROPOSALS, json=_maak())

        assert opnieuw.json()["data"] == {"created": 1, "skipped": 0}
