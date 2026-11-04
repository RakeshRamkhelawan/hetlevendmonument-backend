"""
Tests for Egress Control & SSRF Hardening

Covers:
- Egress policy validation
- Allowlist/denylist matching
- Private IP detection
- Rate limiting
- Audit logging
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.security.egress_control import (
    EgressController,
    EgressDecision,
    EgressPolicy,
    EgressResult,
)


class TestEgressPolicy:
    """Test EgressPolicy dataclass."""

    def test_policy_creation(self):
        """Should create policy with default ports."""
        policy = EgressPolicy(
            tenant_id=1,
            allowed_domains=["api.example.com"],
            blocked_domains=["evil.com"],
        )

        assert policy.tenant_id == 1
        assert policy.allowed_domains == ["api.example.com"]
        assert policy.blocked_domains == ["evil.com"]
        assert policy.allowed_ports == {80, 443}
        assert policy.max_request_size_bytes == 10 * 1024 * 1024
        assert policy.rate_limit_per_minute == 100

    def test_policy_custom_ports(self):
        """Should accept custom ports."""
        policy = EgressPolicy(
            tenant_id=1,
            allowed_domains=["api.example.com"],
            blocked_domains=[],
            allowed_ports={80, 443, 8080},
        )

        assert policy.allowed_ports == {80, 443, 8080}


class TestEgressResult:
    """Test EgressResult dataclass."""

    def test_result_creation(self):
        """Should create result."""
        result = EgressResult(
            decision=EgressDecision.ALLOW,
            resolved_ip="1.2.3.4",
        )

        assert result.decision == EgressDecision.ALLOW
        assert result.resolved_ip == "1.2.3.4"
        assert result.is_allowed() is True

    def test_result_blocked(self):
        """Should indicate not allowed for blocked."""
        result = EgressResult(
            decision=EgressDecision.BLOCK,
            reason="Domain in denylist",
        )

        assert result.is_allowed() is False


class TestEgressController:
    """Test EgressController."""

    @pytest.fixture
    def controller(self):
        """Create fresh controller."""
        return EgressController()

    @pytest.fixture
    def policy(self):
        """Create test policy."""
        return EgressPolicy(
            tenant_id=1,
            allowed_domains=["api.example.com", "*.trusted.com"],
            blocked_domains=["evil.com", "malicious.org"],
            allowed_ports={80, 443},
            rate_limit_per_minute=10,
        )

    def test_set_policy(self, controller, policy):
        """Should store policy."""
        controller.set_policy(policy)

        assert controller._policies[1] == policy

    @pytest.mark.asyncio
    async def test_validate_no_policy(self, controller):
        """Should block when no policy configured."""
        result = await controller.validate_request(
            url="https://api.example.com/data",
            tenant_id=1,
        )

        assert result.decision == EgressDecision.BLOCK
        assert "No egress policy" in result.reason

    @pytest.mark.asyncio
    async def test_validate_blocked_port(self, controller, policy):
        """Should block non-standard ports."""
        controller.set_policy(policy)

        result = await controller.validate_request(
            url="https://api.example.com:8080/data",
            tenant_id=1,
        )

        assert result.decision == EgressDecision.BLOCK
        assert "Port 8080" in result.reason

    @pytest.mark.asyncio
    async def test_validate_size_exceeded(self, controller, policy):
        """Should block oversized requests."""
        controller.set_policy(policy)

        result = await controller.validate_request(
            url="https://api.example.com/data",
            tenant_id=1,
            request_size=20 * 1024 * 1024,  # 20MB
        )

        assert result.decision == EgressDecision.SIZE_EXCEEDED

    @pytest.mark.asyncio
    async def test_validate_denylist(self, controller, policy):
        """Should block denylisted domains."""
        controller.set_policy(policy)

        result = await controller.validate_request(
            url="https://evil.com/data",
            tenant_id=1,
        )

        assert result.decision == EgressDecision.BLOCK
        assert "denylist" in result.reason

    @pytest.mark.asyncio
    async def test_validate_denylist_subdomain(self, controller, policy):
        """Should block subdomains of denylisted domains."""
        controller.set_policy(policy)

        result = await controller.validate_request(
            url="https://sub.evil.com/data",
            tenant_id=1,
        )

        assert result.decision == EgressDecision.BLOCK

    @pytest.mark.asyncio
    async def test_validate_allowlist_exact_match(self, controller, policy):
        """Should allow exact domain match."""
        controller.set_policy(policy)

        with patch.object(controller, "_resolve_hostname", return_value="93.184.216.34"):
            with patch.object(controller, "_is_rate_limited", return_value=False):
                result = await controller.validate_request(
                    url="https://api.example.com/data",
                    tenant_id=1,
                )

        assert result.decision == EgressDecision.ALLOW

    @pytest.mark.asyncio
    async def test_validate_allowlist_wildcard(self, controller, policy):
        """Should allow wildcard subdomains."""
        controller.set_policy(policy)

        with patch.object(controller, "_resolve_hostname", return_value="93.184.216.34"):
            with patch.object(controller, "_is_rate_limited", return_value=False):
                result = await controller.validate_request(
                    url="https://sub.trusted.com/data",
                    tenant_id=1,
                )

        assert result.decision == EgressDecision.ALLOW

    @pytest.mark.asyncio
    async def test_validate_allowlist_subdomain(self, controller, policy):
        """Should allow subdomains of allowed domains."""
        controller.set_policy(policy)

        with patch.object(controller, "_resolve_hostname", return_value="93.184.216.34"):
            with patch.object(controller, "_is_rate_limited", return_value=False):
                result = await controller.validate_request(
                    url="https://v1.api.example.com/data",
                    tenant_id=1,
                )

        assert result.decision == EgressDecision.ALLOW

    @pytest.mark.asyncio
    async def test_validate_not_in_allowlist(self, controller, policy):
        """Should block domains not in allowlist."""
        controller.set_policy(policy)

        result = await controller.validate_request(
            url="https://unknown.com/data",
            tenant_id=1,
        )

        assert result.decision == EgressDecision.BLOCK
        assert "not in allowlist" in result.reason

    @pytest.mark.asyncio
    async def test_validate_private_ip_blocked(self, controller, policy):
        """Should block private IP addresses (SSRF protection)."""
        controller.set_policy(policy)

        with patch.object(controller, "_resolve_hostname", return_value="192.168.1.1"):
            result = await controller.validate_request(
                url="https://api.example.com/data",
                tenant_id=1,
            )

        assert result.decision == EgressDecision.BLOCK
        assert "private IP" in result.reason

    @pytest.mark.asyncio
    async def test_validate_loopback_blocked(self, controller, policy):
        """Should block loopback addresses."""
        controller.set_policy(policy)

        with patch.object(controller, "_resolve_hostname", return_value="127.0.0.1"):
            result = await controller.validate_request(
                url="https://api.example.com/data",
                tenant_id=1,
            )

        assert result.decision == EgressDecision.BLOCK

    @pytest.mark.asyncio
    async def test_validate_rate_limited(self, controller, policy):
        """Should rate limit when threshold exceeded."""
        mock_redis = AsyncMock()
        controller._redis = mock_redis
        mock_redis.incr.return_value = 15  # Above limit of 10

        controller.set_policy(policy)

        with patch.object(controller, "_resolve_hostname", return_value="93.184.216.34"):
            result = await controller.validate_request(
                url="https://api.example.com/data",
                tenant_id=1,
            )

        assert result.decision == EgressDecision.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_validate_dns_failure(self, controller, policy):
        """Should block on DNS resolution failure."""
        controller.set_policy(policy)

        with patch.object(controller, "_resolve_hostname", side_effect=Exception("DNS error")):
            result = await controller.validate_request(
                url="https://api.example.com/data",
                tenant_id=1,
            )

        assert result.decision == EgressDecision.BLOCK
        assert "DNS resolution failed" in result.reason

    def test_is_blocked_exact_match(self, controller):
        """Should block exact domain matches."""
        result = controller._is_blocked("evil.com", ["evil.com"])

        assert result is True

    def test_is_blocked_subdomain(self, controller):
        """Should block subdomains."""
        result = controller._is_blocked("sub.evil.com", ["evil.com"])

        assert result is True

    def test_is_blocked_case_insensitive(self, controller):
        """Should be case insensitive."""
        result = controller._is_blocked("EVIL.COM", ["evil.com"])

        assert result is True

    def test_is_allowed_empty_list(self, controller):
        """Should deny when allowlist is empty."""
        result = controller._is_allowed("example.com", [])

        assert result is False

    def test_is_allowed_exact_match(self, controller):
        """Should allow exact matches."""
        result = controller._is_allowed("example.com", ["example.com"])

        assert result is True

    def test_is_allowed_wildcard(self, controller):
        """Should allow wildcard matches."""
        result = controller._is_allowed("sub.example.com", ["*.example.com"])

        assert result is True

    def test_is_allowed_parent_domain(self, controller):
        """Should allow subdomains of parent domain."""
        result = controller._is_allowed("api.example.com", ["example.com"])

        assert result is True

    def test_is_private_ip_private_range(self, controller):
        """Should detect private IPs."""
        result = controller._is_private_ip("192.168.1.1")

        assert result is True

    def test_is_private_ip_loopback(self, controller):
        """Should detect loopback."""
        result = controller._is_private_ip("127.0.0.1")

        assert result is True

    def test_is_private_ip_public(self, controller):
        """Should allow public IPs."""
        result = controller._is_private_ip("8.8.8.8")

        assert result is False

    def test_is_private_ip_invalid(self, controller):
        """Should handle invalid IPs."""
        result = controller._is_private_ip("not-an-ip")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_rate_limited_no_redis(self, controller, policy):
        """Should not rate limit without Redis."""
        result = await controller._is_rate_limited(1, policy)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_audit_log(self, controller):
        """Should return audit log entries."""
        # Add some entries
        controller._audit_log = [
            {"tenant_id": 1, "decision": "allow", "url": "https://example.com"},
            {"tenant_id": 1, "decision": "block", "url": "https://evil.com"},
            {"tenant_id": 2, "decision": "allow", "url": "https://other.com"},
        ]

        # Get all for tenant 1
        entries = controller.get_audit_log(tenant_id=1)

        assert len(entries) == 2
        assert all(e["tenant_id"] == 1 for e in entries)

    @pytest.mark.asyncio
    async def test_get_audit_log_by_decision(self, controller):
        """Should filter by decision."""
        controller._audit_log = [
            {"tenant_id": 1, "decision": "allow", "url": "https://example.com"},
            {"tenant_id": 1, "decision": "block", "url": "https://evil.com"},
        ]

        entries = controller.get_audit_log(
            tenant_id=1,
            decision=EgressDecision.BLOCK,
        )

        assert len(entries) == 1
        assert entries[0]["decision"] == "block"

    def test_get_stats(self, controller):
        """Should calculate statistics."""
        controller._audit_log = [
            {"tenant_id": 1, "decision": "allow"},
            {"tenant_id": 1, "decision": "allow"},
            {"tenant_id": 1, "decision": "block"},
            {"tenant_id": 1, "decision": "rate_limited"},
        ]

        stats = controller.get_stats(tenant_id=1)

        assert stats["total_requests"] == 4
        assert stats["allowed"] == 2
        assert stats["blocked"] == 1
        assert stats["rate_limited"] == 1
        assert stats["block_rate"] == 0.25
