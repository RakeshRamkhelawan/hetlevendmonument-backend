"""
Configuration Module - Foundation API Integration
ASCII-only, single server policy compliant
"""

import logging
import os
from typing import Any, Optional, cast
from src.core.config.production_config import ProductionConfigManager
from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord


logger = logging.getLogger(__name__)

# Deployment Mode Configuration (Hybride: SaaS of Single-Tenant)
DEPLOYMENT_MODE = os.getenv("DEPLOYMENT_MODE", "saas").lower()
if DEPLOYMENT_MODE not in ["saas", "single_tenant"]:
    logger.warning(f"Invalid DEPLOYMENT_MODE '{DEPLOYMENT_MODE}', defaulting to 'saas'")
    DEPLOYMENT_MODE = "saas"


# Import configuration manager


class Config:
    """Simple configuration wrapper for foundation API"""

    def __init__(self) -> None:
        self.production_config: Any | None = None  # TODO(TYPE): replace Any with concrete type
        self._config_data: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self._load_environment_variables()

    def _load_environment_variables(self) -> None:
        """Load basic environment variables"""
        # Validate critical URLs are set (fail-fast in production)
        environment = os.getenv("ENVIRONMENT", "development")
        redis_url = os.getenv("REDIS_URL")
        api_base_url = os.getenv("API_BASE_URL")

        if environment == "production":
            if not redis_url:
                raise ValueError("REDIS_URL environment variable required in production")
            if not api_base_url:
                raise ValueError("API_BASE_URL environment variable required in production")
            if "localhost" in (redis_url or ""):
                raise ValueError("REDIS_URL cannot contain localhost in production")
            if "localhost" in (api_base_url or ""):
                raise ValueError("API_BASE_URL cannot contain localhost in production")

            # Additional service URL checks
            # OP-112: only enforced when Serena MCP is actually enabled -- this check used to
            # run unconditionally, so production boot failed on a service that is off by
            # default and, for most tenants, never running.
            if os.getenv("ENABLE_SERENA_MCP", "false").lower() == "true":
                serena_api_url = os.getenv("SERENA_API_URL", "http://localhost:8001")
                if "localhost" in serena_api_url:
                    raise ValueError("SERENA_API_URL cannot contain localhost in production")

            for var in ["OLLAMA_HOST"]:
                val = os.getenv(var, "")
                if val and "localhost" in val:
                    raise ValueError(f"{var} cannot contain localhost in production")

        self._config_data = {
            "DATABASE_URL": os.getenv("DATABASE_URL"),
            "REDIS_URL": redis_url or "redis://localhost:6379",  # Development fallback only
            "ENVIRONMENT": environment,
            "DEBUG": os.getenv("DEBUG", "false").lower() == "true",
            "API_HOST": os.getenv("API_HOST", "0.0.0.0"),  # nosec B104: Docker networking (Traefik secures)
            "API_PORT": int(os.getenv("API_PORT", "8000")),
            "API_BASE_URL": api_base_url or "http://backend:8000",  # Default for Docker network
            "SECRET_KEY": os.getenv("SECRET_KEY"),
            "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "local"),  # Default to local
            "LOCAL_LLM_URL": os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1"),
            "ENABLE_SERENA_MCP": os.getenv("ENABLE_SERENA_MCP", "false").lower() == "true",
            "SERENA_SERVICE_PATH": os.getenv("SERENA_SERVICE_PATH", "services/serena"),
            "DEPLOYMENT_MODE": DEPLOYMENT_MODE,
        }
        logger.debug("Loaded DATABASE_URL: %s", database_url_zonder_wachtwoord(self.get("DATABASE_URL")))

    def get(self, key: str, default: Any = None) -> Any:  # TODO(TYPE): replace with concrete type
        """Get configuration value"""
        return self._config_data.get(key, default)

    def get_database_url(self) -> str:
        """Get database URL"""
        return cast(str, self.get("DATABASE_URL"))

    def get_redis_url(self) -> str:
        """Get Redis URL"""
        return cast(str, self.get("REDIS_URL"))

    def is_development(self) -> bool:
        """Check if running in development"""
        return bool(self.get("ENVIRONMENT") == "development")

    def is_debug(self) -> bool:
        """Check if debug mode enabled"""
        return bool(self.get("DEBUG", False))

    def is_serena_mcp_enabled(self) -> bool:
        """Check if Serena MCP is enabled"""
        return bool(self.get("ENABLE_SERENA_MCP", False))

    def get_serena_service_path(self) -> str:
        """Get Serena service path"""
        return cast(str, self.get("SERENA_SERVICE_PATH", "services/serena"))

    def get_serena_api_url(self) -> str:
        """Get Serena API URL"""
        if self.production_config:
            url = self.production_config.tool_broker.serena_api_url
            if url is None:
                return "http://localhost:8001"
            return str(url)
        serena_url = os.getenv("SERENA_API_URL", "http://localhost:8001")
        # Warn if using localhost in production
        if self.get("ENVIRONMENT") == "production" and "localhost" in serena_url:
            import warnings

            warnings.warn("SERENA_API_URL contains localhost in production")
        return serena_url

    def get_serena_api_key(self) -> str | None:
        """Get Serena API key"""
        if self.production_config:
            return cast(str | None, self.production_config.tool_broker.serena_api_key)
        return os.getenv("SERENA_API_KEY")

    def get_seq_thinking_api_url(self) -> str:
        """Get Sequential Thinking API URL"""
        if self.production_config:
            url = self.production_config.tool_broker.seq_thinking_api_url
            if url is None:
                return "http://localhost:8002"
            return str(url)
        seq_url = os.getenv("SEQ_THINKING_API_URL", "http://localhost:8002")
        # Warn if using localhost in production
        if self.get("ENVIRONMENT") == "production" and "localhost" in seq_url:
            import warnings

            warnings.warn("SEQ_THINKING_API_URL contains localhost in production")
        return seq_url

    def get_seq_thinking_api_key(self) -> str | None:
        """Get Sequential Thinking API key"""
        if self.production_config:
            return cast(str | None, self.production_config.tool_broker.seq_thinking_api_key)
        return os.getenv("SEQ_THINKING_API_KEY")

    def get_tool_broker_service_timeout(self) -> int:
        """Get Tool Broker service timeout"""
        if self.production_config:
            return cast(int, self.production_config.tool_broker.tool_broker_service_timeout)
        return int(os.getenv("TOOL_BROKER_SERVICE_TIMEOUT", "30"))

    def get_jwt_algorithm(self) -> str:
        """Get JWT algorithm"""
        if self.production_config and self.production_config.security:
            return cast(str, self.production_config.security.jwt_algorithm)
        return os.getenv("JWT_ALGORITHM", "HS256")

    def get_access_token_expire_minutes(self) -> int:
        """Get access token expire minutes"""
        if self.production_config and self.production_config.security:
            return cast(int, self.production_config.security.jwt_expiry_hours * 60)
        return int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    def initialize_production_config(self) -> bool:
        """Initialize production configuration manager"""
        try:
            self.production_config = ProductionConfigManager()
            # Check if production config manager has load_configuration method
            if hasattr(self.production_config, "_load_configuration"):
                self.production_config._load_configuration()
                logger.info("Production configuration initialized successfully")
                return True
            else:
                logger.warning(
                    "Production configuration using basic config (load_configuration method not available)"
                )
                return True
        except Exception as e:
            logger.error(
                "Production configuration error: %s: %s", type(e).__name__, e, exc_info=True
            )
            return False


