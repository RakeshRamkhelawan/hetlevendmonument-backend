"""Blokkeer echte netwerk- en databaseverbindingen in de unittests (ADR-036 OP-18).

**De bevinding.** Vier unittests openden een ECHTE databaseverbinding omdat bij
`CritiqueStore.store()` alleen `_persist_to_db` was gemockt en niet `_refresh_mv`. Kosten: 56,8s
per test, ~228s samen. Het pad is nagemeten en staat vast: `DatabaseManager.initialize()`
(`src/core/database/database.py:213-302`) doet vijf pogingen met een `asyncio.timeout(10)` en 2s
ertussen -- 5 * (10 + 2) is precies die 57 seconden.

Die vier tests zijn destijds per stuk gerepareerd (beide methodes worden nu gemockt). Wat NOOIT is
gebouwd, en waarom de rij open bleef staan, is de STRUCTURELE borging. Gemeten 2026-08-31:
`tests/unit/conftest.py` BESTOND niet -- niet in de worktree en niet op `origin/develop` -- en geen
enkele fixture in de conftest-keten hield een echte verbinding tegen. Een vijfde test met hetzelfde
patroon zou vandaag opnieuw 57 seconden kosten zonder dat iets het meldt. Dit bestand is die
borging; `tests/unit/conftest.py` hangt hem alleen op.

Hier gebundeld en niet in de conftest zelf, om dezelfde reden als
`tests/fixtures/agent_governance.py`: zo kunnen de tests die deze guard bewaken de exceptie en de
uitzonderingslijst gewoon IMPORTEREN. `tests/unit` is geen package (geen `__init__.py`), dus
`tests.unit.conftest` is niet importeerbaar; `tests.fixtures.*` wel.

**Wat het oppervlak van deze fixtures is.** In dit project is een autouse-fixture die uitzet wat
een andere test meet al eens 1538 tests lang onopgemerkt gebleven, dus expliciet: hieronder worden
precies DRIE namen gepatcht, alle drie in de `socket`-module -- `socket.socket.connect`,
`socket.socket.connect_ex` en `socket.socketpair`. Er wordt GEEN `src.*`-code gepatcht, geen
`get_db_session`, geen engine-fabriek en geen driver-module. Dat is een bewuste keuze:
`tests/fixtures/agent_governance.py` documenteert dat `hitl_ticket_repository` juist NIET autouse
kon zijn omdat het patchen van de brede infrastructuurfunctie `get_db_session` een test brak die
met `is` tegen de echte functie vergeleek. De socket-laag heeft dat probleem niet, en hij ligt
tegelijk LAGER dan elke driver -- asyncpg, psycopg, redis en httpx zijn zo in een keer gedekt.

**Wat hij vandaag WEL en NIET tegenhoudt.** Geblokkeerd is elke uitgaande verbinding behalve naar
de poorten in `POORTEN_MET_GEDATEERDE_UITZONDERING` (6379, 6380, 443). Het OP-18-pad -- PostgreSQL
op 5455/5432 -- valt daar met opzet buiten en wordt dus onverminderd betrapt, net als elke nieuwe
bestemming. De drie uitzonderingen zijn geen goedkeuring maar drie APARTE, grotere bevindingen die
bij het meten aan het licht kwamen: OP-175 (Redis 6380, 32 connects), OP-176 (Google 443, 33
connects, echte Gemini-API) en OP-177 (Redis 6379, 19 connects). Ze staan met hun gemeten aantallen
en vindplaats bij die constante.

**Drie ontwerpkeuzes, alle drie gemeten en niet beredeneerd.**

1. *De blokkade staat alleen AAN tijdens de test zelf, niet tijdens collectie.* Twee modules
   bepalen hun `pytestmark = pytest.mark.skipif(...)` met een echte `connect_ex`-probe naar Redis
   op moduleniveau, dus TIJDENS collectie:
   `tests/unit/core/database/test_the_redis_pool_survives_a_new_event_loop.py:46-48` en
   `tests/unit/core/governance/test_the_redis_limiter_survives_a_new_event_loop.py:31-33`. Zou de
   blokkade daar al aan staan, dan zou de probe "Redis onbereikbaar" concluderen en zouden die
   modules STIL overslaan in plaats van te draaien. Vandaar: installeren in een session-fixture
   (die pas na de collectie loopt), en per test scherpstellen.

2. *`socket.socketpair()` is uitgezonderd, want asyncio kan zonder niet bestaan.* Op Windows is
   `socketpair` geemuleerd via `_fallback_socketpair()` (`Lib/socket.py:623`), dat een ECHTE
   loopback-`connect()` doet, en `SelectorEventLoop._make_self_pipe()` roept dat aan bij het
   AANMAKEN van elke event loop. Zonder deze uitzondering gemeten:

       File "asyncio/selector_events.py", line 120, in _make_self_pipe
         self._ssock, self._csock = socket.socketpair()
       File "socket.py", line 623, in _fallback_socketpair
         csock.connect((addr, port))
       Geblokkeerd: geblokkeerd naar ('127.0.0.1', 57106)

   Gevolg was een half gebouwde loop en daarna `AttributeError: '_WindowsSelectorEventLoop' object
   has no attribute '_ssock'`. Elke async test zou omvallen. Een blanket-uitzondering voor loopback
   is GEEN alternatief: het OP-18-pad verbindt zelf naar `localhost:5455`, dus dan bewaakt de guard
   niets meer.

3. *De exceptie erft van `BaseException`, met opzet niet van `Exception`.* De reden dat OP-18 57
   seconden kostte in plaats van direct te falen, is dat elke laag op dat pad breed vangt:
   `initialize()` heeft `except Exception` met vijf retries (`database.py:294-303`), en
   `CritiqueStore._persist_to_db` en `_refresh_mv` hebben er elk ook een (`critique_store.py:252`,
   `:219`). Een `Exception`-subklasse wordt daar opgeslokt en opnieuw geprobeerd; de test blijft
   dan langzaam en de melding komt nooit boven. `BaseException` gaat door die handlers heen, dus de
   test faalt DIRECT met de uitleg uit `melding()`.
"""

