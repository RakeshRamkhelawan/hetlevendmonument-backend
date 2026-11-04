"""Row Level Security beschermt pas als de applicatie NIET de tabeleigenaar is (OP-151).

PostgreSQL slaat RLS over voor de eigenaar van een tabel en voor een superuser, en
`FORCE ROW LEVEL SECURITY` helpt niet tegen een superuser. De applicatie verbindt vandaag
als `postgres` -- de eigenaar. De 138 policies in de keten zijn daarmee decoratie: de
tenantscheiding rust volledig op `src/core/database/tenant_query_filter.py`, en een
ontbrekende WHERE in een enkele query lekt de gegevens van andere klanten.

Gemeten op 2026-08-16 op een verse database uit `alembic upgrade head`, tabel `agents`
met een rij voor tenant 1 en een voor tenant 2:

    als eigenaar postgres                  2 van 2 rijen
    als niet-eigenaar, tenant 1 gezet      1 van 2 rijen
    als niet-eigenaar, lege tenantcontext  0 van 2 rijen

Deze tests draaien tegen de ECHTE rol die de migratie aanmaakt en de ECHTE rechten die
zij uitdeelt -- niet tegen een rol die de test zelf verzint. Dat onderscheid is de reden
dat ze bestaan: `tests/integration/security/test_foundation_rls.py` maakt zijn eigen
`rls_tester` met zijn eigen policies en bewijst daarmee dat de policyVORM werkt, niet dat
de uitgerolde database beschermt.

De rol heeft bewust NOLOGIN en geen wachtwoord. Daarmee kan CI hem meebouwen zonder dat
er een geheim in de repository staat, en verandert er niets aan een draaiende omgeving
tot iemand bewust `ALTER ROLE ... LOGIN PASSWORD` draait
(`docs/runbooks/applicatie-databaserol.md`). `SET ROLE` werkt ook op een NOLOGIN-rol, dus
het bewijs hieronder is volledig.

**Mutatiebewijs (2026-08-16), per bewaakt element en in beide richtingen:**
- `GRANT SELECT, INSERT, UPDATE, DELETE` uit de migratie gehaald ->
  `test_the_application_role_can_read_every_table` ROOD met de tabelnamen erbij.
- `GRANT USAGE ON SCHEMA public` gehaald -> alle isolatietests ROOD (permission denied).
- De policy op `agents` verwijderd -> `test_the_application_role_sees_only_its_own_tenant`
  ROOD (2 van 2 zichtbaar).
- De rol `SUPERUSER` gegeven -> diezelfde test ROOD; dat is precies de fout die OP-151
  beschrijft, nu betrapt.
- `GRANT CREATE ON SCHEMA public` toegevoegd ->
  `test_the_application_role_cannot_change_the_schema` ROOD. Zonder die helft zou
  "geef de rol alle rechten" een geldige oplossing zijn.
- De normalisatiemigratie uit de keten gehaald ->
  `test_no_policy_raises_when_the_tenant_context_is_missing` ROOD met de veertien tabellen
  die op een lege tenantcontext stuklopen, en
  `test_every_normalised_policy_still_exists_and_is_safe` ROOD per element.
- Alles ongewijzigd -> GROEN, en `test_the_measurement_is_not_vacuous` bewijst dat er
  daadwerkelijk policies en tabellen gemeten worden.
"""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import psycopg2
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, connection as PgConnection
from tests.fixtures.testdatabase import testdatabase_poort

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ROL = "sanskritisetu_app"

# Per xdist-worker een eigen database: de fixture dropt en bouwt hem, dus met een vaste
# naam kappen vier workers elkaars verbinding af midden in de keten.
_SCRATCH_DB = f"app_rol_check_{os.environ.get('PYTEST_XDIST_WORKER', 'main')}"

# De veertien policies die op een lege tenantcontext stukliepen, expliciet benoemd met hun
# policynaam. Een guard over een BENOEMDE verzameling is in vijf seconden te controleren,
# en het mutatiebewijs heeft daarmee een regel per element (aanscherping 2026-08-14).
# `company_templates` staat er bewust bij: die tabel heeft GEEN `tenant_id`-kolom -- de
# kolom heet `contributed_by_tenant_id` -- en zou daarom door de dekkingstest hieronder
# nooit worden gezien (Gate 2-review 2026-08-16, BLOCKER 2).
GENORMALISEERDE_POLICIES: dict[str, str] = {
    "board_decisions": "board_decisions_tenant_isolation",
    "companies": "companies_tenant_isolation",
    "company_templates": "company_templates_tenant_isolation",
    "council_decisions": "tenant_isolation_council",
    "departments": "departments_tenant_isolation",
    "document_versions": "tenant_isolation_policy",
    "documents": "tenant_isolation_policy",
    "external_agents": "external_agents_tenant_isolation",
    "goals": "goals_tenant_isolation",
    "officer_verdicts": "tenant_isolation_officer_verdicts",
    "pack_activation_audit_logs": "pack_activation_audit_tenant_isolation",
    # Deze drie hadden WEL `missing_ok` maar GEEN `NULLIF`: ze overleven een ONTBREKENDE
    # instelling maar niet een LEGE, en leeg is precies wat `SET LOCAL` achterlaat na een
    # commit. De eerste meting telde ze als veilig omdat die op de tekst `, true)` zocht.
    "agent_configs": "tenant_isolation",
    "ai_act_incident_reports": "tenant_isolation",
    "model_provenance_records": "tenant_isolation",
}

# Tabellen met een tenant_id-kolom die GEEN policy hebben. Bijgewerkt 2026-09-15: er zijn
# er nog TWEE, en allebei BLIJVEND. De 29 andere zijn die dag opgelost (ADR-036 OP-155).
#
# De code-aanpassingen die een eerdere Gate 2-review als voorwaarde noemde zijn daarbij
# eerst gedaan, in die volgorde: regels aanzetten voor de code klopt maakt van een
# onzichtbare rij stil een verkeerd antwoord. Twee van de drie genoemde plekken bleken al
# gerepareerd door eerdere sessies; de derde (een lege rechtenlijst in achtergrondtaken,
# `rbac.py::_permissions_for_user`) is op 2026-09-15 gerepareerd, en daarbij is een vierde
# plek gevonden die het register niet noemde: `app_lifespan.py` seedde standaardrollen in
# een lus over alle tenants ZONDER tenantcontext -- dat zou bij de eerste start na de
# omschakeling zijn omgevallen, want de USING-expressie geldt ook als WITH CHECK.
# `audit_logs` stond hier als BLIJVEND; sinds migratie `20261024_audit_leesregel` heeft hij een leesregel per
# klant en een open schrijfregel (ADR-036 OP-246), en is de uitzondering verwijderd. Het applicatiefilter in
# `src/core/database/tenant_query_filter.py` (de audit_logs-tak) is bewust ongemoeid gelaten.
KNOWN_ZONDER_POLICY: dict[str, str] = {
    "alembic_version": (
        "BLIJVEND: migratieboekhouding, heeft geen tenantkolom en hoort er geen te hebben."
    ),
    # De 29 andere regels stonden hier tot 2026-09-15 met de reden "OP-155". Ze zijn die
    # dag opgelost door `20260915_rls_resterende_tabellen.py`. Gemeten op een verse database
    # uit de volledige keten, als NIET-eigenaar:
    #
    #     roles             zonder klantcontext 0 / met eigen klant 1 / andere klant 0
    #     learning_patterns zonder klantcontext 0 / met eigen klant 1 / andere klant 0
    #
    # En op de schrijfkant, die verder gaat dan lezen:
    #
    #     INSERT zonder klantcontext          -> new row violates row-level security policy
    #     INSERT met de klant van een ANDER   -> new row violates row-level security policy
    #     INSERT met de eigen klant           -> INSERT 0 1
    #
    # `learning_patterns` staat er als tweede meting bij omdat die een tenantkolom van het
    # type VARCHAR heeft; die drie tabellen kregen bewust de policyvorm zonder `::INTEGER`.
}

