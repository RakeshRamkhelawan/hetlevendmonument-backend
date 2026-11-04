"""
Integration Test Fixtures - Phase D (Refactored for Stability)
REAL PostgreSQL database with optimized fixture architecture

This version uses session-scoped schema setup with function-scoped
connection reuse for dramatically improved performance and stability.
"""

from src.core.security.bcrypt_patch import patch_bcrypt_about_attribute

patch_bcrypt_about_attribute()

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from collections.abc import AsyncGenerator, Iterator

import pytest
import pytest_asyncio


# De testdatabase wordt EXPLICIET opgegeven -- nooit geraden (ADR-036 OP-243).
#
# Hier stond tot 2026-09-15 een poortscan: probeer 5435, dan 5455, neem wie antwoordt. Drie
# gemeten gebreken, alle drie hier weg:
#   1. Faalde de scan, dan volgde `pytest.skip(..., allow_module_level=True)`. LET OP: de
#      aanname dat dit EXITCODE 0 gaf is NAGEMETEN en ONJUIST -- met beide poorten dicht
#      geeft die skip in een conftest exitcode 1, zowel voor een los bestand als voor de
#      hele map (gemeten 2026-09-15, pytest 8.x). Wat wel klopt: de melding zei alleen
#      "not available on port 5435 or 5455" en noemde de oorzaak niet. Dit is nu een FOUT
#      met het commando erbij, wat beter is dan een skip -- maar het dichtte GEEN
#      stil-groen gat, want dat bestond hier niet.
#   2. Elke oorzaak (poort dicht, verkeerd wachtwoord, ontbrekende driver, typefout in de
#      URL) viel in dezelfde `except Exception` en werd een kale `False`. De resolver laat
#      de echte fout staan.
#   3. De uitkomst van de scan lekte naar `os.environ["POSTGRES_PORT"]`, die 19 andere
#      testbestanden lezen. Die variabele wordt nu AFGELEID uit de opgegeven URL.
#
# Aanleiding: een vergeten `act`-servicecontainer luisterde zes uur op 5435. De scan zei
# "verbinding geslaagd" en de suite zou tegen die wegwerpdatabase hebben gedraaid.
from tests.fixtures.testdatabase import eis_testdatabase, testdatabase_poort, testdatabase_url

# Load .env.test if it exists
env_test_file = Path(__file__).parent.parent.parent / ".env.test"
if env_test_file.exists():
    from dotenv import load_dotenv

    load_dotenv(env_test_file, override=True)

# CRITICAL OVERRIDES
TEST_SECRET_KEY = os.getenv(
    "TEST_SECRET_KEY", "test-secret-key-for-integration-tests-32chars-minimum"
)
os.environ["SANSKRITI_SECRET_KEY"] = TEST_SECRET_KEY
os.environ["JWT_SECRET_KEY"] = TEST_SECRET_KEY
os.environ["ENVIRONMENT"] = "development"
os.environ["TESTING"] = "1"
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

# ActivePieces credentials
os.environ["AP_SERVICE_EMAIL"] = "mock_ap_email@sanskritisetu.org"
os.environ["AP_SERVICE_PASSWORD"] = "mock_ap_password"
os.environ["ACTIVEPIECES_API_URL"] = "http://mock-ap-url"
os.environ["ACTIVEPIECES_EMAIL"] = "mock_ap_email@sanskritisetu.org"
os.environ["ACTIVEPIECES_PASSWORD"] = "mock_ap_password"

# Determine database URL
import socket


def is_running_in_docker() -> bool:
    """Detect if running inside a Docker container.

    Checks an explicit env-var first to prevent false-positives on
    developer machines that happen to have a host named 'postgres'.
    """
    if os.environ.get("RUNNING_IN_DOCKER", "").lower() in ("1", "true", "yes"):
        return True
    if os.path.exists("/.dockerenv"):
        return True
    try:
        socket.gethostbyname("postgres")
        return True
    except socket.gaierror:
        return False


if is_running_in_docker():
    # Ook hier geen terugval (ADR-036 OP-243). In een compose-omgeving ZET compose
    # DATABASE_URL; ontbreekt hij, dan is dat een inrichtingsfout en geen reden om
    # `postgres:5432/sanskriti_test` te gokken.
    FORCED_TEST_DB_URL = os.environ.get("DATABASE_URL", "").strip()
    if not FORCED_TEST_DB_URL:
        raise RuntimeError(
            "DATABASE_URL is niet gezet terwijl de tests in een container draaien. "
            "Compose hoort die te zetten; dit wordt NIET geraden (ADR-036 OP-243)."
        )
else:
    # Geen terugval: is de variabele niet gezet, dan faalt dit met het commando erbij.
    FORCED_TEST_DB_URL = testdatabase_url()

os.environ["DATABASE_URL"] = FORCED_TEST_DB_URL
TEST_DB_URL = FORCED_TEST_DB_URL

# Set Redis URL BEFORE any module imports that might read config
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

# Guard against accidental parallel execution with pytest-xdist.
# Parallel workers sharing a single DB would corrupt transactional isolation.
_xdist_worker = os.environ.get("PYTEST_XDIST_WORKER", "")
if _xdist_worker:
    import warnings

    warnings.warn(
        f"Integration tests are running under pytest-xdist worker '{_xdist_worker}' "
        "against a shared database. Transactional isolation is NOT guaranteed. "
        "Run integration tests without '-n' / '--numprocesses'.",
        stacklevel=1,
    )

# Set PostgreSQL connection details
os.environ["POSTGRES_DB"] = "sanskritisetu_test"
os.environ["POSTGRES_USER"] = "postgres"
os.environ["POSTGRES_PASSWORD"] = "postgres"
os.environ["POSTGRES_HOST"] = "localhost"
# AFGELEID uit de opgegeven URL, niet apart ingesteld. 19 testbestanden lezen deze
# variabele (gemeten 2026-09-15); zo is er nog maar EEN bron van waarheid. Fase 2 van
# OP-243 haalt die lezers zelf weg.
os.environ["POSTGRES_PORT"] = str(testdatabase_poort())

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Imports after path setup
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Import ALL models via canonical registry so every table is in Base.metadata
# before create_all is called. Adding individual imports here is a maintenance
# trap — use import_all_models.py as the single source of truth instead.
import src.core.database.import_all_models  # noqa: F401
from src.core.auth.jwt_handler import jwt_handler
from src.core.database.database import Base, db_manager
from src.core.models import rbac_models

