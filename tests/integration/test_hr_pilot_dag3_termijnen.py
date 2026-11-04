"""HR-pilot dag 3: termijnen vastleggen en zien wat eraan komt (ADR-005, ADR-039).

Echte app-stack, echte Postgres op netwerkpoort 5455, de echte rolzaaier en de echte rechtencontrole.
Vervangen zijn alleen `get_current_user`, de databasesessie en de CSRF-controle. De data zijn
RELATIEF aan vandaag, zodat de test niet vervalt: een certificaat dat over 40 dagen eindigt geeft
een signaal over 10 dagen (30 dagen eerder), enzovoort.

Wat dit vaststelt:

1. `hr:write` legt termijnen vast (formulier en CSV); `hr:read` ziet "Komende termijnen"; wie dat
   recht niet heeft (ook met `*:read`) krijgt 403.
2. De lijst toont de BEREKENDE signaaldata binnen 60 dagen, gesorteerd, met bron en `te_laat`;
   afgeronde regels en data buiten het venster ontbreken.
3. Verzuim bewaart GEEN vrije tekst: geen diagnose of ziekteoorzaak.
4. Elke toevoeging en wijziging schrijft een auditregel.
5. Tenant B ziet de termijnen van tenant A niet en kan ze niet wijzigen.

Wat NIET gemeten is: een draaiende applicatie met scherm.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date, timedelta
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
DEADLINES = "/api/v1/hr/deadlines"
UPCOMING = "/api/v1/hr/deadlines/upcoming"
IMPORT = "/api/v1/hr/deadlines/import"
MEDEWERKER = "medewerker-d3@integration.test"


def _dag(delta: int) -> str:
    return (date.today() + timedelta(days=delta)).isoformat()


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
    app: Any, session: AsyncSession, *, user_id: int, email: str
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

    gebruiker = UserResponse(id=user_id, email=email, tenant_id=TENANT, roles=["user"])
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
async def sessie(postgres_session: AsyncSession) -> AsyncSession:
    await RBACService(postgres_session).ensure_default_roles(TENANT)
    await _gebruiker(postgres_session, MEDEWERKER, ["user"])
    return postgres_session


def _fixture_voor(rollen: list[str], naam: str) -> Any:
    @pytest_asyncio.fixture
    async def _f(integration_app: Any, sessie: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
        email = f"{naam}-d3@integration.test"
        user_id = await _gebruiker(sessie, email, rollen)
        async for client in _client(integration_app, sessie, user_id=user_id, email=email):
            yield client

    return _f


hr_medewerker = _fixture_voor(["hr_medewerker"], "hrm")
goedkeurder = _fixture_voor(["goedkeurder_hr"], "gk")
gewone_gebruiker = _fixture_voor(["user"], "usr")


@pytest_asyncio.fixture
async def alles_lezen(
    integration_app: Any, sessie: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    rol = Role(tenant_id=TENANT, name="alles-lezen-d3", description="test", is_active=True)
    sessie.add(rol)
    await sessie.flush()
    sessie.add(RolePermission(role_id=rol.id, tenant_id=TENANT, resource="*", action="read"))
    await sessie.commit()
    email = "alles-lezen-d3@integration.test"
    user_id = await _gebruiker(sessie, email, ["alles-lezen-d3"])
    async for client in _client(integration_app, sessie, user_id=user_id, email=email):
        yield client


def _certificaat(einde_over: int, **extra: Any) -> dict[str, Any]:
    return {
        "user_email": MEDEWERKER,
        "kind": "certificaat",
        "end_date": _dag(einde_over),
        "description": "VCA",
        **extra,
    }


async def _upcoming(client: AsyncClient) -> list[dict[str, Any]]:
    antwoord = await client.get(UPCOMING)
    assert antwoord.status_code == 200, antwoord.text
    return list(antwoord.json()["data"])


@pytest.mark.integration
@pytest.mark.asyncio
class TestWieMagWat:
    async def test_een_gewone_gebruiker_ziet_geen_termijnen(
        self, gewone_gebruiker: AsyncClient
    ) -> None:
        antwoord = await gewone_gebruiker.get(UPCOMING)

        assert antwoord.status_code == 403, antwoord.text

    async def test_een_jokerleesrecht_geeft_geen_termijnen(self, alles_lezen: AsyncClient) -> None:
        antwoord = await alles_lezen.get(UPCOMING)

        assert antwoord.status_code == 403, antwoord.text

    async def test_een_gewone_gebruiker_kan_niets_vastleggen(
        self, gewone_gebruiker: AsyncClient
    ) -> None:
        antwoord = await gewone_gebruiker.post(DEADLINES, json=_certificaat(40))

        assert antwoord.status_code == 403, antwoord.text

    async def test_wie_alleen_mag_lezen_kan_niets_vastleggen(
        self, goedkeurder: AsyncClient
    ) -> None:
        antwoord = await goedkeurder.post(DEADLINES, json=_certificaat(40))

        assert antwoord.status_code == 403, antwoord.text

    async def test_wie_mag_lezen_ziet_de_lijst(self, goedkeurder: AsyncClient) -> None:
        antwoord = await goedkeurder.get(UPCOMING)

        assert antwoord.status_code == 200, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestKomendeTermijnen:
    async def test_een_certificaat_geeft_een_signaal_dertig_dagen_voor_het_einde(
        self, hr_medewerker: AsyncClient
    ) -> None:
        await hr_medewerker.post(DEADLINES, json=_certificaat(40))

        rijen = await _upcoming(hr_medewerker)

        assert [(r["label"], r["date"], r["bron"]) for r in rijen] == [
            ("Certificaat verlengen", _dag(10), "eigen")
        ]

    async def test_verzuim_geeft_de_probleemanalyse_na_zes_weken(
        self, hr_medewerker: AsyncClient
    ) -> None:
        await hr_medewerker.post(
            DEADLINES, json={"user_email": MEDEWERKER, "kind": "verzuim", "start_date": _dag(-30)}
        )

        rijen = await _upcoming(hr_medewerker)

        assert [(r["label"], r["date"], r["bron"]) for r in rijen] == [
            ("Probleemanalyse", _dag(11), "primair")
        ]

    async def test_het_plan_van_aanpak_volgt_de_werkelijke_analysedatum(
        self, hr_medewerker: AsyncClient
    ) -> None:
        await hr_medewerker.post(
            DEADLINES,
            json={
                "user_email": MEDEWERKER,
                "kind": "verzuim",
                "start_date": _dag(-30),
                "analysis_date": _dag(-5),
            },
        )

        rijen = await _upcoming(hr_medewerker)

        assert ("Plan van aanpak", _dag(9)) in [(r["label"], r["date"]) for r in rijen]

    async def test_een_termijn_die_al_voorbij_is_staat_erbij_als_te_laat(
        self, hr_medewerker: AsyncClient
    ) -> None:
        await hr_medewerker.post(DEADLINES, json=_certificaat(10))

        rijen = await _upcoming(hr_medewerker)

        assert [(r["date"], r["te_laat"]) for r in rijen] == [(_dag(-20), True)]

    async def test_een_termijn_buiten_zestig_dagen_staat_er_niet_bij(
        self, hr_medewerker: AsyncClient
    ) -> None:
        await hr_medewerker.post(DEADLINES, json=_certificaat(200))

        assert await _upcoming(hr_medewerker) == []

    async def test_de_lijst_is_gesorteerd_op_datum(self, hr_medewerker: AsyncClient) -> None:
        await hr_medewerker.post(DEADLINES, json=_certificaat(80))
        await hr_medewerker.post(DEADLINES, json=_certificaat(45))

        rijen = await _upcoming(hr_medewerker)

        assert [r["date"] for r in rijen] == [_dag(15), _dag(50)]

    async def test_een_afgeronde_regel_staat_er_niet_meer_bij(
        self, hr_medewerker: AsyncClient
    ) -> None:
        nieuw = await hr_medewerker.post(DEADLINES, json=_certificaat(40))
        deadline_id = nieuw.json()["data"]["id"]

        await hr_medewerker.patch(f"{DEADLINES}/{deadline_id}", json={"status": "afgerond"})

        assert await _upcoming(hr_medewerker) == []

    async def test_precies_zestig_dagen_vooruit_staat_er_nog_bij(
        self, hr_medewerker: AsyncClient
    ) -> None:
        await hr_medewerker.post(DEADLINES, json=_certificaat(90))

        assert [r["date"] for r in await _upcoming(hr_medewerker)] == [_dag(60)]

    async def test_eenenzestig_dagen_vooruit_staat_er_niet_bij(
        self, hr_medewerker: AsyncClient
    ) -> None:
        await hr_medewerker.post(DEADLINES, json=_certificaat(91))

        assert await _upcoming(hr_medewerker) == []

    async def test_vandaag_is_nog_niet_te_laat(self, hr_medewerker: AsyncClient) -> None:
        await hr_medewerker.post(DEADLINES, json=_certificaat(30))

        rijen = await _upcoming(hr_medewerker)

        assert [(r["date"], r["te_laat"]) for r in rijen] == [(_dag(0), False)]

    async def test_een_termijn_afronden_laat_de_andere_termijnen_van_de_regel_staan(
        self, hr_medewerker: AsyncClient
    ) -> None:
        nieuw = await hr_medewerker.post(
            DEADLINES,
            json={
                "user_email": MEDEWERKER,
                "kind": "verzuim",
                "start_date": _dag(-300),
                "analysis_date": _dag(-270),
            },
        )
        deadline_id = nieuw.json()["data"]["id"]
        voor = [r["label"] for r in await _upcoming(hr_medewerker)]

        await hr_medewerker.patch(f"{DEADLINES}/{deadline_id}", json={"done_label": "Plan van aanpak"})

        na = [r["label"] for r in await _upcoming(hr_medewerker)]
        assert ("Plan van aanpak" in voor, "Plan van aanpak" in na, len(na) == len(voor) - 1) == (
            True,
            False,
            True,
        )

    async def test_een_ingetrokken_afronding_toont_de_regel_weer(
        self, hr_medewerker: AsyncClient
    ) -> None:
        nieuw = await hr_medewerker.post(DEADLINES, json=_certificaat(40))
        deadline_id = nieuw.json()["data"]["id"]
        await hr_medewerker.patch(f"{DEADLINES}/{deadline_id}", json={"status": "afgerond"})

        await hr_medewerker.patch(f"{DEADLINES}/{deadline_id}", json={"status": "open"})

        assert len(await _upcoming(hr_medewerker)) == 1

    async def test_een_uitgetreden_medewerker_staat_er_niet_meer_in(
        self, hr_medewerker: AsyncClient, sessie: AsyncSession
    ) -> None:
        await hr_medewerker.post(DEADLINES, json=_certificaat(40))
        await sessie.execute(
            text("UPDATE users SET deleted_at = now() WHERE email = :e"), {"e": MEDEWERKER}
        )
        await sessie.commit()

        assert await _upcoming(hr_medewerker) == []

    async def test_met_een_offset_komt_het_volgende_deel_van_de_lijst(
        self, hr_medewerker: AsyncClient
    ) -> None:
        await hr_medewerker.post(DEADLINES, json=_certificaat(45))
        await hr_medewerker.post(DEADLINES, json=_certificaat(80))

        antwoord = await hr_medewerker.get(UPCOMING, params={"limit": 1, "offset": 1})

        assert [r["date"] for r in antwoord.json()["data"]] == [_dag(50)]

    async def test_de_analysedatum_kan_later_worden_ingevuld(
        self, hr_medewerker: AsyncClient
    ) -> None:
        nieuw = await hr_medewerker.post(
            DEADLINES, json={"user_email": MEDEWERKER, "kind": "verzuim", "start_date": _dag(-30)}
        )
        deadline_id = nieuw.json()["data"]["id"]

        await hr_medewerker.patch(f"{DEADLINES}/{deadline_id}", json={"analysis_date": _dag(-5)})

        rijen = await _upcoming(hr_medewerker)
        assert ("Plan van aanpak", _dag(9)) in [(r["label"], r["date"]) for r in rijen]


@pytest.mark.integration
@pytest.mark.asyncio
class TestInvoer:
    async def test_een_onbekende_medewerker_geeft_404(self, hr_medewerker: AsyncClient) -> None:
        antwoord = await hr_medewerker.post(
            DEADLINES, json=_certificaat(40, user_email="bestaat-niet@integration.test")
        )

        assert antwoord.status_code == 404, antwoord.text

    async def test_een_certificaat_zonder_einddatum_geeft_422(
        self, hr_medewerker: AsyncClient
    ) -> None:
        antwoord = await hr_medewerker.post(
            DEADLINES, json={"user_email": MEDEWERKER, "kind": "certificaat"}
        )

        assert antwoord.status_code == 422, antwoord.text

    async def test_verzuim_zonder_startdatum_geeft_422(self, hr_medewerker: AsyncClient) -> None:
        antwoord = await hr_medewerker.post(
            DEADLINES, json={"user_email": MEDEWERKER, "kind": "verzuim"}
        )

        assert antwoord.status_code == 422, antwoord.text

    async def test_een_onbekende_soort_geeft_422(self, hr_medewerker: AsyncClient) -> None:
        antwoord = await hr_medewerker.post(DEADLINES, json=_certificaat(40, kind="diagnose"))

        assert antwoord.status_code == 422, antwoord.text

    async def test_verzuim_neemt_geen_vrije_tekst_aan(self, hr_medewerker: AsyncClient) -> None:
        antwoord = await hr_medewerker.post(
            DEADLINES,
            json={
                "user_email": MEDEWERKER,
                "kind": "verzuim",
                "start_date": _dag(-30),
                "description": "rugklachten",
            },
        )

        assert antwoord.status_code == 422, antwoord.text

    async def test_de_tenant_in_het_verzoek_wordt_geweigerd(
        self, hr_medewerker: AsyncClient
    ) -> None:
        antwoord = await hr_medewerker.post(DEADLINES, json=_certificaat(40, tenant_id=2))

        assert antwoord.status_code == 422, antwoord.text

    async def test_een_lege_omschrijving_bij_verzuim_geeft_geen_fout(
        self, hr_medewerker: AsyncClient
    ) -> None:
        antwoord = await hr_medewerker.post(
            DEADLINES,
            json={
                "user_email": MEDEWERKER,
                "kind": "verzuim",
                "start_date": _dag(-30),
                "description": "",
            },
        )

        assert antwoord.status_code == 200, antwoord.text

    async def test_een_analysedatum_voor_de_eerste_ziektedag_geeft_422(
        self, hr_medewerker: AsyncClient
    ) -> None:
        antwoord = await hr_medewerker.post(
            DEADLINES,
            json={
                "user_email": MEDEWERKER,
                "kind": "verzuim",
                "start_date": _dag(-10),
                "analysis_date": _dag(-20),
            },
        )

        assert antwoord.status_code == 422, antwoord.text
        assert "eerste ziektedag" in antwoord.text

    async def test_een_analysedatum_voor_de_eerste_ziektedag_wordt_bij_wijzigen_geweigerd(
        self, hr_medewerker: AsyncClient
    ) -> None:
        nieuw = await hr_medewerker.post(
            DEADLINES, json={"user_email": MEDEWERKER, "kind": "verzuim", "start_date": _dag(-10)}
        )

        antwoord = await hr_medewerker.patch(
            f"{DEADLINES}/{nieuw.json()['data']['id']}", json={"analysis_date": _dag(-20)}
        )

        assert antwoord.status_code == 400, antwoord.text
        assert "eerste ziektedag" in antwoord.text

    async def test_een_analysedatum_op_de_eerste_ziektedag_mag_wel(
        self, hr_medewerker: AsyncClient
    ) -> None:
        antwoord = await hr_medewerker.post(
            DEADLINES,
            json={
                "user_email": MEDEWERKER,
                "kind": "verzuim",
                "start_date": _dag(-10),
                "analysis_date": _dag(-10),
            },
        )

        assert antwoord.status_code == 200, antwoord.text

    async def test_een_te_lange_omschrijving_geeft_422(self, hr_medewerker: AsyncClient) -> None:
        antwoord = await hr_medewerker.post(DEADLINES, json=_certificaat(40, description="x" * 500))

        assert antwoord.status_code == 422, antwoord.text

    async def test_de_lijst_toont_bij_verzuim_nooit_een_omschrijving(
        self, hr_medewerker: AsyncClient
    ) -> None:
        await hr_medewerker.post(
            DEADLINES, json={"user_email": MEDEWERKER, "kind": "verzuim", "start_date": _dag(-30)}
        )

        rijen = await _upcoming(hr_medewerker)

        assert [r["description"] for r in rijen] == [None]


@pytest.mark.integration
@pytest.mark.asyncio
class TestCsvImport:
    @staticmethod
    def _csv(*regels: str) -> dict[str, Any]:
        inhoud = chr(10).join(
            ("user_email,kind,start_date,end_date,analysis_date,description", *regels)
        )
        return {"files": {"file": ("termijnen.csv", inhoud.encode("utf-8"), "text/csv")}}

    async def test_geldige_regels_worden_ingelezen(self, hr_medewerker: AsyncClient) -> None:
        antwoord = await hr_medewerker.post(
            IMPORT,
            **self._csv(
                f"{MEDEWERKER},certificaat,,{_dag(40)},,VCA",
                f"{MEDEWERKER},verzuim,{_dag(-30)},,,",
            ),
        )

        assert antwoord.status_code == 200, antwoord.text
        assert antwoord.json()["data"]["inserted"] == 2
        assert antwoord.json()["data"]["errors"] == []

    async def test_een_foute_regel_krijgt_een_foutmelding_met_regelnummer(
        self, hr_medewerker: AsyncClient
    ) -> None:
        antwoord = await hr_medewerker.post(
            IMPORT,
            **self._csv(
                f"{MEDEWERKER},certificaat,,{_dag(40)},,VCA",
                f"onbekend@integration.test,certificaat,,{_dag(40)},,VCA",
            ),
        )

        data = antwoord.json()["data"]
        assert data["inserted"] == 1
        assert [e["row_index"] for e in data["errors"]] == [3]

    async def test_verzuim_met_omschrijving_wordt_per_regel_geweigerd(
        self, hr_medewerker: AsyncClient
    ) -> None:
        antwoord = await hr_medewerker.post(
            IMPORT, **self._csv(f"{MEDEWERKER},verzuim,{_dag(-30)},,,rugklachten")
        )

        data = antwoord.json()["data"]
        assert (data["inserted"], [e["row_index"] for e in data["errors"]]) == (0, [2])

    async def test_een_te_lange_omschrijving_wordt_per_regel_geweigerd(
        self, hr_medewerker: AsyncClient
    ) -> None:
        antwoord = await hr_medewerker.post(
            IMPORT, **self._csv(f"{MEDEWERKER},certificaat,,{_dag(40)},," + "x" * 201)
        )

        assert antwoord.status_code == 200, antwoord.text
        data = antwoord.json()["data"]
        assert (data["inserted"], [e["row_index"] for e in data["errors"]]) == (0, [2])

    async def test_een_analysedatum_voor_de_eerste_ziektedag_wordt_per_regel_geweigerd(
        self, hr_medewerker: AsyncClient
    ) -> None:
        antwoord = await hr_medewerker.post(
            IMPORT, **self._csv(f"{MEDEWERKER},verzuim,{_dag(-10)},,{_dag(-20)},")
        )

        data = antwoord.json()["data"]
        assert (data["inserted"], [e["row_index"] for e in data["errors"]]) == (0, [2])

    async def test_een_gewone_gebruiker_mag_niet_importeren(
        self, gewone_gebruiker: AsyncClient
    ) -> None:
        antwoord = await gewone_gebruiker.post(
            IMPORT, **self._csv(f"{MEDEWERKER},certificaat,,{_dag(40)},,VCA")
        )

        assert antwoord.status_code == 403, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestAuditregel:
    async def _aantal(self, sessie: AsyncSession, soort: str) -> int:
        return int(
            (
                await sessie.execute(
                    text(
                        "SELECT count(*) FROM audit_logs WHERE tenant_id = :t AND event_type = :e"
                    ),
                    {"t": TENANT, "e": soort},
                )
            ).scalar_one()
        )

    async def test_toevoegen_schrijft_een_auditregel(
        self, hr_medewerker: AsyncClient, sessie: AsyncSession
    ) -> None:
        await hr_medewerker.post(DEADLINES, json=_certificaat(40))

        assert await self._aantal(sessie, "hr_deadline_created") == 1

    async def test_wijzigen_schrijft_een_auditregel(
        self, hr_medewerker: AsyncClient, sessie: AsyncSession
    ) -> None:
        nieuw = await hr_medewerker.post(DEADLINES, json=_certificaat(40))

        await hr_medewerker.patch(
            f"{DEADLINES}/{nieuw.json()['data']['id']}", json={"status": "afgerond"}
        )

        assert await self._aantal(sessie, "hr_deadline_updated") == 1

    async def test_de_auditregel_bevat_geen_omschrijving_of_e_mailadres(
        self, hr_medewerker: AsyncClient, sessie: AsyncSession
    ) -> None:
        await hr_medewerker.post(DEADLINES, json=_certificaat(40))

        tekst = (
            await sessie.execute(
                text(
                    "SELECT coalesce(description, '') || coalesce(CAST(event_metadata AS text), '') "
                    "FROM audit_logs WHERE tenant_id = :t AND event_type = 'hr_deadline_created'"
                ),
                {"t": TENANT},
            )
        ).scalar_one()
        assert MEDEWERKER not in tekst and "VCA" not in tekst


@pytest.mark.integration
@pytest.mark.asyncio
class TestTenantIsolatie:
    async def _vreemde_termijn(self, sessie: AsyncSession) -> int:
        gebruiker = (
            await sessie.execute(
                text(
                    "INSERT INTO users (email, hashed_password, tenant_id, is_active, is_superuser) "
                    "VALUES ('vreemd-d3@integration.test', 'x', :t, true, false) RETURNING id"
                ),
                {"t": ANDERE_TENANT},
            )
        ).scalar_one()
        rij = (
            await sessie.execute(
                text(
                    "INSERT INTO hr_deadlines (tenant_id, user_id, kind, end_date, status) "
                    "VALUES (:t, :u, 'certificaat', :e, 'open') RETURNING id"
                ),
                {"t": ANDERE_TENANT, "u": gebruiker, "e": date.today() + timedelta(days=40)},
            )
        ).scalar_one()
        await sessie.commit()
        return int(rij)

    async def test_tenant_a_ziet_de_termijn_van_tenant_b_niet(
        self, hr_medewerker: AsyncClient, sessie: AsyncSession
    ) -> None:
        await self._vreemde_termijn(sessie)

        antwoord = await hr_medewerker.get(UPCOMING)

        assert "vreemd-d3@integration.test" not in antwoord.text

    async def test_tenant_a_kan_de_termijn_van_tenant_b_niet_wijzigen(
        self, hr_medewerker: AsyncClient, sessie: AsyncSession
    ) -> None:
        vreemd = await self._vreemde_termijn(sessie)

        antwoord = await hr_medewerker.patch(f"{DEADLINES}/{vreemd}", json={"status": "afgerond"})

        assert antwoord.status_code == 404, antwoord.text
