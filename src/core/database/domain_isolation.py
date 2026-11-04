"""
Domain Database Isolation System

Provides clean separation between domain models to prevent:
- Schema conflicts
- Cross-domain coupling
- Testing difficulties

Architecture:
-------------
Each domain has its own Base/metadata, with explicit shared dependencies only.

Example:
    canvas/          -> CanvasBase
    workflow/        -> WorkflowBase
    shared/          -> SharedBase (junction tables, events)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import TracebackType
from typing import Any, List, Optional
from collections.abc import AsyncGenerator, Callable

from sqlalchemy import MetaData
from sqlalchemy.exc import NoReferencedTableError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool


class DomainRegistry:
    """
    Registry for domain-specific database metadata.

    Usage:
        # Register a domain
        registry = DomainRegistry()
        registry.register("canvas", CanvasBase)
        registry.register("workflow", WorkflowBase)

        # Get isolated engine
        engine = registry.create_isolated_engine("canvas")
    """

    def __init__(self) -> None:
        self._domains: dict[str, type[DeclarativeBase]] = {}
        self._dependencies: dict[str, list[str]] = {}

    def register(
        self,
        name: str,
        base: type[DeclarativeBase],
        dependencies: list[str] | None = None,
    ) -> None:
        """
        Register a domain with its Base class.

        Args:
            name: Domain name (e.g., "canvas", "workflow")
            base: SQLAlchemy DeclarativeBase for this domain
            dependencies: List[Any] of other domain names this domain depends on  # TODO(TYPE): replace Any with concrete type
        """
        self._domains[name] = base
        self._dependencies[name] = dependencies or []

    def get_base(self, name: str) -> type[DeclarativeBase]:
        """Get the Base class for a domain."""
        if name not in self._domains:
            raise KeyError(f"Domain '{name}' not registered")
        return self._domains[name]

    def get_metadata(self, name: str) -> MetaData:
        """Get the metadata for a domain."""
        return self.get_base(name).metadata

    def create_isolated_engine(
        self,
        domain: str,
        database_url: str = "sqlite+aiosqlite:///:memory:",
        **engine_kwargs: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> AsyncEngine:
        """
        Create an engine with only this domain's tables.

        This is perfect for isolated testing of a single domain.
        """
        defaults: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        }
        defaults.update(engine_kwargs)

        engine = create_async_engine(database_url, **defaults)
        return engine

    async def create_isolated_tables(
        self, domain: str, engine: AsyncEngine, include_dependencies: bool = True
    ) -> None:
        """
        Create tables for a domain (optionally including dependencies).

        Args:
            domain: Domain name
            engine: SQLAlchemy async engine
            include_dependencies: Whether to also create dependency tables
        """
        domains_to_create = [domain]

        if include_dependencies:
            # Add dependencies (avoid duplicates)
            deps = self._dependencies.get(domain, [])
            for dep in deps:
                if dep not in domains_to_create:
                    domains_to_create.insert(0, dep)  # Dependencies first

        async with engine.begin() as conn:
            for dom in domains_to_create:
                base = self._domains[dom]
                await conn.run_sync(base.metadata.create_all)

    def get_cross_domain_relationships(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Analyze and return all cross-domain foreign keys.

        This helps identify coupling that should be refactored.
        """
        relationships: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        for domain_name, base in self._domains.items():
            for table in base.metadata.tables.values():
                for fk in table.foreign_keys:
                    try:
                        target_table = fk.column.table.name
                        target_schema = fk.column.table.schema
                    except NoReferencedTableError:
                        tokens = fk.target_fullname.split(".")
                        target_table = tokens[-2] if len(tokens) >= 2 else tokens[0]
                        target_schema = tokens[-3] if len(tokens) >= 3 else None

                    # Determine target domain
                    target_domain = None
                    for dname, dbase in self._domains.items():
                        if target_table in dbase.metadata.tables:
                            target_domain = dname
                            break

                    if target_domain and target_domain != domain_name:
                        relationships.append(
                            {
                                "from_domain": domain_name,
                                "from_table": table.name,
                                "to_domain": target_domain,
                                "to_table": target_table,
                                "column": fk.parent.name,
                            }
                        )

        return relationships


