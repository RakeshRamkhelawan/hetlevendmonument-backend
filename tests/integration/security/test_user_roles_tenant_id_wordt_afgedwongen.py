"""De database dwingt af dat een koppeling bij EEN klant hoort (ADR-036 OP-190, deel 2).

Deel 1 liet de koppeltabel `user_roles` onder RLS vallen: een verbinding die onder de policy
valt kan geen koppeling over de klantgrens leggen. Maar de eigenaar omzeilt elke policy (OP-151)
en `user_roles` had geen eigen `tenant_id`; niets in het SCHEMA zei dat gebruiker, rol en
koppeling bij dezelfde klant horen. Deze module bewijst dat het schema dat nu zelf zegt:

- `user_roles.tenant_id` bestaat en is NOT NULL;
- twee samengestelde vreemde sleutels, `(user_id, tenant_id) -> users(id, tenant_id)` en
  `(role_id, tenant_id) -> roles(id, tenant_id)`, weigeren een gekruiste koppeling, ook voor
  de EIGENAAR (rechtstreeks via psycopg2, dus zonder policy);
- een insert zonder `tenant_id` (de rauwe scripts en testopstellingen) krijgt de klant van de
  gebruiker via de vultrigger, en kan daardoor nooit een gekruiste koppeling worden;
- de migratie vult bestaande rijen, faalt luid op een gekruiste of wees-rij zonder iets te
  verwijderen, en haar `downgrade()` draait precies terug wat zij toevoegde.

**Mutatiebewijs (2026-10-09), elke regel een run van dit bestand, kopie als terugweg:**
- sleutel naar `roles` uit de migratie -> 4 ROOD (kruis met klant van de gebruiker, kruis zonder
  `tenant_id`, en twee migratietests);
- sleutel naar `users` weg -> 4 ROOD (kruis met klant van de rol, gebruiker verhuizen, twee
  migratietests);
- vultrigger weg -> 4 ROOD; trigger vult een verkeerde klant (weiger-alles) -> 3 ROOD, ook de
  legitieme koppeling zonder `tenant_id`;
- controle op gekruiste rij weg -> 1 ROOD; migratie VERWIJDERT de gekruiste rij -> 1 ROOD;
- downgrade laat de kolom staan -> 3 ROOD.
Schrijfpadmodule: `assign_role` met een verkeerde klant -> 1 ROOD; Python-default geeft None ->
12 ROOD in `tests/unit/auth/test_user_scope_covers_broker_tools.py` (SQLite).
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg2
import pytest
from psycopg2 import errors
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, connection as PgConnection
from tests.fixtures.testdatabase import testdatabase_poort
from tests.integration.security.test_the_application_role_is_confined_to_its_tenant import (
    _SCRATCH_DB,
    _bouw_verse_database,
    _dsn,
    _postgres_bereikbaar,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_KOP_VOOR_DEZE_MIGRATIE = "20261008_debiteuren_verzenden_en_opvolgen"
_DEZE_MIGRATIE = "20261009_user_roles_tenant_id"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.skipif(
        not _postgres_bereikbaar(),
        reason="vereist PostgreSQL op de netwerkpoort uit SANSKRITISETU_TEST_DATABASE_URL",
    ),
]


def _alembic(*argumenten: str) -> subprocess.CompletedProcess[str]:
    omgeving = dict(os.environ)
    omgeving["DATABASE_URL"] = (
        f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{testdatabase_poort()}/{_SCRATCH_DB}"
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "src/alembic.ini", *argumenten],
        cwd=_REPO_ROOT,
        env=omgeving,
        capture_output=True,
        text=True,
        timeout=900,
    )


def _id(cur: psycopg2.extensions.cursor) -> int:
    rij = cur.fetchone()
    assert rij is not None, "INSERT ... RETURNING id gaf geen rij terug: de opstelling is mislukt"
    return int(rij[0])


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:10]}@op190d2.example.com"


@pytest.fixture(scope="module")
def db() -> Iterator[PgConnection]:
    """Verse database uit de migratieketen, als eigenaar (dus zonder RLS)."""
    _bouw_verse_database()
    conn = psycopg2.connect(_dsn(_SCRATCH_DB))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def wereld(db: PgConnection) -> dict[str, int]:
    """Twee klanten met elk een rol en een gebruiker."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
            "VALUES ('Tid A', 'tid-a', true, 10, 50, 5), ('Tid B', 'tid-b', true, 10, 50, 5)"
        )
        cur.execute("SELECT slug, id FROM tenants WHERE slug IN ('tid-a', 'tid-b')")
        tenants = dict(cur.fetchall())
        uit: dict[str, int] = {"tenant_a": tenants["tid-a"], "tenant_b": tenants["tid-b"]}
        for sleutel, slug in (("a", "tid-a"), ("b", "tid-b")):
            cur.execute(
                "INSERT INTO roles (tenant_id, name) VALUES (%s, %s) RETURNING id",
                (tenants[slug], f"rol-{sleutel}"),
            )
            uit[f"rol_{sleutel}"] = _id(cur)
            cur.execute(
                "INSERT INTO users (tenant_id, email) VALUES (%s, %s) RETURNING id",
                (tenants[slug], _email(f"basis-{sleutel}")),
            )
            uit[f"user_{sleutel}"] = _id(cur)
    return uit


