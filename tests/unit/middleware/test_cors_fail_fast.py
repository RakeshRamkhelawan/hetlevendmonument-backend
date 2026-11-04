"""Unit tests: CORS fail-fast validatie -- SEC-001 (ADR-035 D4).

Het combineren van allow_headers='*' met allow_credentials=True is een
ongeldige CORS configuratie (Fetch spec). staging-config had deze combinatie.

Rode tests -- test_staging en test_validate falen totdat
src/core/middleware/security_headers.py de staging-config fix + validate_cors_config()
bevat.
"""

import pytest


def test_staging_cors_does_not_combine_wildcard_headers_with_credentials() -> None:
    """SEC-001: staging CORS mag niet allow_headers='*' combineren met allow_credentials=True."""
    from src.core.middleware.security_headers import get_cors_config

    config = get_cors_config("staging")
    if config.get("allow_credentials"):
        assert config.get("allow_headers") != ["*"], (
            "staging: allow_headers=['*'] + allow_credentials=True is ongeldige CORS combinatie "
            "(Fetch spec). Gebruik expliciete header-namen."
        )


def test_validate_cors_config_raises_on_wildcard_headers_with_credentials() -> None:
    """SEC-001: validate_cors_config() gooit ValueError bij wildcard headers + credentials."""
    from src.core.middleware.security_headers import validate_cors_config

    with pytest.raises(ValueError, match="allow_headers"):
        validate_cors_config(
            {"allow_headers": ["*"], "allow_credentials": True},
            "staging",
        )


def test_validate_cors_config_accepts_explicit_headers_with_credentials() -> None:
    """SEC-001: expliciete headers + credentials is valide CORS config (geen exception)."""
    from src.core.middleware.security_headers import validate_cors_config

    validate_cors_config(
        {
            "allow_headers": ["Authorization", "Content-Type"],
            "allow_credentials": True,
        },
        "staging",
    )


def test_validate_cors_config_raises_on_wildcard_origins_in_production() -> None:
    """SEC-001: validate_cors_config() gooit ValueError bij wildcard origins in productie."""
    from src.core.middleware.security_headers import validate_cors_config

    with pytest.raises(ValueError):
        validate_cors_config(
            {"allow_origins": ["*"], "allow_credentials": False, "allow_headers": []},
            "production",
        )