# Global registry instance
domain_registry = DomainRegistry()


def register_domain(
    name: str, dependencies: list[str] | None = None
) -> Callable[[type[DeclarativeBase]], type[DeclarativeBase]]:
    """
    Decorator to register a domain's Base class.

    Usage:
        @register_domain("canvas", dependencies=["users"])
        class CanvasBase(DeclarativeBase):
            pass
    """

    def decorator(cls: type[DeclarativeBase]) -> type[DeclarativeBase]:
        domain_registry.register(name, cls, dependencies)
        return cls

    return decorator


class IsolatedDB:
    """
    Context manager for isolated database sessions.

    Usage:
        async with IsolatedDB("canvas") as session:
            canvas = await session.get(Canvas, canvas_id)
    """

    def __init__(
        self,
        domain: str,
        database_url: str = "sqlite+aiosqlite:///:memory:",
        include_dependencies: bool = True,
    ) -> None:
        self.domain = domain
        self.database_url = database_url
        self.include_dependencies = include_dependencies
        self.engine: AsyncEngine | None = None
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        # Create engine
        self.engine = domain_registry.create_isolated_engine(self.domain, self.database_url)

        # Create tables
        await domain_registry.create_isolated_tables(
            self.domain, self.engine, self.include_dependencies
        )

        # Create session
        session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.session = session_factory()

        assert self.session is not None
        return self.session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        if self.session:
            await self.session.rollback()
            await self.session.close()
        if self.engine:
            await self.engine.dispose()
        return None


# Migration helper
class DomainMigrationHelper:
    """
    Helper for creating domain-specific migrations.

    Instead of one giant metadata, each domain gets its own migration chain.
    """

    def __init__(self, domain: str) -> None:
        self.domain = domain
        self.base = domain_registry.get_base(domain)

    def generate_migration_script(self) -> str:
        """Generate a standalone migration script for this domain."""

        tables = list(self.base.metadata.tables.values())

        script = f'''"""
{self.domain} Domain Migration

Auto-generated migration for {self.domain} domain.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from uuid import UUID as PyUUID

# revision identifiers
revision = "{self.domain}_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create {self.domain} domain tables."""
'''

        # Add CREATE TABLE statements
        for table in tables:
            script += f"    # Create {table.name}\n"
            # This is simplified - real implementation would use SQLAlchemy's
            # DDL generation

        script += '''

def downgrade() -> None:
    """Drop {self.domain} domain tables."""
'''

        for table in reversed(tables):
            script += f"    op.drop_table('{table.name}')\n"

        return script


# Testing utilities
@asynccontextmanager
async def isolated_db_session(
    domain: str, database_url: str = "sqlite+aiosqlite:///:memory:"
) -> AsyncGenerator[AsyncSession]:
    """
    Context manager for isolated testing.

    Usage:
        async def test_canvas():
            async with isolated_db_session("canvas") as session:
                canvas = Canvas(name="Test")
                session.add(canvas)
                await session.commit()
    """
    engine = create_async_engine(
        database_url,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Create tables
    await domain_registry.create_isolated_tables(domain, engine)

    # Create session
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()

    await engine.dispose()


# Example usage documentation
EXAMPLE_DOMAINS = """
# Example domain setup:

# 1. users/models.py
class UsersBase(DeclarativeBase):
    pass

class User(UsersBase):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

# Register
register_domain("users")(UsersBase)


# 2. canvas/models.py
class CanvasBase(DeclarativeBase):
    pass

class Canvas(CanvasBase):
    __tablename__ = "canvases"
    id: Mapped[PyUUID] = mapped_column(UUID, primary_key=True)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer)  # FK to users, but NOT enforced at DB level
    # Use application-level validation instead

# Register with dependency
register_domain("canvas", dependencies=["users"])(CanvasBase)


# 3. Testing
async def test_canvas():
    async with isolated_db_session("canvas") as session:
        # Only canvas + users tables exist
        canvas = Canvas(name="Test")
        session.add(canvas)
        await session.commit()
"""
