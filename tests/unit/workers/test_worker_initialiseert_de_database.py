"""De worker moet zijn database initialiseren, anders faalt elke DB-actor (ADR-036 OP-136).

**Hoe dit gevonden is.** Door de stack echt op te starten, niet door een test. In de
dead-letter queue van de draaiende worker lag `cleanup_expired_hitl_tickets`, drie keer gefaald:

    RuntimeError: Database not initialized. Call initialize_database() first.

`get_db_session()` (`src/core/database/session.py:27`) weigert zolang
`db_manager.async_session_maker` leeg is. `initialize_database()` wordt aangeroepen vanuit
`src/core/api/main.py` -- de API -- maar in GEEN van de worker-entrypoints. De worker bouwt in
`workflow_worker.py` wel een eigen engine, maar die staat los van `db_manager`.

Gevolg: elke actor die `get_db_session()` gebruikt faalt. Dat zijn er negen alleen al in
`src/workers/actors.py`, en het raakt onder meer `gdpr_purge` (AVG-verwijderplicht),
`retention_cleanup`, `audit_tasks` en de ketenverificatie uit OP-109. Ze falen naar een
dead-letter queue die niemand leest, dus er is geen signaal.

Dit is NIET lokaal-only: dezelfde code draait in de Azure-worker.

**Waarom een subprocess.** De assertie kijkt naar de globale `db_manager`. Die in dit
testproces initialiseren zou elke latere ORM-test in dezelfde xdist-worker beinvloeden --
precies OP-20. Een subprocess houdt het effect binnen zijn eigen interpreter.

**Waarom de pool geleegd wordt.** `db_manager.initialize()` doet een `SELECT 1` en die
verbinding belandt in de pool. Wordt de initialisatie in een tijdelijke event loop gedaan, dan
is die verbinding daarna aan een gesloten loop gebonden. De middleware disposet daarom direct
na de test; de actors maken hun verbindingen in hun eigen loop.

**Mutatietest (2026-08-13, beide richtingen):**

1. De `add_middleware(DatabaseInitMiddleware())`-regel uit `get_redis_broker()` halen -> ROOD
   (de hook draait dan nooit). De hele klasse verwijderen -> ROOD op de import.
2. De andere kant: `test_de_hook_ruimt_de_pool_op` faalt zodra de `dispose()` wegvalt, dus
   "initialiseer maar laat de verbinding hangen" is geen geldige oplossing.

**Waarom die derde test de aanroep telt in plaats van het gevolg.** Gemeten: met de dispose
weggehaald bleven de eerste twee tests GROEN. In-memory SQLite gebruikt een StaticPool die
dezelfde verbinding hergebruikt en zich niets aantrekt van event loops, dus daar is het gevolg
per constructie onzichtbaar; alleen asyncpg laat het verschil zien en dat vraagt een echte
Postgres. Een guard die niet rood kan worden bewaakt niets, dus telt de derde test de aanroep.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

_ALLES_IN_EEN = """
import asyncio, os, sys

os.environ.pop("TESTING", None)
# Zonder TESTING eist `redis_url()` een echte REDIS_URL (geen stille terugval). In een volledige testronde
# lekt die uit een eerdere test; los gedraaid (en in de pre-commit-selectie) ontbrak hij en faalde de test
# in een schone boom (gemeten 2026-10-24). Het script bouwt alleen een broker op, het maakt geen verbinding.
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# Tel de dispose-aanroepen VOOR de hook draait.
_teller = {"n": 0}
_origineel = AsyncEngine.dispose

async def _geteld(self, close=True):
    _teller["n"] += 1
    return await _origineel(self, close)

AsyncEngine.dispose = _geteld

from src.workers.workflow_worker import DatabaseInitMiddleware
from src.core.database.database import db_manager
from src.core.database.session import get_db_session

DatabaseInitMiddleware().after_process_boot(None)

print("SESSION_MAKER", db_manager.async_session_maker is not None)
print("DISPOSE_AANROEPEN", _teller["n"])

# Tweede, LOSSE event loop -- net als een actor die na de boot-hook draait.
async def _gebruik():
    async with get_db_session() as sessie:
        (await sessie.execute(text("SELECT 1"))).scalar_one()

try:
    asyncio.run(_gebruik())
    print("SESSIE_IN_NIEUWE_LOOP ok")
except Exception as exc:
    print("SESSIE_IN_NIEUWE_LOOP mislukt:", type(exc).__name__, exc)

