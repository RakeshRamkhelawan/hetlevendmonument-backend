"""
SD-7.1: Connection Timeout Configuration
Configures database connection timeouts and retry logic.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class TimeoutConfig:
    """Database timeout configuration."""

    # Connection timeout (seconds to wait for connection)
    connect_timeout: int = 10

    # Command timeout (seconds to wait for query)
    command_timeout: int = 30

    # Statement timeout (max time for a single statement)
    statement_timeout: int = 60

    # Lock timeout (max time to wait for locks)
    lock_timeout: int = 10

    # Idle in transaction timeout
    idle_in_transaction_timeout: int = 60

    # Pool timeout (seconds to wait for pool connection)
    pool_timeout: int = 30

    @classmethod
    def from_env(cls) -> "TimeoutConfig":
        """Create config from environment variables."""
        return cls(
            connect_timeout=int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
            command_timeout=int(os.getenv("DB_COMMAND_TIMEOUT", "30")),
            statement_timeout=int(os.getenv("DB_STATEMENT_TIMEOUT", "60")),
            lock_timeout=int(os.getenv("DB_LOCK_TIMEOUT", "10")),
            idle_in_transaction_timeout=int(os.getenv("DB_IDLE_TIMEOUT", "60")),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
        )

    def to_connection_args(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to SQLAlchemy connection arguments."""
        return {
            "connect_timeout": self.connect_timeout,
            "command_timeout": self.command_timeout,
            "options": f"-c statement_timeout={self.statement_timeout * 1000}",
        }

    def to_postgres_options(self) -> str:
        """Convert to PostgreSQL connection options string."""
        options = [
            f"statement_timeout={self.statement_timeout * 1000}",
            f"lock_timeout={self.lock_timeout * 1000}",
            f"idle_in_transaction_session_timeout={self.idle_in_transaction_timeout * 1000}",
        ]
        return " ".join(f"-c {opt}" for opt in options)


def get_timeout_config() -> TimeoutConfig:
    """Get timeout configuration from environment."""
    config = TimeoutConfig.from_env()

    logger.info(
        f"Database timeouts configured: "
        f"connect={config.connect_timeout}s, "
        f"command={config.command_timeout}s, "
        f"statement={config.statement_timeout}s"
    )

    return config


def apply_timeout_to_url(database_url: str, config: TimeoutConfig | None = None) -> str:
    """
    Apply timeout parameters to a database URL.

    Args:
        database_url: PostgreSQL connection URL
        config: Timeout configuration

    Returns:
        Modified URL with timeout parameters
    """
    config = config or TimeoutConfig.from_env()

    # Add query parameters
    separator = "&" if "?" in database_url else "?"

    params = [
        f"connect_timeout={config.connect_timeout}",
        f"options={config.to_postgres_options()}",
    ]

    return database_url + separator + "&".join(params)
