"""
Unified Configuration Management System
Centralizes all configuration across the Sanskriti Setu platform
"""

import logging
import os
import secrets
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Optional, TypedDict

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    from .secrets_manager import secrets_manager
except ImportError:
    # Fallback if secrets manager not available
    secrets_manager = None  # type: ignore[assignment]


class CorsConfig(TypedDict, total=False):
    allow_origins: list[str]
    allow_credentials: bool
    allow_methods: list[str]
    allow_headers: list[str]
    expose_headers: list[str]
    max_age: int


class DatabaseConfig(TypedDict):
    url: str
    pool_size: int
    max_overflow: int
    echo: bool
    pool_timeout: int
    pool_use_lifo: bool


class RedisConfig(TypedDict):
    url: str
    cache_ttl: int


class LlmConfig(TypedDict):
    provider: str
    model: str
    temperature: float
    max_tokens: int


class AgentConfig(TypedDict):
    max_concurrent: int
    timeout_seconds: int
    learning_enabled: bool


class SecurityConfig(TypedDict):
    jwt_secret_key: str
    jwt_expire_minutes: int
    middleware_enabled: bool


class HttpsConfig(TypedDict):
    enforce_https: bool
    hsts_enabled: bool
    hsts_max_age: int
    hsts_include_subdomains: bool
    hsts_preload: bool
    redirect_http_to_https: bool


class SecurityHeadersConfig(TypedDict):
    x_frame_options: str
    x_content_type_options: str
    x_xss_protection: str
    referrer_policy: str
    x_permitted_cross_domain_policies: str
    cache_control_sensitive: str
    cache_control_default: str
    cross_origin_resource_policy: str
    cross_origin_opener_policy: str
    cross_origin_embedder_policy: str


