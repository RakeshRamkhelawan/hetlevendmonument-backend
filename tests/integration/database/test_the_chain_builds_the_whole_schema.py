"""De migratieketen bouwt het VOLLEDIGE schema op een verse database (ADR-036 OP-140).

**Correctie 2026-09-10.** Deze docstring beschreef tot en met 2026-08-17 een situatie die
sindsdien is opgelost en anders leest bij een oppervlakkige blik. Oorspronkelijke meting
2026-08-16/17 (VOOR de fix):

    draaiende database (sanskritisetu_postgres/sanskritisetu):  183 tabellen
    verse database na `alembic upgrade head`:                   120 tabellen
    modeltabellen die de applicatie verwacht:                   186

Dat gat is gedicht via de OP-147/OP-140-baselinemigratie (`20260817_baseline_tabellen`,
idempotente `CREATE TABLE IF NOT EXISTS`): een verse database ging van 120 naar 191 tabellen,
bevestigd tegen een echte Azure PostgreSQL 16 op 2026-08-27 (ADR-036-register, OP-140,
STATUS=GESLOTEN 2026-08-30). Zelf opnieuw gemeten 2026-09-10 door deze tests daadwerkelijk
te draaien tegen een lokale PostgreSQL: alle GROEN, 192 modeltabellen in `Base.metadata`,
geen enkele ontbreekt in de keten. **Er kan dus WEL een werkende database uit de migraties
worden gemaakt** -- een nieuwe klantomgeving, een tweede regio of herstel na een calamiteit
mist niet langer `notifications`/`token_blacklist`/`workflow_executions`/`deletion_audit`/
`role_permissions`.

**Wat WEL nog openstaat (ADR-036 OP-150, bewust omheind -- zie CLAUDE.md):** dat alle
modeltabellen bestaan bewijst niet dat elke KOLOM en INDEX exact overeenkomt. `alembic check`
op de volledige keten meldt 516 verschillen met `Base.metadata`. Die vraag hoort bij OP-150,
niet bij deze test -- deze test bewaakt uitsluitend tabelvolledigheid.

**Waarom dit een INTEGRATIETEST is en geen architecture-test.**

De eerste versie van deze guard las de offline DDL (`alembic upgrade head --sql`). Dat leek
elegant -- geen database nodig -- en was FOUT. Gemeten: 37 van de 101 migraties in de keten
slaan hun werk over in offline-modus (`if not _is_offline(bind):`), en 28 gebruiken
`sa.inspect(bind)`, wat `backend-patterns.md` #9 juist verbiedt omdat het offline crasht. Acht
tabellen (`c7_workflows`, `learning_patterns`, ...) komen daardoor wel in een echte database
maar staan NERGENS in de offline DDL.

De offline uitvoer is dus geen betrouwbaar beeld van wat de keten bouwt -- en dat raakt meer
dan deze test: `scripts/pre-deploy-check.sh` gebruikt precies die dry-run als veiligheidspoort
(ADR-036 OP-148).

De enige eerlijke meting is daarom: de keten DRAAIEN op een verse database en kijken wat er
staat. Dat kost ongeveer een minuut en vraagt PostgreSQL; vandaar deze plek.

**Dit bestand draait sinds 2026-09-18 blokkerend in `scripts/pre-deploy-check.sh` stap 3c
(ADR-036 OP-227).** Tot die dag stond in dat script alleen een comment dat dat "hoort te"
gebeuren. Bewaakt door `tests/architecture/test_de_deploygate_draait_de_schematoets.py`, die
de aanroep toetst na het strippen van commentaar -- de naam stond namelijk al in een comment.

**Aantal tests, gemeten 2026-09-18 en niet geteld uit deze docstring.** Het zijn er ACHT,
verdeeld over vier klassen: `pytest <dit bestand> -q` geeft `8 passed in 18.51s`, 32,5s
wandklok inclusief het opstarten van een verse pgvector-container. De tekst hierboven zei tot
die dag "deze vier tests" en "alle vier GROEN"; dat was het aantal KLASSEN, en een sprintbrief
heeft die vier zonder nameten overgenomen. Precies de vorm waar dit project op stukloopt: een
verouderde bewering in een toelichting waar de volgende lezer op bouwt.

**Mutatiebewijs (2026-08-17), beide richtingen:**
- De baseline-migratie uit de keten gehaald -> ROOD met de ontbrekende tabelnamen in de
  melding.
- `import src.core.models.hr_skills_models` uit `import_all_models.py` gehaald -> de drie
  HR-tabellen verdwijnen uit `Base.metadata` en duiken op in
  `test_the_chain_creates_nothing_the_models_do_not_know`; dat is de tweede richting en
  precies waarom die test bestaat.
- Ongewijzigd -> GROEN, en `test_the_guard_is_not_vacuous` bewijst dat beide verzamelingen
  gevuld zijn; een lege maakt de eerste test trivially groen.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg2
from tests.fixtures.testdatabase import testdatabase_poort
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

_REPO_ROOT = Path(__file__).resolve().parents[3]
# Per xdist-worker een eigen naam: de fixture is module-scoped en dropt/creeert de
# database, dus met een vaste naam zouden vier workers elkaars verbinding afkappen
# midden in de keten (Gate 2-review 2026-08-17).
_SCRATCH_DB = f"chain_schema_check_{os.environ.get('PYTEST_XDIST_WORKER', 'main')}"

# Tabellen die de keten aanmaakt zonder dat er een ORM-model voor bestaat. Gedateerd
# 2026-08-17, reden per regel.
KNOWN_WITHOUT_MODEL: dict[str, str] = {
    "alembic_version": "beheerd door Alembic zelf; staat per definitie niet in Base.metadata",
    "_baseline_20260817_created": (
        "boekhouding van de baseline-migratie: welke van de 71 tabellen die upgrade zelf heeft "
        "aangemaakt, zodat de downgrade niets weghaalt wat er al stond (Gate 2-review HIGH-1)"
    ),
    "ml_models": "raw-SQL tabel zonder ORM-model -- OP-149",
    "ml_training_data": "raw-SQL tabel zonder ORM-model -- OP-149",
    "pack_activations": "raw-SQL tabel zonder ORM-model -- OP-149",
    "pack_health_metrics": "raw-SQL tabel zonder ORM-model -- OP-149",
    "_bypass_rol_20260915": (
        "boekhouding van de rol-migratie 20260915_bypass_databaserol: legt vast of die "
        "migratie de rol sanskritisetu_bypass IN DEZE DATABASE zelf heeft aangemaakt, zodat "
        "de downgrade een rol die er al was niet verwijdert -- geen domeinmodel, "
        "ADR-036 OP-154, 2026-09-15"
    ),
    "_app_rol_20260818": (
        "boekhouding van de rol-migratie 20260818_applicatie_databaserol: legt vast of "
        "die migratie de rol sanskritisetu_app zelf heeft aangemaakt, zodat de downgrade "
        "de rol niet verwijdert als hij al bestond -- geen domeinmodel, ADR-036 audit 2026-08-18"
    ),
}


def _server_dsn(database: str) -> str:
    poort = str(testdatabase_poort())
    return f"host=127.0.0.1 port={poort} user=postgres password=postgres dbname={database}"


def _verse_database() -> None:
    """Zet een lege database neer waarop de keten kan draaien."""
    conn = psycopg2.connect(_server_dsn("postgres"))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            # Verbindingen van een vorige run afkappen; anders faalt DROP met "in use".
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (_SCRATCH_DB,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{_SCRATCH_DB}"')
            cur.execute(f'CREATE DATABASE "{_SCRATCH_DB}"')
    finally:
        conn.close()


def _draai_de_keten() -> None:
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
        f"`alembic upgrade head` faalde met returncode {resultaat.returncode}. Zonder deze "
        "controle zou de guard een leeg schema meten en stil groen worden.\n"
        f"--- stderr ---\n{resultaat.stderr[-4000:]}"
    )


def _tabellen_in_de_verse_database() -> set[str]:
    conn = psycopg2.connect(_server_dsn(_SCRATCH_DB))
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            return {rij[0].lower() for rij in cur.fetchall()}
    finally:
        conn.close()


def _modeltabellen() -> set[str]:
    from src.core.database import import_all_models  # noqa: F401
    from src.core.database.database import Base

    return {naam.lower() for naam in Base.metadata.tables}


#: Modelkolommen die de migratieketen NIET aanmaakt.
#:
#: **Deze lijst hoort leeg te zijn, en is dat sinds 2026-09-17.** Hij stond die dag even
#: op VIJFENDERTIG kolommen over tien tabellen -- de gemeten drift tussen model en keten,
#: waaronder `tenants.domain` (dat registreren op staging een 500 gaf) en
#: `tenants.stripe_customer_id` (sinds 2025-12-23 in het model, nooit in een migratie).
#: Migratie `20260917_kolomdrift` heeft ze alle 35 alsnog aangemaakt, waarna
#: `test_de_kolomuitzonderingen_zijn_niet_verouderd` de lijst afdwong leeg te maken --
#: precies waarvoor die test bestaat.
#:
#: Komt hier ooit weer iets in, dan is dat een BEWUSTE, gedateerde uitzondering met een
#: reden per regel, en geen plek om een nieuwe kolom te parkeren.
KNOWN_KOLOMMEN_ZONDER_MIGRATIE: dict[str, set[str]] = {}


def _kolommen_in_de_verse_database() -> dict[str, set[str]]:
    """Per tabel de kolomnamen die de keten daadwerkelijk aanmaakt."""
    conn = psycopg2.connect(_server_dsn(_SCRATCH_DB))
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public'"
            )
            uit: dict[str, set[str]] = {}
            for tabel, kolom in cur.fetchall():
                uit.setdefault(tabel.lower(), set()).add(kolom.lower())
            return uit
    finally:
        conn.close()


def _modelkolommen() -> dict[str, set[str]]:
    from src.core.database import import_all_models  # noqa: F401
    from src.core.database.database import Base

    return {
        naam.lower(): {kolom.name.lower() for kolom in tabel.c}
        for naam, tabel in Base.metadata.tables.items()
    }


@pytest.fixture(scope="module")
def keten_schema() -> set[str]:
    """Bouw een verse database met ALLEEN de migraties en geef de tabellen terug."""
    _verse_database()
    _draai_de_keten()
    return _tabellen_in_de_verse_database()


@pytest.fixture(scope="module")
def keten_kolommen(keten_schema: set[str]) -> dict[str, set[str]]:
    """De kolommen van diezelfde verse database.

    Hangt aan `keten_schema` zodat de keten precies EEN keer draait: die duurt minuten.
    """
    assert keten_schema, "de keten heeft geen tabellen opgeleverd"
    return _kolommen_in_de_verse_database()


@pytest.mark.integration
class TestTheChainCreatesEveryModelTable:
    def test_no_model_table_is_missing_from_the_chain(self, keten_schema: set[str]) -> None:
        """Elke tabel die de applicatie verwacht wordt door de keten aangemaakt."""
        ontbreekt = sorted(_modeltabellen() - keten_schema)

        assert not ontbreekt, (
            f"`alembic upgrade head` op een VERSE database maakt deze {len(ontbreekt)} "
            "modeltabellen niet aan:\n"
            + "\n".join(f"  - {t}" for t in ontbreekt)
            + "\n\nDe unittests slagen hier wel doorheen -- die bouwen hun schema met "
            "`Base.metadata.create_all`. Staging en productie draaien de migraties en krijgen "
            "een `UndefinedTable`. Een nieuwe omgeving kan hiermee niet worden opgebouwd "
            "(ADR-036 OP-140)."
        )

    def test_the_chain_creates_nothing_the_models_do_not_know(self, keten_schema: set[str]) -> None:
        """De andere richting: geen DDL zonder model.

        Zonder deze helft zou 'maak alles aan wat je maar kunt bedenken' een geldige oplossing
        zijn voor de test hierboven. Een tabel zonder model is bovendien een echt signaal:
        ofwel dode DDL, ofwel een model dat niet in `import_all_models` staat -- en dat laatste
        is hoe `alembic autogenerate` aan een onverwachte DROP komt.
        """
        onbekend = sorted(keten_schema - _modeltabellen() - set(KNOWN_WITHOUT_MODEL))

        assert not onbekend, (
            f"De keten maakt deze tabellen aan zonder dat er een model voor bestaat: "
            f"{onbekend}. Verwijder de DDL, registreer het model in `import_all_models.py`, of "
            "zet een uitzondering in KNOWN_WITHOUT_MODEL met de reden erbij."
        )


@pytest.mark.integration
class TestTheChainCreatesEveryModelColumn:
    """De tweede as: niet alleen TABELLEN maar ook KOLOMMEN (ADR-036 OP-247/OP-249).

    WAAROM DEZE KLASSE BESTAAT. De tests hierboven vergelijken tabelNAMEN. Een model dat
    een kolom krijgt zonder migratie komt daar dus groen doorheen. Gemeten 2026-09-17 op
    staging: 31 kolommen over 9 tabellen bestonden wel in het model en niet in de
    database. Dat kwam pas boven water toen registreren een 500 gaf met
    `column tenants.domain does not exist` -- na maanden. `stripe_customer_id` staat sinds
    2025-12-23 in het model en in geen enkele migratie.

    Zestienduizend groene tests betrapten dat niet, want de unittests bouwen hun schema met
    `Base.metadata.create_all` en zien het model dus per definitie terug. Alleen een verse
    database uit de MIGRATIES laat het verschil zien, en die staat hier al.
    """

    def test_geen_modelkolom_ontbreekt_in_de_keten(
        self, keten_kolommen: dict[str, set[str]]
    ) -> None:
        # Tabellen die de keten mist meldt `test_no_model_table_is_missing_from_the_chain` al.
        ontbreekt = kolommen_alleen_in_model(
            _modelkolommen(), keten_kolommen, KNOWN_KOLOMMEN_ZONDER_MIGRATIE
        )

        assert not ontbreekt, (
            f"`alembic upgrade head` op een VERSE database maakt deze {len(ontbreekt)} "
            "modelkolommen niet aan:\n"
            + "\n".join(f"  - {k}" for k in ontbreekt)
            + "\n\nDe unittests slagen hier wel doorheen: die bouwen met "
            "`Base.metadata.create_all`. Staging en productie draaien de migraties en "
            "krijgen een `UndefinedColumn` zodra iets die kolom leest. Schrijf een "
            "migratie, of haal de kolom uit het model als hij dood is."
        )

    def test_de_kolomuitzonderingen_zijn_niet_verouderd(
        self, keten_kolommen: dict[str, set[str]]
    ) -> None:
        """Een uitzondering die de keten inmiddels WEL aanmaakt MOET uit de lijst."""
        modelkolommen = _modelkolommen()
        opgelost: list[str] = []
        for tabel, kolommen in sorted(KNOWN_KOLOMMEN_ZONDER_MIGRATIE.items()):
            for kolom in sorted(kolommen):
                in_keten = kolom in keten_kolommen.get(tabel, set())
                in_model = kolom in modelkolommen.get(tabel, set())
                if in_keten or not in_model:
                    opgelost.append(f"{tabel}.{kolom}")

        assert not opgelost, (
            "Deze uitzonderingen kloppen niet meer -- de keten maakt ze inmiddels aan, of "
            f"het model kent ze niet meer: {opgelost}. Haal ze uit "
            "KNOWN_KOLOMMEN_ZONDER_MIGRATIE, anders rot de lijst dicht en dekt hij straks "
            "een echt nieuw gat af."
        )


@pytest.mark.integration
class TestTheGuardMeasuresSomething:
    def test_the_guard_is_not_vacuous(self, keten_schema: set[str]) -> None:
        """Een lege bron maakt de tests hierboven trivially groen."""
        modellen = _modeltabellen()

        assert len(modellen) >= 150, (
            f"Slechts {len(modellen)} modeltabellen gevonden. Op 2026-08-17 waren het er 186. "
            "Laadt `import_all_models` wel alles?"
        )
        assert len(keten_schema) >= 100, (
            f"Slechts {len(keten_schema)} tabellen in de verse database. Heeft de keten wel "
            "gedraaid?"
        )

    def test_the_known_exceptions_are_not_stale(self, keten_schema: set[str]) -> None:
        """Een uitzondering die niet meer bestaat MOET uit de lijst."""
        verdwenen = sorted(naam for naam in KNOWN_WITHOUT_MODEL if naam not in keten_schema)

        assert not verdwenen, (
            f"Deze tabellen worden niet meer door de keten aangemaakt: {verdwenen}. Haal ze "
            "uit KNOWN_WITHOUT_MODEL."
        )


# ============================================================================
# ADR-036 OP-160 -- model en migratieketen zeggen hetzelfde over tenant-integriteit
# ============================================================================


def _samengestelde_fks_in_de_verse_database() -> set[tuple[str, tuple[str, ...], str]]:
    """(tabel, kolommen, doeltabel) van elke FK over MEER DAN EEN kolom.

    Alleen samengestelde keys: dat zijn in dit schema precies de keys die de tenantgrens
    afdwingen. Een enkelvoudige `user_id -> users.id` doet dat niet.
    """
    conn = psycopg2.connect(_server_dsn(_SCRATCH_DB))
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.conrelid::regclass::text,
                       array_agg(a.attname ORDER BY x.ord),
                       c.confrelid::regclass::text
                FROM pg_constraint c
                JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS x(attnum, ord) ON TRUE
                JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = x.attnum
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE c.contype = 'f' AND n.nspname = 'public'
                GROUP BY c.oid, c.conrelid, c.confrelid
                HAVING count(*) > 1
                """
            )
            return {
                (tabel.lower(), tuple(sorted(k.lower() for k in kolommen)), doel.lower())
                for tabel, kolommen, doel in cur.fetchall()
            }
    finally:
        conn.close()


