"""Test configuration module."""

from enum import Enum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Environment types."""

    TEST = "test"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class TestConfig(BaseSettings):
    """Test configuration settings."""

    # Environment
    environment: Environment = Field(default=Environment.TEST)

    # Database Configuration
    database_url: str = Field(default="postgresql+asyncpg://postgres:admin@localhost:5432/postgres")
    database_pool_size: int = Field(default=5)
    database_max_overflow: int = Field(default=10)

    # Test Configuration
    test_data_path: str = Field(default="./test_data")
    mock_external_services: bool = Field(default=True)

    model_config = SettingsConfigDict(env_prefix="TEST_", case_sensitive=False)


# Create singleton instance
test_config = TestConfig()
