"""`suppliers` en `payables` onder Row Level Security: een leverancier of inkoopfactuur is niet over tenants heen te zien of te schrijven.

Crediteuren dag 1 (brief `docs/agent-briefs/generated/2026-10-24-sprint-dag-crediteuren-dag1-inkoopfacturen-vastleggen.md`).
Beide tabellen krijgen dezelfde policyvorm als `receivables`: RLS aan, een policy `FOR ALL USING (tenant_id =
NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)`, geen `FORCE`, geen eigen rol.

Hergebruik: de verse database uit de migratieketen, de applicatierol `sanskritisetu_app` en de helpers komen uit
`test_the_application_role_is_confined_to_its_tenant.py`; de opzet is die van `test_receivables_is_confined_to_its_tenant.py`.

**Beide richtingen.** Rood zolang een tabel of een policy ontbreekt: niet zien, niet schrijven, niet wijzigen, niet verwijderen
en niet verplaatsen van een rij van de andere tenant, voor BEIDE tabellen. Groen-houders (zonder deze helft is "weiger alles"
een geldige oplossing): de eigen rij blijft zichtbaar, invoegbaar, wijzigbaar en verwijderbaar.

**Waarom de weigertests voor UPDATE en DELETE GEEN WHERE hebben.** Een UPDATE of DELETE met een WHERE op kolommen wordt al door de
SELECT-kant van de policy gefilterd; die variant blijft groen bij een kapotte UPDATE- of DELETE-kant. Zonder WHERE bepaalt alleen
de policy van het commando zelf welke rijen geraakt worden. Ze draaien in een teruggedraaide transactie.

**Naast RLS: de samengestelde sleutel.** `payables (tenant_id, supplier_id)` verwijst naar `suppliers (tenant_id, id)`. Ook als
iemand RLS omzeilt (de applicatie verbindt nu als eigenaar, OP-151), kan een factuur van tenant A dus niet naar een leverancier van
tenant B wijzen; `TestTheTableShape` meet dat als eigenaar.

**Wat deze module NIET zegt.** Groen betekent: de applicatierol kan in deze database geen leverancier of factuur van een ander
bedrijf zien of schrijven. Of een klant dat in productie merkt, hangt af van OP-151.
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
_SQLSTATE_UNIQUE_VIOLATION = "23505"
_SQLSTATE_FOREIGN_KEY_VIOLATION = "23503"
_SQLSTATE_CHECK_VIOLATION = "23514"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.skipif(
        not _postgres_bereikbaar(),
        reason="vereist PostgreSQL op de netwerkpoort uit SANSKRITISETU_TEST_DATABASE_URL",
    ),
]

_TABELLEN = ("suppliers", "payables")

_INSERT_LEVERANCIER = "INSERT INTO suppliers (tenant_id, name, iban, email) VALUES (%s, %s, %s, %s)"
_INSERT_FACTUUR = (
    "INSERT INTO payables (tenant_id, supplier_id, invoice_number, amount_cents, currency, invoice_date, due_date, status) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
)


def _leverancier(tenant: int, naam: str) -> tuple[object, ...]:
    return (tenant, naam, None, f"{naam.lower().replace(' ', '')}@leverancier.test")


def _factuur(tenant: int, leverancier: int, nummer: str) -> tuple[object, ...]:
    return (tenant, leverancier, nummer, 125050, "EUR", "2026-10-01", "2026-10-31", "ontvangen")


@dataclass(frozen=True)
class Zaad:
    tenant_a: int
    tenant_b: int
    leverancier_a: int
    leverancier_b: int
    factuur_a: int
    factuur_b: int


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
    """Twee tenants met elk een leverancier en een inkoopfactuur, aangemaakt als eigenaar (omzeilt RLS)."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
            "VALUES ('Crd A', 'crd-a', true, 10, 50, 5), ('Crd B', 'crd-b', true, 10, 50, 5)"
        )
        cur.execute("SELECT slug, id FROM tenants WHERE slug IN ('crd-a', 'crd-b')")
        tenants = dict(cur.fetchall())
        cur.execute(
            _INSERT_LEVERANCIER + " RETURNING id", _leverancier(tenants["crd-a"], "Leverancier A")
        )
        lev_a = _nieuw_id(cur)
        cur.execute(
            _INSERT_LEVERANCIER + " RETURNING id", _leverancier(tenants["crd-b"], "Leverancier B")
        )
        lev_b = _nieuw_id(cur)
        cur.execute(_INSERT_FACTUUR + " RETURNING id", _factuur(tenants["crd-a"], lev_a, "A-001"))
        fac_a = _nieuw_id(cur)
        cur.execute(_INSERT_FACTUUR + " RETURNING id", _factuur(tenants["crd-b"], lev_b, "B-001"))
        fac_b = _nieuw_id(cur)
    return Zaad(tenants["crd-a"], tenants["crd-b"], lev_a, lev_b, fac_a, fac_b)


