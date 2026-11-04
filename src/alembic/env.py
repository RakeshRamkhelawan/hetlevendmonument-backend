import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool

from alembic import context

# Add the parent directory (src/) to the Python path for imports
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from typing import Any, Literal, Optional

from sqlalchemy.sql.schema import SchemaItem
from sqlalchemy.types import TypeEngine

# CRITICAL: Save DATABASE_URL / DATABASE_URL_MIGRATIONS BEFORE importing config.
# Pydantic BaseSettings calls load_dotenv(override=True) during initialization,
# which would overwrite the CI-exported environment variable with the .env file value.
# In production, migrations run under postgres superuser via DATABASE_URL_MIGRATIONS.
database_url_from_ci = os.getenv("DATABASE_URL_MIGRATIONS") or os.getenv("DATABASE_URL")

from src.core.database.database import Base
from src.core.database.database import config as app_config
from src.core.database.model_registry import register_all_models
from src.core.database.url_converter import convert_db_url_for_sync_driver
from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord

# Register all SQLAlchemy models with Base.metadata via centralized registry.
# Failures are logged as warnings instead of crashing the migration chain.
_import_failures = register_all_models()

if _import_failures:
    print(f"[Alembic] WARNING: {len(_import_failures)} model groups failed to import:")
    for group, error in _import_failures:
        print(f"  - {group}: {error}")

# TOEGEVOEGD 2026-08-17 (ADR-036 OP-147, dit was de OORZAAK van OP-140).
#
# Er zijn twee modelregistraties en Alembic gebruikte de kleinste. Gemeten:
# `register_all_models()` levert 143 tabellen in `Base.metadata`,
# `src.core.database.import_all_models` levert er 186 -- 43 verschil, ZONDER importfouten;
# die modules stonden simpelweg niet in de registry.
#
# Alles in dat verschil is voor `--autogenerate` permanent onzichtbaar: het model bestaat,
# de tabel wordt nooit voorgesteld, er komt nooit een migratie. Zo zijn 71 tabellen zonder
# migratie ontstaan. De blinde vlek werkt ook andersom: een model dat hier ontbreekt maar
# in de DATABASE wel bestaat, ziet autogenerate als OVERBODIG -- zo verdween
# `tenants.prana_budget` (archive/a10bd0ad9807).
#
# In dezelfde TOLERANTE vorm als `register_all_models()` hierboven, en met opzet NA het
# afhandelen daarvan (Gate 2-review 2026-08-17). Deze import trekt via
# `api/v1/digital_twin/dependencies.py` ook FastAPI en de LLM-keten mee; een ontbrekende
# optionele dependency in een slanke container zou anders ELKE alembic-aanroep laten
# falen bij het laden van env.py -- nog voor migratie 1. De volledigheid zelf wordt
# bewaakt door `tests/architecture/test_every_model_is_registered.py`, niet door een
# harde import hier.
#
# PRECIES ZIJN OVER WAT DIE GUARD MEET (Gate 2-review 2026-08-17): hij vergelijkt de
# `__tablename__`-declaraties in `src/` met `Base.metadata` NA `import_all_models`. Hij meet
# NIET wat `register_all_models()` alleen zou opleveren, en hij ziet geen tabellen die via
# `sa.Table(...)` zijn gedefinieerd in plaats van als klasse. Een eerdere versie van dit
# comment beweerde dat hij 'beide registraties' bewaakt; dat was onwaar.
try:
    import src.core.database.import_all_models  # noqa: F401
except Exception as _e:  # pragma: no cover - defensief, zoals register_all_models
    print(f"[Alembic] WARNING: import_all_models failed: {type(_e).__name__}: {_e}")

config = context.config

# NOTE: Explicit DATABASE_URL env var takes priority over app_config.
# This allows ci-local.sh and GitHub CI to override the default dev database
# without modifying .env files.
# Use the saved value from BEFORE config was imported (before Pydantic could override it).
database_url = database_url_from_ci or getattr(app_config, "database_url", None)

if database_url:
    database_url = convert_db_url_for_sync_driver(database_url)

    config.set_main_option("sqlalchemy.url", database_url)
    print(f"[Alembic] Using DATABASE_URL: {database_url_zonder_wachtwoord(database_url)}")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(
    obj: SchemaItem,
    name: str | None,
    type_: Literal[
        "schema", "table", "column", "index", "unique_constraint", "foreign_key_constraint"
    ],
    reflected: bool,
    compare_to: SchemaItem | None,
) -> bool:
    """
    Only include objects that are defined in our target_metadata.
    This prevents Alembic from trying to drop tables that it doesn't know about.
    """
    if type_ == "table" and reflected and name not in target_metadata.tables:
        return False
    return True


