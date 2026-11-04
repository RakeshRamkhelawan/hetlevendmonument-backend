"""
Production Configuration Manager for Sanskriti Setu
Advanced configuration management with environment-specific settings
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

# Setup logging
logger = logging.getLogger(__name__)

_MIN_SECRET_KEY_LENGTH = 32
_INSECURE_SECRET_KEYS = frozenset(
    {
        "",
        "dev-secret-change-in-production",
        "changeme",
        "change-me",
        "secret",
        "your-secret-key",
        "supersecret",
        "password",
    }
)


@dataclass
class LLMProviderConfig:
    """LLM Provider Configuration"""

    name: str
    enabled: bool = True
    # `repr=False`: de sleutel hoort niet in een weergave of logregel van deze configuratie.
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
    model: str | None = None
    timeout: int = 30
    rate_limit: int = 100  # requests per minute
    priority: int = 1  # lower = higher priority
    fallback_to: str | None = None


@dataclass
class DatabaseConfig:
    """Database Configuration"""

    url: str
    # Formula: (pool_size + max_overflow) x workers x replicas < pg max_connections
    # With 1 worker x 1 replica (min-replicas=1): (5+10)x1x1 = 15 connections -- well within limits.
    # Increase pool_size if you add more replicas or Gunicorn workers.
    pool_size: int = 5
    max_overflow: int = 10
    # 5s: fail fast and surface the problem immediately (not 30s which hides overload)
    pool_timeout: int = 5
    # 1800s (30 min): recycle connections periodically to avoid stale TCP state.
    # Azure PostgreSQL closes idle connections after ~10 min; pool_pre_ping catches
    # those before use, but recycling reduces the chance of hitting a closed socket.
    pool_recycle: int = 1800
    # Validates connections before use -- prevents "SSL connection has been closed unexpectedly"
    pool_pre_ping: bool = True
    echo: bool = False


@dataclass
class CacheConfig:
    """Cache Configuration"""

    redis_url: str | None = None
    default_ttl: int = 3600  # 1 hour
    max_memory_cache: int = 100  # MB
    enable_redis: bool = True
    enable_memory: bool = True


@dataclass
class SecurityConfig:
    """Security Configuration"""

    secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    bcrypt_rounds: int = 12
    rate_limit_per_minute: int = 60
    enable_cors: bool = True
    # P0-6: Changed from wildcard ["*"] to empty list (must be configured explicitly)
    allowed_origins: list[str] = field(default_factory=list)


@dataclass
class MonitoringConfig:
    """Monitoring and Alerting Configuration"""

    memory_alert_threshold: float = 85.0
    memory_critical_threshold: float = 90.0
    monitoring_interval: float = 60.0  # seconds
    enable_performance_monitoring: bool = True
    log_level: str = "INFO"
    metrics_retention_days: int = 30


@dataclass
class ToolBrokerConfig:
    """Tool Broker Configuration"""

    serena_api_url: str | None = None  # Required via environment variable
    serena_api_key: str | None = None
    seq_thinking_api_url: str | None = None  # Required via environment variable
    seq_thinking_api_key: str | None = None
    tool_broker_service_timeout: int = 30


@dataclass
class FeatureFlags:
    """Feature flags for production deployment"""

    real_llm_integration: bool = False
    ethics_gate_enabled: bool = False
    response_caching: bool = False
    multi_llm_integration: bool = False
    docker_sandbox: bool = False
    advanced_analytics: bool = False
    ml_ethics_engine: bool = False
    real_database: bool = True
    production_logging: bool = True
    performance_optimization: bool = True


class ProductionConfigManager:
    """
    Production Configuration Manager
    Manages all configuration for production deployment
    """

    def __init__(self, config_path: str | None = None) -> None:
        self.config_path = Path(config_path or "production_config.yaml")
        self.environment = os.getenv("ENVIRONMENT", "development")

        # Initialize configurations
        self.llm_providers: dict[str, LLMProviderConfig] = {}
        self.database: DatabaseConfig | None = None
        self.cache: CacheConfig = CacheConfig()
        self.security: SecurityConfig | None = None
        self.monitoring: MonitoringConfig = MonitoringConfig()
        self.tool_broker: ToolBrokerConfig = ToolBrokerConfig()
        self.feature_flags: FeatureFlags = FeatureFlags()

        # Load configuration
        self._load_configuration()

        # P0-6: MOCK-006 - CORS wildcard validation
        if self.environment in ["staging", "production"]:
            allowed_origins = os.getenv("ALLOWED_ORIGINS", "")
            if "*" in allowed_origins:
                raise ValueError(
                    f"CORS wildcard ('*') is not allowed in {self.environment} environment. "
                    "Specify explicit allowed origins for security."
                )

        logger.info(f"Production Configuration Manager initialized for {self.environment}")

    def _load_configuration(self) -> None:
        """Load configuration from file and environment"""
        # Load from file if exists
        if self.config_path.exists():
            self._load_from_file()

        # Override with environment variables
        self._load_from_environment()

        # Set up default providers
        self._setup_default_llm_providers()

        # Validate configuration
        self._validate_configuration()

    def _load_from_file(self) -> None:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path) as f:
                config_data = yaml.safe_load(f)

            # Load each section
            if "llm_providers" in config_data:
                for name, provider_data in config_data["llm_providers"].items():
                    self.llm_providers[name] = LLMProviderConfig(name=name, **provider_data)

            if "database" in config_data:
                self.database = DatabaseConfig(**config_data["database"])

            if "cache" in config_data:
                self.cache = CacheConfig(**config_data["cache"])

            if "security" in config_data:
                self.security = SecurityConfig(**config_data["security"])

            if "monitoring" in config_data:
                self.monitoring = MonitoringConfig(**config_data["monitoring"])

            if "feature_flags" in config_data:
                self.feature_flags = FeatureFlags(**config_data["feature_flags"])

            logger.info(f"Configuration loaded from {self.config_path}")

        except Exception as e:
            logger.warning(f"Could not load configuration file: {e}")

    def _load_from_environment(self) -> None:
        """Override configuration with environment variables"""
        # Database
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            if not self.database:
                self.database = DatabaseConfig(url=db_url)
            else:
                self.database.url = db_url

        # Cache
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            self.cache.redis_url = redis_url

        # Security -- fail-fast if SECRET_KEY absent or insecure in non-dev environments
        secret_key = os.getenv("SECRET_KEY")
        env = os.getenv("ENVIRONMENT", "development").lower()
        if env in ("production", "staging"):
            if not secret_key:
                raise ValueError(
                    "SECRET_KEY environment variable is required in production/staging. "
                    "Set a strong random value of at least 32 characters."
                )
            if secret_key in _INSECURE_SECRET_KEYS:
                raise ValueError(
                    "SECRET_KEY is set to an insecure default value. "
                    "Set a strong random value of at least 32 characters."
                )
            if len(secret_key) < _MIN_SECRET_KEY_LENGTH:
                raise ValueError(
                    f"SECRET_KEY must be at least {_MIN_SECRET_KEY_LENGTH} characters in production/staging. "
                    f"Current length: {len(secret_key)}"
                )
        # For development, fall back to a local-only default to allow dev without secrets
        effective_secret_key = secret_key or "dev-secret-change-in-production"
        if not self.security:
            self.security = SecurityConfig(secret_key=effective_secret_key)
        else:
            self.security.secret_key = effective_secret_key
        self.security.jwt_algorithm = os.getenv("JWT_ALGORITHM", self.security.jwt_algorithm)
        self.security.jwt_expiry_hours = int(
            os.getenv("JWT_EXPIRY_HOURS", self.security.jwt_expiry_hours)
        )

        # P0-6: Configure CORS allowed origins from environment
        # Format: ALLOWED_ORIGINS="https://app.sanskritisetu.org,https://www.sanskritisetu.org"
        allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "")
        if allowed_origins_str:
            self.security.allowed_origins = [
                origin.strip() for origin in allowed_origins_str.split(",") if origin.strip()
            ]
        elif self.environment in ["production", "staging"]:
            # Production/staging: Use frontend URL if no ALLOWED_ORIGINS specified
            frontend_url = os.getenv("FRONTEND_URL", "")
            if frontend_url:
                self.security.allowed_origins = [frontend_url]
            else:
                # No origins configured for production - will be caught by validation
                self.security.allowed_origins = []
        else:
            # Development: Allow localhost origins
            self.security.allowed_origins = [
                "http://localhost:3000",
                "http://localhost:8501",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:8501",
            ]

        # Tool Broker
        self.tool_broker.serena_api_url = os.getenv(
            "SERENA_API_URL", self.tool_broker.serena_api_url
        )
        self.tool_broker.serena_api_key = os.getenv(
            "SERENA_API_KEY", self.tool_broker.serena_api_key
        )
        self.tool_broker.seq_thinking_api_url = os.getenv(
            "SEQ_THINKING_API_URL", self.tool_broker.seq_thinking_api_url
        )
        self.tool_broker.seq_thinking_api_key = os.getenv(
            "SEQ_THINKING_API_KEY", self.tool_broker.seq_thinking_api_key
        )
        self.tool_broker.tool_broker_service_timeout = int(
            os.getenv(
                "TOOL_BROKER_SERVICE_TIMEOUT",
                self.tool_broker.tool_broker_service_timeout,
            )
        )

        # Feature flags from environment
        env_features = {
            "real_llm_integration": os.getenv("ENABLE_REAL_LLM", "false").lower() == "true",
            "ethics_gate_enabled": os.getenv("ENABLE_ETHICS_GATE", "false").lower() == "true",
            "response_caching": os.getenv("ENABLE_CACHING", "false").lower() == "true",
            "multi_llm_integration": os.getenv("ENABLE_MULTI_LLM", "false").lower() == "true",
            "docker_sandbox": os.getenv("ENABLE_DOCKER_SANDBOX", "false").lower() == "true",
            "advanced_analytics": os.getenv("ENABLE_ANALYTICS", "false").lower() == "true",
            "ml_ethics_engine": os.getenv("ENABLE_ML_ETHICS", "false").lower() == "true",
        }

        # Update feature flags
        for flag, value in env_features.items():
            setattr(self.feature_flags, flag, value)

        # Environment-specific overrides
        if self.environment == "production":
            self.feature_flags.production_logging = True
            self.feature_flags.performance_optimization = True
            self.monitoring.log_level = "WARNING"
        elif self.environment == "development":
            self.monitoring.log_level = "DEBUG"

    def _setup_default_llm_providers(self) -> None:
        """Setup default LLM provider configurations"""
        # Mistral AI (EU): het standaardmodel voor klantgegevens (ADR-041 B14). Geen terugval op een
        # ander gehuurd model: een klant die een EU-model koos, krijgt bij een storing een fout.
        mistral_key = os.getenv("MISTRAL_API_KEY")
        if mistral_key or self.feature_flags.real_llm_integration:
            self.llm_providers["mistral"] = LLMProviderConfig(
                name="mistral",
                enabled=bool(mistral_key),
                api_key=mistral_key,
                model=os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
                timeout=30,
                rate_limit=60,
                priority=0,
                fallback_to=None,
            )

        # Anthropic Claude
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key or self.feature_flags.real_llm_integration:
            self.llm_providers["anthropic"] = LLMProviderConfig(
                name="anthropic",
                enabled=bool(anthropic_key),
                api_key=anthropic_key,
                model=os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
                timeout=30,
                rate_limit=50,
                priority=1,
                fallback_to="google",
            )

        # Google Gemini
        google_key = os.getenv("GOOGLE_API_KEY")
        if google_key or self.feature_flags.real_llm_integration:
            self.llm_providers["google"] = LLMProviderConfig(
                name="google",
                enabled=bool(google_key),
                api_key=google_key,
                model=os.getenv("GOOGLE_MODEL", "gemini-2.5-pro"),
                timeout=20,
                rate_limit=60,
                priority=2,
                fallback_to="openai",
            )

        # OpenAI GPT
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key or self.feature_flags.real_llm_integration:
            self.llm_providers["openai"] = LLMProviderConfig(
                name="openai",
                enabled=bool(openai_key),
                api_key=openai_key,
                model="gpt-3.5-turbo",
                timeout=25,
                rate_limit=40,
                priority=3,
                fallback_to=None,  # No fallback - fail fast
            )

        # Mock provider REMOVED for production (P0-3: MOCK-003)
        # In production, fail fast if LLM providers unavailable
        # No silent degradation to mock responses

    def _validate_secret_key(self) -> list[str]:
        """Validate SECRET_KEY policy for production-like environments."""
        if self.environment not in ["production", "staging"]:
            return []

        if not self.security:
            return ["SECRET_KEY must be configured for production/staging."]

        secret_key = self.security.secret_key.strip()
        if not secret_key:
            return ["SECRET_KEY must be configured for production/staging."]

        if len(secret_key) < _MIN_SECRET_KEY_LENGTH:
            return [
                f"SECRET_KEY must be at least {_MIN_SECRET_KEY_LENGTH} characters for production/staging."
            ]

        if secret_key.lower() in _INSECURE_SECRET_KEYS:
            return ["SECRET_KEY cannot use a known insecure default in production/staging."]

        return []

    def _validate_configuration(self) -> None:
        """Validate configuration settings"""
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Database validation
        if self.feature_flags.real_database and not self.database:
            errors.append("Database configuration required when real_database is enabled")

        # Tool Broker validation
        if self.environment == "production":
            if not self.tool_broker.serena_api_url:
                errors.append("SERENA_API_URL environment variable required in production")
            if not self.tool_broker.seq_thinking_api_url:
                errors.append("SEQ_THINKING_API_URL environment variable required in production")
            if "localhost" in (self.tool_broker.serena_api_url or ""):
                errors.append("SERENA_API_URL cannot contain localhost in production")
            if "localhost" in (self.tool_broker.seq_thinking_api_url or ""):
                errors.append("SEQ_THINKING_API_URL cannot contain localhost in production")

        # Security validation
        errors.extend(self._validate_secret_key())

        # P0-6: CORS validation - reject wildcard in production
        if self.security:
            if self.environment in ["production", "staging"]:
                if "*" in self.security.allowed_origins:
                    errors.append(
                        "CORS wildcard ['*'] is not allowed in production/staging. Configure specific origins via ALLOWED_ORIGINS environment variable."
                    )
                if not self.security.allowed_origins:
                    errors.append(
                        "CORS allowed_origins must be configured for production/staging. Set ALLOWED_ORIGINS environment variable."
                    )

            # Validate origin format
            for origin in self.security.allowed_origins:
                if origin != "*" and not origin.startswith(("http://", "https://")):
                    logger.warning(
                        f"CORS origin '{origin}' does not start with http:// or https://"
                    )

        # LLM validation
        if self.feature_flags.real_llm_integration:
            enabled_providers = [p for p in self.llm_providers.values() if p.enabled and p.api_key]
            if not enabled_providers:
                logger.warning("Real LLM integration enabled but no providers have API keys")

        # Cache validation
        if self.cache.enable_redis and not self.cache.redis_url:
            logger.warning("Redis caching enabled but no REDIS_URL provided")

        if errors:
            error_msg = "Configuration validation failed: " + "; ".join(errors)
            logger.error(error_msg)
            if self.environment in ["production", "staging"]:
                raise ValueError(error_msg)

    def save_configuration(self) -> bool:
        """Save current configuration to file"""
        try:
            config_data = {
                "environment": self.environment,
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "llm_providers": {
                    name: {
                        "enabled": provider.enabled,
                        "model": provider.model,
                        "timeout": provider.timeout,
                        "rate_limit": provider.rate_limit,
                        "priority": provider.priority,
                        "fallback_to": provider.fallback_to,
                    }
                    for name, provider in self.llm_providers.items()
                },
                "database": (
                    {
                        "pool_size": self.database.pool_size,
                        "max_overflow": self.database.max_overflow,
                        "pool_timeout": self.database.pool_timeout,
                        "pool_recycle": self.database.pool_recycle,
                        "pool_pre_ping": self.database.pool_pre_ping,
                    }
                    if self.database
                    else {}
                ),
                "cache": {
                    "default_ttl": self.cache.default_ttl,
                    "max_memory_cache": self.cache.max_memory_cache,
                    "enable_redis": self.cache.enable_redis,
                    "enable_memory": self.cache.enable_memory,
                },
                "monitoring": {
                    "memory_alert_threshold": self.monitoring.memory_alert_threshold,
                    "memory_critical_threshold": self.monitoring.memory_critical_threshold,
                    "monitoring_interval": self.monitoring.monitoring_interval,
                    "enable_performance_monitoring": self.monitoring.enable_performance_monitoring,
                    "log_level": self.monitoring.log_level,
                    "metrics_retention_days": self.monitoring.metrics_retention_days,
                },
                "feature_flags": {
                    "real_llm_integration": self.feature_flags.real_llm_integration,
                    "ethics_gate_enabled": self.feature_flags.ethics_gate_enabled,
                    "response_caching": self.feature_flags.response_caching,
                    "multi_llm_integration": self.feature_flags.multi_llm_integration,
                    "docker_sandbox": self.feature_flags.docker_sandbox,
                    "advanced_analytics": self.feature_flags.advanced_analytics,
                    "ml_ethics_engine": self.feature_flags.ml_ethics_engine,
                    "real_database": self.feature_flags.real_database,
                    "production_logging": self.feature_flags.production_logging,
                    "performance_optimization": self.feature_flags.performance_optimization,
                },
            }

            with open(self.config_path, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False)

            logger.info(f"Configuration saved to {self.config_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False

    def get_enabled_llm_providers(self) -> list[LLMProviderConfig]:
        """Get list of enabled LLM providers sorted by priority"""
        enabled = [p for p in self.llm_providers.values() if p.enabled]
        return sorted(enabled, key=lambda x: x.priority)

    def enable_feature(self, feature_name: str) -> bool:
        """Enable a specific feature flag"""
        if hasattr(self.feature_flags, feature_name):
            setattr(self.feature_flags, feature_name, True)
            logger.info(f"Feature enabled: {feature_name}")
            return True
        return False

    def disable_feature(self, feature_name: str) -> bool:
        """Disable a specific feature flag"""
        if hasattr(self.feature_flags, feature_name):
            setattr(self.feature_flags, feature_name, False)
            logger.info(f"Feature disabled: {feature_name}")
            return True
        return False

    def get_production_readiness_score(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Assess production readiness"""
        score = 0
        max_score = 0
        issues: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Database configuration (20 points)
        max_score += 20
        if self.database and self.database.url:
            score += 15
            if self.database.pool_size >= 20:
                score += 5
        else:
            issues.append("Database not configured")

        # Security configuration (25 points)
        max_score += 25
        if self.security:
            if self.security.secret_key != "dev-secret-change-in-production":
                score += 15
            else:
                issues.append("Using default secret key")

            if self.security.jwt_expiry_hours <= 24:
                score += 5
            if self.security.bcrypt_rounds >= 12:
                score += 5
        else:
            issues.append("Security configuration missing")

        # LLM providers (15 points)
        max_score += 15
        enabled_providers = self.get_enabled_llm_providers()
        if len(enabled_providers) >= 2:
            score += 15
        elif len(enabled_providers) == 1:
            score += 10
            issues.append("Only one LLM provider configured")
        else:
            issues.append("No LLM providers configured")

        # Monitoring (15 points)
        max_score += 15
        if self.monitoring.enable_performance_monitoring:
            score += 10
        if self.monitoring.memory_alert_threshold <= 85:
            score += 5

        # Caching (10 points)
        max_score += 10
        if self.cache.redis_url:
            score += 10
        elif self.cache.enable_memory:
            score += 5
            issues.append("No Redis caching configured")

        # Feature completeness (15 points)
        max_score += 15
        production_features = [
            self.feature_flags.production_logging,
            self.feature_flags.performance_optimization,
            self.feature_flags.real_database,
        ]
        score += sum(5 for f in production_features if f)

        percentage = (score / max_score) * 100 if max_score > 0 else 0

        return {
            "score": score,
            "max_score": max_score,
            "percentage": percentage,
            "grade": self._get_readiness_grade(percentage),
            "issues": issues,
            "recommendations": self._get_readiness_recommendations(percentage, issues),
        }

    def _get_readiness_grade(self, percentage: float) -> str:
        """Get readiness grade based on percentage"""
        if percentage >= 90:
            return "A+ (Production Ready)"
        elif percentage >= 80:
            return "A (Ready with minor issues)"
        elif percentage >= 70:
            return "B (Needs improvements)"
        elif percentage >= 60:
            return "C (Major issues)"
        else:
            return "F (Not ready for production)"

    def _get_readiness_recommendations(self, percentage: float, issues: list[str]) -> list[str]:
        """Get recommendations based on readiness assessment"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if percentage < 70:
            recommendations.append("Address critical configuration issues before deployment")

        if "Database not configured" in issues:
            recommendations.append("Configure PostgreSQL database with connection pooling")

        if "Using default secret key" in issues:
            recommendations.append("Generate secure SECRET_KEY for production")

        if "No Redis caching configured" in issues:
            recommendations.append("Set up Redis for improved performance")

        if percentage >= 90:
            recommendations.append("System is production ready - proceed with deployment")

        return recommendations

    def get_configuration_summary(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive configuration summary"""
        return {
            "environment": self.environment,
            "feature_flags": {
                flag: getattr(self.feature_flags, flag)
                for flag in dir(self.feature_flags)
                if not flag.startswith("_")
            },
            "llm_providers": {
                name: {
                    "enabled": provider.enabled,
                    "has_api_key": bool(provider.api_key),
                    "model": provider.model,
                    "priority": provider.priority,
                }
                for name, provider in self.llm_providers.items()
            },
            "database_configured": bool(self.database),
            "cache_configured": bool(self.cache.redis_url),
            "security_configured": bool(
                self.security and self.security.secret_key != "dev-secret-change-in-production"
            ),
            "production_readiness": self.get_production_readiness_score(),
        }


# Global configuration manager
config_manager: ProductionConfigManager | None = None


def get_production_config() -> ProductionConfigManager:
    """Get global production configuration manager"""
    global config_manager
    if config_manager is None:
        config_manager = ProductionConfigManager()
    return config_manager


def initialize_production_config(
    config_path: str | None = None,
) -> ProductionConfigManager:
    """Initialize production configuration manager"""
    global config_manager
    config_manager = ProductionConfigManager(config_path)
    return config_manager
