"""De testdatabase wordt EXPLICIET opgegeven, nooit geraden (ADR-036 OP-243).

**Wat hiervoor stond.** `tests/integration/conftest.py` probeerde poort 5435, dan 5455, en
nam wie er antwoordde. Dat ging op 2026-09-14 mis: een vergeten `act`-servicecontainer
luisterde zes uur op 5435 met daarin de tabellen van zijn eigen migratierun. De detectie
letterlijk nagespeeld gaf "verbinding geslaagd" -- de integratiesuite zou dus hebben
gedraaid tegen een wegwerpdatabase. Niet skippen, niet falen, gewoon meten aan het
verkeerde.

**Waarom een identiteitstoets op de database zelf niet werkt.** Twee ontwerpen zijn
verworpen voordat dit bestand er kwam, en ze staan hier zodat niemand ze opnieuw bedenkt:

1. *Een merkteken dat de suite zelf zet* ("leeg -> markeren, gemarkeerd -> doorgaan,
   tabellen zonder merkteken -> weigeren"). Een NET AANGEMAAKTE productiedatabase is ook
   leeg en valt dus in de markeer-tak -- uitgerekend de enige tak die schrijft. En het
   merkteken maakt zichzelf waar: wie de suite eenmaal per ongeluk tegen zijn
   ontwikkeldatabase draait, krijgt daar voortaan geen waarschuwing meer over.
2. *`alembic_version` tegen de verwachte head.* Een verse CI-database die de keten net heeft
   gedraaid en een lokale van drie dagen oud hebben dezelfde head. Dat meet "heeft dit
   schema", niet "is dit de bedoelde database".

Het antwoord mag dus niet uit de database komen -- die kan alles beweren -- maar uit iets
dat de suite niet zelf kan fabriceren: een keuze van een mens.

**Geen default, met opzet.** `os.getenv(NAAM, "5455")` ziet er bijna hetzelfde uit maar is
een gok met een vast antwoord; dan is precies het probleem hierboven binnen een dag terug.
In deze repo staan twee zulke terugvallen (`tests/conftest.py` met `TEST_PG_PORT` en
`tests/e2e/phase7/conftest.py` met een URL naar poort 55433 en andere inloggegevens); die
worden hier NIET gevolgd. Zie ADR-036 OP-243 Fase 2.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse, urlsplit, urlunsplit

#: De enige bron van waarheid voor waar de integratietests hun database vinden.
VARIABELE = "SANSKRITISETU_TEST_DATABASE_URL"

#: Wat een mens moet draaien als de variabele ontbreekt. Staat in de foutmelding zelf,
#: want een melding die alleen constateert kost de lezer een zoektocht.
VOORBEELD = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5455/sanskritisetu_test"


class TestdatabaseNietOpgegeven(RuntimeError):
    """De integratietests weten niet welke database ze mogen gebruiken.

    Dit is met opzet een FOUT en geen skip: een fout noemt de oorzaak en het commando dat
    hem oplost, een skip alleen "not available".

    NIET de reden, al stond dat eerst wel in OP-243: een module-level skip geeft GEEN
    exitcode 0. Nagemeten 2026-09-15 tegen de oude conftest met beide poorten dicht --
    exitcode 1, voor een los bestand en voor de hele map. Die claim was overgenomen van een
    andere sessie zonder nameting en is ingetrokken.
    """


def testdatabase_url(*, database: str | None = None, sync: bool = False) -> str:
    """Geef de opgegeven testdatabase-URL, of faal met het commando dat het oplost.

    `database` vervangt alleen de DATABASENAAM en laat host, poort en inloggegevens uit de
    opgave staan. Dat is met opzet: in `tests/` komen vier namen voor (`sanskritisetu`,
    `sanskritisetu_test`, `sanskriti_test` en de wegwerpdatabases die drie tests zelf
    aanmaken). Die namen betekenen verschillende dingen en worden hier NIET gelijkgetrokken
    -- alleen de vraag "welke server" krijgt een antwoord.

    `sync=True` geeft de vorm zonder asyncdriver (`postgresql://`), voor de plekken die een
    synchrone engine of `psycopg` gebruiken.
    """
    waarde = _ruwe_url()
    if database is None and not sync:
        return waarde
    delen = urlsplit(waarde)
    schema = "postgresql" if sync else delen.scheme
    pad = f"/{database}" if database is not None else delen.path
    return urlunsplit((schema, delen.netloc, pad, delen.query, delen.fragment))


def _ruwe_url() -> str:
    """De onbewerkte opgave uit de omgeving, of een fout met het commando erbij."""
    waarde = os.environ.get(VARIABELE, "").strip()
    if not waarde:
        raise TestdatabaseNietOpgegeven(
            f"{VARIABELE} is niet gezet, dus de integratietests weten niet tegen welke "
            f"database zij mogen draaien.\n"
            f"Dit wordt NIET geraden: op 2026-09-14 zou een poortscan de suite tegen een "
            f"vergeten wegwerpcontainer hebben laten draaien (ADR-036 OP-243).\n"
            f"\n"
            f"Start de testdatabase en wijs hem aan:\n"
            f"    docker start sanskritisetu_test_db ss_redis_e2e\n"
            f'    export {VARIABELE}="{VOORBEELD}"\n'
            f"PowerShell:\n"
            f'    $env:{VARIABELE} = "{VOORBEELD}"'
        )
    return waarde


def testdatabase_poort() -> int:
    """De poort uit de opgegeven URL -- afgeleid, nooit apart ingesteld.

    Bestaat omdat 19 testbestanden `POSTGRES_PORT` lezen (gemeten 2026-09-15). Die blijven
    in Fase 1 ongewijzigd; `tests/integration/conftest.py` zet die variabele voortaan uit
    DEZE waarde, zodat er nog maar een bron is. Fase 2 haalt de lezers zelf weg.
    """
    poort = urlparse(_ruwe_url()).port
    if poort is None:
        raise TestdatabaseNietOpgegeven(
            f"{VARIABELE} bevat geen poortnummer: {_ruwe_url()!r}. "
            f"Geef de poort expliciet op, bijvoorbeeld {VOORBEELD!r}."
        )
    return poort


#: Een database waarop de suite mag WISSEN heeft een naam die hierop eindigt (brief 2026-10-26). De naam is een keuze
#: van een mens bij het aanmaken van de database; dat is precies de soort aanwijzing waar dit bestand voor kiest.
TESTACHTERVOEGSEL = "_test"

#: De netwerkpoort van de ontwikkeldatabase (`docker-compose`): daar wist de suite nooit, ook niet bij een testnaam.
ONTWIKKELPOORT = 5435


class GeenTestdatabase(RuntimeError):
    """De suite zou iets wissen op een database die niet aantoonbaar een testdatabase is. Er is NIETS gewist."""


def eis_testdatabase(url: str) -> None:
    """Weiger een URL waarop de suite niet mag wissen (`DROP SCHEMA`, verbindingen beeindigen).

    Toegestaan alleen als de databasenaam op `TESTACHTERVOEGSEL` eindigt (exacte schrijfwijze) EN de netwerkpoort niet
    `ONTWIKKELPOORT` is. Gemeten 2026-10-26: zonder deze controle maakte de sessie-fixture van de integratietests de
    gedeelde testdatabase `sanskritisetu` op 5455 leeg; dezelfde fixture kon evengoed naar de ontwikkeldatabase wijzen.

    De foutmelding noemt naam, host en poort, NOOIT het wachtwoord of de rest van de URL.
    """
    delen = urlsplit(url)
    naam = delen.path.lstrip("/")
    poort = delen.port
    redenen: list[str] = []
    # Gate 2 (beveiligingsreview 2026-10-27): bij SQLAlchemy met asyncpg WINT een queryparameter (`?database=`,
    # `?port=`, `?host=`) van het pad en de poort in de URL. `.../x_test?database=sanskritisetu&port=5435` zou de
    # naamcontrole halen terwijl de engine naar de ontwikkeldatabase verbindt. Dezelfde regel als
    # `scripts/wegwerp_database.py::controleer_wegwerp_database`: geen querystring.
    if delen.query:
        redenen.append("de URL bevat queryparameters die host, poort of databasenaam kunnen overschrijven")
    # Zonder host of poort vult asyncpg ze uit PGHOST/PGPORT/PGDATABASE in de omgeving, en die kunnen naar de
    # ontwikkeldatabase wijzen: dan is de poort die hier wordt gecontroleerd niet die van de verbinding.
    if not delen.hostname or poort is None:
        redenen.append("de URL noemt geen host en poort expliciet")
    if not naam.endswith(TESTACHTERVOEGSEL):
        redenen.append(f"de databasenaam {naam!r} eindigt niet op {TESTACHTERVOEGSEL!r}")
    if poort == ONTWIKKELPOORT:
        redenen.append(f"de netwerkpoort {poort} is die van de ontwikkeldatabase")
    if redenen:
        raise GeenTestdatabase(
            "De testsuite weigert hier te wissen: "
            + " en ".join(redenen)
            + f" (host {delen.hostname!r}, poort {poort}). Er is niets gewist en geen verbinding beeindigd. "
            f"Maak een testdatabase aan met een naam op {TESTACHTERVOEGSEL!r}, bijvoorbeeld {VOORBEELD!r}, "
            f"en wijs hem aan via {VARIABELE}."
        )

