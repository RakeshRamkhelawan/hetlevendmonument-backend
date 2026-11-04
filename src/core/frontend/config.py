# Bestand: core/frontend/config.py
"""
Frontend configuration management voor Sanskriti Setu Streamlit applicatie.
Gebruikt Pydantic Settings voor environment variable management.
"""

import logging
from functools import lru_cache
from typing import Any, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Frontend configuration settings.
    Reads settings from environment variables with .env.streamlit file support.
    """

    model_config = SettingsConfigDict(
        env_file=".env.streamlit", env_file_encoding="utf-8", case_sensitive=True
    )

    API_BASE_URL: str = "http://localhost:8000"
    APP_TITLE: str = "[U+0001F549] Sanskriti Setu - AI Multi-Agent Platform"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    API_TIMEOUT: int = 30
    ENABLE_DEBUG: bool = False

    @field_validator("API_BASE_URL")
    @classmethod
    def validate_https_in_production(cls, v: str, info: Any) -> str:  # TODO(TYPE): replace Any with concrete type
        """
        CRITICAL FIX C3: Enforce HTTPS in production environment.
        Prevents credential exposure over unencrypted HTTP connections.
        """
        # Get environment from values dict
        environment = info.data.get("ENVIRONMENT", "development")

        if environment == "production" and v.startswith("http://"):
            raise ValueError(
                "API_BASE_URL must use https:// in production environment. "
                "HTTP transmits credentials in plaintext (OWASP A02:2021 violation)."
            )

        # Log warning for non-production HTTP usage
        if v.startswith("http://") and environment != "development":
            logger.warning(
                f"Using HTTP in {environment} environment. Consider using HTTPS for security."
            )

        return v


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached instance of the settings.
    Uses LRU cache to avoid re-reading environment variables on every call.
    """
    return Settings()


# Export singleton instance
settings = get_settings()
