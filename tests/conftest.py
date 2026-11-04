"""
Pytest configuration and shared fixtures.

This file is automatically loaded by pytest and sets up global test configuration.
"""

import asyncio
import faulthandler
import os
import socket
import sys
import threading
import warnings
from itertools import count
from pathlib import Path
from types import SimpleNamespace
from collections.abc import Iterator
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

# RC-LOOP-1: Force SelectorEventLoop on Windows to avoid IocpProactor.close()
# hanging on socket cleanup (CPython issue #111604).  With ProactorEventLoop the
# _close_self_pipe() call blocks indefinitely when the Proactor cache is non-empty,
# causing pytest-timeout's thread-method interrupt to fire during teardown rather
# than inside the test body.  SelectorEventLoop avoids the issue entirely and is
# sufficient for all unit tests (no subprocess or UDP edge cases).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import anyio
import pytest
import pytest_asyncio

# Remove loguru's default stderr sink early -- before any test imports.
# With -n auto (pytest-xdist), workers redirect/close sys.stderr between tests.
# Loguru holding a reference to the captured stream causes:
#   ValueError: I/O operation on closed file
# Removing id=0 (the default <stderr> sink) silences it completely in workers.
try:
    from loguru import logger as _loguru_logger

    _loguru_logger.remove(0)
except (ValueError, ImportError):
    pass  # Already removed or loguru not installed
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from respx import MockRouter

# Ensure the repository root is importable so `src.*` imports work in all pytest invocation modes.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Must be set before any src.* import -- prevents module-level side effects
# (validate_config_at_startup, singletons) from firing during pytest --collect-only.
# See AUDIT-COLL-01.
os.environ["TESTING"] = "1"

_TEST_JWT_SECRET = "pytest-jwt-secret-key-for-local-hooks-0123456789"
os.environ.setdefault("JWT_SECRET", _TEST_JWT_SECRET)
os.environ.setdefault("JWT_SECRET_KEY", _TEST_JWT_SECRET)

# Vaste hoofdsleutel ALLEEN voor de tests (brief 2026-10-23): zonder hem vallen tests die klantsleutels
# versleutelen los gedraaid om op `HoofdsleutelOntbreekt`. `setdefault`, zodat een echte sleutel uit de
# shell wint. Gegenereerd met `secrets.token_urlsafe(32)`; geen sleutel van enige omgeving, en sterk
# genoeg voor de eisen van `TenantSecretEncryption` (anders `HoofdsleutelTeZwak`).
_TEST_MASTER_ENCRYPTION_KEY = "w0PW8Vh4-UPi70LUTf0Gam8DD7Dc2PAo8x4YO-Y_eMQ"
os.environ.setdefault("MASTER_ENCRYPTION_KEY", _TEST_MASTER_ENCRYPTION_KEY)

# ADR-036 OP-27: `redaction._environment()` leest ENVIRONMENT direct uit os.environ en niet uit de
# settings-default "development" -- anders valt een proces waar de variabele vergeten is stil in de
# ontwikkelmodus, met per worker een andere digest. Gevolg voor de tests: zonder deze regel is de
# uitkomst afhankelijk van de shell waarin pytest draait (gemeten: HTTP 500 op
# test_execute_tool_success zonder de var, groen ermee). Hier vastzetten in plaats van in elke
# CI-workflow, zodat "de suite is groen" een uitspraak over de code is en niet over de shell.
#
# HIER en niet lager in dit bestand, om dezelfde reden als `TESTING` hierboven: alles wat het
# gedrag van een `src.*`-module bepaalt moet gezet zijn VOORDAT die module wordt geimporteerd.
# Ik had hem eerst na `from src.main import create_test_app` en na de bewuste
# `import src.core.api.cva_endpoints` gezet. Twee volledige suite-runs gaven daarna elk EEN
# willekeurige failure -- een andere per run, allemaal los groen. De twee runs ervoor waren
# volledig groen. Module-imports liepen dus in een andere configuratiestaat dan de tests erna.
# Een harde assignment en GEEN `setdefault` (gewijzigd 2026-08-04, ronde 5). Met `setdefault` wint
# een `ENVIRONMENT` uit de shell, en dan is "de suite is groen" alsnog een uitspraak over de shell.
# Concreet: met `ENVIRONMENT=production` in de omgeving eist `redaction.pseudonymisation_key()` een
# echte sleutel en weigert hij zowel de ephemere sleutel als de inhoud-opt-in, waardoor elke
# tooltest omvalt. Dat faalt luid en is dus niet gevaarlijk, maar het is dezelfde klasse fout als de
# plaatsing hierboven -- de suite hoort niet van de shell af te hangen. Wie een test in een andere
# omgeving wil draaien, zet dat expliciet in de test.
os.environ["ENVIRONMENT"] = "test"

# En de inhoud-opt-in expliciet UIT (ADR-036 OP-27, ronde 5). `test` staat in
# `CONTENT_CAPTURE_ENVIRONMENTS`, dus met `TOOL_PAYLOAD_CAPTURE_CONTENT=1` in de shell of in een
# CI-job legt de HELE suite payloads onbewerkt vast. De redactietests vallen dan luid om -- maar de
# eigenschap "standaard uit" wordt dan door het harnas niet afgedwongen, en dat is precies wat de
# regel hierboven voor ENVIRONMENT wel doet. `pop` en niet op "0" zetten: de variabele hoort
# AFWEZIG te zijn, zodat een test die hem zelf zet met een `monkeypatch.setenv` een schone
# beginstand heeft.
os.environ.pop("TOOL_PAYLOAD_CAPTURE_CONTENT", None)