# ============================================================================
# SESSION-SCOPED SCHEMA SETUP (RUNS ONCE PER TEST SESSION)
# ============================================================================

_schema_initialized = False


@pytest.fixture(scope="session", autouse=True)
def setup_database_schema():
    """
    Session-scoped fixture that initializes the database schema ONCE.
    This dramatically improves test performance by avoiding repeated
    schema drop/create cycles.
    """
    import asyncio

    global _schema_initialized

    if _schema_initialized:
        yield
        return

    async def _init_schema():
        from passlib.context import CryptContext
        from sqlalchemy.pool import NullPool

        # VOOR alles wat iets stukmaakt: hieronder worden eerst alle andere verbindingen op deze database
        # beeindigd en dan de schema's gewist. Alleen op een aantoonbare testdatabase (naam op `_test`, niet de
        # ontwikkelpoort 5435); anders een fout en niets gewist (brief 2026-10-26, zie tests/fixtures/testdatabase.py).
        eis_testdatabase(TEST_DB_URL)

        engine = create_async_engine(
            TEST_DB_URL,
            echo=False,
            poolclass=NullPool,
            connect_args={
                "timeout": 60,
                "command_timeout": 300,  # 5 min for schema creation
                "server_settings": {
                    "application_name": "sanskritisetu_test_schema",
                    "jit": "off",
                },
            },
        )

        try:
            async with engine.begin() as conn:
                # Terminate stale connections
                await conn.exec_driver_sql(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid != pg_backend_pid()"
                )

                # Drop and recreate schemas
                await conn.exec_driver_sql("DROP SCHEMA IF EXISTS legacy CASCADE;")
                await conn.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE;")
                await conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS legacy;")
                await conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS public;")

                # Create extensions
                await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector;")

                # All models are already registered via import_all_models at module level.
                # No additional imports needed here.

                # Create all tables — checkfirst=True prevents DuplicateObject when
                # rbac_models.Base and Base share tables (tenants, users, roles, …).
                # Without it the second create_all aborts the transaction and the
                # DROP SCHEMA CASCADE rolls back, leaving the DB in the Alembic-
                # migrated state (missing companies, company_templates, external_agents).
                await conn.run_sync(
                    lambda c: rbac_models.Base.metadata.create_all(c, checkfirst=True)
                )
                await conn.run_sync(lambda c: Base.metadata.create_all(c, checkfirst=True))

                # Create materialized views (not in SQLAlchemy metadata, only in Alembic)
                await conn.exec_driver_sql(
                    "CREATE MATERIALIZED VIEW IF NOT EXISTS critique_hourly_stats AS "
                    "SELECT DATE_TRUNC('hour', created_at) AS hour, "
                    "tenant_id, agent_name, "
                    "AVG(score)::float AS avg_score, COUNT(*)::int AS critique_count "
                    "FROM agent_critiques GROUP BY 1, 2, 3"
                )
                await conn.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_critique_hourly_stats_unique "
                    "ON critique_hourly_stats (hour, tenant_id, agent_name)"
                )

                # Seed baseline data
                pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
                admin_pass_hash = pwd_context.hash("AdminPass123!")

                # Tenants (id=1 default, id=2 for isolation tests)
                await conn.exec_driver_sql(
                    "INSERT INTO tenants (id, name, slug, domain, is_active, max_users, max_agents, max_storage_gb, subscription_tier, subscription_status) "
                    "VALUES (1, 'Default Tenant', 'default', 'default.local', true, 100, 100, 100.0, 'enterprise', 'active') "
                    "ON CONFLICT (id) DO NOTHING"
                )
                await conn.exec_driver_sql(
                    "INSERT INTO tenants (id, name, slug, domain, is_active, max_users, max_agents, max_storage_gb, subscription_tier, subscription_status) "
                    "VALUES (2, 'Other Tenant', 'other', 'other.local', true, 100, 100, 100.0, 'enterprise', 'active') "
                    "ON CONFLICT (id) DO NOTHING"
                )

                # Roles
                await conn.exec_driver_sql(
                    "INSERT INTO roles (name, tenant_id, is_active) VALUES ('admin', 1, true) "
                    "ON CONFLICT (tenant_id, name) DO NOTHING"
                )
                await conn.exec_driver_sql(
                    "INSERT INTO roles (name, tenant_id, is_active) VALUES ('user', 1, true) "
                    "ON CONFLICT (tenant_id, name) DO NOTHING"
                )
                await conn.exec_driver_sql(
                    "INSERT INTO roles (name, tenant_id, is_active) VALUES ('system_admin', 1, true) "
                    "ON CONFLICT (tenant_id, name) DO NOTHING"
                )

                # Get role IDs
                admin_role_result = await conn.exec_driver_sql(
                    "SELECT id FROM roles WHERE name='admin' AND tenant_id=1"
                )
                admin_role_id = admin_role_result.scalar()

                # Users
                await conn.exec_driver_sql(
                    "INSERT INTO users (id, email, hashed_password, is_active, is_superuser, tenant_id) "
                    "VALUES (1, $1, $2, true, true, 1) ON CONFLICT (id) DO NOTHING",
                    ("admin@integration.test", admin_pass_hash),
                )
                await conn.exec_driver_sql(
                    "INSERT INTO users (id, email, hashed_password, is_active, is_superuser, tenant_id) "
                    "VALUES (101, $1, $2, true, true, 1) ON CONFLICT (id) DO NOTHING",
                    ("admin@example.com", admin_pass_hash),
                )
                await conn.exec_driver_sql(
                    "INSERT INTO users (id, email, hashed_password, is_active, is_superuser, tenant_id) "
                    "VALUES (2, $1, $2, true, false, 1) ON CONFLICT (id) DO NOTHING",
                    ("user@integration.test", pwd_context.hash("UserPass123!")),
                )

                # Role assignments
                if admin_role_id:
                    await conn.exec_driver_sql(
                        "INSERT INTO user_roles (user_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        (1, admin_role_id),
                    )
                    await conn.exec_driver_sql(
                        "INSERT INTO user_roles (user_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        (101, admin_role_id),
                    )

                # Permissions
                if admin_role_id:
                    await conn.exec_driver_sql(
                        "INSERT INTO role_permissions (role_id, tenant_id, resource, action) "
                        "VALUES ($1, 1, $2, $3) ON CONFLICT DO NOTHING",
                        (admin_role_id, "*", "*"),
                    )

                # Seed registered_agents for discovery endpoint tests (tenant_id=1)
                _agent_seeds = [
                    (
                        "ai-engineer",
                        "AI Engineer",
                        "AI and ML engineering",
                        "http://localhost:8001",
                        '["ai", "ai-engineering"]',
                    ),
                    (
                        "cloud-architect",
                        "Cloud Architect",
                        "Cloud infrastructure",
                        "http://localhost:8002",
                        '["cloud", "architecture"]',
                    ),
                    (
                        "legal-advisor",
                        "Legal Advisor",
                        "Legal and compliance",
                        "http://localhost:8003",
                        '["legal", "compliance"]',
                    ),
                    (
                        "hr-pro",
                        "HR Pro",
                        "Human resources",
                        "http://localhost:8004",
                        '["hr", "recruitment"]',
                    ),
                    (
                        "security-analyst",
                        "Security Analyst",
                        "Security and audit",
                        "http://localhost:8005",
                        '["security", "audit"]',
                    ),
                    (
                        "sales-optimizer",
                        "Sales Optimizer",
                        "Sales and CRM",
                        "http://localhost:8006",
                        '["sales", "crm", "marketing"]',
                    ),
                    (
                        "data-analyst",
                        "Data Analyst",
                        "Data analytics",
                        "http://localhost:8007",
                        '["data", "analytics"]',
                    ),
                    (
                        "devops-engineer",
                        "DevOps Engineer",
                        "CI/CD and ops",
                        "http://localhost:8008",
                        '["devops", "ci-cd"]',
                    ),
                    (
                        "finance-agent",
                        "Finance Agent",
                        "Finance and accounting",
                        "http://localhost:8009",
                        '["finance", "accounting"]',
                    ),
                    (
                        "ops-manager",
                        "Operations Manager",
                        "Operations and workflow",
                        "http://localhost:8010",
                        '["operations", "workflow", "deployment"]',
                    ),
                ]
                for aid, name, desc, addr, caps in _agent_seeds:
                    await conn.exec_driver_sql(
                        "INSERT INTO registered_agents (agent_id, name, description, address, capabilities, tenant_id, health_status) "
                        "VALUES ($1, $2, $3, $4, $5::jsonb, 1, 'healthy') "
                        "ON CONFLICT (agent_id, tenant_id) DO NOTHING",
                        (aid, name, desc, addr, caps),
                    )

                # Create alembic_version table so health checks can query it
                await conn.exec_driver_sql(
                    "CREATE TABLE IF NOT EXISTS alembic_version ("
                    "    version_num VARCHAR(64) NOT NULL,"
                    "    CONSTRAINT alembic_version_pk PRIMARY KEY (version_num)"
                    ")"
                )
                await conn.exec_driver_sql(
                    "INSERT INTO alembic_version (version_num) VALUES ('head') "
                    "ON CONFLICT (version_num) DO NOTHING"
                )

                # Reset sequences to the actual max seeded ID so that the
                # next auto-generated PK never collides with an explicit one.
                # (Seeded IDs include 1, 2, 101 -- using a fixed value of 2
                # would collide when a test inserts a new user after id=101.)
                await conn.exec_driver_sql(
                    "SELECT setval('tenants_id_seq', (SELECT MAX(id) FROM tenants), true)"
                )
                await conn.exec_driver_sql(
                    "SELECT setval('users_id_seq', (SELECT MAX(id) FROM users), true)"
                )

                print("[SCHEMA SETUP] Database schema initialized successfully")
        finally:
            await engine.dispose()

    # Run schema setup
    asyncio.run(_init_schema())
    _schema_initialized = True
    yield


