"""
IP Whitelist Service for SanskritiSetu

Provides IP-based access control with support for:
- Individual IP addresses
- CIDR notation (e.g., 192.168.0.0/24)
- Header extraction for proxied requests (X-Forwarded-For, X-Real-IP)
- Path-based bypass rules
- In-memory caching for performance
"""

import ipaddress
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class IPWhitelistResult(Enum):
    """Result of IP whitelist check"""

    ALLOWED = "allowed"
    DENIED = "denied"
    BYPASSED = "bypassed"
    ERROR = "error"


@dataclass
class IPWhitelistConfig:
    """Configuration for IP whitelisting"""

    enabled: bool = True
    whitelisted_ips: set[str] = field(default_factory=set)
    bypass_paths: set[str] = field(
        default_factory=lambda: {
            "/health",
            "/status",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        }
    )
    trust_proxy_headers: bool = True
    proxy_header_priority: tuple[str, ...] = ("X-Forwarded-For", "X-Real-IP")
    default_action: str = "allow"  # "allow" or "deny"

    @classmethod
    def from_environment(cls) -> "IPWhitelistConfig":
        """Load configuration from environment variables"""
        enabled = os.getenv("IP_WHITELIST_ENABLED", "false").lower() == "true"

        # Parse whitelisted IPs from environment
        whitelist_str = os.getenv("IP_WHITELIST", "")
        whitelisted_ips = set()
        if whitelist_str:
            whitelisted_ips = {ip.strip() for ip in whitelist_str.split(",") if ip.strip()}
        else:
            # Default: allow common private networks in dev, none in prod
            env = os.getenv("ENVIRONMENT", "development").lower()
            if env == "development":
                whitelisted_ips = {
                    "127.0.0.1",
                    "::1",
                    "10.0.0.0/8",
                    "172.16.0.0/12",
                    "192.168.0.0/16",
                }

        # Parse bypass paths
        bypass_str = os.getenv("IP_WHITELIST_BYPASS_PATHS", "")
        bypass_paths = {
            "/health",
            "/status",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        }
        if bypass_str:
            bypass_paths = {p.strip() for p in bypass_str.split(",") if p.strip()}

        trust_proxy = os.getenv("IP_TRUST_PROXY_HEADERS", "true").lower() == "true"
        default_action = os.getenv("IP_WHITELIST_DEFAULT", "allow")

        return cls(
            enabled=enabled,
            whitelisted_ips=whitelisted_ips,
            bypass_paths=bypass_paths,
            trust_proxy_headers=trust_proxy,
            default_action=default_action,
        )


class IPWhitelistService:
    """
    Service for IP-based access control.

    Supports:
    - Individual IP addresses (IPv4 and IPv6)
    - CIDR notation for IP ranges
    - Header extraction for proxied requests
    - Configurable bypass paths
    """

    def __init__(self, config: IPWhitelistConfig | None = None) -> None:
        self.config = config or IPWhitelistConfig.from_environment()
        self._networks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        self._individual_ips: set[str] = set()
        self._compile_whitelist()

    def _compile_whitelist(self) -> None:
        """Compile whitelist entries into optimized lookup structures"""
        self._networks = []
        self._individual_ips = set()

        for entry in self.config.whitelisted_ips:
            try:
                if "/" in entry:
                    # CIDR notation
                    network = ipaddress.ip_network(entry, strict=False)
                    self._networks.append(network)
                else:
                    # Individual IP
                    ip = ipaddress.ip_address(entry)
                    self._individual_ips.add(str(ip))
            except ValueError as e:
                logger.warning(f"Invalid IP whitelist entry '{entry}': {e}")

    def is_enabled(self) -> bool:
        """Check if IP whitelisting is enabled"""
        return self.config.enabled

    def is_path_bypassed(self, path: str) -> bool:
        """Check if path should bypass IP whitelist check"""
        for bypass_path in self.config.bypass_paths:
            if path == bypass_path or path.startswith(bypass_path + "/"):
                return True
        return False

    def extract_client_ip(self, client_ip: str, headers: dict[str, Any] | None = None) -> str:  # TODO(TYPE): replace Any with concrete type
        """
        Extract the real client IP, considering proxy headers.

        Args:
            client_ip: The direct client IP from connection
            headers: Optional dict of HTTP headers

        Returns:
            The extracted client IP address
        """
        if not self.config.trust_proxy_headers or not headers:
            return client_ip

        for header_name in self.config.proxy_header_priority:
            header_value = headers.get(header_name) or headers.get(header_name.lower())
            if header_value:
                # X-Forwarded-For can contain multiple IPs: client, proxy1, proxy2
                # The first IP is the original client
                # Type narrowing: header_value is confirmed to be truthy, convert to str
                header_str: str = str(header_value)
                if "," in header_str:
                    result: str = header_str.split(",")[0].strip()
                    return result
                result = header_str.strip()
                return result

        return client_ip

    def is_ip_whitelisted(self, ip_address: str) -> bool:
        """
        Check if an IP address is whitelisted.

        Args:
            ip_address: The IP address to check

        Returns:
            True if the IP is whitelisted or if whitelist is disabled
        """
        if not self.config.enabled:
            return True

        if not ip_address or ip_address == "unknown":
            return self.config.default_action == "allow"

        try:
            ip = ipaddress.ip_address(ip_address)

            # Check individual IPs first (fast path)
            if str(ip) in self._individual_ips:
                return True

            # Check networks
            for network in self._networks:
                if ip in network:
                    return True

            return False

        except ValueError:
            logger.warning(f"Invalid IP address format: {ip_address}")
            return self.config.default_action == "allow"

    def check_ip_access(
        self,
        client_ip: str,
        path: str,
        headers: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[IPWhitelistResult, str | None]:
        """
        Check if a request should be allowed based on IP.

        Args:
            client_ip: The client IP address
            path: The request path
            headers: Optional HTTP headers for proxy extraction

        Returns:
            Tuple of (result, reason)
        """
        # Check if whitelisting is disabled
        if not self.config.enabled:
            return (IPWhitelistResult.ALLOWED, "whitelisting_disabled")

        # Check if path is bypassed
        if self.is_path_bypassed(path):
            return (IPWhitelistResult.BYPASSED, f"path_bypassed:{path}")

        # Extract real client IP (considering proxy headers)
        real_ip = self.extract_client_ip(client_ip, headers)

        # Check if IP is whitelisted
        if self.is_ip_whitelisted(real_ip):
            return (IPWhitelistResult.ALLOWED, f"ip_whitelisted:{real_ip}")

        return (IPWhitelistResult.DENIED, f"ip_not_whitelisted:{real_ip}")

    def get_whitelist_summary(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get a summary of the whitelist configuration"""
        return {
            "enabled": self.config.enabled,
            "total_entries": len(self.config.whitelisted_ips),
            "individual_ips": len(self._individual_ips),
            "network_ranges": len(self._networks),
            "bypass_paths": list(self.config.bypass_paths),
            "trust_proxy_headers": self.config.trust_proxy_headers,
        }


def get_ip_whitelist_service() -> IPWhitelistService:
    """Get or create the global IP whitelist service instance"""
    return IPWhitelistService()
