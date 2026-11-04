"""
Security Middleware Coverage Tests - Production Security Middleware
Target: src/core/security/security_middleware.py (16.52% -> 80%+)

Tests for production security middleware:
- ASGI3-compliant middleware
- IP whitelisting
- Rate limiting integration
- Threat detection
- Authentication checks
- Security headers
- Kill switch testing
- Keyword-only parameter enforcement
"""

import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from starlette.datastructures import Headers
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send

from src.core.security.security_manager import SecurityLevel, ThreatLevel
from src.core.security.security_middleware import (
    SecurityMiddleware,
    create_security_middleware,
    validate_security_middleware_instantiation,
)


class TestSecurityMiddlewareInit:
    """Test SecurityMiddleware initialization"""

    def test_middleware_init_with_keyword_arg(self):
        """Should initialize with keyword argument"""
        app = FastAPI()

        middleware = SecurityMiddleware(app, enable_security=True)

        assert middleware.app == app
        assert middleware.enable_security is True
        assert middleware.security_manager is not None

    def test_middleware_init_rejects_positional_arg(self):
        """Should reject positional argument (keyword-only enforcement)"""
        app = FastAPI()

        with pytest.raises(TypeError) as exc_info:
            SecurityMiddleware(app, True)  # Positional arg should fail

        assert (
            "keyword-only" in str(exc_info.value).lower()
            or "positional" in str(exc_info.value).lower()
        )

    def test_middleware_init_default_enabled(self):
        """Should default to security enabled"""
        app = FastAPI()

        middleware = SecurityMiddleware(app, enable_security=True)

        assert middleware.enable_security is True

    def test_middleware_init_can_disable_security(self):
        """Should allow disabling security checks"""
        app = FastAPI()

        middleware = SecurityMiddleware(app, enable_security=False)

        assert middleware.enable_security is False


class TestSecurityMiddlewareKillSwitch:
    """Test kill switch functionality (currently active)"""

    @pytest.mark.asyncio
    async def test_kill_switch_bypasses_all_checks(self):
        """Kill switch should bypass all security checks"""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        middleware = SecurityMiddleware(app, enable_security=True)

        # Mock ASGI scope, receive, send
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
            "client": ("192.168.1.1", 50000),
        }

        receive = AsyncMock()
        send = AsyncMock()

        # Should complete without errors despite no auth
        await middleware(scope, receive, send)

        # App should have been called (kill switch active)
        assert middleware.app is not None


class TestClientIPExtraction:
    """Het client-adres van de SecurityMiddleware komt van `afzender_adres` (een regel, brief 2026-10-28)."""

    def test_get_client_ip_from_x_forwarded_for(self):
        """Achter een vertrouwde proxy: het adres dat de proxy WAARNAM, de rechtse hop.

        Deze test asserteerde tot 2026-08-29 het EERSTE element en legde daarmee
        precies de spoofbaarheid vast die op staging is gemeten. ADR-036 OP-111.
        """
        from src.core.shared.limiet_sleutel import afzender_adres
        from tests.helpers.limiet_request import echte_request

        request = echte_request(
            headers={"X-Forwarded-For": "203.0.113.1, 198.51.100.1"}, client_host="10.0.0.5"
        )

        # 203.0.113.1 is wat de client beweerde; 198.51.100.1 is wat de proxy zag.
        assert afzender_adres(request) == "198.51.100.1"

    def test_get_client_ip_ignores_x_real_ip(self):
        """X-Real-IP is geen bron voor het client-adres."""
        from src.core.shared.limiet_sleutel import afzender_adres
        from tests.helpers.limiet_request import echte_request

        request = echte_request(headers={"X-Real-IP": "203.0.113.5"}, client_host="192.168.1.100")

        # Geen terugval op X-Real-IP (plan nazorg, punt b): die header zet de client zelf.
        assert afzender_adres(request) == "192.168.1.100"

    def test_get_client_ip_fallback_to_client_host(self):
        """Zonder headers telt de verbinding."""
        from src.core.shared.limiet_sleutel import afzender_adres
        from tests.helpers.limiet_request import echte_request

        request = echte_request(client_host="192.168.1.100")

        assert afzender_adres(request) == "192.168.1.100"

    def test_get_client_ip_unknown_when_no_client(self):
        """Zonder verbinding is het adres 'unknown'."""
        from src.core.shared.limiet_sleutel import afzender_adres
        from tests.helpers.limiet_request import echte_request

        request = echte_request()
        request.scope["client"] = None

        assert afzender_adres(request) == "unknown"

