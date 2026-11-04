"""Unit tests for src.core.database.ssl_config."""

import ssl
from unittest.mock import patch, MagicMock

import pytest

from src.core.database.ssl_config import (
    SSLMode,
    get_ssl_context,
    get_database_ssl_args,
    get_asyncpg_ssl_args,
)


def test_ssl_mode_enum_values():
    """Validates all PostgreSQL SSL modes are defined."""
    assert SSLMode.DISABLE.value == "disable"
    assert SSLMode.ALLOW.value == "allow"
    assert SSLMode.PREFER.value == "prefer"
    assert SSLMode.REQUIRE.value == "require"
    assert SSLMode.VERIFY_CA.value == "verify-ca"
    assert SSLMode.VERIFY_FULL.value == "verify-full"


def test_get_ssl_context_disable():
    """Returns None when ssl_mode is DISABLE."""
    assert get_ssl_context(SSLMode.DISABLE) is None


def test_get_ssl_context_require_prefer_allow():
    """Non-verifying modes set CERT_NONE and check_hostname=False."""
    for mode in (SSLMode.REQUIRE, SSLMode.PREFER, SSLMode.ALLOW):
        ctx = get_ssl_context(mode)
        assert ctx is not None
        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_NONE


def test_get_ssl_context_verify_ca():
    """VERIFY_CA requires cert verification but doesn't check hostname."""
    ctx = get_ssl_context(SSLMode.VERIFY_CA)
    assert ctx is not None
    assert ctx.check_hostname is False
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_get_ssl_context_verify_full():
    """VERIFY_FULL requires cert verification and checks hostname."""
    ctx = get_ssl_context(SSLMode.VERIFY_FULL)
    assert ctx is not None
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_get_ssl_context_with_ca_cert(monkeypatch):
    """Loads CA verification locations when path provided."""
    mock_context = MagicMock()
    with patch("ssl.create_default_context", return_value=mock_context):
        ctx = get_ssl_context(SSLMode.VERIFY_CA, ca_cert_path="/path/to/ca.crt")
        assert ctx is mock_context
        mock_context.load_verify_locations.assert_called_once_with("/path/to/ca.crt")


def test_get_ssl_context_with_client_cert(monkeypatch):
    """Loads client cert chain when both cert and key paths are provided."""
    mock_context = MagicMock()
    with patch("ssl.create_default_context", return_value=mock_context):
        ctx = get_ssl_context(
            SSLMode.REQUIRE,
            client_cert_path="/path/to/client.crt",
            client_key_path="/path/to/client.key",
        )
        assert ctx is mock_context
        mock_context.load_cert_chain.assert_called_once_with(
            "/path/to/client.crt", "/path/to/client.key"
        )


def test_get_database_ssl_args_disable(monkeypatch):
    """DB_SSL_MODE=disable returns {'ssl': None}."""
    monkeypatch.setenv("DB_SSL_MODE", "disable")
    args = get_database_ssl_args()
    assert args == {"ssl": None}


def test_get_database_ssl_args_custom_mode(monkeypatch):
    """Returns ssl context dictionary for active SSL mode."""
    monkeypatch.setenv("DB_SSL_MODE", "verify-full")
    args = get_database_ssl_args()
    assert "ssl" in args
    assert isinstance(args["ssl"], ssl.SSLContext)
    assert args["ssl"].check_hostname is True


def test_get_database_ssl_args_invalid_fallback(monkeypatch):
    """Invalid DB_SSL_MODE falls back to prefer."""
    monkeypatch.setenv("DB_SSL_MODE", "nonexistent_mode")
    args = get_database_ssl_args()
    assert "ssl" in args
    assert isinstance(args["ssl"], ssl.SSLContext)
    assert args["ssl"].check_hostname is False


def test_get_asyncpg_ssl_args_disable(monkeypatch):
    """DB_SSL_MODE=disable returns {'ssl': False} for asyncpg."""
    monkeypatch.setenv("DB_SSL_MODE", "disable")
    args = get_asyncpg_ssl_args()
    assert args == {"ssl": False}


def test_get_asyncpg_ssl_args_enabled(monkeypatch):
    """Returns {'ssl': SSLContext} when enabled."""
    monkeypatch.setenv("DB_SSL_MODE", "require")
    args = get_asyncpg_ssl_args()
    assert "ssl" in args
    assert isinstance(args["ssl"], ssl.SSLContext)
