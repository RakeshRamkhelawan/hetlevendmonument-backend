"""
SSRF (Server-Side Request Forgery) Prevention Module
=====================================================

Provides comprehensive protection against SSRF attacks (OWASP A10:2021).

SSRF attacks trick the server into making requests to internal network
resources, cloud metadata services, or other unintended destinations.

Protection Mechanisms:
----------------------
1. IP Address Validation
   - Block private IP ranges (RFC 1918)
   - Block loopback addresses (127.0.0.0/8)
   - Block link-local addresses (169.254.0.0/16)
   - Block cloud metadata services (169.254.169.254)
   - Block multicast and reserved ranges

2. DNS Rebinding Protection
   - Resolve hostname before connection
   - Validate resolved IP against blocklist
   - Cache validated resolutions

3. URL Scheme Validation
   - Only allow http/https schemes
   - Block file://, gopher://, dict://, etc.

4. Port Restrictions
   - Only allow standard HTTP ports (80, 443) by default
   - Configurable port whitelist

Usage:
------
    from src.core.security.ssrf_protection import (
        SSRFProtector,
        validate_url,
        is_safe_url,
        SSRFValidationError,
    )

    # Simple validation
    if is_safe_url("https://example.com/api"):
        # Safe to request
        pass

    # With callback URL validation
    validated_url = validate_url(
        user_provided_url,
        allow_internal=False,
        allowed_ports=[80, 443, 8080]
    )

    # Using the protector class
    protector = SSRFProtector()
    try:
        safe_url = protector.validate_and_resolve(callback_url)
    except SSRFValidationError as e:
        logger.warning(f"SSRF attempt blocked: {e}")

References:
-----------
- OWASP A10:2021 - Server-Side Request Forgery
- CWE-918: Server-Side Request Forgery (SSRF)
- RFC 1918: Private IP Address Space
- AWS/GCP/Azure Metadata Service Documentation
"""

import ipaddress
import logging
import socket
import threading
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

#: Beschermt de PROCESBREDE standaard-tijdslimiet van sockets tijdens een naamsopzoeking.
#:
#: `_resolve_hostname` doet "opslaan, zetten, terugzetten" op `socket.setdefaulttimeout`, en dat
#: is een globale. Zolang die functie op een enkele draad liep was dat onzichtbaar; sinds
#: BE-LLM-004 draait hij via `asyncio.to_thread` op de verzoekweg van elke agent, dus twee
#: taken kunnen hem gelijktijdig uitvoeren:
#:
#:     draad A: vorige=None ; zet(5.0)
#:     draad B: vorige=5.0  ; zet(5.0)      <- leest de TIJDELIJKE waarde van A als "de vorige"
#:     draad A: herstel(None)
#:     draad B: herstel(5.0)                <- het proces staat nu permanent op 5,0
#:
#: Dat is een verloren-update op een globale, en geen enkele single-threaded test kan hem zien.
#: De prijs van dit slot is dat opzoekingen serieel worden; met de cache erboven is dat in de
#: praktijk milliseconden, en het alternatief (de globale helemaal niet meer aanraken) kost de
#: synchrone aanroepers hun tijdslimiet.
_DNS_TIJDSLIMIET_SLOT = threading.Lock()


class SSRFViolationType(str, Enum):
    """Types of SSRF violations detected."""

    PRIVATE_IP = "private_ip"
    LOOPBACK = "loopback"
    LINK_LOCAL = "link_local"
    METADATA_SERVICE = "metadata_service"
    MULTICAST = "multicast"
    RESERVED = "reserved"
    INVALID_SCHEME = "invalid_scheme"
    BLOCKED_PORT = "blocked_port"
    DNS_REBINDING = "dns_rebinding"
    HOSTNAME_RESOLUTION_FAILED = "hostname_resolution_failed"
    INVALID_URL = "invalid_url"
    BLOCKED_HOSTNAME = "blocked_hostname"


class SSRFValidationError(Exception):
    """
    Exception raised when SSRF protection detects a potentially malicious URL.

    Attributes:
        url: The URL that failed validation
        violation_type: The type of SSRF violation detected
        message: Human-readable error message
    """

    def __init__(
        self,
        url: str,
        violation_type: SSRFViolationType,
        message: str,
    ) -> None:
        self.url = url
        self.violation_type = violation_type
        self.message = message
        super().__init__(
            f"SSRF blocked: {message} (type={violation_type.value}, url={self._sanitize_url(url)})"
        )

    @staticmethod
    def _sanitize_url(url: str) -> str:
        """Sanitize URL for logging (remove credentials)."""
        try:
            parsed = urlparse(url)
            # Remove password from URL for logging
            if parsed.password:
                sanitized = url.replace(f":{parsed.password}@", ":***@")
                return sanitized
            return url[:100] + "..." if len(url) > 100 else url
        except Exception:
            return "<invalid-url>"


