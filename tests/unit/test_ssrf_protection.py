"""
Unit tests for SSRF (Server-Side Request Forgery) Prevention Module
====================================================================

Tests comprehensive protection against SSRF attacks including:
- Private IP blocking (RFC 1918)
- Loopback address blocking
- Cloud metadata service blocking
- DNS rebinding protection
- URL scheme validation
- Port restriction enforcement

References:
- OWASP A10:2021 - Server-Side Request Forgery
- CWE-918: Server-Side Request Forgery (SSRF)
"""

import socket
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from src.core.security.ssrf_protection import (
    METADATA_SERVICE_HOSTNAMES,
    METADATA_SERVICE_IPS,
    SafeHttpUrl,
    SSRFConfig,
    SSRFProtector,
    SSRFValidationError,
    SSRFViolationType,
    get_default_protector,
    is_safe_ip,
    is_safe_url,
    validate_callback_url,
    validate_url,
)


# Helper to mock DNS resolution to return a specific IP
def mock_dns_to_ip(ip_list: List[str]):
    """Create a mock for DNS resolution returning specific IPs."""

    def _mock_resolve(hostname):
        return ip_list

    return _mock_resolve


class TestSSRFProtectorBasicValidation:
    """Test basic URL validation functionality."""

    def test_valid_https_url(self):
        """Test that valid HTTPS URLs pass validation."""
        protector = SSRFProtector()
        # Mock DNS to return a public IP
        with patch.object(protector, "_resolve_hostname", return_value=["93.184.216.34"]):
            url = "https://example.com/api/webhook"
            assert protector.validate_url(url) == url

    def test_valid_http_url(self):
        """Test that valid HTTP URLs pass validation."""
        protector = SSRFProtector()
        # Mock DNS to return a public IP
        with patch.object(protector, "_resolve_hostname", return_value=["93.184.216.34"]):
            url = "http://api.example.com/callback"
            assert protector.validate_url(url) == url

    def test_valid_url_with_path_and_query(self):
        """Test URL with path and query parameters."""
        protector = SSRFProtector()
        with patch.object(protector, "_resolve_hostname", return_value=["93.184.216.34"]):
            url = "https://example.com/api/v1/webhook?token=abc123&format=json"
            assert protector.validate_url(url) == url

    def test_valid_url_with_dns_resolution_failure(self):
        """Test that URL with DNS failure still passes basic validation."""
        protector = SSRFProtector()
        # DNS resolution fails (returns empty list)
        with patch.object(protector, "_resolve_hostname", return_value=[]):
            url = "https://example.com/api"
            # Should pass - DNS failures are allowed to let HTTP client handle it
            assert protector.validate_url(url) == url

    def test_invalid_scheme_file(self):
        """Test that file:// scheme is blocked."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url("file:///etc/passwd")
        assert exc_info.value.violation_type == SSRFViolationType.INVALID_SCHEME

    def test_invalid_scheme_gopher(self):
        """Test that gopher:// scheme is blocked."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url("gopher://localhost:25/")
        assert exc_info.value.violation_type == SSRFViolationType.INVALID_SCHEME

    def test_invalid_scheme_dict(self):
        """Test that dict:// scheme is blocked."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url("dict://localhost:11211/")
        assert exc_info.value.violation_type == SSRFViolationType.INVALID_SCHEME

    def test_invalid_scheme_ftp(self):
        """Test that ftp:// scheme is blocked by default."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url("ftp://ftp.example.com/file.txt")
        assert exc_info.value.violation_type == SSRFViolationType.INVALID_SCHEME

    def test_empty_url(self):
        """Test that empty URL raises error."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url("")
        # Empty string URL results in empty scheme, which triggers INVALID_SCHEME
        assert exc_info.value.violation_type in [
            SSRFViolationType.INVALID_URL,
            SSRFViolationType.INVALID_SCHEME,
        ]

    def test_url_without_hostname(self):
        """Test that URL without hostname raises error."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url("http:///path")
        assert exc_info.value.violation_type == SSRFViolationType.INVALID_URL