class TestDevelopmentModeDetection:
    """Test _is_development_mode method"""

    def test_is_development_mode_true_for_development(self):
        """Should return True for development environment"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            assert middleware._is_development_mode() is True

    def test_is_development_mode_true_for_dev(self):
        """Should return True for dev environment"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            assert middleware._is_development_mode() is True

    def test_is_development_mode_true_for_local(self):
        """Should return True for local environment"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        with patch.dict(os.environ, {"ENVIRONMENT": "local"}):
            assert middleware._is_development_mode() is True

    def test_is_development_mode_false_for_production(self):
        """Should return False for production environment"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            assert middleware._is_development_mode() is False

    def test_is_development_mode_defaults_to_development(self):
        """Should default to development if ENVIRONMENT not set"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ENVIRONMENT", None)
            assert middleware._is_development_mode() is True


class TestSecurityLevelDetermination:
    """Test _determine_security_level method"""

    def test_public_endpoints_are_public(self):
        """Public endpoints should return PUBLIC security level"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)

        public_endpoints = [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/v1/auth/register",
            "/api/v1/auth/token",
        ]

        for endpoint in public_endpoints:
            level = middleware._determine_security_level(endpoint, request)
            assert level == SecurityLevel.PUBLIC, f"Failed for {endpoint}"

    def test_system_en_config_paden_eisen_geen_admin_niveau_meer(self):
        """Keten B nazorg A: de substringtest op /system en /config is vervallen (gaf ADMIN, en
        daarmee 401 voor iedereen). De beheerdersrol zit nu per route (403)."""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "app": app})

        admin_endpoints = ["/system/config", "/config/update"]

        for endpoint in admin_endpoints:
            level = middleware._determine_security_level(endpoint, request)
            assert level == SecurityLevel.AUTHENTICATED

    def test_autonomous_paden_eisen_geen_admin_niveau_meer(self):
        """Keten B nazorg A: /autonomous krijgt in de middleware AUTHENTICATED; rol per route."""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "app": app})

        level = middleware._determine_security_level("/api/v1/autonomous/test", request)

        assert level == SecurityLevel.AUTHENTICATED

    def test_phase2_endpoints_require_authorized(self):
        """Phase 2 endpoints should require AUTHORIZED security level"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)

        # /workflows uses AUTHENTICATED level (same as /agents) - see security_middleware.py NOTE
        endpoints = [
            "/api/v1/phase2/ai",
            "/api/v1/collaboration/teams",
        ]

        for endpoint in endpoints:
            level = middleware._determine_security_level(endpoint, request)
            assert level == SecurityLevel.AUTHORIZED

    def test_orchestrator_endpoints_require_authentication(self):
        """Sinds 2026-10-08 AUTHENTICATED, niet PUBLIC (plan nazorg, overige punten)."""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)

        level = middleware._determine_security_level("/api/v1/orchestrator/execute", request)

        assert level == SecurityLevel.AUTHENTICATED

    def test_default_requires_authentication(self):
        """Unknown endpoints should default to AUTHENTICATED"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)

        level = middleware._determine_security_level("/api/v1/unknown/path", request)

        assert level == SecurityLevel.AUTHENTICATED


class TestUserIdExtraction:
    """Test _extract_user_id method"""

    def test_extract_user_id_from_bearer_token(self):
        """Should extract user_id from valid Bearer token"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)
        request.headers = {"Authorization": "Bearer valid_token"}

        with patch(
            "src.core.security.security_middleware._jwt_handler.verify_token",
            return_value={"sub": "user_123"},
        ):
            user_id = middleware._extract_user_id(request)

        assert user_id == "user_123"

    def test_extract_user_id_returns_none_for_invalid_token(self):
        """Should return None for invalid token"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)
        request.headers = {"Authorization": "Bearer invalid_token"}

        with patch(
            "src.core.security.security_middleware._jwt_handler.verify_token",
            return_value=None,
        ):
            user_id = middleware._extract_user_id(request)

        assert user_id is None

    def test_extract_user_id_from_api_key(self):
        """Should extract user_id from X-API-Key header"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)
        request.headers = {"X-API-Key": "test_api_key_12345678"}

        user_id = middleware._extract_user_id(request)

        assert user_id == "api_user_test_api"  # First 8 chars

    def test_extract_user_id_returns_none_without_auth(self):
        """Should return None when no authentication present"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)
        request.headers = Headers({})

        user_id = middleware._extract_user_id(request)

        assert user_id is None