@pytest.fixture(scope="session", autouse=True)
def setup_rls_policies(setup_database_schema):
    """Apply Row-Level Security policies to all tenant-scoped tables.

    Mirrors the RLS setup from production Alembic migrations so that
    tenant-isolation tests behave identically in integration tests.
    """
    import asyncio

    async def _apply_rls():
        engine = create_async_engine(
            TEST_DB_URL,
            echo=False,
            future=True,
        )
        # List of tables with tenant_id that should have RLS
        _ALLOWED_RLS_TABLES: frozenset[str] = frozenset(
            {
                "companies",
                "departments",
                "goals",
                "c7_workflows",
                "conversations",
                "agents",
                "procedures",
                "domain_packs",
                "audit_logs",
            }
        )
        for table in _ALLOWED_RLS_TABLES:
            # Use a separate transaction per table so that failures
            # on missing tables don't abort the whole batch.
            async with engine.begin() as conn:
                try:
                    qtable = f'"{table}"'
                    await conn.execute(text(f"ALTER TABLE {qtable} ENABLE ROW LEVEL SECURITY"))
                except Exception:
                    pass
                try:
                    # PostgreSQL does not support CREATE POLICY IF NOT EXISTS
                    # Use a DO block to idempotently create the policy.
                    qtable = f'"{table}"'
                    qpolicy = f'"{table}_tenant_isolation"'
                    await conn.execute(
                        text(
                            f"""
                            DO $$
                            BEGIN
                                IF NOT EXISTS (
                                    SELECT 1 FROM pg_policies
                                    WHERE schemaname = 'public'
                                    AND tablename = '{table}'
                                    AND policyname = '{table}_tenant_isolation'
                                ) THEN
                                    CREATE POLICY {qpolicy}
                                    ON {qtable}
                                    FOR ALL USING (
                                        tenant_id = current_setting('app.current_tenant')::INTEGER
                                    );
                                END IF;
                            END
                            $$;
                            """
                        )
                    )
                except Exception:
                    pass
        await engine.dispose()

    asyncio.run(_apply_rls())
    yield