def _nieuwe_gebruiker(db: PgConnection, tenant: int) -> int:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO users (tenant_id, email) VALUES (%s, %s) RETURNING id",
            (tenant, _email("tid")),
        )
        return _id(cur)


def _koppelingen(db: PgConnection, user_id: int) -> list[tuple[int, int]]:
    with db.cursor() as cur:
        cur.execute("SELECT role_id, tenant_id FROM user_roles WHERE user_id = %s", (user_id,))
        return [(int(r[0]), int(r[1])) for r in cur.fetchall()]


class TestHetSchemaDwingtDeKlantgrensAf:
    def test_the_column_exists_and_is_not_null(self, db: PgConnection) -> None:
        with db.cursor() as cur:
            cur.execute(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'user_roles' AND column_name = 'tenant_id'"
            )
            rij = cur.fetchone()

        assert rij is not None and rij[0] == "NO"

    def test_a_crossed_link_with_the_tenant_of_the_user_is_refused(
        self, db: PgConnection, wereld: dict[str, int]
    ) -> None:
        """Gebruiker van A, rol van B, koppeling bij A: de sleutel naar `roles` weigert."""
        gebruiker = _nieuwe_gebruiker(db, wereld["tenant_a"])

        with db.cursor() as cur, pytest.raises(errors.ForeignKeyViolation):
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id, tenant_id) VALUES (%s, %s, %s)",
                (gebruiker, wereld["rol_b"], wereld["tenant_a"]),
            )

        assert _koppelingen(db, gebruiker) == []

    def test_a_crossed_link_with_the_tenant_of_the_role_is_refused(
        self, db: PgConnection, wereld: dict[str, int]
    ) -> None:
        """Dezelfde koppeling bij B: de sleutel naar `users` weigert."""
        gebruiker = _nieuwe_gebruiker(db, wereld["tenant_a"])

        with db.cursor() as cur, pytest.raises(errors.ForeignKeyViolation):
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id, tenant_id) VALUES (%s, %s, %s)",
                (gebruiker, wereld["rol_b"], wereld["tenant_b"]),
            )

        assert _koppelingen(db, gebruiker) == []

    def test_a_crossed_link_without_tenant_id_is_refused(
        self, db: PgConnection, wereld: dict[str, int]
    ) -> None:
        """De rauwe vorm van de scripts: zonder `tenant_id` mag het ook niet gekruist lukken."""
        gebruiker = _nieuwe_gebruiker(db, wereld["tenant_a"])

        with db.cursor() as cur, pytest.raises(errors.ForeignKeyViolation):
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                (gebruiker, wereld["rol_b"]),
            )

        assert _koppelingen(db, gebruiker) == []

    def test_a_link_inside_the_tenant_is_accepted_with_an_explicit_tenant_id(
        self, db: PgConnection, wereld: dict[str, int]
    ) -> None:
        gebruiker = _nieuwe_gebruiker(db, wereld["tenant_a"])

        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id, tenant_id) VALUES (%s, %s, %s)",
                (gebruiker, wereld["rol_a"], wereld["tenant_a"]),
            )

        assert _koppelingen(db, gebruiker) == [(wereld["rol_a"], wereld["tenant_a"])]

    def test_a_link_inside_the_tenant_without_tenant_id_gets_the_tenant_of_the_user(
        self, db: PgConnection, wereld: dict[str, int]
    ) -> None:
        gebruiker = _nieuwe_gebruiker(db, wereld["tenant_b"])

        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                (gebruiker, wereld["rol_b"]),
            )

        assert _koppelingen(db, gebruiker) == [(wereld["rol_b"], wereld["tenant_b"])]

    def test_a_linked_user_cannot_be_moved_to_another_tenant(
        self, db: PgConnection, wereld: dict[str, int]
    ) -> None:
        """Zonder dit zou een gebruiker na de koppeling alsnog van klant kunnen wisselen."""
        gebruiker = _nieuwe_gebruiker(db, wereld["tenant_a"])
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                (gebruiker, wereld["rol_a"]),
            )

        with db.cursor() as cur, pytest.raises(errors.ForeignKeyViolation):
            cur.execute(
                "UPDATE users SET tenant_id = %s WHERE id = %s", (wereld["tenant_b"], gebruiker)
            )

        assert _koppelingen(db, gebruiker) == [(wereld["rol_a"], wereld["tenant_a"])]

    def test_deleting_a_linked_user_removes_the_link_and_is_not_refused(
        self, db: PgConnection, wereld: dict[str, int]
    ) -> None:
        """De samengestelde sleutel is NO ACTION; de CASCADE van de enkelvoudige moet winnen."""
        gebruiker = _nieuwe_gebruiker(db, wereld["tenant_a"])
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                (gebruiker, wereld["rol_a"]),
            )
            cur.execute("DELETE FROM users WHERE id = %s", (gebruiker,))

        assert _koppelingen(db, gebruiker) == []

    def test_deleting_a_linked_role_removes_the_link_and_is_not_refused(
        self, db: PgConnection, wereld: dict[str, int]
    ) -> None:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO roles (tenant_id, name) VALUES (%s, %s) RETURNING id",
                (wereld["tenant_a"], f"tijdelijk-{uuid.uuid4().hex[:8]}"),
            )
            rol = _id(cur)
        gebruiker = _nieuwe_gebruiker(db, wereld["tenant_a"])
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)", (gebruiker, rol)
            )
            cur.execute("DELETE FROM roles WHERE id = %s", (rol,))

        assert _koppelingen(db, gebruiker) == []


