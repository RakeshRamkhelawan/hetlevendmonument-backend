"""
Unit tests for Foundation Portal rate limiter wrappers (Task 7).

Covers: _ip_key, _email_key, all 6 decorators are callable,
no client-controlled header fallback.
"""

from __future__ import annotations

import pytest
from fastapi import Request

from src.core.governance.rate_limiter import (
    _email_key,
    _ip_key,
    portal_auth_limit,
    portal_magic_link_email_limit,
    portal_newsletter_limit,
    portal_public_read_limit,
    portal_public_write_limit,
    portal_takedown_limit,
)


class TestIpKey:
    @pytest.mark.unit
    def test_xff_first_value(self) -> None:
        """X-Forwarded-For is client, proxy1, proxy2, ...; the first value is the real client.

        Taking the last value picks the nearest proxy's own address instead (e.g. Traefik),
        which is identical for every request behind it and defeats per-client rate limiting.
        When behind a trusted proxy (private IP), XFF is trusted; direct client access
        ignores XFF to prevent spoofing (GHSA-c2r5-cfqr-c553).
        """
        req = Request(
            scope={  # type: ignore[arg-type]
                "type": "http",
                "headers": [
                    (b"x-forwarded-for", b"203.0.113.1, 10.0.0.1"),
                ],
                "client": ("10.0.0.1", 12345),  # Trusted proxy (private IP)
            }
        )
        assert _ip_key(req) == "ip:203.0.113.1"

    @pytest.mark.unit
    def test_client_host_fallback(self) -> None:
        req = Request(
            scope={  # type: ignore[arg-type]
                "type": "http",
                "headers": [],
                "client": ("192.0.2.1", 12345),
            }
        )
        assert _ip_key(req) == "ip:192.0.2.1"

    @pytest.mark.unit
    def test_unknown_fallback(self) -> None:
        req = Request(
            scope={"type": "http", "headers": []}  # type: ignore[arg-type]
        )
        assert _ip_key(req) == "ip:unknown"


class TestEmailKey:
    @pytest.mark.unit
    def test_parsed_email(self) -> None:
        req = Request(
            scope={"type": "http", "headers": []}  # type: ignore[arg-type]
        )
        req.state.parsed_email = "User@Example.COM"
        assert _email_key(req) == "email:user@example.com"

    @pytest.mark.unit
    def test_missing_parsed_email_includes_ip(self) -> None:
        req = Request(
            scope={"type": "http", "headers": [], "client": ("192.0.2.1", 12345)}  # type: ignore[arg-type]
        )
        key = _email_key(req)
        assert key.startswith("email:unknown:")
        assert "192.0.2.1" in key

    @pytest.mark.unit
    def test_empty_parsed_email(self) -> None:
        req = Request(
            scope={"type": "http", "headers": [], "client": ("192.0.2.1", 12345)}  # type: ignore[arg-type]
        )
        req.state.parsed_email = ""
        key = _email_key(req)
        assert key.startswith("email:unknown:")


class TestRateLimiterDecorators:
    @pytest.mark.unit
    @pytest.mark.parametrize(
        "decorator",
        [
            portal_public_read_limit,
            portal_public_write_limit,
            portal_auth_limit,
            portal_magic_link_email_limit,
            portal_takedown_limit,
            portal_newsletter_limit,
        ],
    )
    def test_all_decorators_are_callable(self, decorator) -> None:
        @decorator
        async def dummy(request: Request) -> str:
            return "ok"

        assert callable(dummy)