import socket
import threading
from collections.abc import Iterator
from typing import Any

import pytest

MARKER_ECHTE_VERBINDING = "echte_netwerkverbinding_toegestaan"

# De echte functies, vastgelegd bij import -- dus voor enige patch.
_ECHTE_CONNECT = socket.socket.connect
_ECHTE_CONNECT_EX = socket.socket.connect_ex
_ECHTE_SOCKETPAIR = socket.socketpair

# Fixtures die BEDOELD zijn om een echte PostgreSQL te raken. Ze hangen alle zes aan
# `postgres_engine`, dat zichzelf netjes overslaat als de database er niet is -- maar met
# `except Exception` (`tests/fixtures/database.py:344-346`), en daar komt een `BaseException` niet
# in. Zonder deze uitzondering zou `tests/unit/test_neo_account_lockout_postgres.py` van SKIPPED
# naar ERROR gaan (gemeten, zie het rapport bij deze commit).
#
# Ze staan NIET in een enkel bestand: `postgres_engine`/`postgres_session` in `database.py`,
# `postgres_test_client` in `api.py`, `postgres_user_factory`/`postgres_test_user` in `auth.py`,
# `postgres_test_tenant` in `tenant.py`. Daarom scant
# `test_de_fixtureuitzondering_is_niet_verouderd` de hele map en niet een bestand -- een eerdere
# versie keek alleen in `database.py` en meldde vier bestaande fixtures als verouderd.
#
# Dezelfde namen staan in `tests/conftest.py:125`, daar voor een auto-skip-hook; hier alleen om te
# bepalen of de blokkade voor deze test aan mag. Dit repareert die hook NIET (dat is OP-44).
FIXTURES_DIE_ECHT_MOGEN_VERBINDEN = frozenset(
    [
        "postgres_engine",
        "postgres_session",
        "postgres_test_client",
        "postgres_test_user",
        "postgres_user_factory",
        "postgres_test_tenant",
    ]
)

