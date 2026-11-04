"""
Configuration management for Sanskriti Setu AI Multi-Agent System
Centralized configuration with environment variable support and feature flags

Pydantic v2 Compatible: Uses pydantic-settings with proper env var handling
"""

import os
from typing import Any, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.shared.docker_utils import check_docker_availability
from src.core.types import IsolationLevel
from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord


class Settings(BaseSettings):
    """
    Application settings with environment variable support

    Note: pydantic-settings automatically maps UPPER_CASE env vars to lowercase field names
    Example: DATABASE_URL env var -> database_url field
    """

    # Environment
    environment: str = Field(default="development")
    debug: bool = Field(default=False)  # P0-5: Changed to False for production safety
    app_setup_mode: bool = Field(default=False)
    setup_artifact_path: str = Field(default=".env.bootstrap")

    @field_validator("debug", mode="before")
    @classmethod
    def validate_debug(cls, v: Any) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Validate debug field using APP_DEBUG env var, ignoring DEBUG env var.

        The DEBUG env var is commonly used by logging tools with non-boolean values.
        Always use APP_DEBUG=true|false for application debug mode.
        """
        # Check APP_DEBUG first (our standard)
        app_debug = os.getenv("APP_DEBUG")
        if app_debug is not None:
            return app_debug.lower() in ("true", "1", "yes", "on")

        # If APP_DEBUG not set, use the field value (default False)
        # Ignore DEBUG env var entirely to avoid conflicts with logging tools
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return False

    # Database Configuration
    database_url: str = Field(default="sqlite:///./sanskriti_setu.db")
    database_pool_size: int = Field(default=5)

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

    # Production Database URLs (for Week 2+)
    production_db_url: str = Field(
        default_factory=lambda: os.getenv("PRODUCTION_DB_URL", "CONFIGURE_IN_ENVIRONMENT")
    )
    sandbox_cva_db_url: str = Field(
        default_factory=lambda: os.getenv("SANDBOX_CVA_DB_URL", "CONFIGURE_IN_ENVIRONMENT")
    )
    sandbox_shared_db_url: str = Field(
        default_factory=lambda: os.getenv("SANDBOX_SHARED_DB_URL", "CONFIGURE_IN_ENVIRONMENT")
    )

    # API Configuration
    api_host: str = Field(default="0.0.0.0")  # nosec B104: Docker networking (Traefik secures)
    api_port: int = Field(default=8000)
    api_title: str = Field(default="Sanskriti Setu API")
    api_version: str = Field(default="1.0.0")

    # Security
    secret_key: str = Field(default="")  # Must be set via SECRET_KEY env var in production
    access_token_expire_minutes: int = Field(default=30)
    password_hash_rounds: int = Field(default=12)

    # External AI Services
    google_api_key: str | None = Field(default=None)
    deepseek_api_key: str | None = Field(default=None)
    openai_api_key: str | None = Field(default=None)
    anthropic_api_key: str | None = Field(default=None)
    ollama_base_url: str | None = Field(default=None)

    # Digital Twin configuration
    twin_suggestion_log_retention_days: int = Field(
        default=2555, ge=2555, description="Retention for twin_suggestion_log (default 7 years)"
    )
    twin_hard_delete_max_hours: int = Field(
        default=24, ge=1, le=720, description="Max hours between hard-delete request and execution"
    )

    # Sandbox Configuration
    default_isolation_level: IsolationLevel = Field(default=IsolationLevel.DOCKER)

    @field_validator("default_isolation_level", mode="before")
    @classmethod
    def normalize_isolation_level(cls, v: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Convert isolation level to lowercase for enum matching"""
        if isinstance(v, str):
            return v.lower()
        return v

    sandbox_timeout: int = Field(default=300)  # 5 minutes
    sandbox_memory_limit: str = Field(default="512m")
    sandbox_cpu_limit: str = Field(default="0.5")

    # Agent Configuration
    max_concurrent_tasks: int = Field(default=10)
    agent_heartbeat_interval: int = Field(default=30)
    agent_task_timeout: int = Field(default=600)  # 10 minutes
    agent_execution_timeout: int = Field(default=30)

    # Redis Configuration (for Week 2+)
    redis_url: str = Field(default="redis://localhost:6379")
    redis_db: int = Field(default=0)

    # Frontend Configuration
    frontend_url: str = Field(default="http://localhost:8501")

    # Foundation Portal (ADR-029) white-label portal base URL for magic links
    foundation_portal_base_url: str = Field(default="http://localhost:5173")

    # Logging
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="sanskriti_setu.log")

    # Focus Builder feature flags
    focus_builder_tool_agent: bool = Field(
        default=False,
        description="Enable tool-calling agent (approach 3) for Focus Builder. Set FOCUS_BUILDER_TOOL_AGENT=true.",
    )

    # Document Storage Configuration (SP-B01)
    storage_backend: str = Field(default="local")
    local_upload_dir: str = Field(default="/tmp/uploads")
    # Ook de globale ASGI-bovengrens voor MaxRequestBodySizeMiddleware (BE-AGT-060 dag 3
    # Gate 2, security-review finding 1) -- niet alleen documents/upload_router.py's eigen
    # cap. Verhogen voor een puur opslag-/UX-reden verruimt daarmee ONBEDOELD ook die globale
    # DoS-bovengrens voor de hele app; wijzig met dat in gedachten.
    max_upload_size_bytes: int = Field(default=50 * 1024 * 1024)  # 50 MB

    # Foundation Portal storage (BE-EP-036, ADR-029) -- azure backend of
    # FoundationStorageService; local backend gebruikt local_upload_dir hierboven.
    azure_storage_connection_string: str | None = Field(default=None)
    azure_storage_account_url: str | None = Field(default=None)
    foundation_blob_container: str = Field(default="foundation-content")

    # Brevo Transactional Email (ADR-029 P1-5)
    brevo_api_key: str | None = Field(default=None)
    brevo_sender_email: str = Field(default="noreply@sanskritisetu.org")
    brevo_sender_name: str = Field(default="Het Levend Monument")
    brevo_webhook_secret: str | None = Field(default=None)

    # Pydantic v2 settings configuration
    model_config = SettingsConfigDict(
        env_file=(
            (".env", ".env.development") if os.getenv("TESTING") != "1" else None
        ),  # Skip env files in tests
        env_file_encoding="utf-8",
        extra="ignore",  # Allow extra fields from .env
        case_sensitive=False,  # ENV_VAR -> env_var mapping
    )