class TestDeMigratie:
    """Draait als LAATSTE in deze module: hij zet de database terug naar `head`."""

    def test_the_migration_is_part_of_the_chain_that_leads_to_the_head(self) -> None:
        """De migratie zit IN de keten naar de kop; hij hoeft niet zelf de kop te zijn.

        Tot 2026-10-14 eiste deze test dat `20261009_user_roles_tenant_id` de kop IS. Dat was
        onwaar zodra de volgende migratie (ROI, HR, auditlog) erbovenop kwam, en de test stond
        rood terwijl er niets mis was met de migratie. Wat hij moet bewaken: de migratie is niet
        uit de keten gevallen. De pin dat er precies EEN kop is staat in
        `tests/unit/database/test_agentic_alembic_chain_complete.py`.

        `alembic history -r <migratie>:heads` faalt als de migratie geen voorouder van een kop is.
        """
        uitslag = _alembic("history", "-r", f"{_DEZE_MIGRATIE}:heads")

        assert uitslag.returncode == 0, uitslag.stderr[-2000:]
        assert _DEZE_MIGRATIE in uitslag.stdout, uitslag.stdout

    def test_the_downgrade_removes_exactly_what_the_upgrade_added(
        self, db: PgConnection, wereld: dict[str, int]
    ) -> None:
        gebruiker = _nieuwe_gebruiker(db, wereld["tenant_a"])
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                (gebruiker, wereld["rol_a"]),
            )

        with db.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'user_roles' AND column_name = 'tenant_id'"
            )
            kolom_voor = cur.fetchone()
        assert kolom_voor == (1,), "voorwaarde: de upgrade staat erop, anders bewijst dit niets"

        uitslag = _alembic("downgrade", _KOP_VOOR_DEZE_MIGRATIE)

        assert uitslag.returncode == 0, uitslag.stderr[-2000:]
        with db.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'user_roles' AND column_name = 'tenant_id'"
            )
            kolom = cur.fetchone()
            cur.execute(
                "SELECT count(*) FROM pg_constraint WHERE conname IN "
                "('uq_roles_id_tenant', 'fk_user_roles_user_tenant', 'fk_user_roles_role_tenant')"
            )
            sleutels = cur.fetchone()
            cur.execute(
                "SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_user_roles_vul_tenant_id'"
            )
            trigger = cur.fetchone()
            cur.execute("SELECT count(*) FROM user_roles WHERE user_id = %s", (gebruiker,))
            behouden = cur.fetchone()
        assert (kolom, sleutels, trigger, behouden) == ((0,), (0,), (0,), (1,))

    def test_the_upgrade_backfills_the_tenant_of_an_existing_link(self, db: PgConnection) -> None:
        """Op de staat van voor de migratie staat er een rij zonder kolom; hij krijgt de klant."""
        uitslag = _alembic("upgrade", "head")

        assert uitslag.returncode == 0, uitslag.stderr[-2000:]
        with db.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM user_roles ur JOIN users u ON u.id = ur.user_id "
                "WHERE ur.tenant_id IS DISTINCT FROM u.tenant_id"
            )
            fout = cur.fetchone()
            cur.execute("SELECT count(*) FROM user_roles")
            totaal = cur.fetchone()
        assert fout == (0,)
        assert totaal is not None and totaal[0] > 0

    def test_the_upgrade_fails_loudly_on_a_crossed_row_and_deletes_nothing(
        self, db: PgConnection, wereld: dict[str, int]
    ) -> None:
        assert _alembic("downgrade", _KOP_VOOR_DEZE_MIGRATIE).returncode == 0
        gebruiker = _nieuwe_gebruiker(db, wereld["tenant_a"])
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                (gebruiker, wereld["rol_b"]),
            )
            cur.execute("SELECT count(*) FROM user_roles")
            voor = cur.fetchone()

        try:
            uitslag = _alembic("upgrade", "head")
            with db.cursor() as cur:
                cur.execute("SELECT count(*) FROM user_roles")
                na = cur.fetchone()
        finally:
            with db.cursor() as cur:
                cur.execute("DELETE FROM user_roles WHERE user_id = %s", (gebruiker,))
            herstel = _alembic("upgrade", "head")

        assert uitslag.returncode != 0
        # Tekst die ALLEEN in de eigen melding staat (de SQL-tekst bij een andere fout niet).
        assert "OP-190 deel 2 afgebroken - 1 koppeling(en)" in (uitslag.stderr + uitslag.stdout)
        assert voor == na
        assert herstel.returncode == 0, herstel.stderr[-2000:]