def _samengestelde_fks_in_de_modellen() -> set[tuple[str, tuple[str, ...], str]]:
    from src.core.database import import_all_models  # noqa: F401
    from src.core.database.database import Base

    gevonden: set[tuple[str, tuple[str, ...], str]] = set()
    for tabel in Base.metadata.tables.values():
        for fk in tabel.foreign_key_constraints:
            if len(fk.elements) > 1:
                kolommen = tuple(sorted(e.parent.name.lower() for e in fk.elements))
                doel = next(iter(fk.elements)).column.table.name.lower()
                gevonden.add((tabel.name.lower(), kolommen, doel))
    return gevonden


@pytest.mark.integration
class TestModelEnKetenZeggenHetzelfdeOverTenantIntegriteit:
    """ADR-036 OP-160: samengestelde foreign keys horen in BEIDE te staan.

    **Waarom dit een guard nodig heeft.** De migratieketen legt op
    `user_persona_preferences` samengestelde verwijzingen naar `users(id, tenant_id)` en
    `personas(id, tenant_id)`. Die dwingen af dat een voorkeur bij een gebruiker en een
    persona van DEZELFDE tenant hoort. Tot 2026-09-15 stonden ze NIET in het model.

    Dat is geen cosmetisch verschil. Een schema dat uit de MODELLEN wordt gebouwd --
    `Base.metadata.create_all`, wat een deel van de tests doet -- kreeg de zwakkere,
    enkelvoudige variant. Een cross-tenant schrijf die productie weigert, liet zo'n test
    gewoon door: groen over iets wat in productie niet kan.

    Gemeten 2026-09-15 op een verse keten: de database had vijf verwijzingen op die tabel,
    het model drie.

    **Mutatiebewijs (2026-09-15), beide richtingen:**
    1. Een van de twee `ForeignKeyConstraint`-regels uit `persona_models.py` gehaald ->
       `test_de_keten_maakt_geen_samengestelde_fk_die_het_model_niet_kent` ROOD met tabel,
       kolommen en doeltabel in de melding.
    2. Idem voor de andere -> ROOD.
    3. Ongewijzigd -> GROEN, en `test_de_meting_is_niet_leeg` bewaakt dat er uberhaupt
       samengestelde keys gevonden worden -- zonder die helft is "vind niets" een geldige
       oplossing.
    """

    def test_de_keten_maakt_geen_samengestelde_fk_die_het_model_niet_kent(
        self, keten_schema: set[str]
    ) -> None:
        ontbreekt = _samengestelde_fks_in_de_verse_database() - _samengestelde_fks_in_de_modellen()
        assert not ontbreekt, (
            "De migratieketen legt samengestelde foreign keys die het MODEL niet kent:\n"
            + "\n".join(
                f"  {tabel} ({', '.join(kolommen)}) -> {doel}"
                for tabel, kolommen, doel in sorted(ontbreekt)
            )
            + "\n\nEen schema uit `Base.metadata.create_all` mist die dan, en een "
            "cross-tenant schrijf die productie weigert slaagt daar wel. Zet de "
            "`ForeignKeyConstraint` in `__table_args__` van het model (ADR-036 OP-160)."
        )

    def test_de_meting_is_niet_leeg(self, keten_schema: set[str]) -> None:
        """Zonder deze toets is 'vind niets, meld niets' een geldige oplossing."""
        aantal = len(_samengestelde_fks_in_de_verse_database())
        assert aantal >= 2, (
            f"Slechts {aantal} samengestelde foreign keys in de verse database. Op "
            "2026-09-15 waren het er minstens twee (beide op `user_persona_preferences`). "
            "Is de detectie stuk of is de migratie uit de keten gevallen?"
        )


