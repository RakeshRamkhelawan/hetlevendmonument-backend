"""
Application Lifespan Manager - Centralized startup/shutdown logic.

This module handles all application lifecycle events following best practices:
- Async context manager pattern (FastAPI recommended)
- Clean separation of startup and shutdown phases
- Environment-aware initialization (development vs production)
- Proper error handling with graceful degradation

Usage:
    from src.core.app_lifespan import app_lifespan
    app = FastAPI(lifespan=app_lifespan)
"""

import asyncio
import os
import sys
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from loguru import logger

if TYPE_CHECKING:
    # Alleen voor de annotaties. Deze twee worden binnen de functies zelf geimporteerd
    # (module-level import van `rbac_service` trekt de halve domeinlaag mee tijdens het
    # opstarten), maar de namen moeten wel kloppen voor de typecontrole.
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.core.services.rbac_service import RBACService

from src.core.caching import get_cache, get_session_manager
from src.core.config.frontend_url import FrontendUrlOntbreekt, frontend_url
from src.core.database.applicatierol_controle import ApplicatieRolFout, controleer_applicatierol
from src.core.database.database import close_database, db_manager, initialize_database
from src.core.events import get_pubsub_manager
from src.core.observability.logging import configure_logging

# Environment configuration
# Dezelfde default als src/main.py: een start zonder ENVIRONMENT is production, niet development.
ENVIRONMENT = os.getenv("ENVIRONMENT", "production").lower()


# =============================================================================
# STARTUP HELPERS
# =============================================================================


async def _init_database() -> bool:
    """Initialize database connection. Returns True on success."""
    try:
        logger.info("[START] Starting database initialization...")
        if not await initialize_database():
            logger.critical("[FAIL] Database initialization failed. Exiting application.")
            return False
        logger.info("[OK] Database initialized successfully")
        await _controleer_databaserol()
        return True
    except ApplicatieRolFout as e:
        # Fail-closed (ADR-036 OP-151): de rol omzeilt RLS, dus de scheiding tussen klanten rust op
        # applicatiecode alleen. De melding legt uit wat er mis is en wat de bedoeling is.
        logger.critical("[FATAL] %s", e)
        return False
    except Exception as e:
        logger.critical(
            "[FATAL] Database initialization exception: %s: %s", type(e).__name__, e, exc_info=True
        )
        return False


async def _controleer_databaserol() -> None:
    """Weiger te starten (productie/staging) als de databaserol Row Level Security omzeilt."""
    if db_manager.engine is None:
        # Fail-closed: zonder engine is er niets gemeten, en "niets gemeten" is geen "veilig".
        raise ApplicatieRolFout(
            "De databaseverbinding bestaat niet; de rol kon niet worden gecontroleerd."
        )
    from src.config import DEPLOYMENT_MODE

    async with db_manager.engine.connect() as conn:
        await controleer_applicatierol(
            conn, omgeving=ENVIRONMENT, single_tenant=DEPLOYMENT_MODE == "single_tenant"
        )


async def _init_tenant_filtering() -> None:
    """Initialize tenant auto-filtering for query security."""
    from src.core.database.tenant_query_filter import init_tenant_auto_filtering

    init_tenant_auto_filtering()
    logger.info("Tenant auto-filtering initialized (queries are tenant-scoped)")


async def _init_redis_services() -> None:
    """Initialize Redis services (cache always, session manager lazy in dev)."""
    # Always initialize cache layer - required by /health/ready endpoint
    try:
        await get_cache()
        logger.info("Redis cache layer initialized")
    except Exception as e:
        logger.warning("Redis cache initialization failed (non-fatal): %s: %s", type(e).__name__, e)

    # Session manager: lazy in development, eager in production
    if ENVIRONMENT == "development":
        logger.info("Redis session manager set to lazy initialization (development mode)")
        return

    try:
        await get_session_manager()
        logger.info("Redis session manager initialized")
    except Exception as e:
        logger.warning("Redis session manager initialization failed: %s: %s", type(e).__name__, e)

    try:
        pubsub = await get_pubsub_manager()
        pubsub.start_listener_task()
        logger.info("Redis pub/sub manager initialized with listener")
    except Exception as e:
        logger.warning("Redis pub/sub initialization failed: %s: %s", type(e).__name__, e)

    # Wire Redis client into ConnectionManager so WSPusher subscriber loop starts (ADR-008 WE-012)
    try:
        from src.core.database.redis import get_redis_client
        from src.core.websocket.manager import connection_manager

        redis_for_ws = await get_redis_client()
        connection_manager._redis = redis_for_ws
        logger.info("ConnectionManager Redis subscriber wired (WS push signals active)")
    except Exception as e:
        logger.warning(
            "ConnectionManager Redis init failed (non-fatal -- signals disabled): %s: %s",
            type(e).__name__,
            e,
        )


async def _init_ucr(app: FastAPI) -> None:
    """Initialize UnifiedCapabilityRegistry with Redis backend (SP-AGT-004)."""
    try:
        from src.core.agents.adapters.redis_capability_cache import RedisCapabilityCache
        from src.core.agents.capability_registry import UnifiedCapabilityRegistry

        ucr = UnifiedCapabilityRegistry(cache=RedisCapabilityCache())
        app.state.ucr = ucr
        logger.info("UnifiedCapabilityRegistry wired with RedisCapabilityCache")
    except (ImportError, OSError, ValueError, AttributeError) as e:
        logger.warning(
            "UCR initialization failed (non-fatal): %s: %s", type(e).__name__, e, exc_info=True
        )


async def _seed_default_roles() -> None:
    """Seed default RBAC roles per tenant, in ELKE omgeving (idempotent).

    Hier stond een overslag voor `development`. Gemeten 2026-10-04: de gezaaide beheerder
    had dan nul rollen, een token met alleen `users:read`, en `/api/v1/agents/` gaf 403.
    Een werkende applicatie gaat voor opstartsnelheid.
    """
    from sqlalchemy import select
    from sqlalchemy.exc import ProgrammingError

    from src.core.models.rbac_models import Tenant
    from src.core.services.rbac_service import RBACService

    try:
        async with db_manager.get_session() as session:
            result = await session.execute(select(Tenant.id))
            tenant_ids = [r[0] for r in result.all()]

            if tenant_ids:
                from src.core.database.bypass_session import adopt_tenant

                rbac = RBACService(session)
                for tid in tenant_ids:
                    # De tenant wordt PER RONDE aangenomen (ADR-036 OP-155).
                    #
                    # Deze lus draait bij het opstarten, buiten elk verzoek, dus er is geen
                    # tenantcontext. `ensure_default_roles` schrijft rijen in `roles` met
                    # een `tenant_id`. Zodra `roles` een policy heeft, geldt de
                    # USING-expressie OOK voor INSERT -- PostgreSQL gebruikt hem dan als
                    # WITH CHECK en werpt een fout
                    # (https://www.postgresql.org/docs/15/sql-createpolicy.html). Zonder
                    # deze regel faalt het seeden van rollen dus bij de eerste start na de
                    # omschakeling naar `sanskritisetu_app`.
                    #
                    # LET OP dat dit ALLEEN voor INSERT geldt. Gemeten 2026-09-15: UPDATE
                    # en DELETE zonder tenantcontext raken nul rijen en slagen ZONDER fout,
                    # want `USING` bepaalt daar eerst welke rijen zichtbaar zijn en dat zijn
                    # er nul. Een vergeten UPDATE- of DELETE-pad meldt zichzelf dus NIET.
                    #
                    # Dit is het patroon dat de vakliteratuur voor batchverwerking
                    # aanbeveelt: een lus per tenant met de context per ronde, in plaats van
                    # een verbinding die alles mag zien. `tid` komt uit de database, nooit
                    # uit invoer.
                    async with adopt_tenant(session, tid):
                        await rbac.ensure_default_roles(tid)
                        await _koppel_de_gezaaide_beheerder(session, rbac, tid)
                logger.info("Default roles seeded")
            else:
                logger.info("No tenants found, skipping role seeding")

    except ProgrammingError as e:
        logger.warning("Tenants table not found (migrations pending?): %s: %s", type(e).__name__, e)
    except Exception as e:
        logger.error("Failed to seed default roles: %s: %s", type(e).__name__, e, exc_info=True)