# Gedateerde uitzonderingslijst (2026-08-31), patroon uit `.claude/rules/quality-gates.md`:
# een GROENE guard met een reden PER regel, in plaats van een rode test die de hele repo stillegt.
#
# **Waarom deze lijst bestaat.** De eerste versie blokkeerde ELKE uitgaande verbinding. Gemeten op
# de volledige `tests/unit` (`-n 4`): dat maakte 77 tests rood die in de baseline groen waren -- 68
# daarvan rechtstreeks op deze guard. Die tests waren niet stuk; ze deden AL een echte verbinding
# en kwamen weg met het stilzwijgend mislukken daarvan. Dat zijn drie eigen bevindingen, elk veel
# groter dan OP-18 zelf, en ze horen in een eigen ADR-rij met een eigen fix -- niet in deze commit,
# die over de borging van OP-18 gaat.
#
# Elke poort hieronder is dus een BEKEND gat, niet een goedkeuring, en heeft een eigen ADR-036-rij
# (OP-175, OP-176, OP-177). Nieuwe bestemmingen zijn wel geblokkeerd, en de PostgreSQL-poorten staan
# er met opzet niet in: het OP-18-pad verbindt naar 5455/5432 en wordt dus onverminderd betrapt.
# Bewaakt door `test_de_getolereerde_poorten_bevatten_geen_databasepoort` (geen databasepoort erin)
# en `test_elke_getolereerde_poort_heeft_een_gemeten_reden` (geen kale set).
#
# Alle aantallen zijn GEMETEN op een volledige `tests/unit -n 4`-run op 2026-08-31, niet geschat.
# De vindplaats staat er als bestand:regel bij, zodat een lezer later niet opnieuw hoeft te meten.
POORTEN_MET_GEDATEERDE_UITZONDERING: dict[int, str] = {
    6380: (
        "OP-175. 32 connects gemeten 2026-08-31. De OORSPRONKELIJK genoemde route is op "
        "2026-09-11 GEFIXED: `tests/unit/api/test_onboarding_router.py` en "
        "`tests/unit/api/test_template_router.py` overriden nu `require_company_layer_enabled` "
        "expliciet, want `router.dependencies = []` verwijdert een router-level `Depends()` "
        "niet retroactief (die is op decoratortijd ingebakken). "
        "DE POORT BLIJFT TOCH GETOLEREERD, en dat is een gemeten correctie op een te vroege "
        "sluiting. Het verwijderen van deze sleutel maakte de volledige poort rood. "
        "VOLLEDIG GEMETEN 2026-09-11 in een schone worktree (`tests/unit tests/architecture "
        "tests/core tests/contracts -n 4`, met de sleutel eruit): 30 failed + 9 errors over "
        "VEERTIEN bestanden -- geen van alle heeft iets met de company-layer te maken. "
        "Per bestand, aantal items: test_sp_g02_cva_e2e 8, test_sp_g04_focus_builder_workflow_"
        "generate 5, copilot/api/test_turn_endpoint 5, test_rbac_service_coverage 4, "
        "test_ai_features 4, copilot/api/test_ws_hardening 3, test_neo_auth_endpoints 2, "
        "copilot/api/test_chat_websocket 2, en elk 1 in test_sp_g03_copilot_ws, "
        "test_sp_e01_password_reset_email, test_bm25_service_extra, core/test_health_endpoints, "
        "core/test_event_consumer en caching/test_cache_tenant_isolation. "
        "DAT IS DE WERKLIJST VAN OP-175: elk van die bestanden opent een echte Redis en hoort "
        "het verbindende pad te mocken. Twee zijn er al gedaan en dat is het bewijs dat het kan: "
        "commit 7a2e7329 mockte `dsar_service._clear_copilot_sessions` (via `get_redis()`) voor "
        "`tests/unit/governance/test_dsar_service_unit.py` en `test_gdpr_user_behavior.py`, en "
        "die zes staan sindsdien niet meer in de lijst hierboven. "
        "Een zevende geval was WEL legitiem en is met de juiste marker opgelost: "
        "`tests/unit/core/database/test_the_redis_pool_survives_a_new_event_loop.py` verbindt "
        "doelbewust echt (het test pool/event-loop-gedrag) en draagt nu "
        "`@pytest.mark.echte_netwerkverbinding_toegestaan`."
    ),
    6379: (
        "OP-177. 19 connects gemeten, zelfde vorm als OP-175 maar via een andere route "
        "(`starlette/routing.py:364` -> FastAPI-route i.p.v. de dependency). Deze poort staat "
        "lokaal WEL open, dus die tests praten met een ECHTE Redis en zijn afhankelijk van de "
        "staat daarvan."
    ),
    443: (
        "OP-176, de gevaarlijkste van de drie. 33 connects gemeten naar Google "
        "(2001:4860:4844:400:: en 2001:4860:4840:400::) op 2026-08-31, via "
        "`google.genai._api_client:1388` -> `httpx/_client.py:825` -> "
        "`httpcore/_backends/sync.py:208 connect_tcp`. "
        "EEN VAN TWEE GEIDENTIFICEERDE OORZAKEN IS GEFIXED 2026-09-11: "
        "`tests/unit/agents/test_focus_builder_chat_agent.py::"
        "test_explain_node_llm_returns_low_confidence_on_error` en "
        "`test_call_intake_llm_falls_back_to_all_none_on_error` maakten een echte Gemini-aanroep "
        "doordat een lokale re-import van `WorkflowGeneratorAgent` in "
        "`focus_builder_chat_agent.py` de bestaande testpatch omzeilde -- beide tests bewijzen nu "
        "met `mock_gen.assert_called_once()` dat de mock daadwerkelijk wordt geraakt. Poort 443 "
        "blijft in deze lijst: het oorspronkelijke aantal (33) is niet aan een enkele aanroeper "
        "toe te schrijven en een volledige `tests/unit -n 4`-hermeting met verbindingslogging om "
        "de resterende bron(nen) te bevestigen is niet gedaan in deze wijziging."
    ),
}