# DATABASE_URL hoort in het rijtje hierboven en stond er niet (ADR-036 OP-243).
#
# `UnifiedConfig` wordt via `_ConfigProxy` gebouwd bij het EERSTE attribuut-gebruik. De
# import hieronder van `src.main` veroorzaakt dat. Staat `DATABASE_URL` op dat moment niet
# in de omgeving, dan laadt pydantic de env-bestanden en wint `.env.local` -- waarna de
# waarde voor de hele testsessie vaststaat. `tests/integration/conftest.py` zet hem daarna,
# en dat is te laat: gemeten 2026-09-15 wees `os.environ["DATABASE_URL"]` naar poort 5455
# terwijl `config.database_url` naar 5435 wees, binnen dezelfde run.
#
# Een AL gezette waarde wordt gerespecteerd (Docker/CI-injectie), net als de guard in
# `src/core/env_loader.py` doet. Is er niets aangewezen, dan gebeurt hier niets: unittests
# hebben geen database nodig en mogen hier niet op omvallen.
# Eerst controleren dat de config nog NIET gebouwd is. Deze controle toetst de TOESTAND en
# niet een regelnummer: wie hierboven `config` aanraakt -- welke import dan ook, nu of over
# een jaar -- laat hem afgaan. Zie tests/fixtures/configvolgorde.py voor het waarom.
from tests.fixtures.configvolgorde import controleer_config_nog_niet_gebouwd  # noqa: E402

controleer_config_nog_niet_gebouwd(sys.modules)

_expliciete_testdatabase = os.environ.get("SANSKRITISETU_TEST_DATABASE_URL", "").strip()
if _expliciete_testdatabase and not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = _expliciete_testdatabase

from src.main import create_test_app

# Pre-load under the src.* key so all xdist workers have it in sys.modules before
# any test runs. Without this, tests on worker gw2 that import core.api (editable-
# install path, without src.) create a sys.modules entry with __name__='core.api'.
# When test_sp_type01_cva_endpoints_types.py then runs `import src.core.api.cva_endpoints`,
# Python finds src.core.api mapped to the core.api module object and raises
# ImportError: cannot import name 'cva_endpoints' from 'core.api'. Pre-loading here
# ensures `src.core.api.cva_endpoints` is resolved before any contaminating import.
import src.core.api.cva_endpoints  # noqa: E402, F401

# Check PostgreSQL availability once at collection time.
#
# Hier stond `int(os.getenv("TEST_PG_PORT", "5455"))`. Die terugval was een gok met een vast
# antwoord: wie er op 5455 antwoordde, bepaalde of `requires_postgres`-tests draaiden. Op
# 2026-09-14 was dat zes uur lang een vergeten act-servicecontainer (ADR-036 OP-243).
#
# Deze conftest geldt voor de HELE suite, ook voor unittests die geen database nodig hebben.
# De variabele is hier daarom NIET verplicht -- maar niet-opgegeven betekent "geen database",
# niet "probeer 5455". Dat is geen terugval: het is de eerlijke afwezigheid van een antwoord.
from urllib.parse import urlparse  # noqa: E402

from tests.fixtures.testdatabase import (  # noqa: E402
    TestdatabaseNietOpgegeven,
    testdatabase_poort,
    testdatabase_url,
)


def _postgres_reachable() -> bool:
    """Return True if the EXPLICITLY configured PostgreSQL is reachable."""
    try:
        host = urlparse(testdatabase_url()).hostname or "localhost"
        poort = testdatabase_poort()
    except TestdatabaseNietOpgegeven:
        return False
    try:
        with socket.create_connection((host, poort), timeout=1):
            return True
    except OSError:
        return False


_POSTGRES_AVAILABLE = _postgres_reachable()

requires_postgres = pytest.mark.skipif(
    not _POSTGRES_AVAILABLE,
    reason="Learning E2E requires PostgreSQL for transaction isolation",
)

# GEEN auto-skip-hook op fixturenaam of op de `requires_postgres`-marker (ADR-036 OP-44,
# gemeten 2026-08-31). Die hook heeft hier tot vandaag als DODE tweede definitie gestaan; bij het
# oplossen is hij VERWIJDERD in plaats van geactiveerd, om twee gemeten redenen:
#
# 1. Hij is overbodig. De 43 items die hij zou raken zijn HERMETEN op 2026-09-01 met een
#    telplugin die exact zijn selectie repliceert, over een volledige `pytest tests/
#    --collect-only` (18.247 gecollecteerd, 2 collectiefouten die ook op develop staan). De
#    eerste versie van dit blok noemde vier mappen die samen NUL van de 43 dekken --
#    `tests/integration/**` levert bij een dichte database geen items op (module-level skip) en
#    `tests/e2e/phase7/**` gebruikt een `skipif`, waarvan de markernaam `skipif` is en niet
#    `requires_postgres`. Dit is de gemeten samenstelling, per bestand:
#      13  tests/e2e/test_unified_learning_toolbroker.py          (via fixture)
#       9  tests/compliance/test_gdpr_compliance.py               (via fixture)
#       8  tests/integration_real/test_postgres_pgvector.py       (via marker)
#       6  tests/integration_real/test_end_to_end.py              (via marker)
#       5  tests/unit/test_neo_account_lockout_postgres.py        (via fixture)
#       2  tests/security/copilot/test_security_findings_regression.py (via fixture)
#    Samen 43: 29 via een `postgres_*`-fixturenaam, 14 via de `requires_postgres`-marker.
#    De guards die ze WEL al dekken:
#      - de 29 fixture-items      -> `postgres_engine` in tests/fixtures/database.py skipt
#                                    zichzelf op de echte TEST_DB_URL
#      - de 14 marker-items       -> de `postgres_available`-fixture in
#                                    tests/integration_real/conftest.py (poort 5435)
#    Activeren veranderde 0 van de 16.158 uitkomsten in tests/unit+architecture+core.
#
# 2. Hij zou verkeerd skippen. De hook keek naar TEST_PG_PORT (default 5455), terwijl
#    tests/integration_real op 5435 werkt. Gemeten met Postgres OP 5435 en 5455 dicht: alle 14
#    `requires_postgres`-tests daar werden geskipt met "PostgreSQL not reachable at
#    localhost:5455", terwijl hun database beschikbaar was. Een collectie-brede hook op een vaste
#    poort maakt de per-map guards juist onbetrouwbaar.
#
# `requires_postgres` HIERBOVEN (regel 120) blijft: dat is een pytest.mark.skipif die tests
# zelf opzetten.