# ============================================================================
# ADR-036 OP-247 -- de driftguard kijkt BEIDE kanten op en leest ook de verwijzingen
# ============================================================================
#
# **Wat hierboven ontbrak (OP-247, 2026-09-17).** De kolomguard vergeleek alleen NAMEN en
# alleen in EEN richting (modelkolom ontbreekt in de keten). Twee gaten bleven daardoor open:
#
# 1. Een kolom die wel in de database staat en niet in het model. Dat is OP-150 en wordt hier
#    niet weggehaald (dataverlies, wacht op een besluit), maar het MOET zichtbaar zijn: een
#    nieuwe kolom zonder model valt anders niet op. Daarom een gedateerde uitzonderingslijst.
# 2. Een verwijzing (foreign key) waarvan doel of kolompaar afwijkt. De samengestelde-FK-guard
#    hierboven sorteert de kolommen en vergelijkt alleen de doeltabel: een omgewisselde
#    verwijzing, (a, b) -> (x, y) in het model tegen (a, b) -> (y, x) in de keten, gaat daar
#    groen doorheen. Hieronder worden ALLE verwijzingen vergeleken als een lijst paren (eigen
#    kolom, doelkolom) in de volgorde van de constraint, plus de doeltabel.
#
# Wat hier BEWUST niet wordt vergeleken: de fysieke kolomvolgorde van een tabel. Gemeten
# 2026-10-20 op een verse keten: 18 tabellen hebben een andere volgorde dan het model, en
# dat is niet te verhelpen zonder tabellen te herbouwen (`ALTER TABLE ADD COLUMN` voegt altijd
# aan het eind toe). Het zegt niets over gedrag; een guard erop kost 18 vaste uitzonderingen
# en beschermt niets.

