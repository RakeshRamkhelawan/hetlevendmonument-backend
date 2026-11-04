"""
Unit tests for IP Whitelist Service and Middleware
"""

import pytest

from src.core.middleware.ip_whitelist import IPWhitelistMiddleware
from src.core.security.ip_whitelist import IPWhitelistConfig, IPWhitelistResult, IPWhitelistService


class TestIPWhitelistConfig:
    """Tests for IPWhitelistConfig"""

    def test_default_config(self):
        """Test default configuration values"""
        config = IPWhitelistConfig()
        assert config.enabled is True
        assert "/health" in config.bypass_paths
        assert config.trust_proxy_headers is True
        assert config.default_action == "allow"

    def test_custom_whitelist(self):
        """Test custom whitelist configuration"""
        config = IPWhitelistConfig(
            enabled=True,
            whitelisted_ips={"127.0.0.1", "192.168.1.0/24"},
            bypass_paths={"/health", "/status"},
        )
        assert config.enabled is True
        assert "127.0.0.1" in config.whitelisted_ips
        assert "/health" in config.bypass_paths


class TestIPWhitelistService:
    """Tests for IPWhitelistService"""

    @pytest.fixture
    def service(self):
        """Create a test service with known whitelist"""
        config = IPWhitelistConfig(
            enabled=True,
            whitelisted_ips={
                "127.0.0.1",
                "::1",
                "192.168.1.0/24",
                "10.0.0.5",
            },
        )
        return IPWhitelistService(config)

    def test_individual_ip_whitelisted(self, service):
        """Test whitelisted individual IP"""
        assert service.is_ip_whitelisted("127.0.0.1") is True
        assert service.is_ip_whitelisted("10.0.0.5") is True

    def test_cidr_range_whitelisted(self, service):
        """Test IP within CIDR range"""
        assert service.is_ip_whitelisted("192.168.1.1") is True
        assert service.is_ip_whitelisted("192.168.1.100") is True
        assert service.is_ip_whitelisted("192.168.1.254") is True

    def test_non_whitelisted_ip(self, service):
        """Test non-whitelisted IP"""
        assert service.is_ip_whitelisted("203.0.113.1") is False
        assert service.is_ip_whitelisted("8.8.8.8") is False

    def test_ipv6_whitelisted(self, service):
        """Test IPv6 localhost"""
        assert service.is_ip_whitelisted("::1") is True

    def test_invalid_ip_format(self, service):
        """Test invalid IP format handling"""
        # Invalid IPs should return True (default allow) for fail-open
        assert service.is_ip_whitelisted("invalid") is True
        assert service.is_ip_whitelisted("") is True

    def test_disabled_whitelist(self, service):
        """Test that disabled whitelist allows all"""
        service.config.enabled = False
        assert service.is_ip_whitelisted("203.0.113.1") is True
        assert service.is_ip_whitelisted("any.ip.address") is True

    def test_path_bypass(self, service):
        """Test path bypass functionality"""
        assert service.is_path_bypassed("/health") is True
        assert service.is_path_bypassed("/health/db") is True
        assert service.is_path_bypassed("/metrics") is True
        assert service.is_path_bypassed("/api/users") is False

    def test_extract_client_ip_from_headers(self, service):
        """Test IP extraction from proxy headers"""
        headers = {"X-Forwarded-For": "203.0.113.1, 198.51.100.1"}
        ip = service.extract_client_ip("192.168.1.1", headers)
        assert ip == "203.0.113.1"

    def test_extract_client_ip_x_real_ip(self, service):
        """Test IP extraction from X-Real-IP header"""
        headers = {"X-Real-IP": "203.0.113.5"}
        ip = service.extract_client_ip("192.168.1.1", headers)
        assert ip == "203.0.113.5"

    def test_extract_client_ip_no_headers(self, service):
        """Test fallback to client IP when no proxy headers"""
        ip = service.extract_client_ip("192.168.1.1", {})
        assert ip == "192.168.1.1"

    def test_check_ip_access_allowed(self, service):
        """Test full access check - allowed"""
        result, reason = service.check_ip_access("127.0.0.1", "/api/users")
        assert result == IPWhitelistResult.ALLOWED
        assert "ip_whitelisted" in reason

    def test_check_ip_access_bypassed(self, service):
        """Test full access check - bypassed path"""
        result, reason = service.check_ip_access("203.0.113.1", "/health")
        assert result == IPWhitelistResult.BYPASSED
        assert "path_bypassed" in reason

    def test_check_ip_access_denied(self, service):
        """Test full access check - denied"""
        result, reason = service.check_ip_access("203.0.113.1", "/api/users")
        assert result == IPWhitelistResult.DENIED
        assert "ip_not_whitelisted" in reason

    def test_get_whitelist_summary(self, service):
        """Test whitelist summary"""
        summary = service.get_whitelist_summary()
        assert summary["enabled"] is True
        assert summary["individual_ips"] == 3  # 127.0.0.1, ::1, 10.0.0.5
        assert summary["network_ranges"] == 1  # 192.168.1.0/24


