"""Unit tests for src.core.database.url_converter."""

import pytest

from src.core.database.url_converter import convert_db_url_for_sync_driver


def test_convert_db_url_postgresql_asyncpg():
    """Converts postgresql+asyncpg:// to postgresql://."""
    async_url = "postgresql+asyncpg://user:password@localhost:5432/testdb"
    expected = "postgresql://user:password@localhost:5432/testdb"
    assert convert_db_url_for_sync_driver(async_url) == expected


def test_convert_db_url_sqlite_aiosqlite():
    """Converts sqlite+aiosqlite:// to sqlite://."""
    async_url = "sqlite+aiosqlite:///test.db"
    expected = "sqlite:///test.db"
    assert convert_db_url_for_sync_driver(async_url) == expected


def test_convert_db_url_empty_raises_value_error():
    """Empty or None database_url raises ValueError."""
    with pytest.raises(ValueError, match="database_url cannot be None or empty"):
        convert_db_url_for_sync_driver("")

    with pytest.raises(ValueError, match="database_url cannot be None or empty"):
        convert_db_url_for_sync_driver(None)  # type: ignore[arg-type]


def test_convert_db_url_alembic_local(monkeypatch):
    """Substitutes docker hostnames with localhost when ALEMBIC_LOCAL=1."""
    monkeypatch.setenv("ALEMBIC_LOCAL", "1")

    url1 = "postgresql+asyncpg://postgres:secret@postgres:5432/sanskriti"
    expected1 = "postgresql://postgres:secret@localhost:5432/sanskriti"
    assert convert_db_url_for_sync_driver(url1) == expected1

    url2 = "postgresql+asyncpg://postgres:secret@postgres-prodmirror:5432/sanskriti"
    expected2 = "postgresql://postgres:secret@localhost:5432/sanskriti"
    assert convert_db_url_for_sync_driver(url2) == expected2


def test_convert_db_url_alembic_local_disabled(monkeypatch):
    """Leaves hostnames untouched when ALEMBIC_LOCAL is 0 or unset."""
    monkeypatch.delenv("ALEMBIC_LOCAL", raising=False)

    url = "postgresql+asyncpg://postgres:secret@postgres:5432/sanskriti"
    expected = "postgresql://postgres:secret@postgres:5432/sanskriti"
    assert convert_db_url_for_sync_driver(url) == expected