#: Kolommen die WEL in de database staan en NIET in het model (OP-150). Gedateerd
#: 2026-10-20, gemeten op een verse keten op head `20261014_pack_activations`. Weghalen is
#: dataverlies en wacht op een besluit; deze lijst mag alleen KRIMPEN. Drie van de dertien
#: zijn NOT NULL zonder standaardwaarde (study_collections.access_code,
#: pack_usage_aggregates.company_size, educational_access.code): een insert uit het model
#: faalt daar op een NOT NULL-schending zodra de tabel gebruikt wordt. Die tabellen waren
#: per 2026-09-17 leeg op alle drie gemeten omgevingen, dus nog zonder gevolg.
KNOWN_KOLOMMEN_ALLEEN_IN_DATABASE: dict[str, dict[str, str]] = {
    "collective_knowledge": {"extra_metadata": "OP-150, 2026-10-20: model kent de kolom niet"},
    "domain_packs": {
        "category": "OP-150, 2026-10-20: model kent de kolom niet",
        "is_active": "OP-150, 2026-10-20: model kent de kolom niet",
    },
    "educational_access": {
        "code": "OP-150, 2026-10-20: NOT NULL zonder default; model kent de kolom niet"
    },
    "pack_usage_aggregates": {
        "avg_health_score": "OP-150, 2026-10-20: model kent de kolom niet",
        "company_size": "OP-150, 2026-10-20: NOT NULL zonder default; model kent de kolom niet",
    },
    "registered_agents": {
        "department": "OP-150, 2026-10-20: model kent de kolom niet",
        "function": "OP-150, 2026-10-20: model kent de kolom niet",
    },
    "roles": {"permissions": "OP-150, 2026-10-20: model kent de kolom niet"},
    "study_collections": {
        "access_code": "OP-150, 2026-10-20: NOT NULL zonder default; model kent de kolom niet"
    },
    "tenants": {"config": "OP-150, 2026-10-20: model kent de kolom niet"},
    "users": {
        "first_name": "OP-150, 2026-10-20: model kent de kolom niet",
        "last_name": "OP-150, 2026-10-20: model kent de kolom niet",
    },
}

