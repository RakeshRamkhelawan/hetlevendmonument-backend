"""Bewaakt de verbindingsblokkade voor de unittests (ADR-036 OP-18).

De blokkade zelf en alle ontwerpkeuzes staan in `tests/fixtures/netwerkblokkade.py`; dit bestand
bewaakt hem. Elke test hieronder is een mutatieregel: de vier eerste zijn ROOD zonder
`tests/unit/conftest.py`, de rest is ROOD zodra de blokkade te breed wordt.

**ROOD-bewijs (gemeten 2026-08-31, met `tests/unit/conftest.py` nog niet aanwezig).** Zonder de
conftest doet een unittest gewoon een echte verbindingspoging en houdt niets hem tegen:
`test_een_uitgaande_tcp_verbinding_wordt_geblokkeerd` kreeg een gewone `OSError` van het
besturingssysteem in plaats van `EchteVerbindingInUnitTest`, en
`test_de_databaseroute_faalt_direct_in_plaats_van_na_57_seconden` liep in de retry-backoff van
`DatabaseManager.initialize()`. Precies dat is de bevinding van OP-18.
"""

import asyncio
import ast
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.fixtures.netwerkblokkade import (
    FIXTURES_DIE_ECHT_MOGEN_VERBINDEN,
    POORTEN_MET_GEDATEERDE_UITZONDERING,
    EchteVerbindingInUnitTest,
)

# Loopback met een poort waar niets luistert. Voor de geblokkeerde tests doet het adres niet toe
# (het besturingssysteem wordt nooit bereikt); 5455 is met opzet gekozen omdat dat de
# PostgreSQL-testpoort is en dus het adres uit de OP-18-bevinding zelf.
_POSTGRES_TESTPOORT = 5455
_DICHTE_POORT = 9  # discard-poort; niets luistert hier


# ---------------------------------------------------------------------------
# Richting (a): een echte verbindingspoging wordt betrapt
# ---------------------------------------------------------------------------


def test_een_uitgaande_tcp_verbinding_wordt_geblokkeerd() -> None:
    """Een gewone `socket.connect()` uit een unittest moet DIRECT falen met onze melding.

    Mutatie: `socket.socket.connect` niet patchen (of de conftest weghalen) -- dan komt hier een
    `OSError` van het besturingssysteem in plaats van `EchteVerbindingInUnitTest`, en is deze test
    rood. Dat is de gemeten toestand van voor deze commit.
    """
    verbinding = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(EchteVerbindingInUnitTest) as fout:
            verbinding.connect(("127.0.0.1", _POSTGRES_TESTPOORT))
    finally:
        verbinding.close()

    # De melding moet bruikbaar zijn: adres, testnaam en wat te doen.
    tekst = str(fout.value)
    assert "127.0.0.1" in tekst
    assert "OP-18" in tekst
    assert "_refresh_mv" in tekst


def test_een_connect_ex_wordt_ook_geblokkeerd() -> None:
    """`connect_ex` is een TWEEDE ingang en moet ook dicht.

    Mutatie: alleen `connect` patchen en `connect_ex` overslaan -- dan geeft `connect_ex` netjes
    een errno terug, de verbindingspoging gaat echt naar buiten, en deze test is rood.
    `connect_ex` is geen theoretisch geval: twee modules in `tests/unit` gebruiken juist deze
    ingang om Redis te proben.
    """
    verbinding = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(EchteVerbindingInUnitTest):
            verbinding.connect_ex(("127.0.0.1", _POSTGRES_TESTPOORT))
    finally:
        verbinding.close()


async def test_de_asyncio_route_wordt_ook_geblokkeerd() -> None:
    """Het pad dat asyncpg werkelijk neemt moet ook dicht.

    Dit is de test die de guard aan de BEVINDING knoopt in plaats van aan een los socket-objectje:
    asyncpg verbindt via `loop.create_connection`, en dat gaat onderwater door
    `socket.socket.connect`. Zou de blokkade alleen synchrone sockets pakken, dan bleef juist het
    databasepad open en bewaakte de guard niets van OP-18.
    """
    with pytest.raises(EchteVerbindingInUnitTest):
        await asyncio.open_connection("127.0.0.1", _POSTGRES_TESTPOORT)


