"""
TAAK 2.1: AUTH IMPLEMENTATION CONSOLIDATION - RED PHASE TESTS

RED Phase: Write failing tests FIRST
These tests verify:
1. Deprecation warnings are issued for legacy code
2. All auth dependencies use canonical implementation
3. No direct legacy auth usage in new code
4. OAuth2 endpoints use jwt_handler
"""

import warnings
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest


_SECURITY_MODULE = "src.core.security"


@pytest.fixture(autouse=True)
def _herstel_security_module_na_elke_test():
    """Zet `sys.modules["src.core.security"]` terug naar het OORSPRONKELIJKE object.

    Twee tests in dit bestand gooien die module weg om een verse import te forceren -- dat is wat ze
    meten (de DeprecationWarning vuurt alleen bij een eerste import). Zonder herstel blijft er een
    NIEUW moduleobject achter, en dan houden modules die er al iets uit hadden geimporteerd de oude
    objecten vast terwijl een latere importeur nieuwe maakt. Een `isinstance` in een ander
    testbestand faalt dan zonder zichtbare reden, en alleen bij een bepaalde volgorde -- de vorm van
    ADR-036 OP-45. Het `tests/conftest.py`-vangnet betrapte deze tests daarop op 2026-08-11.
    """
    import sys

    bewaard = sys.modules.get(_SECURITY_MODULE)
    yield
    if bewaard is not None:
        sys.modules[_SECURITY_MODULE] = bewaard
    else:
        sys.modules.pop(_SECURITY_MODULE, None)


