"""`receivables` onder Row Level Security: een debiteur is niet over tenants heen te zien of te schrijven.

Dag 1 van de debiteurenagent (brief
`docs/agent-briefs/generated/2026-10-04-sprint-dag-debiteurenagent-dag-1-databron.md`).
De tabel krijgt dezelfde policyvorm als `20260915_rls_resterende_tabellen.py`: RLS aan, een
policy `FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_tenant', true),
'')::INTEGER)`, geen `FORCE`, geen eigen rol.

Hergebruik: de verse database uit de migratieketen, de applicatierol `sanskritisetu_app` en
de helpers `_als_de_applicatierol` en `_herstel` komen uit
`test_the_application_role_is_confined_to_its_tenant.py`. Alleen het zaaien staat hier.

**Beide richtingen.** Rood zolang de tabel of de policy ontbreekt: niet zien, niet schrijven,
niet wijzigen, niet verwijderen, niet omzetten van een rij van de andere tenant. Groen-houders
(zonder deze helft is "weiger alles" een geldige oplossing): de eigen rij blijft zichtbaar,
invoegbaar, wijzigbaar en verwijderbaar.

**Waarom de weigertests voor UPDATE en DELETE GEEN WHERE hebben.** Een UPDATE of DELETE met
een WHERE op kolommen wordt al door de SELECT-kant van de policy gefilterd; die variant blijft
groen bij een kapotte UPDATE- of DELETE-kant. Zonder WHERE bepaalt alleen de policy van het
commando zelf welke rijen geraakt worden. Ze draaien in een teruggedraaide transactie.

**Rood-bewijs en mutaties (2026-10-04, gemeten op de echte migratie, kopie als terugweg):**
- Zonder tabel/migratie: 2 failed, 22 errors (`relation "receivables" does not exist`).
- Policy `USING (true)`: 13 failed -- alle weigertests (zien, zonder context, INSERT,
  UPDATE, DELETE, verplaatsen, beide richtingen) plus `still_sees_its_own` (ziet dan ook B).
- Geen policy (RLS aan, weiger alles): 11 failed -- alle `can_still`/`still_sees`-tests,
  het verplaatsen (geen 42501 maar 0 rijen) en de vormtest.
- Ongewijzigd: 24 passed.

**Wat deze module NIET zegt.** Groen betekent: de applicatierol kan in deze database geen
debiteur van een ander bedrijf zien of schrijven. Of een klant dat in productie merkt, hangt
af van OP-151: de applicatie verbindt nu als eigenaar, en voor de eigenaar slaat PostgreSQL
RLS over. Dat is hier zichtbaar gemaakt in `test_the_seed_is_visible_to_the_owner`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import psycopg2
import pytest
from psycopg2.extensions import (
    ISOLATION_LEVEL_AUTOCOMMIT,
    connection as PgConnection,
    cursor as PgCursor,
)
from tests.integration.security.test_the_application_role_is_confined_to_its_tenant import (
    _SCRATCH_DB,
    _als_de_applicatierol,
    _bouw_verse_database,
    _dsn,
    _herstel,
    _postgres_bereikbaar,
)

# SQLSTATE 42501: ook de code van "new row violates row-level security policy".
_SQLSTATE_INSUFFICIENT_PRIVILEGE = "42501"
# SQLSTATE 23505: unique_violation.
_SQLSTATE_UNIQUE_VIOLATION = "23505"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.skipif(
        not _postgres_bereikbaar(),
        reason="vereist PostgreSQL op de netwerkpoort uit SANSKRITISETU_TEST_DATABASE_URL",
    ),
]

_KOLOMMEN = (
    "tenant_id, customer_name, customer_email, invoice_number, amount, currency, due_date, "
    "status, source, external_id"
)


def _rij(tenant: int, nummer: str, bron: str = "handmatig", extern: str | None = None) -> tuple[object, ...]:
    return (
        tenant,
        f"Klant {nummer}",
        f"{nummer.lower()}@debiteur.test",
        nummer,
        "100.25",
        "EUR",
        "2026-09-01",
        "open",
        bron,
        extern,
    )


_INSERT = f"INSERT INTO receivables ({_KOLOMMEN}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"


@dataclass(frozen=True)
class Zaad:
    tenant_a: int
    tenant_b: int
    rij_a: int
    rij_b: int


def _nieuw_id(cur: PgCursor) -> int:
    rij = cur.fetchone()
    assert rij is not None, "INSERT ... RETURNING id gaf geen rij terug: de opstelling is mislukt"
    return int(rij[0])


@pytest.fixture(scope="module")
def db() -> Iterator[PgConnection]:
    """Verse database uit de MIGRATIEKETEN (niet `create_all`: dat maakt geen policies)."""
    _bouw_verse_database()
    conn = psycopg2.connect(_dsn(_SCRATCH_DB))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def zaad(db: PgConnection) -> Zaad:
    """Twee tenants met elk een debiteur, aangemaakt als eigenaar (omzeilt RLS)."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
            "VALUES ('Deb A', 'deb-a', true, 10, 50, 5), ('Deb B', 'deb-b', true, 10, 50, 5)"
        )
        cur.execute("SELECT slug, id FROM tenants WHERE slug IN ('deb-a', 'deb-b')")
        tenants = dict(cur.fetchall())
        cur.execute(_INSERT + " RETURNING id", _rij(tenants["deb-a"], "A-001"))
        rij_a = _nieuw_id(cur)
        cur.execute(_INSERT + " RETURNING id", _rij(tenants["deb-b"], "B-001"))
        rij_b = _nieuw_id(cur)
    return Zaad(tenants["deb-a"], tenants["deb-b"], rij_a, rij_b)


