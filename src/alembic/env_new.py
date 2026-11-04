import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool

from alembic import context

# Add the parent directory (src/) to the Python path for imports
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if src_path not in sys.path:
    sys.path.insert(0, src_path)


# Import CANONICAL Base from database.py (single source of truth)
# NOTE: core.database.models now imports this same Base, so all models use one metadata
from src.core.database.database import Base
from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Load environment variables from .env file
# Skip loading .env if DATABASE_URL is already set from environment (Docker)
if not os.getenv("DATABASE_URL"):
    from dotenv import load_dotenv

    load_dotenv(override=True)

# Get DATABASE_URL from environment variable
database_url = os.getenv("DATABASE_URL")

# If DATABASE_URL is not set, fall back to the one in alembic.ini
if database_url:
    # Convert asyncpg URL to psycopg2 for Alembic CLI compatibility (Serena MCP 2025-10-01)
    database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    # Detect if running in Docker container
    # If DATABASE_URL has 'sanskriti-postgres-test', we're in Docker, keep as-is
    # If it has 'postgres:', we're in dev local env, convert to localhost
    if "@sanskriti-postgres-test:" not in database_url:
        database_url = database_url.replace("@postgres:", "@localhost:")

    config.set_main_option("sqlalchemy.url", database_url)
    print(f"[Alembic] Using DATABASE_URL: {database_url_zonder_wachtwoord(database_url)}")

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use the canonical Base metadata (all models registered here now)
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    if url is None:
        raise ValueError(
            "No database URL configured. Set DATABASE_URL environment variable "
            "or sqlalchemy.url in alembic.ini"
        )

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Get the URL from the main option (respects both env var and alembic.ini)
    url = config.get_main_option("sqlalchemy.url")
    if url is None:
        raise ValueError(
            "No database URL configured. Set DATABASE_URL environment variable "
            "or sqlalchemy.url in alembic.ini"
        )

    # Create engine directly with the URL
    from sqlalchemy import create_engine

    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
