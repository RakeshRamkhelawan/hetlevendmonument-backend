"""
Comprehensive tests for src/core/security/security_manager.py
Coverage target: 100% of security manager
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import bcrypt
import jwt
import pytest

from src.core.security.security_manager import (
    ProductionSecurityManager,
    RateLimitRule,
    SecurityEvent,
    SecurityLevel,
    ThreatLevel,
    get_security_manager,
    require_auth,
)


# Helper fixture to reset the global singleton between tests
@pytest.fixture(autouse=True)
def reset_security_manager_singleton():
    """Reset global security manager singleton before each test"""
    import src.core.security.security_manager as sm

    sm._security_manager = None
    yield
    sm._security_manager = None


class TestSecurityLevelEnum:
    """Test SecurityLevel enum"""

    def test_all_security_levels(self):
        """Test all security levels are defined"""
        assert SecurityLevel.PUBLIC.value == "public"
        assert SecurityLevel.AUTHENTICATED.value == "authenticated"
        assert SecurityLevel.AUTHORIZED.value == "authorized"
        assert SecurityLevel.ADMIN.value == "admin"
        assert SecurityLevel.SYSTEM.value == "system"


class TestThreatLevelEnum:
    """Test ThreatLevel enum"""

    def test_all_threat_levels(self):
        """Test all threat levels are defined with canonical string values."""
        assert ThreatLevel.LOW.value == "low"
        assert ThreatLevel.MEDIUM.value == "medium"
        assert ThreatLevel.HIGH.value == "high"
        assert ThreatLevel.CRITICAL.value == "critical"
        assert ThreatLevel.INFO.value == "info"

    def test_threat_levels_ordered(self):
        """Test threat levels are ordered by increasing severity (enum member order)."""
        levels = [
            ThreatLevel.INFO,
            ThreatLevel.LOW,
            ThreatLevel.MEDIUM,
            ThreatLevel.HIGH,
            ThreatLevel.CRITICAL,
        ]
        members = list(ThreatLevel)
        for i in range(len(levels) - 1):
            assert members.index(levels[i]) < members.index(levels[i + 1])


class TestSecurityEvent:
    """Test SecurityEvent dataclass"""

    def test_security_event_creation(self):
        """Test creating security event"""
        now = datetime.now(timezone.utc)
        event = SecurityEvent(
            event_id="evt-123",
            event_type="login_attempt",
            severity=ThreatLevel.LOW,
            source_ip="192.168.1.1",
            user_id="user-123",
            endpoint="/api/login",
            description="Successful login",
            timestamp=now,
            metadata={"key": "value"},
        )

        assert event.event_id == "evt-123"
        assert event.event_type == "login_attempt"
        assert event.severity == ThreatLevel.LOW
        assert event.source_ip == "192.168.1.1"

    def test_security_event_auto_timestamp(self):
        """Test security event gets automatic timestamp"""
        event = SecurityEvent(
            event_id="evt-123",
            event_type="test",
            severity=ThreatLevel.LOW,
            source_ip="192.168.1.1",
            user_id=None,
            endpoint="/test",
            description="Test event",
        )

        assert isinstance(event.timestamp, datetime)
        assert event.timestamp.tzinfo == timezone.utc


class TestRateLimitRule:
    """Test RateLimitRule dataclass"""

    def test_rate_limit_rule_creation(self):
        """Test creating rate limit rule"""
        rule = RateLimitRule(
            endpoint_pattern="/api/*",
            requests_per_minute=60,
            requests_per_hour=400,
            burst_limit=10,
            security_level=SecurityLevel.AUTHENTICATED,
        )

        assert rule.endpoint_pattern == "/api/*"
        assert rule.requests_per_minute == 60
        assert rule.requests_per_hour == 400
        assert rule.burst_limit == 10
        assert rule.security_level == SecurityLevel.AUTHENTICATED


class TestProductionSecurityManagerInitialization:
    """Test ProductionSecurityManager initialization"""

    @patch("src.core.config.unified_config.config")
    def test_initialization_with_config_secret(self, mock_config):
        """Test initialization with secret from config"""
        mock_config.jwt_secret_key = "config-secret-key"

        manager = ProductionSecurityManager()

        assert manager.secret_key == "config-secret-key"
        assert manager.jwt_algorithm == "HS256"
        assert manager.token_expiry_hours == 24

    @patch("src.core.config.unified_config.config")
    @patch.object(ProductionSecurityManager, "_get_secret_key")
    def test_initialization_with_env_secret(self, mock_get_secret, mock_config):
        """Test initialization with secret from environment"""
        mock_config.jwt_secret_key = None
        mock_get_secret.return_value = "env-secret-key"

        manager = ProductionSecurityManager()

        assert manager.secret_key == "env-secret-key"

    @patch("src.core.config.unified_config.config")
    def test_initialization_generates_secret(self, mock_config):
        """Test initialization generates secret if none provided"""
        mock_config.jwt_secret_key = None

        manager = ProductionSecurityManager()

        assert len(manager.secret_key) > 0

    @patch("src.core.config.unified_config.config")
    def test_initialization_sets_security_headers(self, mock_config):
        """Test initialization sets security headers"""

    @patch("src.core.config.unified_config.config")
    def test_initialization_sets_security_headers(self, mock_config):
        """Test initialization sets security headers"""
        mock_config.jwt_secret_key = "test-key"

        manager = ProductionSecurityManager()

        assert "X-Content-Type-Options" in manager.security_headers
        assert manager.security_headers["X-Content-Type-Options"] == "nosniff"
        assert "X-Frame-Options" in manager.security_headers
        assert "Strict-Transport-Security" in manager.security_headers


class TestTokenGeneration:
    """Test generate_token method"""

    @patch("src.core.config.unified_config.config")
    def test_generate_token_basic(self, mock_config):
        """Test basic token generation"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        token = manager.generate_token("user-123")

        assert isinstance(token, str)
        assert len(token) > 0

    @patch("src.core.config.unified_config.config")
    def test_generate_token_with_security_level(self, mock_config):
        """Test token generation with security level"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        token = manager.generate_token("user-123", SecurityLevel.ADMIN)

        # Decode to verify
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
        assert payload["user_id"] == "user-123"
        assert payload["security_level"] == "admin"

    @patch("src.core.config.unified_config.config")
    def test_generate_token_has_expiry(self, mock_config):
        """Test generated token has expiry"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        token = manager.generate_token("user-123")

        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
        assert "exp" in payload
        assert "iat" in payload

    @patch("src.core.config.unified_config.config")
    def test_generate_token_logs_event(self, mock_config):
        """Test token generation logs security event"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        manager.generate_token("user-123")

        assert len(manager.security_events) == 1
        assert manager.security_events[0].event_type == "token_generated"


class TestTokenVerification:
    """Test verify_token method"""

    @patch("src.core.config.unified_config.config")
    def test_verify_valid_token(self, mock_config):
        """Test verifying valid token"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        token = manager.generate_token("user-123")
        payload = manager.verify_token(token)

        assert payload is not None
        assert payload["user_id"] == "user-123"

    @patch("src.core.config.unified_config.config")
    def test_verify_invalid_token(self, mock_config):
        """Test verifying invalid token"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        payload = manager.verify_token("invalid-token")

        assert payload is None
        assert any(e.event_type == "token_invalid" for e in manager.security_events)

    @patch("src.core.config.unified_config.config")
    def test_verify_expired_token(self, mock_config):
        """Test verifying expired token"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        # Create expired token
        payload = {
            "user_id": "user-123",
            "security_level": "authenticated",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        }
        expired_token = jwt.encode(payload, "test-secret", algorithm="HS256")

        result = manager.verify_token(expired_token)

        assert result is None