# Tabellen waarop de applicatierol bewust NIET mag schrijven. Gedateerd 2026-08-16.
KNOWN_ALLEEN_LEZEN: dict[str, str] = {
    "alembic_version": (
        "de migratieboekhouding is geen applicatiegegeven. Een rol die deze tabel kan "
        "herschrijven kan liegen over de schematoestand, waarna een volgende deploy "
        "migraties overslaat of opnieuw draait. De applicatie leest hem alleen "
        "(health-endpoint)."
    ),
}


def _postgres_bereikbaar() -> bool:
    poort = testdatabase_poort()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        return s.connect_ex(("127.0.0.1", poort)) == 0


pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.skipif(
        not _postgres_bereikbaar(),
        reason="vereist PostgreSQL op POSTGRES_PORT (standaard 5455)",
    ),
]


def _dsn(database: str) -> str:
    poort = str(testdatabase_poort())
    wachtwoord = os.environ.get("POSTGRES_PASSWORD", "postgres")
    gebruiker = os.environ.get("POSTGRES_USER", "postgres")
    return f"host=127.0.0.1 port={poort} user={gebruiker} password={wachtwoord} dbname={database}"


def _bouw_verse_database() -> None:
    beheer = psycopg2.connect(_dsn("postgres"))
    beheer.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with beheer.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (_SCRATCH_DB,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{_SCRATCH_DB}"')
            cur.execute(f'CREATE DATABASE "{_SCRATCH_DB}"')
    finally:
        beheer.close()

    poort = str(testdatabase_poort())
    omgeving = dict(os.environ)
    omgeving["DATABASE_URL"] = (
        f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{poort}/{_SCRATCH_DB}"
    )
    resultaat = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "src/alembic.ini", "upgrade", "head"],
        cwd=_REPO_ROOT,
        env=omgeving,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert resultaat.returncode == 0, (
        f"`alembic upgrade head` faalde (rc={resultaat.returncode}). Zonder deze controle "
        "zou elke test hieronder een leeg schema meten en stil groen worden.\n"
        f"--- stderr ---\n{resultaat.stderr[-4000:]}"
    )


@pytest.fixture(scope="module")
def db() -> Iterator[PgConnection]:
    """Verse database uit de MIGRATIEKETEN, plus twee agents in verschillende tenants.

    Niet `Base.metadata.create_all`: dat maakt geen policies aan, en dan zou deze hele
    module bewijzen dat een tabel zonder RLS geen RLS afdwingt.
    """
    _bouw_verse_database()
    conn = psycopg2.connect(_dsn(_SCRATCH_DB))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
            "VALUES ('Rol A', 'rol-a', true, 10, 50, 5), ('Rol B', 'rol-b', true, 10, 50, 5)"
        )
        cur.execute(
            "INSERT INTO agents (tenant_id, name, agent_type) SELECT id, 'agent-' || slug, "
            "'test' FROM tenants WHERE slug IN ('rol-a', 'rol-b')"
        )
    yield conn
    conn.close()


def _als_de_applicatierol(conn: PgConnection, tenant: str | None) -> psycopg2.extensions.cursor:
    cur = conn.cursor()
    cur.execute(f"SET ROLE {_ROL}")
    cur.execute(f"SET app.current_tenant = '{tenant if tenant is not None else ''}'")
    return cur


def _herstel(cur: psycopg2.extensions.cursor) -> None:
    """Rol EN tenantcontext terugzetten.

    `RESET ROLE` zet `app.current_tenant` niet terug. De verbinding is module-scoped, dus
    zonder deze regel houdt de volgende test de tenant van de vorige vast -- een stille
    afhankelijkheid van testvolgorde (Gate 2-review 2026-08-16, M3).
    """
    cur.execute("RESET ROLE")
    cur.execute("RESET app.current_tenant")
    cur.close()


class TestTheRoleExistsAndIsNotPrivileged:
    def test_the_application_role_exists(self, db: PgConnection) -> None:
        """De migratie maakt de rol aan; zonder rol is er niets om naar over te schakelen."""
        with db.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (_ROL,))
            gevonden = cur.fetchone()

        assert gevonden is not None, (
            f"De rol {_ROL} bestaat niet. De applicatie kan dan alleen als tabeleigenaar "
            "verbinden en Row Level Security doet niets (ADR-036 OP-151)."
        )

    def test_the_application_role_cannot_bypass_row_level_security(self, db: PgConnection) -> None:
        """SUPERUSER of BYPASSRLS maakt de hele exercitie zinloos."""
        with db.cursor() as cur:
            cur.execute(
                "SELECT rolsuper, rolbypassrls, rolcanlogin, rolreplication "
                "FROM pg_roles WHERE rolname = %s",
                (_ROL,),
            )
            rij = cur.fetchone()

        assert rij is not None, f"rol {_ROL} ontbreekt"
        superuser, bypassrls, canlogin, replicatie = rij
        assert not superuser, f"{_ROL} is SUPERUSER en omzeilt daarmee elke policy"
        assert not bypassrls, f"{_ROL} heeft BYPASSRLS en omzeilt daarmee elke policy"
        assert not replicatie, (
            f"{_ROL} heeft REPLICATION. Daarmee kan de rol de volledige WAL uitlezen -- "
            "alle tenants, buiten elke policy om."
        )
        assert not canlogin, (
            f"{_ROL} heeft LOGIN. De migratie hoort de rol zonder wachtwoord en zonder "
            "inlogrecht aan te maken; het inlogrecht wordt per omgeving bewust gezet "
            "(docs/runbooks/applicatie-databaserol.md). Een LOGIN-rol in een migratie "
            "betekent dat er ergens een wachtwoord in de repository staat."
        )

    def test_the_application_role_is_not_a_member_of_another_role(self, db: PgConnection) -> None:
        """Rollidmaatschap is de achterdeur die de vlaggen hierboven niet zien.

        Een `GRANT <andere_rol> TO sanskritisetu_app` geeft via INHERIT alsnog de rechten
        van die rol. Is dat de tabeleigenaar, dan is RLS weer volledig weg terwijl
        `rolsuper` en `rolbypassrls` gewoon op false blijven staan (Gate 2-review
        2026-08-16).
        """
        with db.cursor() as cur:
            cur.execute(
                "SELECT roleid::regrole::text FROM pg_auth_members WHERE member = %s::regrole",
                (_ROL,),
            )
            lidmaatschappen = sorted(rij[0] for rij in cur.fetchall())

        assert not lidmaatschappen, (
            f"{_ROL} is lid van {lidmaatschappen}. Daarmee erft de rol de rechten van die "
            "rol(len); is er een tabeleigenaar bij, dan omzeilt de applicatie elke policy."
        )

    def test_the_application_role_owns_no_tables(self, db: PgConnection) -> None:
        """De eigenaar van een tabel omzeilt RLS op precies die tabel.

        `test_the_application_role_cannot_change_the_schema` bewaakt de WEG ernaartoe;
        deze test bewaakt de UITKOMST. Wie de rol ooit CREATE geeft (bijvoorbeeld om de
        runtime-DDL in `conversation_persistence.py` te laten werken) maakt de applicatie
        eigenaar van die tabellen en daarmee RLS-vrij.
        """
        with db.cursor() as cur:
            cur.execute(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relowner = %s::regrole ORDER BY 1",
                (_ROL,),
            )
            eigendom = sorted(rij[0] for rij in cur.fetchall())

        assert not eigendom, (
            f"{_ROL} is eigenaar van {len(eigendom)} objecten: {eigendom[:10]}. Op die "
            "objecten geldt geen enkele policy."
        )


