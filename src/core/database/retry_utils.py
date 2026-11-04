"""
Database connection retry utilities with exponential backoff
For P0-2: MOCK-002 - Hardcoded Database Credentials
"""

import logging
import time
from functools import wraps
from typing import Any, TypeVar
from collections.abc import Callable

from sqlalchemy.engine import Engine

from sqlalchemy.exc import DBAPIError, OperationalError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_database_operation(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying database operations with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exponential_base: Base for exponential backoff calculation

    Usage:
        @retry_database_operation(max_retries=3)
        def my_database_function():
            # Your database code here
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except (OperationalError, DBAPIError) as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"Database operation '{func.__name__}' failed after {max_retries} retries: {e}"
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (exponential_base**attempt), max_delay)

                    logger.warning(
                        f"Database operation '{func.__name__}' failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay:.2f}s: {e}"
                    )

                    time.sleep(delay)

            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError(f"Database operation '{func.__name__}' failed")

        return wrapper

    return decorator


def create_db_connection_with_retry(database_url: str, max_retries: int = 3) -> Engine:
    """
    Create database connection with retry logic.

    Args:
        database_url: PostgreSQL connection string
        max_retries: Maximum number of connection attempts

    Returns:
        SQLAlchemy Engine instance

    Raises:
        OperationalError: If connection fails after all retries
    """
    from sqlalchemy import create_engine
    from sqlalchemy.pool import QueuePool

    @retry_database_operation(max_retries=max_retries)
    def _create_engine() -> Engine:
        engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=20,
            max_overflow=30,
            pool_timeout=30,
            pool_recycle=3600,
            pool_pre_ping=True,  # Validate connections before use
            connect_args={},
        )

        # Test connection
        with engine.connect() as conn:
            from sqlalchemy import text as sa_text

            conn.execute(sa_text("SELECT 1"))

        logger.info("Database connection established successfully")
        return engine

    return _create_engine()


# Example usage
if __name__ == "__main__":
    import os

    # Example: Retry a database query
    @retry_database_operation(max_retries=3)
    def test_query() -> object:
        from sqlalchemy import text

        engine = create_db_connection_with_retry(os.getenv("DATABASE_URL", ""))
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            return result.fetchone()

    try:
        version = test_query()
        print(f"PostgreSQL version: {version}")
    except Exception as e:
        print(f"Failed to connect: {e}")
