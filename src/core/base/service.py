"""
Base Service Class - Dependency Injection Pattern

Provides a standardized base class for all services with
database session injection.

Part of SC-1.1 implementation.
"""


from sqlalchemy.ext.asyncio import AsyncSession


class BaseService:
    """
    Base class for all services.

    Enforces dependency injection of the database session,
    ensuring consistent database access patterns across services.

    Usage:
        class MyService(BaseService):
            async def my_method(self):
                result = await self.db.execute(...)
                return result
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize service with database session.

        Args:
            db: Async SQLAlchemy session for database operations
        """
        self.db = db
