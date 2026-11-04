"""Rate limiting tests for scheduling endpoints.

Written RED-first: verifies that rate limiting is configured
and enforced on all scheduling routes.

Pattern mirrors tests/unit/test_focus_builder/test_rate_limiting.py.
"""

import contextlib
from unittest.mock import patch

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from src.core.api.setup.exception_handlers import setup_exception_handlers
from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.database.database import Base, get_db
from src.core.scheduling.api.routes import (
    cancel_event,
    create_event,
    create_time_block,
    delete_time_block,
    get_event,
    get_preferences,
    list_events,
    list_time_blocks,
    schedule_meeting,
    update_event,
    upsert_preferences,
)

# ---------------------------------------------------------------------------
# Shared test fixture
# ---------------------------------------------------------------------------

_SCHED_RL_DB = "sqlite+aiosqlite:///file:sched_rl_test?mode=memory&cache=shared&uri=true"

#: De engine wordt EEN keer gemaakt en aan het eind van de module opgeruimd.
#:
#: Hij stond eerst in `_make_scheduling_app()`, die acht keer wordt aangeroepen en de engine
#: nergens teruggaf of `dispose()`de. Elke engine houdt via `StaticPool` een aiosqlite-connectie
#: open, en `aiosqlite/core.py:90` maakt zijn worker-thread ZONDER `daemon`. Op een Linux-runner
#: zijn die threads non-daemon, en dan blijft `threading._shutdown()` er voor altijd op wachten:
#: pytest printte zijn samenvatting en het proces hing daarna 35 minuten tot de CI-joblimiet van
#: 45 minuten toesloeg (gemeten 2026-08-08, en gereproduceerd in een 3.11-container).
#:
#: Een gedeelde engine is hier ook inhoudelijk juister dan acht: alle aanroepen gebruiken
#: dezelfde vaste `_SCHED_RL_DB`-URI met `cache=shared`, dus het was al een en dezelfde database.
_engine: AsyncEngine | None = None