def pytest_configure(config: pytest.Config) -> None:
    """Register pytest markers and xdist enum serialization."""
    from enum import Enum as PyEnum

    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )

    # Register custom serializer for Enum values in execnet (used by xdist)
    try:
        from execnet.gateway_base import _Serializer
        import threading

        original_save = _Serializer._save
        _xdist_depth = threading.local()

        def _custom_save(self: Any, obj: Any) -> None:
            """Custom serializer for xdist: handles Enums, MagicMock, and deep nesting.

            Root causes this guards against:
            1. Enum values -> convert to .value (original purpose)
            2. MagicMock / ORM objects in failure tracebacks -> DumpError from execnet
            3. Deep recursion on circular refs -> depth limit fallback
            All three fall back to repr() which is always a plain string execnet can handle.
            """
            if not hasattr(_xdist_depth, "n"):
                _xdist_depth.n = 0
            _xdist_depth.n += 1
            try:
                if isinstance(obj, PyEnum):
                    return original_save(self, obj.value)
                if _xdist_depth.n > 50:
                    try:
                        return original_save(self, repr(obj)[:200])
                    except Exception:
                        return original_save(self, f"<{type(obj).__name__}>")
                try:
                    return original_save(self, obj)
                except Exception:
                    # DumpError (MagicMock, ORM objects, etc.) or RecursionError
                    try:
                        return original_save(self, repr(obj)[:200])
                    except Exception:
                        return original_save(self, f"<{type(obj).__name__}>")
            finally:
                _xdist_depth.n -= 1

        _Serializer._save = _custom_save
    except (ImportError, AttributeError):
        pass


@pytest.fixture(autouse=True)
def enforce_testing_env(monkeypatch: pytest.MonkeyPatch):
    """Keep TESTING enabled even if imported modules mutate the environment."""
    monkeypatch.setenv("TESTING", "1")


@pytest.fixture(autouse=True)
def _noodstop_staat_voor_andere_tests_uit(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
):
    """De noodstop-controle leest de stand uit de database; die is er in de meeste tests niet.

    Elke deur (broker, Council, workflow, ...) roept `eis_klant_actief` aan, en die is
    FAIL-CLOSED: een stand die niet te lezen is weigert. Zonder deze stub zou elke test die een
    tool of een Council-besluit raakt weigeren op een databaseverbinding die hij nooit nodig had.
    Dit is de GRENS (de database) en niets anders: de rest van `eis_klant_actief` draait echt.

    Een test die de noodstop ZELF meet, markeert zich met `noodstop_echt` en krijgt dan geen stub
    (de lezer of de database is daar het onderwerp van de meting). Een nieuwe deur die de stand
    niet controleert wordt NIET door deze stub verborgen: `tests/architecture/
    test_elke_deur_controleert_de_noodstop.py` leest de broncode.
    """
    if request.node.get_closest_marker("noodstop_echt") is not None:
        yield
        return
    from src.core.noodstop import guard

    async def _klant_staat_niet_stil(tenant_id: int) -> bool:
        return False

    monkeypatch.setattr(guard, "_lees_stand", _klant_staat_niet_stil)
    yield


@pytest.fixture(autouse=True)
def taken_naar_een_stubbroker(request: pytest.FixtureRequest) -> Iterator[None]:
    """Een `.send()` op een workflow-/onderhoudsactor belandt in tests op een StubBroker, niet op Redis.

    De productiecode heeft GEEN stub meer (ADR-036 OP-13): de actors hangen vast aan een echte `RedisBroker`
    (`src/core/tasks/dramatiq_broker.py`). Zonder deze fixture zou elke test die een taak verstuurt een
    verbinding naar Redis proberen. Alleen `enqueue` van die ene broker wordt omgeleid; wie het echte gedrag wil
    toetsen (Redis weg -> fout) gebruikt de markering `echte_broker` of bouwt een eigen broker.

    Terugzetten gebeurt door het instantieattribuut te VERWIJDEREN: `monkeypatch` zet de gebonden methode terug
    als instantieattribuut en laat de broker dus voorgoed omgeleid achter.
    """
    if request.node.get_closest_marker("echte_broker"):
        yield
        return
    from dramatiq.brokers.stub import StubBroker

    from src.core.tasks.dramatiq_broker import workflow_broker

    if workflow_broker is None:
        yield
        return
    stub = StubBroker()  # type: ignore[no-untyped-call]

    def _enqueue(message: Any, *, delay: int | None = None) -> Any:
        if message.queue_name not in stub.queues:
            stub.declare_queue(message.queue_name)
        return stub.enqueue(message, delay=delay)

    workflow_broker.enqueue = _enqueue
    try:
        yield
    finally:
        workflow_broker.__dict__.pop("enqueue", None)


_original_get_event_loop = asyncio.get_event_loop


def _compat_get_event_loop():
    """Restore pre-3.13 behavior for legacy test/plugin paths that expect a current loop."""
    try:
        return _original_get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


asyncio.get_event_loop = _compat_get_event_loop

pytest_plugins = [
    "tests.fixtures.api",
    "tests.fixtures.database",
    "tests.fixtures.auth",
    "tests.fixtures.tenant",
    "tests.fixtures.external_mocks",
]

# CRITICAL: Filter pkg_resources deprecation warning BEFORE any imports that trigger it
# This must be done before pytest's filterwarnings configuration takes effect
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*", category=UserWarning)

# Filter asyncio deprecation warnings
warnings.filterwarnings("ignore", message=".*no current event loop.*", category=DeprecationWarning)

# Filter asyncpg deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="asyncpg.*")


_tenant_id_counter = count(10_000)