class TestIPWhitelistMiddleware:
    """Tests for IPWhitelistMiddleware"""

    @pytest.fixture
    def mock_app(self):
        """Create a mock ASGI app"""

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"OK"})

        return app

    @pytest.fixture
    def whitelist_service(self):
        """Create a whitelist service for testing"""
        config = IPWhitelistConfig(
            enabled=True,
            whitelisted_ips={"127.0.0.1"},
        )
        return IPWhitelistService(config)

    @pytest.mark.asyncio
    async def test_whitelisted_ip_allowed(self, mock_app, whitelist_service):
        """Test that whitelisted IP is allowed through"""
        middleware = IPWhitelistMiddleware(mock_app, whitelist_service)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/users",
            "headers": [],
            "client": ("127.0.0.1", 50000),
        }

        messages = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            messages.append(message)

        await middleware(scope, receive, send)

        assert len(messages) == 2
        assert messages[0]["status"] == 200

    @pytest.mark.asyncio
    async def test_non_whitelisted_ip_blocked(self, mock_app, whitelist_service):
        """Test that non-whitelisted IP is blocked with 403"""
        middleware = IPWhitelistMiddleware(mock_app, whitelist_service)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/users",
            "headers": [],
            "client": ("203.0.113.1", 50000),
        }

        messages = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            messages.append(message)

        await middleware(scope, receive, send)

        assert len(messages) == 2
        assert messages[0]["status"] == 403
        assert b"IP address not whitelisted" in messages[1]["body"]

    @pytest.mark.asyncio
    async def test_bypass_path_allowed(self, mock_app, whitelist_service):
        """Test that bypass paths are allowed even for non-whitelisted IPs"""
        middleware = IPWhitelistMiddleware(mock_app, whitelist_service)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [],
            "client": ("203.0.113.1", 50000),
        }

        messages = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            messages.append(message)

        await middleware(scope, receive, send)

        assert len(messages) == 2
        assert messages[0]["status"] == 200

    @pytest.mark.asyncio
    async def test_non_http_scope_passthrough(self, mock_app, whitelist_service):
        """Test that non-HTTP scopes pass through"""
        middleware = IPWhitelistMiddleware(mock_app, whitelist_service)

        scope = {"type": "websocket"}

        messages = []

        async def receive():
            return {"type": "websocket.connect"}

        async def send(message):
            messages.append(message)

        await middleware(scope, receive, send)

        # Should pass through without checking whitelist
        assert len(messages) == 2


class TestSecurityManagerIntegration:
    """Tests for integration with ProductionSecurityManager"""

    def test_security_manager_has_is_ip_whitelisted(self):
        """Test that security manager has is_ip_whitelisted method"""
        from src.core.security.security_manager import get_security_manager

        manager = get_security_manager()
        assert hasattr(manager, "is_ip_whitelisted")
        assert callable(getattr(manager, "is_ip_whitelisted"))

    def test_is_ip_whitelisted_calls_is_ip_allowed(self):
        """Test that is_ip_whitelisted wraps is_ip_allowed"""
        from src.core.security.security_manager import get_security_manager

        manager = get_security_manager()

        # Both methods should return same result for same IP
        ip = "127.0.0.1"
        result1 = manager.is_ip_allowed(ip)
        result2 = manager.is_ip_whitelisted(ip)
        assert result1 == result2
