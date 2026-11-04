"""Database URL converter for synchronous driver compatibility.

Converts async SQLAlchemy driver URLs to their sync equivalents for use in
Alembic migrations and offline database operations.

Example:
    Convert async SQLAlchemy URL to sync for Alembic:
    >>> from src.core.database.url_converter import convert_db_url_for_sync_driver
    >>> url = "postgresql+asyncpg://user:pass@localhost/db"
    >>> sync_url = convert_db_url_for_sync_driver(url)
    >>> print(sync_url)
    postgresql://user:pass@localhost/db
"""

import os


def convert_db_url_for_sync_driver(database_url: str) -> str:
    """
    Convert an async SQLAlchemy database URL to a synchronous driver equivalent.

    Handles:
    - postgresql+asyncpg:// -> postgresql://
    - sqlite+aiosqlite:// -> sqlite://
    - ALEMBIC_LOCAL host substitutions (postgres -> localhost)

    Args:
        database_url: A SQLAlchemy database URL string (may use async drivers).

    Returns:
        A database URL string compatible with synchronous SQLAlchemy drivers.

    Raises:
        ValueError: If database_url is None or empty.
    """
    if not database_url:
        raise ValueError("database_url cannot be None or empty")

    # Replace async driver schemes with sync equivalents
    url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("sqlite+aiosqlite://", "sqlite://")

    # ALEMBIC_LOCAL mode: replace host names for local development
    if os.getenv("ALEMBIC_LOCAL", "0") == "1":
        url = url.replace("@postgres:", "@localhost:")
        url = url.replace("@postgres-prodmirror:", "@localhost:")

    return url
