"""
tests/fixtures/database_mocks.py - Database Mocking Utilities

Provides in-memory repositories, tenant context mocks, and transaction helpers.
All mocks are isolated and don't require external database connections.

KEY PRINCIPLES:
1. Generic repository pattern for any model
2. In-memory storage (no DB required)
3. Thread-safe operations
4. Tenant isolation support

Created: 2025-12-11
"""

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar

import pytest

# Type variable for generic repository
T = TypeVar("T")


# ============================================================================
# IN-MEMORY REPOSITORY (Generic)
# ============================================================================


class InMemoryRepository(Generic[T]):
    """
    Generic in-memory repository for any model.

    Provides CRUD operations without database dependency.
    Useful for testing business logic in isolation.

    Example:
        >>> from src.core.models.rbac_models import User
        >>> repo = InMemoryRepository(User)
        >>> user = User(id=1, email="test@example.com", tenant_id=1)
        >>> await repo.add(user)
        >>> found = await repo.get_by_id(1)
        >>> assert found.email == "test@example.com"
    """

    def __init__(
        self,
        model: Type[T],
        tenant_aware: bool = True,
    ):
        """
        Initialize repository.

        Args:
            model: SQLAlchemy model class
            tenant_aware: If True, filter by tenant_id automatically
        """
        self.model = model
        self.tenant_aware = tenant_aware
        self._storage: Dict[Any, T] = {}  # id -> instance
        self._next_id = 1
        self._tenant_context: Optional[int] = None
        self.call_log: List[Dict[str, Any]] = []

    def set_tenant_context(self, tenant_id: Optional[int]):
        """Set current tenant for filtering."""
        self._tenant_context = tenant_id

    async def add(self, instance: T) -> T:
        """
        Add instance to repository.

        Auto-assigns ID if not set.
        """
        self.call_log.append({"method": "add", "model": self.model.__name__})

        # Auto-assign ID if not set
        if not hasattr(instance, "id") or instance.id is None:
            instance.id = self._next_id
            self._next_id += 1

        # Store deep copy to prevent external mutations
        self._storage[instance.id] = deepcopy(instance)
        return instance

    async def get_by_id(self, id: Any) -> Optional[T]:
        """
        Get instance by ID.

        Respects tenant context if tenant_aware=True.
        """
        self.call_log.append({"method": "get_by_id", "id": id})

        instance = self._storage.get(id)

        # Check tenant isolation
        if instance and self.tenant_aware and self._tenant_context:
            if hasattr(instance, "tenant_id"):
                if instance.tenant_id != self._tenant_context:
                    return None  # Tenant mismatch

        return deepcopy(instance) if instance else None

    async def get_all(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[T]:
        """
        Get all instances with optional filtering.

        Args:
            filters: Dict of field_name -> value to filter by
            limit: Max results to return
            offset: Skip first N results

        Returns:
            List of matching instances
        """
        self.call_log.append({"method": "get_all", "filters": filters})

        results = list(self._storage.values())

        # Apply tenant filtering
        if self.tenant_aware and self._tenant_context:
            results = [
                r
                for r in results
                if hasattr(r, "tenant_id") and r.tenant_id == self._tenant_context
            ]

        # Apply custom filters
        if filters:
            for field, value in filters.items():
                results = [r for r in results if hasattr(r, field) and getattr(r, field) == value]

        # Apply pagination
        results = results[offset:]
        if limit:
            results = results[:limit]

        return [deepcopy(r) for r in results]

    async def update(self, instance: T) -> T:
        """Update existing instance."""
        self.call_log.append({"method": "update", "id": instance.id})

        if instance.id not in self._storage:
            raise ValueError(f"{self.model.__name__} with id={instance.id} not found")

        self._storage[instance.id] = deepcopy(instance)
        return instance

    async def delete(self, id: Any) -> bool:
        """
        Delete instance by ID.

        Returns:
            True if deleted, False if not found
        """
        self.call_log.append({"method": "delete", "id": id})

        if id in self._storage:
            del self._storage[id]
            return True

        return False

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count instances with optional filters."""
        results = await self.get_all(filters=filters)
        return len(results)

    def reset(self):
        """Clear all data."""
        self._storage.clear()
        self.call_log.clear()
        self._next_id = 1


# ============================================================================
# MOCK TENANT CONTEXT
# ============================================================================


@dataclass
class MockTenantContext:
    """
    Mock tenant context for testing multi-tenant logic.

    Simulates tenant isolation without middleware.

    Example:
        >>> ctx = MockTenantContext(tenant_id=1)
        >>> with ctx:
        ...     # Code here runs with tenant_id=1
        ...     pass
    """

    tenant_id: Optional[int]
    bypass_filter: bool = False
    user_id: Optional[int] = None

    def __enter__(self):
        """Enter context (use in 'with' statement)."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context."""
        pass

    async def __aenter__(self):
        """Async enter context."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async exit context."""
        pass


# ============================================================================
# TRANSACTION MOCKS
# ============================================================================


class MockTransaction:
    """
    Mock database transaction.

    Simulates commit/rollback behavior without real database.

    Example:
        >>> async with MockTransaction() as tx:
        ...     # Do work
        ...     await tx.commit()
    """

    def __init__(self):
        """Initialize transaction."""
        self.committed = False
        self.rolled_back = False
        self.active = True

    async def commit(self):
        """Commit transaction."""
        if not self.active:
            raise RuntimeError("Transaction already finished")

        self.committed = True
        self.active = False

    async def rollback(self):
        """Rollback transaction."""
        if not self.active:
            raise RuntimeError("Transaction already finished")

        self.rolled_back = True
        self.active = False

    async def __aenter__(self):
        """Start transaction."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Auto-rollback on exception."""
        if self.active:
            if exc_type:
                await self.rollback()
            else:
                await self.commit()


class MockSession:
    """
    Mock database session with transaction support.

    Example:
        >>> session = MockSession()
        >>> async with session.begin():
        ...     # Transaction context
        ...     pass
    """

    def __init__(self):
        """Initialize session."""
        self.in_transaction = False
        self.committed_count = 0
        self.rollback_count = 0

    def begin(self) -> MockTransaction:
        """Begin new transaction."""
        self.in_transaction = True
        return MockTransaction()

    async def commit(self):
        """Commit current work."""
        self.committed_count += 1

    async def rollback(self):
        """Rollback current work."""
        self.rollback_count += 1

    async def close(self):
        """Close session."""
        self.in_transaction = False


# ============================================================================
# QUERY BUILDER MOCK
# ============================================================================


class MockQuery:
    """
    Mock SQLAlchemy query builder.

    Provides chainable filter/order/limit methods.

    Example:
        >>> query = MockQuery([user1, user2, user3])
        >>> results = query.filter(email="test@example.com").limit(1).all()
    """

    def __init__(self, data: List[T]):
        """
        Initialize with dataset.

        Args:
            data: List of objects to query
        """
        self._data = data
        self._filters: List[Callable] = []
        self._limit: Optional[int] = None
        self._offset: int = 0
        self._order_by: Optional[Callable] = None

    def filter(self, **kwargs) -> "MockQuery":
        """Add filter condition."""

        def filter_fn(obj):
            return all(getattr(obj, k, None) == v for k, v in kwargs.items())

        self._filters.append(filter_fn)
        return self

    def filter_by(self, **kwargs) -> "MockQuery":
        """Alias for filter (SQLAlchemy compatibility)."""
        return self.filter(**kwargs)

    def order_by(self, key: Callable) -> "MockQuery":
        """Set ordering function."""
        self._order_by = key
        return self

    def limit(self, n: int) -> "MockQuery":
        """Limit results."""
        self._limit = n
        return self

    def offset(self, n: int) -> "MockQuery":
        """Skip first N results."""
        self._offset = n
        return self

    def all(self) -> List[T]:
        """Execute query and return all results."""
        results = self._data

        # Apply filters
        for filter_fn in self._filters:
            results = [r for r in results if filter_fn(r)]

        # Apply ordering
        if self._order_by:
            results = sorted(results, key=self._order_by)

        # Apply pagination
        results = results[self._offset :]
        if self._limit:
            results = results[: self._limit]

        return results

    def first(self) -> Optional[T]:
        """Get first result."""
        results = self.all()
        return results[0] if results else None

    def count(self) -> int:
        """Count results."""
        return len(self.all())


# ============================================================================
# PYTEST FIXTURES
# ============================================================================


@pytest.fixture
def in_memory_repository():
    """
    Factory fixture for creating InMemoryRepository instances.

    Usage:
        def test_repo(in_memory_repository):
            user_repo = in_memory_repository(User)
            await user_repo.add(User(email="test@example.com"))
    """

    def factory(model: Type[T], tenant_aware: bool = True) -> InMemoryRepository[T]:
        return InMemoryRepository(model, tenant_aware=tenant_aware)

    return factory


@pytest.fixture
def mock_tenant_context() -> MockTenantContext:
    """
    Provide MockTenantContext.

    Usage:
        def test_isolation(mock_tenant_context):
            async with mock_tenant_context:
                # Tenant context is active
                assert mock_tenant_context.tenant_id == 1
    """
    return MockTenantContext(tenant_id=1)


@pytest.fixture
def mock_transaction() -> MockTransaction:
    """
    Provide MockTransaction.

    Usage:
        async def test_tx(mock_transaction):
            async with mock_transaction as tx:
                await tx.commit()
            assert mock_transaction.committed
    """
    return MockTransaction()


@pytest.fixture
def mock_session() -> MockSession:
    """
    Provide MockSession.

    Usage:
        async def test_session(mock_session):
            async with mock_session.begin():
                await mock_session.commit()
    """
    return MockSession()


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================


def create_repository(
    model: Type[T],
    initial_data: Optional[List[T]] = None,
    tenant_aware: bool = True,
) -> InMemoryRepository[T]:
    """
    Factory for creating pre-populated repository.

    Example:
        >>> repo = create_repository(User, initial_data=[user1, user2])
        >>> count = await repo.count()
        >>> assert count == 2
    """
    repo = InMemoryRepository(model, tenant_aware=tenant_aware)

    if initial_data:
        # Use asyncio.run in factory (sync context)
        async def populate():
            for item in initial_data:
                await repo.add(item)

        asyncio.run(populate())

    return repo
