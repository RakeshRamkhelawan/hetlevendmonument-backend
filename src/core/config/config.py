"""
Configuration Management - Pydantic BaseSettings Implementation
Laadt configuratie uit .env bestand zoals gespecificeerd in FASE 1 plan
"""

from decimal import Decimal
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings using Pydantic BaseSettings
    Laadt alle variabelen uit .env bestand
    """

    # Database configuratie
    database_url: str = ""

    # Redis configuratie
    redis_url: str = ""

    # Security configuratie
    secret_key: str = ""

    # Optionele configuratie
    environment: str = "development"
    debug: bool = False

    # ML Configuration
    ml_model_path: str = "models/pack_recommendation.pkl"
    ml_min_training_samples: int = 100
    ml_training_lookback_days: int = 90
    ml_recommendations_enabled: bool = True
    ml_min_confidence_threshold: float = 0.6

    # App / Auth settings (mirrors src/core/config.py)
    APP_NAME: str = "SanskritiSetu"
    DEBUG: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "a_default_secret_key_that_must_be_overridden_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    SERENA_API_URL: str = "http://localhost:8001"
    SERENA_API_KEY: str | None = None
    TOOL_BROKER_SERVICE_TIMEOUT: int = 30

    # Digital Twin LLM Cost Rates (EUR per 1M tokens)
    TWIN_COST_CLAUDE_INPUT_EUR_PER_1M: Decimal = Decimal("3.00")
    TWIN_COST_CLAUDE_OUTPUT_EUR_PER_1M: Decimal = Decimal("15.00")
    TWIN_COST_GEMINI_INPUT_EUR_PER_1M: Decimal = Decimal("0.50")
    TWIN_COST_GEMINI_OUTPUT_EUR_PER_1M: Decimal = Decimal("1.50")
    TWIN_COST_LOCAL_INPUT_EUR_PER_1M: Decimal = Decimal("0.00")
    TWIN_COST_LOCAL_OUTPUT_EUR_PER_1M: Decimal = Decimal("0.00")

    # NLP Settings
    NLP_PARSE_RATE_LIMIT: str = "30/minute"
    NLP_EXECUTE_RATE_LIMIT: str = "10/minute"
    NLP_MATCH_RATE_LIMIT: str = "60/minute"
    NLP_SUGGEST_RATE_LIMIT: str = "60/minute"
    NLP_MAX_TEXT_LENGTH: int = 5000
    NLP_MAX_CANDIDATES: int = 1000
    NLP_MAX_NAMES_PER_REQUEST: int = 50
    NLP_CONTEXT_MAX_AGE_MINUTES: int = 30
    NLP_CONTEXT_MAX_CLARIFICATION_ATTEMPTS: int = 3
    NLP_CONTEXT_ENABLE_REDIS: bool = False
    NLP_FUZZY_CACHE_TTL_SECONDS: int = 300
    NLP_FUZZY_SCORE_CUTOFF: int = 70
    NLP_FUZZY_MAX_SUGGESTIONS: int = 5
    NLP_SESSION_ID_ENTROPY_BYTES: int = 16

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables
    )


# Global settings instance (lazy initialization)
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get application settings"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
