"""De ene Redis-wachtrij van de workflow-, onderhouds- en achtergrondtaken (ADR-036 OP-13, brief 2026-10-21).

**Waarom dit bestaat.** `src/workers/workflow_worker.py` zette bij het IMPORTEREN een `StubBroker` als procesbrede
broker en wisselde hem pas om als iemand `get_redis_broker()` aanriep. Elke actor die vooraf met `@dramatiq.actor`
was gedecoreerd, bond aan die stub. Een `.send()` voor die wissel (de API-processen deden dat nooit) landde in een
geheugenwachtrij die niemand uitleest, zonder fout. Welke actor waar landde hing af van importvolgorde.

**Wat er nu is.** Een broker, `workflow_broker`, een echte `RedisBroker`. Hij maakt bij het importeren GEEN
verbinding (dramatiq verbindt pas bij het eerste bericht), dus importeren blijft goedkoop en veilig in tests.
Actors binden er EXPLICIET aan via `workflow_actor`, net als de leerwerker en de bonlezer met hun eigen broker.
Er is geen `set_broker()` en geen `StubBroker` in `src/` (bewaakt door
`tests/architecture/test_geen_procesbrede_broker.py`). Tests krijgen een StubBroker via een fixture in
`tests/conftest.py`, niet via de productiecode.

**Geen stille val.** Is Redis niet bereikbaar, dan geeft `.send()` een `ConnectionError` (gemeten in
`tests/unit/workers/test_workflowtaak_landt_op_de_echte_wachtrij.py`). Wat een aanroeper daarmee doet is zijn zaak;
`src/workers/workflow_verzending.py` (ActivePieces dag 1) maakt er een FAILED-uitvoering, een dead letter en een 503 van.

**De werker.** `dramatiq src.workers.workflow_worker:redis_broker src.workers.actors` blijft werken: die module
geeft dezelfde `workflow_broker` terug onder de naam `redis_broker`.
"""

import asyncio
import os
from typing import TYPE_CHECKING, Any

# Initialize dramatiq imports to None to avoid possibly unbound variable warnings
RedisBroker: Any = None
AsyncIO: Any = None
Middleware: Any = object  # basisklasse-terugval als dramatiq ontbreekt (zie DatabaseInitMiddleware)  # TODO(TYPE): replace Any with concrete type
dramatiq_module: Any = None

_DRAMATIQ_AVAILABLE: bool = False
try:
    import dramatiq as _dramatiq_module
    from dramatiq.brokers.redis import RedisBroker as _RedisBroker
    from dramatiq.middleware import AsyncIO as _AsyncIO
    from dramatiq.middleware import Middleware as _Middleware

    dramatiq_module = _dramatiq_module
    RedisBroker = _RedisBroker
    AsyncIO = _AsyncIO
    Middleware = _Middleware
    _DRAMATIQ_AVAILABLE = True
except ImportError:
    if os.getenv("TESTING") != "1":
        raise ImportError(
            "dramatiq is required for workflow workers. Install with: pip install dramatiq[redis]"
        )

TESTING_MODE = os.getenv("TESTING") == "1"

#: Alleen voor tests zonder REDIS_URL: de broker bestaat dan wel, maar er wordt niets mee verbonden.
_TEST_REDIS_URL = "redis://127.0.0.1:6379/0"


def _sanitize_env_url(value: str | None) -> str:
    """Normalize env URL values to tolerate accidental inline comments in tests."""
    if not value:
        return ""
    return value.split(" #", 1)[0].strip()


