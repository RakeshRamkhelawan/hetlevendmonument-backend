"""
Unified Database Connection Manager - Centralized session management
Eliminates duplicate engines and standardizes session lifecycle
"""

import asyncio
import logging
import os
import sys
import warnings
from contextlib import asynccontextmanager
from typing import Any, cast
from collections.abc import AsyncGenerator

from fastapi import HTTPException
from sqlalchemy import event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import DisconnectionError, OperationalError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as SQLTimeoutError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql.dml import Insert

from src.core.config.unified_config import config
from .tenant_query_guard import register_query_guard
from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord

__all__ = [
    "config",
    "Base",
    "DatabaseManager",
    "db_manager",
    "initialize_database",
    "get_async_session",
    "get_db",
    "get_async_db",
    "get_redis",
    "close_database",
]

logger = logging.getLogger(__name__)

_module = sys.modules[__name__]
if __name__ == "core.database.database":
    sys.modules.setdefault("src.core.database.database", _module)
elif __name__ == "src.core.database.database":
    sys.modules.setdefault("core.database.database", _module)

# Declarative Base for async SQLAlchemy 2.0 models
# This Base is used for all new async models (RBAC, etc.)
# Legacy models in core/database/models.py use separate Base (to be migrated)
Base = declarative_base()


def _validate_als_security_insert(
    table_name: str,
    values: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> None:  # TODO(TYPE): replace Any with concrete type
    """Preserve legacy validation semantics for direct Core inserts used by security tests."""

    if table_name == "immune_antibodies":
        effectiveness = values.get("effectiveness")
        if effectiveness is not None and not 0.0 <= effectiveness <= 1.0:
            raise ValueError(f"Effectiveness must be between 0.0 and 1.0, got {effectiveness}")

        action_type = values.get("action_type")
        valid_actions = {
            "block",
            "rate_limit",
            "quarantine",
            "isolate_tenant",
            "alert",
            "circuit_break",
        }
        if action_type is not None and action_type not in valid_actions:
            raise ValueError(
                f"Invalid action_type: {action_type}. Must be one of {sorted(valid_actions)}"
            )

    if table_name == "organism_registry":
        status = values.get("status")
        valid_statuses = {"healthy", "stressed", "overloaded", "zombie", "recovering"}
        if status is not None and status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}. Must be one of {sorted(valid_statuses)}")

    if table_name == "signal_audit_log":
        tier = values.get("tier")
        valid_tiers = {"REFLEX", "COGNITIVE", "EMOTIONAL", "SYNAPTIC", "BROADCAST"}
        if tier is not None and tier not in valid_tiers:
            raise ValueError(f"Invalid tier: {tier}")


@event.listens_for(Engine, "before_execute", retval=True)
def _enforce_als_security_insert_validation(
    conn: Any,  # TODO(TYPE): replace Any with concrete type
    clauseelement: Any,  # TODO(TYPE): replace Any with concrete type
    multiparams: Any,  # TODO(TYPE): replace Any with concrete type
    params: Any,  # TODO(TYPE): replace Any with concrete type
    execution_options: Any,  # TODO(TYPE): replace Any with concrete type
) -> tuple[Any, Any, Any]:  # TODO(TYPE): replace Any with concrete type
    """Validate direct INSERT statements for ALS security models before execution."""

    if isinstance(clauseelement, Insert) and clauseelement.table is not None:
        table_name = clauseelement.table.name
        if table_name in {"immune_antibodies", "organism_registry", "signal_audit_log"}:
            compiled = clauseelement.compile(dialect=conn.dialect)
            _validate_als_security_insert(table_name, dict(compiled.params))

    return clauseelement, multiparams, params