@dataclass(frozen=True)
class SSRFConfig:
    """
    Configuration for SSRF protection.

    Attributes:
        allowed_schemes: URL schemes that are allowed (default: http, https)
        allowed_ports: Ports that are allowed (None = only 80/443)
        allow_private_networks: Allow requests to private IP ranges
        allow_loopback: Allow requests to localhost/127.x.x.x
        allow_link_local: Allow requests to link-local addresses
        allow_metadata_services: Allow requests to cloud metadata services
        blocked_hostnames: Additional hostnames to block
        dns_resolution_timeout: Timeout for DNS resolution (seconds)
        enable_dns_rebinding_protection: Resolve and validate IPs before request
    """

    allowed_schemes: frozenset[str] = field(default_factory=lambda: frozenset({"http", "https"}))
    allowed_ports: frozenset[int] | None = field(
        default_factory=lambda: frozenset({80, 443, 8080, 8443})
    )
    allow_private_networks: bool = False
    allow_loopback: bool = False
    allow_link_local: bool = False
    allow_metadata_services: bool = False
    blocked_hostnames: frozenset[str] = field(default_factory=frozenset)
    dns_resolution_timeout: float = 5.0
    enable_dns_rebinding_protection: bool = True


# Cloud metadata service IPs and hostnames
METADATA_SERVICE_IPS: frozenset[str] = frozenset(
    {
        "169.254.169.254",  # AWS, GCP, Azure, DigitalOcean
        "100.100.100.200",  # Alibaba Cloud
        "192.0.0.192",  # Oracle Cloud
    }
)

METADATA_SERVICE_HOSTNAMES: frozenset[str] = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
        "kubernetes.default.svc",
        "kubernetes.default",
    }
)

# Private IP ranges (RFC 1918 + others)
PRIVATE_IP_NETWORKS: tuple[ipaddress.IPv4Network, ...] = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)

# Other blocked ranges
LOOPBACK_NETWORK = ipaddress.IPv4Network("127.0.0.0/8")
LINK_LOCAL_NETWORK = ipaddress.IPv4Network("169.254.0.0/16")
MULTICAST_NETWORK = ipaddress.IPv4Network("224.0.0.0/4")

# Reserved/special ranges
RESERVED_NETWORKS: tuple[ipaddress.IPv4Network, ...] = (
    ipaddress.IPv4Network("0.0.0.0/8"),  # Current network
    ipaddress.IPv4Network("100.64.0.0/10"),  # Carrier-grade NAT
    ipaddress.IPv4Network("192.0.0.0/24"),  # IETF Protocol Assignments
    ipaddress.IPv4Network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.IPv4Network("198.18.0.0/15"),  # Network Interconnect Testing
    ipaddress.IPv4Network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.IPv4Network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.IPv4Network("240.0.0.0/4"),  # Reserved for future use
    ipaddress.IPv4Network("255.255.255.255/32"),  # Broadcast
)

# IPv6 blocked ranges
IPV6_BLOCKED_NETWORKS: tuple[ipaddress.IPv6Network, ...] = (
    ipaddress.IPv6Network("::1/128"),  # Loopback
    ipaddress.IPv6Network("::ffff:0:0/96"),  # IPv4-mapped
    ipaddress.IPv6Network("fc00::/7"),  # Unique local
    ipaddress.IPv6Network("fe80::/10"),  # Link-local
    ipaddress.IPv6Network("ff00::/8"),  # Multicast
)


