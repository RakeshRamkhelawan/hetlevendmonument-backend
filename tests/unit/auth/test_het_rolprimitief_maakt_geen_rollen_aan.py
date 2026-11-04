"""OP-185 en OP-184: het rol-aanmaakprimitief mag geen rollen verzinnen.

Het escalatiepad dat deze tests dichtzetten is vier schakels lang (ADR-036 OP-182 t/m
OP-186). Deze tests dekken schakel 1 en 2:

- OP-184: `role_name` staat in het REQUEST-model dat POST /api/v1/auth/register bindt,
  dus een willekeurige aanmelder kan zijn eigen rolnaam meesturen.
- OP-185: een onbekende rolnaam wordt AANGEMAAKT en toegekend
  (`auth_service.py:177`), dus elke tekenreeks die dat primitief bereikt is een rol.

Elke toets heeft een tegenhanger die de LEGITIEME kant bewijst, zodat "weiger alles"
geen geldige oplossing is.
"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import AuthService, RegistrationRequest, UserCreate
from src.core.models.rbac_models import Role


def _db_met_rolantwoord(rol: Role | None) -> AsyncSession:
    """Een dubbel dat eerst 'geen bestaande gebruiker' en dan `rol` teruggeeft."""
    db = AsyncMock(spec=AsyncSession)
    eerste = MagicMock()
    eerste.scalar_one_or_none.return_value = None
    tweede = MagicMock()
    tweede.scalar_one_or_none.return_value = rol
    # Een vaste lijst als side_effect is hier verkeerd: create_user doet na de twee
    # SELECT's ook nog de INSERT in user_roles, en dan loopt de lijst leeg met een
    # StopAsyncIteration die niets met de toets te maken heeft. Vandaar een teller die na
    # de tweede aanroep een neutraal antwoord blijft geven.
    antwoorden = [eerste, tweede]

    async def execute(*_args: object, **_kwargs: object) -> MagicMock:
        if antwoorden:
            return antwoorden.pop(0)
        neutraal = MagicMock()
        neutraal.scalar_one_or_none.return_value = None
        return neutraal

    db.execute = AsyncMock(side_effect=execute)
    # `db.flush()` is in het echt het moment waarop een nieuwe rij zijn id krijgt, en
    # create_user bouwt daarna een UserResponse die een INT id eist. Een dubbel dat niets
    # doet laat dat omvallen op een reden die niets met deze toets te maken heeft, dus
    # deelt dit dubbel ids uit zoals de database dat zou doen.
    toegevoegd: list[object] = []

    def add(obj: object) -> None:
        toegevoegd.append(obj)

    async def flush(*_args: object, **_kwargs: object) -> None:
        for volgnummer, obj in enumerate(toegevoegd, start=1):
            if getattr(obj, "id", None) is None:
                obj.id = volgnummer

    db.add = MagicMock(side_effect=add)
    db.flush = AsyncMock(side_effect=flush)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.mark.unit
class TestHetPubliekeSchema:
    """OP-184: het publieke registratieverzoek mag geen rol kunnen dragen."""

    def test_het_publieke_schema_kent_geen_rolveld(self) -> None:
        """De kern van OP-184: geen veld, dus niets om mee te sturen."""
        assert "role_name" not in RegistrationRequest.model_fields
        assert "role" not in RegistrationRequest.model_fields

    def test_het_publieke_schema_weigert_een_onbekend_veld(self) -> None:
        """De guard hangt aan het GEDRAG, niet aan de veldnaam role_name.

        De rij van OP-184 zegt het met een gemeten reden: een naam-guard is te omzeilen
        door het veld `initial_profile` te noemen. Daarom weigert dit schema ELK extra
        veld in plaats van een lijst met verboden namen bij te houden.
        """
        with pytest.raises(ValidationError):
            RegistrationRequest(
                email="nieuw@example.com",
                password="GeldigWachtwoord1",
                initial_profile="admin",
            )

    def test_het_publieke_schema_bewaakt_nog_steeds_de_wachtwoordsterkte(self) -> None:
        """De legitieme kant: bij het weghalen van het rolveld mag de wachtwoordcheck
        niet sneuvelen. Zonder deze toets is 'schema vervangen door een simpeler model'
        een geldige maar onveilige oplossing."""
        with pytest.raises(ValidationError):
            RegistrationRequest(email="nieuw@example.com", password="zwak")

    def test_een_geldig_verzoek_wordt_wel_geaccepteerd(self) -> None:
        """De legitieme kant van het schema zelf."""
        verzoek = RegistrationRequest(email="nieuw@example.com", password="GeldigWachtwoord1")
        assert verzoek.email == "nieuw@example.com"

    def test_het_registratie_endpoint_bindt_het_publieke_schema(self) -> None:
        """Het schema opschonen helpt niet als het endpoint het oude model blijft binden."""
        from src.core.api.auth.router_registration import register_user

        annotaties = register_user.__annotations__
        assert annotaties["user_data"] is RegistrationRequest, annotaties


@pytest.mark.unit
class TestHetRolprimitief:
    """OP-185: nooit impliciet een rol aanmaken."""

    @pytest.mark.asyncio
    async def test_een_onbekende_rol_wordt_niet_aangemaakt(self) -> None:
        """De kern van OP-185: geen rol in de tenant betekent weigeren, niet aanmaken."""
        db = _db_met_rolantwoord(None)
        service = AuthService()

        with patch("src.core.auth.auth_service.log_security_event", new=AsyncMock()):
            resultaat = await service.create_user(
                db,
                UserCreate(
                    email="aanvaller@example.com",
                    password="GeldigWachtwoord1",
                    role_name="system_admin",
                ),
                client_ip="127.0.0.1",
                tenant_id=1,
                request_path="/test",
            )

        assert resultaat is None, resultaat
        toegevoegde_rollen = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Role)]
        assert toegevoegde_rollen == [], toegevoegde_rollen
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_een_bestaande_rol_werkt_wel(self) -> None:
        """De legitieme kant: met een BESTAANDE rol hoort registreren gewoon te lukken,
        en er mag dan ook niets worden aangemaakt."""
        bestaande = Role(name="user", tenant_id=1)
        bestaande.id = 7
        db = _db_met_rolantwoord(bestaande)
        service = AuthService()

        with patch("src.core.auth.auth_service.log_security_event", new=AsyncMock()):
            with patch("src.core.auth.auth_service.jwt_handler") as jwt:
                jwt.hash_password = AsyncMock(return_value="gehasht")
                resultaat = await service.create_user(
                    db,
                    UserCreate(
                        email="gewoon@example.com",
                        password="GeldigWachtwoord1",
                        role_name="user",
                    ),
                    client_ip="127.0.0.1",
                    tenant_id=1,
                    request_path="/test",
                )

        toegevoegde_rollen = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Role)]
        assert toegevoegde_rollen == [], toegevoegde_rollen
        assert resultaat is not None
        db.commit.assert_awaited()


@pytest.mark.unit
class TestHetBeheerderspad:
    """OP-184, tweede pad: admin/users_router.py:35 heeft `role` als vrije tekst."""

    @pytest.mark.asyncio
    async def test_een_onbekende_rol_wordt_geweigerd_met_een_duidelijke_fout(self) -> None:
        """Een beheerder mag een rol kiezen, maar geen rol verzinnen.

        En de fout moet de WAARHEID vertellen: de oude code liet create_user None
        teruggeven en het endpoint maakte daar 409 "User already exists" van, wat de
        beheerder op het verkeerde spoor zet.
        """
        from src.core.api.v1.admin.users_router import (
            AdminUserCreateRequest,
            create_admin_user,
        )

        db = _db_met_rolantwoord(None)
        huidige = MagicMock()
        huidige.tenant_id = 1
        huidige.id = 1
        verzoek = MagicMock()
        verzoek.client = None

        with pytest.raises(HTTPException) as fout:
            await create_admin_user(
                AdminUserCreateRequest(
                    email="nieuw@example.com", password="GeldigWachtwoord1", role="verzonnen_rol"
                ),
                verzoek,
                huidige,
                db,
            )

        assert fout.value.status_code == 400, fout.value.status_code
        assert "verzonnen_rol" in str(fout.value.detail)
        # Let op de formulering: NIET "er is geen enkele rol aangemaakt". Dit pad zaait
        # sinds de Gate-2-reparatie eerst de standaardlijst (admin/editor/user), en dat
        # HOORT te gebeuren -- anders kan een verse tenant nooit zijn eerste beheerder
        # krijgen. Wat niet mag, is dat de VERZONNEN naam een rol wordt.
        namen = [c.args[0].name for c in db.add.call_args_list if isinstance(c.args[0], Role)]
        assert "verzonnen_rol" not in namen, namen
        assert set(namen) <= {
            "admin",
            "editor",
            "user",
            "debiteuren",
            "crediteuren",
            "goedkeurder",
            "goedkeurder_hr",
            "hr_medewerker",
        }, namen

@pytest.mark.unit
class TestDeBevindingenUitDeGate2Review:
    """Twee blokkerende bevindingen van de Gate-2-reviewer op 2026-09-11."""

    def test_het_bestaande_registratieformulier_blijft_werken(self) -> None:
        """HIGH: `extra="forbid"` mag het veld `name` niet weigeren.

        De frontend post sinds lang {name, email, password}
        (frontend/src/lib/api/client.ts:367). De eerste versie van dit schema kende `name`
        niet, en `extra="forbid"` maakte daar een 422 van -- een gemeten breuk van
        levende, legitieme functionaliteit. Zonder deze toets is "gewoon alles weigeren"
        een geldige oplossing.
        """
        verzoek = RegistrationRequest(
            name="Jan Jansen", email="jan@example.com", password="GeldigWachtwoord1"
        )
        assert verzoek.name == "Jan Jansen"

    def test_weergavevelden_blijven_werken(self) -> None:
        """`extra="forbid"` mag ook `full_name` en `username` niet weigeren.

        `full_name` wordt door manual_register gebruikt en `username` door
        bestaande aanroepers zoals tests/integration/test_auth_integration_old.py.
        """
        verzoek = RegistrationRequest(
            username="janjansen",
            full_name="Jan Jansen",
            email="jan@example.com",
            password="GeldigWachtwoord1",
        )
        assert verzoek.username == "janjansen"
        assert verzoek.full_name == "Jan Jansen"

    def test_een_rolveld_wordt_nog_steeds_geweigerd(self) -> None:
        """De andere kant van dezelfde reparatie: weergavenamen erbij mag de deur niet
        openzetten voor een rol."""
        for veld in ("role_name", "role", "initial_profile"):
            with pytest.raises(ValidationError):
                RegistrationRequest(
                    email="jan@example.com", password="GeldigWachtwoord1", **{veld: "admin"}
                )

    @pytest.mark.asyncio
    async def test_het_beheerderspad_zaait_de_standaardrollen_voor_het_controleert(self) -> None:
        """MEDIUM: fail-secure mag geen fail-dead worden.

        Gemeten door de reviewer: de rolcontrole stond VOOR de aanroep van
        ensure_default_roles (die pas na create_user kwam), dus een verse tenant zonder
        rollen kon nooit zijn eerste beheerder krijgen -- de HTTPException viel voordat er
        iets was gezaaid. Deze toets legt de VOLGORDE vast en niet alleen het bestaan van
        de aanroep.
        """
        from src.core.api.v1.admin import users_router

        volgorde: list[str] = []

        db = _db_met_rolantwoord(None)
        oorspronkelijke_execute = db.execute

        async def execute(*args: object, **kwargs: object) -> object:
            volgorde.append("rolcontrole")
            return await oorspronkelijke_execute(*args, **kwargs)

        db.execute = AsyncMock(side_effect=execute)

        nep_rbac = MagicMock()

        async def zaai(_tenant_id: int) -> None:
            volgorde.append("zaaien")

        nep_rbac.ensure_default_roles = AsyncMock(side_effect=zaai)
        nep_rbac.assign_role = AsyncMock()
        # De platformrolcontrole komt na het zaaien en voor de rolcontrole; een gewone rol mag altijd.
        nep_rbac.mag_rol_uitdelen = AsyncMock(return_value=True)

        huidige = MagicMock()
        huidige.tenant_id = 1
        huidige.id = 1
        verzoek = MagicMock()
        verzoek.client = None

        with patch.object(users_router, "RBACService", return_value=nep_rbac):
            with pytest.raises(HTTPException):
                await users_router.create_admin_user(
                    users_router.AdminUserCreateRequest(
                        email="nieuw@example.com",
                        password="GeldigWachtwoord1",
                        role="verzonnen_rol",
                    ),
                    verzoek,
                    huidige,
                    db,
                )

        assert volgorde[:2] == ["zaaien", "rolcontrole"], volgorde


@pytest.mark.unit
class TestDeTenantgrensInDeRolresolutie:
    """De tenantfilter in de rolresolutie is de dragende grens van deze fix.

    Gemeten door de Gate-2-securityreviewer op 2026-09-11: met
    `.where(Role.tenant_id == tenant_id)` WEGGEHAALD uit auth_service.py bleven alle elf
    toetsen groen. Oorzaak: de andere toetsen gebruiken een AsyncMock die een vaste rol
    teruggeeft ongeacht de query, dus WHERE-clausules zijn daar onzichtbaar. Een refactor
    kon de tenantgrens dus stil verwijderen terwijl de OP-185-guard groen bleef.

    Deze klasse draait daarom tegen een ECHTE (sqlite-)sessie, waar de WHERE wel telt.
    """

    @pytest_asyncio.fixture
    async def sessie(self) -> AsyncIterator[AsyncSession]:
        """Een echte async sessie met alleen de tabellen die dit pad aanraakt."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from src.core.models.rbac_models import Base

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        tabellen = [
            Base.metadata.tables[naam] for naam in ("tenants", "roles", "users", "user_roles")
        ]
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tabellen))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as sessie:
            yield sessie
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_een_rol_uit_een_andere_tenant_telt_niet(self, sessie: AsyncSession) -> None:
        """De grens: dezelfde rolnaam in tenant 9 mag een aanvraag in tenant 1 niet helpen."""
        sessie.add(Role(name="system_admin", tenant_id=9))
        await sessie.commit()

        with patch("src.core.auth.auth_service.log_security_event", new=AsyncMock()):
            resultaat = await AuthService().create_user(
                sessie,
                UserCreate(
                    email="aanvaller@example.com",
                    password="GeldigWachtwoord1",
                    role_name="system_admin",
                ),
                client_ip="127.0.0.1",
                tenant_id=1,
                request_path="/test",
            )

        assert resultaat is None, resultaat
        rollen = (await sessie.execute(select(Role).where(Role.tenant_id == 1))).scalars().all()
        assert rollen == [], rollen

    @pytest.mark.asyncio
    async def test_een_rol_in_de_eigen_tenant_telt_wel(self, sessie: AsyncSession) -> None:
        """De legitieme kant tegen dezelfde echte sessie, zodat "weiger alles" afvalt."""
        sessie.add(Role(name="user", tenant_id=1))
        await sessie.commit()

        with patch("src.core.auth.auth_service.log_security_event", new=AsyncMock()):
            with patch("src.core.auth.auth_service.jwt_handler") as jwt:
                jwt.hash_password = AsyncMock(return_value="gehasht")
                resultaat = await AuthService().create_user(
                    sessie,
                    UserCreate(
                        email="gewoon@example.com",
                        password="GeldigWachtwoord1",
                        role_name="user",
                    ),
                    client_ip="127.0.0.1",
                    tenant_id=1,
                    request_path="/test",
                )

        assert resultaat is not None
        assert resultaat.email == "gewoon@example.com"
        rolnamen = [
            r.name for r in (await sessie.execute(select(Role).where(Role.tenant_id == 1))).scalars()
        ]
        assert rolnamen == ["user"], rolnamen