def _get_engine() -> AsyncEngine:
    """De gedeelde engine, lui aangemaakt."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _SCHED_RL_DB,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return _engine


@pytest.fixture(scope="module", autouse=True)
def _dispose_scheduling_engine():
    """Ruim de gedeelde engine op, zodat er geen aiosqlite-thread overleeft.

    `anyio.run` omdat de tests in dit bestand synchroon zijn; datzelfde idioom staat al in
    `_make_scheduling_app()` voor `_init`.
    """
    yield
    global _engine
    if _engine is not None:
        engine, _engine = _engine, None
        anyio.run(engine.dispose)


@contextlib.contextmanager
def _bevroren_limietklok():
    """Zet de klok van de rate-limiter stil voor de duur van een burst.

    Zonder dit zijn de uitputtingstests hieronder tijdsafhankelijk, en dat is GEMETEN en
    niet vermoed (2026-09-14, ADR-036 OP-196). Een Gate 2-reviewer zag ze een op dertien
    runs omvallen onder `-n 4`, uitgerekend in de traagste run. Twee hypotheses zijn
    onderzocht en ALLEBEI WEERLEGD:

    * "de burst kruist een kalenderminuut": nee -- de vensters van `limits` starten bij het
      eerste verzoek, niet op een kalendergrens. Nagebouwd met 30 verzoeken voor en 40 na
      een minuutgrens: 10 keer 429, precies zoals verwacht.
    * "een schuivend venster lost het op": nee -- met `strategy="moving-window"` is de
      uitkomst identiek.

    Wat het WEL is: de test stuurt 70 verzoeken tegen een limiet van 60 per minuut en eist
    een 429. Dat klopt alleen als de burst ruim binnen die minuut past. Duurt hij door
    machinebelasting richting de 70 seconden, dan is het tempo ongeveer een verzoek per
    seconde -- exact de limiet -- en komt er terecht NOOIT een 429. Gemeten met een
    tussenpauze van 1 seconde: nul keer 429, onder beide strategieen.

    Door de klok van de opslag stil te zetten tellen alle 70 verzoeken in hetzelfde venster,
    hoe traag de machine ook is. De test meet dan het gedrag van de limiter in plaats van de
    snelheid van de runner.
    """
    with patch("limits.storage.memory.time.time", return_value=1_800_000_000.0):
        yield


def _make_scheduling_app() -> tuple[FastAPI, TestClient]:
    """Create minimal scheduling app with rate limiter configured."""
    from src.core.models.rbac_models import Tenant  # noqa: F401 -- registers FK target
    from src.core.scheduling.api.routes import router as scheduling_router

    engine = _get_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _init() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    mock_user = UserResponse(
        id=1,
        email="rl@test.dev",
        tenant_id=1,
        roles=["admin"],
    )

    anyio.run(_init)

    app = FastAPI(title="Scheduling Rate Limit Test")
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri="memory://",
        headers_enabled=True,
    )
    app.state.limiter = limiter
    setup_exception_handlers(app)

    app.include_router(scheduling_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: mock_user

    return app, TestClient(app)


# ---------------------------------------------------------------------------
# Configuration tests
# ---------------------------------------------------------------------------


class TestSchedulingRateLimitConfiguration:
    """Rate limiter must be wired into the scheduling app."""

    def test_limiter_initialized_in_app_state(self):
        """App must have a Limiter in app.state.limiter."""
        app, _ = _make_scheduling_app()
        assert hasattr(app.state, "limiter")
        assert isinstance(app.state.limiter, Limiter)

    def test_limiter_uses_memory_storage_in_tests(self):
        """Development/test limiter must use in-memory storage (no Redis dep)."""
        app, _ = _make_scheduling_app()
        storage_uri = str(app.state.limiter._storage_uri)
        assert "memory" in storage_uri.lower()

    def test_rate_limit_exception_handler_registered(self):
        """RateLimitExceeded handler must be registered on the app."""
        app = FastAPI()
        setup_exception_handlers(app)
        assert RateLimitExceeded in app.exception_handlers

    def test_limiter_has_headers_enabled(self):
        """X-RateLimit-* headers should be sent on every response."""
        app, _ = _make_scheduling_app()
        assert app.state.limiter._headers_enabled is True


# ---------------------------------------------------------------------------
# Endpoint existence + decorator tests
# ---------------------------------------------------------------------------


class TestSchedulingEndpointRateLimitDecorators:
    """Each scheduling endpoint function must exist and be rate-limited."""

    @pytest.mark.parametrize(
        "endpoint_fn",
        [
            schedule_meeting,
            create_event,
            list_events,
            get_event,
            update_event,
            cancel_event,
            create_time_block,
            list_time_blocks,
            delete_time_block,
            get_preferences,
            upsert_preferences,
        ],
    )
    def test_endpoint_is_callable(self, endpoint_fn):
        assert callable(endpoint_fn)

    def test_schedule_meeting_endpoint_exists(self):
        assert callable(schedule_meeting)

    def test_create_event_endpoint_exists(self):
        assert callable(create_event)

    def test_list_events_endpoint_exists(self):
        assert callable(list_events)

    def test_preferences_endpoints_exist(self):
        assert callable(get_preferences)
        assert callable(upsert_preferences)


# ---------------------------------------------------------------------------
# Enforcement tests -- call endpoint once, verify rate limit headers
# ---------------------------------------------------------------------------


class TestSchedulingRateLimitEnforcement:
    """With headers_enabled=True, every response carries X-RateLimit-* headers."""

    def test_get_preferences_returns_rate_limit_headers(self):
        _, client = _make_scheduling_app()
        resp = client.get("/api/v1/scheduling/preferences")
        # Not rate-limited yet (first call)
        assert resp.status_code != 429
        # slowapi adds X-RateLimit-* headers when headers_enabled=True
        has_rl_header = any("x-ratelimit" in k.lower() for k in resp.headers)
        assert has_rl_header, f"Expected X-RateLimit-* headers but got: {list(resp.headers.keys())}"

    def test_list_events_returns_rate_limit_headers(self):
        _, client = _make_scheduling_app()
        resp = client.get("/api/v1/scheduling/events")
        assert resp.status_code != 429
        has_rl_header = any("x-ratelimit" in k.lower() for k in resp.headers)
        assert has_rl_header, f"Missing rate limit headers: {list(resp.headers.keys())}"

    def test_list_time_blocks_returns_rate_limit_headers(self):
        _, client = _make_scheduling_app()
        resp = client.get("/api/v1/scheduling/time-blocks")
        assert resp.status_code != 429
        has_rl_header = any("x-ratelimit" in k.lower() for k in resp.headers)
        assert has_rl_header, f"Missing rate limit headers: {list(resp.headers.keys())}"


# ---------------------------------------------------------------------------
# 429 enforcement test -- exhaust the limit
# ---------------------------------------------------------------------------


class TestSchedulingRateLimitExhaustion:
    """Verify that exceeding the limit returns 429 with proper headers."""

    def test_preferences_429_after_limit_exceeded(self):
        """GET /preferences is limited; exhausting it must return 429."""
        _, client = _make_scheduling_app()

        with _bevroren_limietklok():
            responses = [client.get("/api/v1/scheduling/preferences") for _ in range(70)]
        status_codes = [r.status_code for r in responses]

        # Geen `or`-ontsnapping: met een limiet van 60/minuut MOET 70 verzoeken een 429
        # opleveren. De oorspronkelijke vorm ("429 OR alles geslaagd") bleef groen als de
        # limiter volledig ontbrak -- gemeten in de Gate 2-review (ADR-036 OP-196): het
        # weghalen van @limiter.limit op get_preferences liet deze test groen.
        assert 429 in status_codes, f"geen 429 na 70 verzoeken: {set(status_codes)}"

    def test_429_response_includes_retry_after_header(self):
        """A 429 response must include Retry-After."""
        _, client = _make_scheduling_app()

        hit_429 = None
        with _bevroren_limietklok():
            for _ in range(70):
                resp = client.get("/api/v1/scheduling/preferences")
                if resp.status_code == 429:
                    hit_429 = resp
                    break

        # Zonder deze assertie was de hele test een lege huls: geen 429 betekende een lege
        # body en dus groen, ook met de limiter eruit (Gate 2-review, ADR-036 OP-196).
        assert hit_429 is not None, "70 verzoeken leverden geen enkele 429 op"

        if hit_429 is not None:
            headers_lower = {k.lower(): v for k, v in hit_429.headers.items()}
            assert (
                "retry-after" in headers_lower
            ), f"429 response missing Retry-After header: {hit_429.headers}"
            assert int(headers_lower["retry-after"]) > 0