async def test_de_databaseroute_faalt_direct_in_plaats_van_na_57_seconden() -> None:
    """`DatabaseManager.initialize()` moet DIRECT falen, niet na de retry-backoff.

    Dit is OP-18 zelf, als test. `initialize()` doet vijf pogingen met een `asyncio.timeout(10)`
    en 2s ertussen (`src/core/database/database.py:219-302`); dat is de 56,8s per test die de
    bevinding meldde. De guard moet daar dwars door heen, ook al vangt `initialize()` zowel
    `except TimeoutError` als `except Exception`. Dat lukt alleen omdat
    `EchteVerbindingInUnitTest` van `BaseException` erft.

    Mutatie: laat de exceptie van `Exception` erven in plaats van `BaseException` -- dan slikt
    `initialize()` hem op, probeert vijf keer opnieuw, en deze test is rood op de tijdsgrens.
    Een verse `DatabaseManager` en niet de globale `db_manager`, want die kan door een andere test
    al geinitialiseerd zijn en dan keert `initialize()` direct terug zonder te verbinden.
    """
    from src.core.database.database import DatabaseManager

    manager = DatabaseManager()
    postgres_config: dict[str, object] = {
        "url": f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{_POSTGRES_TESTPOORT}/x",
        "echo": False,
        "pool_size": 1,
        "max_overflow": 0,
        "pool_timeout": 5,
    }

    begin = time.monotonic()
    with patch.object(manager, "_get_db_config", return_value=postgres_config):
        with pytest.raises(EchteVerbindingInUnitTest):
            await manager.initialize()
    verstreken = time.monotonic() - begin

    # Ruim marge onder de 57s uit de bevinding, en ook onder de 60s suite-timeout.
    assert verstreken < 15, f"initialize() deed er {verstreken:.1f}s over -- backoff niet ontweken"


# ---------------------------------------------------------------------------
# Richting (b): legitiem gedrag blijft ongemoeid
# ---------------------------------------------------------------------------


async def test_een_correct_gemockte_databaseroute_blijft_groen() -> None:
    """De GEREPAREERDE vorm van de vier OP-18-tests moet groen en snel blijven.

    Dit is de tweede mutatierichting: een guard die "weiger alles" doet zou hier ook rood maken.
    `CritiqueStore.store()` heeft TWEE databasepaden -- `_persist_to_db` en `_refresh_mv` -- en
    alleen de eerste mocken was precies de bug. Met beide gemockt hoort er geen enkele
    verbindingspoging te zijn.
    """
    from src.core.agents.critique_store import Critique, CritiqueStore

    CritiqueStore._instance = None
    try:
        store = CritiqueStore()
        critique = Critique(
            critique_id="op18-guard-001",
            agent_name="guard_agent",
            task_id="task-op18",
            tenant_id=7,
            score=0.5,
            issues=[],
            suggestions=[],
            mode="ADVISORY",
            timestamp=datetime.now(timezone.utc),
            metadata=None,
        )

        begin = time.monotonic()
        with (
            patch.object(store, "_persist_to_db", new_callable=AsyncMock) as persist,
            patch.object(store, "_refresh_mv", new_callable=AsyncMock) as refresh,
        ):
            resultaat = await store.store(critique)
        verstreken = time.monotonic() - begin

        assert resultaat is True
        persist.assert_called_once_with(critique)
        refresh.assert_called_once()
        assert verstreken < 5, f"gemockte store() duurde {verstreken:.1f}s -- er verbond iets echt"
    finally:
        CritiqueStore._instance = None


def test_een_socket_aanmaken_en_binden_mag_nog() -> None:
    """Alleen UITGAAND verbinden is geblokkeerd, niet de rest van de socket-laag.

    Zonder deze test is "weiger elke socket-operatie" een geldige oplossing, en dan sloopt de
    guard functionaliteit in plaats van hem te bewaken.
    """
    verbinding = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        verbinding.bind(("127.0.0.1", 0))
        verbinding.listen(1)
        _, poort = verbinding.getsockname()
        assert poort > 0
    finally:
        verbinding.close()


def test_socketpair_blijft_werken_want_asyncio_heeft_hem_nodig() -> None:
    """`socket.socketpair()` MOET door de blokkade heen komen.

    Dit is de mutatie de andere kant op voor de derde gepatchte naam. Op Windows is `socketpair`
    geemuleerd met een echte loopback-`connect()` (`Lib/socket.py:623`), en
    `SelectorEventLoop._make_self_pipe()` roept dat aan bij het aanmaken van ELKE event loop.
    Mutatie: haal de bypass uit `_socketpair_met_bypass` -- dan faalt niet alleen deze test maar
    valt elke async test in de suite om op een half gebouwde loop
    (`AttributeError: '_WindowsSelectorEventLoop' object has no attribute '_ssock'`, gemeten).
    """
    links, rechts = socket.socketpair()
    try:
        links.sendall(b"ping")
        assert rechts.recv(4) == b"ping"
    finally:
        links.close()
        rechts.close()


@pytest.mark.echte_netwerkverbinding_toegestaan
def test_de_opt_out_marker_staat_een_echte_verbinding_toe() -> None:
    """De opt-out moet werken, anders is er geen uitweg voor een test die echt moet verbinden.

    Vandaag draagt precies een echte test die marker:
    `tests/unit/test_ssl_tls.py::TestCertificateValidation::test_certificate_expiry_check`.
    Hier wordt de marker zelf getoetst: de poging moet bij het besturingssysteem AANKOMEN, dus we
    verwachten een gewone `OSError` (refused of timeout). `EchteVerbindingInUnitTest` erft van
    `BaseException` en niet van `OSError`, dus als de blokkade hier onterecht toch geldt, vangt
    `pytest.raises(OSError)` hem NIET en is deze test rood -- precies wat je wil.
    """
    verbinding = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    verbinding.settimeout(0.2)
    try:
        with pytest.raises(OSError):
            verbinding.connect(("127.0.0.1", _DICHTE_POORT))
    finally:
        verbinding.close()


