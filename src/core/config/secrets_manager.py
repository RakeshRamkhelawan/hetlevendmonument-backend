"""
Secrets Management Integration for Kubernetes and Production
Handles secure retrieval and validation of secrets from various sources
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SecretsManager:
    """Production secrets management with Kubernetes integration"""

    def __init__(self) -> None:
        self.secrets_cache: dict[str, str] = {}
        self.kubernetes_secrets_path = Path("/var/run/secrets")
        self.is_kubernetes = self._detect_kubernetes_environment()

    def _detect_kubernetes_environment(self) -> bool:
        """Detect if running in Kubernetes environment"""
        indicators = [
            os.path.exists("/var/run/secrets/kubernetes.io"),
            os.environ.get("KUBERNETES_SERVICE_HOST"),
            os.environ.get("POD_NAME"),
            os.environ.get("KUBERNETES_NAMESPACE"),
        ]
        return any(indicators)

    def get_secret(self, key: str, default: str | None = None) -> str | None:
        """
        Retrieve secret with fallback chain:
        1. Kubernetes mounted secrets
        2. Environment variables
        3. Docker secrets
        4. Default value
        """
        # Check cache first
        if key in self.secrets_cache:
            return self.secrets_cache[key]

        secret_value = None

        # 1. Try Kubernetes mounted secrets
        if self.is_kubernetes:
            secret_value = self._get_kubernetes_secret(key)

        # 2. Try environment variables
        if not secret_value:
            secret_value = os.getenv(key)

        # 3. Try Docker secrets
        if not secret_value:
            secret_value = self._get_docker_secret(key)

        # 4. Use default
        if not secret_value:
            secret_value = default

        # Cache successful retrievals
        if secret_value:
            self.secrets_cache[key] = secret_value
            logger.debug(f"Secret '{key}' retrieved successfully")
        else:
            logger.warning(f"Secret '{key}' not found in any source")

        return secret_value

    def _get_kubernetes_secret(self, key: str) -> str | None:
        """Retrieve secret from Kubernetes mounted volume"""
        try:
            # Standard Kubernetes secret mount path
            secret_file = self.kubernetes_secrets_path / "sanskriti-setu-secrets" / key.lower()

            if secret_file.exists():
                content = secret_file.read_text().strip()
                logger.debug(f"Retrieved Kubernetes secret: {key}")
                return content

            # Try alternative paths
            alternative_paths = [
                self.kubernetes_secrets_path / key.lower(),
                self.kubernetes_secrets_path / key.upper(),
                Path(f"/etc/secrets/{key.lower()}"),
                Path(f"/etc/secrets/{key.upper()}"),
            ]

            for path in alternative_paths:
                if path.exists():
                    content = path.read_text().strip()
                    logger.debug(f"Retrieved Kubernetes secret from {path}: {key}")
                    return content

        except Exception as e:
            logger.warning(f"Failed to read Kubernetes secret {key}: {e}")

        return None

    def _get_docker_secret(self, key: str) -> str | None:
        """Retrieve secret from Docker secrets"""
        try:
            secret_file = Path(f"/run/secrets/{key.lower()}")
            if secret_file.exists():
                content = secret_file.read_text().strip()
                logger.debug(f"Retrieved Docker secret: {key}")
                return content
        except Exception as e:
            logger.warning(f"Failed to read Docker secret {key}: {e}")

        return None

    def get_database_url(self) -> str:
        """Construct database URL from individual secrets"""
        # Try to get complete DATABASE_URL first
        db_url = self.get_secret("DATABASE_URL")
        if db_url and not db_url.startswith("OVERRIDE"):
            return db_url

        # Construct from individual components
        host = self.get_secret("DATABASE_HOST", "postgres-service.sanskriti-setu.svc.cluster.local")
        port = self.get_secret("DATABASE_PORT", "5432")
        user = self.get_secret("POSTGRES_USER", "sanskriti_user")
        password = self.get_secret("POSTGRES_PASSWORD")
        database = self.get_secret("DATABASE_NAME", "sanskriti_setu_prod")

        if not password:
            raise ValueError("Database password not found in secrets")

        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"

    def get_redis_url(self) -> str:
        """Construct Redis URL from secrets"""
        # Try complete REDIS_URL first
        redis_url = self.get_secret("REDIS_URL")
        if redis_url and not redis_url.startswith("OVERRIDE"):
            return redis_url

        # Construct from components
        host = self.get_secret("REDIS_HOST", "redis-service.sanskriti-setu.svc.cluster.local")
        port = self.get_secret("REDIS_PORT", "6379")
        password = self.get_secret("REDIS_PASSWORD")

        if password:
            return f"redis://:{password}@{host}:{port}"
        else:
            return f"redis://{host}:{port}"

    def validate_required_secrets(self, environment: str) -> dict[str, bool]:
        """Validate that all required secrets are available"""
        required_secrets = {
            "JWT_SECRET_KEY": False,
            "GOOGLE_API_KEY": False,
        }

        if environment == "production":
            production_secrets = {
                "DATABASE_URL": False,
                "REDIS_URL": False,
                "SENTRY_DSN": False,
            }
            required_secrets.update(production_secrets)

        # Check each required secret
        for secret_key in required_secrets:
            value = self.get_secret(secret_key)
            required_secrets[secret_key] = bool(
                value and not value.startswith("OVERRIDE") and len(value.strip()) > 0
            )

        return required_secrets

    def get_secrets_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive secrets status for monitoring"""
        return {
            "kubernetes_environment": self.is_kubernetes,
            "secrets_path_exists": self.kubernetes_secrets_path.exists(),
            "cached_secrets_count": len(self.secrets_cache),
            "environment_variables_count": len(
                [k for k in os.environ.keys() if "SECRET" in k.upper() or "PASSWORD" in k.upper()]
            ),
            "docker_secrets_available": Path("/run/secrets").exists(),
        }

    def clear_cache(self) -> None:
        """Clear secrets cache (for testing/rotation)"""
        self.secrets_cache.clear()
        logger.info("Secrets cache cleared")


# Global secrets manager instance
secrets_manager = SecretsManager()