# Feature Flags Configuration
FEATURE_FLAGS = {
    # Phase 4 - Learning rollout defaults
    "learning_enabled": False,
    "agent_learning": False,  # ADR-025 Task 3.1: twin intervention -> LearningExperience bridge
    "learning_group_core": False,
    "learning_group_generated": False,
    "learning_group_specialist": False,
    "learning_group_technical": False,
    "learning_group_als": False,
    # Week 1 - Core functionality
    "basic_cva_agent": True,
    "mock_sandbox": False,  # Disabled for production - using real Docker sandbox
    "simple_task_queue": True,
    "basic_approval_queue": True,
    "streamlit_ui": True,
    # Week 2 - Enhanced functionality - Enable by default for production
    "real_llm_integration": True,
    "real_docker_sandbox": True,
    "multi_agent_orchestration": True,  # Enable multi-agent features
    "advanced_task_routing": True,
    "websocket_updates": True,  # Enable WebSocket features
    "agent_load_balancing": True,
    # Week 3 - Advanced features - Enable by default for production
    "ml_ethics_engine": True,  # Enable ML ethics features
    "knowledge_evolution": True,
    "advanced_ui": True,  # Enable advanced UI features
    "performance_analytics": True,
    "custom_agent_plugins": True,
    # Phase 2 - Intelligent Multi-LLM Orchestration
    "multi_llm_integration": True,  # Multi-LLM provider orchestration
    "response_caching": True,  # LLM response caching system
    "ethics_gate_enabled": True,  # AI safety and ethics validation
    "intelligent_routing": True,  # Performance-based LLM routing
    "dynamic_load_balancing": True,  # Dynamic LLM load balancing
    # Phase 3 - Advanced Agent Collaboration & Knowledge Evolution
    "agent_mesh_enabled": True,  # Multi-agent communication mesh
    "collaborative_tasks": True,  # Multi-agent task coordination
    "adaptive_learning": True,  # Agent capability evolution
    "knowledge_patterns": True,  # Pattern discovery and learning
    "system_optimization": True,  # Autonomous system optimization
    "intelligent_monitoring": True,  # Advanced system monitoring
    "performance_prediction": True,  # Predictive performance analysis
    "resource_orchestration": True,  # Dynamic resource allocation
    # Phase 4 - Autonomous AI Ecosystem & Self-Expansion
    "autonomous_ai_ecosystem": True,  # Overall Phase 4 autonomous systems
    "autonomous_agent_generation": True,  # Dynamic agent creation
    "self_healing_architecture": True,  # Automatic system repair
    "dynamic_code_generation": True,  # Runtime code generation
    "emergent_intelligence": True,  # Emergent behavior facilitation
    "autonomous_system_analysis": True,  # System needs analysis
    "self_expanding_capabilities": True,  # Self-capability expansion
    "meta_learning_systems": True,  # Learning about learning
    "autonomous_optimization": True,  # Self-optimization systems
    # ADR-036 OP-12 (addendum SS8.2): CVAAutonomousTrigger's oversight_gate/tenant-
    # resolutie/audit-logging/Prana-budget-fixes zijn geimplementeerd, maar het pad blijft
    # vandaag onbereikbaar (geen externe aanroeper, zie
    # tests/architecture/test_op12_autonomous_breakthrough_stays_unwired.py). Deze vlag is
    # defense-in-depth, geen vervanging van die guard-tests -- default UIT.
    "autonomous_breakthrough": False,
    # ADR-036 OP-24 (BE-SEC-048): initiator-eis + Council-raadpleging op
    # EnhancedBaseAgent.execute_tool(). Taak 0 (2026-08-26) vond geen levende externe
    # aanroeper van deze methode op de ~20 subklassen buiten de ALS-boom -- default UIT,
    # architecturale consistentie voor de dag dat dit pad wel live gaat.
    "enhanced_base_agent_initiator_check": False,
}