class FakeRedisClient:
    """Minimal async Redis test double for list-backed conversation history."""

    def __init__(self) -> None:
        self._lists: dict[str, list[str]] = {}
        self._ttl: dict[str, int] = {}

    async def rpush(self, key: str, value: str) -> int:
        values = self._lists.setdefault(key, [])
        values.append(value)
        return len(values)

    async def expire(self, key: str, ttl: int) -> bool:
        self._ttl[key] = ttl
        return True

    async def ltrim(self, key: str, start: int, end: int) -> bool:
        values = self._lists.get(key, [])
        self._lists[key] = values[self._normalize_slice(values, start, end)]
        return True

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        values = self._lists.get(key, [])
        return list(values[self._normalize_slice(values, start, end)])

    async def delete(self, key: str) -> int:
        existed = key in self._lists
        self._lists.pop(key, None)
        self._ttl.pop(key, None)
        return 1 if existed else 0

    @staticmethod
    def _normalize_slice(values: list[Any], start: int, end: int) -> slice:
        size = len(values)
        normalized_start = start if start >= 0 else max(size + start, 0)
        normalized_end = end if end >= 0 else size + end

        if end == -1:
            normalized_end = size - 1

        if normalized_start >= size:
            return slice(size, size)

        normalized_end = min(normalized_end, size - 1)
        if normalized_end < normalized_start:
            return slice(0, 0)

        return slice(normalized_start, normalized_end + 1)


class TenantFactory:
    """Backward-compatible ID factory for older security tests."""

    @classmethod
    def next_id(cls) -> int:
        return next(_tenant_id_counter)


def _reset_auth_rate_limiter() -> None:
    """Clear auth limiter state so test requests do not leak across fixtures."""
    from src.core.api.auth import router as auth_router_module

    storage = getattr(auth_router_module.auth_limiter, "_storage", None)
    if storage is None:
        return
    if hasattr(storage, "reset"):
        storage.reset()
        return
    if hasattr(storage, "clear"):
        storage.clear()


def _reset_security_manager_rate_limits() -> None:
    """Clear security manager rate limit state so test requests do not leak across fixtures."""
    try:
        from src.core.security.security_manager import _security_manager

        if _security_manager is not None:
            _security_manager.rate_limits.clear()
            # RC-SEC-1: blocked_ips persists for process lifetime without this clear.
            # URL paths like /api/gdpr/delete-all contain SQL keywords (DELETE) that trigger
            # _log_security_event(CRITICAL) -> blocked_ips.add(ip). Without clearing this,
            # ALL subsequent tests from the same IP ("testclient") get HTTP 429.
            _security_manager.blocked_ips.clear()
            # RC-SEC-2: failed_attempts accumulates across tests, inflating threat scores
            # and causing legitimate test requests to be blocked.
            _security_manager.failed_attempts.clear()
    except Exception:
        pass
    # De IP-reputatie (plan nazorg, punt b) staat in Redis en overleeft dus het proces. Elke
    # test krijgt een verse instantie op een nep-Redis in het geheugen, zodat een blokkade uit
    # de ene test nooit een andere test (of een andere bouwer op dezelfde Redis) raakt. Tests
    # die echte Redis willen, geven zelf een IpReputation mee aan de middleware.
    try:
        from src.core.security import ip_reputation
        from tests.fixtures.nep_redis import NepRedis

        ip_reputation._ip_reputation = ip_reputation.IpReputation(client=NepRedis())
    except Exception:
        pass


def _do_global_reset():
    """Reset all known module-level singletons to prevent inter-test pollution."""
    # --- RC1: Prometheus REGISTRY ---
    try:
        from prometheus_client import REGISTRY

        _keep = ("python_", "process_", "gc_")
        to_remove = [
            coll
            for name, coll in list(REGISTRY._names_to_collectors.items())
            if not name.startswith(_keep)
        ]
        for coll in to_remove:
            try:
                REGISTRY.unregister(coll)
            except Exception:
                pass
    except Exception:
        pass

    # --- RC2: Governance _rate_limiter (InMemoryRateLimiter singleton) ---
    # privacy_rate_limit / copilot_turn_limit / ai_transparency_limit all write to this
    # singleton. Without reset, requests accumulate across tests and trigger 429 in later tests.
    # See CLAUDE.md: "_rate_limiter is module-level singleton -- altijd resetten in setup_method"
    try:
        from src.core.governance.rate_limiter import _rate_limiter

        _rate_limiter._requests.clear()
        _rate_limiter._last_cleanup = 0.0
    except Exception:
        pass

    # --- RC3: Auth rate limiter (slowapi in-memory storage) ---
    _reset_auth_rate_limiter()
    _reset_security_manager_rate_limits()

    # --- RC4: Predictive evolution engine singleton ---
    try:
        from src.core.learning.predictive_evolution import predictive_evolution_engine

        predictive_evolution_engine.metrics_history = []
        predictive_evolution_engine.predictions = []
        predictive_evolution_engine.learning_models = {}
        predictive_evolution_engine.optimization_patterns = []
        predictive_evolution_engine.is_monitoring = False
    except Exception:
        pass

    # --- RC5: ContextVars ---
    try:
        from src.core.middleware.tenant_context import _current_user_scopes, _tenant_context

        _tenant_context.set(None)
        _current_user_scopes.set([])
    except Exception:
        pass

    # RC6 (de globale tenantfilter-listener) staat NIET hier maar in `_reset_global_state`
    # hieronder, omdat het een SAVE/RESTORE is en geen reset. Zie de uitleg daar.


def _tenant_filter_is_active() -> bool | None:
    """Of de globale tenantfilter-listener nu geregistreerd staat, of None als onbekend."""
    try:
        from src.core.database.tenant_query_filter import tenant_auto_filtering_is_active

        return tenant_auto_filtering_is_active()
    except Exception:
        return None