@event.listens_for(Engine, "begin")
def _zet_tenantcontext(conn: Any) -> None:  # TODO(TYPE): replace Any with concrete type
    """Zet `app.current_tenant` bij het begin van ELKE transactie (ADR-036 OP-151).

    Row Level Security leest de tenant uit deze PostgreSQL-instelling. Zij stond eerder
    eenmalig, direct na het aanmaken van de sessie. Gemeten 2026-08-16:

        SET LOCAL app.current_tenant = '42'  -> current_setting(...) = '42'
        commit()                             -> current_setting(...) = ''   <-- weg

    `SET LOCAL` is transactie-gebonden. Zodra een endpoint zelf `await db.commit()` doet --
    de normale gang van zaken -- draaide de rest van dat verzoek dus ZONDER tenantcontext.
    Vandaag valt dat niet op omdat de applicatie als tabeleigenaar verbindt en PostgreSQL
    RLS voor de eigenaar overslaat; onder de rol `sanskritisetu_app` levert het nul rijen
    op zonder foutmelding.

    Drie keuzes die bewust zo zijn:

    - **Op de klasse `Engine`, niet op een enkele engine.** De codebase bouwt zestien
      engines op dezelfde `DATABASE_URL` (workers, read-replica, domeinisolatie). Een
      listener op alleen `db_manager`'s engine zou die allemaal missen, en dat is precies
      hoe een sessie stil zonder context komt te draaien.
    - **Er wordt ALTIJD iets gezet, ook zonder tenant.** Een lege waarde geeft via
      `NULLIF(..., '')` een NULL en dus nul rijen. Zou het event bij een lege ContextVar
      niets doen, dan blijft een eerdere sessie-brede `SET` staan en erft dit verzoek de
      tenant van het vorige -- een cross-tenant lek in plaats van een lege uitkomst.
    - **`set_config(..., true)` en geen `SET LOCAL ... = :t`.** PostgreSQL accepteert geen
      bindparameter in een utility-statement; gemeten op het echte pad (asyncpg) gaf die
      vorm `PostgresSyntaxError`. Het derde argument `true` maakt de instelling
      transactie-lokaal, exact zoals `SET LOCAL`.

    Een fout hier wordt NIET weggelogd. Kan de context niet worden gezet, dan hoort de
    transactie niet door te gaan: het verschil tussen "geen gegevens" en "geen context"
    mag niet onder een waarschuwing verdwijnen.
    """
    if conn.dialect.name != "postgresql":
        return  # SQLite (unit-tests) kent geen RLS en geen GUC's.

    try:
        from src.core.middleware.tenant_context import get_tenant_id
    except ImportError:  # pragma: no cover - alleen tijdens het opstarten van de module
        return

    tenant_id = get_tenant_id()
    # int() is de injectiewering voor het geval de ContextVar ooit een string draagt; de
    # waarde gaat daarna als bindparameter mee, dus er wordt geen SQL samengesteld.
    waarde = str(int(tenant_id)) if tenant_id else ""
    conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": waarde})


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(
    _type: JSONB,
    _compiler: object,
    **_kw: object,
) -> str:
    """Allow metadata creation on SQLite test databases for models using JSONB."""
    return "JSON"