def get_feature_flag(flag_name: str) -> bool:
    """Get feature flag value, with environment variable override"""
    env_var = f"FEATURE_{flag_name.upper()}"
    env_value = os.getenv(env_var)

    if env_value is not None:
        return env_value.lower() in ("true", "1", "yes", "on")

    return FEATURE_FLAGS.get(flag_name, False)


def set_feature_flag(flag_name: str, enabled: bool) -> None:
    """Set feature flag value (for testing/development)"""
    FEATURE_FLAGS[flag_name] = enabled


def get_database_url(environment: str = "development") -> str:
    """Get appropriate database URL based on environment"""
    settings = get_settings()

    if environment == "production":
        return settings.production_db_url
    elif environment == "sandbox_cva":
        return settings.sandbox_cva_db_url
    elif environment == "sandbox_shared":
        return settings.sandbox_shared_db_url
    else:
        return settings.database_url


# Global settings instance
_settings: Settings | None = None
REVIEWED_SETUP_ARTIFACT_NAME = ".env.bootstrap"


def get_settings() -> Settings:
    """Get application settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment (useful for testing)"""
    global _settings
    _settings = Settings()
    return _settings


def is_production() -> bool:
    """Return True when the active environment is production."""
    return get_settings().environment.lower() == "production"


def is_setup_mode_enabled() -> bool:
    """Return whether explicit bootstrap mode is enabled."""
    return get_settings().app_setup_mode


def get_setup_artifact_path() -> str:
    """Return the configured setup artifact path candidate for setup writes."""
    return get_settings().setup_artifact_path


def get_setup_artifact_name() -> str:
    """Return the only reviewed bootstrap artifact name allowed for setup writes."""
    return REVIEWED_SETUP_ARTIFACT_NAME


# Environment-specific configurations
ENVIRONMENTS = {
    "development": {
        "debug": True,
        "log_level": "DEBUG",
        "database_url": "sqlite:///./dev_sanskriti_setu.db",
        "isolation_level": IsolationLevel.MOCK,
    },
    "testing": {
        "debug": True,
        "log_level": "WARNING",
        "database_url": "sqlite:///:memory:",
        "isolation_level": IsolationLevel.MOCK,
    },
    "staging": {
        "debug": False,
        "log_level": "INFO",
        "isolation_level": IsolationLevel.PROCESS,
    },
    "production": {
        "debug": False,
        "log_level": "WARNING",
        "isolation_level": IsolationLevel.CONTAINER,
    },
}