class SSRFProtector:
    """
    Main SSRF protection class.

    Validates URLs and IP addresses against security policies to prevent
    Server-Side Request Forgery attacks.

    Example:
        protector = SSRFProtector()

        # Validate a user-provided callback URL
        try:
            safe_url = protector.validate_url("https://webhook.example.com/callback")
            # URL is safe to use
        except SSRFValidationError as e:
            logger.warning(f"Blocked SSRF attempt: {e}")
    """

    def __init__(self, config: SSRFConfig | None = None) -> None:
        """
        Initialize SSRF protector with configuration.

        Args:
            config: SSRFConfig instance (uses defaults if None)
        """
        self.config = config or SSRFConfig()
        self._resolved_cache: dict[str, list[str]] = {}

    def validate_url(self, url: str) -> str:
        """
        Validate a URL against SSRF protection rules.

        Args:
            url: The URL to validate

        Returns:
            The validated URL (unchanged if valid)

        Raises:
            SSRFValidationError: If the URL fails validation
        """
        # Parse URL
        try:
            parsed = urlparse(url)
        except Exception as e:
            raise SSRFValidationError(
                url=url,
                violation_type=SSRFViolationType.INVALID_URL,
                message=f"Failed to parse URL: {e}",
            )

        # Validate scheme
        if parsed.scheme.lower() not in self.config.allowed_schemes:
            raise SSRFValidationError(
                url=url,
                violation_type=SSRFViolationType.INVALID_SCHEME,
                message=f"Scheme '{parsed.scheme}' not allowed. Allowed: {self.config.allowed_schemes}",
            )

        # Validate port
        port = parsed.port
        if port is None:
            # Use default ports for scheme
            port = 443 if parsed.scheme.lower() == "https" else 80

        if self.config.allowed_ports and port not in self.config.allowed_ports:
            raise SSRFValidationError(
                url=url,
                violation_type=SSRFViolationType.BLOCKED_PORT,
                message=f"Port {port} not allowed. Allowed: {self.config.allowed_ports}",
            )

        # Get hostname
        hostname = parsed.hostname
        if not hostname:
            raise SSRFValidationError(
                url=url,
                violation_type=SSRFViolationType.INVALID_URL,
                message="URL has no hostname",
            )

        # Check blocked hostnames
        hostname_lower = hostname.lower()
        if hostname_lower in self.config.blocked_hostnames:
            raise SSRFValidationError(
                url=url,
                violation_type=SSRFViolationType.BLOCKED_HOSTNAME,
                message=f"Hostname '{hostname}' is blocked",
            )

        # Check metadata service hostnames
        if not self.config.allow_metadata_services:
            if hostname_lower in METADATA_SERVICE_HOSTNAMES:
                raise SSRFValidationError(
                    url=url,
                    violation_type=SSRFViolationType.METADATA_SERVICE,
                    message=f"Access to cloud metadata service hostname '{hostname}' is blocked",
                )

        # Check if hostname is an IP address
        try:
            ip = ipaddress.ip_address(hostname)
            self._validate_ip_address(ip, url)
        except ValueError:
            # Not an IP address, resolve hostname if DNS rebinding protection enabled
            if self.config.enable_dns_rebinding_protection:
                self._validate_hostname_resolution(hostname, url)

        return url

    def validate_and_resolve(self, url: str) -> tuple[str, list[str]]:
        """
        Validate URL and return resolved IP addresses.

        Args:
            url: The URL to validate

        Returns: Tuple[Any, ...] of (validated_url, list_of_resolved_ips)  # TODO(TYPE): replace Any with concrete type

        Raises:
            SSRFValidationError: If the URL fails validation
        """
        validated_url = self.validate_url(url)
        parsed = urlparse(validated_url)
        hostname = parsed.hostname

        if not hostname:
            return validated_url, []

        # Check if already an IP
        try:
            ip = ipaddress.ip_address(hostname)
            return validated_url, [str(ip)]
        except ValueError:
            pass

        # Resolve hostname
        resolved_ips = self._resolve_hostname(hostname)
        return validated_url, resolved_ips

    def _validate_ip_address(
        self,
        ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
        url: str,
    ) -> None:
        """
        Validate an IP address against security policies.

        Args:
            ip: The IP address to validate
            url: Original URL (for error reporting)

        Raises:
            SSRFValidationError: If the IP address fails validation
        """
        ip_str = str(ip)

        # Check metadata service IPs first (highest priority block)
        if not self.config.allow_metadata_services:
            if ip_str in METADATA_SERVICE_IPS:
                raise SSRFValidationError(
                    url=url,
                    violation_type=SSRFViolationType.METADATA_SERVICE,
                    message=f"Access to cloud metadata service IP '{ip_str}' is blocked",
                )

        if isinstance(ip, ipaddress.IPv4Address):
            self._validate_ipv4(ip, url)
        else:
            self._validate_ipv6(ip, url)

    def _validate_ipv4(self, ip: ipaddress.IPv4Address, url: str) -> None:
        """Validate IPv4 address."""
        # Loopback check
        if not self.config.allow_loopback and ip in LOOPBACK_NETWORK:
            raise SSRFValidationError(
                url=url,
                violation_type=SSRFViolationType.LOOPBACK,
                message=f"Loopback address '{ip}' is blocked",
            )

        # Private networks check
        if not self.config.allow_private_networks:
            for network in PRIVATE_IP_NETWORKS:
                if ip in network:
                    raise SSRFValidationError(
                        url=url,
                        violation_type=SSRFViolationType.PRIVATE_IP,
                        message=f"Private IP address '{ip}' in {network} is blocked",
                    )

        # Link-local check
        if not self.config.allow_link_local and ip in LINK_LOCAL_NETWORK:
            raise SSRFValidationError(
                url=url,
                violation_type=SSRFViolationType.LINK_LOCAL,
                message=f"Link-local address '{ip}' is blocked",
            )

        # Multicast check
        if ip in MULTICAST_NETWORK:
            raise SSRFValidationError(
                url=url,
                violation_type=SSRFViolationType.MULTICAST,
                message=f"Multicast address '{ip}' is blocked",
            )

        # Reserved ranges check
        for network in RESERVED_NETWORKS:
            if ip in network:
                raise SSRFValidationError(
                    url=url,
                    violation_type=SSRFViolationType.RESERVED,
                    message=f"Reserved IP address '{ip}' in {network} is blocked",
                )

    def _validate_ipv6(self, ip: ipaddress.IPv6Address, url: str) -> None:
        """Validate IPv6 address."""
        for network in IPV6_BLOCKED_NETWORKS:
            if ip in network:
                # Determine violation type
                if network == ipaddress.IPv6Network("::1/128"):
                    violation_type = SSRFViolationType.LOOPBACK
                elif network == ipaddress.IPv6Network("fc00::/7"):
                    violation_type = SSRFViolationType.PRIVATE_IP
                elif network == ipaddress.IPv6Network("fe80::/10"):
                    violation_type = SSRFViolationType.LINK_LOCAL
                elif network == ipaddress.IPv6Network("ff00::/8"):
                    violation_type = SSRFViolationType.MULTICAST
                else:
                    violation_type = SSRFViolationType.RESERVED

                raise SSRFValidationError(
                    url=url,
                    violation_type=violation_type,
                    message=f"IPv6 address '{ip}' in blocked range {network}",
                )

    def _resolve_hostname(self, hostname: str) -> list[str]:
        """
        Resolve hostname to IP addresses.

        Args:
            hostname: The hostname to resolve

        Returns: List[Any] of resolved IP addresses  # TODO(TYPE): replace Any with concrete type

        **De vorige waarde van de standaardtijdslimiet wordt hersteld (2026-09-23).** Hier stond
        `socket.setdefaulttimeout(None)` in de `finally`, en dat is geen herstel maar een WIS:
        `None` betekent "geen limiet", terwijl een andere bibliotheek in hetzelfde proces er een
        ingesteld kan hebben. Deze functie zette dus stil de instelling van een ander terug op
        oneindig -- een neveneffect dat procesbreed is en nergens te zien. Zolang deze controle
        alleen bij het inrichten draaide viel dat niet op; sinds BE-LLM-004 draait hij op het
        verzoekpad van elke agent.
        """
        # Check cache
        if hostname in self._resolved_cache:
            return self._resolved_cache[hostname]

        with _DNS_TIJDSLIMIET_SLOT:
            vorige_limiet = socket.getdefaulttimeout()
            try:
                # Set timeout for DNS resolution
                socket.setdefaulttimeout(self.config.dns_resolution_timeout)
                results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                ips: list[str] = [str(result[4][0]) for result in results]
                # `sorted(set(...))` en NIET `list(set(...))`: de volgorde van een set hangt af
                # van de hash-seed, die per PROCES verschilt. Zolang alleen gecontroleerd werd
                # of elk adres deugde, maakte de volgorde niets uit. Sinds BE-LLM-004 pint de
                # aanroeper zich vast op het EERSTE adres, en dan kiest worker 1 een ander
                # adres dan worker 3 -- en na een herstart weer anders. Een storing die per
                # worker verschilt en er als flakiness uitziet, is het duurste soort.
                ips = sorted(set(ips))
                self._resolved_cache[hostname] = ips
                return ips
            except socket.gaierror as e:
                logger.warning("DNS resolution failed for '%s': %s", hostname, e)
                return []
            finally:
                socket.setdefaulttimeout(vorige_limiet)

    def _validate_hostname_resolution(self, hostname: str, url: str) -> None:
        """
        Resolve hostname and validate all resolved IPs.

        Args:
            hostname: The hostname to resolve and validate
            url: Original URL (for error reporting)

        Raises:
            SSRFValidationError: If any resolved IP is blocked

        Note:
            DNS resolution failures are logged but don't block the request
            to avoid blocking valid external services during DNS hiccups.
            The actual HTTP client will fail if the hostname is truly invalid.
        """
        resolved_ips = self._resolve_hostname(hostname)

        if not resolved_ips:
            # DNS resolution failed - log warning but allow
            # The HTTP client will handle truly invalid hostnames
            logger.debug(
                "DNS resolution returned no results for '%s', "
                "allowing request (HTTP client will validate)",
                hostname,
            )
            return

        # Validate all resolved IPs
        for ip_str in resolved_ips:
            try:
                ip = ipaddress.ip_address(ip_str)
                self._validate_ip_address(ip, url)
            except SSRFValidationError:
                # Re-raise with DNS rebinding context
                raise SSRFValidationError(
                    url=url,
                    violation_type=SSRFViolationType.DNS_REBINDING,
                    message=f"Hostname '{hostname}' resolves to blocked IP '{ip_str}'",
                )