class TestTheRoleIsConfinedToOneTenant:
    def test_the_application_role_sees_its_own_tenant(self, db: PgConnection) -> None:
        """Met de juiste tenantcontext is de eigen rij WEL zichtbaar.

        Zonder deze helft zou een policy die alles weigert de test hieronder halen, en dan
        is de applicatie stuk in plaats van veilig.
        """
        with db.cursor() as cur:
            cur.execute("SELECT id FROM tenants WHERE slug = 'rol-a'")
            rij = cur.fetchone()
        assert rij is not None
        tenant_a = rij[0]

        cur = _als_de_applicatierol(db, str(tenant_a))
        try:
            cur.execute("SELECT count(*) FROM agents WHERE tenant_id = %s", (tenant_a,))
            resultaat = cur.fetchone()
        finally:
            _herstel(cur)

        assert resultaat is not None and resultaat[0] == 1, (
            f"De applicatierol ziet zijn EIGEN rij niet (gevonden: {resultaat}). De policy "
            "of de rechten sluiten te veel af."
        )

    def test_the_application_role_sees_only_its_own_tenant(self, db: PgConnection) -> None:
        """De rij van de andere tenant is onzichtbaar -- ook zonder WHERE in de query."""
        with db.cursor() as cur:
            cur.execute(
                "SELECT id, slug FROM tenants WHERE slug IN ('rol-a','rol-b') ORDER BY slug"
            )
            tenants = dict((slug, ident) for ident, slug in cur.fetchall())

        cur = _als_de_applicatierol(db, str(tenants["rol-a"]))
        try:
            cur.execute("SELECT tenant_id FROM agents")
            zichtbaar = {rij[0] for rij in cur.fetchall()}
        finally:
            _herstel(cur)

        assert tenants["rol-b"] not in zichtbaar, (
            f"De applicatierol ziet met tenantcontext {tenants['rol-a']} ook de gegevens van "
            f"tenant {tenants['rol-b']} (zichtbaar: {sorted(zichtbaar)}). Dit is een query "
            "ZONDER WHERE -- precies het geval dat de databaselaag hoort af te vangen."
        )

    def test_without_tenant_context_the_application_role_sees_nothing(
        self, db: PgConnection
    ) -> None:
        """Geen tenantcontext betekent geen rijen -- niet 'alle rijen'."""
        cur = _als_de_applicatierol(db, None)
        try:
            cur.execute("SELECT count(*) FROM agents")
            resultaat = cur.fetchone()
        finally:
            _herstel(cur)

        assert resultaat is not None and resultaat[0] == 0, (
            f"Zonder tenantcontext ziet de applicatierol {resultaat} rijen. Een sessie die "
            "vergeet de tenant te zetten hoort niets te zien, niet alles."
        )


class TestEveryPolicyToleratesAMissingTenant:
    def test_no_policy_raises_when_the_tenant_context_is_missing(self, db: PgConnection) -> None:
        """Een lege tenantcontext geeft nul rijen, nooit een fout.

        `current_setting('app.current_tenant')` zonder tweede argument gooit
        `unrecognized configuration parameter`; met een lege waarde erin gooit
        `''::integer` een `invalid input syntax`. Gemeten 2026-08-16: veertien van de 138
        policies hadden die vorm. Een sessie zonder tenantcontext is niet exotisch -- de
        vier workers en een half dozijn andere sessieproducenten zetten hem nooit.

        **Een lege tabel maakt dit niet onschuldig, en dat is nagemeten.** De verwachting
        dat PostgreSQL de policy-expressie overslaat als er geen rijen zijn, klopt niet:
        `goals`, `departments`, `documents` en `company_templates` zijn alle vier leeg en
        gaven alle vier `invalid input syntax for type integer: ""`. Deze test meet dus
        echt iets -- laat niemand hem later "opruimen" met dat argument.

        Elke tabel krijgt een VERSE cursor en de lus controleert expliciet dat de
        verbinding in autocommit staat: zonder dat aborteert de eerste fout de transactie
        en falen alle volgende iteraties met `InFailedSqlTransaction`, waarna deze test
        138 van de 138 tabellen als stuk rapporteert en de echte elf verbergt.
        """
        assert db.autocommit, (
            "Deze verbinding staat niet in autocommit. Dan besmet een mislukte iteratie "
            "alle volgende en rapporteert deze test alles als stuk -- vals rood dat de "
            "echte oorzaak verbergt (Gate 2-review 2026-08-16, M1)."
        )

        with db.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (_ROL,))
            rol_bestaat = cur.fetchone() is not None
        assert rol_bestaat, (
            f"De rol {_ROL} bestaat niet, dus elke iteratie hieronder zou falen met "
            "'role does not exist' en de melding zou naar de verkeerde oorzaak wijzen. "
            "Draai eerst `alembic upgrade head`."
        )

        with db.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT tablename FROM pg_policies WHERE schemaname = 'public' "
                "ORDER BY tablename"
            )
            tabellen = [rij[0] for rij in cur.fetchall()]

        gefaald: list[str] = []
        for tabel in tabellen:
            cur = db.cursor()
            try:
                cur.execute(f"SET ROLE {_ROL}")
                cur.execute("SET app.current_tenant = ''")
                cur.execute(f'SELECT count(*) FROM "{tabel}"')
            except psycopg2.Error as fout:
                gefaald.append(
                    f"{tabel}: {type(fout).__name__}: {str(fout).strip().splitlines()[0]}"
                )
            finally:
                try:
                    _herstel(cur)
                except psycopg2.Error:
                    db.rollback()
                    cur.close()

        assert not gefaald, (
            f"{len(gefaald)} van de {len(tabellen)} tabellen met een policy geven een FOUT in "
            "plaats van nul rijen zodra de tenantcontext ontbreekt:\n"
            + "\n".join(f"  - {r}" for r in gefaald)
            + "\n\nGebruik NULLIF(current_setting('app.current_tenant', true), '')::INTEGER."
        )

    def test_every_normalised_policy_still_exists_and_is_safe(self, db: PgConnection) -> None:
        """De veertien genormaliseerde policies, bij naam, met de veilige vorm.

        De test hierboven kan namelijk ook groen worden door een policy te DROPPEN in
        plaats van te herschrijven -- en dan is de tabel voor elke tenant open. Voor
        `company_templates` is dat extra verraderlijk: die tabel heeft geen `tenant_id`, dus
        `test_every_table_with_a_tenant_column_has_a_policy` ziet hem nooit (Gate 2-review
        2026-08-16, BLOCKER 2).
        """
        with db.cursor() as cur:
            cur.execute(
                "SELECT tablename, policyname, qual FROM pg_policies WHERE schemaname = 'public'"
            )
            aanwezig = {(t, p): q for t, p, q in cur.fetchall()}

        ontbreekt: list[str] = []
        onveilig: list[str] = []
        for tabel, policy in GENORMALISEERDE_POLICIES.items():
            qual = aanwezig.get((tabel, policy))
            if qual is None:
                ontbreekt.append(f"{tabel}.{policy}")
            elif not (
                "current_setting('app.current_tenant'::text, true)" in qual
                and "NULLIF(" in qual.upper()
            ):
                onveilig.append(f"{tabel}.{policy}: {qual}")

        assert not ontbreekt, (
            f"Deze policies bestaan niet (meer): {ontbreekt}. Een verwijderde policy maakt "
            "de tabel voor elke tenant leesbaar onder de applicatierol -- dat is geen "
            "oplossing voor de crash-gevoelige vorm maar een groter gat."
        )
        assert not onveilig, (
            "Deze policies gebruiken `current_setting` zonder `missing_ok`:\n"
            + "\n".join(f"  - {r}" for r in onveilig)
        )

    def test_the_platform_template_exception_survived_the_normalisation(
        self, db: PgConnection
    ) -> None:
        """`company_templates` houdt zijn tenant-overstijgende tak voor platformsjablonen.

        De andere richting van de test hierboven: de normalisatie mocht die OR-tak niet
        opeten. Zonder deze test zou een herschrijving naar een kale
        `contributed_by_tenant_id = ...` groen zijn, en dan verdwijnen platformsjablonen
        voor iedereen.
        """
        with db.cursor() as cur:
            cur.execute(
                "SELECT qual FROM pg_policies WHERE schemaname = 'public' "
                "AND tablename = 'company_templates' AND policyname = %s",
                (GENORMALISEERDE_POLICIES["company_templates"],),
            )
            rij = cur.fetchone()

        assert rij is not None, "de policy op company_templates ontbreekt"
        assert "is_platform_template" in rij[0], (
            f"De policy op company_templates noemt `is_platform_template` niet meer: "
            f"{rij[0]}. Platformsjablonen zijn dan voor geen enkele tenant zichtbaar."
        )