class DatabaseInitMiddleware(Middleware):  # type: ignore[misc]
    """Initialiseer `db_manager` in elk workerproces (ADR-036 OP-136).

    Zonder dit weigert `get_db_session()` met "Database not initialized" en faalt ELKE actor die
    een databasesessie opent -- negen alleen al in `src/workers/actors.py`, waaronder
    `gdpr_purge` (AVG-verwijderplicht), `retention_cleanup`, `audit_tasks` en de
    ketenverificatie uit OP-109. Ze verdwijnen na drie pogingen in de dead-letter queue, zonder
    dat iets erover meldt. Zo is dit gevonden: niet door een test, maar door de stack op te
    starten en die wachtrij te lezen.

    De API roept `initialize_database()` aan in `src/core/api/main.py`; de worker deed dat
    nergens. De eigen engine hierboven in dit bestand staat los van `db_manager` en helpt die
    actors dus niet.

    **`after_process_boot` en niet bij import.** Deze hook draait NA de fork, in elk
    workerproces apart. Een engine die voor de fork wordt gemaakt deelt zijn connectiepool met
    alle kinderen, en dat is niet veilig.

    **Waarom de pool daarna leeg moet.** `db_manager.initialize()` doet een `SELECT 1` en die
    verbinding belandt in de pool. Hij is gemaakt in de tijdelijke event loop van `asyncio.run`
    hieronder, dus na afloop hoort hij bij een gesloten loop en is hij onbruikbaar. `dispose()`
    gooit hem weg; het session-maker-object blijft geldig en de actors maken hun verbindingen
    daarna in hun eigen loop. `tests/unit/workers/test_worker_initialiseert_de_database.py`
    bewaakt beide helften.
    """

    def after_process_boot(self, broker: object) -> None:  # noqa: ARG002
        from src.core.database.database import db_manager, initialize_database

        async def _initialiseer() -> None:
            await initialize_database()
            engine = db_manager.engine
            if engine is not None:
                await engine.dispose()

        asyncio.run(_initialiseer())


def redis_url() -> str:
    """De Redis-URL van de wachtrij; buiten tests een harde fout als hij ontbreekt (geen stille terugval)."""
    url = _sanitize_env_url(os.getenv("REDIS_URL"))
    if url:
        return url
    if TESTING_MODE:
        return _TEST_REDIS_URL
    raise RuntimeError(
        "CRITICAL: REDIS_URL environment variable is required. "
        "Set to a Redis connection string (e.g., redis://...)"
    )


def bouw_broker(url: str) -> "_RedisBrokerType":
    """Een echte RedisBroker met de middleware die elk workerproces nodig heeft.

    Maakt geen verbinding: dramatiq verbindt pas bij het eerste `enqueue` of bij het consumeren.
    """
    broker: "_RedisBrokerType" = RedisBroker(url=url)
    broker.add_middleware(AsyncIO())  # type: ignore[no-untyped-call]  # dramatiq mist stubs
    # ADR-036 OP-136: zonder deze middleware heeft geen enkel workerproces een
    # geinitialiseerde `db_manager` en faalt elke actor die `get_db_session()` opent.
    broker.add_middleware(DatabaseInitMiddleware())  # type: ignore[no-untyped-call]  # dramatiq mist stubs
    return broker


#: De broker waar elke actor van de workflow-, onderhouds- en achtergrondtaken aan bindt.
workflow_broker: "_RedisBrokerType | None" = (
    bouw_broker(redis_url()) if _DRAMATIQ_AVAILABLE else None
)


def _workflow_actor(fn: object = None, /, **opties: object) -> object:
    """`@dramatiq.actor` met de broker er EXPLICIET aan vast (zoals de leerwerker en de bonlezer).

    Te gebruiken als `@workflow_actor` of `@workflow_actor(queue_name=..., max_retries=...)`. Zonder dramatiq
    (alleen in tests) geeft dit de functie ongewijzigd terug.
    """
    if not _DRAMATIQ_AVAILABLE:
        return fn if fn is not None else (lambda f: f)
    if fn is not None:
        return dramatiq_module.actor(fn, broker=workflow_broker, **opties)
    return dramatiq_module.actor(broker=workflow_broker, **opties)


if TYPE_CHECKING:
    # Voor mypy en pyright IS dit `dramatiq.actor`: zijn overloads houden de gedecoreerde actors getypeerd
    # (anders "Untyped decorator makes function untyped" op elke actor). De `broker=` komt er op runtime bij.
    import dramatiq as _dramatiq_voor_typering
    from dramatiq.brokers.redis import RedisBroker as _RedisBrokerType

    workflow_actor = _dramatiq_voor_typering.actor
else:
    workflow_actor = _workflow_actor