# Default protector instance
_default_protector: SSRFProtector | None = None


def get_default_protector() -> SSRFProtector:
    """Get or create default SSRF protector instance."""
    global _default_protector
    if _default_protector is None:
        _default_protector = SSRFProtector()
    return _default_protector


def validate_url(
    url: str,
    *,
    allow_private_networks: bool = False,
    allow_loopback: bool = False,
    allowed_ports: set[int] | None = None,
) -> str:
    """
    Validate a URL against SSRF protection rules.

    Convenience function using default configuration.

    Args:
        url: The URL to validate
        allow_private_networks: Whether to allow private IP ranges
        allow_loopback: Whether to allow localhost/127.x.x.x
        allowed_ports: Set[Any] of allowed ports (default: 80, 443, 8080, 8443)  # TODO(TYPE): replace Any with concrete type

    Returns:
        The validated URL

    Raises:
        SSRFValidationError: If the URL fails validation

    Example:
        try:
            safe_url = validate_url(user_input)
        except SSRFValidationError:
            return {"error": "Invalid URL"}
    """
    config = SSRFConfig(
        allow_private_networks=allow_private_networks,
        allow_loopback=allow_loopback,
        allowed_ports=frozenset(allowed_ports) if allowed_ports else None,
    )
    protector = SSRFProtector(config)
    return protector.validate_url(url)