class TestThePolicyCoverageIsComplete:
    def test_every_table_with_a_tenant_column_has_a_policy(self, db: PgConnection) -> None:
        """Een tabel met tenant_id zonder policy is onder de applicatierol volledig open."""
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                  AND EXISTS (SELECT 1 FROM information_schema.columns col
                              WHERE col.table_schema = 'public' AND col.table_name = c.relname
                                AND col.column_name = 'tenant_id')
                  AND NOT (c.relrowsecurity AND EXISTS (SELECT 1 FROM pg_policies p
                                  WHERE p.schemaname = 'public' AND p.tablename = c.relname))
                ORDER BY 1
                """
            )
            zonder = sorted(rij[0] for rij in cur.fetchall())

        onverwacht = [t for t in zonder if t not in KNOWN_ZONDER_POLICY]

        assert not onverwacht, (
            f"{len(onverwacht)} tabellen hebben een tenant_id maar geen policy:\n"
            + "\n".join(f"  - {t}" for t in onverwacht)
            + "\n\nOnder de applicatierol zijn die tabellen voor elke tenant volledig "
            "leesbaar. Voeg een policy toe, of zet een uitzondering met reden in "
            "KNOWN_ZONDER_POLICY."
        )

    def test_every_policy_is_actually_enabled(self, db: PgConnection) -> None:
        """Een policy op een tabel met RLS UIT doet niets, en `pg_policies` verzwijgt dat.

        `pg_policies` bevat geen enkele verwijzing naar `relrowsecurity` -- een policy op
        een tabel waarvoor Row Level Security is uitgeschakeld staat er identiek in.
        Zonder deze test blijven ALLE tests hierboven groen onder
        `ALTER TABLE <x> DISABLE ROW LEVEL SECURITY`, en dat is geen theoretisch geval: de
        keten bevat die opdracht voor elf tabellen (Gate 2-review ronde 2, BLOCKER 3).

        Alleen `agents` wordt in deze module gedragsmatig getoetst; voor de overige 137
        policies is dit de controle dat ze uberhaupt worden geevalueerd.
        """
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT p.tablename
                FROM (SELECT DISTINCT tablename FROM pg_policies WHERE schemaname = 'public') p
                JOIN pg_class c ON c.relname = p.tablename
                JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
                WHERE NOT c.relrowsecurity
                ORDER BY 1
                """
            )
            uit = sorted(rij[0] for rij in cur.fetchall())

        assert not uit, (
            f"{len(uit)} tabellen hebben wel een policy maar Row Level Security staat UIT:\n"
            + "\n".join(f"  - {t}" for t in uit)
            + "\n\nDie policies worden nooit geevalueerd. Zet RLS aan met "
            "`ALTER TABLE <naam> ENABLE ROW LEVEL SECURITY`."
        )

    def test_the_known_exceptions_are_not_stale(self, db: PgConnection) -> None:
        """Een uitzondering die inmiddels wel een policy heeft MOET uit de lijst."""
        with db.cursor() as cur:
            cur.execute("SELECT DISTINCT tablename FROM pg_policies WHERE schemaname = 'public'")
            met_policy = {rij[0] for rij in cur.fetchall()}

        opgelost = sorted(t for t in KNOWN_ZONDER_POLICY if t in met_policy)

        assert not opgelost, (
            f"Deze tabellen staan in KNOWN_ZONDER_POLICY maar hebben inmiddels wel een "
            f"policy: {opgelost}. Haal ze uit de lijst, anders rot de uitzondering dicht."
        )


