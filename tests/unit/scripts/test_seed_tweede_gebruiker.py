"""`scripts/seed_tweede_gebruiker.py` weigert in production/staging en maakt een niet-beheerder.

Keten B nazorg, punt G: er is geen gebruiker zonder beheerdersrol om de rolgrenzen mee te testen.
Het script maakt er een in de bestaande dev-tenant. Het script bestaat nog niet; deze tests leggen
de interface vast die de bouwer precies zo maakt (zie ook de terugmelding van de testspecialist):

    scripts/seed_tweede_gebruiker.py  (importeerbaar zonder bijwerkingen: geen get_config(),
                                       geen databaseverbinding op importniveau)

    class OmgevingGeweigerd(RuntimeError)

    def controleer_omgeving(env: Mapping[str, str]) -> None
        Gooit OmgevingGeweigerd als APP_ENV OF ENVIRONMENT (hoofdletterongevoelig, spaties
        genegeerd) "production" of "staging" is. Anders geen effect.

    async def maak_tweede_gebruiker(
        session: AsyncSession, *, tenant_id: int, email: str, password: str
    ) -> int
        Maakt (of hergebruikt, idempotent) de gebruiker in `tenant_id`, met PRECIES de rol "user"
        (de rol met alleen leesrechten), `is_superuser=False`. Maakt
        de rol "user" in die tenant als hij nog niet bestaat. Geeft het user-id terug. Schrijft het
        wachtwoord gehasht.

    def main(env: Mapping[str, str] | None = None) -> int
        Roept `controleer_omgeving` EERST aan (voor elke databasetoegang); bij weigering: meldt de
        reden op stderr en geeft exitcode 1. env=None betekent os.environ.

Waarom APP_ENV EN ENVIRONMENT: `.env.example` kent APP_ENV, de applicatieconfiguratie leest
ENVIRONMENT (src/core/config/config_validator.py). Een script dat alleen op de een let, laat de
ander door. Weigeren is fail-closed: alleen een van beide op production/staging is genoeg.

Autouse-fixtures nagelopen: `tests/conftest.py` zet ENVIRONMENT=test (geen invloed: de
weigertests geven hun eigen `env`-mapping mee en lezen os.environ niet).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.dependencies import is_admin
from src.core.auth.auth_service import UserResponse
from src.core.models.rbac_models import Role, Tenant, User, user_roles

# Geladen via bestandspad: `tests/unit/scripts/__init__.py` schaduwt het pakket `scripts`, dus
# `import scripts.seed_tweede_gebruiker` geeft los gedraaid ModuleNotFoundError.
SCRIPT_PAD = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "seed_tweede_gebruiker.py"
TENANT = 1


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_seed_tweede_gebruiker_under_test", SCRIPT_PAD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("omgeving", ["production", "staging", "Production", " STAGING "])
@pytest.mark.parametrize("variabele", ["APP_ENV", "ENVIRONMENT"])
def test_weigert_in_production_en_staging(variabele: str, omgeving: str) -> None:
    script = _script()

    with pytest.raises(script.OmgevingGeweigerd):
        script.controleer_omgeving({variabele: omgeving})


@pytest.mark.parametrize("omgeving", ["development", "test", "local"])
def test_weigert_niet_in_een_ontwikkelomgeving(omgeving: str) -> None:
    """Andere kant op: 'weiger altijd' is geen geldige oplossing."""
    script = _script()

    assert script.controleer_omgeving({"APP_ENV": omgeving}) is None


def test_main_geeft_exitcode_1_in_production_zonder_database_te_raken() -> None:
    script = _script()

    assert script.main({"APP_ENV": "production"}) == 1


async def test_maakt_een_gebruiker_met_alleen_de_rol_user(db_session: AsyncSession) -> None:
    script = _script()
    db_session.add(Tenant(id=TENANT, name="T1", slug="seed-tweede-1"))
    await db_session.commit()

    user_id = await script.maak_tweede_gebruiker(
        db_session, tenant_id=TENANT, email="medewerker@x.example", password="Wachtwoord-1!"
    )

    rollen = (
        await db_session.execute(
            select(Role.name)
            .join(user_roles, user_roles.c.role_id == Role.id)
            .where(user_roles.c.user_id == user_id)
        )
    ).scalars().all()
    assert list(rollen) == ["user"]


async def test_de_gebruiker_is_geen_superuser(db_session: AsyncSession) -> None:
    script = _script()
    db_session.add(Tenant(id=TENANT, name="T1", slug="seed-tweede-2"))
    await db_session.commit()

    user_id = await script.maak_tweede_gebruiker(
        db_session, tenant_id=TENANT, email="medewerker@x.example", password="Wachtwoord-1!"
    )

    gebruiker = (await db_session.execute(select(User).where(User.id == user_id))).scalar_one()
    assert gebruiker.is_superuser is False


async def test_de_centrale_definitie_noemt_de_gebruiker_geen_beheerder(
    db_session: AsyncSession,
) -> None:
    script = _script()
    db_session.add(Tenant(id=TENANT, name="T1", slug="seed-tweede-3"))
    await db_session.commit()
    user_id = await script.maak_tweede_gebruiker(
        db_session, tenant_id=TENANT, email="medewerker@x.example", password="Wachtwoord-1!"
    )
    rollen = (
        await db_session.execute(
            select(Role.name)
            .join(user_roles, user_roles.c.role_id == Role.id)
            .where(user_roles.c.user_id == user_id)
        )
    ).scalars().all()

    gebruiker = UserResponse(
        id=user_id, email="medewerker@x.example", tenant_id=TENANT, roles=list(rollen)
    )

    assert is_admin(gebruiker) is False


async def test_twee_keer_draaien_maakt_geen_tweede_gebruiker(db_session: AsyncSession) -> None:
    """Idempotent: een herhaling levert hetzelfde id, geen duplicaat."""
    script = _script()
    db_session.add(Tenant(id=TENANT, name="T1", slug="seed-tweede-4"))
    await db_session.commit()

    eerste = await script.maak_tweede_gebruiker(
        db_session, tenant_id=TENANT, email="medewerker@x.example", password="Wachtwoord-1!"
    )
    tweede = await script.maak_tweede_gebruiker(
        db_session, tenant_id=TENANT, email="medewerker@x.example", password="Wachtwoord-1!"
    )

    assert eerste == tweede


def test_de_rol_debiteuren_kan_ook_leestools_gebruiken() -> None:
    """OP-143: een agent leest `role_permissions`; zonder `tools:read` kan de seedgebruiker niets.

    Gelijk aan de zaailijst in `RBACService.ensure_default_roles` (daar bewaakt
    `tests/architecture/test_role_permissions_cover_every_seeded_role.py` de tabel per rol).
    """
    rechten = set(_script().ROLLEN["debiteuren"][1])

    assert {("tools", "read"), ("receivables", "propose")} <= rechten