def apply_environment_config(env_name: str) -> None:
    """Apply environment-specific configuration overrides"""
    if env_name not in ENVIRONMENTS:
        raise ValueError(f"Unknown environment: {env_name}")

    env_config = ENVIRONMENTS[env_name]
    settings = get_settings()

    for key, value in env_config.items():
        if hasattr(settings, key):
            setattr(settings, key, value)


# Configuration validation
def validate_configuration() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Validate configuration and return any errors"""
    errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    settings = get_settings()

    # Check SECRET_KEY in all environments
    default_keys = ["dev-secret-key-change-in-production-please", "dev-secret-key"]
    if not settings.secret_key or settings.secret_key in default_keys:
        errors.append("SECRET_KEY must be set")
    elif len(settings.secret_key) < 64:
        errors.append("SECRET_KEY must be at least 64 characters long")

    # Check that the primary LLM provider is configured for production
    # Dit was een eis op DEEPSEEK_API_KEY: de uitrol moest een sleutel hebben voor een leverancier die
    # niet met klantgegevens mag (ADR-041 B14). Het platformstandaardmodel is Mistral (EU).
    if is_production() and not os.environ.get("MISTRAL_API_KEY"):
        errors.append("MISTRAL_API_KEY must be set in production")

        # P0-5: Check debug mode in production
        if settings.debug:
            errors.append("DEBUG mode must be disabled (False) in production environment")

    # Check database URL format and presence
    if not settings.database_url:
        errors.append("DATABASE_URL must be set.")
    elif not (
        settings.database_url.startswith("postgresql://")
        or settings.database_url.startswith("postgresql+asyncpg://")
    ):
        errors.append(
            "DATABASE_URL must be a PostgreSQL connection string (e.g., postgresql://...)."
        )

    # Production-specific checks
    if is_production():
        if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
            errors.append("Production DATABASE_URL cannot use localhost or 127.0.0.1.")

        # Check for common default passwords
        default_passwords = [
            "password",
            "pass",
            "default",
            "changeme",
            "123456",
            "sanskriti_pass",
        ]
        if any(f":{pwd}@" in settings.database_url.lower() for pwd in default_passwords):
            errors.append("Production DATABASE_URL contains a common default password.")

        # Check SECRET_KEY for production
        if not settings.secret_key:
            errors.append("SECRET_KEY must be set in production environment.")
        elif len(settings.secret_key) < 64:
            errors.append("SECRET_KEY must be at least 64 characters long for security.")

        # Check sandbox configuration
        if settings.default_isolation_level == IsolationLevel.DOCKER:
            if not check_docker_availability():
                errors.append(
                    "Docker daemon is not running or accessible. Cannot use IsolationLevel.DOCKER."
                )

        # Check Foundation Portal base URL in production
        # Use urllib.parse for accurate host extraction instead of string matching
        # to avoid false positives like https://my-localhost-service.com
        from urllib.parse import urlparse
        parsed = urlparse(settings.foundation_portal_base_url)
        hostname = parsed.hostname or ""
        if hostname in ("localhost", "127.0.0.1"):
            errors.append(
                "FOUNDATION_PORTAL_BASE_URL cannot use localhost or 127.0.0.1 in production."
            )

    return {"errors": [str(e) for e in errors], "warnings": []}


if __name__ == "__main__":
    # Configuration testing/debugging
    settings = get_settings()
    print(f"Environment: {settings.environment}")
    print(f"Debug: {settings.debug}")
    print(f"Database URL: {database_url_zonder_wachtwoord(settings.database_url)}")
    print(f"Feature flags: {FEATURE_FLAGS}")

    # Validate configuration
    validation = validate_configuration()
    if validation["errors"]:
        print(f"Configuration errors: {validation['errors']}")
    if validation["warnings"]:
        print(f"Configuration warnings: {validation['warnings']}")