def _tenant(z: Zaad, kant: str) -> int:
    return z.tenant_a if kant == "a" else z.tenant_b


def _id(z: Zaad, kant: str) -> int:
    return z.rij_a if kant == "a" else z.rij_b


def _als_app(
    conn: PgConnection, tenant: int | None, sql: str, params: tuple[object, ...] = ()
) -> tuple[int, str | None, list[tuple[object, ...]]]:
    """Voer uit als applicatierol; geef (rowcount, melding bij 42501, rijen bij SELECT).

    Alleen 42501 telt als weigering; elke andere fout laat de test als fout falen.
    """
    cur = _als_de_applicatierol(conn, str(tenant) if tenant is not None else None)
    melding: str | None = None
    geraakt = 0
    rijen: list[tuple[object, ...]] = []
    try:
        cur.execute(sql, params)
        geraakt = cur.rowcount
        if cur.description is not None:
            rijen = list(cur.fetchall())
    except psycopg2.Error as fout:
        if fout.pgcode != _SQLSTATE_INSUFFICIENT_PRIVILEGE:
            raise
        melding = str(fout).strip().splitlines()[0]
    finally:
        _herstel(cur)
    return geraakt, melding, rijen


def _in_transactie(
    conn: PgConnection, tenant: int, sql: str, params: tuple[object, ...], meting: str,
    meting_params: tuple[object, ...],
) -> tuple[int, str | None, int]:
    """Statement als applicatierol in een transactie, meten als eigenaar, terugdraaien."""
    cur = conn.cursor()
    melding: str | None = None
    geraakt = 0
    gemeten: int | None = None
    cur.execute("BEGIN")
    try:
        app = _als_de_applicatierol(conn, str(tenant))
        try:
            app.execute(sql, params)
            geraakt = app.rowcount
        except psycopg2.Error as fout:
            if fout.pgcode != _SQLSTATE_INSUFFICIENT_PRIVILEGE:
                raise
            melding = str(fout).strip().splitlines()[0]
        else:
            app.execute("RESET ROLE")
            app.execute("RESET app.current_tenant")
            cur.execute(meting, meting_params)
            rij = cur.fetchone()
            assert rij is not None
            gemeten = int(rij[0])
        finally:
            app.close()
    finally:
        cur.execute("ROLLBACK")
        cur.close()
    if gemeten is None:
        with conn.cursor() as eigenaar:
            eigenaar.execute(meting, meting_params)
            rij = eigenaar.fetchone()
            assert rij is not None
            gemeten = int(rij[0])
    return geraakt, melding, gemeten


