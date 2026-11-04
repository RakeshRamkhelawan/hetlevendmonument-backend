"""Centralized application configuration with NLP settings."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized application settings using Pydantic.
    Settings are loaded from a .env file and can be overridden by environment variables.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "ToolBrokerService"
    DEBUG: bool = False

    # Serena API settings
    SERENA_API_URL: str = "http://localhost:8001"
    SERENA_API_KEY: str | None = None

    # Sequential Thinking API settings
    SEQ_THINKING_API_URL: str = "http://localhost:8002"
    SEQ_THINKING_API_KEY: str | None = None

    # Redis settings
    REDIS_URL: str = "redis://localhost:6379/0"

    # Tool Broker Service settings
    TOOL_BROKER_SERVICE_TIMEOUT: int = 30  # Default timeout in seconds

    # Security settings (voorbeeld)
    SECRET_KEY: str = "a_default_secret_key_that_must_be_overridden_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # -- NLP Settings -----------------------------------------------------

    # Rate limiting for NLP endpoints
    NLP_PARSE_RATE_LIMIT: str = "30/minute"  # Rate limit for /parse endpoint
    NLP_EXECUTE_RATE_LIMIT: str = "10/minute"  # Rate limit for /execute endpoint
    NLP_MATCH_RATE_LIMIT: str = "60/minute"  # Rate limit for /match-participants
    NLP_SUGGEST_RATE_LIMIT: str = "60/minute"  # Rate limit for /suggest-corrections

    # Input validation
    NLP_MAX_TEXT_LENGTH: int = 5000  # Maximum text length for NLP input
    NLP_MAX_CANDIDATES: int = 1000  # Maximum participants for fuzzy matching
    NLP_MAX_NAMES_PER_REQUEST: int = 50  # Maximum names per match request

    # Context management
    NLP_CONTEXT_MAX_AGE_MINUTES: int = 30  # Context expiration time
    NLP_CONTEXT_MAX_CLARIFICATION_ATTEMPTS: int = 3  # Max clarification questions
    NLP_CONTEXT_ENABLE_REDIS: bool = False  # Enable Redis for context persistence

    # Fuzzy matching
    NLP_FUZZY_CACHE_TTL_SECONDS: int = 300  # Cache TTL in seconds (5 minutes)
    NLP_FUZZY_SCORE_CUTOFF: int = 70  # Minimum match score (0-100)
    NLP_FUZZY_MAX_SUGGESTIONS: int = 5  # Maximum correction suggestions

    # Session security
    NLP_SESSION_ID_ENTROPY_BYTES: int = 16  # Entropy for session ID generation

    # -- ML Recommendation Settings -----------------------------------------

    ml_recommendations_enabled: bool = False  # Enable ML pack recommendations
    ml_min_confidence_threshold: float = 0.50  # Minimum ML confidence (0.0-1.0)
    ml_model_path: str = "models/pack_recommendation.pkl"  # Path to ML model file


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
