"""
Secure Secrets Loader

Loads secrets from Docker Secrets (files) or environment variables.
Docker Secrets are the preferred method in production.

Usage:
    from src.core.config.secrets_loader import get_secret

    jwt_secret = get_secret("JWT_SECRET_KEY")
    # Tries file at /run/secrets/jwt_secret first
    # Falls back to JWT_SECRET_KEY env var
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Set

from loguru import logger


def get_secret(secret_name: str, default: str | None = None) -> str:
    """
    Get a secret value from Docker Secrets or environment variable.

    Priority:
    1. /run/secrets/{secret_name.lower()} file
    2. {SECRET_NAME}_FILE environment variable (path to file)
    3. {SECRET_NAME} environment variable (direct value)
    4. Default value (if provided)

    Args:
        secret_name: Name of the secret (e.g., "JWT_SECRET_KEY")
        default: Default value if not found

    Returns:
        Secret value

    Raises:
        ValueError: If secret not found and no default provided
    """
    # Normalize secret name
    secret_file_name = secret_name.lower().replace("_", "_")

    # 1. Try Docker Secrets default location
    docker_secret_path = Path(f"/run/secrets/{secret_file_name}")
    if docker_secret_path.exists():
        try:
            value = docker_secret_path.read_text().strip()
            if value:
                logger.debug(f"Loaded secret {secret_name} from Docker Secrets")
                return value
        except Exception as e:
            logger.warning(f"Failed to read Docker Secret {secret_name}: {e}")

    # 2. Try _FILE environment variable (custom path)
    file_env_var = f"{secret_name}_FILE"
    file_path = os.getenv(file_env_var)
    if file_path:
        try:
            value = Path(file_path).read_text().strip()
            if value:
                logger.debug(f"Loaded secret {secret_name} from {file_path}")
                return value
        except Exception as e:
            logger.warning(f"Failed to read secret file at {file_path}: {e}")

    # 3. Try direct environment variable
    env_value = os.getenv(secret_name)
    if env_value:
        logger.debug(f"Loaded secret {secret_name} from environment variable")
        # Security: Warn if using env var in production
        if os.getenv("ENVIRONMENT") == "production":
            logger.warning(
                f"Secret {secret_name} loaded from environment variable. "
                "Consider using Docker Secrets for better security."
            )
        return env_value

    # 4. Use default if provided
    if default is not None:
        logger.debug(f"Using default value for {secret_name}")
        return default

    # 5. Fail if no value found
    raise ValueError(
        f"Secret {secret_name} not found. "
        f"Set Docker Secret at /run/secrets/{secret_file_name}, "
        f"set {secret_name}_FILE to a file path, "
        f"or set {secret_name} environment variable."
    )


def get_secret_or_none(secret_name: str) -> str | None:
    """Get secret or return None if not found."""
    try:
        return get_secret(secret_name)
    except ValueError:
        return None


def load_all_secrets() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Load all required secrets for the application.

    Returns: Dict[str, Any]ionary of secret names to values  # TODO(TYPE): replace Any with concrete type
    """
    secrets: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    required_secrets = [
        "JWT_SECRET_KEY",
        "DATABASE_URL",
        "REDIS_URL",
    ]

    optional_secrets = [
        "GOOGLE_API_KEY",
        "SMTP_PASSWORD",
        "STRIPE_API_KEY",
        "SENTRY_DSN",
    ]

    # Load required secrets
    for secret_name in required_secrets:
        try:
            secrets[secret_name] = get_secret(secret_name)
        except ValueError as e:
            logger.error(f"Required secret not found: {e}")
            raise

    # Load optional secrets
    for secret_name in optional_secrets:
        value = get_secret_or_none(secret_name)
        if value:
            secrets[secret_name] = value

    return secrets


# Convenience functions for common secrets
def get_jwt_secret() -> str:
    """Get JWT signing secret."""
    return get_secret("JWT_SECRET_KEY")


def get_database_password() -> str:
    """Get database password."""
    return get_secret("DATABASE_PASSWORD")


def get_redis_password() -> str | None:
    """Get Redis password (optional)."""
    return get_secret_or_none("REDIS_PASSWORD")


def get_google_api_key() -> str | None:
    """Get Google API key (optional)."""
    return get_secret_or_none("GOOGLE_API_KEY")