# `aan` en `nodeid` zijn procesbreed: een verbinding kan ook op een worker-thread worden geopend
# (een sync driver in een executor) en moet daar net zo goed betrapt worden. De bypass is
# THREAD-LOCAL, zodat de socketpair-uitzondering van thread A de blokkade voor thread B niet
# openzet.
_blokkade: dict[str, Any] = {"aan": False, "nodeid": ""}
_bypass = threading.local()


class EchteVerbindingInUnitTest(BaseException):
    """Een unittest probeerde een echte TCP-verbinding te openen (ADR-036 OP-18).

    Erft van `BaseException` en niet van `Exception`; de reden staat in de moduledocstring onder
    ontwerpkeuze 3.
    """


def melding(nodeid: str, adres: object) -> str:
    """Bouw de foutmelding. Noemt de test, het adres, en wat de lezer moet DOEN."""
    return (
        f"Deze unittest probeerde een ECHTE netwerkverbinding te openen naar {adres!r}.\n"
        f"Test: {nodeid}\n"
        "In tests/unit is dat geblokkeerd (ADR-036 OP-18). Een unittest die echt verbindt is "
        "afhankelijk van een draaiende database en kost 57 seconden aan retry-backoff: "
        "DatabaseManager.initialize() doet vijf pogingen van 10 seconden.\n"
        "Wat je moet doen: mock het pad dat verbindt. Let op dat een aanroep MEER DAN EEN "
        "databasepad kan hebben -- bij CritiqueStore.store() zijn dat _persist_to_db EN "
        "_refresh_mv, en alleen de eerste mocken was precies de OP-18-bug.\n"
        "Hoort deze test wel echt te verbinden? Zet @pytest.mark."
        f"{MARKER_ECHTE_VERBINDING} erop en schrijf in de docstring waarom."
    )