# (tabel, ((eigen kolom, doelkolom), ...) in constraintvolgorde, doeltabel)
Verwijzing = tuple[str, tuple[tuple[str, str], ...], str]

#: Verwijzingen die de keten WEL legt en het model NIET declareert, alleen voor tabellen die
#: een model hebben. Gedateerd 2026-10-20 (OP-150). Tabellen zonder model (OP-149) doen hier
#: niet mee: de guard vergelijkt alleen tabellen die beide kanten kennen.
KNOWN_VERWIJZINGEN_ALLEEN_IN_DATABASE: dict[Verwijzing, str] = {
    ("agent_governance_contracts", (("tenant_id", "id"),), "tenants"): "OP-150, 2026-10-20",
    ("domain_packs", (("tenant_id", "id"),), "tenants"): "OP-150, 2026-10-20",
    ("focus_builder_flows", (("tenant_id", "id"),), "tenants"): "OP-150, 2026-10-20",
    ("pack_usage_aggregates", (("pack_id", "id"),), "domain_packs"): "OP-150, 2026-10-20",
    ("user_notification_preferences", (("tenant_id", "id"),), "tenants"): "OP-150, 2026-10-20",
    ("user_notification_preferences", (("user_id", "id"),), "users"): "OP-150, 2026-10-20",
}