class TestSSRFProtectorPrivateIPBlocking:
    """Test blocking of private IP addresses (RFC 1918)."""

    @pytest.mark.parametrize(
        "ip",
        [
            "10.0.0.1",
            "10.255.255.255",
            "10.0.0.0",
        ],
    )
    def test_blocks_10_0_0_0_slash_8(self, ip: str):
        """Test blocking of 10.0.0.0/8 range."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url(f"http://{ip}/")
        assert exc_info.value.violation_type == SSRFViolationType.PRIVATE_IP

    @pytest.mark.parametrize(
        "ip",
        [
            "172.16.0.1",
            "172.31.255.255",
            "172.20.0.1",
        ],
    )
    def test_blocks_172_16_0_0_slash_12(self, ip: str):
        """Test blocking of 172.16.0.0/12 range."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url(f"http://{ip}/")
        assert exc_info.value.violation_type == SSRFViolationType.PRIVATE_IP

    @pytest.mark.parametrize(
        "ip",
        [
            "192.168.0.1",
            "192.168.1.1",
            "192.168.255.255",
        ],
    )
    def test_blocks_192_168_0_0_slash_16(self, ip: str):
        """Test blocking of 192.168.0.0/16 range."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url(f"http://{ip}/")
        assert exc_info.value.violation_type == SSRFViolationType.PRIVATE_IP

    def test_allows_private_ip_when_configured(self):
        """Test that private IPs are allowed with configuration."""
        config = SSRFConfig(allow_private_networks=True)
        protector = SSRFProtector(config)
        url = "http://192.168.1.1/"
        assert protector.validate_url(url) == url


class TestSSRFProtectorLoopbackBlocking:
    """Test blocking of loopback addresses."""

    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",
            "127.0.0.2",
            "127.255.255.255",
            "127.1.1.1",
        ],
    )
    def test_blocks_loopback_ips(self, ip: str):
        """Test blocking of 127.0.0.0/8 range."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url(f"http://{ip}/")
        assert exc_info.value.violation_type == SSRFViolationType.LOOPBACK

    def test_allows_loopback_when_configured(self):
        """Test that loopback is allowed with configuration."""
        config = SSRFConfig(allow_loopback=True)
        protector = SSRFProtector(config)
        url = "http://127.0.0.1/"
        assert protector.validate_url(url) == url

    def test_blocks_localhost_resolving_to_loopback(self):
        """Test blocking when 'localhost' resolves to loopback."""
        protector = SSRFProtector()
        # Mock DNS to return loopback
        with patch.object(protector, "_resolve_hostname", return_value=["127.0.0.1"]):
            with pytest.raises(SSRFValidationError) as exc_info:
                protector.validate_url("http://localhost/")
            assert exc_info.value.violation_type == SSRFViolationType.DNS_REBINDING


class TestSSRFProtectorMetadataServiceBlocking:
    """Test blocking of cloud metadata service endpoints."""

    @pytest.mark.parametrize("ip", sorted(METADATA_SERVICE_IPS))
    def test_blocks_metadata_service_ips(self, ip: str):
        """Test blocking of cloud metadata service IPs."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url(f"http://{ip}/")
        assert exc_info.value.violation_type == SSRFViolationType.METADATA_SERVICE

    def test_blocks_aws_metadata_endpoint(self):
        """Test blocking of AWS metadata endpoint."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url("http://169.254.169.254/latest/meta-data/")
        assert exc_info.value.violation_type == SSRFViolationType.METADATA_SERVICE

    def test_blocks_aws_metadata_with_credential_path(self):
        """Test blocking of AWS metadata IAM credential endpoint."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url(
                "http://169.254.169.254/latest/meta-data/iam/security-credentials/"
            )
        assert exc_info.value.violation_type == SSRFViolationType.METADATA_SERVICE

    @pytest.mark.parametrize("hostname", sorted(METADATA_SERVICE_HOSTNAMES))
    def test_blocks_metadata_hostnames(self, hostname: str):
        """Test blocking of cloud metadata service hostnames."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url(f"http://{hostname}/")
        assert exc_info.value.violation_type == SSRFViolationType.METADATA_SERVICE


