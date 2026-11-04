"""De schrijfpaden van `user_roles` onder de applicatierol (ADR-036 OP-190, deel 1).

`test_user_roles_is_confined_to_its_tenant.py` bewijst de POLICY met kale SQL. Deze module
bewijst wat de registerrij van OP-190 als niet gedaan noemt: dat de ECHTE schrijfplekken in
`src` blijven werken onder die policy, en dat ze er geen koppeling over de klantgrens mee
kunnen leggen of afnemen.

**Hoe de echte functies onder de applicatierol lopen.** Een asyncpg-verbinding naar de verse
migratiedatabase met `server_settings={"role": "sanskritisetu_app"}`: de verbinding is van de
eigenaar maar draait als de niet-eigenaar zonder BYPASSRLS (`current_user` wordt in
`test_the_session_runs_as_the_application_role` gemeten). De tenantcontext zet de ECHTE hook
`_zet_tenantcontext` (het `begin`-event op `Engine`) vanuit de ContextVar, precies zoals de
applicatie dat doet. Er is geen eigen policy of rol verzonnen.

**Wat "geweigerd" hier betekent.** Elke schrijfplek heeft naast de databasepolicy ook een
codecontrole (`_doelgebruiker_in_tenant`, `Role.tenant_id == ...`, `can_manage_users`). Een
poging over de klantgrens kan dus door de code of door de policy worden tegengehouden; de
tests toetsen het RESULTAAT: een fout of weigering EN geen enkele gekruiste rij erbij (en een
bestaande rij van de andere klant blijft staan). `vervang_rollen` heeft geen eigen
gebruikerscontrole -- de aanroeper is verantwoordelijk -- en is daardoor de plek waar de
policy zelf het laatste woord heeft (`TestRbacVervangRollen`).

**Staleness.** `SCHRIJFPLEKKEN` is de benoemde verzameling, gesleuteld op
`bestand::functie`. `TestDeLijstKlopt` leest `src` structureel (AST): een nieuwe schrijfplek
die niet in de lijst staat faalt, en een lijstregel waarvan de plek is verdwenen of waarvan
de testklasse niet bestaat faalt ook.

**Wat deze module NIET zegt.** Groen betekent: in deze database, onder de applicatierol, doen
deze zeven plekken wat ze moeten. Of een klant het in productie merkt hangt af van OP-151
(de draaiende applicatie verbindt als tabeleigenaar en omzeilt elke policy) en van deel 2
van OP-190 (een kolom `tenant_id` op `user_roles`). De scripts `src/ensure_demo_user.py` en
`scripts/seed_demo.py` draaien buiten de applicatie en zijn niet gemeten.

**Rood voor de reparatie (gemeten 2026-10-09, serieel, DB `sanskritisetu_b`).** De fixture van
`test_the_application_role_is_confined_to_its_tenant.py` zoals op 4c966d81: `31 errors`
(`tenants.max_agents` NOT NULL). Na de fixture gaf dat bestand `30 passed, 1 failed`: de
guard `test_geen_enkele_policy_heeft_een_onbewezen_vorm` meldde de policy
`user_roles.rls_user_roles_tenant_isolation`; die staat nu met reden in
`_KNOWN_AFWIJKENDE_VORM`.

**Mutatiebewijs (2026-10-09), elke regel een run van dit bestand, kopie als terugweg:**
- `_zet_tenantcontext` uitgezet (de `begin`-hook doet niets) -> 12 ROOD: elke schrijfactie
  binnen de eigen klant, de sessiemeting en `test_the_policy_alone_refuses_...`.
- Policy op `user_roles` vervangen door `USING (true) WITH CHECK (true)` -> 1 ROOD:
  `TestRbacVervangRollen::test_the_policy_alone_refuses_a_user_of_another_customer`, de enige
  plek zonder codecontrole.
- `vervang_rollen` zonder `Role.tenant_id`-vergelijking -> 30 GROEN. Dat is een bevinding
  over de dieptebescherming, geen gat in de test: onder de applicatierol verbergt de policy
  op `roles` de rol van de andere klant, dus de codecontrole is er dubbel. Waar de
  applicatie als eigenaar verbindt (OP-151) is hij de enige.
- `assign_role` zonder `_doelgebruiker_in_tenant` -> 30 GROEN, zelfde reden: de policy op
  `user_roles` weigert de koppeling.
- Een regel in `SCHRIJFPLEKKEN` die niet bestaat -> 2 ROOD (`test_no_listed_site_has_
  disappeared`, `test_every_listed_site_has_an_existing_test_class`).
- Een nieuw bestand met `user_roles.insert()` in `src/core` -> 1 ROOD
  (`test_every_write_site_in_src_is_in_the_list`); een bestand met een lokale lijst
  `roles.append(1)` en `user_roles.select()` -> GROEN.
- Alles ongewijzigd -> 30 passed.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import psycopg2
import pytest
from fastapi import HTTPException
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, connection as PgConnection
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from tests.fixtures.testdatabase import testdatabase_poort
from tests.integration.security.test_the_application_role_is_confined_to_its_tenant import (
    _ROL,
    _SCRATCH_DB,
    _bouw_verse_database,
    _dsn,
    _postgres_bereikbaar,
)

from src.core.api.v1.user_management.crud_router import (
    RoleAssignment,
    UserCreate as BeheerUserCreate,
    assign_user_roles,
    create_user as beheer_create_user,
)
from src.core.api.v1.users.schemas import UserCreate as LijstUserCreate, UserUpdate
from src.core.api.v1.users.users_detail_router import update_user as detail_update_user
from src.core.api.v1.users.users_list_router import create_user as lijst_create_user
from src.core.auth.api_deps import UserResponse as AuthUserResponse
from src.core.auth.auth_service import AuthService, UserCreate as AuthUserCreate
from src.core.database.database import _zet_tenantcontext
from src.core.middleware.tenant_context import set_tenant_id
from src.core.models.rbac_models import User
from src.core.services.rbac_service import RBACService

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WACHTWOORD = "Sterk-Wachtwoord1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.skipif(
        not _postgres_bereikbaar(),
        reason="vereist PostgreSQL op de netwerkpoort uit SANSKRITISETU_TEST_DATABASE_URL",
    ),
]


# --------------------------------------------------------------------------------------
# De benoemde verzameling: elke schrijfplek op `user_roles` in `src`, per bestand::functie
# --------------------------------------------------------------------------------------

#: Schrijfplek -> de testklasse hieronder die hem aanroept. Gemeten 2026-10-09 op 4c966d81.
SCHRIJFPLEKKEN: dict[str, str] = {
    "src/core/auth/auth_service.py::AuthService.create_user": "TestAuthServiceCreateUser",
    "src/core/api/v1/user_management/crud_router.py::create_user": "TestBeheerCreateUser",
    "src/core/api/v1/users/users_list_router.py::create_user": "TestLijstCreateUser",
    "src/core/api/v1/users/users_detail_router.py::update_user": "TestDetailUpdateUser",
    "src/core/services/rbac_service.py::RBACService.assign_role": "TestRbacAssignRole",
    "src/core/services/rbac_service.py::RBACService.revoke_role": "TestRbacRevokeRole",
    "src/core/services/rbac_service.py::RBACService.vervang_rollen": "TestRbacVervangRollen",
}

#: Treffers van de scan die GEEN schrijfplek op de applicatiedatabase zijn. Reden per regel.
KNOWN_BUITEN_BEREIK: dict[str, str] = {
    "src/ensure_demo_user.py::_zorg_voor_rol_en_gebruiker": (
        "Script dat de demogebruiker aanmaakt, buiten de draaiende applicatie. Niet gemeten "
        "onder de applicatierol; genoemd in de brief van OP-190 deel 1 -- 2026-10-09."
    ),
    "src/core/auth/websocket_auth.py::AuthenticatedUser.__post_init__": (
        "`self.roles = []` op een gewone dataclass met rolnamen als tekst; geen ORM-relatie "
        "en geen database -- 2026-10-09."
    ),
}

_TABEL_SCHRIJVERS = {"insert", "delete", "update"}
_LIJST_SCHRIJVERS = {"extend", "append", "remove", "clear", "insert", "pop"}


# --------------------------------------------------------------------------------------
# Opstelling
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Wereld:
    """De echte rijen waar de tests mee werken, per klant."""

    tenant_a: int
    tenant_b: int
    rol_a: int
    rol_a_extra: int
    rol_a_user: int
    rol_b: int
    rol_b_extra: int
    rol_b_user: int
    beheerder_a: int


def _nieuw_id(cur: psycopg2.extensions.cursor) -> int:
    rij = cur.fetchone()
    assert rij is not None, "INSERT ... RETURNING id gaf geen rij terug: de opstelling is mislukt"
    return int(rij[0])


@pytest.fixture(scope="module")
def db() -> Iterator[PgConnection]:
    """Verse database uit de migratieketen; de eigenaarsverbinding is alleen voor de opstelling."""
    _bouw_verse_database()
    conn = psycopg2.connect(_dsn(_SCRATCH_DB))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def wereld(db: PgConnection) -> Wereld:
    """Twee klanten met elk hun rollen, aangemaakt als eigenaar (omzeilt RLS)."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
            "VALUES ('Pad A', 'pad-a', true, 10, 50, 5), ('Pad B', 'pad-b', true, 10, 50, 5)"
        )
        cur.execute("SELECT slug, id FROM tenants WHERE slug IN ('pad-a', 'pad-b')")
        tenants = dict(cur.fetchall())
        rollen: dict[str, int] = {}
        for sleutel, slug, naam in (
            ("rol_a", "pad-a", "rol-a"),
            ("rol_a_extra", "pad-a", "rol-a-extra"),
            ("rol_a_user", "pad-a", "user"),
            ("rol_b", "pad-b", "rol-b"),
            ("rol_b_extra", "pad-b", "rol-b-extra"),
            ("rol_b_user", "pad-b", "user"),
        ):
            cur.execute(
                "INSERT INTO roles (tenant_id, name) VALUES (%s, %s) RETURNING id",
                (tenants[slug], naam),
            )
            rollen[sleutel] = _nieuw_id(cur)
        # Een echte beheerder: het auditlog heeft een foreign key op `users`, dus een
        # verzonnen id (0) laat de auditregel van de route stuklopen.
        cur.execute(
            "INSERT INTO users (tenant_id, email) VALUES (%s, %s) RETURNING id",
            (tenants["pad-a"], _email("beheerder")),
        )
        beheerder_a = _nieuw_id(cur)
    return Wereld(
        tenant_a=tenants["pad-a"], tenant_b=tenants["pad-b"], beheerder_a=beheerder_a, **rollen
    )