def kolommen_alleen_in_model(
    model: dict[str, set[str]],
    keten: dict[str, set[str]],
    uitzonderingen: dict[str, set[str]],
) -> list[str]:
    """Kolommen die het model kent en de keten niet (de oude richting)."""
    uit: list[str] = []
    for tabel, kolommen in sorted(model.items()):
        if tabel not in keten:
            continue
        for kolom in sorted(kolommen - keten[tabel] - uitzonderingen.get(tabel, set())):
            uit.append(f"{tabel}.{kolom}")
    return uit


def kolommen_alleen_in_keten(
    model: dict[str, set[str]],
    keten: dict[str, set[str]],
    uitzonderingen: dict[str, dict[str, str]],
) -> list[str]:
    """Kolommen die de keten maakt en het model niet kent (de nieuwe richting)."""
    uit: list[str] = []
    for tabel, kolommen in sorted(keten.items()):
        if tabel not in model:
            continue  # tabel zonder model: KNOWN_WITHOUT_MODEL en OP-149 gaan daarover
        for kolom in sorted(kolommen - model[tabel] - set(uitzonderingen.get(tabel, {}))):
            uit.append(f"{tabel}.{kolom}")
    return uit


def verwijzingen_alleen_in_een_kant(
    model: set[Verwijzing],
    keten: set[Verwijzing],
    tabellen_met_model: set[str],
    uitzonderingen_keten: dict[Verwijzing, str],
) -> tuple[list[Verwijzing], list[Verwijzing]]:
    """(alleen in model, alleen in keten) over alle verwijzingen van tabellen met model.

    Een omgewisseld kolompaar of een ander doel levert in BEIDE lijsten een regel op: de
    modelvariant staat dan alleen in het model en de ketenvariant alleen in de keten.
    """
    alleen_model = sorted(v for v in model - keten if v[0] in tabellen_met_model)
    alleen_keten = sorted(
        v for v in keten - model if v[0] in tabellen_met_model and v not in uitzonderingen_keten
    )
    return alleen_model, alleen_keten