def _restore_tenant_filter(was_active: bool | None) -> None:
    """Zet de listener terug naar de staat van voor de test."""
    if was_active is None:
        return
    try:
        from src.core.database.tenant_query_guard import register_query_guard, remove_query_guard

        nu_actief = _tenant_filter_is_active()
        if was_active and nu_actief is False:
            register_query_guard()
        elif not was_active and nu_actief is True:
            remove_query_guard()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_global_state():
    """Reset all shared singletons before and after every test.

    RC6 -- de globale tenantfilter-listener (ADR-036 OP-20, oorzaak).

    `init_tenant_auto_filtering()` hangt een `do_orm_execute`-listener aan de Session-KLASSE met
    `propagate=True`. Dat is procesbreed: registreert een test hem -- direct, of indirect via
    `db_manager.initialize()` -> `register_query_guard()`, of via de app-lifespan -- dan krijgt
    daarna ELKE sessie in dat proces een automatisch tenantfilter, ook een eigen
    in-memory-SQLite-sessie van een ander testbestand. En dat filter is fail-secure: zonder tenant
    in de ContextVar levert het NUL rijen, stil. Samen met RC5 hierboven, dat de ContextVar juist
    leegmaakt, is dat fataal -- twee individueel correcte dingen die een test laten falen zonder
    exception en zonder log.

    Gemeten 2026-08-11: `tests/unit/test_database_coverage.py` registreerde hem op index 595 en
    `test_sp_e01_password_reset_email.py::test_forgot_password_calls_email_service` viel om op
    index 848. Reproductie in 3,29 s door alleen de listener te registreren.

    **Dit is een SAVE/RESTORE en geen reset, en dat verschil is gemeten.** Mijn eerste versie
    verwijderde de listener onvoorwaardelijk bij elke test. Gevolg: 14 tests in
    `tests/unit/test_tenant_query_filter.py` vielen om, want die hebben het filter juist NODIG --
    een module-scoped fixture registreert hem, en die loopt VOOR deze function-scoped fixture. Een
    reset zet dus precies uit wat die tests meten. Terugzetten naar de staat van voor de test doet
    beide goed: wie hem zelf aanzet houdt hem, wie hem per ongeluk laat staan raakt hem kwijt.

    `remove_query_guard()` en niet `remove_tenant_auto_filtering()`: die eerste zet OOK
    `_GUARD_REGISTERED` terug. Alleen de listener weghalen zou `register_query_guard()` daarna
    laten overslaan, en dan is het tenantfilter permanent afwezig -- een fail-secure filter dat geen
    filter meer is, terwijl de isolatietests groen blijven.
    """
    _do_global_reset()
    filter_was_active = _tenant_filter_is_active()
    yield
    _restore_tenant_filter(filter_was_active)
    _do_global_reset()


@pytest.fixture
def user_token(test_token: str) -> str:
    """Backward-compatible alias for tests expecting a regular user token."""
    return test_token


@pytest.fixture
def auth_headers(test_token: str) -> dict[str, str]:
    """Backward-compatible auth headers for tests using the shared unit auth fixtures."""
    return {"Authorization": f"Bearer {test_token}"}


