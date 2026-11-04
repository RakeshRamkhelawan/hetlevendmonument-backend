"""Unit tests for src.core.database.timeout_config."""

from src.core.database.timeout_config import (
    TimeoutConfig,
    get_timeout_config,
    apply_timeout_to_url,
)


def test_timeout_config_defaults():
    """Validates standard default timeout values."""
    config = TimeoutConfig()
    assert config.connect_timeout == 10
    assert config.command_timeout == 30
    assert config.statement_timeout == 60
    assert config.lock_timeout == 10
    assert config.idle_in_transaction_timeout == 60
    assert config.pool_timeout == 30


def test_timeout_config_from_env(monkeypatch):
    """Parses environment variables correctly."""
    monkeypatch.setenv("DB_CONNECT_TIMEOUT", "5")
    monkeypatch.setenv("DB_COMMAND_TIMEOUT", "15")
    monkeypatch.setenv("DB_STATEMENT_TIMEOUT", "45")
    monkeypatch.setenv("DB_LOCK_TIMEOUT", "7")
    monkeypatch.setenv("DB_IDLE_TIMEOUT", "120")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "25")

    config = TimeoutConfig.from_env()
    assert config.connect_timeout == 5
    assert config.command_timeout == 15
    assert config.statement_timeout == 45
    assert config.lock_timeout == 7
    assert config.idle_in_transaction_timeout == 120
    assert config.pool_timeout == 25


def test_to_connection_args():
    """Generates connection argument dictionary for SQLAlchemy."""
    config = TimeoutConfig(connect_timeout=12, command_timeout=24, statement_timeout=36)
    args = config.to_connection_args()
    assert args["connect_timeout"] == 12
    assert args["command_timeout"] == 24
    assert args["options"] == "-c statement_timeout=36000"


def test_to_postgres_options():
    """Generates postgres command line options string with millisecond conversions."""
    config = TimeoutConfig(
        statement_timeout=10,
        lock_timeout=5,
        idle_in_transaction_timeout=20,
    )
    opts = config.to_postgres_options()
    assert "-c statement_timeout=10000" in opts
    assert "-c lock_timeout=5000" in opts
    assert "-c idle_in_transaction_session_timeout=20000" in opts


def test_get_timeout_config_logging(monkeypatch):
    """get_timeout_config helper returns loaded configuration."""
    monkeypatch.setenv("DB_CONNECT_TIMEOUT", "8")
    cfg = get_timeout_config()
    assert cfg.connect_timeout == 8


def test_apply_timeout_to_url_no_existing_query():
    """Appends timeouts with '?' when URL has no query parameters."""
    url = "postgresql+asyncpg://localhost:5432/sanskriti"
    config = TimeoutConfig(connect_timeout=3)
    modified = apply_timeout_to_url(url, config)
    assert modified.startswith(url + "?")
    assert "connect_timeout=3" in modified
    assert "options=" in modified


def test_apply_timeout_to_url_existing_query():
    """Appends timeouts with '&' when URL already contains query parameters."""
    url = "postgresql+asyncpg://localhost:5432/sanskriti?ssl=true"
    config = TimeoutConfig(connect_timeout=4)
    modified = apply_timeout_to_url(url, config)
    assert modified.startswith(url + "&")
    assert "connect_timeout=4" in modified