def _alle_verwijzingen_in_de_verse_database() -> set[Verwijzing]:
    conn = psycopg2.connect(_server_dsn(_SCRATCH_DB))
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.relname,
                       array_agg(la.attname ORDER BY x.ord),
                       array_agg(ra.attname ORDER BY x.ord),
                       rt.relname
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_class rt ON rt.oid = c.confrelid
                JOIN pg_namespace n ON n.oid = c.connamespace
                JOIN LATERAL unnest(c.conkey, c.confkey) WITH ORDINALITY AS x(l, r, ord) ON TRUE
                JOIN pg_attribute la ON la.attrelid = c.conrelid AND la.attnum = x.l
                JOIN pg_attribute ra ON ra.attrelid = c.confrelid AND ra.attnum = x.r
                WHERE c.contype = 'f' AND n.nspname = 'public'
                GROUP BY c.oid, t.relname, rt.relname
                """
            )
            return {
                (
                    tabel.lower(),
                    tuple((a.lower(), b.lower()) for a, b in zip(eigen, doel, strict=True)),
                    doeltabel.lower(),
                )
                for tabel, eigen, doel, doeltabel in cur.fetchall()
            }
    finally:
        conn.close()


def _alle_verwijzingen_in_de_modellen() -> set[Verwijzing]:
    from src.core.database import import_all_models  # noqa: F401
    from src.core.database.database import Base

    gevonden: set[Verwijzing] = set()
    for tabel in Base.metadata.tables.values():
        for fk in tabel.foreign_key_constraints:
            paren = tuple((e.parent.name.lower(), e.column.name.lower()) for e in fk.elements)
            doel = next(iter(fk.elements)).column.table.name.lower()
            gevonden.add((tabel.name.lower(), paren, doel))
    return gevonden


@pytest.mark.integration
class TestDeDriftguardKijktBeideKantenOp:
    """ADR-036 OP-247: kolommen in beide richtingen, verwijzingen met doel en kolompaar."""

    def test_geen_databasekolom_zonder_model(self, keten_kolommen: dict[str, set[str]]) -> None:
        onbekend = kolommen_alleen_in_keten(
            _modelkolommen(), keten_kolommen, KNOWN_KOLOMMEN_ALLEEN_IN_DATABASE
        )
        assert not onbekend, (
            f"De keten maakt deze {len(onbekend)} kolommen aan die het model niet kent:\n"
            + "\n".join(f"  - {k}" for k in onbekend)
            + "\n\nZet de kolom in het model, of (alleen bij een bewust besluit) in "
            "KNOWN_KOLOMMEN_ALLEEN_IN_DATABASE met datum en reden. Weghalen uit de database "
            "is dataverlies en hoort bij OP-150."
        )

    def test_de_databaseuitzonderingen_zijn_niet_verouderd(
        self, keten_kolommen: dict[str, set[str]]
    ) -> None:
        modelkolommen = _modelkolommen()
        verouderd = [
            f"{tabel}.{kolom}"
            for tabel, kolommen in sorted(KNOWN_KOLOMMEN_ALLEEN_IN_DATABASE.items())
            for kolom in sorted(kolommen)
            if kolom not in keten_kolommen.get(tabel, set())
            or kolom in modelkolommen.get(tabel, set())
        ]
        assert not verouderd, (
            "Deze uitzonderingen kloppen niet meer (de keten maakt de kolom niet meer aan, of "
            f"het model kent hem inmiddels): {verouderd}. Haal ze uit "
            "KNOWN_KOLOMMEN_ALLEEN_IN_DATABASE."
        )

    def test_geen_verwijzing_wijkt_af_tussen_model_en_keten(self, keten_schema: set[str]) -> None:
        model = _alle_verwijzingen_in_de_modellen()
        keten = _alle_verwijzingen_in_de_verse_database()
        alleen_model, alleen_keten = verwijzingen_alleen_in_een_kant(
            model,
            keten,
            {t.lower() for t in _modelkolommen()} & keten_schema,
            KNOWN_VERWIJZINGEN_ALLEEN_IN_DATABASE,
        )
        assert not alleen_model and not alleen_keten, (
            "Model en keten leggen niet dezelfde verwijzingen.\n"
            + "Alleen in het MODEL (tabel, ((eigen, doel), ...), doeltabel):\n"
            + "\n".join(f"  {v}" for v in alleen_model)
            + "\nAlleen in de KETEN:\n"
            + "\n".join(f"  {v}" for v in alleen_keten)
            + "\n\nEen omgewisseld kolompaar of een ander doel staat in beide lijsten. "
            "Corrigeer het model of schrijf een migratie."
        )

    def test_de_verwijzingsuitzonderingen_zijn_niet_verouderd(self, keten_schema: set[str]) -> None:
        model = _alle_verwijzingen_in_de_modellen()
        keten = _alle_verwijzingen_in_de_verse_database()
        verouderd = sorted(
            v for v in KNOWN_VERWIJZINGEN_ALLEEN_IN_DATABASE if v not in keten or v in model
        )
        assert not verouderd, (
            f"Deze verwijzingsuitzonderingen kloppen niet meer: {verouderd}. Haal ze uit "
            "KNOWN_VERWIJZINGEN_ALLEEN_IN_DATABASE."
        )

    def test_het_volledige_model_is_selecteerbaar_op_de_keten(self, keten_schema: set[str]) -> None:
        """De staging-fout letterlijk nagespeeld: een SELECT van ALLE modelkolommen.

        Op 2026-09-17 brak registreren op `column tenants.domain does not exist`: een query die
        het volledige model selecteert faalt zodra een enkele kolom ontbreekt. Een registratietest
        op een keten-database bleek dat NIET te zien (gemeten 2026-10-20: 29 van 29 groen op een
        keten zonder `tenants.domain` en zonder `tenants.max_users`; de ORM laat niet-gezette
        kolommen uit de INSERT en registratie leest de rij niet terug). Daarom wordt hier voor
        elke modeltabel de SELECT uitgevoerd die de ORM zelf zou bouwen, met `LIMIT 0`.
        """
        from sqlalchemy import select
        from sqlalchemy.dialects import postgresql

        from src.core.database import import_all_models  # noqa: F401
        from src.core.database.database import Base

        stuk: list[str] = []
        conn = psycopg2.connect(_server_dsn(_SCRATCH_DB))
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        try:
            for naam, tabel in sorted(Base.metadata.tables.items()):
                if naam.lower() not in keten_schema:
                    continue  # ontbrekende TABELLEN meldt een andere test
                sql = str(
                    select(tabel)
                    .limit(0)
                    .compile(
                        dialect=postgresql.dialect(),
                        compile_kwargs={"literal_binds": True},
                    )
                )
                with conn.cursor() as cur:
                    try:
                        cur.execute(sql)
                    except psycopg2.Error as fout:
                        stuk.append(f"{naam}: {str(fout).strip().splitlines()[0]}")
        finally:
            conn.close()

        assert not stuk, (
            f"Een SELECT van het volledige model faalt op {len(stuk)} tabellen van de keten:\n"
            + "\n".join(f"  - {regel}" for regel in stuk)
        )

    def test_de_verwijzingsmeting_is_niet_leeg(self, keten_schema: set[str]) -> None:
        keten = _alle_verwijzingen_in_de_verse_database()
        model = _alle_verwijzingen_in_de_modellen()
        assert len(keten) >= 200 and len(model) >= 200, (
            f"Slechts {len(keten)} verwijzingen in de keten en {len(model)} in het model; op "
            "2026-10-20 waren dat er 294 en 282. Is de detectie stuk?"
        )


class TestDeVergelijkingZelfIsNietBlind:
    """Mutatiebewijs zonder database: de vergelijking vangt wat hij moet vangen."""

    def test_een_kolom_alleen_in_het_model_wordt_gezien(self) -> None:
        model = {"tenants": {"id", "domain"}}
        keten = {"tenants": {"id"}}
        assert kolommen_alleen_in_model(model, keten, {}) == ["tenants.domain"]

    def test_een_kolom_alleen_in_de_keten_wordt_gezien(self) -> None:
        model = {"tenants": {"id"}}
        keten = {"tenants": {"id", "config"}}
        assert kolommen_alleen_in_keten(model, keten, {}) == ["tenants.config"]

    def test_een_uitzondering_dekt_alleen_de_genoemde_kolom(self) -> None:
        model = {"tenants": {"id"}}
        keten = {"tenants": {"id", "config", "nieuw"}}
        uit = kolommen_alleen_in_keten(model, keten, {"tenants": {"config": "reden"}})
        assert uit == ["tenants.nieuw"]

    def test_een_omgewisselde_verwijzing_wordt_gezien(self) -> None:
        model: set[Verwijzing] = {("kind", (("a", "x"), ("b", "y")), "ouder")}
        keten: set[Verwijzing] = {("kind", (("a", "y"), ("b", "x")), "ouder")}
        alleen_model, alleen_keten = verwijzingen_alleen_in_een_kant(model, keten, {"kind"}, {})
        assert alleen_model and alleen_keten

    def test_een_andere_volgorde_van_dezelfde_paren_wordt_gezien(self) -> None:
        model: set[Verwijzing] = {("kind", (("a", "x"), ("b", "y")), "ouder")}
        keten: set[Verwijzing] = {("kind", (("b", "y"), ("a", "x")), "ouder")}
        alleen_model, alleen_keten = verwijzingen_alleen_in_een_kant(model, keten, {"kind"}, {})
        assert alleen_model and alleen_keten

    def test_een_ander_doel_wordt_gezien(self) -> None:
        model: set[Verwijzing] = {("kind", (("ouder_id", "id"),), "ouder")}
        keten: set[Verwijzing] = {("kind", (("ouder_id", "id"),), "grootouder")}
        alleen_model, alleen_keten = verwijzingen_alleen_in_een_kant(model, keten, {"kind"}, {})
        assert alleen_model and alleen_keten

    def test_identieke_verwijzingen_geven_niets(self) -> None:
        v: set[Verwijzing] = {("kind", (("a", "x"), ("b", "y")), "ouder")}
        assert verwijzingen_alleen_in_een_kant(v, set(v), {"kind"}, {}) == ([], [])
