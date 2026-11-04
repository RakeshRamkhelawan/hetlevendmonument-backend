"""
Egress Control & SSRF Hardening

Provides:
- Allowlist/denylist based egress control
- DNS rebinding protection
- Rate limiting per tenant
- Request/response size limits
- Audit logging for all egress attempts
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, cast
from urllib.parse import urlparse

import dns.resolver

logger = logging.getLogger(__name__)


class EgressDecision(Enum):
    """Decision for egress request."""

    ALLOW = "allow"
    BLOCK = "block"
    RATE_LIMITED = "rate_limited"
    SIZE_EXCEEDED = "size_exceeded"


@dataclass
class EgressPolicy:
    """Egress policy for a tenant."""

    tenant_id: int
    allowed_domains: list[str]  # Allowlist (default deny)
    blocked_domains: list[str]  # Denylist (higher priority)
    allowed_ports: set[int] | None = None  # Default: {80, 443}
    max_request_size_bytes: int = 10 * 1024 * 1024  # 10MB
    max_response_size_bytes: int = 50 * 1024 * 1024  # 50MB
    rate_limit_per_minute: int = 100

    def __post_init__(self) -> None:
        if self.allowed_ports is None:
            self.allowed_ports = {80, 443}


@dataclass
class EgressResult:
    """Result of egress validation."""

    decision: EgressDecision
    reason: str | None = None
    resolved_ip: str | None = None

    def is_allowed(self) -> bool:
        return self.decision == EgressDecision.ALLOW


class EgressController:
    """
    Controller for egress traffic validation.

    Implements defense-in-depth:
    1. Check denylist (immediate block)
    2. Check allowlist (default deny)
    3. Check private IP ranges (SSRF protection)
    4. DNS rebinding protection (resolve -> check IP)
    5. Rate limiting
    6. Size limits
    """

    # Private IP ranges (RFC 1918 + others)
    PRIVATE_NETWORKS = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),  # Link-local
        ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ]

    def __init__(self, redis_client: Any | None = None) -> None:  # TODO(TYPE): replace Any with concrete type
        self._redis = redis_client
        self._policies: dict[int, EgressPolicy] = {}
        self._audit_log: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

    def set_policy(self, policy: EgressPolicy) -> None:
        """Set egress policy for a tenant."""
        self._policies[policy.tenant_id] = policy
        logger.info(f"Set egress policy for tenant {policy.tenant_id}")

    async def validate_request(
        self,
        url: str,
        tenant_id: int,
        agent_id: str | None = None,
        request_size: int = 0,
    ) -> EgressResult:
        """
        Validate egress request.

        Args:
            url: Target URL
            tenant_id: Tenant ID
            agent_id: Agent ID (for audit)
            request_size: Request body size in bytes

        Returns:
            EgressResult with decision
        """
        policy = self._policies.get(tenant_id)
        if not policy:
            # Default deny if no policy
            result = EgressResult(
                decision=EgressDecision.BLOCK, reason="No egress policy configured for tenant"
            )
            await self._log_egress(tenant_id, agent_id, url, result)
            return result

        # Parse URL
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        if hostname is None:
            result = EgressResult(
                decision=EgressDecision.BLOCK,
                reason="Invalid URL: no hostname",
            )
            await self._log_egress(tenant_id, agent_id, url, result)
            return result

        # Check port
        if port not in (policy.allowed_ports or set()):
            result = EgressResult(
                decision=EgressDecision.BLOCK, reason=f"Port {port} not in allowed ports"
            )
            await self._log_egress(tenant_id, agent_id, url, result)
            return result

        # Check size
        if request_size > policy.max_request_size_bytes:
            result = EgressResult(
                decision=EgressDecision.SIZE_EXCEEDED,
                reason=f"Request size {request_size} exceeds limit",
            )
            await self._log_egress(tenant_id, agent_id, url, result)
            return result

        # Check denylist (higher priority)
        if self._is_blocked(hostname, policy.blocked_domains):
            result = EgressResult(decision=EgressDecision.BLOCK, reason="Domain in denylist")
            await self._log_egress(tenant_id, agent_id, url, result)
            return result

        # Check allowlist (default deny)
        if not self._is_allowed(hostname, policy.allowed_domains):
            result = EgressResult(decision=EgressDecision.BLOCK, reason="Domain not in allowlist")
            await self._log_egress(tenant_id, agent_id, url, result)
            return result

        # DNS rebinding protection: resolve and check IP
        try:
            resolved_ip = await self._resolve_hostname(hostname)
            if self._is_private_ip(resolved_ip):
                result = EgressResult(
                    decision=EgressDecision.BLOCK,
                    reason=f"DNS resolved to private IP: {resolved_ip}",
                    resolved_ip=resolved_ip,
                )
                await self._log_egress(tenant_id, agent_id, url, result)
                return result
        except Exception as e:
            logger.warning(f"DNS resolution failed for {hostname}: {e}")
            result = EgressResult(
                decision=EgressDecision.BLOCK, reason=f"DNS resolution failed: {e}"
            )
            await self._log_egress(tenant_id, agent_id, url, result)
            return result

        # Check rate limit
        if await self._is_rate_limited(tenant_id, policy):
            result = EgressResult(
                decision=EgressDecision.RATE_LIMITED, reason="Rate limit exceeded"
            )
            await self._log_egress(tenant_id, agent_id, url, result)
            return result

        # All checks passed
        result = EgressResult(
            decision=EgressDecision.ALLOW,
            resolved_ip=resolved_ip,
        )
        await self._log_egress(tenant_id, agent_id, url, result)
        return result

    def _is_blocked(self, hostname: str, blocked_domains: list[str]) -> bool:
        """Check if hostname matches denylist."""
        hostname_lower = hostname.lower()
        for blocked in blocked_domains:
            blocked_lower = blocked.lower()
            if hostname_lower == blocked_lower or hostname_lower.endswith(f".{blocked_lower}"):
                return True
        return False

    def _is_allowed(self, hostname: str, allowed_domains: list[str]) -> bool:
        """Check if hostname matches allowlist."""
        # Empty allowlist = allow none (default deny)
        if not allowed_domains:
            return False

        hostname_lower = hostname.lower()
        for allowed in allowed_domains:
            allowed_lower = allowed.lower()
            # Exact match
            if hostname_lower == allowed_lower:
                return True
            # Subdomain match (if allowed starts with *.)
            if allowed.startswith("*."):
                suffix = allowed_lower[2:]  # Remove *.
                if hostname_lower.endswith(suffix) or hostname_lower == suffix:
                    return True
            # Parent domain match
            if hostname_lower.endswith(f".{allowed_lower}"):
                return True
        return False

    async def _resolve_hostname(self, hostname: str) -> str:
        """Resolve hostname to IP address."""
        try:
            answers = dns.resolver.resolve(hostname, "A")
            return str(answers[0])
        except Exception:
            # Try IPv6
            answers = dns.resolver.resolve(hostname, "AAAA")
            return str(answers[0])

    def _is_private_ip(self, ip_str: str) -> bool:
        """Check if IP is in private ranges."""
        try:
            ip = ipaddress.ip_address(ip_str)
            for network in self.PRIVATE_NETWORKS:
                if ip in network:
                    return True
            return False
        except ValueError:
            return False

    async def _is_rate_limited(self, tenant_id: int, policy: EgressPolicy) -> bool:
        """Check if tenant is rate limited."""
        if not self._redis:
            return False

        key = f"egress_rate:{tenant_id}"
        current = await self._redis.incr(key)
        if current == 1:
            await self._redis.expire(key, 60)  # 1 minute window

        return cast(int, current) > policy.rate_limit_per_minute

    async def _log_egress(
        self,
        tenant_id: int,
        agent_id: str | None,
        url: str,
        result: EgressResult,
    ) -> None:
        """Log egress attempt to audit log."""
        from datetime import datetime, timezone

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "url": url,
            "decision": result.decision.value,
            "reason": result.reason,
            "resolved_ip": result.resolved_ip,
        }

        self._audit_log.append(entry)

        if result.decision == EgressDecision.ALLOW:
            logger.debug(f"Egress ALLOWED: {url} (tenant={tenant_id})")
        else:
            logger.warning(
                f"Egress {result.decision.value.upper()}: {url} "
                f"(tenant={tenant_id}, reason={result.reason})"
            )

    def get_audit_log(
        self,
        tenant_id: int | None = None,
        decision: EgressDecision | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get audit log entries."""
        entries = self._audit_log

        if tenant_id:
            entries = [e for e in entries if e["tenant_id"] == tenant_id]

        if decision:
            entries = [e for e in entries if e["decision"] == decision.value]

        return entries[-limit:]

    def get_stats(self, tenant_id: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get egress statistics for tenant."""
        entries = [e for e in self._audit_log if e["tenant_id"] == tenant_id]

        allowed = len([e for e in entries if e["decision"] == "allow"])
        blocked = len([e for e in entries if e["decision"] == "block"])
        rate_limited = len([e for e in entries if e["decision"] == "rate_limited"])

        return {
            "tenant_id": tenant_id,
            "total_requests": len(entries),
            "allowed": allowed,
            "blocked": blocked,
            "rate_limited": rate_limited,
            "block_rate": blocked / len(entries) if entries else 0,
        }