def test_de_getolereerde_poorten_bevatten_geen_databasepoort() -> None:
    """De uitzonderingslijst mag NOOIT een databasepoort bevatten.

    Dit is de belangrijkste begrenzing van de gedateerde uitzondering: zodra iemand 5432 of 5455
    toevoegt "om de suite groen te krijgen", bewaakt deze guard OP-18 niet meer en is de hele
    commit zinloos geworden. Dan hoort deze test rood te zijn.

    Mutatie: zet `5455: "even groen maken"` in `POORTEN_MET_GEDATEERDE_UITZONDERING` -- dan valt
    deze test EN `test_een_uitgaande_tcp_verbinding_wordt_geblokkeerd` om.
    """
    databasepoorten = {5432, 5455, 5435}
    overtreding = sorted(databasepoorten & set(POORTEN_MET_GEDATEERDE_UITZONDERING))
    assert not overtreding, (
        f"Databasepoort(en) {overtreding} staan in POORTEN_MET_GEDATEERDE_UITZONDERING. Daarmee "
        "is de OP-18-borging uitgezet: juist het databasepad moet betrapt worden."
    )


def test_elke_getolereerde_poort_heeft_een_gemeten_reden() -> None:
    """Geen kale set: elke uitzondering draagt een reden met een vindplaats.

    De vier eisen bij een gedateerde uitzondering vragen een reden PER regel. Een lege of
    nietszeggende string is precies hoe zo'n lijst alsnog dichtrot.
    """
    te_dun = sorted(
        poort
        for poort, reden in POORTEN_MET_GEDATEERDE_UITZONDERING.items()
        if len(reden) < 80 or "gemeten" not in reden
    )
    assert not te_dun, (
        f"Deze uitzonderingen hebben geen bruikbare, gemeten reden: {te_dun}. Schrijf erbij "
        "hoeveel connects zijn gemeten en welke code ze veroorzaakt."
    )


def test_een_getolereerde_poort_wordt_doorgelaten() -> None:
    """De uitzondering moet ook echt werken, anders is de suite rood.

    Tweede mutatierichting voor de poortenlijst: haal 6379 uit
    `POORTEN_MET_GEDATEERDE_UITZONDERING` en deze test valt om -- en met hem de 19 tests die
    vandaag op die poort leunen.
    """
    verbinding = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    verbinding.settimeout(0.2)
    try:
        # Mag WEL naar het besturingssysteem: dus of het lukt, of een gewone OSError. Onze
        # `BaseException` erft niet van `OSError`, dus als de blokkade hier onterecht toch geldt,
        # ontsnapt hij aan deze `except` en is de test rood.
        try:
            verbinding.connect(("127.0.0.1", 6379))
        except OSError:
            pass
    finally:
        verbinding.close()


# ---------------------------------------------------------------------------
# De uitzonderingslijst mag niet dichtrotten
# ---------------------------------------------------------------------------


def test_de_fixtureuitzondering_is_niet_verouderd() -> None:
    """Elke naam in `FIXTURES_DIE_ECHT_MOGEN_VERBINDEN` moet nog een echte fixture zijn.

    Dit is de staleness-helft uit `.claude/rules/quality-gates.md`: een uitzondering die is
    opgelost of hernoemd MOET uit de lijst, anders staat er stilletjes een gat open. Er wordt op
    STRUCTUUR getoetst en niet op tekst -- de namen komen uit de AST als functies met een
    fixture-decorator, zodat een naam die alleen in een comment of docstring voorkomt niet
    meetelt.

    De hele map `tests/fixtures/` wordt gescand en niet alleen `database.py`. Dat is geen
    voorzorg maar een gemeten correctie: de eerste versie keek alleen in `database.py` en meldde
    vier van de zes namen als verouderd, terwijl ze alle zes bestaan -- verspreid over vier
    modules (`database.py`, `api.py`, `auth.py`, `tenant.py`). De guard was dus te NAUW, niet de
    lijst te ruim. Precies de faalvorm die deze test hoort te vangen, en hij ving zichzelf.
    """
    fixturemap = Path(__file__).resolve().parents[1] / "fixtures"

    fixturenamen: set[str] = set()
    for bron in sorted(fixturemap.glob("*.py")):
        boom = ast.parse(bron.read_text(encoding="utf-8"))
        for knoop in boom.body:
            if not isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in knoop.decorator_list:
                # `ast.dump` zou de docstring meelezen; daarom expliciet over de decorators.
                if "fixture" in ast.unparse(decorator):
                    fixturenamen.add(knoop.name)
                    break

    verouderd = sorted(FIXTURES_DIE_ECHT_MOGEN_VERBINDEN - fixturenamen)
    assert not verouderd, (
        "Deze namen staan in FIXTURES_DIE_ECHT_MOGEN_VERBINDEN maar zijn geen fixture (meer) in "
        f"tests/fixtures/: {verouderd}. Haal ze uit de lijst in "
        "tests/fixtures/netwerkblokkade.py, anders staat er een uitzondering open die niets "
        "meer dekt."
    )