class TestSSRFProtectorLinkLocalBlocking:
    """Test blocking of link-local addresses."""

    @pytest.mark.parametrize(
        "ip",
        [
            "169.254.0.1",
            "169.254.1.1",
            "169.254.255.254",
        ],
    )
    def test_blocks_link_local_ips(self, ip: str):
        """Test blocking of 169.254.0.0/16 range (except metadata)."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url(f"http://{ip}/")
        # Should be either LINK_LOCAL or METADATA_SERVICE
        assert exc_info.value.violation_type in [
            SSRFViolationType.LINK_LOCAL,
            SSRFViolationType.METADATA_SERVICE,
        ]


class TestSSRFProtectorPortRestrictions:
    """Test port restriction enforcement."""

    def test_allows_port_80(self):
        """Test that port 80 is allowed."""
        protector = SSRFProtector()
        url = "http://example.com:80/"
        assert protector.validate_url(url) == url

    def test_allows_port_443(self):
        """Test that port 443 is allowed."""
        protector = SSRFProtector()
        url = "https://example.com:443/"
        assert protector.validate_url(url) == url

    def test_allows_port_8080(self):
        """Test that port 8080 is allowed by default."""
        protector = SSRFProtector()
        url = "http://example.com:8080/"
        assert protector.validate_url(url) == url

    def test_blocks_non_standard_port(self):
        """Test that non-standard ports are blocked."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url("http://example.com:22/")
        assert exc_info.value.violation_type == SSRFViolationType.BLOCKED_PORT

    def test_blocks_redis_port(self):
        """Test that Redis port is blocked."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url("http://example.com:6379/")
        assert exc_info.value.violation_type == SSRFViolationType.BLOCKED_PORT

    def test_blocks_internal_service_ports(self):
        """Test that internal service ports are blocked."""
        protector = SSRFProtector()
        internal_ports = [3306, 5432, 27017, 11211, 9200]
        for port in internal_ports:
            with pytest.raises(SSRFValidationError) as exc_info:
                protector.validate_url(f"http://example.com:{port}/")
            assert exc_info.value.violation_type == SSRFViolationType.BLOCKED_PORT

    def test_custom_allowed_ports(self):
        """Test custom port whitelist."""
        config = SSRFConfig(allowed_ports=frozenset({80, 443, 9000}))
        protector = SSRFProtector(config)

        # Allowed port
        assert protector.validate_url("http://example.com:9000/") == "http://example.com:9000/"

        # Blocked port
        with pytest.raises(SSRFValidationError):
            protector.validate_url("http://example.com:8080/")


class TestSSRFProtectorDNSRebinding:
    """Test DNS rebinding protection."""

    def test_blocks_hostname_resolving_to_private_ip(self):
        """Test that hostname resolving to private IP is blocked."""
        protector = SSRFProtector()

        # Mock DNS resolution to return private IP
        with patch.object(protector, "_resolve_hostname", return_value=["10.0.0.1"]):
            with pytest.raises(SSRFValidationError) as exc_info:
                protector.validate_url("http://evil.example.com/")
            assert exc_info.value.violation_type == SSRFViolationType.DNS_REBINDING

    def test_blocks_hostname_resolving_to_loopback(self):
        """Test that hostname resolving to loopback is blocked."""
        protector = SSRFProtector()

        with patch.object(protector, "_resolve_hostname", return_value=["127.0.0.1"]):
            with pytest.raises(SSRFValidationError) as exc_info:
                protector.validate_url("http://localhost.evil.com/")
            assert exc_info.value.violation_type == SSRFViolationType.DNS_REBINDING

    def test_blocks_hostname_resolving_to_metadata(self):
        """Test that hostname resolving to metadata IP is blocked."""
        protector = SSRFProtector()

        with patch.object(protector, "_resolve_hostname", return_value=["169.254.169.254"]):
            with pytest.raises(SSRFValidationError) as exc_info:
                protector.validate_url("http://metadata.evil.com/")
            assert exc_info.value.violation_type == SSRFViolationType.DNS_REBINDING

    def test_allows_hostname_resolving_to_public_ip(self):
        """Test that hostname resolving to public IP is allowed."""
        protector = SSRFProtector()

        with patch.object(protector, "_resolve_hostname", return_value=["93.184.216.34"]):
            url = "http://example.com/"
            assert protector.validate_url(url) == url

    def test_allows_hostname_with_dns_failure(self):
        """Test that hostname with DNS failure is allowed (HTTP client handles)."""
        protector = SSRFProtector()

        with patch.object(protector, "_resolve_hostname", return_value=[]):
            url = "http://unknown-host.example.com/"
            # Should pass - let HTTP client handle the DNS failure
            assert protector.validate_url(url) == url


class TestSSRFProtectorReservedRanges:
    """Test blocking of reserved IP ranges."""

    @pytest.mark.parametrize(
        "ip",
        [
            "0.0.0.1",  # Current network
            "100.64.0.1",  # Carrier-grade NAT
            "192.0.2.1",  # TEST-NET-1
            "198.51.100.1",  # TEST-NET-2
            "203.0.113.1",  # TEST-NET-3
            "240.0.0.1",  # Reserved for future use
        ],
    )
    def test_blocks_reserved_ranges(self, ip: str):
        """Test blocking of reserved IP ranges."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url(f"http://{ip}/")
        assert exc_info.value.violation_type == SSRFViolationType.RESERVED

    def test_blocks_multicast_addresses(self):
        """Test blocking of multicast addresses."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url("http://224.0.0.1/")
        assert exc_info.value.violation_type == SSRFViolationType.MULTICAST


class TestSSRFProtectorIPv6:
    """Test IPv6 address validation."""

    def test_blocks_ipv6_loopback(self):
        """Test blocking of IPv6 loopback."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url("http://[::1]/")
        assert exc_info.value.violation_type == SSRFViolationType.LOOPBACK

    def test_blocks_ipv6_unique_local(self):
        """Test blocking of IPv6 unique local addresses."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url("http://[fd00::1]/")
        assert exc_info.value.violation_type == SSRFViolationType.PRIVATE_IP

    def test_blocks_ipv6_link_local(self):
        """Test blocking of IPv6 link-local addresses."""
        protector = SSRFProtector()
        with pytest.raises(SSRFValidationError) as exc_info:
            protector.validate_url("http://[fe80::1]/")
        assert exc_info.value.violation_type == SSRFViolationType.LINK_LOCAL


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_validate_url_function(self):
        """Test validate_url convenience function."""
        # Valid URL with direct IP (public)
        # Use an IP that's not in blocked ranges
        url = validate_url("http://93.184.216.34/")
        assert url == "http://93.184.216.34/"

        # Invalid URL (loopback)
        with pytest.raises(SSRFValidationError):
            validate_url("http://127.0.0.1/")

    def test_validate_url_with_options(self):
        """Test validate_url with configuration options."""
        # Allow loopback
        url = validate_url("http://127.0.0.1/", allow_loopback=True)
        assert url == "http://127.0.0.1/"

        # Custom ports - use IP to avoid DNS
        url = validate_url("http://93.184.216.34:9000/", allowed_ports={80, 443, 9000})
        assert url == "http://93.184.216.34:9000/"

    def test_is_safe_url_function(self):
        """Test is_safe_url convenience function."""
        # Direct IP tests (avoid DNS resolution)
        assert is_safe_url("http://93.184.216.34/") is True  # Public IP
        assert is_safe_url("http://127.0.0.1/") is False  # Loopback
        assert is_safe_url("http://169.254.169.254/") is False  # Metadata
        assert is_safe_url("http://10.0.0.1/") is False  # Private

    def test_is_safe_ip_function(self):
        """Test is_safe_ip convenience function."""
        assert is_safe_ip("93.184.216.34") is True  # Public IP
        assert is_safe_ip("127.0.0.1") is False  # Loopback
        assert is_safe_ip("10.0.0.1") is False  # Private
        assert is_safe_ip("169.254.169.254") is False  # Metadata

    def test_validate_callback_url_function(self):
        """Test validate_callback_url function."""
        # Valid URL with public IP
        result = validate_callback_url("http://93.184.216.34/webhook")
        assert result == "http://93.184.216.34/webhook"

        # Invalid URL returns None
        result = validate_callback_url("http://127.0.0.1/")
        assert result is None

        # Empty/None returns None
        assert validate_callback_url(None) is None
        assert validate_callback_url("") is None

    def test_get_default_protector(self):
        """Test get_default_protector returns singleton."""
        p1 = get_default_protector()
        p2 = get_default_protector()
        assert p1 is p2


class TestSSRFValidationError:
    """Test SSRFValidationError class."""

    def test_error_contains_violation_type(self):
        """Test that error contains violation type."""
        error = SSRFValidationError(
            url="http://127.0.0.1/",
            violation_type=SSRFViolationType.LOOPBACK,
            message="Loopback address blocked",
        )
        assert error.violation_type == SSRFViolationType.LOOPBACK
        assert "LOOPBACK" in str(error).upper() or "loopback" in str(error)

    def test_error_sanitizes_credentials(self):
        """Test that error sanitizes credentials in URL."""
        error = SSRFValidationError(
            url="http://user:secretpassword@example.com/",
            violation_type=SSRFViolationType.PRIVATE_IP,
            message="Test error",
        )
        error_str = str(error)
        assert "secretpassword" not in error_str
        assert "***" in error_str


class TestSSRFConfig:
    """Test SSRFConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SSRFConfig()
        assert "http" in config.allowed_schemes
        assert "https" in config.allowed_schemes
        assert config.allow_private_networks is False
        assert config.allow_loopback is False
        assert config.allow_link_local is False
        assert config.allow_metadata_services is False
        assert config.enable_dns_rebinding_protection is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = SSRFConfig(
            allowed_schemes=frozenset({"https"}),
            allowed_ports=frozenset({443}),
            allow_private_networks=True,
            blocked_hostnames=frozenset({"blocked.example.com"}),
        )
        assert config.allowed_schemes == frozenset({"https"})
        assert config.allowed_ports == frozenset({443})
        assert config.allow_private_networks is True
        assert "blocked.example.com" in config.blocked_hostnames

    def test_config_immutability(self):
        """Test that config is immutable (frozen dataclass)."""
        config = SSRFConfig()
        with pytest.raises(Exception):  # FrozenInstanceError
            config.allow_loopback = True


