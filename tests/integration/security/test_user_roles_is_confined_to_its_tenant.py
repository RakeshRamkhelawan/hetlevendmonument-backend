"""`user_roles` onder Row Level Security: een koppeling is niet over tenants heen te zien of te leggen (OP-190).

`user_roles` is een kale koppeltabel zonder `tenant_id`. `users` en `roles` hebben wel een
policy, maar de koppeltabel zelf had er geen: een RECHTSTREEKSE lees- of schrijfactie op
`user_roles` had nul databasebescherming. Onder de applicatierol (niet-eigenaar, RLS
afgedwongen) is dat precies wat deze module meet, met ECHTE rijen: per tenant een gebruiker en
een rol in `users` en `roles`, en een koppeling daartussen.

Hergebruik: het bouwen van de verse database uit de migratieketen, de applicatierol
`sanskritisetu_app` en de helpers `_als_de_applicatierol` en `_herstel` komen uit
`test_the_application_role_is_confined_to_its_tenant.py`. Er is geen eigen rol of eigen policy
verzonnen -- dat onderscheid is de reden dat die module bestaat. Alleen het zaaien van de
twee tenants staat hier apart; zie de docstring van de `db`-fixture voor de reden.

**Welke tests ROOD horen te staan zolang de policy ontbreekt, en welke bewust GROEN zijn:**

ROOD (de policy op `user_roles` bestaat nog niet):
- `test_tenant_a_sees_no_user_roles_row_of_tenant_b`
- `test_without_tenant_context_user_roles_shows_nothing`
- `test_a_cross_tenant_link_is_refused` (drie combinaties)
- `test_user_roles_has_an_enabled_policy_in_the_migrated_database`

GROEN, en dat is de bedoeling (de omgekeerde helft; zonder deze twee is "weiger alles" een
geldige oplossing):
- `test_tenant_a_still_sees_its_own_link`
- `test_tenant_a_can_still_write_its_own_link`
- `test_the_seed_is_visible_to_the_owner` (de meting is niet leeg)

**Het gat in `test_every_table_with_a_tenant_column_has_a_policy`.** Die test zoekt tabellen op
de KOLOM `tenant_id` en ziet `user_roles` daarom per constructie niet. Hij is niet aangepast.
`test_user_roles_has_an_enabled_policy_in_the_migrated_database` vult het gat aan met een
toets op de TABELNAAM, in de echte database (relrowsecurity en pg_policies), en is dus een
tweede, onafhankelijke meting van hetzelfde ding.

**Wat deze module NIET zegt.** Groen betekent: de applicatierol is in deze database niet in
staat een koppeling over tenants te zien of te leggen. Of een klant dat in productie merkt,
hangt af van OP-151 (de applicatie verbindt nu als eigenaar en omzeilt elke policy).

**Commit en bewijs van roodheid.** Deze tests gaan SAMEN met de migratie in een commit; er
bestaat dus geen aparte rode commit (besluit regie: de pre-commit-hook draait de geraakte
Python-tests en stopt bij rood). Het bewijs van roodheid is, gemeten 2026-10-04 (twee runs):
een boom van 2de4ed8c ZONDER de migratie 20261004_user_roles_rls.py, plus alleen dit
bestand en tests/architecture/test_user_roles_has_row_level_security_in_an_active_migration.py,
geeft "18 failed, 49 passed". Een eerdere versie van deze alinea noemde "8 rood, 43 groen"
op 29c546fb; dat getal is vervangen omdat het niet meer met de huidige testbestanden klopt.

**Tweede ronde (reviewbevindingen).** `TestTheOtherCommandsAreConfinedToo` hieronder vult de
gaten die de review vond: UPDATE, DELETE, het omzetten van een eigen koppeling naar de andere
tenant (WITH CHECK op UPDATE), de spiegel (tenant B tegenover A) en een join. Elke test van
die klasse draait voor beide richtingen (A op B en B op A). De join-test is NIET rood te
krijgen door het ontbreken van een policy op `user_roles`: `users` en `roles` zijn zelf al
beveiligd. Hij vangt alleen een policy die te veel weigert.

**Mutatiebewijs:** zie de docstring van de migratie-guard
`tests/architecture/test_user_roles_has_row_level_security_in_an_active_migration.py` voor de
mutaties aan de migratie-kant. Gedragsmutaties voor deze module staan hieronder, per element;
ze zijn uitgevoerd in de scratch-database via SQL (de migratie zelf is niet aangeraakt):
- Policy met een `WITH CHECK (true)` naast een correcte USING -> de drie INSERT-combinaties
  worden toegelaten: ROOD.
- Policy die alleen `roles` toetst (de gebruiker niet) -> combinatie (gebruiker van B, rol van
  A) wordt toegelaten: ROOD.
- Policy die alleen `users` toetst (de rol niet) -> combinatie (gebruiker van A, rol van B)
  wordt toegelaten: ROOD.
- Policy die alles weigert -> `test_tenant_a_still_sees_its_own_link` en
  `test_tenant_a_can_still_write_its_own_link` ROOD.

Tweede ronde, gemeten door de policy in de scratch-database te vervangen (elke regel is een
run van dit bestand, de rest bleef groen):
- Alleen FOR SELECT -> ROOD: `test_tenant_a_can_still_write_its_own_link`, de vier
  `repoint`-varianten, de twee `can_still_update` en de twee `can_still_delete`.
- Alleen FOR INSERT -> ROOD: `test_tenant_a_still_sees_its_own_link`, de vier `repoint`,
  `can_still_update`, `can_still_delete` en de join-test (allemaal beide richtingen).
- Alleen UPDATE zonder policy -> ROOD: de vier `repoint` en de twee `can_still_update`.
- Alleen DELETE zonder policy -> ROOD: de twee `can_still_delete`.
- DELETE-policy `USING (true)` -> ROOD: `cannot_delete_a_link_of_the_other_tenant` (twee).
- UPDATE-policy `USING (true) WITH CHECK (true)` -> ROOD: `cannot_update_a_link_of_the_other_tenant`
  (twee) en de vier `repoint`.
- UPDATE-policy met alleen `WITH CHECK (true)` (rest goed) -> ROOD: de vier `repoint`.
- Policy die alleen de gebruiker toetst -> ROOD: `gebruiker-A-met-rol-B` en `rol-omzetten` (twee).
- Policy die alleen de rol toetst -> ROOD: `gebruiker-B-met-rol-van-A` en `gebruiker-omzetten`
  (twee).
- Policy `USING (true)` -> ROOD: alle lees-, verwijder-, wijzig-, omzet- en INSERT-weigertests.
- Policy `USING (false)` -> ROOD: alle "still"-tests, de `repoint` en de join-test.
Let op: een UPDATE of DELETE MET een WHERE op kolommen wordt al door de SELECT-policy
gefilterd; die variant zou bij een kapotte UPDATE- of DELETE-policy groen blijven. Daarom
gebruiken de tests voor weigering een statement ZONDER WHERE in een teruggedraaide transactie
(`_in_transactie_als_applicatierol`).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
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

pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.skipif(
        not _postgres_bereikbaar(),
        reason="vereist PostgreSQL op de netwerkpoort uit SANSKRITISETU_TEST_DATABASE_URL",
    ),
]


@pytest.fixture(scope="module")
def db() -> Iterator[PgConnection]:
    """Verse database uit de migratieketen, met twee tenants `rol-a` en `rol-b`.

    Dezelfde bouw als de `db`-fixture in `test_the_application_role_is_confined_to_its_tenant.py`
    (die `_bouw_verse_database` hier hergebruikt wordt), maar met een EIGEN tenantinsert:
    de kolommen `max_users`, `max_agents` en `max_storage_gb` zijn NOT NULL zonder default in
    de gemigreerde database (gemeten op kop 20260920_tenant_llm), en de insert in de bestaande
    fixture noemt ze niet. Die fixture faalt daardoor op dit commit al bij de opstelling,
    vooraf aan elke policy -- een bestaand defect buiten OP-190, niet aangepast.
    """
    _bouw_verse_database()
    conn = psycopg2.connect(_dsn(_SCRATCH_DB))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
            "VALUES ('Rol A', 'rol-a', true, 10, 50, 5), ('Rol B', 'rol-b', true, 10, 50, 5)"
        )
    yield conn
    conn.close()


@dataclass(frozen=True)
class Koppelingen:
    """De echte rijen waar de tests mee werken, per tenant."""

    tenant_a: int
    tenant_b: int
    gebruiker_a: int
    gebruiker_b: int
    rol_a: int
    rol_a_extra: int
    rol_b: int
    rol_b_extra: int


def _nieuw_id(cur: PgCursor) -> int:
    """Het id uit `INSERT ... RETURNING id`; een lege uitkomst is een opstellingsfout."""
    rij = cur.fetchone()
    assert rij is not None, "INSERT ... RETURNING id gaf geen rij terug: de opstelling is mislukt"
    return int(rij[0])


@pytest.fixture(scope="module")
def koppelingen(db: PgConnection) -> Iterator[Koppelingen]:
    """Per tenant een echte gebruiker en rol, plus een eigen koppeling per tenant.

    Aangemaakt als eigenaar (die omzeilt RLS), zodat de opstelling niet afhangt van de
    policy die wordt getoetst. `rol_a_extra` en `rol_b_extra` zijn tweede rollen die de schrijftests
    gebruiken, zodat die de gezaaide koppelingen niet raken (een dubbele sleutel zou een
    opstellingsfout zijn, geen weigering door een policy).
    """
    with db.cursor() as cur:
        cur.execute("SELECT slug, id FROM tenants WHERE slug IN ('rol-a', 'rol-b')")
        tenants = dict(cur.fetchall())
        ids: dict[str, int] = {}
        for sleutel, slug in (("a", "rol-a"), ("b", "rol-b")):
            cur.execute(
                "INSERT INTO users (tenant_id, email) VALUES (%s, %s) RETURNING id",
                (tenants[slug], f"koppeling-{sleutel}@op190.test"),
            )
            ids[f"gebruiker_{sleutel}"] = _nieuw_id(cur)
            cur.execute(
                "INSERT INTO roles (tenant_id, name) VALUES (%s, %s) RETURNING id",
                (tenants[slug], f"rol-{sleutel}"),
            )
            ids[f"rol_{sleutel}"] = _nieuw_id(cur)
        cur.execute(
            "INSERT INTO roles (tenant_id, name) VALUES (%s, 'rol-a-extra') RETURNING id",
            (tenants["rol-a"],),
        )
        ids["rol_a_extra"] = _nieuw_id(cur)
        cur.execute(
            "INSERT INTO roles (tenant_id, name) VALUES (%s, 'rol-b-extra') RETURNING id",
            (tenants["rol-b"],),
        )
        ids["rol_b_extra"] = _nieuw_id(cur)
        for sleutel in ("a", "b"):
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                (ids[f"gebruiker_{sleutel}"], ids[f"rol_{sleutel}"]),
            )
    yield Koppelingen(
        tenant_a=tenants["rol-a"],
        tenant_b=tenants["rol-b"],
        gebruiker_a=ids["gebruiker_a"],
        gebruiker_b=ids["gebruiker_b"],
        rol_a=ids["rol_a"],
        rol_a_extra=ids["rol_a_extra"],
        rol_b=ids["rol_b"],
        rol_b_extra=ids["rol_b_extra"],
    )


def _koppel_als_applicatierol(
    conn: PgConnection, tenant: int, gebruiker: int, rol: int
) -> str | None:
    """Probeer een koppeling te leggen als de applicatierol; geef de foutmelding of None.

    Een geweigerde INSERT heeft SQLSTATE 42501 `insufficient_privilege`
    (de melding "new row violates row-level security policy"). Elke ANDERE fout wordt niet opgevangen: een foutieve
    opstelling hoort als fout te falen en niet als "geweigerd" te tellen.
    Is de INSERT geslaagd, dan ruimt deze helper de rij op als eigenaar, zodat een rode
    uitkomst de volgende test niet besmet.
    """
    cur = _als_de_applicatierol(conn, str(tenant))
    melding: str | None = None
    try:
        cur.execute(
            "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
            (gebruiker, rol),
        )
    except psycopg2.Error as fout:
        if fout.pgcode != _SQLSTATE_INSUFFICIENT_PRIVILEGE:
            raise
        melding = str(fout).strip().splitlines()[0]
    finally:
        _herstel(cur)
    if melding is None:
        with conn.cursor() as opruim:
            opruim.execute(
                "DELETE FROM user_roles WHERE user_id = %s AND role_id = %s",
                (gebruiker, rol),
            )
    return melding


class TestTheSeedIsReal:
    def test_the_seed_is_visible_to_the_owner(
        self, db: PgConnection, koppelingen: Koppelingen
    ) -> None:
        """De meting is niet leeg: de eigenaar ziet beide koppelingen.

        Zonder deze test kan "tenant A ziet niets van B" ook waar zijn omdat er niets staat.
        """
        with db.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM user_roles WHERE user_id IN (%s, %s)",
                (koppelingen.gebruiker_a, koppelingen.gebruiker_b),
            )
            rij = cur.fetchone()

        assert rij is not None and rij[0] == 2, (
            f"De eigenaar ziet {rij} van de 2 gezaaide koppelingen. De opstelling klopt niet, "
            "dus de isolatietests hieronder zeggen niets."
        )


class TestTheControlGroupIsUnderRls:
    def test_the_application_role_is_confined_on_roles_in_this_module(
        self, db: PgConnection, koppelingen: Koppelingen
    ) -> None:
        """Controlemeting: in DEZE opstelling valt de applicatierol wel onder RLS op `roles`.

        `roles` heeft sinds 20260915 een policy. Ziet tenant A hier de rol van B niet, dan is
        de rol echt niet-eigenaar en werkt de tenantcontext; het rood hieronder komt dan
        door de ontbrekende policy op `user_roles` en niet door de opstelling.
        """
        cur = _als_de_applicatierol(db, str(koppelingen.tenant_a))
        try:
            cur.execute("SELECT count(*) FROM roles WHERE id = %s", (koppelingen.rol_b,))
            rij = cur.fetchone()
        finally:
            _herstel(cur)

        assert rij is not None and rij[0] == 0, (
            f"Tenant {koppelingen.tenant_a} ziet de rol van tenant {koppelingen.tenant_b} "
            f"op `roles` (gevonden: {rij}). De applicatierol valt in deze opstelling niet "
            "onder RLS; de uitkomsten hieronder zijn dan niet te vertrouwen."
        )


class TestTenantAIsConfinedToItsOwnLinks:
    def test_tenant_a_sees_no_user_roles_row_of_tenant_b(
        self, db: PgConnection, koppelingen: Koppelingen
    ) -> None:
        """Een SELECT zonder WHERE onder tenant A toont de koppeling van B niet."""
        cur = _als_de_applicatierol(db, str(koppelingen.tenant_a))
        try:
            cur.execute("SELECT user_id FROM user_roles")
            zichtbaar = {rij[0] for rij in cur.fetchall()}
        finally:
            _herstel(cur)

        assert koppelingen.gebruiker_b not in zichtbaar, (
            f"Tenant {koppelingen.tenant_a} ziet de koppeling van gebruiker "
            f"{koppelingen.gebruiker_b} van tenant {koppelingen.tenant_b} "
            f"(zichtbare gebruikers: {sorted(zichtbaar)}). `user_roles` heeft geen policy: "
            "een rechtstreekse query erop is voor elke tenant open."
        )

    def test_without_tenant_context_user_roles_shows_nothing(
        self, db: PgConnection, koppelingen: Koppelingen
    ) -> None:
        """Geen tenantcontext betekent nul koppelingen, niet alle koppelingen."""
        cur = _als_de_applicatierol(db, None)
        try:
            cur.execute(
                "SELECT count(*) FROM user_roles WHERE user_id IN (%s, %s)",
                (koppelingen.gebruiker_a, koppelingen.gebruiker_b),
            )
            rij = cur.fetchone()
        finally:
            _herstel(cur)

        assert rij is not None and rij[0] == 0, (
            f"Zonder tenantcontext ziet de applicatierol {rij[0] if rij else rij} van de 2 "
            "koppelingen in `user_roles`. Een sessie die de tenant vergeet te zetten hoort "
            "niets te zien."
        )

    @pytest.mark.parametrize(
        ("gebruiker", "rol"),
        [
            ("gebruiker_a", "rol_b"),
            ("gebruiker_b", "rol_a_extra"),
            ("gebruiker_b", "rol_b_extra"),
        ],
        ids=["gebruiker-A-met-rol-B", "gebruiker-B-met-rol-van-A", "gebruiker-B-met-rol-B"],
    )
    def test_a_cross_tenant_link_is_refused(
        self, db: PgConnection, koppelingen: Koppelingen, gebruiker: str, rol: str
    ) -> None:
        """Tenant A kan geen koppeling leggen waar een kant van een andere tenant is.

        Drie combinaties, want de policy moet BEIDE kanten toetsen (de Devil's Advocate uit
        de brief): een policy die alleen `roles` toetst laat (gebruiker van B, rol van A)
        door, en een die alleen `users` toetst laat (gebruiker van A, rol van B) door. De
        derde (beide van B) is de kale cross-tenant schrijfactie.
        """
        melding = _koppel_als_applicatierol(
            db,
            koppelingen.tenant_a,
            getattr(koppelingen, gebruiker),
            getattr(koppelingen, rol),
        )

        assert melding is not None and "row-level security" in melding, (
            f"De INSERT van ({gebruiker}, {rol}) onder tenant {koppelingen.tenant_a} is "
            f"TOEGELATEN of om een andere reden geweigerd (melding: {melding}). Verwacht: "
            "'new row violates row-level security policy'. Een kale `permission denied` "
            "telt niet: dat is een ontbrekend recht en geen policy."
        )


class TestTenantAKeepsItsOwnLinks:
    """De omgekeerde helft: zonder deze twee is "weiger alles" een geldige oplossing."""

    def test_tenant_a_still_sees_its_own_link(
        self, db: PgConnection, koppelingen: Koppelingen
    ) -> None:
        cur = _als_de_applicatierol(db, str(koppelingen.tenant_a))
        try:
            cur.execute(
                "SELECT count(*) FROM user_roles WHERE user_id = %s AND role_id = %s",
                (koppelingen.gebruiker_a, koppelingen.rol_a),
            )
            rij = cur.fetchone()
        finally:
            _herstel(cur)

        assert rij is not None and rij[0] == 1, (
            f"Tenant {koppelingen.tenant_a} ziet zijn EIGEN koppeling niet (gevonden: {rij}). "
            "De policy sluit te veel af."
        )

    def test_tenant_a_can_still_write_its_own_link(
        self, db: PgConnection, koppelingen: Koppelingen
    ) -> None:
        melding = _koppel_als_applicatierol(
            db, koppelingen.tenant_a, koppelingen.gebruiker_a, koppelingen.rol_a_extra
        )

        assert melding is None, (
            f"Tenant {koppelingen.tenant_a} mag zijn EIGEN koppeling niet leggen: {melding}. "
            "De policy weigert te veel."
        )


class TestTheMigratedDatabaseCoversUserRoles:
    def test_user_roles_has_an_enabled_policy_in_the_migrated_database(
        self, db: PgConnection
    ) -> None:
        """Toets op de TABELNAAM, in de echte database; vult het gat in de dekkingstest aan.

        `test_every_table_with_a_tenant_column_has_a_policy` zoekt op de kolom `tenant_id`
        en ziet `user_roles` daarom nooit. Hier: staat RLS aan op `user_roles` EN bestaat er
        een policy voor.
        """
        with db.cursor() as cur:
            cur.execute(
                "SELECT c.relrowsecurity, "
                "(SELECT count(*) FROM pg_policies p "
                " WHERE p.schemaname = 'public' AND p.tablename = 'user_roles') "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = 'user_roles'"
            )
            rij = cur.fetchone()

        assert rij is not None, "de tabel user_roles bestaat niet in de gemigreerde database"
        rls_aan, aantal_policies = rij
        assert rls_aan and aantal_policies >= 1, (
            f"`user_roles`: RLS aan={rls_aan}, aantal policies={aantal_policies}. "
            "Beide moeten gelden, anders is de tabel onder de applicatierol open."
        )


# ---------------------------------------------------------------------------------------
# Tweede ronde: UPDATE, DELETE, omzetten, spiegel en join.
# ---------------------------------------------------------------------------------------

_DATUM_VOOR = "2001-01-01 00:00:00"
_DATUM_NA = "2002-02-02 00:00:00"

# (handelende kant, andere kant): de spiegeltest is dezelfde test met de kanten omgedraaid.
_RICHTINGEN = pytest.mark.parametrize(
    ("eigen", "ander"), [("a", "b"), ("b", "a")], ids=["A-op-B", "B-op-A"]
)
# Voor tests die alleen de eigen kant nodig hebben; zelfde ids, dus dezelfde testnamen.
_EIGEN_KANT = pytest.mark.parametrize("eigen", ["a", "b"], ids=["A-op-B", "B-op-A"])


def _veld(k: Koppelingen, naam: str, kant: str) -> int:
    return int(getattr(k, f"{naam}_{kant}"))


def _uitvoeren_als_applicatierol(
    conn: PgConnection, tenant: int, sql: str, params: tuple[object, ...]
) -> tuple[int, str | None]:
    """Voer een statement uit als applicatierol; geef (geraakte rijen, melding bij 42501).

    Alleen SQLSTATE 42501 telt als weigering door een policy; elke andere fout wordt niet
    opgevangen en laat de test als fout falen.
    """
    cur = _als_de_applicatierol(conn, str(tenant))
    melding: str | None = None
    geraakt = 0
    try:
        cur.execute(sql, params)
        geraakt = cur.rowcount
    except psycopg2.Error as fout:
        if fout.pgcode != _SQLSTATE_INSUFFICIENT_PRIVILEGE:
            raise
        melding = str(fout).strip().splitlines()[0]
    finally:
        _herstel(cur)
    return geraakt, melding


def _eigenaar_telt(conn: PgConnection, sql: str, params: tuple[object, ...]) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rij = cur.fetchone()
    assert rij is not None
    return int(rij[0])


@contextmanager
def _eigen_koppeling(conn: PgConnection, k: Koppelingen, kant: str) -> Iterator[tuple[int, int]]:
    """Een aparte koppeling (gebruiker, extra rol) voor een tenant, met een bekende datum.

    Aangemaakt als eigenaar (omzeilt RLS) en achteraf opgeruimd als eigenaar, ook als een
    mutatie de rij verplaatst of verwijdert, zodat een rode test de volgende niet besmet.
    """
    gebruiker = _veld(k, "gebruiker", kant)
    rol = _veld(k, "rol", kant)
    extra = _extra_rol(k, kant)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO user_roles (user_id, role_id, created_at) VALUES (%s, %s, %s)",
            (gebruiker, extra, _DATUM_VOOR),
        )
    try:
        yield gebruiker, extra
    finally:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM user_roles WHERE role_id IN (%s, %s) "
                "OR (user_id = %s AND role_id <> %s)",
                (k.rol_a_extra, k.rol_b_extra, gebruiker, rol),
            )


def _extra_rol(k: Koppelingen, kant: str) -> int:
    return k.rol_a_extra if kant == "a" else k.rol_b_extra


def _in_transactie_als_applicatierol(
    conn: PgConnection,
    tenant: int,
    sql: str,
    params: tuple[object, ...],
    meting_sql: str,
    meting_params: tuple[object, ...],
    voorbereiding: tuple[tuple[str, tuple[object, ...]], ...] = (),
) -> tuple[int, str | None, int]:
    """Voer een statement ZONDER dekkende WHERE uit als applicatierol, meet als eigenaar, rol terug.

    Waarom in een transactie die wordt teruggedraaid: een UPDATE of DELETE met een WHERE op
    kolommen heeft SELECT-rechten nodig en wordt dan al door een SELECT-policy gefilterd.
    Een test met WHERE zou dus groen blijven bij een kapotte UPDATE- of DELETE-policy zolang
    de SELECT-policy goed is. Zonder WHERE bepaalt alleen de policy van het commando zelf
    welke rijen geraakt worden. De transactie voorkomt dat de opstelling blijvend wordt
    aangetast; de meting gebeurt binnen de transactie als eigenaar.

    Geeft (geraakte rijen, melding bij 42501, meting). Bij een weigering (42501) is de
    transactie afgebroken; de meting is dan de ongewijzigde toestand na de rollback.
    """
    cur = conn.cursor()
    melding: str | None = None
    geraakt = 0
    meting: int | None = None
    cur.execute("BEGIN")
    try:
        for voor_sql, voor_params in voorbereiding:
            cur.execute(voor_sql, voor_params)
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
            cur.execute(meting_sql, meting_params)
            rij = cur.fetchone()
            assert rij is not None
            meting = int(rij[0])
        finally:
            app.close()
    finally:
        cur.execute("ROLLBACK")
        cur.close()
    if meting is None:
        meting = _eigenaar_telt(conn, meting_sql, meting_params)
    return geraakt, melding, meting


class TestTheOtherCommandsAreConfinedToo:
    """UPDATE, DELETE, omzetten, spiegel en join; een policy die alleen SELECT of alleen
    INSERT dekt blijft hier niet groen."""

    @_RICHTINGEN
    def test_a_tenant_cannot_see_a_link_of_the_other_tenant(
        self, db: PgConnection, koppelingen: Koppelingen, eigen: str, ander: str
    ) -> None:
        cur = _als_de_applicatierol(db, str(_veld(koppelingen, "tenant", eigen)))
        try:
            cur.execute("SELECT user_id FROM user_roles")
            zichtbaar = {rij[0] for rij in cur.fetchall()}
        finally:
            _herstel(cur)

        assert _veld(koppelingen, "gebruiker", ander) not in zichtbaar, (
            f"Tenant {eigen} ziet de koppeling van tenant {ander} "
            f"(zichtbare gebruikers: {sorted(zichtbaar)})."
        )

    @_RICHTINGEN
    def test_a_tenant_cannot_delete_a_link_of_the_other_tenant(
        self, db: PgConnection, koppelingen: Koppelingen, eigen: str, ander: str
    ) -> None:
        with _eigen_koppeling(db, koppelingen, ander) as (gebruiker, rol):
            geraakt, melding, over = _in_transactie_als_applicatierol(
                db,
                _veld(koppelingen, "tenant", eigen),
                "DELETE FROM user_roles",
                (),
                "SELECT count(*) FROM user_roles WHERE user_id = %s AND role_id = %s",
                (gebruiker, rol),
            )

        assert over == 1, (
            f"Tenant {eigen} heeft de koppeling van tenant {ander} verwijderd "
            f"(geraakte rijen: {geraakt}, melding: {melding}); de eigenaar ziet nog {over} rij(en)."
        )

    @_RICHTINGEN
    def test_a_tenant_cannot_update_a_link_of_the_other_tenant(
        self, db: PgConnection, koppelingen: Koppelingen, eigen: str, ander: str
    ) -> None:
        with _eigen_koppeling(db, koppelingen, ander) as (gebruiker, rol):
            geraakt, melding, ongewijzigd = _in_transactie_als_applicatierol(
                db,
                _veld(koppelingen, "tenant", eigen),
                "UPDATE user_roles SET created_at = %s",
                (_DATUM_NA,),
                "SELECT count(*) FROM user_roles "
                "WHERE user_id = %s AND role_id = %s AND created_at = %s",
                (gebruiker, rol, _DATUM_VOOR),
            )

        assert ongewijzigd == 1, (
            f"Tenant {eigen} heeft de koppeling van tenant {ander} gewijzigd "
            f"(geraakte rijen: {geraakt}, melding: {melding}); de datum is niet meer de oorspronkelijke."
        )

    @_RICHTINGEN
    @pytest.mark.parametrize("wat", ["rol", "gebruiker"], ids=["rol-omzetten", "gebruiker-omzetten"])
    def test_a_tenant_cannot_repoint_its_own_link_to_the_other_tenant(
        self, db: PgConnection, koppelingen: Koppelingen, eigen: str, ander: str, wat: str
    ) -> None:
        """WITH CHECK op UPDATE: de nieuwe rij moet ook bij de eigen tenant horen.

        De enige koppeling van de eigen tenant is hier de aparte; de gezaaide wordt in de
        (teruggedraaide) transactie eerst door de eigenaar weggehaald, zodat de UPDATE zonder
        WHERE precies een rij raakt en geen dubbele sleutel kan opleveren.
        """
        kolom = "role_id" if wat == "rol" else "user_id"
        doel = (
            _extra_rol(koppelingen, ander)
            if wat == "rol"
            else _veld(koppelingen, "gebruiker", ander)
        )
        with _eigen_koppeling(db, koppelingen, eigen) as (gebruiker, rol):
            geraakt, melding, op_oude_plek = _in_transactie_als_applicatierol(
                db,
                _veld(koppelingen, "tenant", eigen),
                f"UPDATE user_roles SET {kolom} = %s",
                (doel,),
                "SELECT count(*) FROM user_roles WHERE user_id = %s AND role_id = %s",
                (gebruiker, rol),
                voorbereiding=(
                    (
                        "DELETE FROM user_roles WHERE user_id = %s AND role_id = %s",
                        (gebruiker, _veld(koppelingen, "rol", eigen)),
                    ),
                ),
            )

        assert melding is not None and "row-level security" in melding and op_oude_plek == 1, (
            f"Tenant {eigen} kon zijn eigen koppeling omzetten naar tenant {ander} "
            f"({wat}; geraakte rijen: {geraakt}, melding: {melding}, rij op oude plek: "
            f"{op_oude_plek}). Verwacht: 'new row violates row-level security policy' "
            "en de rij ongewijzigd."
        )

    @_EIGEN_KANT
    def test_a_tenant_can_still_update_its_own_link(
        self, db: PgConnection, koppelingen: Koppelingen, eigen: str
    ) -> None:
        with _eigen_koppeling(db, koppelingen, eigen) as (gebruiker, rol):
            geraakt, melding = _uitvoeren_als_applicatierol(
                db,
                _veld(koppelingen, "tenant", eigen),
                "UPDATE user_roles SET created_at = %s WHERE user_id = %s AND role_id = %s",
                (_DATUM_NA, gebruiker, rol),
            )
            gewijzigd = _eigenaar_telt(
                db,
                "SELECT count(*) FROM user_roles "
                "WHERE user_id = %s AND role_id = %s AND created_at = %s",
                (gebruiker, rol, _DATUM_NA),
            )

        assert gewijzigd == 1, (
            f"Tenant {eigen} mag zijn EIGEN koppeling niet wijzigen "
            f"(geraakte rijen: {geraakt}, melding: {melding}). De policy weigert te veel."
        )

    @_EIGEN_KANT
    def test_a_tenant_can_still_delete_its_own_link(
        self, db: PgConnection, koppelingen: Koppelingen, eigen: str
    ) -> None:
        with _eigen_koppeling(db, koppelingen, eigen) as (gebruiker, rol):
            geraakt, melding = _uitvoeren_als_applicatierol(
                db,
                _veld(koppelingen, "tenant", eigen),
                "DELETE FROM user_roles WHERE user_id = %s AND role_id = %s",
                (gebruiker, rol),
            )

        assert geraakt == 1, (
            f"Tenant {eigen} mag zijn EIGEN koppeling niet verwijderen "
            f"(geraakte rijen: {geraakt}, melding: {melding}). De policy weigert te veel."
        )

    @_EIGEN_KANT
    def test_a_join_of_users_user_roles_and_roles_returns_only_own_rows(
        self, db: PgConnection, koppelingen: Koppelingen, eigen: str
    ) -> None:
        """Alle drie de kanten van de join zijn van de eigen tenant, en de join is niet leeg."""
        tenant = _veld(koppelingen, "tenant", eigen)
        cur = _als_de_applicatierol(db, str(tenant))
        try:
            cur.execute(
                "SELECT DISTINCT u.tenant_id, r.tenant_id FROM users u "
                "JOIN user_roles ur ON ur.user_id = u.id "
                "JOIN roles r ON r.id = ur.role_id"
            )
            tenants = {(rij[0], rij[1]) for rij in cur.fetchall()}
        finally:
            _herstel(cur)

        assert tenants == {(tenant, tenant)}, (
            f"De join onder tenant {eigen} geeft (tenant gebruiker, tenant rol) = "
            f"{sorted(tenants)}; verwacht precies [({tenant}, {tenant})]."
        )