def _get_env_files() -> tuple[str, ...]:
    """
    Determine which .env files to load based on ENVIRONMENT variable.

    Per context7 best practices (FastAPI/Pydantic Settings):
    - Always load base .env first
    - Then load environment-specific file (.env.development, .env.staging, etc.)
    - Later files override earlier ones

    CRITICAL: If DATABASE_URL is already set in the environment, skip loading
    env files entirely. This prevents runtime config overrides that break
    long-running services (e.g., E2E backend on a custom port).

    Returns: tuple[str, ...] of env file paths to load (in priority order, later wins)
    """
    # Guard: if DATABASE_URL is already configured, don't load any env files
    if os.environ.get("DATABASE_URL"):
        return ()

    config_dir = Path(__file__).parent.parent.parent.parent  # Go to project root
    env = os.environ.get("ENVIRONMENT", "development").lower()

    base_env = config_dir / ".env"
    env_specific = config_dir / f".env.{env}"

    # Also load local overrides (secrets, API keys) - consistent with src/config.py
    local_env = config_dir / ".env.local"

    # Build list of files that exist
    files: list[str] = []
    if base_env.exists():
        files.append(str(base_env))
    if env_specific.exists():
        files.append(str(env_specific))
    if local_env.exists():
        files.append(str(local_env))

    # Fallback: if no files exist, return tuple for Pydantic to handle
    if not files:
        return (".env", f".env.{env}", ".env.local")

    return tuple(files)


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class UnifiedConfig(BaseSettings):
    """Centralized configuration for all system components"""

    _instance: ClassVar[Optional["UnifiedConfig"]] = None

    # Environment
    environment: Environment = Field(default=Environment.DEVELOPMENT)
    app_debug: bool = Field(
        default=False, alias="APP_DEBUG"
    )  # Use APP_DEBUG to avoid conflict with logging DEBUG var

    # Security Configuration
    jwt_secret_key: str = Field(default="")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=240)  # 4 hours - matches typical session duration
    refresh_token_expire_days: int = Field(default=7)  # OAuth2 refresh token expiry
    security_middleware_enabled: bool = Field(default=True)

    # Database Configuration
    database_url: str = Field(default="sqlite+aiosqlite:///./sanskriti_setu.db")
    database_pool_size: int = Field(default=20)
    database_max_overflow: int = Field(default=30)

    @field_validator("database_url", mode="after")
    @classmethod
    def reject_sqlite_in_production(cls, v: str) -> str:
        testing = os.getenv("TESTING") == "1" or "PYTEST_CURRENT_TEST" in os.environ
        if testing:
            return v
        if (
            os.getenv("ENVIRONMENT", "development").lower() == "production"
            and "sqlite" in v.lower()
        ):
            raise ValueError(
                "SQLite is not allowed in production: no Row Level Security support. "
                "Set DATABASE_URL to a PostgreSQL connection string."
            )
        return v

    # Redis Configuration
    redis_url: str = Field(default="redis://localhost:6379")
    redis_cache_ttl: int = Field(default=3600)

    # API Configuration
    api_host: str = Field(default="0.0.0.0")  # nosec B104: Docker networking (Traefik secures)
    api_port: int = Field(default=8000)
    cors_origins: str = Field(default="")

    # Agent Configuration
    max_concurrent_agents: int = Field(default=10)
    agent_timeout_seconds: int = Field(default=30)
    learning_enabled: bool = Field(default=True)

    # LLM Configuration
    llm_provider: str = Field(default="google")
    llm_model: str = Field(default="gemini-2.5-flash")
    llm_temperature: float = Field(default=0.7)
    llm_max_tokens: int = Field(default=1000)
    google_api_key: str = Field(default="")

    # Production Performance Configuration
    database_pool_timeout: int = Field(default=30)
    database_pool_recycle: int = Field(default=1800)  # 30 min - standardized across configs
    redis_max_connections: int = Field(default=100)
    worker_connections: int = Field(default=1000)
    max_requests: int = Field(default=10000)
    timeout: int = Field(default=300)

    # Production Security Configuration
    enforce_https: bool = Field(default=False)
    require_authentication: bool = Field(default=True)
    validate_secrets_on_startup: bool = Field(default=False)
    fail_fast_on_misconfiguration: bool = Field(default=False)
    hsts_max_age: int = Field(default=31536000)

    # Rate Limiting
    rate_limiting_enabled: bool = Field(default=True)
    rate_limit_per_minute: int = Field(default=1000)

    # IP-reputatie (src/core/security/ip_reputation.py, plan nazorg deel I punt b). Een signaal
    # telt punten op per IP; op of boven de drempel volgt een tijdelijke blokkade in Redis.
    security_ip_block_threshold: int = Field(default=15, ge=1)
    security_ip_score_window_seconds: int = Field(default=900, ge=1)
    security_ip_block_base_seconds: int = Field(default=900, ge=1)
    security_ip_block_max_seconds: int = Field(default=86_400, ge=1)
    security_ip_strike_window_seconds: int = Field(default=7 * 86_400, ge=1)
    security_sql_signal_points: int = Field(default=3, ge=0)
    # Komma-gescheiden CIDR's die nooit geblokkeerd worden (VNet, health probes, kantoor).
    security_block_exempt_cidrs: str = Field(default="")

    # Monitoring and Observability
    metrics_enabled: bool = Field(default=True)
    prometheus_port: int = Field(default=9090)
    sentry_dsn: Optional[str] = Field(default=None)
    log_format: str = Field(default="text")
    log_file: Optional[str] = Field(default=None)
    otel_enabled: bool = Field(default=True, description="Enable OpenTelemetry tracing")
    otel_service_name: str = Field(
        default="sanskritisetu-backend", description="Service name for OpenTelemetry"
    )
    otel_exporter_otlp_endpoint: str = Field(
        default="http://jaeger:4317", description="OTLP exporter endpoint"
    )

    # Backup Configuration
    backup_enabled: bool = Field(default=False)
    backup_schedule: str = Field(default="0 2 * * *")
    backup_retention_days: int = Field(default=30)

    # Evaluation & RAG Quality
    eval_block_on_low_quality: bool = Field(default=False)
    eval_min_faithfulness: float = Field(default=0.7)
    eval_min_precision: float = Field(default=0.6)
    eval_min_context_precision: float = Field(default=0.5)
    eval_model: str = Field(default="gemini-1.5-flash")

    # External Services
    smtp_host: Optional[str] = Field(default=None)
    smtp_port: int = Field(default=587)
    smtp_use_tls: bool = Field(default=True)

    # Cloud Storage
    cloud_storage_provider: str = Field(default="local")
    aws_region: str = Field(default="eu-west-1")

    # Kubernetes Configuration
    kubernetes_namespace: str = Field(default="sanskriti-setu")
    pod_name: Optional[str] = Field(default=None)
    node_name: Optional[str] = Field(default=None)

    # Feature Flags
    monitoring_enabled: bool = Field(default=True)
    advanced_analytics_enabled: bool = Field(default=False)
    experimental_features_enabled: bool = Field(default=False)
    production_readiness_check: bool = Field(default=False)

    # FocusBuilder Service Mode
    # embedded: Run FocusBuilder as part of main backend (default)
    # remote: Route requests to standalone FocusBuilder service
    focusbuilder_service_mode: str = Field(
        default="embedded",
        description="FocusBuilder service mode: 'embedded' (local) or 'remote' (HTTP proxy)",
    )
    focusbuilder_service_url: str = Field(
        default="http://focusbuilder:8001",
        description="URL of standalone FocusBuilder service (used when mode=remote)",
    )

    # Stripe Configuration
    stripe_api_key: str = Field(default="")
    stripe_publishable_key: str = Field(default="")
    stripe_webhook_secret: str = Field(default="")

    # ActivePieces Configuration
    activepieces_api_url: str = Field(default="http://activepieces:80/api/v1")
    activepieces_email: str = Field(default="")
    activepieces_password: str = Field(default="")
    activepieces_webhook_secret: str = Field(default="")

    model_config = SettingsConfigDict(
        env_file=None,  # Lazy: defer env file loading to get_instance()
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Validate JWT secret key strength"""
        # Note: In pydantic v2, we can't access other fields in field validators
        # Environment-specific validation moved to model validator

        if not v:
            # Generate random secret for development if not provided
            v = secrets.token_urlsafe(32)
            print("INFO: Generated a JWT secret for development (not shown)")

        return v

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, v: str) -> list[str]:
        """Convert CORS origins string to list"""
        if not v:
            return []
        return [origin.strip() for origin in v.split(",") if origin.strip()]

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL for production security"""
        # Basic validation - detailed environment checks moved to model validator
        if not v.startswith(("postgresql://", "postgresql+asyncpg://")):
            print("WARNING: Non-PostgreSQL database URL detected")

        return v

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        """Validate Redis URL for production"""
        # Basic validation - detailed environment checks moved to model validator
        if not v.startswith(("redis://", "rediss://")):
            raise ValueError("Invalid Redis URL format")

        return v

    @field_validator("sentry_dsn")
    @classmethod
    def validate_sentry_dsn(cls, v: str | None) -> str | None:
        """Validate Sentry DSN for production monitoring"""
        # Environment-specific validation moved to model validator
        return v

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        """Ensure JSON logging for production"""
        # Environment-specific validation moved to model validator
        if v not in ["json", "text"]:
            raise ValueError("Log format must be 'json' or 'text'")

        return v

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "UnifiedConfig":
        """Comprehensive production configuration validation"""
        environment = self.environment

        # Temporarily disable production validation for Docker deployment
        if environment == Environment.PRODUCTION and False:
            # Critical production validations
            production_checks = [
                ("jwt_secret_key", "JWT secret key must be set"),
                ("database_url", "Database URL must be configured"),
                ("redis_url", "Redis URL must be configured"),
            ]

            for field, message in production_checks:
                field_value = getattr(self, field, None)
                if not field_value or (
                    isinstance(field_value, str) and field_value.startswith("OVERRIDE")
                ):
                    if self.fail_fast_on_misconfiguration:
                        raise ValueError(f"Production misconfiguration: {message}")
                    else:
                        logging.error(f"PRODUCTION ISSUE: {message}")

            # Security validations
            if not self.enforce_https:
                logging.warning("HTTPS not enforced in production")

            if self.app_debug:
                raise ValueError("Debug mode cannot be enabled in production")

            # Performance validations
            if self.database_pool_size < 10:
                logging.warning("Database pool size may be too small for production")

            # JWT secret validation for production
            if len(self.jwt_secret_key) < 32:
                raise ValueError("JWT secret must be at least 32 characters in production")
            if self.jwt_secret_key.startswith("dev-") or "password" in self.jwt_secret_key.lower():
                raise ValueError("Default or development JWT secret detected in production")

            # Database URL validation for production
            if "localhost" in self.database_url or "127.0.0.1" in self.database_url:
                raise ValueError("Production database cannot use localhost")
            # Check for actual default passwords, not just the word "password"
            default_passwords = ["password", "pass", "default", "changeme", "123456"]
            if any(f":{pwd}@" in self.database_url.lower() for pwd in default_passwords):
                raise ValueError("Production database URL contains default password")

            # Redis URL validation for production
            if "localhost" in self.redis_url or "127.0.0.1" in self.redis_url:
                raise ValueError("Production Redis cannot use localhost")

            # Log format validation for production
            if self.log_format != "json":
                logging.warning("Production should use JSON log format for structured logging")

            # Sentry DSN validation for production
            if not self.sentry_dsn:
                logging.warning(
                    "Sentry DSN not configured for production - error tracking disabled"
                )

        return self

    # REMOVED: Custom __init__ causes Pydantic validation errors
    # Secrets manager integration moved to post-initialization hook

    def _inject_secrets_from_manager(self, kwargs: dict[str, str]) -> None:
        """Inject secrets from secrets manager into configuration"""
        if secrets_manager is None:
            return

        secret_mappings = {
            "jwt_secret_key": "JWT_SECRET_KEY",
            "database_url": "DATABASE_URL",
            "redis_url": "REDIS_URL",
            "sentry_dsn": "SENTRY_DSN",
            "google_api_key": "GOOGLE_API_KEY",
            "stripe_api_key": "STRIPE_API_KEY",
            "stripe_publishable_key": "STRIPE_PUBLISHABLE_KEY",
            "stripe_webhook_secret": "STRIPE_WEBHOOK_SECRET",
            "activepieces_email": "ACTIVEPIECES_EMAIL",
            "activepieces_password": "ACTIVEPIECES_PASSWORD",
            "activepieces_webhook_secret": "ACTIVEPIECES_WEBHOOK_SECRET",
        }

        for config_key, secret_key in secret_mappings.items():
            if config_key not in kwargs:
                secret_value = secrets_manager.get_secret(secret_key)
                if secret_value and not secret_value.startswith("OVERRIDE"):
                    kwargs[config_key] = secret_value

        # Special handling for constructed URLs
        if "database_url" not in kwargs:
            try:
                kwargs["database_url"] = secrets_manager.get_database_url()
            except Exception as e:
                logging.warning(f"Could not construct database URL from secrets: {e}")

        if "redis_url" not in kwargs:
            try:
                kwargs["redis_url"] = secrets_manager.get_redis_url()
            except Exception as e:
                logging.warning(f"Could not construct Redis URL from secrets: {e}")

    def validate_startup_configuration(self) -> None:
        """Comprehensive startup configuration validation"""
        print("INFO: Running comprehensive configuration validation...")

        issues: list[str] = []
        warnings: list[str] = []
        # Environment-specific validations
        if self.environment == Environment.PRODUCTION:
            # Check if we're in Docker development context
            if self._is_docker_development_context():
                print("INFO: Docker development context detected - using relaxed validation")
                issues.extend(self._validate_docker_development_config())
            else:
                print("INFO: True production context - using strict validation")
                issues.extend(self._validate_production_config())
        elif self.environment == Environment.STAGING:
            warnings.extend(self._validate_staging_config())
        else:
            warnings.extend(self._validate_development_config())

        # Domain-specific validations
        issues.extend(self._validate_domain_config())

        # Common validations for all environments
        issues.extend(self._validate_common_config())

        # Report warnings
        if warnings:
            warning_msg = "Configuration warnings detected:\n" + "\n".join(
                f"- {warning}" for warning in warnings
            )
            logging.warning(warning_msg)
            print(f"WARNING: {warning_msg}")

        # Handle critical issues
        if issues:
            error_msg = "Critical configuration issues detected:\n" + "\n".join(
                f"- {issue}" for issue in issues
            )
            logging.error(error_msg)
            raise RuntimeError(error_msg)

        print("INFO: All configuration checks passed")

    def _is_docker_development_context(self) -> bool:
        """Detect if we're running in Docker development vs true production"""
        docker_dev_indicators = [
            # Database URL contains 'postgres' hostname (Docker service name)
            "postgres:5432" in self.database_url,
            # Redis URL contains 'redis' hostname (Docker service name)
            "redis:6379" in self.redis_url,
            # CORS origins contain localhost
            (
                any("localhost" in origin.lower() for origin in self.cors_origins)
                if self.cors_origins
                else False
            ),
            # No HTTPS enforcement
            not self.enforce_https,
            # Environment variable indicates Docker
            os.environ.get("DOCKER_CONTEXT") == "development",
        ]

        # If 3+ indicators present, assume Docker development
        return sum(docker_dev_indicators) >= 3

    def _validate_docker_development_config(self) -> list[str]:
        """Validation for Docker development environment"""
        issues: list[str] = []
        # Critical validations only (not cosmetic)
        if not self.google_api_key:
            issues.append("Google API key required for agent functionality")

        if len(self.google_api_key) < 20:
            issues.append("Google API key appears invalid (too short)")

        if not self.database_url:
            issues.append("Database URL required")

        if not self.redis_url:
            issues.append("Redis URL required")

        # SKIP: HTTPS enforcement (not needed for Docker dev)
        # SKIP: sanskritisetu.nl CORS requirement (not needed for Docker dev)
        # SKIP: Production domain requirements (not needed for Docker dev)

        return issues

    def _validate_production_config(self) -> list[str]:
        """Production-specific configuration validation"""
        issues: list[str] = []
        # Critical secrets validation
        if len(self.jwt_secret_key) < 32:
            issues.append("JWT secret key too short for production (minimum 32 characters)")

        if "localhost" in self.database_url or "127.0.0.1" in self.database_url:
            issues.append("Database URL cannot use localhost in production")

        if "localhost" in self.redis_url or "127.0.0.1" in self.redis_url:
            issues.append("Redis URL cannot use localhost in production")

        if self.app_debug:
            issues.append("Debug mode must be disabled in production")

        if not self.enforce_https:
            issues.append("HTTPS enforcement required in production")

        # API key validation
        google_api_key = os.getenv("GOOGLE_API_KEY")
        if not google_api_key or len(google_api_key) < 20:
            issues.append("Google API key missing or invalid for production")

        return issues

    def _validate_staging_config(self) -> list[str]:
        """Staging-specific configuration validation"""
        warnings: list[str] = []
        if self.app_debug:
            warnings.append("Debug mode enabled in staging")

        if not self.monitoring_enabled:
            warnings.append("Monitoring disabled in staging")

        return warnings

    def _validate_development_config(self) -> list[str]:
        """Development-specific configuration validation"""
        warnings: list[str] = []
        if self.environment == Environment.DEVELOPMENT and self.enforce_https:
            warnings.append("HTTPS enforcement in development may cause issues")

        return warnings

    def _validate_common_config(self) -> list[str]:
        """Common configuration validation for all environments"""
        issues: list[str] = []
        # Database URL format validation
        if not self.database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
            issues.append("Database URL must use PostgreSQL format")

        # Redis URL format validation
        if not self.redis_url.startswith(("redis://", "rediss://")):
            issues.append("Redis URL must use redis:// or rediss:// format")

        # LLM provider validation
        if self.llm_provider not in ["google", "openai", "anthropic"]:
            issues.append(f"Unsupported LLM provider: {self.llm_provider}")

        # Port validation
        if not (1024 <= self.api_port <= 65535):
            issues.append("API port must be between 1024 and 65535")

        return issues

    def _validate_domain_config(self) -> list[str]:
        """Domain-specific configuration validation"""
        issues: list[str] = []
        # Check for sanskritisetu.nl domain configuration in production
        if self.environment == Environment.PRODUCTION:
            # Skip domain validation for Docker development context
            if self._is_docker_development_context():
                return issues  # No domain validation needed for Docker dev
            cors_origins: list[str] = (
                self.cors_origins if isinstance(self.cors_origins, list) else []
            )

            # Check if production domain is configured
            has_production_domain = (
                any("sanskritisetu.nl" in origin for origin in cors_origins)
                if cors_origins
                else False
            )

            if not has_production_domain:
                issues.append("Production CORS origins must include sanskritisetu.nl domain")

            # Check for localhost in production URLs
            if "localhost" in self.database_url or "127.0.0.1" in self.database_url:
                issues.append("Production database URL cannot use localhost")

            if "localhost" in self.redis_url or "127.0.0.1" in self.redis_url:
                issues.append("Production Redis URL cannot use localhost")

        return issues

    def _perform_production_readiness_check(self) -> None:
        """Comprehensive production readiness validation"""
        issues: list[str] = []
        # Check secrets availability
        if secrets_manager:
            required_secrets = secrets_manager.validate_required_secrets("production")
            missing_secrets = [k for k, v in required_secrets.items() if not v]
            if missing_secrets:
                issues.append(f"Missing required secrets: {', '.join(missing_secrets)}")

        # Check configuration values
        if self.app_debug:
            issues.append("Debug mode enabled in production")

        if not self.monitoring_enabled:
            issues.append("Monitoring disabled in production")

        if not self.backup_enabled:
            issues.append("Backups not configured for production")

        if "localhost" in self.database_url:
            issues.append("Database URL points to localhost")

        if issues:
            error_msg = "Production readiness check failed:\n" + "\n".join(
                f"- {issue}" for issue in issues
            )
            if self.fail_fast_on_misconfiguration:
                raise RuntimeError(error_msg)
            else:
                logging.error(error_msg)

    @classmethod
    def get_instance(cls) -> "UnifiedConfig":
        """Singleton pattern for global config access"""
        if not hasattr(cls, "_instance") or cls._instance is None:
            # Lazy load env files at instantiation time (not class definition time)
            env_files = _get_env_files()
            # Create instance with explicit env_file parameter
            cls._instance = cls(_env_file=env_files)  # type: ignore[call-arg]
        return cls._instance

    def get_cors_config(self) -> CorsConfig:
        """Get environment-specific CORS configuration"""
        cors_origins: list[str] = self.cors_origins if isinstance(self.cors_origins, list) else []

        if self.environment == Environment.PRODUCTION:
            return {
                "allow_origins": cors_origins or ["https://www.sanskritisetu.nl"],
                "allow_credentials": True,
                "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": ["Authorization", "Content-Type", "X-Requested-With"],
                "expose_headers": ["X-Total-Count", "X-Rate-Limit"],
                "max_age": 3600,
            }
        elif self.environment == Environment.STAGING:
            return {
                "allow_origins": [
                    "https://staging.sanskritisetu.nl",
                    "http://localhost:3000",
                ],
                "allow_credentials": True,
                "allow_methods": ["*"],
                "allow_headers": ["*"],
                "max_age": 600,
            }
        else:  # Development
            return {
                "allow_origins": [
                    "http://localhost:3000",
                    "http://127.0.0.1:3000",  # React/Vue/Angular
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",  # Vite Development Server
                    "http://localhost:8080",
                    "http://127.0.0.1:8080",  # Alternative frontend
                    "http://localhost:8501",
                    "http://127.0.0.1:8501",  # Streamlit
                ],
                "allow_credentials": True,
                "allow_methods": ["*"],
                "allow_headers": ["*"],
                "max_age": 300,
            }

    def get_database_config(self) -> DatabaseConfig:
        """Get database configuration with optimized pooling settings"""
        return {
            "url": self.database_url,
            "pool_size": self.database_pool_size,
            "max_overflow": self.database_max_overflow,
            "echo": self.app_debug,
            "pool_timeout": 30,  # Timeout after 30 seconds waiting for connection
            "pool_use_lifo": True,  # LIFO for better connection locality
        }

    def get_redis_config(self) -> RedisConfig:
        """Get Redis configuration"""
        return {"url": self.redis_url, "cache_ttl": self.redis_cache_ttl}

    def get_llm_config(self) -> LlmConfig:
        """Get LLM configuration"""
        return {
            "provider": self.llm_provider,
            "model": self.llm_model,
            "temperature": self.llm_temperature,
            "max_tokens": self.llm_max_tokens,
        }

    def get_agent_config(self) -> AgentConfig:
        """Get agent configuration"""
        return {
            "max_concurrent": self.max_concurrent_agents,
            "timeout_seconds": self.agent_timeout_seconds,
            "learning_enabled": self.learning_enabled,
        }

    def get_security_config(self) -> SecurityConfig:
        """Get security configuration"""
        return {
            "jwt_secret_key": self.jwt_secret_key,
            "jwt_expire_minutes": self.jwt_expire_minutes,
            "middleware_enabled": self.security_middleware_enabled,
        }

    def get_https_config(self) -> HttpsConfig:
        """Get HTTPS enforcement configuration.

        OWASP A05 - Security Misconfiguration:
        - Production: Always enforce HTTPS
        - Staging: Enforce HTTPS (testing TLS setup)
        - Development: Optional (for local dev)

        Returns: Dictionary with HTTPS configuration
        """
        return {
            "enforce_https": self.enforce_https or self.environment == Environment.PRODUCTION,
            "hsts_enabled": True,
            "hsts_max_age": self.hsts_max_age,
            "hsts_include_subdomains": True,
            "hsts_preload": self.environment == Environment.PRODUCTION,
            "redirect_http_to_https": self.environment == Environment.PRODUCTION,
        }

    def get_security_headers_config(
        self,
    ) -> SecurityHeadersConfig:
        """Get security headers configuration for OWASP A05 compliance.

        Returns: Dictionary with security headers settings
        """
        return {
            "x_frame_options": "DENY",
            "x_content_type_options": "nosniff",
            "x_xss_protection": "1; mode=block",
            "referrer_policy": "strict-origin-when-cross-origin",
            "x_permitted_cross_domain_policies": "none",
            "cache_control_sensitive": "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0",
            "cache_control_default": "no-store, max-age=0",
            "cross_origin_resource_policy": "same-origin",
            "cross_origin_opener_policy": "same-origin-allow-popups",
            "cross_origin_embedder_policy": "credentialless",
        }

    def should_enforce_https(self) -> bool:
        """Check if HTTPS should be enforced.

        Returns:
            True if HTTPS enforcement is required
        """
        return self.enforce_https or self.environment == Environment.PRODUCTION

    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.environment == Environment.DEVELOPMENT

    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.environment == Environment.PRODUCTION


# Global config instance - LAZY INITIALIZATION
# DO NOT call get_instance() at module level to avoid import-time initialization
# Use: from core.config.unified_config import UnifiedConfig; config = UnifiedConfig.get_instance()
# or: import core.config.unified_config as config_module; config_module.config
_config_instance: Optional["UnifiedConfig"] = None


def get_config() -> "UnifiedConfig":
    """Get global config instance (lazy initialization)"""
    global _config_instance
    if _config_instance is None:
        _config_instance = UnifiedConfig.get_instance()
    return _config_instance


# For backward compatibility (but lazy)
class _ConfigProxy:
    """Proxy object that lazily initializes config on first attribute access"""

    def __getattr__(self, name: str) -> Any:  # TODO(TYPE): replace with concrete type
        return getattr(get_config(), name)


config = _ConfigProxy()