@pytest.fixture(scope="session", autouse=True)
def setup_db_manager():
    """
    Session-scoped fixture that initializes the global db_manager singleton.
    Must run after setup_database_schema so the DB exists.
    """
    import asyncio

    from sqlalchemy.pool import NullPool

    async def _init():
        engine = create_async_engine(
            TEST_DB_URL,
            echo=False,
            poolclass=NullPool,
            connect_args={
                "timeout": 30,
                "command_timeout": 60,
                "server_settings": {
                    "application_name": "sanskritisetu_test_app",
                    "jit": "off",
                },
            },
        )
        db_manager.set_engine(engine)
        return engine

    _engine = asyncio.run(_init())
    yield
    asyncio.run(_engine.dispose())
    db_manager.engine = None
    db_manager.async_session_maker = None
    db_manager._initialized = False


# ============================================================================
# MODULE-SCOPED DB RESET (PREVENTS CROSS-MODULE STATE POLLUTION)
# ============================================================================

_seed_pass_hashes_cache: dict[str, str] = {}

_MODULE_AGENT_SEEDS: list[tuple[str, str, str, str, str]] = [
    (
        "ai-engineer",
        "AI Engineer",
        "AI and ML engineering",
        "http://localhost:8001",
        '["ai", "ai-engineering"]',
    ),
    (
        "cloud-architect",
        "Cloud Architect",
        "Cloud infrastructure",
        "http://localhost:8002",
        '["cloud", "architecture"]',
    ),
    (
        "legal-advisor",
        "Legal Advisor",
        "Legal and compliance",
        "http://localhost:8003",
        '["legal", "compliance"]',
    ),
    ("hr-pro", "HR Pro", "Human resources", "http://localhost:8004", '["hr", "recruitment"]'),
    (
        "security-analyst",
        "Security Analyst",
        "Security and audit",
        "http://localhost:8005",
        '["security", "audit"]',
    ),
    (
        "sales-optimizer",
        "Sales Optimizer",
        "Sales and CRM",
        "http://localhost:8006",
        '["sales", "crm", "marketing"]',
    ),
    (
        "data-analyst",
        "Data Analyst",
        "Data analytics",
        "http://localhost:8007",
        '["data", "analytics"]',
    ),
    (
        "devops-engineer",
        "DevOps Engineer",
        "CI/CD and ops",
        "http://localhost:8008",
        '["devops", "ci-cd"]',
    ),
    (
        "finance-agent",
        "Finance Agent",
        "Finance and accounting",
        "http://localhost:8009",
        '["finance", "accounting"]',
    ),
    (
        "ops-manager",
        "Operations Manager",
        "Operations and workflow",
        "http://localhost:8010",
        '["operations", "workflow", "deployment"]',
    ),
]


def _get_seed_pass_hashes() -> dict[str, str]:
    """Compute bcrypt hashes once and cache them across all module resets."""
    if not _seed_pass_hashes_cache:
        from passlib.context import CryptContext

        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        _seed_pass_hashes_cache["admin"] = ctx.hash("AdminPass123!")
        _seed_pass_hashes_cache["user"] = ctx.hash("UserPass123!")
    return _seed_pass_hashes_cache