class TestSafeHttpUrlPydanticModel:
    """Test SafeHttpUrl Pydantic model."""

    def test_valid_url_passes(self):
        """Test that valid URL passes validation."""
        # Use IP address to avoid DNS resolution
        model = SafeHttpUrl(url="http://93.184.216.34/webhook")
        assert model.url == "http://93.184.216.34/webhook"

    def test_private_ip_fails(self):
        """Test that private IP fails validation."""
        with pytest.raises(Exception):  # ValidationError
            SafeHttpUrl(url="http://192.168.1.1/")

    def test_loopback_fails(self):
        """Test that loopback fails validation."""
        with pytest.raises(Exception):  # ValidationError
            SafeHttpUrl(url="http://127.0.0.1/")


class TestIntegrationScenarios:
    """Integration tests for real-world SSRF attack scenarios."""

    def test_blocks_ssrf_via_redirect_target(self):
        """Test blocking of potential redirect targets."""
        # These are common SSRF attack targets - all use direct IPs
        attack_urls = [
            "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
            "http://127.0.0.1:22/",
            "http://127.0.0.1:6379/",
            "http://10.0.0.1:8080/admin",
            "file:///etc/passwd",
            "gopher://127.0.0.1:25/_MAIL",
        ]

        for url in attack_urls:
            assert not is_safe_url(url), f"Should block: {url}"

    def test_allows_legitimate_public_ips(self):
        """Test that legitimate public IPs are allowed."""
        # Use direct public IPs to avoid DNS
        legitimate_urls = [
            "http://93.184.216.34/",  # example.com's IP
            "https://8.8.8.8/",  # Google DNS (as example)
            "http://104.21.0.1/",  # Cloudflare range
        ]

        for url in legitimate_urls:
            assert is_safe_url(url), f"Should allow: {url}"

    def test_blocks_encoded_attacks(self):
        """Test blocking of various attack attempts."""
        # Direct IP attacks
        assert not is_safe_url("http://127.0.0.1/")
        assert not is_safe_url("http://10.0.0.1/")
        assert not is_safe_url("http://192.168.1.1/")


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_handles_malformed_urls_gracefully(self):
        """Test that malformed URLs are handled gracefully."""
        protector = SSRFProtector()

        malformed_urls = [
            "not-a-url",
            "://missing-scheme.com",
            "http://",
            "http:///no-host",
        ]

        for url in malformed_urls:
            # Should raise SSRFValidationError, not crash
            with pytest.raises(SSRFValidationError):
                protector.validate_url(url)

    def test_boundary_ips_in_ranges(self):
        """Test boundary IPs at edge of blocked ranges."""
        protector = SSRFProtector()

        # First IP in private range (should be blocked)
        with pytest.raises(SSRFValidationError):
            protector.validate_url("http://10.0.0.0/")

        # Last IP in private range (should be blocked)
        with pytest.raises(SSRFValidationError):
            protector.validate_url("http://10.255.255.255/")

        # First IP in 172.16.0.0/12 range
        with pytest.raises(SSRFValidationError):
            protector.validate_url("http://172.16.0.0/")

        # Last IP in 172.16.0.0/12 range
        with pytest.raises(SSRFValidationError):
            protector.validate_url("http://172.31.255.255/")

        # First IP in 192.168.0.0/16 range
        with pytest.raises(SSRFValidationError):
            protector.validate_url("http://192.168.0.0/")

        # Last IP in 192.168.0.0/16 range
        with pytest.raises(SSRFValidationError):
            protector.validate_url("http://192.168.255.255/")

    def test_public_ip_boundaries(self):
        """Test IPs just outside private ranges are allowed."""
        protector = SSRFProtector()

        # Just above 172.31.255.255 (end of 172.16.0.0/12)
        # 172.32.0.0 should be allowed (not in private range)
        url = "http://172.32.0.1/"
        assert protector.validate_url(url) == url

        # Just below 172.16.0.0 (start of 172.16.0.0/12)
        # 172.15.255.255 should be allowed
        url = "http://172.15.255.255/"
        assert protector.validate_url(url) == url