def _gebruiker(db: PgConnection, tenant: int, rollen: tuple[int, ...] = ()) -> int:
    """Een verse gebruiker als eigenaar, optioneel met koppelingen; per test een eigen rij."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO users (tenant_id, email) VALUES (%s, %s) RETURNING id",
            (tenant, _email("pad")),
        )
        user_id = _nieuw_id(cur)
        for rol in rollen:
            cur.execute("INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)", (user_id, rol))
    return user_id


def _rollen_van(db: PgConnection, user_id: int) -> set[int]:
    """De rol-ids van een gebruiker, en (OP-190 deel 2) elke rij draagt de klant van de gebruiker."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT ur.role_id, ur.tenant_id, u.tenant_id FROM user_roles ur "
            "JOIN users u ON u.id = ur.user_id WHERE ur.user_id = %s",
            (user_id,),
        )
        rijen = cur.fetchall()
    verkeerd = [r for r in rijen if r[1] != r[2]]
    assert not verkeerd, f"koppeling(en) zonder de klant van de gebruiker: {verkeerd}"
    return {int(rij[0]) for rij in rijen}


def _gebruiker_met_email(db: PgConnection, email: str) -> int | None:
    with db.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        rij = cur.fetchone()
    return None if rij is None else int(rij[0])


def _aantal_gekruist(db: PgConnection) -> int:
    """Koppelingen waarvan gebruiker en rol bij VERSCHILLENDE klanten horen."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM user_roles ur "
            "JOIN users u ON u.id = ur.user_id JOIN roles r ON r.id = ur.role_id "
            "WHERE u.tenant_id <> r.tenant_id"
        )
        rij = cur.fetchone()
    assert rij is not None
    return int(rij[0])


def _async_url() -> str:
    gebruiker = os.environ.get("POSTGRES_USER", "postgres")
    wachtwoord = os.environ.get("POSTGRES_PASSWORD", "postgres")
    return (
        f"postgresql+asyncpg://{gebruiker}:{wachtwoord}@127.0.0.1:"
        f"{testdatabase_poort()}/{_SCRATCH_DB}"
    )


@asynccontextmanager
async def _applicatiesessie(tenant: int | None) -> AsyncGenerator[AsyncSession]:
    """Een sessie die als `sanskritisetu_app` draait, met de tenantcontext van de ContextVar."""
    engine = create_async_engine(
        _async_url(), poolclass=NullPool, connect_args={"server_settings": {"role": _ROL}}
    )
    set_tenant_id(tenant)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as sessie:
            yield sessie
    finally:
        set_tenant_id(None)
        await engine.dispose()


def _ingelogd(wereld: Wereld, *, superuser: bool = False) -> SimpleNamespace:
    """De ingelogde gebruiker zoals de routes hem krijgen: id, klant, rolnamen, superuservlag."""
    return SimpleNamespace(
        id=wereld.beheerder_a,
        email="beheer@op190.example.com",
        tenant_id=wereld.tenant_a,
        roles=["admin"],
        is_superuser=superuser,
    )


def _als_user(wereld: Wereld, *, superuser: bool = False) -> User:
    return cast(User, _ingelogd(wereld, superuser=superuser))


def _als_auth_user(wereld: Wereld) -> AuthUserResponse:
    return cast(AuthUserResponse, _ingelogd(wereld))


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:10]}@op190.example.com"


# --------------------------------------------------------------------------------------
# De meting zelf is niet leeg
# --------------------------------------------------------------------------------------


class TestDeMetingIsNietLeeg:
    def test_the_tenant_hook_is_registered_on_the_engine_class(self) -> None:
        """Zonder de `begin`-hook staat `app.current_tenant` leeg en slaagt GEEN schrijfactie."""
        assert event.contains(Engine, "begin", _zet_tenantcontext)

    async def test_the_session_runs_as_the_application_role(self, wereld: Wereld) -> None:
        """Draaide de sessie als eigenaar, dan bewijst elke test hieronder niets."""
        async with _applicatiesessie(wereld.tenant_a) as sessie:
            rij = (
                await sessie.execute(
                    text("SELECT current_user, current_setting('app.current_tenant', true)")
                )
            ).one()

        assert (rij[0], rij[1]) == (_ROL, str(wereld.tenant_a))

    def test_the_crossing_count_sees_a_crossing_row(self, db: PgConnection, wereld: Wereld) -> None:
        """Controlegroep: de telling vindt een gekruiste rij als die er is.

        Sinds OP-190 deel 2 weigert de database zo'n rij. Om de telling toch te toetsen haalt
        deze test de sleutel naar `roles` binnen EEN transactie weg, legt de rij, telt, en
        draait alles terug (ROLLBACK): het schema en de data blijven zoals ze waren.
        """
        voor = _aantal_gekruist(db)
        gebruiker_a = _gebruiker(db, wereld.tenant_a)
        with db.cursor() as cur:
            cur.execute("BEGIN")
            try:
                cur.execute("ALTER TABLE user_roles DROP CONSTRAINT fk_user_roles_role_tenant")
                cur.execute(
                    "INSERT INTO user_roles (user_id, role_id, tenant_id) VALUES (%s, %s, %s)",
                    (gebruiker_a, wereld.rol_b, wereld.tenant_a),
                )
                tijdens = _aantal_gekruist(db)
            finally:
                cur.execute("ROLLBACK")

        assert (voor, tijdens, _aantal_gekruist(db)) == (0, 1, 0)


# --------------------------------------------------------------------------------------
# De zeven schrijfplekken
# --------------------------------------------------------------------------------------


class TestAuthServiceCreateUser:
    """`AuthService.create_user` -- het registratiepad (auth_service.py)."""

    async def test_inside_the_own_tenant_the_user_and_the_link_are_written(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        email = _email("registratie")

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            resultaat = await AuthService().create_user(
                sessie,
                AuthUserCreate(email=email, password=_WACHTWOORD, role_name="rol-a"),
                tenant_id=wereld.tenant_a,
                request_path="/test",
            )

        user_id = _gebruiker_met_email(db, email)
        assert resultaat is not None and user_id is not None
        assert _rollen_van(db, user_id) == {wereld.rol_a}

    @pytest.mark.parametrize(
        "doel_klant,rolnaam",
        [("b", "rol-b"), ("a", "rol-b")],
        ids=["klant-b-met-rol-van-b", "eigen-klant-met-rol-van-b"],
    )
    async def test_across_the_tenant_border_nothing_is_written(
        self, db: PgConnection, wereld: Wereld, doel_klant: str, rolnaam: str
    ) -> None:
        email = _email("registratie-vreemd")
        gekruist_voor = _aantal_gekruist(db)
        tenant = wereld.tenant_a if doel_klant == "a" else wereld.tenant_b

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            resultaat = await AuthService().create_user(
                sessie,
                AuthUserCreate(email=email, password=_WACHTWOORD, role_name=rolnaam),
                tenant_id=tenant,
                request_path="/test",
            )

        assert resultaat is None
        assert _gebruiker_met_email(db, email) is None
        assert _aantal_gekruist(db) == gekruist_voor


class TestBeheerCreateUser:
    """`create_user` in `api/v1/user_management/crud_router.py` (beheerderspad)."""

    async def test_inside_the_own_tenant_the_user_and_the_link_are_written(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        email = _email("beheer")

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            await beheer_create_user(
                BeheerUserCreate(
                    email=email,
                    password=_WACHTWOORD,
                    full_name=None,
                    is_active=True,
                    role_ids=[wereld.rol_a],
                ),
                wereld.tenant_a,
                sessie,
                _als_auth_user(wereld),
            )

        user_id = _gebruiker_met_email(db, email)
        assert user_id is not None
        assert _rollen_van(db, user_id) == {wereld.rol_a}

    async def test_a_target_tenant_of_another_customer_writes_nothing(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        email = _email("beheer-vreemd")
        gekruist_voor = _aantal_gekruist(db)

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            with pytest.raises((HTTPException, DBAPIError)):
                await beheer_create_user(
                    BeheerUserCreate(
                        email=email,
                        password=_WACHTWOORD,
                        full_name=None,
                        is_active=True,
                        role_ids=[wereld.rol_b],
                    ),
                    wereld.tenant_b,
                    sessie,
                    _als_auth_user(wereld),
                )

        assert _gebruiker_met_email(db, email) is None
        assert _aantal_gekruist(db) == gekruist_voor

    async def test_a_role_of_another_customer_is_skipped_and_never_linked(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        email = _email("beheer-vreemde-rol")
        gekruist_voor = _aantal_gekruist(db)

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            await beheer_create_user(
                BeheerUserCreate(
                    email=email,
                    password=_WACHTWOORD,
                    full_name=None,
                    is_active=True,
                    role_ids=[wereld.rol_b],
                ),
                wereld.tenant_a,
                sessie,
                _als_auth_user(wereld),
            )

        user_id = _gebruiker_met_email(db, email)
        assert user_id is not None and _rollen_van(db, user_id) == set()
        assert _aantal_gekruist(db) == gekruist_voor


class TestLijstCreateUser:
    """`create_user` in `api/v1/users/users_list_router.py` (`user.roles.extend`)."""

    async def test_inside_the_own_tenant_the_extra_role_is_linked(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        email = _email("lijst")

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            await lijst_create_user(
                LijstUserCreate(email=email, password=_WACHTWOORD, role_ids=[wereld.rol_a_extra]),
                wereld.tenant_a,
                sessie,
                _als_user(wereld),
            )

        user_id = _gebruiker_met_email(db, email)
        assert user_id is not None
        assert _rollen_van(db, user_id) == {wereld.rol_a_user, wereld.rol_a_extra}

    async def test_a_superuser_targeting_another_customer_writes_nothing(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        """De codecontrole (`can_manage_users`) laat een superuser door; de database niet."""
        email = _email("lijst-vreemd")
        gekruist_voor = _aantal_gekruist(db)

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            with pytest.raises(HTTPException) as fout:
                await lijst_create_user(
                    LijstUserCreate(
                        email=email, password=_WACHTWOORD, role_ids=[wereld.rol_b_extra]
                    ),
                    wereld.tenant_b,
                    sessie,
                    _als_user(wereld, superuser=True),
                )

        assert fout.value.status_code == 400
        assert _gebruiker_met_email(db, email) is None
        assert _aantal_gekruist(db) == gekruist_voor

    async def test_a_role_of_another_customer_is_refused_and_never_linked(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        email = _email("lijst-vreemde-rol")
        gekruist_voor = _aantal_gekruist(db)

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            with pytest.raises(HTTPException) as fout:
                await lijst_create_user(
                    LijstUserCreate(email=email, password=_WACHTWOORD, role_ids=[wereld.rol_b]),
                    wereld.tenant_a,
                    sessie,
                    _als_user(wereld),
                )

        assert fout.value.status_code == 400
        assert _aantal_gekruist(db) == gekruist_voor


def _verzoek() -> SimpleNamespace:
    """Genoeg verzoek voor de auditregel van een platformweigering; deze tests sturen er geen af."""
    return SimpleNamespace(
        method="PUT", url=SimpleNamespace(path="/api/v1/users/0"), client=SimpleNamespace(host="127.0.0.1")
    )


class TestDetailUpdateUser:
    """`update_user` in `api/v1/users/users_detail_router.py` (`user.roles = roles`)."""

    async def test_inside_the_own_tenant_the_roles_are_replaced(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        user_id = _gebruiker(db, wereld.tenant_a, (wereld.rol_a,))

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            await detail_update_user(
                user_id,
                UserUpdate(role_ids=[wereld.rol_a_extra]),
                sessie,
                _als_user(wereld),
                request=_verzoek(),
            )

        assert _rollen_van(db, user_id) == {wereld.rol_a_extra}

    async def test_a_superuser_updating_a_user_of_another_customer_changes_nothing(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        """De codecontrole laat een superuser door; de policy verbergt de gebruiker."""
        user_id = _gebruiker(db, wereld.tenant_b, (wereld.rol_b,))

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            with pytest.raises(HTTPException) as fout:
                await detail_update_user(
                    user_id,
                    UserUpdate(role_ids=[wereld.rol_b_extra]),
                    sessie,
                    _als_user(wereld, superuser=True),
                    request=_verzoek(),
                )

        assert fout.value.status_code == 404
        assert _rollen_van(db, user_id) == {wereld.rol_b}

    async def test_a_role_of_another_customer_is_refused_and_the_old_link_stays(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        user_id = _gebruiker(db, wereld.tenant_a, (wereld.rol_a,))
        gekruist_voor = _aantal_gekruist(db)

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            with pytest.raises(HTTPException) as fout:
                await detail_update_user(
                    user_id,
                    UserUpdate(role_ids=[wereld.rol_b]),
                    sessie,
                    _als_user(wereld),
                    request=_verzoek(),
                )

        assert fout.value.status_code == 400
        assert _rollen_van(db, user_id) == {wereld.rol_a}
        assert _aantal_gekruist(db) == gekruist_voor


class TestRbacAssignRole:
    """`RBACService.assign_role` (`user_roles.insert`)."""

    async def test_inside_the_own_tenant_the_link_is_written(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        user_id = _gebruiker(db, wereld.tenant_a)

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            gelukt = await RBACService(sessie).assign_role(user_id, "rol-a-extra", wereld.tenant_a)

        assert gelukt is True
        assert _rollen_van(db, user_id) == {wereld.rol_a_extra}

    async def test_a_user_of_another_customer_gets_no_link(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        user_id = _gebruiker(db, wereld.tenant_b)
        gekruist_voor = _aantal_gekruist(db)

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            gelukt = await RBACService(sessie).assign_role(user_id, "rol-a", wereld.tenant_a)

        assert gelukt is False
        assert _rollen_van(db, user_id) == set()
        assert _aantal_gekruist(db) == gekruist_voor

    async def test_a_role_of_another_customer_is_not_linked(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        user_id = _gebruiker(db, wereld.tenant_a)
        gekruist_voor = _aantal_gekruist(db)

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            gelukt = await RBACService(sessie).assign_role(user_id, "rol-b", wereld.tenant_a)

        assert gelukt is False
        assert _rollen_van(db, user_id) == set()
        assert _aantal_gekruist(db) == gekruist_voor


class TestRbacRevokeRole:
    """`RBACService.revoke_role` (`user_roles.delete`)."""

    async def test_inside_the_own_tenant_the_link_is_removed(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        user_id = _gebruiker(db, wereld.tenant_a, (wereld.rol_a_extra,))

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            gelukt = await RBACService(sessie).revoke_role(user_id, "rol-a-extra", wereld.tenant_a)

        assert gelukt is True
        assert _rollen_van(db, user_id) == set()

    async def test_a_user_of_another_customer_keeps_his_link(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        user_id = _gebruiker(db, wereld.tenant_b, (wereld.rol_b,))

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            gelukt = await RBACService(sessie).revoke_role(user_id, "rol-a", wereld.tenant_a)

        assert gelukt is False
        assert _rollen_van(db, user_id) == {wereld.rol_b}


class TestRbacVervangRollen:
    """`RBACService.vervang_rollen` (`delete` + `insert`) en de route `assign_user_roles`."""

    async def test_inside_the_own_tenant_the_roles_are_replaced(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        user_id = _gebruiker(db, wereld.tenant_a, (wereld.rol_a,))

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            namen = await RBACService(sessie).vervang_rollen(
                user_id, [wereld.rol_a_extra], wereld.tenant_a
            )

        assert namen == ["rol-a-extra"]
        assert _rollen_van(db, user_id) == {wereld.rol_a_extra}

    async def test_the_policy_alone_refuses_a_user_of_another_customer(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        """Geen enkele codecontrole op de gebruiker: hier beslist de policy en niets anders."""
        user_id = _gebruiker(db, wereld.tenant_b, (wereld.rol_b,))
        gekruist_voor = _aantal_gekruist(db)

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            with pytest.raises(DBAPIError):
                await RBACService(sessie).vervang_rollen(user_id, [wereld.rol_a], wereld.tenant_a)

        assert _rollen_van(db, user_id) == {wereld.rol_b}
        assert _aantal_gekruist(db) == gekruist_voor

    async def test_a_role_of_another_customer_is_skipped_never_linked(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        user_id = _gebruiker(db, wereld.tenant_a, (wereld.rol_a,))
        gekruist_voor = _aantal_gekruist(db)

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            namen = await RBACService(sessie).vervang_rollen(
                user_id, [wereld.rol_b], wereld.tenant_a
            )

        assert namen == []
        assert _aantal_gekruist(db) == gekruist_voor

    async def test_the_route_replaces_roles_inside_the_own_tenant(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        user_id = _gebruiker(db, wereld.tenant_a, (wereld.rol_a,))

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            await assign_user_roles(
                user_id,
                RoleAssignment(role_ids=[wereld.rol_a_extra]),
                sessie,
                _als_auth_user(wereld),
            )

        assert _rollen_van(db, user_id) == {wereld.rol_a_extra}

    async def test_the_route_cannot_reach_a_user_of_another_customer(
        self, db: PgConnection, wereld: Wereld
    ) -> None:
        user_id = _gebruiker(db, wereld.tenant_b, (wereld.rol_b,))

        async with _applicatiesessie(wereld.tenant_a) as sessie:
            with pytest.raises(HTTPException) as fout:
                await assign_user_roles(
                    user_id,
                    RoleAssignment(role_ids=[wereld.rol_b_extra]),
                    sessie,
                    _als_auth_user(wereld),
                )

        assert fout.value.status_code == 404
        assert _rollen_van(db, user_id) == {wereld.rol_b}


# --------------------------------------------------------------------------------------
# Staleness: de lijst klopt met `src`
# --------------------------------------------------------------------------------------


def _is_naam(knoop: ast.expr, naam: str) -> bool:
    return (isinstance(knoop, ast.Name) and knoop.id == naam) or (
        isinstance(knoop, ast.Attribute) and knoop.attr == naam
    )


def _zoek_schrijfplekken_in(bron: str, pad: str) -> set[str]:
    """Structurele scan: `user_roles.insert/delete/update(...)` en mutaties van `<x>.roles`.

    Expliciete recursie met de omsluitende klasse/functie, want `ast.walk` kent geen scope.
    Een kale lokale lijst `roles.append(...)` (geen attribuut) telt NIET: dat is geen relatie.
    """
    gevonden: set[str] = set()

    def bezoek(knoop: ast.AST, scope: tuple[str, ...]) -> None:
        for kind in ast.iter_child_nodes(knoop):
            binnen = scope
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                binnen = (*scope, kind.name)
            raak = False
            if isinstance(kind, ast.Call) and isinstance(kind.func, ast.Attribute):
                if kind.func.attr in _TABEL_SCHRIJVERS and _is_naam(kind.func.value, "user_roles"):
                    raak = True
                elif (
                    kind.func.attr in _LIJST_SCHRIJVERS
                    and isinstance(kind.func.value, ast.Attribute)
                    and kind.func.value.attr == "roles"
                ):
                    raak = True
            elif isinstance(kind, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                doelen = kind.targets if isinstance(kind, ast.Assign) else [kind.target]
                raak = any(isinstance(d, ast.Attribute) and d.attr == "roles" for d in doelen)
            if raak:
                gevonden.add(f"{pad}::{'.'.join(scope)}")
            bezoek(kind, binnen)

    bezoek(ast.parse(bron), ())
    return gevonden


def _alle_schrijfplekken_in_src() -> set[str]:
    """Over `git ls-files` (ook nieuwe, nog niet gecommitte bestanden); migraties vallen af."""
    uitvoer = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "src"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\n")
    gevonden: set[str] = set()
    for pad in sorted(p for p in uitvoer if p.endswith(".py") and "/alembic/" not in p):
        bestand = _REPO_ROOT / pad
        if bestand.is_file():
            gevonden |= _zoek_schrijfplekken_in(bestand.read_text(encoding="utf-8"), pad)
    return gevonden


class TestDeLijstKlopt:
    def test_every_write_site_in_src_is_in_the_list(self) -> None:
        onbekend = _alle_schrijfplekken_in_src() - set(SCHRIJFPLEKKEN) - set(KNOWN_BUITEN_BEREIK)

        assert not onbekend, (
            f"Nieuwe schrijfplek(ken) op user_roles zonder test onder de applicatierol: "
            f"{sorted(onbekend)}. Voeg ze toe aan SCHRIJFPLEKKEN met een testklasse in dit "
            "bestand, of aan KNOWN_BUITEN_BEREIK met een reden."
        )

    def test_no_listed_site_has_disappeared(self) -> None:
        gevonden = _alle_schrijfplekken_in_src()
        verdwenen = sorted(k for k in {*SCHRIJFPLEKKEN, *KNOWN_BUITEN_BEREIK} if k not in gevonden)

        assert not verdwenen, f"Deze regels staan in de lijst maar bestaan niet meer: {verdwenen}"

    def test_every_listed_site_has_an_existing_test_class(self) -> None:
        module = sys.modules[__name__]
        zonder = sorted(k for k, klasse in SCHRIJFPLEKKEN.items() if not hasattr(module, klasse))

        assert not zonder, (
            f"Deze schrijfplekken wijzen naar een testklasse die niet bestaat: {zonder}"
        )

    def test_the_scanner_ignores_a_plain_local_list(self) -> None:
        """Legitiem lijkend geval: een lokale lijst `roles` is geen koppelingsrelatie."""
        bron = "def f():\n    roles = []\n    roles.append('x')\n    return roles\n"

        assert _zoek_schrijfplekken_in(bron, "x.py") == set()

    def test_the_scanner_sees_each_form_of_write(self) -> None:
        bron = (
            "def a(db):\n    db.execute(user_roles.insert())\n"
            "def b(u):\n    u.roles.extend([])\n"
            "def c(u):\n    u.roles = []\n"
            "class K:\n    def d(self, m):\n        m.user_roles.delete()\n"
        )

        assert _zoek_schrijfplekken_in(bron, "x.py") == {
            "x.py::a",
            "x.py::b",
            "x.py::c",
            "x.py::K.d",
        }