@pytest.fixture(scope="module", autouse=True)
def reset_db_per_module(setup_database_schema):
    """Truncate all user data and re-seed before each test module.

    HTTP endpoint sessions use get_db() which creates independent sessions
    that commit permanently -- savepoint rollback in postgres_session does NOT
    cover those commits. Earlier test modules accumulate DB state that breaks
    later tests. This fixture gives every module a clean, known baseline state.
    """
    import asyncio
    from sqlalchemy.pool import NullPool

    async def _reset() -> None:
        engine = create_async_engine(
            TEST_DB_URL,
            echo=False,
            poolclass=NullPool,
            connect_args={
                "timeout": 30,
                "command_timeout": 120,
                "server_settings": {"application_name": "sanskritisetu_test_reset", "jit": "off"},
            },
        )
        try:
            async with engine.begin() as conn:
                # Kill connections stuck in open transactions from previous module.
                # Copilot tests spawn async council tasks that may be cancelled by
                # pytest teardown mid-transaction, leaving connections in
                # "idle in transaction" state. These hold table locks that cause
                # TRUNCATE to deadlock. We only kill stuck connections, NOT idle
                # pool connections (those are safe for subsequent tests to reuse).
                #
                # Age threshold (added after observing flaky ConnectionDoesNotExistError
                # failures, 2026-07-04): without this, a connection that is only
                # milliseconds into a legitimate, in-progress multi-statement transaction
                # at the exact moment this query runs would ALSO match "idle in
                # transaction" and get killed, breaking whatever test/task was using it.
                # 5 seconds is generous for any real request's transaction but far
                # shorter than "stuck for the rest of the module".
                await conn.exec_driver_sql(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid != pg_backend_pid() "
                    "AND state = 'idle in transaction' "
                    "AND state_change < now() - interval '5 seconds'"
                )

                # Discover all user tables except alembic_version (no PK seq, keep as-is)
                result = await conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' AND tablename != 'alembic_version'"
                    )
                )
                tables = [row[0] for row in result.fetchall()]

                if tables:
                    # TRUNCATE with CASCADE handles FK ordering; RESTART IDENTITY
                    # resets sequences so auto-generated PKs start from 1 again.
                    table_list = ", ".join(f'"{t}"' for t in tables)
                    await conn.execute(
                        text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")  # noqa: S608
                    )

                # Company-layer test files (test_company_fase1_integration.py,
                # test_company_layer_fase1_integration.py, test_company_layer_isolated.py)
                # DROP tables in their teardown without always dropping tenants.
                # Checking only "tenants" misses cases where external_agents /
                # company_templates / goals / users are dropped but tenants stays.
                recovery_result = await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM pg_tables "
                        "WHERE schemaname='public' "
                        "AND tablename IN ('tenants', 'users', 'company_templates', 'external_agents', 'goals')"
                    )
                )
                if (recovery_result.scalar() or 0) < 5:
                    await conn.run_sync(
                        lambda c: rbac_models.Base.metadata.create_all(c, checkfirst=True)
                    )
                    await conn.run_sync(lambda c: Base.metadata.create_all(c, checkfirst=True))

                # Re-seed tenants
                await conn.exec_driver_sql(
                    "INSERT INTO tenants (id, name, slug, domain, is_active, max_users, max_agents, max_storage_gb, subscription_tier, subscription_status) "
                    "VALUES (1, 'Default Tenant', 'default', 'default.local', true, 100, 100, 100.0, 'enterprise', 'active') "
                    "ON CONFLICT (id) DO NOTHING"
                )
                await conn.exec_driver_sql(
                    "INSERT INTO tenants (id, name, slug, domain, is_active, max_users, max_agents, max_storage_gb, subscription_tier, subscription_status) "
                    "VALUES (2, 'Other Tenant', 'other', 'other.local', true, 100, 100, 100.0, 'enterprise', 'active') "
                    "ON CONFLICT (id) DO NOTHING"
                )

                # Re-seed roles
                for role_name in ("admin", "user", "system_admin"):
                    await conn.exec_driver_sql(
                        "INSERT INTO roles (name, tenant_id, is_active) VALUES ($1, 1, true) "
                        "ON CONFLICT (tenant_id, name) DO NOTHING",
                        (role_name,),
                    )

                admin_role_result = await conn.exec_driver_sql(
                    "SELECT id FROM roles WHERE name='admin' AND tenant_id=1"
                )
                admin_role_id = admin_role_result.scalar()

                # Re-seed users with pre-computed hashes
                hashes = _get_seed_pass_hashes()
                admin_hash = hashes["admin"]
                user_hash = hashes["user"]
                await conn.exec_driver_sql(
                    "INSERT INTO users (id, email, hashed_password, is_active, is_superuser, tenant_id) "
                    "VALUES (1, $1, $2, true, true, 1) ON CONFLICT (id) DO NOTHING",
                    ("admin@integration.test", admin_hash),
                )
                await conn.exec_driver_sql(
                    "INSERT INTO users (id, email, hashed_password, is_active, is_superuser, tenant_id) "
                    "VALUES (101, $1, $2, true, true, 1) ON CONFLICT (id) DO NOTHING",
                    ("admin@example.com", admin_hash),
                )
                await conn.exec_driver_sql(
                    "INSERT INTO users (id, email, hashed_password, is_active, is_superuser, tenant_id) "
                    "VALUES (2, $1, $2, true, false, 1) ON CONFLICT (id) DO NOTHING",
                    ("user@integration.test", user_hash),
                )

                if admin_role_id:
                    for uid in (1, 101):
                        await conn.exec_driver_sql(
                            "INSERT INTO user_roles (user_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                            (uid, admin_role_id),
                        )
                    await conn.exec_driver_sql(
                        "INSERT INTO role_permissions (role_id, tenant_id, resource, action) "
                        "VALUES ($1, 1, $2, $3) ON CONFLICT DO NOTHING",
                        (admin_role_id, "*", "*"),
                    )

                # Re-seed registered_agents
                for aid, name, desc, addr, caps in _MODULE_AGENT_SEEDS:
                    await conn.exec_driver_sql(
                        "INSERT INTO registered_agents (agent_id, name, description, address, capabilities, tenant_id, health_status) "
                        "VALUES ($1, $2, $3, $4, $5::jsonb, 1, 'healthy') "
                        "ON CONFLICT (agent_id, tenant_id) DO NOTHING",
                        (aid, name, desc, addr, caps),
                    )

                # Reset sequences so auto-generated PKs don't collide with seeded IDs
                await conn.exec_driver_sql(
                    "SELECT setval('tenants_id_seq', (SELECT MAX(id) FROM tenants), true)"
                )
                await conn.exec_driver_sql(
                    "SELECT setval('users_id_seq', (SELECT MAX(id) FROM users), true)"
                )
        finally:
            await engine.dispose()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_reset())
    finally:
        loop.close()

    # Synchronously invalidate the shared db_manager pool after each module reset.
    # DDL from test_company_layer_isolated.py invalidates asyncpg's type cache; stale
    # pooled connections then race with pg_terminate_backend and fail mid-operation.
    # sync_engine.pool.dispose() is safe to call without an event loop.
    from src.core.database.database import db_manager

    if db_manager.is_initialized():
        try:
            db_manager.engine.sync_engine.pool.dispose()
        except Exception:
            pass

    yield