class TestPasswordHashing:
    """Test password hashing methods"""

    @patch("src.core.config.unified_config.config")
    def test_hash_password(self, mock_config):
        """Test password hashing"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        hashed = manager.hash_password("password123")

        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != "password123"

    @patch("src.core.config.unified_config.config")
    def test_verify_password_correct(self, mock_config):
        """Test verifying correct password"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        hashed = manager.hash_password("password123")
        is_valid = manager.verify_password("password123", hashed)

        assert is_valid is True

    @patch("src.core.config.unified_config.config")
    def test_verify_password_incorrect(self, mock_config):
        """Test verifying incorrect password"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        hashed = manager.hash_password("password123")
        is_valid = manager.verify_password("wrong-password", hashed)

        assert is_valid is False


class TestIPAllowlist:
    """Test is_ip_allowed method"""

    @patch("src.core.config.unified_config.config")
    @patch("os.getenv")
    def test_localhost_allowed(self, mock_getenv, mock_config):
        """Test localhost is allowed"""
        mock_config.jwt_secret_key = "test-secret"
        mock_getenv.return_value = "127.0.0.1,::1"
        manager = ProductionSecurityManager()

        is_allowed = manager.is_ip_allowed("127.0.0.1")

        assert is_allowed is True

    @patch("src.core.config.unified_config.config")
    @patch("os.getenv")
    def test_private_network_allowed(self, mock_getenv, mock_config):
        """Test private network IP is allowed"""
        mock_config.jwt_secret_key = "test-secret"
        mock_getenv.return_value = "192.168.0.0/16"
        manager = ProductionSecurityManager()

        is_allowed = manager.is_ip_allowed("192.168.1.100")

        assert is_allowed is True

    @patch("src.core.config.unified_config.config")
    @patch("os.getenv")
    def test_public_ip_not_allowed(self, mock_getenv, mock_config):
        """Test public IP is not allowed"""
        mock_config.jwt_secret_key = "test-secret"
        mock_getenv.return_value = "127.0.0.1"
        manager = ProductionSecurityManager()

        is_allowed = manager.is_ip_allowed("8.8.8.8")

        assert is_allowed is False

    @patch("src.core.config.unified_config.config")
    def test_invalid_ip_not_allowed(self, mock_config):
        """Test invalid IP is not allowed"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        is_allowed = manager.is_ip_allowed("invalid-ip")

        assert is_allowed is False