def test_de_standaard_tijdslimiet_van_het_proces_blijft_zoals_hij_was() -> None:
    """De opzoeking mag de instelling van een ANDERE bibliotheek niet wissen (BE-LLM-004).

    `_resolve_hostname` zet een tijdslimiet voor de duur van de opzoeking. De `finally` zette
    die daarna op `None` -- en dat is geen herstel maar "geen limiet meer", procesbreed, voor
    elke socket van elke andere gebruiker in hetzelfde proces. Zolang deze controle alleen bij
    het inrichten draaide viel dat niet op; sinds fase 2b draait hij op het verzoekpad van
    elke agent.

    Een test die dit afdwingt kan alleen hier staan: het neveneffect is onzichtbaar in de
    uitkomst van de functie zelf.
    """
    protector = SSRFProtector()
    vorige = socket.getdefaulttimeout()
    socket.setdefaulttimeout(12.5)
    try:
        protector._resolve_hostname("een-naam-die-niet-bestaat.invalid")
        assert socket.getdefaulttimeout() == 12.5, (
            "de standaard tijdslimiet van het proces is gewijzigd door een DNS-opzoeking"
        )
    finally:
        socket.setdefaulttimeout(vorige)


def test_de_globale_tijdslimiet_wordt_onder_een_slot_verzet() -> None:
    """Twee draden mogen elkaars TIJDELIJKE waarde niet als "de vorige" lezen.

    `_resolve_hostname` doet save/set/restore op `socket.setdefaulttimeout` -- een PROCESBREDE
    waarde. Sinds BE-LLM-004 draait die functie via `asyncio.to_thread` op het verzoekpad, dus
    gelijktijdig. Zonder slot:

        draad A: vorige=None ; zet(5.0)
        draad B: vorige=5.0  ; zet(5.0)
        draad A: herstel(None)
        draad B: herstel(5.0)   -> het proces staat permanent op 5,0

    **Waarom deze test geen twee draden gebruikt.** Een test die op een interleaving hoopt is
    flaky, en dit project verbiedt flaky tests. De invariant is scherper te stellen: op het
    moment dat de globale gewijzigd IS (dus tijdens de opzoeking), moet het slot vastzitten.
    Dat is deterministisch en sterft zodra iemand het slot weghaalt of eromheen werkt.
    """
    from src.core.security import ssrf_protection

    protector = SSRFProtector()
    gezien: list[bool] = []

    def _nep_getaddrinfo(*_args: object, **_kwargs: object) -> list[object]:
        gezien.append(ssrf_protection._DNS_TIJDSLIMIET_SLOT.locked())
        raise socket.gaierror("geen antwoord, deze test meet alleen het slot")

    with patch.object(socket, "getaddrinfo", _nep_getaddrinfo):
        protector._resolve_hostname("een-naam.invalid")

    assert gezien == [True], (
        "de procesbrede tijdslimiet wordt gewijzigd zonder dat het slot vastzit; twee "
        "gelijktijdige opzoekingen kunnen elkaars tijdelijke waarde als 'de vorige' lezen"
    )