class TestTheGrantsAreCompleteButNotWider:
    def test_the_application_role_can_read_every_table(self, db: PgConnection) -> None:
        """Een tabel zonder GRANT geeft `permission denied` -- een storing, geen lek."""
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'm', 'v')
                  AND NOT has_table_privilege(%s, c.oid, 'SELECT')
                ORDER BY 1
                """,
                (_ROL,),
            )
            zonder_recht = sorted(rij[0] for rij in cur.fetchall())

        assert not zonder_recht, (
            f"De applicatierol mag {len(zonder_recht)} tabellen niet lezen:\n"
            + "\n".join(f"  - {t}" for t in zonder_recht)
            + "\n\nDit gebeurt als een migratie na de rechtenmigratie een tabel aanmaakt "
            "waar ALTER DEFAULT PRIVILEGES niet op aanslaat -- bijvoorbeeld omdat een "
            "andere rol hem heeft aangemaakt."
        )

    def test_the_application_role_can_write_every_table(self, db: PgConnection) -> None:
        """Lezen alleen is niet genoeg; de applicatie schrijft ook.

        Met een uitzonderingslijst, want zonder die lijst is "geef de rol alles" de enige
        groene uitkomst en wordt elke versmalling een rode test -- precies andersom dan de
        bedoeling (Gate 2-review 2026-08-16, BLOCKER "de guard verbiedt versmalling").
        """
        ontbrekend: dict[str, list[str]] = {}
        with db.cursor() as cur:
            for recht in ("INSERT", "UPDATE", "DELETE"):
                cur.execute(
                    """
                    SELECT c.relname FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                      AND NOT has_table_privilege(%s, c.oid, %s)
                    ORDER BY 1
                    """,
                    (_ROL, recht),
                )
                gevonden = [rij[0] for rij in cur.fetchall() if rij[0] not in KNOWN_ALLEEN_LEZEN]
                if gevonden:
                    ontbrekend[recht] = gevonden

        assert not ontbrekend, "De applicatierol mist schrijfrechten: " + "; ".join(
            f"{recht} op {len(t)} tabellen ({t[:5]})" for recht, t in ontbrekend.items()
        )

    def test_the_application_role_cannot_change_the_schema(self, db: PgConnection) -> None:
        """De rol mag geen DDL. Anders is 'geef alles' een geldige oplossing.

        Migraties draaien bewust met een ANDERE, hoger geprivilegieerde verbinding; de
        applicatie hoort geen tabellen te kunnen maken of weggooien.
        """
        with db.cursor() as cur:
            cur.execute("SELECT has_schema_privilege(%s, 'public', 'CREATE')", (_ROL,))
            rij = cur.fetchone()

        assert rij is not None and rij[0] is False, (
            f"{_ROL} mag CREATE op schema public. Daarmee kan de applicatie tabellen "
            "aanmaken -- en de eigenaar van een tabel omzeilt RLS, dus dat ondergraaft "
            "precies wat deze rol moet opleveren."
        )


class TestTheSwitchIsStillBlocked:
    """Waarom de rol vandaag NOLOGIN is en er geen connectiestring omgaat.

    Dit is geen bijvangst maar de kern van OP-154. Beide Gate 2-reviewers kwamen er
    onafhankelijk op uit en ik heb het zelf nagemeten.
    """

    def test_the_login_lookup_finds_nothing_under_the_application_role(
        self, db: PgConnection
    ) -> None:
        """Het inlogpad zoekt op e-mailadres VOORDAT de tenant bekend is -- en vindt niets.

        `users` heeft sinds `20260522_add_rls_core_tables` een tenant-policy. Authenticatie
        heeft per definitie nog geen tenantcontext (`src/core/api/auth/router_login.py`),
        dus onder de applicatierol geeft die lookup nul rijen: niemand kan meer inloggen,
        registreren of een wachtwoord herstellen. `TenantFilterBypass` helpt niet -- dat zet
        alleen de ORM-hook uit, PostgreSQL trekt zich er niets van aan.

        **Deze test legt een MEETPUNT vast, geen staleness-mechanisme.** Een eerdere versie
        van deze docstring beweerde dat hij rood wordt zodra OP-154 is opgelost. Dat is
        onwaar en de Gate 2-review heeft het aangetoond: onder oplossing A (SECURITY
        DEFINER-functies) loopt het inloggen via een functie en geeft deze query nog steeds
        nul rijen, en onder oplossing B meet hij de verkeerde rol. Alleen het VERRUIMEN van
        de policy op `users` -- precies wat het runbook verbiedt -- zou hem rood maken.

        Staleness-mechanisme: ONTBREEKT. Deze test heeft geen anker dat rood wordt zodra
        de omschakeling wel is uitgevoerd. De eerdere verwijzing naar
        `test_the_switch_has_not_been_enabled_yet` was dood -- die test bestaat nergens in
        de `tests/`-boom (vastgesteld 2026-08-30, ADR-036 OP-154).
        """
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO users (tenant_id, email) SELECT id, 'inlog-op154@proef.test' "
                "FROM tenants WHERE slug = 'rol-a' ON CONFLICT DO NOTHING"
            )
            cur.execute("SELECT count(*) FROM users WHERE email = 'inlog-op154@proef.test'")
            rij = cur.fetchone()
        assert rij is not None and rij[0] == 1, "de proefgebruiker is niet aangemaakt"

        cur = _als_de_applicatierol(db, None)
        try:
            cur.execute("SELECT count(*) FROM users WHERE email = 'inlog-op154@proef.test'")
            gevonden = cur.fetchone()
        finally:
            _herstel(cur)

        assert gevonden is not None and gevonden[0] == 0, (
            f"De inloglookup vindt {gevonden} rijen onder de applicatierol. Als dat niet "
            "langer 0 is, is OP-154 opgelost -- werk dan ADR-036 en "
            "docs/runbooks/applicatie-databaserol.md bij en pas deze test aan, want dan is "
            "de omschakeling niet meer geblokkeerd."
        )

    # HIER HOORT HET STALENESS-ANKER VAN OP-154 TE STAAN, EN DAT IS ER NIET.
    #
    # De Gate 2-review toonde aan dat de test hierboven geen anker IS: onder oplossing A
    # (SECURITY DEFINER-functies) blijft deze query nul rijen geven en onder oplossing B
    # meet hij de verkeerde rol. Terecht.
    #
    # De vervanging die ik daarop schreef -- rood zodra de rol LOGIN krijgt, of er een
    # SECURITY DEFINER-functie op `users` bestaat, of er een tweede BYPASSRLS-rol is --
    # bleek bij het mutatiebewijs ZELF hol: met `ALTER ROLE sanskritisetu_app LOGIN`
    # actief (nagemeten: `rolcanlogin` = True, ook na de testrun) bleef hij groen. De
    # oorzaak daarvan is NIET vastgesteld. Hij is daarom verwijderd in plaats van
    # blijven staan: een guard waarvan gemeten is dat hij niets betrapt, is erger dan
    # geen guard, want hij wekt de indruk dat het punt geborgd is.
    #
    # Wat de blokkade vandaag wel vasthoudt: de rol heeft NOLOGIN (afgedwongen door
    # `test_the_application_role_cannot_bypass_row_level_security`), er is geen enkele
    # DATABASE_URL gewijzigd, en OP-154 staat in ADR-036 met het runbook.
    # TODO(OP-154): een staleness-anker dat aantoonbaar rood wordt.

class TestTheMeasurementIsHonest:
    def test_the_measurement_is_not_vacuous(self, db: PgConnection) -> None:
        """Lege verzamelingen maken elke test hierboven trivially groen."""
        with db.cursor() as cur:
            cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")
            rij = cur.fetchone()
            aantal_policies = rij[0] if rij else 0
            cur.execute(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r'"
            )
            rij = cur.fetchone()
            aantal_tabellen = rij[0] if rij else 0
            cur.execute("SELECT count(*) FROM agents")
            rij = cur.fetchone()
            aantal_agents = rij[0] if rij else 0

        assert aantal_policies >= 130, (
            f"Slechts {aantal_policies} policies gevonden; op 2026-08-16 waren het er 138. "
            "Heeft de keten wel gedraaid?"
        )
        assert aantal_tabellen >= 150, f"Slechts {aantal_tabellen} tabellen in de database."
        assert aantal_agents == 2, (
            f"{aantal_agents} agents in plaats van 2. Zonder rijen in twee tenants bewijzen "
            "de isolatietests niets."
        )


# ============================================================================
# ADR-036 OP-154 -- de aparte verbinding voor het pre-authenticatiepad
# ============================================================================

_BYPASS_ROL = "sanskritisetu_bypass"

# Alleen deze VIER tabellen mag de bypass-rol lezen. Afgelezen uit
# `src/core/api/auth/router_login.py:175-190` op commit 19e4fe34: `select(User)` met
# `selectinload(User.roles)` raakt `users`, `roles` en de koppeltabel `user_roles`, en
# `select(AccountLockout)` raakt `account_lockouts`.
#
# `tenants` stond hier eerst bij met als reden "voor registratie". Nagemeten en ONWAAR:
# `router_registration.py:41-81` doet geen `select(Tenant)`; de tenant komt uit
# `require_tenant_id()` (ContextVar). Verwijderd in plaats van met een nieuwe reden
# behouden -- een rol die elke policy omzeilt krijgt geen tabel "voor de zekerheid".
_PRE_AUTH_TABELLEN = {"users", "roles", "user_roles", "account_lockouts"}

# Per RUN willekeurig, nooit een constante. Een `finally` overleeft geen `kill -9`, en in
# dit project worden pytest-runs gekilld (`valkuil_integration_db_lock_after_kill`). Blijft
# de rol dan met LOGIN achter, dan is een wachtwoord UIT DE REPOSITORY meteen bruikbaar --
# en de testcontainer publiceert 0.0.0.0:5455, niet alleen localhost. Met een waarde die
# alleen in het geheugen van die ene run bestond, is een achtergebleven LOGIN hooguit een
# rommeltje en geen bruikbare toegang.
_PROEFWACHTWOORD = secrets.token_urlsafe(32)


@pytest.fixture
def applicatierol_kan_even_inloggen(db: PgConnection) -> Iterator[None]:
    """Geeft `sanskritisetu_app` tijdelijk LOGIN, en neemt dat gegarandeerd terug.

    **Dit is nodig en niet optioneel.** PostgreSQL toetst het recht om `SET ROLE` te doen
    tegen `session_user`. De `db`-fixture verbindt als `postgres` (superuser), dus een
    `SET ROLE`-meting daarlangs slaagt ALTIJD -- ook na een `REVOKE`. Dat is gemeten op
    2026-09-15: de eerste versie van deze meting zei "escalatie lukt altijd" en was
    waardeloos. Alleen een ECHTE inlogverbinding als de applicatierol meet het recht.

    **Let op: rollen zijn cluster-breed, niet per database.** Deze fixture raakt dus ook
    andere databases op dezelfde server. Daarom staat het terugzetten in een `finally`, is
    het wachtwoord per run willekeurig, en wordt een rol die AL inlogbaar was met rust
    gelaten.

    Dat laatste is geen beleefdheid maar een correctie: een eerdere versie zette altijd
    onvoorwaardelijk `NOLOGIN PASSWORD NULL` terug. Had een beheerder de rol net volgens
    `docs/runbooks/applicatie-databaserol.md` ingericht, dan wiste deze test diens
    wachtwoord. Dat is geen herstel maar forceren, en het zou een omgeving stukmaken die
    niets met deze test te maken heeft.
    """
    with db.cursor() as cur:
        cur.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname = %s", (_ROL,))
        rij = cur.fetchone()
    if rij is not None and rij[0]:
        pytest.skip(
            f"{_ROL} heeft AL inlogrecht: waarschijnlijk bewust ingericht volgens het "
            "runbook. Deze test zou diens wachtwoord wissen, dus hij slaat over."
        )

    with db.cursor() as cur:
        cur.execute(f"ALTER ROLE {_ROL} LOGIN PASSWORD %s", (_PROEFWACHTWOORD,))
    try:
        yield
    finally:
        with db.cursor() as cur:
            cur.execute(f"ALTER ROLE {_ROL} NOLOGIN PASSWORD NULL")


class TestDeBypassRolIsAlleenViaEenEigenVerbindingBereikbaar:
    """OP-154: het pre-authenticatiepad krijgt een EIGEN verbinding, geen rolwissel.

    De vier eigenschappen hieronder zijn gemeten op 2026-09-15 (PostgreSQL 15.19) voordat
    ze hier zijn vastgelegd; deze tests bewaken ze tegen de ECHTE rol die de migratie
    aanmaakt.
    """

    def test_de_bypass_rol_bestaat_en_omzeilt_rls(self, db: PgConnection) -> None:
        """Zonder BYPASSRLS ziet de rol nul rijen -- exact de storing die hij moet oplossen."""
        with db.cursor() as cur:
            cur.execute(
                "SELECT rolbypassrls, rolcanlogin, rolsuper FROM pg_roles WHERE rolname = %s",
                (_BYPASS_ROL,),
            )
            rij = cur.fetchone()

        assert rij is not None, (
            f"De rol {_BYPASS_ROL} bestaat niet. `20260915_bypass_databaserol` hoort hem "
            "aan te maken; zonder die rol is het pre-authenticatiepad na de omschakeling stil kapot."
        )
        bypassrls, canlogin, super_ = rij
        assert bypassrls is True, (
            f"{_BYPASS_ROL} heeft GEEN BYPASSRLS. Dan geeft de inloglookup nul rijen zonder "
            "foutmelding -- de rol lost dan niets op en wekt de indruk van wel."
        )
        assert canlogin is False, (
            f"{_BYPASS_ROL} kan inloggen. De migratie hoort NOLOGIN te zetten: een wachtwoord "
            "hoort niet in de repository, en zonder LOGIN verandert er niets aan een "
            "draaiende omgeving (zie docs/runbooks/applicatie-databaserol.md)."
        )
        assert super_ is False, f"{_BYPASS_ROL} is superuser. Dat mag nooit."

    def test_de_bypass_rol_is_niet_gegrant_aan_de_applicatierol(self, db: PgConnection) -> None:
        """Het grant is precies wat optie B onveilig maakte -- het mag er niet zijn.

        Gemeten 2026-09-15 vanaf een echte inlogverbinding: met het grant lukt een kale
        `SET ROLE` en zijn ALLE tenants zichtbaar, ook met NOINHERIT. BYPASSRLS is een
        rol-attribuut en geen overerfbaar privilege.
        """
        with db.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_auth_members m "
                "JOIN pg_roles lid ON lid.oid = m.member "
                "JOIN pg_roles rol ON rol.oid = m.roleid "
                "WHERE rol.rolname = %s AND lid.rolname = %s",
                (_BYPASS_ROL, _ROL),
            )
            gegrant = cur.fetchone() is not None

        assert not gegrant, (
            f"{_BYPASS_ROL} is gegrant aan {_ROL}. Daarmee kan de applicatieverbinding met "
            "een enkel `SET ROLE` ALLE tenants zien, permanent en niet alleen binnen een "
            "bypass-blok. De bypass-rol hoort ALLEEN via een eigen verbinding bereikbaar te "
            "zijn (ADR-036 OP-154, besluit Rakesh 2026-08-17)."
        )

    def test_de_applicatierol_kan_niet_omschakelen_naar_de_bypass_rol(
        self, db: PgConnection, applicatierol_kan_even_inloggen: None
    ) -> None:
        """De kern van het ontwerp, gemeten vanaf een ECHTE inlogverbinding.

        Niet via `SET ROLE` vanaf de superuser-verbinding van de `db`-fixture: die toetst
        het recht tegen `session_user` en slaagt altijd.
        """
        verbinding = psycopg2.connect(
            f"host=127.0.0.1 port={testdatabase_poort()} user={_ROL} "
            f"password={_PROEFWACHTWOORD} dbname={_SCRATCH_DB}"
        )
        try:
            with verbinding.cursor() as cur:
                cur.execute("SELECT session_user")
                rij = cur.fetchone()
                assert rij is not None and rij[0] == _ROL, (
                    "De verbinding draait niet als de applicatierol; dan meet deze test niets."
                )
                with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                    cur.execute(f"SET ROLE {_BYPASS_ROL}")
        finally:
            verbinding.close()

    def test_de_bypass_rol_mag_alleen_de_pre_auth_tabellen_lezen(self, db: PgConnection) -> None:
        """Deze rol omzeilt elke policy; hoe minder hij mag zien, hoe minder een lek waard is.

        Mutatierichting die ertoe doet: `GRANT SELECT ON ALL TABLES` in plaats van de vijf
        genoemde tabellen maakt deze test ROOD. Zonder deze helft zou "geef de bypass-rol
        alles" een geldige oplossing zijn.
        """
        with db.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.role_table_grants "
                "WHERE grantee = %s AND table_schema = 'public'",
                (_BYPASS_ROL,),
            )
            toegekend = {rij[0] for rij in cur.fetchall()}

        teveel = toegekend - _PRE_AUTH_TABELLEN
        assert not teveel, (
            f"{_BYPASS_ROL} mag {len(teveel)} tabel(len) lezen die niet op het "
            f"pre-authenticatiepad liggen: {sorted(teveel)}. Deze rol omzeilt ELKE policy; "
            "elke extra tabel is klantdata die op een enkele verbinding te lezen is. Breid de "
            "set alleen uit met een eigen migratie per omgezette aanroepplek (OP-154 stap 2)."
        )
        ontbreekt = _PRE_AUTH_TABELLEN - toegekend
        assert not ontbreekt, (
            f"{_BYPASS_ROL} mist SELECT op {sorted(ontbreekt)}. Het inlogpad leest die wel, "
            "dus dit geeft `permission denied` op het echte pad."
        )


# ============================================================================
# ADR-036 OP-155 -- elke policy gebruikt een vorm waarvan het GEDRAG is aangetoond
# ============================================================================

#: De twee policyvormen waarvan `TestDeNieuwePoliciesSchermenEchtAf` hieronder het gedrag
#: bewijst, precies zoals PostgreSQL ze teruggeeft in `pg_policies.qual`.
_BEWEZEN_VORMEN: frozenset[str] = frozenset(
    {
        "(tenant_id = (NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))::integer)",
        "((tenant_id)::text = NULLIF(current_setting('app.current_tenant'::text, true), "
        "''::text))",
    }
)

#: Policies die BEWUST een andere vorm hebben. Reden per regel, gedateerd.
_KNOWN_AFWIJKENDE_VORM: dict[tuple[str, str], str] = {
    (
        "company_templates",
        "company_templates_platform",
    ): "Gedeelde catalogus: platformsjablonen zijn bewust voor elke klant leesbaar. "
    "Alleen SELECT, en alleen voor rijen met `is_platform_template = true`. Die tabel "
    "heeft geen `tenant_id`-kolom -- 2026-09-16.",
    (
        "company_templates",
        "company_templates_tenant_isolation",
    ): "Zelfde catalogus, schrijfkant: een klant ziet platformsjablonen PLUS zijn eigen "
    "bijdragen. De klantvergelijking gebruikt `contributed_by_tenant_id` in plaats van "
    "`tenant_id`, verder identiek aan de bewezen INTEGER-vorm -- 2026-09-16.",
    (
        "user_roles",
        "rls_user_roles_tenant_isolation",
    ): "Koppeltabel zonder `tenant_id`: de policy toetst via EXISTS-subqueries dat zowel de "
    "gebruiker als de rol bij de huidige klant horen. Het gedrag (zien, leggen, wijzigen, "
    "verwijderen, over de klantgrens) wordt per commando gemeten in "
    "`test_user_roles_is_confined_to_its_tenant.py` en de schrijfpaden in "
    "`test_user_roles_schrijfpaden_onder_de_applicatierol.py` -- OP-190, 2026-10-09.",
}


@pytest.mark.integration
class TestElkePolicyGebruiktEenBewezenVorm:
    """De vorm wordt op een representant BEWEZEN en daarna overal AFGEDWONGEN.

    **Waarom dit naast de gedragstests hieronder bestaat.** Die bewijzen dat de twee
    policyvormen doen wat ze moeten doen, maar op TWEE tabellen: `roles` voor de
    INTEGER-vorm en `learning_patterns` voor de VARCHAR-vorm. Gemeten 2026-09-16 op de
    ketendatabase staan er 171 policies in `public`. Een `CREATE POLICY ... USING (true)`
    op een van de andere 169 haalt zowel de aanwezigheidstest als die gedragstests -- en
    dat is precies het gat dat beide Gate 2-reviews van 2026-09-15 noemden.

    Alle 169 een eigen gedragsproef geven zou per tabel een geldige proefrij vragen. Deze
    test doet het andersom: de VORM is behaviouraal bewezen, dus elke policy moet een van
    die vormen gebruiken. Een nieuwe vorm is geen fout, maar vraagt een eigen gedragsproef
    of een regel in `_KNOWN_AFWIJKENDE_VORM` met de reden erbij.

    Gemeten uitgangspunt: vier verschillende expressies over 171 policies -- 162x de
    INTEGER-vorm, 7x de VARCHAR-vorm, en twee bewuste uitzonderingen op
    `company_templates`.

    **Mutatiebewijs (2026-09-16), beide richtingen, een regel per element:**
    - `ALTER POLICY ... USING (true)` op `agents`                 -> ROOD, met naam
    - `::integer`-cast weggehaald uit de vorm op `agents`         -> ROOD, met naam
    - `company_templates_platform` uit de uitzonderingslijst      -> ROOD (staleness-kant)
    - een niet-bestaande uitzondering toegevoegd                  -> ROOD (staleness-kant)
    - ongewijzigd                                                 -> GROEN
    """

    def test_geen_enkele_policy_heeft_een_onbewezen_vorm(self, db: PgConnection) -> None:
        """Een policy met een eigen expressie is nergens aangetoond en telt dus als open."""
        with db.cursor() as cur:
            cur.execute(
                "SELECT tablename, policyname, qual FROM pg_policies "
                "WHERE schemaname = 'public' AND qual IS NOT NULL ORDER BY 1, 2"
            )
            alle = cur.fetchall()

        assert alle, (
            "Nul policies gevonden in `public`. Deze test meet dan niets -- controleer of "
            "de migratieketen tegen deze database is gedraaid."
        )

        afwijkend = [
            (tabel, naam, qual)
            for tabel, naam, qual in alle
            if qual not in _BEWEZEN_VORMEN and (tabel, naam) not in _KNOWN_AFWIJKENDE_VORM
        ]
        regels = "".join(chr(10) + f"  - {t}.{n}: {q}" for t, n, q in afwijkend)

        assert not afwijkend, (
            f"{len(afwijkend)} van de {len(alle)} policies gebruiken een vorm waarvan het "
            "gedrag nergens is aangetoond:"
            + regels
            + chr(10) * 2
            + "Een policy die er goed UITZIET is niet hetzelfde als een policy die "
            "afschermt: `USING (true)` haalt elke aanwezigheidstest. Voeg een gedragsproef "
            "toe aan `_GEDRAGSPROEVEN` en de vorm aan `_BEWEZEN_VORMEN`, of zet de "
            "uitzondering met een reden in `_KNOWN_AFWIJKENDE_VORM`."
        )

    def test_de_uitzonderingen_zijn_niet_verouderd(self, db: PgConnection) -> None:
        """Een uitzondering die niet meer bestaat MOET weg -- anders rot de lijst dicht."""
        with db.cursor() as cur:
            cur.execute(
                "SELECT tablename, policyname FROM pg_policies WHERE schemaname = 'public'"
            )
            bestaand = {(tabel, naam) for tabel, naam in cur.fetchall()}

        verdwenen = sorted(k for k in _KNOWN_AFWIJKENDE_VORM if k not in bestaand)
        assert not verdwenen, (
            "Deze uitzonderingen staan in `_KNOWN_AFWIJKENDE_VORM` maar bestaan niet meer "
            f"in de database: {verdwenen}. Haal ze weg, anders dekt de lijst iets af wat "
            "er niet is en verbergt hij later een echte afwijking."
        )


# ============================================================================
# ADR-036 OP-155 -- de 29 nieuwe policies WERKEN, niet alleen BESTAAN
# ============================================================================

#: Twee representanten van de 29 policies uit `20260915_rls_resterende_tabellen.py`, met
#: hun kolomtype. Ze zijn zo gekozen dat ze de twee VORMEN dekken die de migratie legt.
_GEDRAGSPROEVEN: dict[str, str] = {
    # INTEGER-variant, met `::INTEGER` in de policy. `roles` is bovendien de tabel met de
    # grootste blast radius: de autorisatie hangt eraan.
    "roles": "integer",
    # VARCHAR-variant, ZONDER `::INTEGER`. Als die cast er per ongeluk toch in komt, faalt
    # de policy op elke rij en wordt de tabel onzichtbaar -- stil.
    "learning_patterns": "varchar",
}


@pytest.mark.integration
class TestDeNieuwePoliciesSchermenEchtAf:
    """De 29 policies uit OP-155 worden op GEDRAG getoetst, niet op aanwezigheid.

    **Waarom dit bestaat.** Beide Gate 2-reviews van 2026-09-15 wezen onafhankelijk op
    hetzelfde gat: `test_every_table_with_a_tenant_column_has_a_policy` accepteert ELKE
    policy. `CREATE POLICY ... USING (true)` op alle 29 tabellen haalt die test, haalt
    `test_no_policy_raises_when_the_tenant_context_is_missing`, haalt
    `test_every_policy_is_actually_enabled` en haalt de staleness-test. Alle 29 tabellen
    konden dus volledig openstaan met een groene suite.

    De metingen die de werking aantonen stonden tot dan als COMMENTAAR in
    `KNOWN_ZONDER_POLICY`. Een comment kan niet rood worden.

    **Mutatiebewijs (2026-09-16), beide richtingen en per element:**
    1. De policy op `roles` vervangen door `USING (true)` -> `test_zonder_tenantcontext...`
       en `test_de_andere_tenant_blijft_onzichtbaar` ROOD voor die tabel.
    2. Idem voor `learning_patterns` -> ROOD.
    3. De `::INTEGER`-cast toevoegen aan de VARCHAR-policy -> die tabel wordt onzichtbaar
       met eigen tenantcontext -> `test_met_de_eigen_tenant_is_de_eigen_rij_zichtbaar` ROOD.
       Dit is de mutatie die de tweede policyvorm rechtvaardigt.
    4. Ongewijzigd -> GROEN.
    """

    @staticmethod
    def _zet_proefrijen(db: PgConnection, tabel: str, kolomtype: str) -> tuple[int, int]:
        """Een rij voor tenant `rol-a` en een voor `rol-b`. Geeft (a, b) terug."""
        with db.cursor() as cur:
            cur.execute("SELECT id, slug FROM tenants WHERE slug IN ('rol-a','rol-b')")
            tenants = {slug: ident for ident, slug in cur.fetchall()}
            cast = "::text" if kolomtype == "varchar" else ""
            if tabel == "roles":
                cur.execute(
                    f"INSERT INTO roles (tenant_id, name, is_active) "
                    f"SELECT id{cast}, 'gedragsproef-' || slug, true FROM tenants "
                    f"WHERE slug IN ('rol-a','rol-b') ON CONFLICT DO NOTHING"
                )
            else:
                cur.execute(
                    f"INSERT INTO learning_patterns (pattern_id, tenant_id, pattern_type, "
                    f"trigger_conditions, learned_behavior, confidence_score, success_rate, "
                    f"occurrence_count, is_active, created_at, updated_at) "
                    f"SELECT 'proef-' || slug, id{cast}, 'x', '{{}}'::jsonb, '{{}}'::jsonb, "
                    f"0.5, 0.5, 1, true, now(), now() FROM tenants "
                    f"WHERE slug IN ('rol-a','rol-b') ON CONFLICT DO NOTHING"
                )
        return tenants["rol-a"], tenants["rol-b"]

    @pytest.mark.parametrize("tabel,kolomtype", sorted(_GEDRAGSPROEVEN.items()))
    def test_zonder_tenantcontext_is_de_tabel_leeg(
        self, db: PgConnection, tabel: str, kolomtype: str
    ) -> None:
        """Fail-secure: geen context betekent geen rijen, niet alle rijen."""
        self._zet_proefrijen(db, tabel, kolomtype)
        cur = _als_de_applicatierol(db, None)
        try:
            cur.execute(f"SELECT count(*) FROM {tabel}")
            rij = cur.fetchone()
            aantal = rij[0] if rij else -1
        finally:
            _herstel(cur)

        assert aantal == 0, (
            f"`{tabel}` toont {aantal} rijen aan de applicatierol ZONDER tenantcontext. De "
            "policy hoort dan nul rijen te geven. Staat er een `USING (true)`?"
        )

    @pytest.mark.parametrize("tabel,kolomtype", sorted(_GEDRAGSPROEVEN.items()))
    def test_met_de_eigen_tenant_is_de_eigen_rij_zichtbaar(
        self, db: PgConnection, tabel: str, kolomtype: str
    ) -> None:
        """De tegenrichting. Zonder deze helft is 'weiger alles' een geldige policy.

        Dit is ook de test die een verkeerde CAST op de VARCHAR-tabellen betrapt: met
        `::INTEGER` in de policy matcht daar niets meer en wordt de tabel onzichtbaar.
        """
        tenant_a, _ = self._zet_proefrijen(db, tabel, kolomtype)
        cur = _als_de_applicatierol(db, str(tenant_a))
        try:
            cur.execute(f"SELECT count(*) FROM {tabel}")
            rij = cur.fetchone()
            aantal = rij[0] if rij else -1
        finally:
            _herstel(cur)

        assert aantal >= 1, (
            f"`{tabel}` toont NUL rijen aan de applicatierol MET tenantcontext {tenant_a}, "
            "terwijl er een rij voor die tenant staat. De policy sluit te veel af -- let op "
            "een `::INTEGER`-cast op een VARCHAR-kolom."
        )

    @pytest.mark.parametrize("tabel,kolomtype", sorted(_GEDRAGSPROEVEN.items()))
    def test_de_andere_tenant_blijft_onzichtbaar(
        self, db: PgConnection, tabel: str, kolomtype: str
    ) -> None:
        """De kern: een query ZONDER WHERE mag de andere klant niet opleveren."""
        tenant_a, tenant_b = self._zet_proefrijen(db, tabel, kolomtype)
        cur = _als_de_applicatierol(db, str(tenant_a))
        try:
            cur.execute(f"SELECT tenant_id FROM {tabel}")
            zichtbaar = {str(r[0]) for r in cur.fetchall()}
        finally:
            _herstel(cur)

        assert str(tenant_b) not in zichtbaar, (
            f"`{tabel}` toont met tenantcontext {tenant_a} OOK rijen van tenant {tenant_b} "
            f"(zichtbaar: {sorted(zichtbaar)}). Dit is een query zonder WHERE -- precies het "
            "geval dat de databaselaag hoort af te vangen."
        )

    def test_schrijven_zonder_tenantcontext_faalt_bij_INSERT(self, db: PgConnection) -> None:
        """INSERT is de ENIGE schrijfsoort die luid faalt -- en dat is meetbaar.

        UPDATE en DELETE zonder context raken nul rijen en slagen zonder fout; dat is
        gemeten en staat in `20260915_rls_resterende_tabellen.py`. Deze test legt de luide
        helft vast, zodat een latere `WITH CHECK (true)` opvalt.
        """
        cur = _als_de_applicatierol(db, None)
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(
                    "INSERT INTO roles (tenant_id, name, is_active) "
                    "VALUES (1, 'mag-niet', true)"
                )
        finally:
            db.rollback()
            _herstel(cur)