class TestRateLimiting:
    """Test check_rate_limit method"""

    @patch("src.core.config.unified_config.config")
    def test_rate_limit_allows_first_request(self, mock_config):
        """Test rate limit allows first request"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        is_allowed = manager.check_rate_limit("192.168.1.1", "/health", SecurityLevel.PUBLIC)

        assert is_allowed is True

    @patch("src.core.config.unified_config.config")
    def test_rate_limit_blocks_excessive_requests(self, mock_config):
        """Test rate limit blocks excessive requests"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        # Find rate limit for health endpoint
        rule = None
        for r in manager.rate_limit_rules:
            if r.endpoint_pattern == "/health":
                rule = r
                break

        # Make requests up to limit
        for _ in range(rule.requests_per_minute):
            manager.check_rate_limit("192.168.1.1", "/health", SecurityLevel.PUBLIC)

        # Next request should be blocked
        is_allowed = manager.check_rate_limit("192.168.1.1", "/health", SecurityLevel.PUBLIC)

        assert is_allowed is False

    @patch("src.core.config.unified_config.config")
    def test_rate_limit_different_ips_independent(self, mock_config):
        """Test rate limits are independent per IP"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        # Make many requests from IP1
        for _ in range(100):
            manager.check_rate_limit("192.168.1.1", "/health", SecurityLevel.PUBLIC)

        # Request from IP2 should still be allowed
        is_allowed = manager.check_rate_limit("192.168.1.2", "/health", SecurityLevel.PUBLIC)

        assert is_allowed is True


class TestThreatDetection:
    """Test detect_suspicious_activity method"""

    @patch("src.core.config.unified_config.config")
    def test_detect_low_threat(self, mock_config):
        """Test detecting low threat activity"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        threat = manager.detect_suspicious_activity("192.168.1.1", "user-123", "/api/data")

        assert threat == ThreatLevel.LOW

    @patch("src.core.config.unified_config.config")
    def test_detect_high_threat_sensitive_endpoint(self, mock_config):
        """Test detecting high threat for sensitive endpoints"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        threat = manager.detect_suspicious_activity("192.168.1.1", "user-123", "/admin/config")

        assert threat in (ThreatLevel.MEDIUM, ThreatLevel.HIGH, ThreatLevel.CRITICAL)

    @patch("src.core.config.unified_config.config")
    def test_detect_sql_injection_attempt(self, mock_config):
        """Test detecting SQL injection attempt"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        # Sinds 2026-10-08 (plan nazorg, punt a) is een SQL-patroon een SIGNAAL: een
        # MEDIUM-event, geen bijdrage aan de dreigingsscore en geen blokkade.
        assert manager.sql_injection_signal("192.168.1.1", "user-123", "/api/data?id=1 OR 1=1")
        threat = manager.detect_suspicious_activity(
            "192.168.1.1", "user-123", "/api/data?id=1 OR 1=1"
        )
        assert threat == ThreatLevel.LOW
        [event] = [e for e in manager.security_events if e.event_type == "sql_injection_signal"]
        assert event.severity == ThreatLevel.MEDIUM
        assert "192.168.1.1" not in manager.blocked_ips

    @patch("src.core.config.unified_config.config")
    def test_detect_failed_login_attempts(self, mock_config):
        """Test detecting multiple failed login attempts"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        # Simulate failed attempts
        manager.failed_attempts["192.168.1.1"] = [datetime.now(timezone.utc) for _ in range(5)]

        threat = manager.detect_suspicious_activity("192.168.1.1", "user-123", "/api/login")

        assert threat in (ThreatLevel.MEDIUM, ThreatLevel.HIGH, ThreatLevel.CRITICAL)


class TestSQLInjectionDetection:
    """Test _contains_sql_injection method"""

    @patch("src.core.config.unified_config.config")
    def test_detects_select_statement(self, mock_config):
        """Test detection of SELECT statement"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        has_injection = manager._contains_sql_injection("SELECT * FROM users")

        assert has_injection is True

    @patch("src.core.config.unified_config.config")
    def test_detects_union_select(self, mock_config):
        """Test detection of UNION SELECT"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        has_injection = manager._contains_sql_injection("1 UNION SELECT password FROM users")

        assert has_injection is True

    @patch("src.core.config.unified_config.config")
    def test_detects_sql_comments(self, mock_config):
        """Test detection of SQL comments"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        has_injection = manager._contains_sql_injection("admin'--")

        assert has_injection is True

    @patch("src.core.config.unified_config.config")
    def test_normal_text_not_detected(self, mock_config):
        """Test normal text is not flagged"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        has_injection = manager._contains_sql_injection("This is a normal query")

        assert has_injection is False


class TestSecurityReporting:
    """Test security reporting methods"""

    @patch("src.core.config.unified_config.config")
    def test_get_security_headers(self, mock_config):
        """Test getting security headers"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        headers = manager.get_security_headers()

        assert isinstance(headers, dict)
        assert "X-Content-Type-Options" in headers
        assert "X-Frame-Options" in headers

    @patch("src.core.config.unified_config.config")
    def test_get_security_report(self, mock_config):
        """Test getting security report"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        # Create some events
        manager._log_security_event(
            "test_event",
            ThreatLevel.MEDIUM,
            "192.168.1.1",
            "user-123",
            "/api/test",
            "Test event",
        )

        report = manager.get_security_report()

        assert "total_events" in report
        assert "recent_events_24h" in report
        assert "threat_distribution" in report
        assert "security_status" in report

    @patch("src.core.config.unified_config.config")
    def test_security_report_healthy_status(self, mock_config):
        """Test security report shows healthy status"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        # Add low severity events
        for _ in range(3):
            manager._log_security_event(
                "test", ThreatLevel.LOW, "192.168.1.1", None, "/test", "Test"
            )

        report = manager.get_security_report()

        assert report["security_status"] == "healthy"

    @patch("src.core.config.unified_config.config")
    def test_security_report_alert_status(self, mock_config):
        """Test security report shows alert status"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        # Add high severity events
        for _ in range(10):
            manager._log_security_event(
                "test", ThreatLevel.HIGH, "192.168.1.1", None, "/test", "Test"
            )

        report = manager.get_security_report()

        assert report["security_status"] == "alert"


class TestSecurityEventLogging:
    """Test _log_security_event method"""

    @patch("src.core.config.unified_config.config")
    def test_log_event_creates_record(self, mock_config):
        """Test logging event creates record"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        manager._log_security_event(
            "test_event",
            ThreatLevel.LOW,
            "192.168.1.1",
            "user-123",
            "/api/test",
            "Test description",
        )

        assert len(manager.security_events) == 1
        event = manager.security_events[0]
        assert event.event_type == "test_event"
        assert event.severity == ThreatLevel.LOW

    @patch("src.core.config.unified_config.config")
    def test_log_critical_event_no_longer_blocks_ip(self, mock_config):
        """Een CRITICAL-event blokkeert niet meer zelf (plan nazorg, punt a).

        Blokkeren is de beslissing van de IP-reputatie in Redis (score, drempel, tijdslimiet).
        """
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        manager._log_security_event(
            "attack",
            ThreatLevel.CRITICAL,
            "192.168.1.1",
            None,
            "/api/test",
            "Critical threat detected",
        )

        assert "192.168.1.1" not in manager.blocked_ips