async def _koppel_de_gezaaide_beheerder(
    session: "AsyncSession", rbac: "RBACService", tenant_id: int
) -> None:
    """Geeft de gezaaide beheerder de rol `admin` -- eenmalig, bij het opstarten.

    HET PROBLEEM DAT DIT OPLOST (gemeten 2026-09-17 op staging).
    `seed.py` maakt de beheerder aan en zet `is_superuser = True`, maar KOPPELT hem aan
    geen enkele rol. `ensure_default_roles` maakt de rollen aan, maar koppelt ze aan geen
    enkele gebruiker. Niets daartussen deed het, en `assign_role` wordt alleen vanuit
    HTTP-endpoints aangeroepen. Gemeten stand op staging:

        users       1   (admin@sanskritisetu.org, is_superuser = True)
        roles       3   (admin, editor, user)
        user_roles  0   <-- leeg

    Gevolg: inloggen lukt, maar het token krijgt alleen `users:read`. `_get_user_scopes`
    (`router_login.py:133`) leidt scopes UITSLUITEND af uit `user.roles`, en
    `scope_validator` kent geen uitzondering voor `is_superuser`. Elk endpoint met een
    scope antwoordt daarom 403:

        WARNING | User 1 missing scope OAuth2Scope.AGENTS_READ

    De beheerder kon dus inloggen en verder niets. Met de rol `admin` gekoppeld lost de
    databasefallback in `scope_validator` het wel op: `ensure_default_roles` geeft die rol
    een `*`/`*`-permissierij en `user_has_permission` matcht daar letterlijk op
    (`rbac_service.py:139` e.v.).

    WAAROM ALLEEN BIJ NUL ROLLEN.
    Dit is een BOOTSTRAP, geen handhaving. Heeft het account al een rol -- ook een andere,
    ook een beperktere -- dan blijft die staan. Anders zou een beheerder die deze rechten
    bewust heeft ingetrokken ze bij de eerstvolgende herstart stil terugkrijgen, en dat is
    een rechtenverhoging die niemand heeft aangevraagd.

    `tenant_id` komt uit de database (de lus in `_seed_default_roles`), nooit uit invoer.
    Deze functie draait al BINNEN een `adopt_tenant`-blok van de aanroeper.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from src.core.database.seed import DEFAULT_ADMIN_EMAIL
    from src.core.models.rbac_models import User

    resultaat = await session.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.email == DEFAULT_ADMIN_EMAIL, User.tenant_id == tenant_id)
    )
    beheerder = resultaat.scalar_one_or_none()

    if beheerder is None:
        logger.info(
            "[SEED] geen gezaaide beheerder in tenant %s -- geen rol te koppelen", tenant_id
        )
        return

    if beheerder.roles:
        logger.debug(
            "[SEED] beheerder %s heeft al rollen (%s) -- ongemoeid gelaten",
            DEFAULT_ADMIN_EMAIL,
            [r.name for r in beheerder.roles],
        )
        return

    gelukt = await rbac.assign_role(beheerder.id, "admin", tenant_id)
    # De gezaaide beheerder heeft de vlag `is_superuser` en IS dus een platformbeheerder; het gezag om
    # platformrollen uit te delen is de ROL `system_admin` (OP-189), en zonder die rol zou het enige
    # platformaccount niemand kunnen aanwijzen. Alleen in deze bootstrap-tak (nul rollen): een bestaand
    # account dat al rollen heeft wordt niet bij elke herstart stil verhoogd (brief 2026-10-19).
    if gelukt and getattr(beheerder, "is_superuser", False):
        await rbac.ensure_platform_role(tenant_id)
        if not await rbac.assign_role(beheerder.id, "system_admin", tenant_id):
            logger.error(
                "[SEED] [FAIL] kon de rol 'system_admin' niet koppelen aan %s in tenant %s",
                DEFAULT_ADMIN_EMAIL,
                tenant_id,
            )
    if gelukt:
        logger.info(
            "[SEED] [OK] gezaaide beheerder %s gekoppeld aan de rol 'admin' in tenant %s",
            DEFAULT_ADMIN_EMAIL,
            tenant_id,
        )
    else:
        logger.error(
            "[SEED] [FAIL] kon de rol 'admin' niet koppelen aan %s in tenant %s -- "
            "die beheerder kan inloggen maar krijgt op elk endpoint met een scope een 403",
            DEFAULT_ADMIN_EMAIL,
            tenant_id,
        )


async def _verify_critical_data() -> None:
    """
    Verify that critical data exists after seeding.
    Raises RuntimeError if data is missing - this BLOCKS app startup.
    """
    from sqlalchemy import text

    from src.core.database.bypass_session import adopt_tenant

    try:
        async with db_manager.get_session() as session:
            # Check default tenant -- BUITEN de aangenomen klant, en dat kan ook:
            # `tenants` heeft geen afschermingsregel (gemeten 2026-09-17 op staging:
            # als `sanskritisetu_app` zonder klantcontext is de rij gewoon zichtbaar).
            result = await session.execute(
                text("SELECT id, slug FROM tenants WHERE slug = 'default'")
            )
            tenant_row = result.fetchone()

            if not tenant_row:
                raise RuntimeError(
                    "CRITICAL: Default tenant does not exist after seeding. "
                    "Database seeding failed. Check logs for errors."
                )

            tenant_id = tenant_row[0]
            logger.info("[OK] Verified: Default tenant exists (id=%s)", tenant_id)

            # Check admin user -- BINNEN de aangenomen klant (ADR-036 OP-153).
            #
            # `users` heeft wel een afschermingsregel. Deze controle draait bij het
            # OPSTARTEN, buiten elk verzoek, dus de ContextVar is leeg en de regel geeft
            # nul rijen. Zonder klantcontext concludeert deze functie daardoor dat de
            # beheerder niet bestaat terwijl hij er gewoon staat, en weigert de applicatie
            # te starten.
            #
            # Gemeten 2026-09-17 als `sanskritisetu_app` tegen de staging-database:
            #     users ZONDER klantcontext   0
            #     users MET klantcontext 1    1
            #
            # Dit is de TWEEDE plek met dezelfde oorzaak; de eerste zit in
            # `src/core/database/seed.py`. Beide schrijven/lezen met rauwe SQL, en dat was
            # precies het vocabulaire dat `scripts/triage_tenantcontext_schrijfpaden.py`
            # niet kende -- die zocht alleen ORM-aanroepen. Dat gat is in dezelfde ronde
            # gedicht.
            #
            # `tenant_id` komt uit de database hierboven, nooit uit invoer.
            async with adopt_tenant(session, tenant_id):
                result = await session.execute(
                    text(
                        "SELECT id, email FROM users WHERE email = 'admin@sanskritisetu.org' AND tenant_id = :tid"
                    ),
                    {"tid": tenant_id},
                )
                user_row = result.fetchone()

            if not user_row:
                raise RuntimeError(
                    "CRITICAL: Admin user does not exist after seeding. "
                    "Database seeding failed. Check logs for errors."
                )

            user_id = user_row[0]
            logger.info("[OK] Verified: Admin user exists (id=%s, email=%s)", user_id, user_row[1])
            logger.info("[OK] Critical data verification PASSED - App is safe to start")

    except RuntimeError:
        raise  # Re-raise critical errors
    except Exception as e:
        raise RuntimeError(f"Failed to verify critical data: {e}")


async def _seed_platform_templates() -> None:
    """Zaait de platformsjablonen (idempotent: bestaande namen worden overgeslagen).

    Zonder deze stap toont de onboarding 0 sjablonen: `seed_platform_templates` had geen
    aanroeper in `src/` (gemeten 2026-10-04). Hoort bij het zaaien van de beginstand en dus
    niet bij `_seed_default_roles`: die draait ook los, en moet geen sjablonen schrijven.

    OPEN PUNT (OP-151): de zaaier gebruikt `TenantFilterBypass`, dat alleen de ORM-hook
    uitzet. Onder de applicatierol `sanskritisetu_app` is die omzeiling niet gemeten.
    BEKENDE BEPERKING: in modus `development` slaat `_seed_initial_data` het zaaien over
    als de standaardtenant al bestaat; een oude ontwikkeldatabase krijgt de sjablonen dan
    pas na een schone start.
    """
    from src.core.company.seed_templates import seed_platform_templates

    try:
        async with db_manager.get_session() as session:
            aantal = await seed_platform_templates(session)
        logger.info("[SEED] platform templates seeded (%s new)", aantal)
    except Exception as e:
        logger.error(
            "[SEED] platform templates seeding failed: %s: %s", type(e).__name__, e, exc_info=True
        )


async def _seed_initial_data_with_retry(max_attempts: int = 3) -> None:
    """
    Seed initial data with retry logic and verification.
    Raises exception if seeding fails after all retries.
    """
    import asyncio

    from src.core.database.seed import seed_database

    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("[SEED] Attempt %s/%s: Starting database seeding...", attempt, max_attempts)

            # Use a new session for seeding
            async with db_manager.get_session() as session:
                success = await seed_database(session)

                if not success:
                    raise RuntimeError("seed_database() returned False")

            # Verify that data was actually created
            await _verify_critical_data()

            # Na de controle en BUITEN de pogingenlus-fout: een mislukte sjabloonzaaiing mag
            # het opstarten niet stoppen en geen nieuwe poging van het zaaien uitlokken.
            await _seed_platform_templates()

            logger.info("[SEED] [OK] Seeding completed successfully on attempt %s", attempt)
            return  # Success - exit function

        except Exception as e:
            logger.error(
                "[SEED] Attempt %s failed: %s: %s", attempt, type(e).__name__, e, exc_info=True
            )

            if attempt == max_attempts:
                logger.critical(
                    "[SEED] [FAIL] Database seeding failed after %s attempts. "
                    "App cannot start safely. Last error: %s: %s",
                    max_attempts,
                    type(e).__name__,
                    e,
                )
                raise RuntimeError(
                    f"Database seeding failed after {max_attempts} attempts. "
                    f"Cannot start application without admin user. Check logs."
                ) from e

            # Exponential backoff
            wait_seconds = 2**attempt
            logger.warning("[SEED] Retrying in %s seconds...", wait_seconds)
            await asyncio.sleep(wait_seconds)


async def _default_tenant_exists() -> bool:
    """Check if default tenant already exists (cheap guard for seed skip)."""
    from sqlalchemy import text

    try:
        async with db_manager.get_session() as session:
            result = await session.execute(
                text("SELECT 1 FROM tenants WHERE slug = 'default' LIMIT 1")
            )
            return result.fetchone() is not None
    except Exception:
        return False


async def _seed_initial_data() -> None:
    """Seed initial data, skipping in development when data already exists."""
    if ENVIRONMENT == "development":
        if await _default_tenant_exists():
            logger.info("Development mode: default tenant exists, skipping seed")
            return

    await _seed_initial_data_with_retry()


async def _init_agent_health_write_bridge(app: FastAPI) -> None:
    """Initialize AgentHealthMonitor write-bridge per tenant."""
    try:
        from sqlalchemy import text

        from src.core.agents.agent_health_monitor_agent import get_health_monitor
        from src.core.agents.agent_router_agent import get_agent_router
        from src.core.database.redis import get_redis_client
        from src.core.database.session import get_db_session

        async with db_manager.get_session() as session:
            result = await session.execute(text("SELECT id FROM tenants"))
            tenant_ids = [r[0] for r in result.all()]

        # SP-ADR023-002 Dag 2: this warmup loop runs for every existing tenant at
        # startup and therefore almost always wins the AgentRouterAgent singleton's
        # first-creation-wins race -- without redis_client here, the cross-worker
        # routing cache would never activate for any pre-existing tenant.
        redis_client = await get_redis_client()

        for tenant_id in tenant_ids:
            router = get_agent_router(
                tenant_id, async_session_factory=get_db_session, redis_client=redis_client
            )
            monitor = get_health_monitor(tenant_id, router_ref=router)
            # Voer een eerste check uit (pusht status buiten lock) -- zie CG-005
            await monitor._check_all()
            # Start de monitoring loop voor continue updates
            await monitor.start()

        logger.info(
            "[OK] AgentHealthMonitor write-bridge initialized for %s tenants", len(tenant_ids)
        )
    except Exception as e:
        logger.warning(
            "AgentHealthMonitor write-bridge initialization failed: %s: %s", type(e).__name__, e
        )


async def _init_guna_router(app: FastAPI) -> None:
    """
    Initialize GunaRouter (Semantic + Deterministic hybrid).

    This is the Rajasic layer that provides intelligent routing.
    """
    try:
        from src.core.semantic_router.hybrid_router import create_guna_router

        # Create router for default tenant (others created on-demand)
        guna_router = await create_guna_router(tenant_id=1)

        # Store in app state
        app.state.guna_router = guna_router

        logger.info("[OK] GunaRouter initialized (Tamasic + Rajasic)")

    except Exception as e:
        logger.error("GunaRouter initialization failed: %s: %s", type(e).__name__, e, exc_info=True)
        # Non-fatal: app can function without semantic routing


async def _init_event_system(app: FastAPI) -> None:
    """
    Initialize event system with handlers in monolith.

    Gebruikt Redis Pub/Sub voor interne event afhandeling (ADR-006).
    """
    try:
        from src.core.events import get_event_consumer, get_pubsub_manager
        from src.core.events.handlers import (
            AgentEventHandler,
            AuditEventHandler,
            NotificationEventHandler,
            TaskEventHandler,
            WorkflowEventHandler,
        )

        # Initialize Redis Pub/Sub
        pubsub = await get_pubsub_manager()

        # Register Redis Pub/Sub event handlers (consumers in monolith)
        workflow_handler = WorkflowEventHandler(pubsub)
        notification_handler = NotificationEventHandler(pubsub)
        agent_handler = AgentEventHandler(pubsub)
        task_handler = TaskEventHandler(pubsub)
        audit_handler = AuditEventHandler(pubsub)

        await workflow_handler.register_handlers()
        await notification_handler.register_handlers()
        await agent_handler.register_handlers()
        await task_handler.register_handlers()
        await audit_handler.register_handlers()

        # Store handlers in app state for access
        app.state.event_handlers = {
            "workflow": workflow_handler,
            "notification": notification_handler,
            "agent": agent_handler,
            "task": task_handler,
            "audit": audit_handler,
        }

        logger.info("[OK] Redis Pub/Sub event handlers initialized")

        # Maak consumer status tracker aan (health endpoint gebruikt _connected/get_stats)
        event_consumer = await get_event_consumer(pubsub_manager=pubsub)
        await event_consumer.connect()
        app.state.event_consumer = event_consumer

        logger.info("[OK] Event system initialized (Redis Pub/Sub)")

    except Exception as e:
        logger.error(
            "Event system initialization failed: %s: %s", type(e).__name__, e, exc_info=True
        )
        # Non-fatal: app can still function without event system


async def _init_twin_event_bridge(app: FastAPI) -> None:
    """Initialize TwinEventBridge in the background to avoid blocking startup."""

    async def _background_init() -> None:
        try:
            from src.core.learning.wiring.twin_event_bridge import get_twin_event_bridge

            bridge = await get_twin_event_bridge()
            app.state.twin_event_bridge = bridge
            logger.info("[OK] TwinEventBridge initialized")
        except Exception as e:
            logger.error(
                "TwinEventBridge initialization failed: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
            # Non-fatal: app can function without twin event forwarding

    asyncio.create_task(_background_init())
    logger.info("TwinEventBridge background initialization started")


async def _cleanup_batch_manager() -> None:
    """Shutdown ObservationBatchManager singleton."""
    try:
        from src.core.learning.batching.batch_manager import shutdown_batch_manager

        await shutdown_batch_manager()
        logger.info("[OK] ObservationBatchManager stopped")
    except Exception as e:
        logger.warning("ObservationBatchManager cleanup failed: %s", e)


async def _cleanup_twin_event_bridge() -> None:
    """Shutdown TwinEventBridge."""
    try:
        from src.core.learning.wiring.twin_event_bridge import shutdown_twin_event_bridge

        await shutdown_twin_event_bridge()
        logger.info("[OK] TwinEventBridge stopped")
    except Exception as e:
        logger.warning("TwinEventBridge cleanup failed: %s", e)


async def _init_alert_notification_bridge(app: FastAPI) -> None:
    """Wire AlertManager to NotificationService for real alert delivery."""
    try:
        from src.core.connectors.notification import NotificationService
        from src.core.connectors.resolver import ProviderResolver
        from src.core.observability.alert_manager import AlertManager
        from src.core.observability.alert_notification_bridge import (
            AlertNotificationBridge,
        )

        alert_manager = AlertManager()
        resolver = ProviderResolver(tenant_id="system")
        notification_service = NotificationService(resolver)

        bridge = AlertNotificationBridge(alert_manager, notification_service)

        app.state.alert_manager = alert_manager
        app.state.notification_service = notification_service
        app.state.alert_bridge = bridge

        logger.info("[OK] AlertNotificationBridge initialized")
    except Exception as e:
        logger.warning(
            "AlertNotificationBridge initialization failed: %s: %s",
            type(e).__name__,
            e,
        )


async def _init_council_warmup() -> None:
    """Warm de council op, zodat het eerste voorstel na een herstart niet door koude kosten een TIMEOUT-veto krijgt."""
    # Alles binnen de try: de opwarming is een versnelling, geen voorwaarde. Een importfout mag het opstarten niet stoppen
    # (de init-lus raiset elke fout opnieuw).
    try:
        from src.core.copilot.council.factory import warm_up_risk_register
        from src.core.database.database import db_manager

        session_maker = db_manager.async_session_maker
        if session_maker is None:
            logger.warning("Council-opwarming overgeslagen: geen database-sessiefabriek")
            return
        gelukt = await warm_up_risk_register(session_maker)
        # f-string: de logging van deze app vult %-argumenten niet in (zie de regel "total startup: %.2fs" in de log).
        logger.info(f"Council opgewarmd: {'ja' if gelukt else 'nee, zie waarschuwing'}")
    except Exception as exc:
        logger.warning(
            "Council-opwarming mislukt: %s: %s", type(exc).__name__, exc, exc_info=True
        )


async def _init_council_cache_invalidator(app: FastAPI) -> None:
    """Wire Council cache invalidator to event bus for cache flushes."""
    try:
        from src.core.caching import get_cache_manager  # type: ignore[attr-defined]
        from src.core.copilot.council.cache import OfficerVerdictCache
        from src.core.copilot.council.cache_invalidator import (
            CacheInvalidator,
            get_cache_invalidation_event_bus,
        )

        cache_layer = get_cache_manager()
        if cache_layer.redis_client is None:
            logger.warning("Council cache invalidator: Redis not available, skipping")
            return

        from typing import cast

        from redis.asyncio import Redis

        council_cache = OfficerVerdictCache(cast(Redis, cache_layer.redis_client))  # type: ignore[type-arg]
        invalidator = CacheInvalidator(council_cache)
        event_bus = get_cache_invalidation_event_bus()

        event_bus.subscribe("rbac.role_changed", invalidator.on_role_changed)
        event_bus.subscribe("toolbroker.allowlist_updated", invalidator.on_allowlist_updated)
        event_bus.subscribe("tenant.policy_updated", invalidator.on_policy_updated)

        app.state.council_cache = council_cache
        app.state.council_cache_invalidator = invalidator

        logger.info("[OK] Council cache invalidator initialized with 3 event subscribers")
    except Exception as e:
        logger.warning(
            "Council cache invalidator initialization failed: %s: %s",
            type(e).__name__,
            e,
        )


async def _init_proactive_deps(app: FastAPI) -> None:
    """Wire app.state dependencies required by ProactiveScheduler (WE-020/021).

    Sets app.state.copilot_service, notification_dispatcher, tenant_repo,
    redis_client. All use session-factory pattern to avoid long-lived DB sessions.
    """
    try:
        from src.core.copilot.notification.budget import NotificationBudgetTracker
        from src.core.copilot.notification.digest import DigestQueue
        from src.core.copilot.notification.dispatcher import NotificationDispatcher
        from src.core.copilot.notification.preferences_repo import (
            UserNotificationPreferencesRepo,
        )
        from src.core.copilot.notification.ws_pusher import WSPusher
        from src.core.copilot.proactive.deps import _DBTenantRepo, _ProactiveServiceProxy
        from src.core.database.session import get_db_session
        from src.core.database.redis import get_redis_client

        redis_client = await get_redis_client()
        app.state.redis_client = redis_client

        # Build notification components (Redis-backed, no DB session needed)
        ws_pusher = WSPusher(redis=redis_client)
        digest_queue = DigestQueue(redis=redis_client)
        budget_tracker = NotificationBudgetTracker(redis_client)

        # PrefsRepo wrapper: creates a fresh DB session per get_for_user() call.
        # Avoids holding a long-lived session across the scheduler lifetime.
        class _RefreshingPrefsRepo:
            async def get_for_user(self, user_id: int, tenant_id: int) -> object:
                async with get_db_session() as db:
                    repo = UserNotificationPreferencesRepo(db)
                    return await repo.get_for_user(user_id=user_id, tenant_id=tenant_id)

            async def save(self, prefs: object) -> None:
                async with get_db_session() as db:
                    repo = UserNotificationPreferencesRepo(db)
                    await repo.save(prefs)  # type: ignore[attr-defined]

        dispatcher = NotificationDispatcher(
            budget_tracker=budget_tracker,
            preferences_repo=_RefreshingPrefsRepo(),  # type: ignore[arg-type]
            ws_pusher=ws_pusher,
            digest_queue=digest_queue,
        )

        app.state.notification_dispatcher = dispatcher

        # TenantRepo and CopilotService proxy -- fresh session per call
        tenant_repo = _DBTenantRepo(session_factory=get_db_session)
        app.state.tenant_repo = tenant_repo

        service_proxy = _ProactiveServiceProxy(session_factory=get_db_session)
        app.state.copilot_service = service_proxy

        # SP-WE-21 (NEW-WIRE-004): wire the 9 additional app.state dependencies
        _wire_proactive_extras(app, session_factory=get_db_session)

        logger.info(
            "[OK] ProactiveScheduler dependencies initialized "
            "(copilot_service, notification_dispatcher, tenant_repo, redis_client, "
            "health_registry, failover_provider, prometheus_client, "
            "consent_repo, audit_repo, role_repo, workflow_repo, pii_scanner, dpia_repo)"
        )
    except Exception as exc:
        logger.warning(
            "_init_proactive_deps failed (non-fatal -- proactive monitors disabled): %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )


def _wire_proactive_extras(app: FastAPI, session_factory: object) -> None:
    """Wire the ProactiveScheduler dependencies missed by initial wiring (SP-WE-21).

    Sets:
      - app.state.health_registry      (InMemoryHealthMonitorRegistry)
      - app.state.failover_provider    (LLMFallbackChain via get_fallback_chain)
      - app.state.prometheus_client    (StubPrometheusClient)
      - app.state.consent_repo         (StubConsentRepo)
      - app.state.audit_repo           (StubAuditRepo)
      - app.state.role_repo            (StubRoleRepo)
      - app.state.workflow_repo        (StubWorkflowRepo)
      - app.state.pii_scanner          (StubWorkflowPIIScanner)
      - app.state.dpia_repo            (StubDPIARepo)

    Each assignment is guarded so a partial failure does not block the others.
    No app.state attribute is overwritten if already set by an earlier subsystem.
    """
    # 1. HealthMonitorRegistry (per SP-WE-18 contract; create here if absent)
    if getattr(app.state, "health_registry", None) is None:
        try:
            from src.core.als.registry import InMemoryHealthMonitorRegistry

            app.state.health_registry = InMemoryHealthMonitorRegistry()
            logger.info("ProactiveDeps: health_registry initialized (InMemory)")
        except Exception as exc:
            logger.warning(
                "ProactiveDeps: health_registry unavailable: %s: %s",
                type(exc).__name__,
                exc,
            )

    # 2. LLM Failover provider (reuse module-level singleton)
    if getattr(app.state, "failover_provider", None) is None:
        try:
            from src.core.llm.fallback_chain import get_fallback_chain

            app.state.failover_provider = get_fallback_chain()
            logger.info("ProactiveDeps: failover_provider initialized")
        except Exception as exc:
            logger.warning(
                "ProactiveDeps: failover_provider unavailable: %s: %s",
                type(exc).__name__,
                exc,
            )

    # 3. Prometheus client (stub: no real metrics until full impl is wired)
    if getattr(app.state, "prometheus_client", None) is None:
        try:
            from src.core.copilot.proactive.stub_repos import StubPrometheusClient

            app.state.prometheus_client = StubPrometheusClient()
            logger.info("ProactiveDeps: prometheus_client initialized (stub)")
        except Exception as exc:
            logger.warning(
                "ProactiveDeps: prometheus_client unavailable: %s: %s",
                type(exc).__name__,
                exc,
            )

    # 4-9. Repositories and PII scanner (all stubs returning empty results).
    try:
        from src.core.copilot.proactive.stub_repos import (
            StubAuditRepo,
            StubConsentRepo,
            StubDPIARepo,
            StubRoleRepo,
            StubWorkflowPIIScanner,
            StubWorkflowRepo,
        )

        if getattr(app.state, "consent_repo", None) is None:
            app.state.consent_repo = StubConsentRepo(session_factory)
            logger.info("ProactiveDeps: consent_repo initialized (stub)")

        if getattr(app.state, "audit_repo", None) is None:
            app.state.audit_repo = StubAuditRepo(session_factory)
            logger.info("ProactiveDeps: audit_repo initialized (stub)")

        if getattr(app.state, "role_repo", None) is None:
            app.state.role_repo = StubRoleRepo(session_factory)
            logger.info("ProactiveDeps: role_repo initialized (stub)")

        if getattr(app.state, "workflow_repo", None) is None:
            app.state.workflow_repo = StubWorkflowRepo(session_factory)
            logger.info("ProactiveDeps: workflow_repo initialized (stub)")

        if getattr(app.state, "pii_scanner", None) is None:
            app.state.pii_scanner = StubWorkflowPIIScanner()
            logger.info("ProactiveDeps: pii_scanner initialized (stub)")

        if getattr(app.state, "dpia_repo", None) is None:
            app.state.dpia_repo = StubDPIARepo(session_factory)
            logger.info("ProactiveDeps: dpia_repo initialized (stub)")
    except Exception as exc:
        logger.warning(
            "ProactiveDeps: stub repositories unavailable: %s: %s",
            type(exc).__name__,
            exc,
        )


async def _init_proactive_scheduler(app: FastAPI) -> None:
    """Start ProactiveScheduler with interval-based proactive monitors.

    Event-driven monitors (interval_seconds=0) are handled by
    _init_compliance_monitors(). Only interval-based monitors are
    registered with APScheduler here.
    """
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        from src.core.copilot.proactive.scheduler import ProactiveScheduler

        # Core dependencies -- shared with compliance monitors
        copilot_service = getattr(app.state, "copilot_service", None)
        dispatcher = getattr(app.state, "notification_dispatcher", None)
        tenant_repo = getattr(app.state, "tenant_repo", None)
        redis_client = getattr(app.state, "redis_client", None)

        if copilot_service is None or dispatcher is None:
            logger.info(
                "ProactiveScheduler: copilot_service or dispatcher not ready, "
                "skipping (will be started when services are available)"
            )
            return

        if tenant_repo is None:
            logger.warning("ProactiveScheduler: tenant_repo not available, skipping")
            return

        if redis_client is None:
            logger.warning("ProactiveScheduler: Redis not available, skipping")
            return

        # Build interval-based monitors one-by-one so a missing protocol
        # dependency for one monitor does not kill the others.
        monitors: list[Any] = []  # TODO(TYPE): replace Any with concrete type

        # Platform monitors
        try:
            from src.core.copilot.proactive.monitors.agent_health import (
                AgentHealthMonitor,
            )

            health_registry = getattr(app.state, "health_registry", None)
            if health_registry is not None:
                monitors.append(
                    AgentHealthMonitor(
                        copilot_service,
                        dispatcher,
                        health_registry,
                        tenant_repo,
                        redis_client,
                    )
                )
            else:
                logger.info(
                    "ProactiveScheduler: health_registry not available, skipping AgentHealthMonitor"
                )
        except Exception as e:
            logger.warning(
                "ProactiveScheduler: AgentHealthMonitor skipped: %s: %s",
                type(e).__name__,
                e,
            )

        try:
            from src.core.copilot.proactive.monitors.circuit_breaker import (
                CircuitBreakerMonitor,
            )

            failover_provider = getattr(app.state, "failover_provider", None)
            if failover_provider is not None:
                monitors.append(
                    CircuitBreakerMonitor(
                        copilot_service,
                        dispatcher,
                        failover_provider,
                        tenant_repo,
                        redis_client,
                    )
                )
            else:
                logger.info(
                    "ProactiveScheduler: failover_provider not available, "
                    "skipping CircuitBreakerMonitor"
                )
        except Exception as e:
            logger.warning(
                "ProactiveScheduler: CircuitBreakerMonitor skipped: %s: %s",
                type(e).__name__,
                e,
            )

        try:
            from src.core.copilot.proactive.monitors.queue_depth import (
                QueueDepthMonitor,
            )

            queue_names = getattr(app.state, "dramatiq_queue_names", ["default", "high", "low"])
            monitors.append(
                QueueDepthMonitor(
                    copilot_service,
                    dispatcher,
                    tenant_repo,
                    redis_client,
                    queue_names,
                )
            )
        except Exception as e:
            logger.warning(
                "ProactiveScheduler: QueueDepthMonitor skipped: %s: %s",
                type(e).__name__,
                e,
            )

        try:
            from src.core.copilot.proactive.monitors.token_spike import (
                TokenSpikeMonitor,
            )
            from src.core.copilot.proactive.monitors.workflow_latency import (
                WorkflowLatencyMonitor,
            )

            prom_client = getattr(app.state, "prometheus_client", None)
            if prom_client is not None:
                monitors.append(
                    WorkflowLatencyMonitor(
                        copilot_service,
                        dispatcher,
                        prom_client,
                        tenant_repo,
                        redis_client,
                    )
                )
                monitors.append(
                    TokenSpikeMonitor(
                        copilot_service,
                        dispatcher,
                        prom_client,
                        tenant_repo,
                        redis_client,
                    )
                )
            else:
                logger.info(
                    "ProactiveScheduler: prometheus_client not available, "
                    "skipping WorkflowLatencyMonitor and TokenSpikeMonitor"
                )
        except Exception as e:
            logger.warning(
                "ProactiveScheduler: latency/token monitors skipped: %s: %s",
                type(e).__name__,
                e,
            )

        # Compliance monitors (interval-based)
        try:
            from src.core.copilot.proactive.monitors.consent_expiry import (
                ConsentExpiryMonitor,
            )

            consent_repo = getattr(app.state, "consent_repo", None)
            if consent_repo is not None:
                monitors.append(
                    ConsentExpiryMonitor(
                        copilot_service,
                        dispatcher,
                        tenant_repo,
                        redis_client,
                        consent_repo,
                    )
                )
            else:
                logger.info(
                    "ProactiveScheduler: consent_repo not available, skipping ConsentExpiryMonitor"
                )
        except Exception as e:
            logger.warning(
                "ProactiveScheduler: ConsentExpiryMonitor skipped: %s: %s",
                type(e).__name__,
                e,
            )

        try:
            from src.core.copilot.proactive.monitors.audit_anomaly import (
                AuditAnomalyMonitor,
            )

            audit_repo = getattr(app.state, "audit_repo", None)
            role_repo = getattr(app.state, "role_repo", None)
            if audit_repo is not None and role_repo is not None:
                monitors.append(
                    AuditAnomalyMonitor(
                        copilot_service,
                        dispatcher,
                        tenant_repo,
                        redis_client,
                        audit_repo,
                        role_repo,
                    )
                )
            else:
                logger.info(
                    "ProactiveScheduler: audit_repo or role_repo not available, "
                    "skipping AuditAnomalyMonitor"
                )
        except Exception as e:
            logger.warning(
                "ProactiveScheduler: AuditAnomalyMonitor skipped: %s: %s",
                type(e).__name__,
                e,
            )

        try:
            from src.core.copilot.proactive.monitors.sensitive_workflow import (
                SensitiveWorkflowMonitor,
            )

            workflow_repo = getattr(app.state, "workflow_repo", None)
            pii_scanner = getattr(app.state, "pii_scanner", None)
            dpia_repo = getattr(app.state, "dpia_repo", None)
            if workflow_repo is not None and pii_scanner is not None and dpia_repo is not None:
                monitors.append(
                    SensitiveWorkflowMonitor(
                        copilot_service,
                        dispatcher,
                        tenant_repo,
                        redis_client,
                        workflow_repo,
                        pii_scanner,
                        dpia_repo,
                    )
                )
            else:
                logger.info(
                    "ProactiveScheduler: workflow_repo, pii_scanner or dpia_repo "
                    "not available, skipping SensitiveWorkflowMonitor"
                )
        except Exception as e:
            logger.warning(
                "ProactiveScheduler: SensitiveWorkflowMonitor skipped: %s: %s",
                type(e).__name__,
                e,
            )

        if not monitors:
            logger.info(
                "ProactiveScheduler: no interval-based monitors available, skipping scheduler start"
            )
            return

        apsched = AsyncIOScheduler()
        scheduler = ProactiveScheduler(
            scheduler=apsched,
            tenant_repo=tenant_repo,
            monitors=monitors,
        )
        scheduler.start()
        app.state.proactive_scheduler = scheduler

        logger.info(
            "[OK] ProactiveScheduler started with %d interval-based monitors",
            len(monitors),
        )
    except Exception as e:
        logger.warning(
            "ProactiveScheduler initialization failed (non-fatal): %s: %s",
            type(e).__name__,
            e,
        )


async def _cleanup_proactive_scheduler(app: FastAPI) -> None:
    """Gracefully shutdown ProactiveScheduler."""
    try:
        scheduler = getattr(app.state, "proactive_scheduler", None)
        if scheduler is not None:
            scheduler.shutdown(wait=True)
            logger.info("[OK] ProactiveScheduler shut down")
    except Exception as e:
        logger.warning(
            "ProactiveScheduler shutdown failed: %s: %s",
            type(e).__name__,
            e,
        )


async def _init_compliance_monitors(app: FastAPI) -> None:
    """Wire event-driven compliance monitors to the shared event bus.

    Event-driven monitors (interval_seconds=0) subscribe in __init__ and
    are stored in app.state so they are not garbage-collected.
    Interval-based compliance monitors are handled by ProactiveScheduler.
    """
    try:
        from src.core.copilot.council.cache_invalidator import (
            SimpleEventBus,
            get_cache_invalidation_event_bus,
        )
        from src.core.copilot.proactive.monitors import (
            DSARExportMonitor,
            PolicyChangeMonitor,
        )

        # Reuse the existing SimpleEventBus (compliance events are in-process)
        event_bus: SimpleEventBus = get_cache_invalidation_event_bus()

        # Placeholder services -- real wiring happens when CopilotService
        # and NotificationDispatcher are fully integrated in Sprint 5 Day 4.
        copilot_service = getattr(app.state, "copilot_service", None)
        dispatcher = getattr(app.state, "notification_dispatcher", None)

        # If services are not yet available, skip wiring but log it.
        # Monitors can be instantiated later by the scheduler factory.
        if copilot_service is None or dispatcher is None:
            logger.info(
                "Compliance monitors: copilot_service or dispatcher not ready, "
                "skipping event-driven wiring (will be done by scheduler factory)"
            )
            return

        # Tenant repo is required for admin lookups.
        tenant_repo = getattr(app.state, "tenant_repo", None)
        if tenant_repo is None:
            logger.warning("Compliance monitors: tenant_repo not available, skipping")
            return

        redis_client = getattr(app.state, "redis_client", None)
        if redis_client is None:
            logger.warning("Compliance monitors: Redis not available, skipping")
            return

        dsar_monitor = DSARExportMonitor(
            copilot_service, dispatcher, tenant_repo, redis_client, event_bus
        )
        policy_monitor = PolicyChangeMonitor(
            copilot_service, dispatcher, tenant_repo, redis_client, event_bus
        )

        app.state.compliance_monitors = {
            "dsar_export": dsar_monitor,
            "policy_change": policy_monitor,
        }

        logger.info(
            "[OK] Compliance monitors wired: dsar_export + policy_change (%d event subscribers)",
            len(event_bus._subscribers),
        )
    except Exception as e:
        logger.warning(
            "Compliance monitors initialization failed: %s: %s",
            type(e).__name__,
            e,
        )


async def _init_llm_service() -> None:
    """Initialize LLM service with futureproof guarantees.

    This function ensures an LLM provider is ALWAYS available.
    Never fails - falls back through multiple providers to Mock as last resort.
    """
    try:
        from src.core.llm.llm_config import get_llm_service

        logger.info("Initializing Futureproof LLM Service...")
        service = await get_llm_service()
        health = await service.health_check()

        logger.info("=" * 60)
        logger.info("[OK] LLM Service Status: %s", health["status"].upper())
        logger.info("   Provider: %s", health["provider"])
        logger.info("   Model: %s", health["model"])
        logger.info("   Initialized: %s", health["initialized"])
        logger.info("=" * 60)

        if health["status"] == "healthy":
            logger.info("[OK] LLM service fully operational")
        elif health["status"] == "degraded":
            logger.warning("[WARN] LLM service in degraded mode (using mock)")
        else:
            logger.error("[ERROR] LLM service has issues but is functional")

    except Exception as e:
        logger.critical(
            "CRITICAL: LLM service initialization failed: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
        )
        logger.critical("Application may not function correctly without LLM")


async def _init_feature_flags(app: FastAPI) -> None:
    """Initialize FeatureFlagManager and store in app.state.ff_manager."""
    try:
        from src.core.database.redis import get_redis_client
        from src.core.feature_flags import FeatureFlagManager

        redis_client = await get_redis_client()
        ff_manager = FeatureFlagManager(redis_client=redis_client)
        app.state.ff_manager = ff_manager
        logger.info("[OK] FeatureFlagManager initialized in app.state")
    except Exception as e:
        logger.warning(
            "FeatureFlagManager initialization failed (using fallback): %s: %s",
            type(e).__name__,
            e,
        )
        from src.core.feature_flags import FeatureFlagManager

        app.state.ff_manager = FeatureFlagManager()


# =============================================================================
# SHUTDOWN HELPERS
# =============================================================================


async def _cleanup_redis() -> None:
    """Disconnect all Redis services."""
    try:
        cache = await get_cache()
        await cache.disconnect()
        logger.info("Redis cache disconnected")
    except Exception as e:
        logger.warning("Failed to disconnect Redis cache: %s: %s", type(e).__name__, e)

    try:
        session_manager = await get_session_manager()
        await session_manager.disconnect()
        logger.info("Redis session manager disconnected")
    except Exception as e:
        logger.warning("Failed to disconnect Redis session manager: %s: %s", type(e).__name__, e)

    try:
        pubsub = await get_pubsub_manager()
        await pubsub.disconnect()
        logger.info("Redis pub/sub manager disconnected")
    except Exception as e:
        logger.warning("Failed to disconnect Redis pub/sub manager: %s: %s", type(e).__name__, e)


async def _cleanup_event_publisher() -> None:
    """Disconnect event publisher if active."""
    try:
        from src.core.events import get_event_publisher

        event_publisher = await get_event_publisher()
        await event_publisher.disconnect()
    except Exception as e:
        logger.warning("Failed to disconnect event publisher: %s: %s", type(e).__name__, e)


async def _cleanup_event_consumer() -> None:
    """Disconnect event consumer if active."""
    try:
        from src.core.events import get_event_consumer

        event_consumer = await get_event_consumer()
        await event_consumer.disconnect()
        logger.info("Event consumer disconnected")
    except Exception as e:
        logger.warning("Failed to disconnect event consumer: %s: %s", type(e).__name__, e)


async def _cleanup_activepieces() -> None:
    """Gracefully cleanup ActivePieces client and circuit breaker."""
    try:
        from src.core.activepieces.client import ActivePiecesClient

        # Reset the singleton circuit breaker to clean state
        for breaker in ActivePiecesClient._circuit_breakers.values():
            cb_state = breaker.get_state()
            logger.info(
                "activepieces_shutdown",
                circuit_state=cb_state.get("state"),
                failure_count=cb_state.get("failure_count"),
            )
        # Reset to allow fresh start on next startup
        ActivePiecesClient._circuit_breakers.clear()
        logger.info("ActivePieces circuit breakers reset")
    except Exception as e:
        logger.warning("Failed to cleanup ActivePieces client: %s: %s", type(e).__name__, e)


async def _cleanup_guna_router() -> None:
    """Cleanup GunaRouter resources."""
    try:
        # Close any open embedder sessions
        # NOTE: In full implementation, track all routers per tenant and close each one
        logger.info("GunaRouter cleanup completed")
    except Exception as e:
        logger.warning("Failed to cleanup GunaRouter: %s: %s", type(e).__name__, e)


async def _cleanup_tenant_factories() -> None:
    """Cleanup cached tenant-specific factory instances on shutdown."""
    try:
        from src.core.memory.factory import _tenant_memory_managers

        for mm in _tenant_memory_managers.values():
            try:
                await mm.cleanup()
            except Exception:
                pass
        _tenant_memory_managers.clear()

        from src.core.strategy.factory import _tenant_strategy_engines

        _tenant_strategy_engines.clear()

        from src.core.agents.learning_loop import _tenant_learning_loops

        _tenant_learning_loops.clear()

        logger.info("Tenant factory caches cleaned up")
    except Exception as e:
        logger.warning("Failed to cleanup tenant factories: %s: %s", type(e).__name__, e)


# =============================================================================
# MAIN LIFESPAN CONTEXT MANAGER
# =============================================================================


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan context manager for application lifecycle.

    Handles startup (before yield) and shutdown (after yield) phases.
    """
    # === STARTUP PHASE ===
    configure_logging()
    startup_start = time.perf_counter()
    logger.info("[START] Starting up FastAPI application...")

    # Wire dependency injection container before any request arrives
    from src.main import wire_container

    wire_container()

    # NOTE: register_all_routers(app) is now called synchronously in create_app()
    # per ADR-033: router registration must happen before lifespan (before ASGI stack starts).
    # Keeping this comment so future readers know it was intentionally moved.

    is_test_mode = os.getenv("TESTING") == "1" or "PYTEST_CURRENT_TEST" in os.environ

    # Mails (uitnodiging, wachtwoordherstel) bevatten een link naar de frontend. Zonder FRONTEND_URL buiten een zachte omgeving
    # zou die naar localhost wijzen en voor een medewerker niets waard zijn: liever niet starten dan stil verkeerde links sturen.
    if not is_test_mode:
        try:
            frontend_url(ENVIRONMENT)
        except FrontendUrlOntbreekt as fout:
            logger.critical("[FATAL] %s", fout)
            sys.exit(1)

    # CRITICAL: Database must initialize or we exit
    t0 = time.perf_counter()
    db_initialized = await _init_database()
    logger.info("[STARTUP] _init_database took %.2fs", time.perf_counter() - t0)
    if not db_initialized:
        if is_test_mode:
            logger.warning(
                "Database not available during test startup; continuing in degraded test mode"
            )
            app.state.ready = False
            yield
            logger.info("Application shutdown complete")
            return
        logger.critical("[ABORT] ABORTING STARTUP: Database not available")
        sys.exit(1)  # <- FAIL-FAST: Force container restart

    # Wire governance event handlers now that DB is ready (SP-DSM-006 ADR-034)
    from src.core.governance.event_handlers import register_governance_event_handlers

    register_governance_event_handlers()

    # Initialize services with timing logs.
    # De lijst is expliciet geannoteerd omdat hij kale coroutine-functies mengt met
    # wrappers die `app` meegeven; zonder annotatie kan mypy het lambda-type niet afleiden.
    # De wrappers stonden als `lambda app=app: ...` -- die default-arg-truc is hier
    # overbodig (`app` is de parameter van deze functie en wordt nergens herbonden) en
    # maakte de lambda's juist niet-afleidbaar.
    init_steps: list[tuple[str, Callable[[], Awaitable[None]]]] = [
        ("_init_tenant_filtering", _init_tenant_filtering),
        ("_init_redis_services", _init_redis_services),
        ("_init_ucr", lambda: _init_ucr(app)),
        ("_init_feature_flags", lambda: _init_feature_flags(app)),
        ("_seed_initial_data", _seed_initial_data),
        ("_seed_default_roles", _seed_default_roles),
        ("_init_event_system", lambda: _init_event_system(app)),
        ("_init_twin_event_bridge", lambda: _init_twin_event_bridge(app)),
        ("_init_alert_notification_bridge", lambda: _init_alert_notification_bridge(app)),
        ("_init_llm_service", _init_llm_service),
        ("_init_agent_health_write_bridge", lambda: _init_agent_health_write_bridge(app)),
        ("_init_guna_router", lambda: _init_guna_router(app)),
        ("_init_council_cache_invalidator", lambda: _init_council_cache_invalidator(app)),
        ("_init_council_warmup", _init_council_warmup),
        ("_init_proactive_deps", lambda: _init_proactive_deps(app)),
        ("_init_compliance_monitors", lambda: _init_compliance_monitors(app)),
        ("_init_proactive_scheduler", lambda: _init_proactive_scheduler(app)),
    ]

    for step_name, step_func in init_steps:
        t0 = time.perf_counter()
        try:
            await step_func()
        except Exception as e:
            logger.error(
                "[STARTUP] %s failed after %.2fs: %s: %s",
                step_name,
                time.perf_counter() - t0,
                type(e).__name__,
                e,
            )
            raise
        logger.info("[STARTUP] %s took %.2fs", step_name, time.perf_counter() - t0)

    total_startup = time.perf_counter() - startup_start
    app.state.ready = True
    logger.info("[OK] Application ready to accept requests (total startup: %.2fs)", total_startup)

    yield

    # === SHUTDOWN PHASE ===
    logger.info("Shutting down FastAPI application...")

    await _cleanup_batch_manager()
    await _cleanup_twin_event_bridge()
    await _cleanup_tenant_factories()
    await _cleanup_activepieces()
    await _cleanup_event_consumer()  # voor Redis sluiten
    await _cleanup_event_publisher()  # voor Redis sluiten
    await _cleanup_proactive_scheduler(app)
    await _cleanup_redis()
    await _cleanup_guna_router()
    await close_database()

    logger.info("Application shutdown complete")
