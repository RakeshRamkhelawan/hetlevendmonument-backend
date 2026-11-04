"""
SD-5.2: Database SSL Mode Configuration
Configures SSL/TLS for database connections.
"""

import os
import ssl
from enum import Enum
from typing import Any, Optional


class SSLMode(str, Enum):
    """PostgreSQL SSL modes."""

    DISABLE = "disable"
    ALLOW = "allow"
    PREFER = "prefer"
    REQUIRE = "require"
    VERIFY_CA = "verify-ca"
    VERIFY_FULL = "verify-full"


def get_ssl_context(
    ssl_mode: SSLMode = SSLMode.REQUIRE,
    ca_cert_path: str | None = None,
    client_cert_path: str | None = None,
    client_key_path: str | None = None,
) -> ssl.SSLContext | None:
    """
    Create SSL context for database connections.

    Args:
        ssl_mode: PostgreSQL SSL mode
        ca_cert_path: Path to CA certificate
        client_cert_path: Path to client certificate
        client_key_path: Path to client private key

    Returns:
        SSLContext or None if SSL is disabled
    """
    if ssl_mode == SSLMode.DISABLE:
        return None

    context = ssl.create_default_context()

    if ssl_mode in (SSLMode.VERIFY_CA, SSLMode.VERIFY_FULL):
        context.check_hostname = ssl_mode == SSLMode.VERIFY_FULL
        context.verify_mode = ssl.CERT_REQUIRED

        if ca_cert_path:
            context.load_verify_locations(ca_cert_path)
    else:
        # For require/prefer/allow - don't verify cert
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    # Load client certificate if provided
    if client_cert_path and client_key_path:
        context.load_cert_chain(client_cert_path, client_key_path)

    return context


def get_database_ssl_args() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get SSL arguments for SQLAlchemy from environment.

    Environment variables:
        DB_SSL_MODE: PostgreSQL SSL mode
        DB_SSL_CA_CERT: Path to CA certificate
        DB_SSL_CLIENT_CERT: Path to client certificate
        DB_SSL_CLIENT_KEY: Path to client private key

    Returns: Dict[str, Any] with connect_args for SQLAlchemy  # TODO(TYPE): replace Any with concrete type
    """
    ssl_mode_str = os.getenv("DB_SSL_MODE", "prefer")

    try:
        ssl_mode = SSLMode(ssl_mode_str)
    except ValueError:
        ssl_mode = SSLMode.PREFER

    if ssl_mode == SSLMode.DISABLE:
        return {"ssl": None}

    ssl_context = get_ssl_context(
        ssl_mode=ssl_mode,
        ca_cert_path=os.getenv("DB_SSL_CA_CERT"),
        client_cert_path=os.getenv("DB_SSL_CLIENT_CERT"),
        client_key_path=os.getenv("DB_SSL_CLIENT_KEY"),
    )

    return {"ssl": ssl_context}


def get_asyncpg_ssl_args() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get SSL arguments for asyncpg connections.

    Returns: Dict[str, Any] with SSL configuration for asyncpg  # TODO(TYPE): replace Any with concrete type
    """
    ssl_mode_str = os.getenv("DB_SSL_MODE", "prefer")

    if ssl_mode_str == "disable":
        return {"ssl": False}

    ssl_context = get_ssl_context(
        ssl_mode=(
            SSLMode(ssl_mode_str)
            if ssl_mode_str in SSLMode.__members__.values()
            else SSLMode.PREFER
        ),
        ca_cert_path=os.getenv("DB_SSL_CA_CERT"),
        client_cert_path=os.getenv("DB_SSL_CLIENT_CERT"),
        client_key_path=os.getenv("DB_SSL_CLIENT_KEY"),
    )

    return {"ssl": ssl_context} if ssl_context else {"ssl": True}