class TestCleanup:
    """Test cleanup_old_data method"""

    @patch("src.core.config.unified_config.config")
    def test_cleanup_removes_old_events(self, mock_config):
        """Test cleanup removes old events"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        # Add old event
        old_event = SecurityEvent(
            event_id="old",
            event_type="test",
            severity=ThreatLevel.LOW,
            source_ip="192.168.1.1",
            user_id=None,
            endpoint="/test",
            description="Old event",
            timestamp=datetime.now(timezone.utc) - timedelta(days=31),
        )
        manager.security_events.append(old_event)

        # Add recent event
        manager._log_security_event(
            "recent", ThreatLevel.LOW, "192.168.1.1", None, "/test", "Recent event"
        )

        manager.cleanup_old_data()

        assert len(manager.security_events) == 1
        assert manager.security_events[0].event_id != "old"

    @patch("src.core.config.unified_config.config")
    def test_cleanup_removes_old_failed_attempts(self, mock_config):
        """Test cleanup removes old failed attempts"""
        mock_config.jwt_secret_key = "test-secret"
        manager = ProductionSecurityManager()

        # Add old failed attempts
        manager.failed_attempts["192.168.1.1"] = [datetime.now(timezone.utc) - timedelta(days=2)]

        manager.cleanup_old_data()

        assert "192.168.1.1" not in manager.failed_attempts


class TestGlobalSecurityManager:
    """Test get_security_manager function"""

    @patch("src.core.config.unified_config.config")
    def test_get_security_manager_returns_instance(self, mock_config):
        """Test factory returns instance"""
        mock_config.jwt_secret_key = "test-secret"

        manager = get_security_manager()

        assert isinstance(manager, ProductionSecurityManager)

    @patch("src.core.config.unified_config.config")
    def test_get_security_manager_singleton(self, mock_config):
        """Test factory returns same instance"""
        mock_config.jwt_secret_key = "test-secret"

        manager1 = get_security_manager()
        manager2 = get_security_manager()

        assert manager1 is manager2


class TestRequireAuthDecorator:
    """Test require_auth decorator"""

    def test_decorator_wraps_function(self):
        """Test decorator wraps function"""

        @require_auth(SecurityLevel.AUTHENTICATED)
        async def test_func():
            return "success"

        assert callable(test_func)

    @pytest.mark.asyncio
    async def test_decorated_function_callable(self):
        """Test decorated function is callable"""

        @require_auth(SecurityLevel.AUTHENTICATED)
        async def test_func():
            return "success"

        result = await test_func()

        assert result == "success"
