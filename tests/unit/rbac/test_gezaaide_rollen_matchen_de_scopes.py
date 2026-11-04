"""Gezaaide rollen krijgen rechten die de scopes ook echt dekken (OP-187 + OP-191).

**OP-191 -- de grammatica.** Endpoints EISEN meervoud (`agents:read`, `workflows:read`;
`src/core/auth/scopes.py`), maar `ensure_default_roles` zaaide enkelvoud (`agent`,
`workflow`). `scope_validator` splitst `agents:read` naar `resource="agents"` en
`user_has_permission` matcht letterlijk op `resource == "agents"` of `"*"`. `"agent"` is niet
`"agents"`, dus `editor` en `user` hadden rechten die met geen enkele scope konden matchen --
alleen `admin` overleefde, via zijn wildcard.

**OP-187 -- de overslaan-tak.** `if name not in existing_names:` stond om de HELE tak heen,
dus een rol die al bestond kreeg nooit zijn permissierijen. Gemeten 2026-09-15 in de live
database: `user` bestond met NUL rechten terwijl de standaardlijst hem er twee belooft.

**Beide richtingen, met opzet.** Zonder de tegentests zou "geef elke rol de wildcard" de
eerste twee halen, en dan is elke gebruiker beheerder.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import Role, RolePermission, Tenant
from src.core.services.rbac_service import RBACService


async def _rechten_van(db: AsyncSession, tenant_id: int, rolnaam: str) -> set[tuple[str, str]]:
    rol = (
        await db.execute(select(Role).where(Role.tenant_id == tenant_id, Role.name == rolnaam))
    ).scalar_one_or_none()
    assert rol is not None, f"Rol {rolnaam!r} bestaat niet in tenant {tenant_id}."
    rijen = await db.execute(
        select(RolePermission.resource, RolePermission.action).where(
            RolePermission.role_id == rol.id
        )
    )
    return {(r, a) for r, a in rijen.all()}


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeGezaaideRechtenSprekenDeTaalVanDeScopes:
    async def test_een_gezaaide_rol_dekt_de_scope_die_endpoints_eisen(
        self, db_session: AsyncSession
    ) -> None:
        """OP-191: `agents:read` moet matchen op wat `user` krijgt."""
        tenant_id = 5191
        db_session.add(Tenant(id=tenant_id, name="Grammatica", slug="grammatica-5191"))
        await db_session.commit()

        await RBACService(db_session).ensure_default_roles(tenant_id)

        rechten = await _rechten_van(db_session, tenant_id, "user")
        assert ("agents", "read") in rechten, (
            f"De rol `user` kreeg {sorted(rechten)}. Endpoints eisen `agents:read`, en "
            "`user_has_permission` matcht letterlijk op de resource -- enkelvoud `agent` "
            "matcht daar nooit mee (ADR-036 OP-191)."
        )

    async def test_een_gezaaide_rol_krijgt_niet_meer_dan_bedoeld(
        self, db_session: AsyncSession
    ) -> None:
        """De andere richting: zonder deze zou 'geef iedereen de wildcard' halen."""
        tenant_id = 5192
        db_session.add(Tenant(id=tenant_id, name="Grens", slug="grens-5192"))
        await db_session.commit()

        await RBACService(db_session).ensure_default_roles(tenant_id)

        rechten = await _rechten_van(db_session, tenant_id, "user")
        assert ("*", "*") not in rechten, (
            f"De rol `user` kreeg de wildcard: {sorted(rechten)}. Dan is elke gebruiker "
            "beheerder en is de reparatie erger dan de fout."
        )
        assert ("users", "write") not in rechten


@pytest.mark.unit
@pytest.mark.asyncio
class TestEenBestaandeRolKrijgtZijnRechtenAlsnog:
    async def test_een_rol_zonder_rechten_wordt_aangevuld(self, db_session: AsyncSession) -> None:
        """OP-187: de overslaan-tak liet een bestaande rol permissieloos achter."""
        tenant_id = 5193
        db_session.add(Tenant(id=tenant_id, name="Aanvullen", slug="aanvullen-5193"))
        db_session.add(Role(tenant_id=tenant_id, name="user", description="Bestond al"))
        await db_session.commit()

        assert await _rechten_van(db_session, tenant_id, "user") == set()

        await RBACService(db_session).ensure_default_roles(tenant_id)

        rechten = await _rechten_van(db_session, tenant_id, "user")
        assert ("agents", "read") in rechten, (
            "Een rol die al bestond kreeg zijn rechten niet. `ensure_default_roles` hoort de "
            "standaard te GARANDEREN, niet alleen bij een lege tenant (ADR-036 OP-187)."
        )

    async def test_een_rol_buiten_de_standaardlijst_blijft_ongemoeid(
        self, db_session: AsyncSession
    ) -> None:
        """De andere richting: de functie mag geen rechten uitdelen die niemand vroeg.

        Zonder deze test zou 'geef elke bestaande rol de wildcard' de test hierboven halen --
        en dan wordt precies het OP-185-primitief een privilege-escalatie.
        """
        tenant_id = 5194
        db_session.add(Tenant(id=tenant_id, name="Ongemoeid", slug="ongemoeid-5194"))
        db_session.add(
            Role(tenant_id=tenant_id, name="system_admin", description="Niet in de lijst")
        )
        await db_session.commit()

        await RBACService(db_session).ensure_default_roles(tenant_id)

        rechten = await _rechten_van(db_session, tenant_id, "system_admin")
        assert rechten == set(), (
            f"Een rol buiten de standaardlijst kreeg rechten: {sorted(rechten)}. Dat is "
            "precies de signatuur van het OP-185-primitief, nu met rechten erbij."
        )

    async def test_twee_keer_zaaien_verdubbelt_niets(self, db_session: AsyncSession) -> None:
        """Idempotent: de functie wordt op meerdere plekken aangeroepen."""
        tenant_id = 5195
        db_session.add(Tenant(id=tenant_id, name="Idempotent", slug="idempotent-5195"))
        await db_session.commit()

        dienst = RBACService(db_session)
        await dienst.ensure_default_roles(tenant_id)
        eerste = await _rechten_van(db_session, tenant_id, "user")
        await dienst.ensure_default_roles(tenant_id)
        tweede = await _rechten_van(db_session, tenant_id, "user")

        assert eerste == tweede, (
            "Een tweede aanroep veranderde de rechten. `ensure_default_roles` wordt vanuit "
            "drie plekken aangeroepen; dubbele rijen zijn dan een kwestie van tijd."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestRolmodelDebiteuren:
    """Optie A (plan-van-aanpak-nazorg deel II punt 1): een rol `debiteuren` met precies
    `receivables:read` en `receivables:write`; de rol `user` mag debiteuren alleen lezen.
    Sinds wfb-dag1 stap 7 ook `receivables:propose`: `/reminder-proposals` vraagt dat recht,
    gelijk aan de agent-tool `send_payment_reminder`."""

    async def test_de_rol_debiteuren_krijgt_precies_lezen_en_schrijven(
        self, db_session: AsyncSession
    ) -> None:
        tenant_id = 5195
        db_session.add(Tenant(id=tenant_id, name="Debiteuren", slug="debiteuren-5195"))
        await db_session.commit()

        await RBACService(db_session).ensure_default_roles(tenant_id)

        assert await _rechten_van(db_session, tenant_id, "debiteuren") == {
            ("receivables", "read"),
            ("receivables", "write"),
            ("receivables", "propose"),
            # OP-143: een agent leest `role_permissions`; de rol had in de oude matrix `read`.
            ("tools", "read"),
        }

    async def test_de_rol_user_mag_debiteuren_lezen_maar_niet_schrijven(
        self, db_session: AsyncSession
    ) -> None:
        tenant_id = 5196
        db_session.add(Tenant(id=tenant_id, name="Lezer", slug="lezer-5196"))
        await db_session.commit()

        await RBACService(db_session).ensure_default_roles(tenant_id)

        rechten = await _rechten_van(db_session, tenant_id, "user")
        assert ("receivables", "read") in rechten
        assert ("receivables", "write") not in rechten
        assert ("receivables", "propose") not in rechten

    async def test_twee_keer_zaaien_geeft_geen_dubbele_rechten(
        self, db_session: AsyncSession
    ) -> None:
        tenant_id = 5197
        db_session.add(Tenant(id=tenant_id, name="Idempotent", slug="idempotent-5197"))
        await db_session.commit()

        await RBACService(db_session).ensure_default_roles(tenant_id)
        await RBACService(db_session).ensure_default_roles(tenant_id)

        rol = (
            await db_session.execute(
                select(Role).where(Role.tenant_id == tenant_id, Role.name == "debiteuren")
            )
        ).scalar_one()
        aantal = (
            await db_session.execute(
                select(RolePermission.id).where(RolePermission.role_id == rol.id)
            )
        ).all()
        assert len(aantal) == 4  # read, write, propose en tools:read -- elk een keer