def _opruimen(conn: PgConnection, nummer: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM receivables WHERE invoice_number = %s", (nummer,))


_RICHTINGEN = pytest.mark.parametrize(
    ("eigen", "ander"), [("a", "b"), ("b", "a")], ids=["A-op-B", "B-op-A"]
)
_EIGEN = pytest.mark.parametrize("eigen", ["a", "b"], ids=["A", "B"])


class TestTheSetupIsReal:
    def test_the_seed_is_visible_to_the_owner(self, db: PgConnection, zaad: Zaad) -> None:
        """De meting is niet leeg; dit is ook het OP-151-gat: de eigenaar ziet alles."""
        with db.cursor() as cur:
            cur.execute("SELECT count(*) FROM receivables WHERE id IN (%s, %s)", (zaad.rij_a, zaad.rij_b))
            rij = cur.fetchone()

        assert rij is not None and rij[0] == 2, f"De eigenaar ziet {rij} van de 2 gezaaide rijen."


class TestATenantCannotReachTheOther:
    @_RICHTINGEN
    def test_a_tenant_does_not_see_a_receivable_of_the_other(
        self, db: PgConnection, zaad: Zaad, eigen: str, ander: str
    ) -> None:
        _, melding, rijen = _als_app(db, _tenant(zaad, eigen), "SELECT id FROM receivables")
        zichtbaar = {r[0] for r in rijen}

        assert _id(zaad, ander) not in zichtbaar, (
            f"Tenant {eigen} ziet de debiteur van tenant {ander} (zichtbaar: {sorted(zichtbaar)}, "
            f"melding: {melding})."
        )

    def test_without_tenant_context_nothing_is_visible(self, db: PgConnection, zaad: Zaad) -> None:
        _, melding, rijen = _als_app(db, None, "SELECT count(*) FROM receivables")

        assert melding is None and rijen == [(0,)], (
            f"Zonder tenantcontext: {rijen} (melding: {melding}); verwacht 0 rijen."
        )

    @_RICHTINGEN
    def test_an_insert_with_the_tenant_of_the_other_is_refused(
        self, db: PgConnection, zaad: Zaad, eigen: str, ander: str
    ) -> None:
        nummer = f"X-{eigen}{ander}-INS"
        try:
            _, melding, _ = _als_app(db, _tenant(zaad, eigen), _INSERT, _rij(_tenant(zaad, ander), nummer))
        finally:
            _opruimen(db, nummer)

        assert melding is not None and "row-level security" in melding, (
            f"Tenant {eigen} kon een debiteur schrijven onder tenant {ander} (melding: {melding})."
        )

    @_RICHTINGEN
    def test_a_tenant_cannot_update_a_receivable_of_the_other(
        self, db: PgConnection, zaad: Zaad, eigen: str, ander: str
    ) -> None:
        geraakt, melding, ongewijzigd = _in_transactie(
            db, _tenant(zaad, eigen),
            "UPDATE receivables SET status = 'betaald'", (),
            "SELECT count(*) FROM receivables WHERE id = %s AND status = 'open'", (_id(zaad, ander),),
        )

        assert ongewijzigd == 1, (
            f"Tenant {eigen} wijzigde de debiteur van tenant {ander} (geraakt: {geraakt}, "
            f"melding: {melding})."
        )

    @_RICHTINGEN
    def test_a_tenant_cannot_delete_a_receivable_of_the_other(
        self, db: PgConnection, zaad: Zaad, eigen: str, ander: str
    ) -> None:
        geraakt, melding, over = _in_transactie(
            db, _tenant(zaad, eigen),
            "DELETE FROM receivables", (),
            "SELECT count(*) FROM receivables WHERE id = %s", (_id(zaad, ander),),
        )

        assert over == 1, (
            f"Tenant {eigen} verwijderde de debiteur van tenant {ander} (geraakt: {geraakt}, "
            f"melding: {melding})."
        )

    @_RICHTINGEN
    def test_a_tenant_cannot_move_its_own_receivable_to_the_other(
        self, db: PgConnection, zaad: Zaad, eigen: str, ander: str
    ) -> None:
        """WITH CHECK op UPDATE: de nieuwe rij moet ook bij de eigen tenant horen."""
        geraakt, melding, op_plek = _in_transactie(
            db, _tenant(zaad, eigen),
            "UPDATE receivables SET tenant_id = %s WHERE id = %s", (_tenant(zaad, ander), _id(zaad, eigen)),
            "SELECT count(*) FROM receivables WHERE id = %s AND tenant_id = %s",
            (_id(zaad, eigen), _tenant(zaad, eigen)),
        )

        assert melding is not None and "row-level security" in melding and op_plek == 1, (
            f"Tenant {eigen} kon zijn debiteur naar tenant {ander} verplaatsen (geraakt: "
            f"{geraakt}, melding: {melding}, nog op eigen plek: {op_plek})."
        )


class TestATenantKeepsItsOwn:
    """De omgekeerde helft: zonder deze is "weiger alles" een geldige oplossing."""

    @_EIGEN
    def test_a_tenant_still_sees_its_own_receivable(self, db: PgConnection, zaad: Zaad, eigen: str) -> None:
        _, melding, rijen = _als_app(db, _tenant(zaad, eigen), "SELECT id FROM receivables")

        assert {r[0] for r in rijen} == {_id(zaad, eigen)}, (
            f"Tenant {eigen} ziet {rijen} (melding: {melding}); verwacht precies zijn eigen rij."
        )

    @_EIGEN
    def test_a_tenant_can_still_insert_its_own_receivable(
        self, db: PgConnection, zaad: Zaad, eigen: str
    ) -> None:
        nummer = f"X-{eigen}-EIGEN"
        try:
            geraakt, melding, _ = _als_app(db, _tenant(zaad, eigen), _INSERT, _rij(_tenant(zaad, eigen), nummer))
        finally:
            _opruimen(db, nummer)

        assert melding is None and geraakt == 1, f"Eigen INSERT geweigerd: {melding}."

    @_EIGEN
    def test_a_tenant_can_still_update_its_own_receivable(
        self, db: PgConnection, zaad: Zaad, eigen: str
    ) -> None:
        geraakt, melding, gewijzigd = _in_transactie(
            db, _tenant(zaad, eigen),
            "UPDATE receivables SET status = 'herinnerd' WHERE id = %s", (_id(zaad, eigen),),
            "SELECT count(*) FROM receivables WHERE id = %s AND status = 'herinnerd'", (_id(zaad, eigen),),
        )

        assert gewijzigd == 1, f"Eigen UPDATE kwam niet aan (geraakt: {geraakt}, melding: {melding})."

    @_EIGEN
    def test_a_tenant_can_still_delete_its_own_receivable(
        self, db: PgConnection, zaad: Zaad, eigen: str
    ) -> None:
        geraakt, melding, over = _in_transactie(
            db, _tenant(zaad, eigen),
            "DELETE FROM receivables WHERE id = %s", (_id(zaad, eigen),),
            "SELECT count(*) FROM receivables WHERE id = %s", (_id(zaad, eigen),),
        )

        assert over == 0, f"Eigen DELETE kwam niet aan (geraakt: {geraakt}, melding: {melding})."


class TestTheTableShape:
    def test_rls_is_enabled_with_a_policy_and_not_forced(self, db: PgConnection) -> None:
        """RLS aan, minstens een policy, en GEEN FORCE (brief: geen FORCE, interlock 3)."""
        with db.cursor() as cur:
            cur.execute(
                "SELECT c.relrowsecurity, c.relforcerowsecurity, "
                "(SELECT count(*) FROM pg_policies p WHERE p.schemaname = 'public' "
                " AND p.tablename = 'receivables') "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = 'receivables'"
            )
            rij = cur.fetchone()

        assert rij == (True, False, 1), f"(rls aan, force, policies) = {rij}; verwacht (True, False, 1)."

    def test_the_amount_is_a_decimal_column(self, db: PgConnection) -> None:
        """Geld is decimaal, nooit float."""
        with db.cursor() as cur:
            cur.execute(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'receivables' AND column_name = 'amount'"
            )
            rij = cur.fetchone()

        assert rij == ("numeric",), f"`amount` heeft type {rij}; verwacht numeric."

    def test_a_second_import_of_the_same_external_id_is_refused(self, db: PgConnection, zaad: Zaad) -> None:
        """Unieke sleutel (tenant_id, source, external_id): geen dubbele factuur uit een bron."""
        melding: str | None = None
        with db.cursor() as cur:
            cur.execute(_INSERT, _rij(zaad.tenant_a, "IMP-1", "import", "EXT-1"))
            try:
                cur.execute(_INSERT, _rij(zaad.tenant_a, "IMP-2", "import", "EXT-1"))
            except psycopg2.Error as fout:
                if fout.pgcode != _SQLSTATE_UNIQUE_VIOLATION:
                    raise
                melding = fout.pgcode
        _opruimen(db, "IMP-1")
        _opruimen(db, "IMP-2")

        assert melding == _SQLSTATE_UNIQUE_VIOLATION, "Een tweede rij met dezelfde bron + extern_id werd toegelaten."

    def test_the_same_external_id_under_another_tenant_is_allowed(self, db: PgConnection, zaad: Zaad) -> None:
        """De andere kant: de sleutel is per tenant, niet globaal."""
        with db.cursor() as cur:
            cur.execute(_INSERT, _rij(zaad.tenant_a, "IMP-3", "import", "EXT-2"))
            cur.execute(_INSERT, _rij(zaad.tenant_b, "IMP-4", "import", "EXT-2"))
            cur.execute("SELECT count(*) FROM receivables WHERE external_id = 'EXT-2'")
            rij = cur.fetchone()
        _opruimen(db, "IMP-3")
        _opruimen(db, "IMP-4")

        assert rij == (2,), f"Zelfde extern_id bij twee tenants: {rij} rijen; verwacht 2."