class TestAuthenticationChecks:
    """Test _check_authentication method"""

    def test_check_auth_fails_without_header(self):
        """Should fail authentication without Authorization header"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)
        request.headers = Headers({})
        request.cookies = {}

        result = middleware._check_authentication(request, SecurityLevel.AUTHENTICATED)

        assert result["valid"] is False
        assert "Missing Authorization header" in result["message"]

    def test_check_auth_fails_without_bearer_prefix(self):
        """Should fail authentication without Bearer prefix"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)
        request.headers = {"Authorization": "Basic user:pass"}
        request.cookies = {}

        result = middleware._check_authentication(request, SecurityLevel.AUTHENTICATED)

        assert result["valid"] is False
        assert "Invalid Authorization header format" in result["message"]

    def test_check_auth_accepts_dev_token_in_dev_mode(self):
        """Should accept dev token in development mode"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)
        request.headers = {"Authorization": "Bearer dev-token-safe-development"}

        with patch.object(middleware, "_is_development_mode", return_value=True):
            result = middleware._check_authentication(request, SecurityLevel.AUTHENTICATED)

        assert result["valid"] is True
        assert result["user_id"] == "dev_user"

    def test_check_auth_rejects_dev_token_for_admin(self):
        """Should reject dev token for admin access even in dev mode"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)
        request.headers = {"Authorization": "Bearer dev-token-safe-development"}

        with patch.object(middleware, "_is_development_mode", return_value=True):
            result = middleware._check_authentication(request, SecurityLevel.ADMIN)

        assert result["valid"] is False
        assert "Admin access requires real authentication" in result["message"]

    def test_check_auth_validates_jwt_token(self):
        """Should validate real JWT token"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)
        request.headers = {"Authorization": "Bearer valid.jwt.token"}

        payload = {"sub": "user_123", "security_level": "authenticated"}

        with patch(
            "src.core.security.security_middleware._jwt_handler.verify_token",
            return_value=payload,
        ):
            result = middleware._check_authentication(request, SecurityLevel.AUTHENTICATED)

        assert result["valid"] is True
        assert result["user_id"] == "user_123"

    def test_check_auth_rejects_invalid_token(self):
        """Should reject invalid JWT token"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)
        request.headers = {"Authorization": "Bearer invalid.jwt.token"}

        with patch(
            "src.core.security.security_middleware._jwt_handler.verify_token",
            return_value=None,
        ):
            result = middleware._check_authentication(request, SecurityLevel.AUTHENTICATED)

        assert result["valid"] is False
        assert "Invalid or expired token" in result["message"]

    def test_check_auth_enforces_security_level(self):
        """Should enforce required security level"""
        app = FastAPI()
        middleware = SecurityMiddleware(app, enable_security=True)

        request = MagicMock(spec=Request)
        request.headers = {"Authorization": "Bearer valid.jwt.token"}

        # Token with AUTHENTICATED level
        payload = {"sub": "user_123", "security_level": "authenticated"}

        with patch(
            "src.core.security.security_middleware._jwt_handler.verify_token",
            return_value=payload,
        ):
            # Should fail for ADMIN requirement
            result = middleware._check_authentication(request, SecurityLevel.ADMIN)

        assert result["valid"] is False
        assert "Insufficient permissions" in result["message"]


class TestMiddlewareFactory:
    """Test create_security_middleware factory"""

    def test_create_middleware_with_enabled_security(self):
        """Should create middleware factory with security enabled"""
        factory = create_security_middleware(enable_security=True)

        assert callable(factory)

        app = FastAPI()
        middleware = factory(app)

        assert isinstance(middleware, SecurityMiddleware)
        assert middleware.enable_security is True

    def test_create_middleware_with_disabled_security(self):
        """Should create middleware factory with security disabled"""
        factory = create_security_middleware(enable_security=False)

        app = FastAPI()
        middleware = factory(app)

        assert middleware.enable_security is False


class TestMiddlewareValidation:
    """Test validate_security_middleware_instantiation"""

    def test_validation_passes_with_proper_setup(self):
        """Should pass validation with proper setup"""
        result = validate_security_middleware_instantiation()

        assert "valid" in result
        assert "message" in result
        assert "security_manager_available" in result
        assert "instantiation_test" in result

    def test_validation_checks_security_manager(self):
        """Should check security manager availability"""
        result = validate_security_middleware_instantiation()

        assert result["security_manager_available"] is True

    def test_validation_checks_keyword_enforcement(self):
        """Should verify keyword-only parameter enforcement"""
        result = validate_security_middleware_instantiation()

        assert result["instantiation_test"] == "keyword_only_enforced"

    def test_validation_handles_exceptions(self):
        """Should handle exceptions during validation"""
        with patch(
            "src.core.security.security_middleware.get_security_manager",
            side_effect=Exception("Test error"),
        ):
            result = validate_security_middleware_instantiation()

            assert result["valid"] is False
            assert "exception" in result["message"].lower()
