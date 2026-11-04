"""
Tests for Security Manager - Authentication & Password Management

Coverage target: 80%+
Tests password hashing, token generation, and security validation
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from datetime import datetime, timedelta

import pytest

from src.core.security.security_manager import ProductionSecurityManager, SecurityLevel, ThreatLevel


class TestPasswordHashing:
    """Test password hashing functionality"""

    def test_hash_password(self):
        """Should hash password using bcrypt"""
        manager = ProductionSecurityManager()

        password = "MySecurePassword123!"
        hashed = manager.hash_password(password)

        assert hashed is not None
        assert hashed != password
        assert hashed.startswith("$2b$")  # bcrypt prefix

    def test_verify_password_correct(self):
        """Should verify correct password"""
        manager = ProductionSecurityManager()

        password = "MySecurePassword123!"
        hashed = manager.hash_password(password)

        assert manager.verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Should reject incorrect password"""
        manager = ProductionSecurityManager()

        password = "MySecurePassword123!"
        hashed = manager.hash_password(password)

        assert manager.verify_password("WrongPassword", hashed) is False

    def test_different_passwords_different_hashes(self):
        """Same password should produce different hashes (salt)"""
        manager = ProductionSecurityManager()

        password = "MySecurePassword123!"
        hash1 = manager.hash_password(password)
        hash2 = manager.hash_password(password)

        # Different hashes due to salt
        assert hash1 != hash2

        # But both verify correctly
        assert manager.verify_password(password, hash1) is True
        assert manager.verify_password(password, hash2) is True


class TestTokenGeneration:
    """Test JWT token generation"""

    def test_generate_token(self):
        """Should create valid JWT access token"""
        manager = ProductionSecurityManager()

        token = manager.generate_token(
            user_id="user123", security_level=SecurityLevel.AUTHENTICATED
        )

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_valid_token(self):
        """Should verify valid token"""
        manager = ProductionSecurityManager()

        token = manager.generate_token(user_id="user123")
        payload = manager.verify_token(token)

        assert payload is not None
        assert payload.get("user_id") == "user123"

    def test_verify_invalid_token(self):
        """Should return None for invalid token"""
        manager = ProductionSecurityManager()

        payload = manager.verify_token("invalid.token.here")

        assert payload is None

    def test_token_contains_security_level(self):
        """Token should contain security level"""
        manager = ProductionSecurityManager()

        token = manager.generate_token(user_id="user123", security_level=SecurityLevel.ADMIN)
        payload = manager.verify_token(token)

        assert payload is not None
        assert payload.get("security_level") == SecurityLevel.ADMIN.value


class TestSecurityManagerInit:
    """Test SecurityManager initialization"""

    def test_init_basic(self):
        """Should initialize security manager"""
        manager = ProductionSecurityManager()

        assert manager.secret_key is not None
        assert manager.jwt_algorithm == "HS256"
        assert manager.token_expiry_hours == 24

    def test_init_with_security_headers(self):
        """Should initialize with security headers"""
        manager = ProductionSecurityManager()

        headers = manager.get_security_headers()
        assert "X-Content-Type-Options" in headers
        assert headers["X-Frame-Options"] == "DENY"

    def test_rate_limit_rules_initialized(self):
        """Should initialize rate limit rules"""
        manager = ProductionSecurityManager()

        assert len(manager.rate_limit_rules) > 0


class TestSecurityFeatures:
    """Test security detection features"""

    def test_detect_sql_injection(self):
        """Should detect SQL injection attempts"""
        manager = ProductionSecurityManager()

        # Sinds 2026-10-08 een signaal (MEDIUM), geen CRITICAL en geen blokkade (plan nazorg).
        assert manager.sql_injection_signal(
            "192.168.1.100", "user123", "/api?query=SELECT * FROM users"
        )

        sql_events = [e for e in manager.security_events if e.event_type == "sql_injection_signal"]
        assert len(sql_events) == 1
        assert sql_events[0].severity == ThreatLevel.MEDIUM

    def test_check_rate_limit(self):
        """Should enforce rate limits"""
        manager = ProductionSecurityManager()

        # First request should pass
        allowed = manager.check_rate_limit(
            ip_address="192.168.1.1",
            endpoint="/health",
            security_level=SecurityLevel.PUBLIC,
        )
        assert allowed is True

    def test_is_ip_allowed(self):
        """Should check if IP is allowed"""
        manager = ProductionSecurityManager()

        # Localhost should be allowed
        assert manager.is_ip_allowed("127.0.0.1") is True

    def test_security_report(self):
        """Should generate security report"""
        manager = ProductionSecurityManager()

        report = manager.get_security_report()

        assert "total_events" in report
        assert "security_status" in report
        assert "threat_distribution" in report


class TestSecurityManagerIntegration:
    """Integration tests for SecurityManager"""

    def test_full_auth_flow(self):
        """Test complete authentication flow"""
        manager = ProductionSecurityManager()

        # 1. Hash password
        password = "UserPassword123!"
        hashed = manager.hash_password(password)

        # 2. Verify password
        assert manager.verify_password(password, hashed) is True

        # 3. Create token
        token = manager.generate_token(user_id="user123")

        # 4. Verify token
        payload = manager.verify_token(token)

        assert payload is not None
        assert payload.get("user_id") == "user123"

    def test_module_importable(self):
        """SecurityManager should be importable"""
        from src.core.security.security_manager import ProductionSecurityManager as PSM

        manager = PSM()
        assert manager is not None

    def test_get_security_manager_function(self):
        """get_security_manager should return singleton"""
        from src.core.security.security_manager import get_security_manager

        manager1 = get_security_manager()
        manager2 = get_security_manager()

        # Should return same instance
        assert manager1 is manager2