class DatabaseManager:
    """
    Centralized database manager - single source of truth for all database operations
    Eliminates duplicate engines and provides consistent session management
    """

    def __init__(self) -> None:
        self.engine: AsyncEngine | None = None
        self.async_session_maker: async_sessionmaker[AsyncSession] | None = None
        self._initialized = False

    def is_initialized(self) -> bool:
        """
        Public API to check if database manager has been initialized.

        Returns:
            bool: True if engine is set and manager is initialized
        """
        return self._initialized and self.engine is not None

    def set_engine(self, engine: AsyncEngine) -> None:
        """
        Manually set the engine (useful for testing to inject a shared engine)
        """
        self.engine = engine
        self.async_session_maker = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self._initialized = True
        logger.info("Unified database manager engine set manually")

    def create_poolless_engine(self) -> AsyncEngine:
        """Een verse engine zonder connectiepool, met dezelfde URL en echo als deze manager.

        Voor een achtergrondrun die zijn eigen event loop heeft (`asyncio.run`): elke verbinding
        leeft zo lang als de sessie en blijft nooit in een pool achter voor een andere loop. De
        aanroeper doet `await engine.dispose()` aan het eind. De gedeelde `self.engine` wordt niet
        aangeraakt. De tenantcontext (`_zet_tenantcontext`) luistert op de klasse `Engine` en
        geldt dus ook hier.
        """
        from sqlalchemy.pool import NullPool

        if self.engine is not None:
            url: str | URL = self.engine.url
            echo = bool(self.engine.echo)
        else:
            db_config = self._get_db_config()
            url = cast(str, db_config["url"])
            echo = bool(db_config.get("echo", False))
        engine = create_async_engine(url, poolclass=NullPool, echo=echo)
        try:
            register_query_guard(cast(Engine, engine))
        except Exception as e:
            logger.warning(f"Could not register query guard: {e}")
        return engine

    def create_small_pool_engine(
        self, *, pool_size: int, max_overflow: int, pool_timeout: int
    ) -> AsyncEngine:
        """Een verse engine met een KLEINE eigen pool, met dezelfde URL en echo als deze manager.

        Voor een kleine, vaste taak naast de applicatie (de noodstopcontrole): een eigen pool zodat
        die taak de pool van de applicatie niet leegtrekt, en een kort `pool_timeout` zodat
        uitputting snel een fout geeft in plaats van een wachtrij. De pool hoort bij de event loop
        waarin hij wordt gebruikt; de aanroeper bouwt er een per loop. De gedeelde `self.engine`
        wordt niet aangeraakt. SQLite kent deze poolopties niet en krijgt de poolloze engine.
        """
        if self.engine is not None:
            url: str | URL = self.engine.url
            echo = bool(self.engine.echo)
        else:
            db_config = self._get_db_config()
            url = cast(str, db_config["url"])
            echo = bool(db_config.get("echo", False))
        if str(url).startswith("sqlite"):
            return self.create_poolless_engine()
        engine = create_async_engine(
            url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_pre_ping=True,
            pool_recycle=1800,
            echo=echo,
        )
        try:
            register_query_guard(cast(Engine, engine))
        except Exception as e:
            logger.warning(f"Could not register query guard: {e}")
        return engine

    def _get_db_config(self) -> dict[str, object]:
        """Helper to retrieve database configuration."""
        return cast(dict[str, object], config.get_database_config())

    async def initialize(self) -> bool:
        """Initialize the centralized database engine with extensive diagnostics"""
        if self._initialized:
            logger.info("[OK] Database already initialized, skipping")
            return True

        max_retries = 5
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                logger.info(f"[U+0001F504] Database init attempt {attempt + 1}/{max_retries}")

                # DIAGNOSTIC: Check config availability
                db_config = self._get_db_config()
                # Mask password in URL for logging
                safe_url = cast(str, db_config.get("url", "MISSING"))
                if "@" in safe_url and ":" in safe_url:
                    # Simple masking log could be improved but sufficient for now
                    logger.debug(f"[LIST] DB URL Configured (Masked): {database_url_zonder_wachtwoord(safe_url)}")

                engine_args: dict[str, object] = {
                    "echo": bool(db_config["echo"]),
                    "pool_pre_ping": True,
                    "pool_recycle": 1800,  # 30 min - standardized across configs
                }

                db_url = cast(str, db_config["url"])
                if "sqlite" not in db_url:
                    engine_args.update(
                        {
                            "pool_size": cast(int, db_config["pool_size"]),
                            "max_overflow": cast(int, db_config["max_overflow"]),
                            "pool_timeout": cast(int, db_config.get("pool_timeout", 30)),
                        }
                    )
                else:
                    from sqlalchemy.pool import StaticPool

                    if ":memory:" in db_url or "mode=memory" in db_url:
                        engine_args["poolclass"] = StaticPool
                        engine_args["connect_args"] = {"check_same_thread": False}

                # DIAGNOSTIC: Log engine creation
                logger.debug(f"[TOOL] Creating async engine with args: {list(engine_args.keys())}")
                self.engine = create_async_engine(db_url, **engine_args)

                # DIAGNOSTIC: Test connection with timeout
                logger.info("[U+0001F50C] Testing database connectivity...")
                async with asyncio.timeout(10):  # <- Prevent infinite hang
                    async with self.engine.begin() as conn:
                        result = await conn.execute(text("SELECT 1"))
                        logger.debug(f"[SEARCH] Connection test result: {result.scalar()}")

                # Create session maker
                self.async_session_maker = async_sessionmaker(
                    bind=self.engine, class_=AsyncSession, expire_on_commit=False
                )

                # Register query guard for tenant filtering enforcement
                try:
                    register_query_guard(cast(Engine, self.engine))
                except Exception as e:
                    logger.warning(f"Could not register query guard: {e}")

                self._initialized = True
                logger.info("[OK] Unified database manager initialized successfully")
                return True

            except TimeoutError as e:
                logger.error(f"[TIMER] Database connection TIMEOUT on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"[WAIT] Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.critical(
                        f"[BOOM] FATAL: Database connection timeout after {max_retries} attempts"
                    )
                    return False

            except Exception as e:
                logger.error(
                    f"[FAIL] Database init attempt {attempt + 1}/{max_retries} failed: {type(e).__name__}: {e}",
                    exc_info=True,  # <- Full stack trace
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    logger.critical(
                        f"[BOOM] FATAL: Failed to initialize database after {max_retries} attempts"
                    )
                    return False
        return False

    @asynccontextmanager
    async def get_session(self, max_retries: int = 3) -> AsyncGenerator[AsyncSession, None]:
        """
        Centralized session context manager with comprehensive error handling and retry logic

        Args:
            max_retries: Maximum number of retry attempts for connection issues
        """
        if not self._initialized:
            if not await self.initialize():
                raise RuntimeError("Database manager not initialized")

        if self.async_session_maker is None:
            raise RuntimeError("Database session maker not initialized")

        retry_count = 0
        last_exception = None

        while retry_count <= max_retries:
            session = None
            try:
                session = self.async_session_maker()

                # Test session with a simple query. Dit opent tevens de transactie,
                # waardoor `_zet_tenantcontext` (het `begin`-event) de RLS-context zet --
                # en dat gebeurt daarna opnieuw bij ELKE volgende transactie van deze
                # sessie. Zie de toelichting bij dat event.
                await session.execute(text("SELECT 1"))

                yield session
                await session.commit()
                return  # Success - exit retry loop

            except (DisconnectionError, OperationalError, SQLTimeoutError) as e:
                # Connection-related errors - attempt retry
                retry_count += 1
                last_exception = e

                if session:
                    try:
                        await session.rollback()
                        await session.close()
                    except Exception:
                        pass  # Ignore cleanup errors

                if retry_count <= max_retries:
                    wait_time = min(2**retry_count, 10)  # Exponential backoff, max 10s
                    logger.warning(
                        f"Database connection error (attempt {retry_count}/{max_retries}): {e}. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)

                    # Try to reinitialize connection
                    try:
                        if self.engine is not None:
                            await self.engine.dispose()
                        self._initialized = False
                        await self.initialize()
                    except Exception as init_error:
                        logger.error(f"Failed to reinitialize database connection: {init_error}")
                else:
                    logger.error(f"Database connection failed after {max_retries} retries: {e}")
                    raise

            except SQLAlchemyError as e:
                # Non-connection SQLAlchemy errors - don't retry
                if session:
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                logger.error(f"Database SQLAlchemy error: {e}")
                raise

            except HTTPException:
                # HTTP exceptions (like 401/404) are normal flow control
                # Don't log as database errors, just cleanup and re-raise
                if session:
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                raise

            except Exception as e:
                # Other unexpected errors - don't retry
                if session:
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                logger.error(f"Unexpected database session error: {e}")
                raise

            finally:
                if session:
                    try:
                        await session.close()
                    except Exception as close_error:
                        logger.warning(f"Error closing session: {close_error}")

        # If we get here, all retries failed
        if last_exception:
            raise last_exception
        else:
            raise RuntimeError("Database session creation failed")

    async def health_check(self) -> bool:
        """Check database connectivity (Fail-fast, no retries)"""
        try:
            # Use 0 retries to ensure health check responds within Docker timeout (5s)
            async with self.get_session(max_retries=0) as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
            self._initialized = False
            logger.info("Database connections closed")


# Global database manager instance
db_manager = DatabaseManager()

# Legacy compatibility functions
engine: AsyncEngine | None = None
async_session_maker: async_sessionmaker[AsyncSession] | None = None


async def initialize_database() -> bool:
    """
    Legacy compatibility function - delegates to unified database manager
    """
    # Guard: In test mode, preserve pre-initialized engine from fixtures
    if os.getenv("TESTING") == "1" and db_manager.is_initialized():
        logger.info(
            "[TEST MODE] Using pre-initialized test database engine - skipping app initialization"
        )
        return True

    global engine, async_session_maker

    result = await db_manager.initialize()
    if result:
        # Set legacy global variables for backward compatibility
        engine = db_manager.engine
        async_session_maker = db_manager.async_session_maker

    return result


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide database session with proper isolation for concurrent requests.
    Context manager automatically handles session lifecycle.

    DEPRECATED: Use get_db() for FastAPI Depends(). @asynccontextmanager
    breaks FastAPI dependency injection. See ADR and DECISION_LOG.
    """

    warnings.warn(
        "get_async_session is deprecated. Use get_db() for FastAPI dependencies.",
        DeprecationWarning,
        stacklevel=2,
    )
    if not db_manager.async_session_maker:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")

    async with db_manager.async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        # Context manager automatically closes session - no explicit close() needed


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.

    FIX: Direct session lifecycle instead of nested async generator.
    The previous pattern (async for session in get_async_session(): yield session)
    causes deadlocks in FastAPI due to nested async generator cleanup issues.
    See: https://github.com/fastapi/fastapi/issues/3205
    """
    if not db_manager.async_session_maker:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")

    session = db_manager.async_session_maker()
    try:
        # De RLS-tenantcontext wordt gezet door `_zet_tenantcontext`, het `begin`-event op
        # de engine -- bij ELKE transactie van deze sessie, niet alleen de eerste. Hier
        # stond eerder een eenmalige `SET LOCAL`; die was weg zodra een endpoint zelf
        # `await db.commit()` deed. Zie de toelichting bij dat event.
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Backward-compatible alias for legacy endpoints and security tests."""
    async for session in get_db():
        yield session


async def get_redis() -> AsyncGenerator[Any, None]:  # TODO(TYPE): replace Any with concrete type
    """
    FastAPI dependency for Redis client.
    Returns an async Redis client for use in endpoints.
    """
    from src.core.database.redis import get_redis_client

    client = await get_redis_client()
    try:
        yield client
    finally:
        pass  # Connection pool managed globally


async def close_database() -> None:
    """
    Legacy compatibility function - delegates to unified database manager
    """
    await db_manager.close()