@pytest.fixture
def admin_auth_headers(admin_token: str) -> dict[str, str]:
    """Authorization headers with admin token for endpoints requiring ADMIN security level."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
async def tenant_a(db_session: AsyncSession):
    """Create a tenant ORM instance for legacy security tests expecting .id access."""
    from src.core.models.rbac_models import Tenant

    tenant = Tenant(
        name=f"Tenant A {TenantFactory.next_id()}",
        slug=f"tenant-a-{TenantFactory.next_id()}",
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def tenant_b(db_session: AsyncSession):
    """Create a second tenant ORM instance for legacy cross-tenant security tests."""
    from src.core.models.rbac_models import Tenant

    tenant = Tenant(
        name=f"Tenant B {TenantFactory.next_id()}",
        slug=f"tenant-b-{TenantFactory.next_id()}",
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest.fixture
def audit_logger():
    """Provide the enterprise audit logger to security tests outside its original module."""
    from src.core.als.enterprise.audit.audit_logger import AuditLogger

    return AuditLogger(tenant_id=1)


@pytest.fixture
def redis_client() -> FakeRedisClient:
    """Provide a minimal async Redis-compatible client for memory unit tests."""
    return FakeRedisClient()


@pytest.fixture
def mock_signal_bus():
    """Shared async mock bus for shadow security fixtures."""

    bus = AsyncMock()
    bus.emit = AsyncMock(return_value=None)
    return bus


@pytest_asyncio.fixture
async def shadow_ceo(mock_signal_bus):
    """Provide ShadowCEO outside its dedicated test module."""
    from src.core.als.enterprise.shadow.shadow_ceo import ShadowCEO

    shadow = ShadowCEO(
        tenant_id=1,
        signal_bus=mock_signal_bus,
        agent_id="shadow_ceo_test",
    )
    yield shadow


@pytest.fixture
def gatekeeper():
    """Provide Gatekeeper outside its dedicated test module."""
    from src.core.als.enterprise.gatekeeper import Gatekeeper

    return Gatekeeper(tenant_id=1)


@pytest.fixture(scope="session")
def event_loop_policy():
    # RC-LOOP-1 extension: ensure xdist workers also use SelectorEventLoop on Windows.
    # ensure_main_thread_event_loop calls set_event_loop_policy(this), so returning
    # DefaultEventLoopPolicy() on Windows would silently undo the module-level override.
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session", autouse=True)
def ensure_main_thread_event_loop(event_loop_policy):
    """Ensure a current event loop exists for legacy async test/plugin paths."""
    asyncio.set_event_loop_policy(event_loop_policy)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        loop.close()
        asyncio.set_event_loop(None)


# CRITICAL FIX: Removed session-scoped event_loop fixture.
# pytest-asyncio 0.24+ in auto mode manages event loops automatically.
# A session-scoped event_loop fixture conflicts with function-scoped
# async fixtures and causes ScopeMismatch errors.
# See: https://pytest-asyncio.readthedocs.io/en/latest/reference/changelog.html


@pytest.fixture
def respx_mock():
    """Provide a minimal local respx-compatible router for HTTP mocking tests."""
    with MockRouter(assert_all_mocked=False) as router:
        yield router


@pytest.fixture
def client(async_engine):
    """Shared sync TestClient backed by the same test engine used by db_session."""
    from src.core.database import database as database_module
    from src.core.database.database import get_db

    session_factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    database_module.db_manager.set_engine(async_engine)
    database_module.engine = async_engine
    database_module.async_session_maker = session_factory

    async def override_get_db():
        async with session_factory() as session:
            yield session

    test_app = create_test_app(db_session_override=override_get_db)
    test_app.dependency_overrides[get_db] = override_get_db

    from src.core.auth.dependencies import (
        get_current_user,
        get_current_user_dependency,
        get_current_user_id,
    )
    from src.core.auth.scopes import OAuth2Scope
    from src.core.database.database import get_db as scope_get_db
    from src.core.middleware.tenant_context import _current_user_scopes, set_tenant_id

    async def override_current_user():
        set_tenant_id(1)
        _current_user_scopes.set(
            [
                OAuth2Scope.ADMIN_ALL.value,
                OAuth2Scope.AGENTS_READ.value,
                OAuth2Scope.AGENTS_WRITE.value,
            ]
        )
        return SimpleNamespace(
            id=1,
            email="test@example.com",
            tenant_id=1,
            roles=["admin"],
            is_superuser=True,
        )

    async def override_current_user_id() -> int:
        set_tenant_id(1)
        _current_user_scopes.set(
            [
                OAuth2Scope.ADMIN_ALL.value,
                OAuth2Scope.AGENTS_READ.value,
                OAuth2Scope.AGENTS_WRITE.value,
            ]
        )
        return 1

    test_app.dependency_overrides[get_current_user] = override_current_user
    test_app.dependency_overrides[get_current_user_dependency] = override_current_user
    test_app.dependency_overrides[get_current_user_id] = override_current_user_id

    # Override for evaluation endpoints that use get_current_tenant_id
    from src.core.api.search_endpoints import get_current_tenant_id

    def override_get_current_tenant_id():
        return 1

    test_app.dependency_overrides[get_current_tenant_id] = override_get_current_tenant_id

    # Override WebSocket authentication dependency
    from src.core.auth.websocket_auth import AuthenticatedUser, get_ws_user

    def override_get_ws_user() -> AuthenticatedUser:
        return AuthenticatedUser(
            user_id="test-user-1",
            tenant_id=1,
            email="test@example.com",
            roles=["admin", "user"],
        )

    test_app.dependency_overrides[get_ws_user] = override_get_ws_user

    _reset_auth_rate_limiter()
    _reset_security_manager_rate_limits()
    test_client = TestClient(test_app)
    yield test_client
    test_app.dependency_overrides.clear()
    test_client.close()
    _reset_auth_rate_limiter()
    _reset_security_manager_rate_limits()


@pytest.fixture
def client_no_bypass(async_engine):
    """Shared sync TestClient backed by the fixture engine and no auth bypasses."""
    from src.core.database import database as database_module
    from src.core.database.database import get_db

    session_factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    database_module.db_manager.set_engine(async_engine)
    database_module.engine = async_engine
    database_module.async_session_maker = session_factory

    async def override_get_db():
        async with session_factory() as session:
            yield session

    test_app = create_test_app(db_session_override=override_get_db)
    test_app.dependency_overrides[get_db] = override_get_db

    _reset_auth_rate_limiter()
    _reset_security_manager_rate_limits()
    test_client = TestClient(test_app)
    yield test_client
    test_app.dependency_overrides.clear()
    test_client.close()
    _reset_auth_rate_limiter()
    _reset_security_manager_rate_limits()


@pytest_asyncio.fixture(scope="function")
async def async_client(async_engine) -> AsyncGenerator[AsyncClient, None]:
    """Shared async client backed by the test app and isolated SQLite sessions."""
    from src.core.database import database as database_module
    from src.core.database.database import get_db

    session_factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    database_module.db_manager.set_engine(async_engine)
    database_module.engine = async_engine
    database_module.async_session_maker = session_factory

    async def override_get_db():
        async with session_factory() as session:
            yield session

    test_app = create_test_app(db_session_override=override_get_db)
    test_app.dependency_overrides[get_db] = override_get_db

    from src.core.auth.dependencies import (
        get_current_user,
        get_current_user_dependency,
        get_current_user_id,
    )
    from src.core.auth.scopes import OAuth2Scope
    from src.core.database.database import get_db as scope_get_db
    from src.core.middleware.tenant_context import _current_user_scopes, set_tenant_id

    async def override_current_user():
        set_tenant_id(1)
        _current_user_scopes.set(
            [
                OAuth2Scope.ADMIN_ALL.value,
                OAuth2Scope.AGENTS_READ.value,
                OAuth2Scope.AGENTS_WRITE.value,
            ]
        )
        return SimpleNamespace(
            id=1,
            email="test@example.com",
            tenant_id=1,
            roles=["admin"],
            is_superuser=True,
        )

    async def override_current_user_id() -> int:
        set_tenant_id(1)
        _current_user_scopes.set(
            [
                OAuth2Scope.ADMIN_ALL.value,
                OAuth2Scope.AGENTS_READ.value,
                OAuth2Scope.AGENTS_WRITE.value,
            ]
        )
        return 1

    test_app.dependency_overrides[get_current_user] = override_current_user
    test_app.dependency_overrides[get_current_user_dependency] = override_current_user
    test_app.dependency_overrides[get_current_user_id] = override_current_user_id

    transport = ASGITransport(app=test_app)
    _reset_auth_rate_limiter()
    _reset_security_manager_rate_limits()
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        follow_redirects=True,
    ) as test_client:
        yield test_client

    test_app.dependency_overrides.clear()
    _reset_auth_rate_limiter()
    _reset_security_manager_rate_limits()


# ---------------------------------------------------------------------------
# Opt-in hook for subprocess-based type checker tests
# ---------------------------------------------------------------------------
# Tests marked with @pytest.mark.typecheck invoke pyright or mypy as a
# subprocess (slow, ~60-300s). They are skipped by default to keep the unit
# test suite fast. Run with --run-typecheck to include them.
#
# Example:
#   pytest tests/unit/temp_disabled/test_pyright_audit.py \
#          --run-typecheck --timeout=600


def pytest_addoption(parser: pytest.Parser) -> None:
    try:
        parser.addoption(
            "--run-typecheck",
            action="store_true",
            default=False,
            help=(
                "Run slow subprocess-based type checker tests (pyright, mypy). "
                "Off by default. Combine with --timeout=600 for pyright tests."
            ),
        )
    except ValueError as exc:
        if "--run-typecheck" not in str(exc):
            raise


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """De ENIGE definitie van deze hook in dit bestand (ADR-036 OP-44).

    Tot 2026-08-31 stond hierboven een TWEEDE definitie met een PostgreSQL-auto-skip. Python houdt
    de laatste, dus die was dode code. Hij is verwijderd en niet samengevoegd; de gemeten reden
    staat bij de constanten bovenaan dit bestand.
    """
    if not config.getoption("--run-typecheck", default=False):
        skip = pytest.mark.skip(reason="subprocess type checker test -- use --run-typecheck to run")
        for item in items:
            if "typecheck" in item.keywords:
                item.add_marker(skip)


# ---------------------------------------------------------------------------
# Shutdown-guard: noem de thread die het proces openhoudt (ADR-036 OP-132)
# ---------------------------------------------------------------------------

_SESSIE_EXITSTATUS = {"waarde": 0}


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Bewaar de exitcode zodat de guard hieronder hem ongewijzigd kan doorgeven."""
    _SESSIE_EXITSTATUS["waarde"] = int(exitstatus)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Betrap een thread die de interpreter niet laat afsluiten, en noem hem bij naam.

    **De bevinding.** De CI-stap `Full unit tests` liep drie keer vast NA de laatste testregel:
    `15530 passed in 16:18`, daarna niets meer tot de timeout. De stackdump (2026-08-11, run
    31541512756) wees het aan:

        Current thread (most recent call first):
          File ".../threading.py", line 1590 in _shutdown

    `threading._shutdown` is de fase waarin CPython bij het afsluiten op alle NON-DAEMON threads
    wacht. Er leeft er dus een die nooit eindigt. De tests zelf zijn klaar en groen; het proces
    komt alleen niet weg.

    Twee eerdere hypotheses zijn hiermee weerlegd, allebei plausibel en allebei fout: het 1,3 GB
    JSON-rapport (na die fix bleef de hang, en werd zelfs iets langer) en een kindproces dat de
    pijp naar `tee` openhield (`PYTEST-AFGEROND` verscheen niet, dus pytest leefde nog).

    **Waarom lokaal niets te zien is.** Op Windows, volle suite single-process: 24:03, netjes
    afgesloten, nul non-daemon threads. CI draait met echte Postgres- en Redis-containers, dus daar
    lopen codepaden die lokaal niet eens starten.

    **Wat deze hook doet.** Blijven er non-daemon threads over, dan schrijft hij naam en stack van
    elke thread naar stderr -- dat is de informatie die nodig is om de bron te repareren, en die
    ontbrak in drie CI-runs. Daarna sluit hij het proces af met de ONGEWIJZIGDE exitcode, zodat een
    falende suite blijft falen. Zonder dat blijft de job hangen tot de timeout en is er geen
    uitslag, ook niet als alles groen was.

    **Dit is een stopgap, geen oplossing.** De thread zelf moet nog gevonden en opgeruimd worden;
    dat staat als OP-132 in ADR-036. Zolang die er is meldt deze hook hem bij elke run, dus hij kan
    niet stil blijven bestaan.
    """
    import sys
    import threading
    import traceback

    achterblijvers = [
        t
        for t in threading.enumerate()
        if t is not threading.main_thread() and not t.daemon and t.is_alive()
    ]
    if not achterblijvers:
        return

    frames = sys._current_frames()
    print("\n[SHUTDOWN-GUARD] Non-daemon threads die de interpreter openhouden:", file=sys.stderr)
    for t in achterblijvers:
        print(f"[SHUTDOWN-GUARD]   thread {t.name!r} (ident={t.ident})", file=sys.stderr)
        frame = frames.get(t.ident or -1)
        if frame is not None:
            for regel in traceback.format_stack(frame):
                for deelregel in regel.rstrip().splitlines():
                    print(f"[SHUTDOWN-GUARD]     {deelregel}", file=sys.stderr)
    sys.stderr.flush()
    sys.stdout.flush()

    code = _SESSIE_EXITSTATUS["waarde"]
    print(
        f"[SHUTDOWN-GUARD] Proces wordt geforceerd afgesloten met exitcode {code}. "
        "Zonder dit hangt de run tot de CI-timeout (ADR-036 OP-132).",
        file=sys.stderr,
    )
    sys.stderr.flush()

    # `iter/ci-fase1`-aanvulling: een faulthandler-deadline die OOK een hang zonder
    # non-daemon thread vangt (bv. een blokkerende `atexit`-handler, die in geen enkele
    # thread-opsomming voorkomt). Gemeten 2026-08-08: de CI-stap `Full unit tests` deed 35
    # minuten NIETS na de samenvatting tot de joblimiet toesloeg, zonder dat dit net (dat
    # alleen non-daemon threads telt) iets kon zien. Bewust WEL nog steeds de ORIGINELE
    # exitcode (`os._exit(code)` hieronder) -- deze deadline verandert niet OF een groene run
    # rood wordt bij een bekende, getrackte threadlek (ADR-036 OP-132 blijft een stopgap-
    # observatie, geen harde poort), maar zorgt dat een ONBEKENDE hang nooit meer 35 minuten
    # stil is.
    if _HANG_DEADLINE_SECONDS > 0:
        faulthandler.dump_traceback_later(
            _HANG_DEADLINE_SECONDS, exit=True, file=sys.__stderr__ or sys.stderr
        )

    os._exit(code)


#: Seconden na de samenvatting waarna faulthandler alle thread-stacks dumpt en het proces
#: doodt, als vangnet naast (niet in plaats van) de non-daemon-threadcontrole hierboven.
_HANG_DEADLINE_SECONDS = int(os.environ.get("SS_HANG_DEADLINE_SECONDS", "120"))


# ---------------------------------------------------------------------------
# Vangnet 2: een test die `sys.modules` sloopt zonder herstel
# ---------------------------------------------------------------------------
#
# Waarom dit bestaat. `del sys.modules["src.x"]` zonder herstel laat de volgende importeur
# een VERS moduleobject maken. Twee klassen met dezelfde naam uit twee moduleobjecten zijn
# dan niet meer `is`-gelijk, terwijl ze identiek printen -- een `isinstance()` in een
# volstrekt ander testbestand faalt dan zonder zichtbare reden.
#
# Dit is niet theoretisch en niet nieuw: ADR-036 OP-45 beschrijft dezelfde vorm, en
# `tests/unit/api/v1/agents/test_agent_router_lazy_import.py` documenteert hem in zijn
# docstring en herstelt daarom netjes in een `finally`. Toch faalde op 2026-08-11
# `tests/unit/workflow/test_workflow_real_routing.py::test_create_workflow_engine_injects_agent_router`
# in de volle suite en niet los. Gemeten reproductie:
#
#   import src.core.workflow.providers, src.core.workflow.worker
#   del sys.modules["src.core.workflow.providers"]
#   -> 1 failed in 0.55s: "create_workflow_engine() moet een ProductionAgentRuntime opleveren"
#
# Dit net wijst de DADER aan in plaats van het slachtoffer, zodat er geen bisect van tien
# runs nodig is.
#
# Waarom IDENTITEIT en niet aanwezigheid: `importlib.reload()` werkt het bestaande
# moduleobject bij en houdt de identiteit gelijk. Alleen een `del` gevolgd door herimport
# maakt een nieuw object. Legitieme reloads geven hier dus geen valse positief.

_MODULE_SNAPSHOT: dict[str, int] = {}


def _snapshot_src_modules() -> dict[str, int] | None:
    """De `src.*`-modules met hun object-identiteit, of None als er niet te meten valt.

    `sys.modules` kan tijdens het aflopen van GROOTTE veranderen wanneer een andere thread
    importeert, en dan gooit CPython `RuntimeError: dictionary changed size during iteration`.
    Dat is niet theoretisch: `tests/unit/agents/test_base_agent_toolbroker.py` start een
    sandbox-manager die op de achtergrond importeert, en daar liep de eerste versie van dit net op
    stuk (gemeten in de volledige containerrun).

    Een paar keer opnieuw proberen, en anders None. Bewust GEEN lege dict teruggeven: dat zou als
    "alle modules verdwenen" gelezen worden en elke test rood maken. Een mislukte meting is geen
    bewijs van een overtreding.
    """
    for _ in range(5):
        try:
            return {
                name: id(mod) for name, mod in list(sys.modules.items()) if name.startswith("src.")
            }
        except RuntimeError:
            continue
    return None


@pytest.fixture(scope="session", autouse=True)
def _seed_module_snapshot():
    """Leg de startsituatie vast voordat de eerste test loopt."""
    startstand = _snapshot_src_modules()
    _MODULE_SNAPSHOT.clear()
    if startstand is not None:
        _MODULE_SNAPSHOT.update(startstand)
    yield


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: pytest.Item, nextitem: pytest.Item | None) -> None:
    """Faal de test die een `src.*`-module verving of weggooide zonder herstel.

    `trylast=True` zodat de fixture-teardown (en dus een correct `finally`-herstel) al
    gebeurd is -- anders zou juist het NETTE patroon betrapt worden.
    """
    if not _MODULE_SNAPSHOT:
        return

    current = _snapshot_src_modules()
    if current is None:
        # Kon niet meten (een andere thread importeerde tijdens het aflopen). Overslaan en de
        # snapshot laten staan; een mislukte meting is geen bewijs van een overtreding, en een
        # lege dict zou als "alles verdwenen" gelezen worden.
        return

    verdwenen = sorted(name for name in _MODULE_SNAPSHOT if name not in current)
    vervangen = sorted(
        name
        for name, ident in _MODULE_SNAPSHOT.items()
        if name in current and current[name] != ident
    )

    # Altijd bijwerken, ook na een treffer: zo meldt alleen de EERSTE dader zich en
    # verdrinkt de uitvoer niet in tientallen slachtoffers.
    _MODULE_SNAPSHOT.clear()
    _MODULE_SNAPSHOT.update(current)

    if not verdwenen and not vervangen:
        return

    regels = [
        f"{item.nodeid} liet sys.modules kapot achter. Dat breekt `isinstance`/`is` in "
        "ANDERE testbestanden, want een herimport maakt nieuwe klasse-objecten met "
        "dezelfde naam.",
    ]
    if verdwenen:
        regels.append(f"  verdwenen uit sys.modules: {', '.join(verdwenen)}")
    if vervangen:
        regels.append(f"  vervangen door een ander object: {', '.join(vervangen)}")
    regels.append(
        "  Herstel ze in een `finally`. Zie tests/unit/api/v1/agents/"
        "test_agent_router_lazy_import.py voor het patroon dat dit goed doet (ADR-036 OP-45)."
    )
    pytest.fail("\n".join(regels), pytrace=False)
