"""Een agent-toolactie erft het recht van de MENS die hem aanvroeg (SP-COUNCIL-GATE-001).

Aanleiding, gemeten 2026-08-15. `RBACService.user_has_scope_for()` toetste alleen of de
actienaam in `_COUNCIL_ALLOWED_ACTION_TYPES` staat; `user_id` werd blijkens de eigen docstring
genegeerd ("unused for MVP"). Dat was al als MINOR-1 vastgelegd in
`docs/backend/review/review-BE-GOV-001.md`. Voor de copilot viel het niet op -- dat is een
vaste, korte lijst chat-acties. Voor het agent-pad valt het wel op: de naam van een BROKER-tool
staat niet op die lijst, dus de SecurityOfficer gaf `MISSING_SCOPE` en elke toolactie strandde.

Het gat gaat twee kanten op, en de tweede is de gevaarlijke: zou je die lijst simpelweg
uitbreiden met de toolnamen, dan mag IEDERE gebruiker via een agent IEDERE tool draaien --
inclusief een leesactie op personeelsdata. Precies dat is wat deze tests verbieden.

De maatstaf staat in `src/core/config/tool_risk_levels.yml` naast het risiconiveau, zodat een
nieuwe tool zijn drempel op dezelfde plek meekrijgt als zijn risico. Een tool zonder regel valt
terug op de striktste eis (zero-trust, gelijk aan `default_risk_level: high`).
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import Role, Tenant, User  # noqa: E402

TENANT_A = 4301
TENANT_B = 4302

HR_TOOL = "query_hr_database"
COPILOT_ACTIE = "send_notification"


async def _user_with_role(
    session: AsyncSession,
    *,
    user_id: int,
    tenant_id: int,
    role_name: str,
    rechten: tuple[tuple[str, str], ...] = (),
) -> None:
    """Zet een tenant, een rol en een gebruiker neer -- idempotent per tenant.

    Rollen en rechten komen van de ECHTE zaaier (`ensure_default_roles`), niet uit deze test:
    de rechtencontrole leest sinds OP-143 `role_permissions`, en een rol zonder rijen heeft geen
    recht. Een rolnaam die de zaaier niet kent (een eigen rol) krijgt precies de `rechten` die
    de test opgeeft.
    """
    from sqlalchemy import select

    from src.core.models.rbac_models import RolePermission
    from src.core.services.rbac_service import RBACService

    bestaat = (
        await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if bestaat is None:
        session.add(Tenant(id=tenant_id, name=f"Scope {tenant_id}", slug=f"scope-{tenant_id}"))
        await session.flush()

    await RBACService(session).ensure_default_roles(tenant_id)
    rol = (
        (await session.execute(select(Role).where(Role.tenant_id == tenant_id, Role.name == role_name)))
        .scalars()
        .first()
    )
    if rol is None:
        rol = Role(tenant_id=tenant_id, name=role_name)
        session.add(rol)
        await session.flush()
        for resource, actie in rechten:
            session.add(
                RolePermission(
                    role_id=rol.id, tenant_id=tenant_id, resource=resource, action=actie
                )
            )
        await session.flush()

    gebruiker = User(
        id=user_id,
        tenant_id=tenant_id,
        email=f"u{user_id}@scope.test",
        hashed_password="x",
    )
    gebruiker.roles.append(rol)
    session.add(gebruiker)
    await session.commit()


@pytest.mark.unit
@pytest.mark.asyncio
class TestABrokerToolNeedsARealPermission:
    async def test_a_user_with_the_permission_is_allowed(self, db_session: AsyncSession) -> None:
        """De helft die voorkomt dat 'weiger alles' een geldige oplossing is."""
        from src.core.auth.rbac import rbac_service

        await _user_with_role(db_session, user_id=4310, tenant_id=TENANT_A, role_name="admin")

        assert await rbac_service.user_has_scope_for(4310, HR_TOOL, tenant_id=TENANT_A) is True, (
            "Een beheerder mag de HR-tool niet draaien. Dan staat de piloot alsnog stil, nu om "
            "een andere reden."
        )

    async def test_a_user_without_the_permission_is_refused(self, db_session: AsyncSession) -> None:
        """De test die het hele punt draagt.

        Zonder deze grens kan iedereen die met een agent mag praten via die agent
        personeelsdata opvragen -- de agent zou dan een rechtenverhoging zijn in plaats van een
        hulpmiddel.
        """
        from src.core.auth.rbac import rbac_service

        await _user_with_role(db_session, user_id=4311, tenant_id=TENANT_A, role_name="user")

        assert await rbac_service.user_has_scope_for(4311, HR_TOOL, tenant_id=TENANT_A) is False, (
            "Een gewone gebruiker mag via een agent personeelsdata opvragen. De agent is dan "
            "een omweg om de rechten van de aanvrager heen."
        )

    async def test_a_low_threshold_tool_is_open_to_an_ordinary_user(
        self, db_session: AsyncSession
    ) -> None:
        """De tweede richting: het is geen 'alleen beheerders'-schakelaar.

        Uit de Gate 2-review: zonder dit geval haalt `return gebruiker_heeft_rol("admin")`
        alle andere asserties en is de hele `tool_required_permission`-lijst decoratie. Deze
        test dwingt af dat de eis PER TOOL wordt gelezen.
        """
        from src.core.auth.rbac import rbac_service

        await _user_with_role(db_session, user_id=4313, tenant_id=TENANT_A, role_name="user")

        assert await rbac_service.user_has_scope_for(4313, "list_tasks", tenant_id=TENANT_A) is (
            True
        ), (
            "Een gewone gebruiker mag geen leesactie draaien die alleen leesrecht vraagt. Dan "
            "wordt er niet per tool gekeken maar een vaste drempel toegepast."
        )

    async def test_an_unknown_tool_is_refused_even_for_an_admin(
        self, db_session: AsyncSession
    ) -> None:
        """Zero-trust, en bewust met een BEHEERDER.

        Met een gewone gebruiker zou de weigering ook uit de rol kunnen komen; met een
        beheerder bewijst hij dat het aan de TOOL ligt. Er is met opzet geen prefix-terugval:
        een naamruimte mag een tool niet ongemerkt soepeler maken dan de default.
        """
        from src.core.auth.rbac import rbac_service

        await _user_with_role(db_session, user_id=4312, tenant_id=TENANT_A, role_name="admin")

        assert (
            await rbac_service.user_has_scope_for(
                4312, "local__tool_die_niet_bestaat", tenant_id=TENANT_A
            )
            is False
        ), (
            "Een tool zonder eigen regel kwam door de controle. Dan opent elke nieuwe tool "
            "zichzelf zolang niemand eraan denkt hem te classificeren."
        )

    async def test_two_tools_can_have_two_different_thresholds(
        self, db_session: AsyncSession
    ) -> None:
        """Een gebruiker die de ene tool wel en de andere niet mag -- in EEN test.

        Zonder dit kan een implementatie met een enkele globale drempel alle tests halen.

        Het schrijfrecht-voorbeeld was `schedule_training`. Die eist sinds 2026-09-21 `admin`
        en niet `write`: hij muteert dezelfde personeelsdata die `query_hr_database` leest, en
        een schrijfactie mag nooit losser zijn dan het lezen ervan. Een tool die WEL op
        schrijfrecht staat is daarom het voorbeeld geworden -- deze test gaat over het verschil
        tussen twee drempels, niet over deze twee namen.
        """
        from src.core.auth.rbac import rbac_service

        write_tool = "local__write_file"
        await _user_with_role(
            db_session,
            user_id=4314,
            tenant_id=TENANT_A,
            role_name="moderator",
            rechten=(("tools", "read"), ("tools", "write")),
        )

        mag = await rbac_service.user_has_scope_for(4314, write_tool, tenant_id=TENANT_A)
        mag_niet = await rbac_service.user_has_scope_for(4314, HR_TOOL, tenant_id=TENANT_A)

        assert mag is True and mag_niet is False, (
            f"{write_tool}={mag} (schrijfrecht, hoort True) en {HR_TOOL}={mag_niet} "
            "(beheerrecht, hoort False). Gelijke uitkomsten betekenen een vaste drempel."
        )

    async def test_an_unknown_permission_name_in_the_config_refuses(
        self, db_session: AsyncSession
    ) -> None:
        """Een typefout in de configuratie moet WEIGEREN, niet doorlaten.

        Een waarde die niet in `TOOL_RECHTEN` staat moet WEIGEREN. Zou die verderop worden
        weggevangen als "geen eis", dan opent een typefout de tool voor iedereen.
        """
        from unittest.mock import patch

        from src.core.auth.rbac import rbac_service

        await _user_with_role(db_session, user_id=4315, tenant_id=TENANT_A, role_name="admin")

        with patch(
            "src.core.tool_broker.risk_classifier.ToolRiskClassifier.required_permission",
            return_value="bestaat_niet",
        ):
            uitkomst = await rbac_service.user_has_scope_for(4315, HR_TOOL, tenant_id=TENANT_A)

        assert uitkomst is False, "Een onbekende rechtennaam liet de actie toch door."


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheRealSeederProducesUsableRoles:
    """De test die ontbrak, en die de ernstigste fout van deze dag betrapte.

    Elke andere test in dit bestand maakt zijn rollen ZELF aan, met kleine letters. Daarmee
    verzint de test zijn eigen vocabulaire aan beide kanten van de vergelijking en bewijst hij
    alleen dat de functie deterministisch is. De ECHTE producent is `RoleSeeder`, en die
    schrijft `role_def.name` weg -- `Admin`, `Editor`, `Viewer` met hoofdletter, want de
    kleine-letterversies zijn de dict-SLEUTELS. Overlap met de toenmalige rolmatrix (inmiddels verwijderd, OP-143): nul.

    Gemeten 2026-08-16 door de Gate 2-reviewer: in een tenant die via deze seeder is ingericht
    kreeg ook de beheerder een lege rechtenverzameling, dus werd ELKE broker-tool geweigerd en
    stond de piloot nog steeds stil op MISSING_SCOPE.
    """

    async def test_a_seeded_admin_may_run_the_pilot_tool(self, db_session: AsyncSession) -> None:
        from sqlalchemy import select

        from src.core.auth.rbac import rbac_service
        from src.core.models.rbac_models import Role, Tenant, User
        from src.core.services.rbac_service import RBACService

        tenant_id = 4340
        db_session.add(Tenant(id=tenant_id, name="Seeder 4340", slug="seeder-4340"))
        await db_session.commit()

        # `ensure_default_roles` en NIET `RoleSeeder` (ADR-036 OP-235b). Die tweede zaaier
        # was dode code -- nul productie-importeurs, gemeten 2026-09-15 -- en is verwijderd.
        # Deze test toetste dus tot vandaag een zaaipad dat geen enkele tenant doorliep.
        await RBACService(db_session).ensure_default_roles(tenant_id)
        await db_session.commit()

        rollen = list(
            (await db_session.execute(select(Role).where(Role.tenant_id == tenant_id)))
            .scalars()
            .all()
        )
        assert rollen, "ensure_default_roles maakte geen rollen; dan toetst deze test niets."
        beheerder = next((r for r in rollen if r.name.strip().lower() == "admin"), None)
        assert beheerder is not None, (
            f"Geen beheerdersrol na ensure_default_roles: {sorted(r.name for r in rollen)}."
        )

        gebruiker = User(id=4341, tenant_id=tenant_id, email="seed@scope.test", hashed_password="x")
        gebruiker.roles.append(beheerder)
        db_session.add(gebruiker)
        await db_session.commit()

        assert await rbac_service.user_has_scope_for(4341, HR_TOOL, tenant_id=tenant_id) is True, (
            f"De beheerder van een normaal ingerichte tenant mag de piloot-tool niet draaien. "
            f"Gezaaid is de rolnaam {beheerder.name!r}; komt die niet overeen met "
            "een rij in `role_permissions`, dan krijgt niemand ooit een recht."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestPermissionsComeFromAllRoles:
    async def test_a_second_role_can_carry_the_permission(self, db_session: AsyncSession) -> None:
        """De UNIE over rollen, met het recht in de TWEEDE rol.

        Elke andere test geeft een gebruiker precies een rol, dus een terugval op `roles[0]`
        zou daar groen blijven. `user_roles` kent geen ordening, dus 'de eerste rol' is niet
        gedefinieerd -- daarom de unie, en daarom deze test.
        """
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from src.core.auth.rbac import rbac_service
        from src.core.models.rbac_models import Role, User

        await _user_with_role(db_session, user_id=4350, tenant_id=TENANT_A, role_name="user")
        # `selectinload`: zonder dit doet `.roles.append(...)` een lazy load, en die werkt niet
        # in async (MissingGreenlet).
        gebruiker = (
            await db_session.execute(
                select(User).options(selectinload(User.roles)).where(User.id == 4350)
            )
        ).scalar_one()
        tweede = (
            (
                await db_session.execute(
                    select(Role).where(Role.tenant_id == TENANT_A, Role.name == "admin")
                )
            )
            .scalars()
            .one()
        )
        gebruiker.roles.append(tweede)
        await db_session.commit()

        assert await rbac_service.user_has_scope_for(4350, HR_TOOL, tenant_id=TENANT_A) is True, (
            "Het recht zit in de tweede rol en telt niet mee. Wordt alleen de eerste rol "
            "gelezen, dan hangt het antwoord af van een volgorde die niet is gedefinieerd."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheCheckIsTenantBound:
    async def test_a_permission_does_not_travel_across_tenants(
        self, db_session: AsyncSession
    ) -> None:
        """Beheerder van tenant B is geen beheerder van tenant A.

        `user_has_scope_for` kreeg alleen een `user_id`. Een opzoeking op alleen dat nummer is
        precies het patroon dat CLAUDE.md-regel 11 verbiedt.
        """
        from src.core.auth.rbac import rbac_service

        await _user_with_role(db_session, user_id=4320, tenant_id=TENANT_B, role_name="admin")

        assert await rbac_service.user_has_scope_for(4320, HR_TOOL, tenant_id=TENANT_A) is False, (
            "Een beheerder uit een andere tenant kwam door de controle. Dat is een "
            "cross-tenant rechtenlek."
        )

    async def test_without_a_tenant_the_check_fails_closed(self, db_session: AsyncSession) -> None:
        """Kan de controle niet tenant-gebonden worden uitgevoerd, dan is het antwoord nee."""
        from src.core.auth.rbac import rbac_service

        await _user_with_role(db_session, user_id=4321, tenant_id=TENANT_A, role_name="admin")

        assert await rbac_service.user_has_scope_for(4321, HR_TOOL) is False, (
            "Zonder tenant kwam de controle toch door. Een vergeten parameter mag nooit een "
            "openstaande deur zijn."
        )

    async def test_a_deactivated_role_grants_nothing(self, db_session: AsyncSession) -> None:
        """Een rol uitzetten MOET de toegang stoppen.

        Gate 2-review ronde 2: de eerste versie las alleen `rol.name` en negeerde
        `Role.is_active`. Een beheerder die een rol deactiveert verwacht dat de toegang
        stopt; met `admin` betekende dat: personeelsgegevens blijven opvraagbaar.
        """
        from sqlalchemy import select

        from src.core.auth.rbac import rbac_service
        from src.core.models.rbac_models import Role

        await _user_with_role(db_session, user_id=4330, tenant_id=TENANT_A, role_name="admin")
        rol = (
            (
                await db_session.execute(
                    select(Role).where(Role.tenant_id == TENANT_A, Role.name == "admin")
                )
            )
            .scalars()
            .first()
        )
        assert rol is not None
        rol.is_active = False
        await db_session.commit()

        assert await rbac_service.user_has_scope_for(4330, HR_TOOL, tenant_id=TENANT_A) is False, (
            "Een gedeactiveerde rol geeft nog steeds toegang. Uitzetten doet dan niets."
        )

    async def test_a_role_from_another_tenant_grants_nothing(
        self, db_session: AsyncSession
    ) -> None:
        """De koppeltabel `user_roles` heeft geen tenantkolom -- de ROL wel.

        Gate 2-ronde 3: de tenant-helft van de rolcontrole had geen test. Elke andere test
        maakt de rol aan in de tenant van de gebruiker zelf, dus die conditie kon worden
        verwijderd zonder dat er iets rood werd. Deze toestand is echt mogelijk: niets in het
        schema verbiedt dat een rol uit tenant B aan een gebruiker in tenant A hangt.
        """
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from src.core.auth.rbac import rbac_service
        from src.core.models.rbac_models import Role, Tenant, User

        await _user_with_role(db_session, user_id=4360, tenant_id=TENANT_A, role_name="user")
        bestaat_b = (
            await db_session.execute(select(Tenant).where(Tenant.id == TENANT_B))
        ).scalar_one_or_none()
        if bestaat_b is None:
            db_session.add(Tenant(id=TENANT_B, name="Scope 4302", slug="scope-4302"))
            await db_session.flush()

        from src.core.models.rbac_models import RolePermission

        vreemde_rol = Role(tenant_id=TENANT_B, name="admin")
        db_session.add(vreemde_rol)
        await db_session.flush()
        # Een ECHTE beheerdersrol van de andere tenant: met een `*:*`-rij. Zonder rij zou de
        # weigering ook volgen uit "geen rechten" en bewijst de test niets over de tenantgrens.
        db_session.add(
            RolePermission(role_id=vreemde_rol.id, tenant_id=TENANT_B, resource="*", action="*")
        )
        await db_session.flush()
        gebruiker = (
            await db_session.execute(
                select(User).options(selectinload(User.roles)).where(User.id == 4360)
            )
        ).scalar_one()
        gebruiker.roles.append(vreemde_rol)
        await db_session.commit()

        assert await rbac_service.user_has_scope_for(4360, HR_TOOL, tenant_id=TENANT_A) is False, (
            "Een beheerdersrol die bij een ANDERE tenant hoort telde mee. Dat is een "
            "cross-tenant rechtenlek via de koppeltabel."
        )

    async def test_an_unknown_user_is_refused(self, db_session: AsyncSession) -> None:
        from sqlalchemy import select

        from src.core.auth.rbac import rbac_service

        afwezig = (
            await db_session.execute(select(User).where(User.id == 999_999))
        ).scalar_one_or_none()
        assert afwezig is None, "Deze gebruiker hoort niet te bestaan; anders toetst de test niets."

        assert await rbac_service.user_has_scope_for(999_999, HR_TOOL, tenant_id=TENANT_A) is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestCopilotBehaviourIsUnchanged:
    async def test_a_copilot_action_still_passes_without_a_tenant(self) -> None:
        """Vangnet tegen een stille regressie op het copilot-pad.

        De chat-acties uit `_COUNCIL_ALLOWED_ACTION_TYPES` gedroegen zich altijd al zo: naam op
        de lijst is genoeg. Die grens verschuift vandaag NIET -- deze dag gaat over toolnamen
        die daar niet op staan. Verandert dit antwoord, dan is de copilot geraakt door werk dat
        alleen het agent-pad hoorde te raken.
        """
        from src.core.auth.rbac import rbac_service

        assert await rbac_service.user_has_scope_for(1, COPILOT_ACTIE) is True

    async def test_an_unknown_copilot_action_is_still_refused(self) -> None:
        from src.core.auth.rbac import rbac_service

        assert await rbac_service.user_has_scope_for(1, "unknown:nonexistent_xyz") is False
