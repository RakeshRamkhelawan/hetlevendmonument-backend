"""De rechtencontrole voor agent-tools werkt onder de applicatierol (ADR-036 OP-143, OP-155).

`user_has_scope_for` draait zonder verzoek (ook in workers) en opent daarom een EIGEN sessie
zonder tenantcontext. Onder `sanskritisetu_app` (niet-eigenaar, RLS afgedwongen) geeft elke SELECT
dan nul rijen ZONDER foutmelding, en `RBACService.user_has_permission` slikt een fout als `False`.
Gevolg als `adopt_tenant` zou ontbreken: iedereen, ook een beheerder, krijgt `MISSING_SCOPE` met de
verkeerde reden. De tests in `tests/integration/test_tools_lezen_hun_rechten_uit_de_database.py`
lopen als tabeleigenaar (de integratiedatabase) en zien dat niet; deze module wel.

**Hoe.** Verse migratiedatabase, rollen en rechten van de ECHTE zaaier (`ensure_default_roles`,
als eigenaar), gebruikers via `user_roles`. Daarna wordt de sessiefabriek van `db_manager`
vervangen door een engine die als `sanskritisetu_app` draait (asyncpg met
`server_settings role`), en roept de test de echte `rbac_service.user_has_scope_for` aan.

**Wat deze module NIET zegt.** Groen betekent: in deze database, onder de applicatierol, geeft de
controle de juiste antwoorden. De draaiende applicatie verbindt nog als tabeleigenaar (OP-151).

**Mutatiebewijs:** zie de docstring van `test_an_admin_is_allowed_under_the_application_role`.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator, Iterator
from dataclasses import dataclass

import psycopg2
import pytest
import pytest_asyncio
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, connection as PgConnection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from tests.fixtures.testdatabase import testdatabase_poort
from tests.integration.security.test_the_application_role_is_confined_to_its_tenant import (
    _ROL,
    _SCRATCH_DB,
    _bouw_verse_database,
    _dsn,
    _postgres_bereikbaar,
)

from src.core.database.database import db_manager
from src.core.middleware.tenant_context import set_tenant_id
from src.core.services.rbac_service import RBACService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.skipif(
        not _postgres_bereikbaar(),
        reason="vereist PostgreSQL op de netwerkpoort uit SANSKRITISETU_TEST_DATABASE_URL",
    ),
]

LEES_TOOL = "list_tasks"
SCHRIJF_TOOL = "local__write_file"
BEHEER_TOOL = "query_hr_database"


def _url() -> str:
    gebruiker = os.environ.get("POSTGRES_USER", "postgres")
    wachtwoord = os.environ.get("POSTGRES_PASSWORD", "postgres")
    return (
        f"postgresql+asyncpg://{gebruiker}:{wachtwoord}@127.0.0.1:"
        f"{testdatabase_poort()}/{_SCRATCH_DB}"
    )


@dataclass(frozen=True)
class Gebruikers:
    tenant_a: int
    tenant_b: int
    per_rol: dict[str, int]
    beheerder_van_b: int


@pytest.fixture(scope="module")
def db() -> Iterator[PgConnection]:
    _bouw_verse_database()
    conn = psycopg2.connect(_dsn(_SCRATCH_DB))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    yield conn
    conn.close()


@pytest_asyncio.fixture
async def gebruikers(db: PgConnection) -> Gebruikers:
    """Twee klanten, rollen van de echte zaaier, per rol een gebruiker met PRECIES die rol.

    Idempotent per run: de tenants worden alleen aangemaakt als ze nog niet bestaan.
    """
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
            "VALUES ('Rol A', 'tr-a', true, 10, 50, 5), ('Rol B', 'tr-b', true, 10, 50, 5) "
            "ON CONFLICT DO NOTHING"
        )
        cur.execute("SELECT slug, id FROM tenants WHERE slug IN ('tr-a', 'tr-b')")
        tenants = dict(cur.fetchall())

    # De ECHTE producent, als eigenaar (die omzeilt RLS; zo hangt de opstelling niet af van wat
    # hieronder wordt gemeten).
    eigenaar = create_async_engine(_url(), poolclass=NullPool)
    try:
        for slug in ("tr-a", "tr-b"):
            async with AsyncSession(eigenaar) as sessie:
                await RBACService(sessie).ensure_default_roles(tenants[slug])
    finally:
        await eigenaar.dispose()

    with db.cursor() as cur:
        cur.execute("SELECT tenant_id, name, id FROM roles")
        rollen = {(t, n): i for t, n, i in cur.fetchall()}

        def maak(tenant: int, rol: str) -> int:
            cur.execute(
                "INSERT INTO users (tenant_id, email) VALUES (%s, %s) RETURNING id",
                (tenant, f"{rol}-{uuid.uuid4().hex[:8]}@op143.example.com"),
            )
            row = cur.fetchone()
            assert row is not None
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                (row[0], rollen[(tenant, rol)]),
            )
            return int(row[0])

        per_rol = {rol: maak(tenants["tr-a"], rol) for rol in ("admin", "user", "editor")}
        van_b = maak(tenants["tr-b"], "admin")
    return Gebruikers(tenants["tr-a"], tenants["tr-b"], per_rol, van_b)


@pytest_asyncio.fixture
async def als_applicatierol(
    monkeypatch: pytest.MonkeyPatch, gebruikers: Gebruikers
) -> AsyncGenerator[None, None]:
    """`db_manager` geeft sessies die als `sanskritisetu_app` draaien; daarna wordt hersteld."""
    engine = create_async_engine(
        _url(), poolclass=NullPool, connect_args={"server_settings": {"role": _ROL}}
    )
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(
        db_manager,
        "async_session_maker",
        async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False),
    )
    monkeypatch.setattr(db_manager, "_initialized", True)
    # Geen ambient tenant: precies de situatie van een worker, buiten elk verzoek.
    set_tenant_id(None)
    yield
    await engine.dispose()


async def _mag(user_id: int, tenant_id: int, tool: str) -> bool:
    from src.core.auth.rbac import rbac_service

    return await rbac_service.user_has_scope_for(user_id, tool, tenant_id=tenant_id)


@pytest.mark.asyncio
class TestOnderDeApplicatierol:
    async def test_the_session_really_runs_as_the_application_role(
        self, als_applicatierol: None
    ) -> None:
        """Draaide dit als eigenaar, dan bewijst elke test hieronder niets."""
        from sqlalchemy import text

        async with db_manager.get_session() as sessie:
            gebruiker = (await sessie.execute(text("SELECT current_user"))).scalar_one()

        assert gebruiker == _ROL

    async def test_an_admin_is_allowed_under_the_application_role(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        """Zonder `adopt_tenant` ziet de SELECT nul rijen en krijgt ook de beheerder MISSING_SCOPE.

        **Mutatiebewijs (2026-10-09), kopie als terugweg:** `adopt_tenant` uit
        `_gebruiker_heeft_recht` gehaald -> 3 ROOD: deze test, `test_a_user_may_read_but_not_write`
        en `test_an_editor_may_read_under_the_application_role` (alle drie verwachten `True`);
        de weigertests blijven GROEN, want zonder context is ook de weigering "juist" -- daarom
        staan de toestaantests ernaast. Ongewijzigd -> 6 GROEN.
        """
        assert await _mag(gebruikers.per_rol["admin"], gebruikers.tenant_a, BEHEER_TOOL) is True

    async def test_a_user_may_read_but_not_write(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        lees = await _mag(gebruikers.per_rol["user"], gebruikers.tenant_a, LEES_TOOL)
        schrijf = await _mag(gebruikers.per_rol["user"], gebruikers.tenant_a, SCHRIJF_TOOL)

        assert (lees, schrijf) == (True, False)

    async def test_an_editor_may_read_under_the_application_role(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        assert await _mag(gebruikers.per_rol["editor"], gebruikers.tenant_a, LEES_TOOL) is True

    async def test_an_admin_of_another_tenant_is_refused(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        assert await _mag(gebruikers.beheerder_van_b, gebruikers.tenant_a, LEES_TOOL) is False

    async def test_the_context_does_not_leak_after_the_check(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        """`adopt_tenant` zet de ContextVar terug: er blijft geen tenant hangen voor de volgende."""
        from src.core.middleware.tenant_context import get_tenant_id

        await _mag(gebruikers.per_rol["admin"], gebruikers.tenant_a, LEES_TOOL)

        assert get_tenant_id() is None