def _poort_van(adres: Any) -> int | None:
    """Haal de doelpoort uit een socket-adres, of None als die er niet in zit.

    IPv4 geeft `(host, poort)`, IPv6 `(host, poort, flowinfo, scopeid)`, en een AF_UNIX-socket
    geeft een string. Alleen een echte int-poort telt.
    """
    if isinstance(adres, tuple) and len(adres) >= 2 and isinstance(adres[1], int):
        return adres[1]
    return None


def _geldt_de_blokkade(adres: Any) -> bool:
    """True als de blokkade nu geldt voor deze thread EN dit adres."""
    if not bool(_blokkade["aan"]) or getattr(_bypass, "actief", 0):
        return False
    return _poort_van(adres) not in POORTEN_MET_GEDATEERDE_UITZONDERING


def _connect_met_blokkade(zelf: Any, adres: Any, *args: Any, **kwargs: Any) -> Any:
    if _geldt_de_blokkade(adres):
        raise EchteVerbindingInUnitTest(melding(str(_blokkade["nodeid"]), adres))
    return _ECHTE_CONNECT(zelf, adres, *args, **kwargs)


def _connect_ex_met_blokkade(zelf: Any, adres: Any, *args: Any, **kwargs: Any) -> Any:
    if _geldt_de_blokkade(adres):
        raise EchteVerbindingInUnitTest(melding(str(_blokkade["nodeid"]), adres))
    return _ECHTE_CONNECT_EX(zelf, adres, *args, **kwargs)


def _socketpair_met_bypass(*args: Any, **kwargs: Any) -> Any:
    """Laat `socket.socketpair()` door de blokkade heen -- zie ontwerpkeuze 2.

    Alleen voor de duur van deze aanroep en alleen voor deze thread, zodat het gat zo klein is als
    het kan.
    """
    _bypass.actief = getattr(_bypass, "actief", 0) + 1
    try:
        return _ECHTE_SOCKETPAIR(*args, **kwargs)
    finally:
        _bypass.actief -= 1


def registreer_marker(config: pytest.Config) -> None:
    """Registreer de opt-out-marker; `addopts` bevat `--strict-markers`."""
    config.addinivalue_line(
        "markers",
        f"{MARKER_ECHTE_VERBINDING}: unittest mag een echte netwerkverbinding openen "
        "(ADR-036 OP-18; reden verplicht in de docstring)",
    )


def reden_om_echt_te_mogen_verbinden(node: pytest.Item) -> str:
    """Geef de reden waarom deze test mag verbinden, of een leegte als hij dat niet mag.

    Twee uitzonderingen, beide gemeten en niet bedacht:

    1. De expliciete marker. Vandaag draagt precies een test hem:
       `tests/unit/test_ssl_tls.py::TestCertificateValidation::test_certificate_expiry_check`
       doet een echte `socket.create_connection((DOMAIN, 443))` en vangt daarna alleen
       `(socket.timeout, socket.gaierror, ssl.SSLError, ConnectionRefusedError)` om zichzelf over
       te slaan. Zonder marker gaat hij op deze guard ROOD in plaats van SKIPPED -- gemeten:
       `EchteVerbindingInUnitTest ... naar ('::1', 443, 0, 0)`.
    2. Een test die een van de PostgreSQL-fixtures opvraagt -- zie
       `FIXTURES_DIE_ECHT_MOGEN_VERBINDEN` hierboven.

    Bewust GEEN gedateerde padenlijst met staleness-test voor de marker (het patroon uit
    `.claude/rules/quality-gates.md`): een marker staat op de test zelf en verdwijnt mee als die
    test verdwijnt, dus hij kan niet dichtrotten zoals een lijst met bestandspaden. De
    fixture-namen zijn wel zo'n lijst, en die wordt wel bewaakt --
    `test_de_fixtureuitzondering_is_niet_verouderd`.
    """
    if node.get_closest_marker(MARKER_ECHTE_VERBINDING) is not None:
        return f"marker @pytest.mark.{MARKER_ECHTE_VERBINDING}"
    gevraagd = FIXTURES_DIE_ECHT_MOGEN_VERBINDEN.intersection(getattr(node, "fixturenames", []))
    if gevraagd:
        return f"vraagt PostgreSQL-fixture(s): {', '.join(sorted(gevraagd))}"
    return ""