# ============================================================================
# FUNCTION-SCOPED FIXTURES (FAST - NO SCHEMA CREATION)
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def postgres_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    Function-scoped engine that reuses the session-scoped schema.
    Only handles connection management - no schema changes.
    """
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        poolclass=NullPool,
        connect_args={
            "timeout": 30,
            "command_timeout": 60,
            "server_settings": {
                "application_name": "sanskritisetu_test",
                "jit": "off",
            },
        },
    )

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def postgres_session(
    postgres_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Function-scoped session with transaction rollback for isolation.
    TRUNCATE is used for cleanup instead of schema recreation.
    """
    connection = await postgres_engine.connect()
    transaction = await connection.begin()

    async_session_maker = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
        # "create_savepoint" wraps each ORM flush in a SAVEPOINT so that
        # SQLAlchemy doesn't escalate the outer BEGIN to a real commit.
        # The outer transaction is always rolled back in the finally block,
        # giving per-test database isolation without schema recreation.
        join_transaction_mode="create_savepoint",
    )

    # Uitgeschakeld is uitgeschakeld: de tenant-middleware en de WebSocket-ingangen toetsen de
    # accountstatus met een EIGEN sessie (`account_status._sessiemaker`). Die ziet de gebruikers uit
    # de transactie van deze fixture niet: wijs hem naar DEZELFDE verbinding. Alleen de ligging
    # van de database wordt omgeleid, de controle zelf blijft de echte; `db_manager` blijft ongemoeid.
    from src.core.auth import account_status as _account_status

    _origineel_sessiemaker = _account_status._sessiemaker
    _account_status._sessiemaker = lambda: async_session_maker

    async with async_session_maker() as session:
        try:
            yield session
        finally:
            _account_status._sessiemaker = _origineel_sessiemaker
            await session.close()
            if transaction.is_active:
                await transaction.rollback()
            await connection.close()


