"""
AUDIT-P0-C1: SQLite defaults in config.py and unified_config.py must be blocked
in production to prevent bypassing Row Level Security.

RED phase: test_settings_rejects_sqlite_in_production and
test_unified_config_rejects_sqlite_in_production will FAIL until validators are added.
"""

import pytest


@pytest.mark.unit
class TestSettingsSQLiteProductionGuard:
    """Settings (config.py) must reject SQLite URLs in ENVIRONMENT=production."""

    def test_settings_allows_sqlite_in_development(self, monkeypatch):
        """SQLite is fine in development — default must still work."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("TESTING", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        from src.core.shared.config import Settings

        s = Settings(database_url="sqlite:///./sanskriti_setu.db")
        assert "sqlite" in s.database_url

    def test_settings_rejects_sqlite_in_production(self, monkeypatch):
        """RED: SQLite must be rejected when ENVIRONMENT=production."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("TESTING", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        from src.core.shared.config import Settings

        with pytest.raises(Exception, match="(?i)sqlite|production|rls"):
            Settings(database_url="sqlite:///./sanskriti_setu.db")

    def test_settings_allows_postgres_in_production(self, monkeypatch):
        """PostgreSQL URL must be accepted in production."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("TESTING", raising=False)

        from src.core.shared.config import Settings

        s = Settings(database_url="postgresql+asyncpg://user:pass@db:5432/prod")
        assert "postgresql" in s.database_url

    def test_settings_allows_sqlite_in_testing_mode(self, monkeypatch):
        """TESTING=1 must bypass the production guard (test environments)."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("TESTING", "1")

        from src.core.shared.config import Settings

        s = Settings(database_url="sqlite:///./sanskriti_setu.db")
        assert "sqlite" in s.database_url


@pytest.mark.unit
class TestUnifiedConfigSQLiteProductionGuard:
    """UnifiedConfig (unified_config.py) must reject SQLite URLs in production."""

    def test_unified_config_allows_sqlite_in_development(self, monkeypatch):
        """SQLite is fine in development."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("TESTING", raising=False)

        from src.core.config.unified_config import UnifiedConfig

        c = UnifiedConfig(database_url="sqlite+aiosqlite:///./sanskriti_setu.db")
        assert "sqlite" in c.database_url

    def test_unified_config_rejects_sqlite_in_production(self, monkeypatch):
        """RED: SQLite must be rejected when ENVIRONMENT=production."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("TESTING", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        from src.core.config.unified_config import UnifiedConfig

        with pytest.raises(Exception, match="(?i)sqlite|production|rls"):
            UnifiedConfig(database_url="sqlite+aiosqlite:///./sanskriti_setu.db")

    def test_unified_config_allows_postgres_in_production(self, monkeypatch):
        """PostgreSQL URL must be accepted in production."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("TESTING", raising=False)

        from src.core.config.unified_config import UnifiedConfig

        c = UnifiedConfig(database_url="postgresql+asyncpg://user:pass@db:5432/prod")
        assert "postgresql" in c.database_url

    def test_unified_config_allows_sqlite_in_testing_mode(self, monkeypatch):
        """TESTING=1 must bypass the production guard."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("TESTING", "1")

        from src.core.config.unified_config import UnifiedConfig

        c = UnifiedConfig(database_url="sqlite+aiosqlite:///./sanskriti_setu.db")
        assert "sqlite" in c.database_url