def is_safe_url(url: str) -> bool:
    """
    Check if a URL is safe (does not trigger SSRF protections).

    Convenience function for simple boolean checks.

    Args:
        url: The URL to check

    Returns:
        True if the URL is safe, False otherwise

    Example:
        if is_safe_url(callback_url):
            await make_callback(callback_url)
        else:
            logger.warning("Blocked unsafe callback URL")
    """
    try:
        get_default_protector().validate_url(url)
        return True
    except SSRFValidationError:
        return False


def is_safe_ip(ip_string: str) -> bool:
    """
    Check if an IP address is safe.

    Args:
        ip_string: IP address as string

    Returns:
        True if the IP is safe, False otherwise
    """
    try:
        ip = ipaddress.ip_address(ip_string)
        protector = get_default_protector()
        protector._validate_ip_address(ip, f"http://{ip_string}/")
        return True
    except (ValueError, SSRFValidationError):
        return False


# Pydantic validator for URL fields
class SafeHttpUrl(BaseModel):
    """
    Pydantic model for validating safe HTTP URLs.

    Use this as a field type in Pydantic models to automatically
    validate URLs against SSRF attacks.

    Example:
        class WebhookConfig(BaseModel):
            callback_url: SafeHttpUrl

        config = WebhookConfig(callback_url="https://example.com/webhook")
    """

    url: str = Field(..., description="Validated HTTP/HTTPS URL")

    @field_validator("url")
    @classmethod
    def validate_safe_url(cls, v: str) -> str:
        """Validate URL is safe from SSRF."""
        return validate_url(v)


def validate_callback_url(url: str | None) -> str | None:
    """
    Validate a callback URL, returning None if invalid.

    Designed for optional callback URL fields where we want to
    silently reject invalid URLs rather than raise exceptions.

    Args:
        url: Optional callback URL

    Returns:
        Validated URL or None if invalid/empty
    """
    if not url:
        return None

    try:
        return validate_url(url)
    except SSRFValidationError as e:
        logger.warning("Blocked callback URL: %s", e)
        return None


# Export key components
__all__ = [
    "SSRFProtector",
    "SSRFConfig",
    "SSRFValidationError",
    "SSRFViolationType",
    "validate_url",
    "is_safe_url",
    "is_safe_ip",
    "SafeHttpUrl",
    "validate_callback_url",
    "get_default_protector",
    "METADATA_SERVICE_IPS",
    "METADATA_SERVICE_HOSTNAMES",
]