@pytest.fixture(scope="session")
def integration_app() -> FastAPI:
    """Session-scoped FastAPI app for integration testing."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from src.core.api.router_registry import register_all_routers
    from src.core.exceptions.handlers import register_exception_handlers
    from src.core.feature_flags import FeatureFlagManager
    from src.core.middleware.tenant_middleware import TenantMiddleware

    test_app = FastAPI(
        title="SanskritiSetu Integration Tests",
        description="Production-ready integration testing",
        version="2.0.0-integration",
    )

    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    test_app.add_middleware(TenantMiddleware)

    register_all_routers(test_app)
    register_exception_handlers(test_app)

    # Initialize FeatureFlagManager for testing
    test_app.state.ff_manager = FeatureFlagManager()

    # Initialize db_manager so governance event handlers can write audit rows.
    # The handler uses db_manager.async_session_maker() -- without this, all
    # AuditLogEmitEvent handlers return early (db_manager not initialized).
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.core.database.database import db_manager

    if not db_manager.is_initialized():
        _integration_engine = create_async_engine(TEST_DB_URL, echo=False, pool_pre_ping=True)
        db_manager.set_engine(_integration_engine)

    from src.core.governance.event_handlers import register_governance_event_handlers

    register_governance_event_handlers()

    return test_app


@pytest.fixture
def account_actief_zonder_database() -> Iterator[None]:
    """Opt-in: de accountcontrole van de middleware staat uit voor tests met een verzonnen gebruiker.

    Voor tests die iets anders meten (tenantisolatie, RBAC) met een token voor een gebruiker die
    niet in de database staat. De controle zelf (uitgezet = 401, database weg = 503) wordt gemeten in
    `tests/integration/test_uitgeschakeld_is_uitgeschakeld.py`, met echte gebruikers.
    """
    from unittest.mock import AsyncMock, patch

    from src.core.auth import account_status

    with patch.object(
        account_status,
        "haal_account_status",
        AsyncMock(return_value=account_status.AccountStatus.ACTIEF),
    ):
        yield


@pytest_asyncio.fixture(scope="function")
async def integration_client(
    integration_app: FastAPI, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """Function-scoped async HTTP client with DB override."""
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.database.database import get_db
    from src.core.database.session import get_db_session

    async def override_get_db():
        yield postgres_session

    integration_app.dependency_overrides[get_db] = override_get_db
    integration_app.dependency_overrides[api_get_db] = override_get_db
    integration_app.dependency_overrides[get_db_session] = override_get_db

    transport = ASGITransport(app=integration_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=True
    ) as client:
        yield client

    # Cleanup
    for dep in [get_db, api_get_db, get_db_session]:
        if dep in integration_app.dependency_overrides:
            del integration_app.dependency_overrides[dep]

@pytest_asyncio.fixture(scope="function")
async def authenticated_client(
    integration_app: FastAPI, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """Function-scoped async HTTP client with DB override + mock admin user.

    Use this fixture for tests that hit endpoints requiring authentication.
    """
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_db
    from src.core.database.session import get_db_session

    async def override_get_db():
        yield postgres_session

    async def override_get_current_user():
        from types import SimpleNamespace

        return SimpleNamespace(
            id=1,
            email="admin@integration.test",
            tenant_id=1,
            is_active=True,
            is_superuser=True,
            roles=["admin"],
        )

    integration_app.dependency_overrides[get_db] = override_get_db
    integration_app.dependency_overrides[api_get_db] = override_get_db
    integration_app.dependency_overrides[get_db_session] = override_get_db
    integration_app.dependency_overrides[get_current_user] = override_get_current_user

    token = _build_test_token(
        user_id=1,
        email="admin@integration.test",
        tenant_id=1,
        scopes=["admin:*"],
    )
    transport = ASGITransport(app=integration_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        follow_redirects=True,
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client

    for dep in [get_db, api_get_db, get_db_session, get_current_user]:
        if dep in integration_app.dependency_overrides:
            del integration_app.dependency_overrides[dep]


@pytest_asyncio.fixture(scope="function")
async def unauthenticated_client(
    integration_app: FastAPI, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """Function-scoped async HTTP client with DB override but NO auth override.

    Use this fixture for tests that assert authentication behaviour (401/403).
    """
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.database.database import get_db
    from src.core.database.session import get_db_session

    async def override_get_db():
        yield postgres_session

    integration_app.dependency_overrides[get_db] = override_get_db
    integration_app.dependency_overrides[api_get_db] = override_get_db
    integration_app.dependency_overrides[get_db_session] = override_get_db

    transport = ASGITransport(app=integration_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=True
    ) as client:
        yield client

    for dep in [get_db, api_get_db, get_db_session]:
        if dep in integration_app.dependency_overrides:
            del integration_app.dependency_overrides[dep]


@pytest.fixture(scope="function", autouse=True)
def reset_cache_singleton():
    """Reset the global async cache singleton and Redis pool before every test.

    Prevents RuntimeError from redis.asyncio clients bound to a closed event loop
    when pytest-asyncio creates a fresh loop per test.
    """
    from src.core.caching.cache_layer import _cache_instance

    # pylint: disable=protected-access
    if _cache_instance is not None:
        _cache_instance.connected = False
        _cache_instance.redis_client = None

    import src.core.caching.cache_layer as cache_layer_module

    cache_layer_module._cache_instance = None

    # Also reset the global Redis connection pool from redis.py
    from src.core.database.redis import reset_redis_pool

    reset_redis_pool()
    yield


@pytest.fixture(scope="function", autouse=True)
def reset_rate_limiter():
    """Reset InMemoryRateLimiter singleton between integration tests.

    The governance rate limiter is a module-level singleton that accumulates
    request counts across tests. Without a reset, tests that run after
    high-traffic tests (e.g. test_concurrent_decisions with 50 requests)
    receive 429 responses, failing even though they are individually valid.
    Mirrors the setup_method reset pattern used in unit tests.
    """
    from src.core.governance.rate_limiter import _rate_limiter

    _rate_limiter._requests.clear()
    _rate_limiter._last_cleanup = 0.0
    yield
    _rate_limiter._requests.clear()
    _rate_limiter._last_cleanup = 0.0


# ============================================================================
# AUTHENTICATION FIXTURES
# ============================================================================


def _build_test_token(
    *, user_id: int, email: str, tenant_id: int, scopes: list[str] | None = None
) -> str:
    """Create a JWT for a seeded integration user without hitting login rate limits."""
    data: dict[str, Any] = {
        "sub": str(user_id),
        "user_id": user_id,
        "email": email,
        "tenant_id": tenant_id,
    }
    if scopes is not None:
        data["scopes"] = scopes
    return jwt_handler.create_access_token(data=data)


@pytest_asyncio.fixture(scope="function")
async def admin_token() -> str:
    """Get admin JWT token for the seeded integration admin user.

    Does NOT depend on integration_client -- the token is a pure computation
    over constants and avoids spinning up the full HTTP client/session/engine
    chain for callers that only need a header value.
    """
    return _build_test_token(
        user_id=1,
        email="admin@integration.test",
        tenant_id=1,
        scopes=["admin:*"],
    )


@pytest_asyncio.fixture(scope="function")
async def normal_user_token() -> str:
    """Get normal user JWT token for the seeded integration user."""
    return _build_test_token(user_id=2, email="user@integration.test", tenant_id=1)


@pytest.fixture(scope="function")
def admin_auth_headers(admin_token: str) -> dict[str, str]:
    """Return Authorization headers with admin token."""
    return {"Authorization": f"Bearer {admin_token}"}


# ============================================================================
# ALIASES FOR BACKWARD COMPATIBILITY
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def db_session(
    postgres_session: AsyncSession,
) -> AsyncGenerator[AsyncSession, None]:
    """Alias for postgres_session."""
    yield postgres_session


@pytest_asyncio.fixture(scope="function")
async def async_session(
    postgres_session: AsyncSession,
) -> AsyncGenerator[AsyncSession, None]:
    """Alias for postgres_session."""
    yield postgres_session


@pytest_asyncio.fixture(scope="function")
async def client(integration_client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    """Alias for integration_client."""
    yield integration_client


# ============================================================================
# SESSION FIXTURE
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_tenant(postgres_session: AsyncSession) -> dict[str, Any]:
    """Return the pre-seeded test tenant."""
    from sqlalchemy import select

    from src.core.database.tenant_query_filter import TenantFilterBypass
    from src.core.models.rbac_models import Tenant

    with TenantFilterBypass():
        result = await postgres_session.execute(select(Tenant).where(Tenant.id == 1))
        tenant = result.scalar_one()
        return {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "domain": tenant.domain,
        }


# ============================================================================
# MISSING FIXTURES - Added for test compatibility
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def normal_user_with_token() -> dict[str, Any]:
    """Return token and seeded user info without hitting login rate limits."""
    return {
        "token": _build_test_token(user_id=2, email="user@integration.test", tenant_id=1),
        "user_id": 2,
        "email": "user@integration.test",
        "tenant_id": 1,
    }


@pytest_asyncio.fixture(scope="function")
async def test_user_with_token(
    normal_user_with_token: dict[str, Any],
) -> dict[str, Any]:
    """Alias for normal_user_with_token."""
    return normal_user_with_token


@pytest_asyncio.fixture(scope="function")
async def test_user_token(normal_user_with_token: dict[str, Any]) -> str:
    """Return only the JWT string for the normal test user."""
    return normal_user_with_token["token"]


@pytest_asyncio.fixture(scope="function")
async def admin_user_with_token() -> dict[str, Any]:
    """Return admin token and seeded user info without hitting login rate limits."""
    return {
        "token": _build_test_token(
            user_id=1,
            email="admin@integration.test",
            tenant_id=1,
            scopes=["admin:*"],
        ),
        "user_id": 1,
        "email": "admin@integration.test",
        "tenant_id": 1,
    }


@pytest.fixture(scope="function")
def test_user() -> dict[str, Any]:
    """Pre-seeded regular user (id=2, user@integration.test, password=UserPass123!)."""
    return {
        "id": 2,
        "email": "user@integration.test",
        "password": "UserPass123!",
        "tenant_id": 1,
    }


@pytest.fixture(scope="function")
def test_admin_user() -> dict[str, Any]:
    """Pre-seeded admin user (id=1, admin@integration.test, password=AdminPass123!)."""
    return {
        "id": 1,
        "email": "admin@integration.test",
        "password": "AdminPass123!",
        "tenant_id": 1,
    }


@pytest_asyncio.fixture(scope="function")
async def test_tenant_2(postgres_session: AsyncSession) -> dict[str, Any]:
    """Return the pre-seeded secondary tenant (id=2, slug=other)."""
    from sqlalchemy import select

    from src.core.database.tenant_query_filter import TenantFilterBypass
    from src.core.models.rbac_models import Tenant

    with TenantFilterBypass():
        result = await postgres_session.execute(select(Tenant).where(Tenant.id == 2))
        tenant = result.scalar_one()
        return {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "domain": tenant.domain,
        }


@pytest_asyncio.fixture(scope="function")
async def test_client(
    integration_client: AsyncClient,
) -> AsyncGenerator[AsyncClient, None]:
    """Alias for integration_client."""
    yield integration_client


@pytest_asyncio.fixture(scope="function")
async def async_client(
    integration_client: AsyncClient,
) -> AsyncGenerator[AsyncClient, None]:
    """Alias for integration_client (async variant name)."""
    yield integration_client


# ============================================================================
# AUTHENTICATED API CLIENT
# ============================================================================


class AuthenticatedAPIClient:
    """
    High-level API client that auto-injects an Authorization header and
    returns response bodies as plain dicts (supports optional schema_type
    parameter for forward-compatible usage).
    """

    def __init__(self, client: AsyncClient, token: str) -> None:
        self._client = client
        self._auth_headers = {"Authorization": f"Bearer {token}"}

    # ------------------------------------------------------------------
    # Convenience methods -- return parsed JSON (raises on non-2xx JSON)
    # ------------------------------------------------------------------

    async def post(
        self,
        url: str,
        data: Any = None,
        *,
        json: Any = None,
        schema_type: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload = json if json is not None else data
        response = await self._client.post(url, json=payload, headers=self._auth_headers, **kwargs)
        return response.json()

    async def get(
        self,
        url: str,
        schema_type: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response = await self._client.get(url, headers=self._auth_headers, **kwargs)
        return response.json()

    async def put(
        self,
        url: str,
        data: Any = None,
        *,
        json: Any = None,
        schema_type: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload = json if json is not None else data
        response = await self._client.put(url, json=payload, headers=self._auth_headers, **kwargs)
        return response.json()

    async def patch(
        self,
        url: str,
        data: Any = None,
        *,
        json: Any = None,
        schema_type: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload = json if json is not None else data
        response = await self._client.patch(url, json=payload, headers=self._auth_headers, **kwargs)
        return response.json()

    async def delete(
        self,
        url: str,
        schema_type: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response = await self._client.delete(url, headers=self._auth_headers, **kwargs)
        return response.json()

    # ------------------------------------------------------------------
    # Raw method -- returns the full httpx.Response for status/header
    # assertions and error-mode testing.
    #
    # Usage:
    #   resp = await api.request("POST", "/api/v1/...", json={...})
    #   assert resp.status_code == 422
    # ------------------------------------------------------------------

    async def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Response:
        """Low-level method returning the raw httpx.Response.

        Allows callers to assert against status codes, headers, and
        non-JSON bodies -- useful for testing failure/error paths where
        the high-level convenience methods would raise on .json().
        """
        extra_headers = kwargs.pop("headers", {})
        return await self._client.request(
            method, url, headers={**self._auth_headers, **extra_headers}, **kwargs
        )

    async def login(self, email: str, password: str) -> dict[str, Any]:
        """Perform a login and return the token response dict."""
        response = await self._client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": password},
        )
        return response.json()


@pytest_asyncio.fixture(scope="function")
async def authenticated_api(
    integration_client: AsyncClient,
    normal_user_with_token: dict[str, Any],
) -> AuthenticatedAPIClient:
    """
    Return an AuthenticatedAPIClient pre-configured with the normal user token.
    Calls like `await authenticated_api.post(url, json=payload)` automatically
    include the Bearer token and return the parsed JSON dict.
    """
    return AuthenticatedAPIClient(integration_client, normal_user_with_token["token"])


# ============================================================================
# MISSING FIXTURES (referenced by tests, never defined)
# ============================================================================


@pytest.fixture(scope="function")
def test_tenant_id() -> int:
    """Return the ID of the pre-seeded default tenant."""
    return 1


@pytest_asyncio.fixture(scope="function")
async def db(postgres_session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Alias for postgres_session — used by DSAR and other tests expecting 'db: AsyncSession'."""
    yield postgres_session