# HARD afsluiten, anders hangt dit proces voor altijd (ADR-036 OP-132).
# `get_db_session()` hierboven opent een aiosqlite-verbinding, en aiosqlite draait die op een
# NON-DAEMON thread (`aiosqlite/core.py:_connection_worker_thread`). Bij het afsluiten wacht
# CPython in `threading._shutdown` op zulke threads. Alles is op dit punt al geprint, maar
# `subprocess.run` wacht op het EINDE VAN HET PROCES en niet op de uitvoer -- dus liep dit script
# op CI twee keer in de timeout (180s en 600s) terwijl het werk al klaar was.
# `os._exit` slaat de opruiming over; dat mag hier, want dit is een wegwerp-probeproces.
sys.stdout.flush()
sys.stderr.flush()
os._exit(0)
"""


def _draai(code: str) -> subprocess.CompletedProcess[str]:
    """Draai een fragment in een VERSE interpreter.

    De grens staat op 600s. Lokaal duurt het fragment ~8s; de ruimte is er voor een koude
    CI-runner, waar `src.core.database` en zijn modellaag zonder warme schijfcache geladen moeten
    worden.

    **Waarom die grens niet het probleem was.** Dit script liep op CI twee keer in de timeout,
    eerst op 180s en daarna op 600s. Ik heb de eerste keer aan de bound gesleuteld en dat was de
    verkeerde conclusie: 600 seconden voor werk dat er lokaal 8 kost is geen traagheid maar een
    HANG. De oorzaak staat onderaan het script -- `get_db_session()` opent een aiosqlite-verbinding
    op een non-daemon thread, en `subprocess.run` wacht op het einde van het PROCES, niet op de
    uitvoer. Alles was allang geprint. Vandaar de `os._exit(0)` daar.

    **Waar de kosten NIET zitten.** Ik heb `DatabaseInitMiddleware` eerst naar een eigen lichte
    module verplaatst in de veronderstelling dat `workflow_worker` (met de workflow-engine
    eraan) de dure import was. Gemeten in beide volgordes: `import src.workers.workflow_worker`
    5,3-8,7s tegen `import src.workers.database_init` 7,6s -- geen verschil buiten de ruis. Die
    verplaatsing is daarom teruggedraaid; de kosten zitten in `src.core.database`, dat dit script
    hoe dan ook nodig heeft. Wat wel hielp: van drie subprocessen naar een (26s -> 8s lokaal).
    """
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=600,
    )


@pytest.fixture(scope="module")
def uitvoer() -> subprocess.CompletedProcess[str]:
    """EEN subprocess voor alle drie de asserties.

    Elk subprocess importeert `src.core.database` en dat trekt de modellaag mee. Drie tests maal
    die kosten was verspilling; twee losse fragmenten ook. Alles staat nu in een script dat de
    drie markeringen achter elkaar print.
    """
    return _draai(_ALLES_IN_EEN)


@pytest.mark.timeout(1300)
class TestDeWorkerInitialiseertZijnDatabase:
    def test_de_hook_zet_een_session_maker(self, uitvoer) -> None:
        """Zonder dit weigert `get_db_session()` en faalt elke DB-actor in de worker."""
        r = uitvoer

        assert "SESSION_MAKER True" in r.stdout, (
            "De worker heeft na het booten van zijn proces geen session maker. Elke actor die "
            "`get_db_session()` gebruikt faalt dan met 'Database not initialized' en verdwijnt "
            "na drie pogingen in de dead-letter queue -- zonder dat iets erover meldt.\n\n"
            f"stdout:\n{r.stdout}\n\nstderr:\n{r.stderr[-1500:]}"
        )

    def test_een_sessie_werkt_daarna_in_een_nieuwe_event_loop(self, uitvoer) -> None:
        """De andere richting: initialiseren alleen is niet genoeg, het moet ook bruikbaar zijn.

        `db_manager.initialize()` doet een `SELECT 1`, en die verbinding wordt gemaakt in de
        tijdelijke event loop van de boot-hook. Blijft hij in de pool staan, dan krijgt de eerste
        actor een verbinding die bij een gesloten loop hoort. Zonder deze helft zou
        "initialiseer en laat de verbinding hangen" slagen op de test hierboven.

        Deze test toetst de EIGENSCHAP en niet de interne opbouw van de pool. Een eerdere versie
        keek naar `pool.checkedin()` en viel op CI om met
        `AttributeError: 'StaticPool' object has no attribute 'checkedin'` -- in-memory SQLite
        gebruikt een StaticPool. Dat was een test die een implementatiedetail toetste in plaats
        van het gedrag; lokaal groen, op CI rood.
        """
        r = uitvoer

        assert "SESSIE_IN_NIEUWE_LOOP ok" in r.stdout, (
            "Een sessie openen in een NIEUWE event loop lukt niet na de boot-hook. Dat is precies "
            "wat een actor doet, dus in deze toestand faalt de eerste taak alsnog.\n\n"
            f"stdout:\n{r.stdout}\n\nstderr:\n{r.stderr[-1500:]}"
        )

    def test_de_hook_ruimt_de_pool_op(self, uitvoer) -> None:
        """Toetst de `dispose()` DIRECT, want geen enkele SQLite-test kan hem missen.

        Gemeten 2026-08-13: met de dispose weggehaald bleven de twee tests hierboven allebei
        GROEN. In-memory SQLite gebruikt een StaticPool die dezelfde verbinding hergebruikt en
        zich niets aantrekt van event loops -- het gedrag dat de dispose beschermt is daar
        onzichtbaar. Alleen asyncpg laat het verschil zien, en dat vraagt een echte Postgres.

        Vandaar deze derde test: hij telt de aanroep in plaats van het gevolg. Minder mooi, maar
        hij gaat WEL rood als iemand de regel weghaalt -- en dat is het enige wat een guard moet
        kunnen. De reden dat de dispose er hoort te staan blijft de docstring van
        `DatabaseInitMiddleware`.

        Mutatietest (2026-08-13): `await engine.dispose()` vervangen door `pass` -> ROOD op deze
        test, groen op de andere twee. Dat verschil is precies waarom hij bestaat.
        """
        r = uitvoer

        assert "DISPOSE_AANROEPEN 1" in r.stdout, (
            "De boot-hook disposet de engine niet. De verbinding uit de `SELECT 1` van "
            "`db_manager.initialize()` blijft dan in de pool zitten, gebonden aan de tijdelijke "
            "event loop van de hook -- op Postgres krijgt de eerste actor daardoor een "
            "onbruikbare verbinding.\n\n"
            f"stdout:\n{r.stdout}\n\nstderr:\n{r.stderr[-1500:]}"
        )