# Global configuration instance
config = Config()

# Alias for backward compatibility with code expecting 'settings'
settings = config


# Configuration initialization function
def initialize_config() -> bool:
    """Initialize configuration system"""
    try:
        # Try to initialize production config
        config.initialize_production_config()
        logger.info("Configuration system initialized")
        return True
    except Exception as e:
        logger.error(
            "Configuration initialization error: %s: %s", type(e).__name__, e, exc_info=True
        )
        return False


# Convenience functions
def get_database_url() -> str:
    return config.get_database_url()


def get_redis_url() -> str:
    return config.get_redis_url()


def is_development() -> bool:
    return config.is_development()


def get_api_base_url() -> str:
    """Get API base URL from environment"""
    api_url = config.get("API_BASE_URL")
    if api_url is None:
        return "http://backend:8000"  # Default for Docker network
    return str(api_url)


def is_serena_mcp_enabled() -> bool:
    return config.is_serena_mcp_enabled()


def get_serena_service_path() -> str:
    return config.get_serena_service_path()


def get_serena_api_url() -> str:
    return config.get_serena_api_url()


def get_serena_api_key() -> str | None:
    return config.get_serena_api_key()


def get_seq_thinking_api_url() -> str:
    return config.get_seq_thinking_api_url()


def get_seq_thinking_api_key() -> str | None:
    return config.get_seq_thinking_api_key()


def get_tool_broker_service_timeout() -> int:
    return config.get_tool_broker_service_timeout()


def get_jwt_algorithm() -> str:
    return config.get_jwt_algorithm()


def get_access_token_expire_minutes() -> int:
    return config.get_access_token_expire_minutes()


# Compatibility re-export for legacy tests
try:
    from dotenv import load_dotenv  # noqa: F401
except Exception:
    load_dotenv = None  # type: ignore[assignment]