@pytest.fixture(scope="function")
def tenant_fixture() -> Any:
    """Return the seeded default tenant as a namespace (supports .id, .name, etc.)."""
    from types import SimpleNamespace

    return SimpleNamespace(id=1, name="Default Tenant", slug="default", domain="default.local")


@pytest.fixture(scope="function")
def other_tenant_fixture() -> Any:
    """Return the seeded secondary tenant as a namespace — for tenant-isolation tests."""
    from types import SimpleNamespace

    return SimpleNamespace(id=2, name="Other Tenant", slug="other", domain="other.local")


@pytest_asyncio.fixture(scope="function")
async def client_no_auth(integration_client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    """An AsyncClient without Authorization headers — for testing 401/403 paths."""
    yield integration_client


@pytest_asyncio.fixture(scope="function")
async def normal_user_with_workflow_scopes() -> dict[str, Any]:
    """Normal user token that includes workflow-related scopes.

    Mirrors normal_user_with_token but adds workflow:read + workflow:write claims
    so that workflow versioning / sprint-3 endpoints accept the token.
    """
    token = jwt_handler.create_access_token(
        data={
            "sub": "2",
            "user_id": 2,
            "email": "user@integration.test",
            "tenant_id": 1,
            "scopes": [
                "workflows:read",
                "workflows:write",
                "workflows:execute",
                "agents:read",
                "agents:write",
            ],
        }
    )
    return {"token": token, "user_id": 2, "email": "user@integration.test", "tenant_id": 1}


@pytest_asyncio.fixture(scope="function")
async def authenticated_workflow_api(
    integration_client: AsyncClient,
    normal_user_with_workflow_scopes: dict[str, Any],
) -> AuthenticatedAPIClient:
    """AuthenticatedAPIClient pre-configured with workflow-scoped token."""
    return AuthenticatedAPIClient(integration_client, normal_user_with_workflow_scopes["token"])
