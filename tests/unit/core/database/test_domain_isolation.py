"""Unit tests for src.core.database.domain_isolation."""

import pytest
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.core.database.domain_isolation import (
    DomainRegistry,
    register_domain,
    IsolatedDB,
    DomainMigrationHelper,
    isolated_db_session,
    domain_registry,
)


class BaseA(DeclarativeBase):
    pass


class ModelA(BaseA):
    __tablename__ = "table_a"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, default="test")


class BaseB(DeclarativeBase):
    pass


class ModelB(BaseB):
    __tablename__ = "table_b"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    a_id: Mapped[int] = mapped_column(Integer, ForeignKey("table_a.id"))


def test_domain_registry_register_and_get():
    """Register and retrieve Base and Metadata."""
    registry = DomainRegistry()
    registry.register("domain_a", BaseA, dependencies=["dep_x"])

    assert registry.get_base("domain_a") is BaseA
    assert registry.get_metadata("domain_a") is BaseA.metadata

    with pytest.raises(KeyError, match="Domain 'unknown' not registered"):
        registry.get_base("unknown")


def test_register_domain_decorator():
    """Decorator registers domain in global domain_registry."""
    @register_domain("decorated_domain", dependencies=["dep_1"])
    class DecoratedBase(DeclarativeBase):
        pass

    assert domain_registry.get_base("decorated_domain") is DecoratedBase
    assert domain_registry._dependencies["decorated_domain"] == ["dep_1"]


@pytest.mark.asyncio
async def test_domain_registry_create_isolated_engine():
    """Creates an AsyncEngine with StaticPool."""
    registry = DomainRegistry()
    engine = registry.create_isolated_engine("test_domain")
    assert isinstance(engine, AsyncEngine)
    await engine.dispose()


class BaseDep(DeclarativeBase):
    pass


class ModelDep(BaseDep):
    __tablename__ = "table_dep"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String, default="dep")


@pytest.mark.asyncio
async def test_domain_registry_create_isolated_tables_with_dependencies():
    """Creates tables for target domain and its dependencies."""
    registry = DomainRegistry()
    registry.register("domain_a", BaseA)
    registry.register("domain_dep", BaseDep, dependencies=["domain_a"])

    engine = registry.create_isolated_engine("domain_dep")
    await registry.create_isolated_tables("domain_dep", engine, include_dependencies=True)

    # Validate tables exist
    async with engine.connect() as conn:
        from sqlalchemy import text
        res = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = {row[0] for row in res.fetchall()}
        assert "table_a" in tables
        assert "table_dep" in tables

    await engine.dispose()


def test_get_cross_domain_relationships():
    """Detects foreign keys pointing across domain boundaries."""
    registry = DomainRegistry()
    registry.register("domain_a", BaseA)
    registry.register("domain_b", BaseB)

    relationships = registry.get_cross_domain_relationships()
    assert len(relationships) == 1
    rel = relationships[0]
    assert rel["from_domain"] == "domain_b"
    assert rel["from_table"] == "table_b"
    assert rel["to_domain"] == "domain_a"
    assert rel["to_table"] == "table_a"
    assert rel["column"] == "a_id"


@pytest.mark.asyncio
async def test_isolated_db_context_manager(monkeypatch):
    """IsolatedDB context manager yields an active session and cleans up."""
    domain_registry.register("isolated_test_domain", BaseA)

    async with IsolatedDB("isolated_test_domain") as session:
        assert isinstance(session, AsyncSession)
        item = ModelA(id=1, name="isolated")
        session.add(item)
        await session.flush()
        assert item.id == 1


def test_domain_migration_helper():
    """Generates standalone Alembic migration script."""
    domain_registry.register("migration_test_domain", BaseA)
    helper = DomainMigrationHelper("migration_test_domain")
    script = helper.generate_migration_script()

    assert "migration_test_domain Domain Migration" in script
    assert "def upgrade() -> None:" in script
    assert "def downgrade() -> None:" in script
    assert "op.drop_table('table_a')" in script


@pytest.mark.asyncio
async def test_isolated_db_session_helper():
    """isolated_db_session async context manager yields usable AsyncSession."""
    domain_registry.register("session_helper_domain", BaseA)

    async with isolated_db_session("session_helper_domain") as session:
        assert isinstance(session, AsyncSession)
        item = ModelA(id=99, name="session_item")
        session.add(item)
        await session.flush()
        assert item.name == "session_item"


@pytest.mark.asyncio
async def test_isolated_db_cleans_up_engine_on_exit(monkeypatch):
    """IsolatedDB.__aexit__ must dispose the engine (verifies dispose is not unreachable)."""
    domain_registry.register("cleanup_test_domain", BaseA)

    disposed = False
    orig_dispose = AsyncEngine.dispose

    async def track_dispose(self):
        nonlocal disposed
        disposed = True
        await orig_dispose(self)

    monkeypatch.setattr(AsyncEngine, "dispose", track_dispose)

    db = IsolatedDB("cleanup_test_domain")
    async with db as session:
        assert isinstance(session, AsyncSession)

    assert disposed is True, "engine.dispose() was not called on __aexit__ (unreachable code bug)"