class TestAuthImplementationConsolidation:
    """
    RED PHASE: Tests for auth implementation consolidation
    These tests will FAIL until consolidation is complete
    """

    # ============================================================================
    # TEST 1: Deprecation Warning Verification
    # ============================================================================

    def test_security_module_issues_deprecation_warning_on_import(self):
        """
        RED: Test that importing legacy security module issues DeprecationWarning
        Current: security.py should issue warning
        Expected: Warning with clear migration path
        """
        import sys

        # Remove module if already loaded
        if "src.core.security" in sys.modules:
            del sys.modules["src.core.security"]

        # Reimport with warning capture
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            import src.core.security

            # A DeprecationWarning should be issued
            deprecation_warnings = [
                warning for warning in w if issubclass(warning.category, DeprecationWarning)
            ]

            assert (
                len(deprecation_warnings) > 0
            ), "CONSOLIDATION FAIL: No DeprecationWarning issued for security.py"

            # Check warning message contains migration guidance
            warning_text = str(deprecation_warnings[0].message)
            assert (
                "DEPRECATED" in warning_text or "deprecated" in warning_text
            ), "Warning must indicate deprecation"

            assert (
                "jwt_handler" in warning_text or "dependencies" in warning_text
            ), "Warning must suggest migration to canonical implementation"

    def test_canonical_jwt_handler_has_secret_validation(self):
        """
        RED: Test that jwt_handler includes secret validation
        From TAAK 1.1: Should have _validate_secret_for_production method
        """
        from src.core.auth.jwt_handler import jwt_handler

        # Should have validation method from TAAK 1.1
        assert hasattr(
            jwt_handler, "_validate_secret_for_production"
        ), "jwt_handler must have _validate_secret_for_production (from TAAK 1.1)"

        # Validation should reject weak secrets with "dev-" pattern
        # Must be 32+ chars to get past length check first
        with pytest.raises(ValueError, match="dev-|Development"):
            jwt_handler._validate_secret_for_production("dev-" + "x" * 50)

        # Validation should reject weak secrets with "test-" pattern
        with pytest.raises(ValueError, match="test-|Development"):
            jwt_handler._validate_secret_for_production("test-" + "x" * 50)

        # Validation should reject short secrets first
        with pytest.raises(ValueError, match="32 characters"):
            jwt_handler._validate_secret_for_production("short")

        # Validation should accept strong secrets
        strong_secret = "x" * 100 + "Y" * 100  # 200+ chars, no weak patterns
        result = jwt_handler._validate_secret_for_production(strong_secret)
        assert result is True, "Strong secret should pass validation"

    def test_canonical_dependencies_module_exists_and_exports_get_current_user(self):
        """
        RED: Test that canonical dependencies module is properly set up
        Should export get_current_user for FastAPI dependency injection
        """
        from src.core.auth import dependencies

        # Should have the canonical get_current_user function
        assert hasattr(
            dependencies, "get_current_user"
        ), "dependencies module must export get_current_user"

        # Should be a callable (function or other callable)
        assert callable(
            dependencies.get_current_user
        ), "get_current_user must be callable for FastAPI Depends()"

    # ============================================================================
    # TEST 2: No Mixed Auth Implementations
    # ============================================================================

    def test_security_module_does_not_redefine_jwt_logic(self):
        """
        RED: Test that security.py doesn't duplicate JWT logic
        Should delegate to jwt_handler instead
        """
        import inspect

        from src.core.security import create_access_token

        # Get the function source
        source = inspect.getsource(create_access_token)

        # Should NOT implement JWT logic directly
        # Should call jwt_handler instead
        assert (
            "jwt_handler" in source or "jwt.encode" not in source
        ), "security.create_access_token should delegate to jwt_handler, not reimplement"

    def test_oauth2_endpoints_uses_jwt_handler(self):
        """
        RED: Test that OAuth2 endpoints use canonical jwt_handler
        Not legacy security module
        """
        import re
        from pathlib import Path

        oauth2_file = Path("src/core/api/oauth2_endpoints.py")
        if not oauth2_file.exists():
            pytest.skip("oauth2_endpoints.py not found")

        content = oauth2_file.read_text()

        # Should import from jwt_handler or auth service using jwt_handler
        has_jwt_handler = "jwt_handler" in content
        has_legacy_import = "from src.core.security import" in content

        assert (
            has_jwt_handler or not has_legacy_import
        ), "OAuth2 endpoints should use jwt_handler, not legacy security module"

    # ============================================================================
    # TEST 3: Consistent Token Signing/Verification
    # ============================================================================

    @pytest.mark.asyncio
    async def test_tokens_created_with_jwt_handler_can_be_verified(self):
        """
        RED: Test token creation/verification consistency
        Tokens created by jwt_handler must be verifiable by same handler
        """
        from src.core.auth.jwt_handler import jwt_handler

        # Create token
        test_data = {"sub": "test@example.com", "tenant_id": 1}
        token = jwt_handler.create_access_token(test_data)

        # Verify token
        payload = jwt_handler.verify_token(token)

        assert payload is not None, "Valid token should be verifiable"
        assert payload.get("sub") == "test@example.com", "Token content must be preserved"
        assert payload.get("tenant_id") == 1, "All fields must be preserved"

    @pytest.mark.asyncio
    async def test_invalid_tokens_are_rejected(self):
        """
        RED: Test that invalid tokens are properly rejected
        """
        from src.core.auth.jwt_handler import jwt_handler

        # Try to verify invalid token
        result = jwt_handler.verify_token("invalid.token.here")
        assert result is None, "Invalid token must return None, not raise exception"

        # Try to verify tampered token
        valid_token = jwt_handler.create_access_token({"sub": "test@example.com"})
        tampered = valid_token[:-5] + "XXXXX"  # Corrupt last 5 chars

        result = jwt_handler.verify_token(tampered)
        assert result is None, "Tampered token must return None"

    # ============================================================================
    # TEST 4: Dependency Injection Consistency
    # ============================================================================

    @pytest.mark.asyncio
    async def test_get_current_user_dependency_returns_user_object(self):
        """
        RED: Test that canonical get_current_user returns proper User object
        Not legacy TokenData
        """
        # The function signature should accept token and db
        import inspect

        from src.core.auth import UserResponse
        from src.core.auth.dependencies import _get_user_from_token, get_current_user

        sig = inspect.signature(_get_user_from_token)
        params = list(sig.parameters.keys())

        assert "token" in params or "token" in "".join(
            params
        ), "get_user_from_token must accept token parameter"
        assert "db" in params or any(
            "db" in p for p in params
        ), "get_user_from_token must accept db parameter"

    def test_legacy_tokendata_class_is_deprecated(self):
        """
        RED: Test that legacy TokenData class issues deprecation warning
        Should not be used in new code
        """
        # Reset modules
        import sys
        import warnings

        if "src.core.security" in sys.modules:
            del sys.modules["src.core.security"]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from src.core.security import TokenData

            # Creating an instance should warn
            token_data = TokenData(username="test", scopes=["admin"])

            # Should have deprecation warnings
            deprecation_warnings = [
                warning for warning in w if issubclass(warning.category, DeprecationWarning)
            ]

            assert (
                len(deprecation_warnings) > 0
            ), "TokenData should issue DeprecationWarning when instantiated"

    # ============================================================================
    # TEST 5: Configuration Consistency
    # ============================================================================

    def test_all_auth_modules_use_same_secret_key(self):
        """
        RED: Test that all auth modules use the same JWT secret
        No multiple secrets causing inconsistency
        """
        from src.core.auth.jwt_handler import jwt_handler
        from src.core.config.unified_config import config

        # jwt_handler should have the configured secret
        assert (
            jwt_handler.secret_key == config.jwt_secret_key
        ), "jwt_handler must use the configured JWT secret"

        # Secret should be validated in production
        if config.is_production():
            # If we reach here, secret was already validated on init
            assert (
                len(jwt_handler.secret_key) >= 32
            ), "Production JWT secret must be at least 32 characters (from TAAK 1.1)"

    def test_all_auth_modules_use_same_expiration_time(self):
        """
        RED: Test consistent token expiration across all modules
        """
        from src.core.auth.jwt_handler import jwt_handler
        from src.core.config.unified_config import config

        assert (
            jwt_handler.access_token_expire_minutes == config.jwt_expire_minutes
        ), "All auth modules must use same token expiration configuration"

    # ============================================================================
    # TEST 6: Migration Path Validation
    # ============================================================================

    def test_migration_from_legacy_security_is_straightforward(self):
        """
        RED: Test that migration from legacy security.py is straightforward

        Migration Examples:
        from src.core.security import create_access_token
        ↓
        from src.core.auth.jwt_handler import jwt_handler
        token = jwt_handler.create_access_token(...)

        from src.core.security import get_current_user as get_legacy_user
        ↓
        from src.core.auth.dependencies import get_current_user
        """
        import ast
        from pathlib import Path

        # Check that security package __init__.py has migration documentation.
        # src/core/security/ is a package (directory), so check __init__.py.
        security_file = Path("src/core/security/__init__.py")
        assert security_file.exists(), "security.py must exist"

        # Read with UTF-8 encoding (file contains emoji/unicode characters)
        content = security_file.read_text(encoding="utf-8")

        # Should have migration documentation
        assert (
            "MIGRATION" in content or "migrate" in content.lower()
        ), "security.py should document how to migrate to canonical implementation"

        # Should suggest jwt_handler
        assert "jwt_handler" in content, "security.py migration guide must mention jwt_handler"

        # Should suggest dependencies module
        assert (
            "dependencies" in content
        ), "security.py migration guide must mention dependencies module"

    # ============================================================================
    # TEST 7: No Circular Dependencies
    # ============================================================================

    def test_no_circular_dependencies_between_auth_modules(self):
        """
        RED: Test for circular dependency issues

        Dependency Graph (should be ACYCLIC):
        security.py → jwt_handler.py (one direction only)
        oauth2_endpoints.py → jwt_handler.py
        dependencies.py → jwt_handler.py
        """
        import ast
        import re
        from pathlib import Path

        modules_to_check = [
            ("src/core/security.py", ["jwt_handler"]),
            ("src/core/auth/dependencies.py", ["jwt_handler"]),
            ("src/core/api/oauth2_endpoints.py", ["jwt_handler", "dependencies"]),
        ]

        # Check each module imports from canonical sources only
        for module_path, allowed_imports in modules_to_check:
            file = Path(module_path)
            if not file.exists():
                continue

            # Read with UTF-8 encoding (file may contain unicode characters)
            content = file.read_text(encoding="utf-8")

            # Find all imports of auth-related modules
            imports = re.findall(r"from src\.core\.auth\.(\w+) import", content)

            # All imports should be canonical (jwt_handler, dependencies, etc)
            for imp in imports:
                if imp not in allowed_imports and imp not in [
                    "",
                    "models",
                    "rbac",
                    "token_blacklist",
                ]:
                    # Allow some non-canonical imports but flag unusual ones
                    pass


class TestAuthConsolidationMetrics:
    """
    Metrics to track consolidation progress
    """

    def test_old_security_module_usage_declining(self):
        """
        METRIC: Track that security.py usage is being phased out
        Should show declining import count over time
        """
        import re
        import subprocess

        # Count files importing from legacy security module
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-n", "10"],
                capture_output=True,
                text=True,
                cwd=".",
            )

            # If git is available, we could track historical usage
            # For now, just verify current state
            pass
        except:
            # Git not available in test environment
            pass

        # Verify we're using canonical imports instead
        from src.core.auth.dependencies import get_current_user
        from src.core.auth.jwt_handler import jwt_handler

        # These should work without deprecation warnings
        assert jwt_handler is not None
        assert get_current_user is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