def compare_type(
    ctx: Any,
    inspected_column: Any,
    metadata_column: Any,
    inspected_type: TypeEngine[Any],  # TODO(TYPE): replace with concrete type
    metadata_type: TypeEngine[Any],  # TODO(TYPE): replace with concrete type
) -> bool | None:
    """Treat JSON and JSONB as equivalent to prevent pre-existing drift noise.

    PostgreSQL JSON and JSONB are functionally equivalent for SQLAlchemy
    reads/writes. Flagging them as different creates persistent drift that
    has no operational impact and would require risky ALTER COLUMN ops.
    """
    from sqlalchemy import JSON as SAJSON
    from sqlalchemy.dialects.postgresql import JSONB as PGJSONB

    inspected_is_json = isinstance(inspected_type, (SAJSON, PGJSONB))
    metadata_is_json = isinstance(metadata_type, (SAJSON, PGJSONB))
    if inspected_is_json and metadata_is_json:
        return False  # no difference
    return None  # use default comparison


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if url is None:
        raise ValueError("No database URL configured.")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=compare_type,
    )

    with context.begin_transaction():
        context.run_migrations()


def _ensure_alembic_version_column_width(engine: Any) -> None:
    """Ensure alembic_version.version_num is VARCHAR(64) before migrations run.

    Alembic creates alembic_version.version_num as VARCHAR(32) by default, but
    our revision IDs are up to 46 characters. This function runs in a SEPARATE
    connection (its own committed transaction) so it does not interfere with
    Alembic's own transaction management on the migration connection.

    The function is idempotent:
    - If the table does not exist: creates it with VARCHAR(64).
    - If the table exists with a narrow column: widens it to VARCHAR(64).
    - If the table already has VARCHAR(64): no-op.
    """
    from sqlalchemy import text

    # engine.begin() opens a fresh connection, begins a transaction, and
    # auto-commits on success / rolls back on exception. NullPool guarantees
    # this connection is physically separate from the migration connection.
    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(64) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            )
        """)
        )
        # Widen the column if it was already created with the Alembic default
        # of VARCHAR(32). The DO block is idempotent: a no-op when >= 64.
        conn.execute(
            text("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name   = 'alembic_version'
                      AND column_name  = 'version_num'
                      AND character_maximum_length IS NOT NULL
                      AND character_maximum_length < 64
                ) THEN
                    ALTER TABLE alembic_version
                        ALTER COLUMN version_num TYPE VARCHAR(64);
                END IF;
            END $$;
        """)
        )
    print("[Alembic] alembic_version.version_num ensured >= VARCHAR(64)")


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if url is None:
        raise ValueError("No database URL configured.")

    from sqlalchemy import create_engine

    connectable = create_engine(url, poolclass=pool.NullPool)

    print(f"[DEBUG] Connected to database: {connectable.dialect.name}")

    # Enforce PostgreSQL for online migrations (SQLite is offline-only for CI)
    if connectable.dialect.name != "postgresql":
        raise ValueError(
            f"Online migrations require PostgreSQL, but got: {connectable.dialect.name}\n"
            f"DATABASE_URL={database_url_zonder_wachtwoord(url)}\n"
            "This may indicate a configuration error in SQLAlchemy URL or .env file."
        )

    # Ensure alembic_version.version_num is VARCHAR(64) BEFORE opening the
    # migration connection. Uses engine.begin() so the DDL is committed in its
    # own transaction and is fully visible when Alembic starts its transaction.
    _ensure_alembic_version_column_width(connectable)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=compare_type,
        )

        print("[DEBUG] Entering transaction block.")
        with context.begin_transaction():
            # Sentinel so RLS policies using current_setting('app.current_tenant', true)
            # return NULL (deny) instead of raising "unrecognized configuration parameter"
            # when the migration role is not a superuser/BYPASSRLS holder.
            from sqlalchemy import text as _text

            connection.execute(_text("SET LOCAL app.current_tenant = '0'"))
            print("[DEBUG] Running context.run_migrations()...")
            context.run_migrations()
            print("[DEBUG] Finished context.run_migrations().")


if context.is_offline_mode():
    print("[DEBUG] Running offline migrations.")
    run_migrations_offline()
else:
    print("[DEBUG] Running online migrations.")
    run_migrations_online()
print("[DEBUG] Alembic env.py execution complete.")