def _tenant(z: Zaad, kant: str) -> int:
    return z.tenant_a if kant == "a" else z.tenant_b


def _rij_id(z: Zaad, tabel: str, kant: str) -> int:
    if tabel == "suppliers":
        return z.leverancier_a if kant == "a" else z.leverancier_b
    return z.factuur_a if kant == "a" else z.factuur_b


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
    conn: PgConnection,
    tenant: int,
    sql: str,
    params: tuple[object, ...],
    meting: str,
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


def _opruimen(conn: PgConnection, tabel: str, kolom: str, waarde: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {tabel} WHERE {kolom} = %s", (waarde,))


_RICHTINGEN = pytest.mark.parametrize(
    ("eigen", "ander"), [("a", "b"), ("b", "a")], ids=["A-op-B", "B-op-A"]
)
_EIGEN = pytest.mark.parametrize("eigen", ["a", "b"], ids=["A", "B"])
_TABEL = pytest.mark.parametrize("tabel", _TABELLEN)


class TestTheSetupIsReal:
    @_TABEL
    def test_the_seed_is_visible_to_the_owner(
        self, db: PgConnection, zaad: Zaad, tabel: str
    ) -> None:
        """De meting is niet leeg; dit is ook het OP-151-gat: de eigenaar ziet alles."""
        with db.cursor() as cur:
            cur.execute(
                f"SELECT count(*) FROM {tabel} WHERE id IN (%s, %s)",
                (_rij_id(zaad, tabel, "a"), _rij_id(zaad, tabel, "b")),
            )
            rij = cur.fetchone()

        assert rij is not None and rij[0] == 2, (
            f"De eigenaar ziet {rij} van de 2 gezaaide rijen in {tabel}."
        )


class TestATenantCannotReachTheOther:
    @_TABEL
    @_RICHTINGEN
    def test_a_tenant_does_not_see_a_row_of_the_other(
        self, db: PgConnection, zaad: Zaad, tabel: str, eigen: str, ander: str
    ) -> None:
        _, melding, rijen = _als_app(db, _tenant(zaad, eigen), f"SELECT id FROM {tabel}")
        zichtbaar = {r[0] for r in rijen}

        assert _rij_id(zaad, tabel, ander) not in zichtbaar, (
            f"Tenant {eigen} ziet een rij van tenant {ander} in {tabel} (zichtbaar: {sorted(zichtbaar)}, melding: {melding})."
        )

    @_TABEL
    def test_without_tenant_context_nothing_is_visible(
        self, db: PgConnection, zaad: Zaad, tabel: str
    ) -> None:
        _, melding, rijen = _als_app(db, None, f"SELECT count(*) FROM {tabel}")

        assert melding is None and rijen == [(0,)], (
            f"Zonder tenantcontext in {tabel}: {rijen} (melding: {melding}); verwacht 0 rijen."
        )

    @_RICHTINGEN
    def test_a_supplier_insert_with_the_tenant_of_the_other_is_refused(
        self, db: PgConnection, zaad: Zaad, eigen: str, ander: str
    ) -> None:
        naam = f"X-{eigen}{ander}-LEV"
        try:
            _, melding, _ = _als_app(
                db,
                _tenant(zaad, eigen),
                _INSERT_LEVERANCIER,
                _leverancier(_tenant(zaad, ander), naam),
            )
        finally:
            _opruimen(db, "suppliers", "name", naam)

        assert melding is not None and "row-level security" in melding, (
            f"Tenant {eigen} kon een leverancier schrijven onder tenant {ander} (melding: {melding})."
        )

    @_RICHTINGEN
    def test_a_payable_insert_with_the_tenant_of_the_other_is_refused(
        self, db: PgConnection, zaad: Zaad, eigen: str, ander: str
    ) -> None:
        nummer = f"X-{eigen}{ander}-INS"
        leverancier_ander = zaad.leverancier_a if ander == "a" else zaad.leverancier_b
        try:
            _, melding, _ = _als_app(
                db,
                _tenant(zaad, eigen),
                _INSERT_FACTUUR,
                _factuur(_tenant(zaad, ander), leverancier_ander, nummer),
            )
        finally:
            _opruimen(db, "payables", "invoice_number", nummer)

        assert melding is not None and "row-level security" in melding, (
            f"Tenant {eigen} kon een factuur schrijven onder tenant {ander} (melding: {melding})."
        )

    @_TABEL
    @_RICHTINGEN
    def test_a_tenant_cannot_update_a_row_of_the_other(
        self, db: PgConnection, zaad: Zaad, tabel: str, eigen: str, ander: str
    ) -> None:
        kolom, waarde = ("name", "Gekraakt") if tabel == "suppliers" else ("status", "betaald")
        geraakt, melding, ongewijzigd = _in_transactie(
            db,
            _tenant(zaad, eigen),
            f"UPDATE {tabel} SET {kolom} = %s",
            (waarde,),
            f"SELECT count(*) FROM {tabel} WHERE id = %s AND {kolom} <> %s",
            (_rij_id(zaad, tabel, ander), waarde),
        )

        assert ongewijzigd == 1, (
            f"Tenant {eigen} wijzigde een rij van tenant {ander} in {tabel} (geraakt: {geraakt}, melding: {melding})."
        )

    @_RICHTINGEN
    def test_a_tenant_cannot_delete_a_payable_of_the_other(
        self, db: PgConnection, zaad: Zaad, eigen: str, ander: str
    ) -> None:
        geraakt, melding, over = _in_transactie(
            db,
            _tenant(zaad, eigen),
            "DELETE FROM payables",
            (),
            "SELECT count(*) FROM payables WHERE id = %s",
            (_rij_id(zaad, "payables", ander),),
        )

        assert over == 1, (
            f"Tenant {eigen} verwijderde een factuur van tenant {ander} (geraakt: {geraakt}, melding: {melding})."
        )

    @_RICHTINGEN
    def test_a_tenant_cannot_delete_a_supplier_of_the_other(
        self, db: PgConnection, zaad: Zaad, eigen: str, ander: str
    ) -> None:
        """Zonder WHERE. De eigen facturen gaan in DEZELFDE opdracht mee weg (CTE), anders stuit het DELETE op de sleutel van
        de eigen leverancier en zegt de test niets over de afscherming; de rijen van de ander zijn dan het enige dat telt."""
        geraakt, melding, over = _in_transactie(
            db,
            _tenant(zaad, eigen),
            "WITH weg AS (DELETE FROM payables RETURNING 1) DELETE FROM suppliers",
            (),
            "SELECT count(*) FROM suppliers WHERE id = %s",
            (_rij_id(zaad, "suppliers", ander),),
        )

        assert over == 1, (
            f"Tenant {eigen} verwijderde een leverancier van tenant {ander} (geraakt: {geraakt}, melding: {melding})."
        )

    @_TABEL
    @_RICHTINGEN
    def test_a_tenant_cannot_move_its_own_row_to_the_other(
        self, db: PgConnection, zaad: Zaad, tabel: str, eigen: str, ander: str
    ) -> None:
        """WITH CHECK op UPDATE: de nieuwe rij moet ook bij de eigen tenant horen."""
        geraakt, melding, op_plek = _in_transactie(
            db,
            _tenant(zaad, eigen),
            f"UPDATE {tabel} SET tenant_id = %s WHERE id = %s",
            (_tenant(zaad, ander), _rij_id(zaad, tabel, eigen)),
            f"SELECT count(*) FROM {tabel} WHERE id = %s AND tenant_id = %s",
            (_rij_id(zaad, tabel, eigen), _tenant(zaad, eigen)),
        )

        assert melding is not None and "row-level security" in melding and op_plek == 1, (
            f"Tenant {eigen} kon zijn rij in {tabel} naar tenant {ander} verplaatsen (geraakt: {geraakt}, "
            f"melding: {melding}, nog op eigen plek: {op_plek})."
        )


class TestATenantKeepsItsOwn:
    """De omgekeerde helft: zonder deze is "weiger alles" een geldige oplossing."""

    @_TABEL
    @_EIGEN
    def test_a_tenant_still_sees_its_own_row(
        self, db: PgConnection, zaad: Zaad, tabel: str, eigen: str
    ) -> None:
        _, melding, rijen = _als_app(db, _tenant(zaad, eigen), f"SELECT id FROM {tabel}")

        assert {r[0] for r in rijen} == {_rij_id(zaad, tabel, eigen)}, (
            f"Tenant {eigen} ziet {rijen} in {tabel} (melding: {melding}); verwacht precies zijn eigen rij."
        )

    @_EIGEN
    def test_a_tenant_can_still_insert_its_own_supplier_and_payable(
        self, db: PgConnection, zaad: Zaad, eigen: str
    ) -> None:
        naam = f"X-{eigen}-EIGEN"
        leverancier = zaad.leverancier_a if eigen == "a" else zaad.leverancier_b
        try:
            geraakt_l, melding_l, _ = _als_app(
                db,
                _tenant(zaad, eigen),
                _INSERT_LEVERANCIER,
                _leverancier(_tenant(zaad, eigen), naam),
            )
            geraakt_f, melding_f, _ = _als_app(
                db,
                _tenant(zaad, eigen),
                _INSERT_FACTUUR,
                _factuur(_tenant(zaad, eigen), leverancier, naam),
            )
        finally:
            _opruimen(db, "payables", "invoice_number", naam)
            _opruimen(db, "suppliers", "name", naam)

        assert (melding_l, geraakt_l, melding_f, geraakt_f) == (None, 1, None, 1), (
            f"Eigen INSERT geweigerd (leverancier: {melding_l}, factuur: {melding_f})."
        )

    @_TABEL
    @_EIGEN
    def test_a_tenant_can_still_update_its_own_row(
        self, db: PgConnection, zaad: Zaad, tabel: str, eigen: str
    ) -> None:
        kolom, waarde = (
            ("name", "Nieuwe naam") if tabel == "suppliers" else ("status", "gecontroleerd")
        )
        geraakt, melding, gewijzigd = _in_transactie(
            db,
            _tenant(zaad, eigen),
            f"UPDATE {tabel} SET {kolom} = %s WHERE id = %s",
            (waarde, _rij_id(zaad, tabel, eigen)),
            f"SELECT count(*) FROM {tabel} WHERE id = %s AND {kolom} = %s",
            (_rij_id(zaad, tabel, eigen), waarde),
        )

        assert gewijzigd == 1, (
            f"Eigen UPDATE kwam niet aan in {tabel} (geraakt: {geraakt}, melding: {melding})."
        )

    @_EIGEN
    def test_a_tenant_can_still_delete_its_own_payable(
        self, db: PgConnection, zaad: Zaad, eigen: str
    ) -> None:
        geraakt, melding, over = _in_transactie(
            db,
            _tenant(zaad, eigen),
            "DELETE FROM payables WHERE id = %s",
            (_rij_id(zaad, "payables", eigen),),
            "SELECT count(*) FROM payables WHERE id = %s",
            (_rij_id(zaad, "payables", eigen),),
        )

        assert over == 0, f"Eigen DELETE kwam niet aan (geraakt: {geraakt}, melding: {melding})."


class TestTheTableShape:
    @_TABEL
    def test_rls_is_enabled_with_a_policy_and_not_forced(
        self, db: PgConnection, tabel: str
    ) -> None:
        """RLS aan, minstens een policy, en GEEN FORCE (interlock 3)."""
        with db.cursor() as cur:
            cur.execute(
                "SELECT c.relrowsecurity, c.relforcerowsecurity, "
                "(SELECT count(*) FROM pg_policies p WHERE p.schemaname = 'public' AND p.tablename = %s) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = %s",
                (tabel, tabel),
            )
            rij = cur.fetchone()

        assert rij == (True, False, 1), (
            f"{tabel}: (rls aan, force, policies) = {rij}; verwacht (True, False, 1)."
        )

    def test_the_amount_is_a_whole_number_of_cents(self, db: PgConnection) -> None:
        """Geld is een geheel aantal centen, nooit float of tekst."""
        with db.cursor() as cur:
            cur.execute(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'payables' AND column_name = 'amount_cents'"
            )
            rij = cur.fetchone()

        assert rij == ("bigint",), f"`amount_cents` heeft type {rij}; verwacht bigint."

    def test_a_payable_cannot_point_to_a_supplier_of_another_tenant(
        self, db: PgConnection, zaad: Zaad
    ) -> None:
        """De samengestelde sleutel: ook als eigenaar (zonder RLS) is een kruisverwijzing onmogelijk."""
        code: str | None = None
        with db.cursor() as cur:
            try:
                cur.execute(_INSERT_FACTUUR, _factuur(zaad.tenant_a, zaad.leverancier_b, "KRUIS-1"))
            except psycopg2.Error as fout:
                if fout.pgcode != _SQLSTATE_FOREIGN_KEY_VIOLATION:
                    raise
                code = fout.pgcode
        _opruimen(db, "payables", "invoice_number", "KRUIS-1")

        assert code == _SQLSTATE_FOREIGN_KEY_VIOLATION, (
            "Een factuur van tenant A kon naar een leverancier van tenant B wijzen."
        )

    def test_the_same_invoice_of_the_same_supplier_twice_is_refused(
        self, db: PgConnection, zaad: Zaad
    ) -> None:
        """Unieke sleutel (tenant_id, supplier_id, invoice_number): geen dubbele factuur."""
        code: str | None = None
        with db.cursor() as cur:
            cur.execute(_INSERT_FACTUUR, _factuur(zaad.tenant_a, zaad.leverancier_a, "DUBBEL-1"))
            try:
                cur.execute(
                    _INSERT_FACTUUR, _factuur(zaad.tenant_a, zaad.leverancier_a, "DUBBEL-1")
                )
            except psycopg2.Error as fout:
                if fout.pgcode != _SQLSTATE_UNIQUE_VIOLATION:
                    raise
                code = fout.pgcode
        _opruimen(db, "payables", "invoice_number", "DUBBEL-1")

        assert code == _SQLSTATE_UNIQUE_VIOLATION, (
            "Dezelfde factuur van dezelfde leverancier werd twee keer toegelaten."
        )

    def test_a_supplier_name_in_another_case_is_refused(self, db: PgConnection, zaad: Zaad) -> None:
        """De unieke sleutel op de naam is hoofdletterongevoelig (Gate 2: "Acme BV" en "ACME BV" zijn een leverancier)."""
        code: str | None = None
        with db.cursor() as cur:
            try:
                cur.execute(_INSERT_LEVERANCIER, _leverancier(zaad.tenant_a, "LEVERANCIER A"))
            except psycopg2.Error as fout:
                if fout.pgcode != _SQLSTATE_UNIQUE_VIOLATION:
                    raise
                code = fout.pgcode
        _opruimen(db, "suppliers", "name", "LEVERANCIER A")

        assert code == _SQLSTATE_UNIQUE_VIOLATION, "Een leverancier in andere hoofdletters werd toegelaten naast de bestaande."

    def test_an_invoice_number_in_another_case_is_refused(self, db: PgConnection, zaad: Zaad) -> None:
        code: str | None = None
        with db.cursor() as cur:
            try:
                cur.execute(_INSERT_FACTUUR, _factuur(zaad.tenant_a, zaad.leverancier_a, "a-001"))
            except psycopg2.Error as fout:
                if fout.pgcode != _SQLSTATE_UNIQUE_VIOLATION:
                    raise
                code = fout.pgcode
        _opruimen(db, "payables", "invoice_number", "a-001")

        assert code == _SQLSTATE_UNIQUE_VIOLATION, "Een factuurnummer in andere hoofdletters werd toegelaten naast het bestaande."

    def test_the_same_invoice_number_under_another_tenant_is_allowed(
        self, db: PgConnection, zaad: Zaad
    ) -> None:
        """De andere kant: de sleutel is per tenant (en leverancier), niet globaal."""
        with db.cursor() as cur:
            cur.execute(_INSERT_FACTUUR, _factuur(zaad.tenant_a, zaad.leverancier_a, "ZELFDE-1"))
            cur.execute(_INSERT_FACTUUR, _factuur(zaad.tenant_b, zaad.leverancier_b, "ZELFDE-1"))
            cur.execute("SELECT count(*) FROM payables WHERE invoice_number = 'ZELFDE-1'")
            rij = cur.fetchone()
        _opruimen(db, "payables", "invoice_number", "ZELFDE-1")

        assert rij == (2,), f"Hetzelfde factuurnummer bij twee tenants: {rij} rijen; verwacht 2."

    @pytest.mark.parametrize(
        ("kolom", "waarde"),
        [("status", "'verzonnen'"), ("amount_cents", "-5"), ("currency", "'eur'")],
        ids=["status", "bedrag", "valuta"],
    )
    def test_the_database_refuses_nonsense_values(
        self, db: PgConnection, zaad: Zaad, kolom: str, waarde: str
    ) -> None:
        """Het vangnet onder de repository: een CHECK op status, bedrag en valuta."""
        basis = {"status": "'ontvangen'", "amount_cents": "100", "currency": "'EUR'"}
        basis[kolom] = waarde
        code: str | None = None
        with db.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO payables (tenant_id, supplier_id, invoice_number, amount_cents, currency, invoice_date, "
                    "due_date, status) VALUES "
                    f"({zaad.tenant_a}, {zaad.leverancier_a}, 'CHK-{kolom}', {basis['amount_cents']}, {basis['currency']}, "
                    f"'2026-10-01', '2026-10-31', {basis['status']})"
                )
            except psycopg2.Error as fout:
                if fout.pgcode != _SQLSTATE_CHECK_VIOLATION:
                    raise
                code = fout.pgcode
        _opruimen(db, "payables", "invoice_number", f"CHK-{kolom}")

        assert code == _SQLSTATE_CHECK_VIOLATION, f"De database liet {kolom}={waarde} toe."