@pytest.fixture(scope="session", autouse=True)
def installeer_verbindingsblokkade() -> Iterator[None]:
    """Hang de blokkade in de socket-laag. Scherpstellen doet `blokkeer_echte_verbindingen`.

    Session-scope en niet op moduleniveau, zodat de patch pas NA de collectie hangt -- zie
    ontwerpkeuze 1 in de moduledocstring.
    """
    socket.socket.connect = _connect_met_blokkade  # type: ignore[method-assign]
    socket.socket.connect_ex = _connect_ex_met_blokkade  # type: ignore[method-assign]
    socket.socketpair = _socketpair_met_bypass  # type: ignore[assignment]
    try:
        yield
    finally:
        # `connect`/`connect_ex` staan niet in `socket.socket.__dict__` -- ze komen van
        # `_socket.socket` (nagemeten: beide False). Teruggeven doe je dus met `delattr`, niet met
        # een setattr naar de overgeerfde functie; anders blijft er een klasse-attribuut achter
        # dat er eerst niet was.
        for naam in ("connect", "connect_ex"):
            if naam in socket.socket.__dict__:
                delattr(socket.socket, naam)
        socket.socketpair = _ECHTE_SOCKETPAIR  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def blokkeer_echte_verbindingen(request: pytest.FixtureRequest) -> Iterator[None]:
    """Zet de blokkade aan voor deze ene test, tenzij hij een uitzondering heeft.

    **Mutatie-bewijs (beide richtingen, `.claude/rules/quality-gates.md`).** De guard bewaakt een
    expliciet benoemde verzameling van DRIE namen, en er is een mutatieregel per naam:

      - `socket.socket.connect` -> `test_een_uitgaande_tcp_verbinding_wordt_geblokkeerd` en
        `test_de_databaseroute_faalt_direct_in_plaats_van_na_57_seconden`;
      - `socket.socket.connect_ex` -> `test_een_connect_ex_wordt_ook_geblokkeerd`;
      - `socket.socketpair` -> `test_socketpair_blijft_werken_want_asyncio_heeft_hem_nodig` (die
        muteert de andere kant op: hij faalt als de uitzondering VERDWIJNT).

    Richting (a), betrapt wat hij moet betrappen: met `tests/unit/conftest.py` weggehaald zijn
    `test_een_uitgaande_tcp_verbinding_wordt_geblokkeerd`,
    `test_een_connect_ex_wordt_ook_geblokkeerd`, `test_de_asyncio_route_wordt_ook_geblokkeerd` en
    `test_de_databaseroute_faalt_direct_in_plaats_van_na_57_seconden` alle vier ROOD. Dat is het
    ROOD-bewijs van OP-18.

    Richting (b), laat door wat legitiem is: een correct gemockte databaseroute blijft groen EN
    snel (`test_een_correct_gemockte_databaseroute_blijft_groen`), een socket aanmaken/binden/
    luisteren mag nog (`test_een_socket_aanmaken_en_binden_mag_nog`), `socket.socketpair()` blijft
    werken zodat async tests blijven bestaan, en de opt-out werkt
    (`test_de_opt_out_marker_staat_een_echte_verbinding_toe`).
    """
    if reden_om_echt_te_mogen_verbinden(request.node):
        yield
        return

    vorige_aan = _blokkade["aan"]
    vorige_nodeid = _blokkade["nodeid"]
    _blokkade["aan"] = True
    _blokkade["nodeid"] = request.node.nodeid
    try:
        yield
    finally:
        _blokkade["aan"] = vorige_aan
        _blokkade["nodeid"] = vorige_nodeid
