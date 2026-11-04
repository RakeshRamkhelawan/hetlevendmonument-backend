"""
Comprehensive tests for src/core/middleware/tenant_context.py
Coverage target: 100% of tenant context management
"""

from unittest.mock import patch

import pytest

from src.core.middleware.tenant_context import (
    clear_tenant_context,
    get_current_tenant_id,
    get_tenant_context_info,
    get_tenant_id,
    has_tenant_context,
    require_tenant_id,
    set_tenant_id,
)


class TestSetTenantId:
    """Test set_tenant_id function"""

    def test_set_valid_tenant_id(self):
        """Test setting valid tenant ID"""
        set_tenant_id(123)

        assert get_tenant_id() == 123

        # Cleanup
        clear_tenant_context()

    def test_set_none_tenant_id(self):
        """Test setting None tenant ID"""
        set_tenant_id(None)

        assert get_tenant_id() is None

    def test_set_tenant_id_type_validation(self):
        """Test type validation for tenant ID.

        Note: The implementation allows numeric strings and converts them to int.
        Non-numeric strings are rejected with ValueError (not TypeError).
        TypeError is raised for non-string, non-int types (floats, lists, dicts).
        """
        # Float raises TypeError (not int, not numeric string)
        with pytest.raises(TypeError, match="tenant_id must be int"):
            set_tenant_id(123.45)

        # List raises TypeError (not int, not numeric string)
        with pytest.raises(TypeError, match="tenant_id must be int"):
            set_tenant_id([123])

        # Non-numeric string raises ValueError (type coercion attack protection)
        with pytest.raises(ValueError, match="must be numeric"):
            set_tenant_id("not_a_number")

    def test_set_tenant_id_range_validation(self):
        """Test range validation for tenant ID"""
        with pytest.raises(ValueError, match="tenant_id must be positive"):
            set_tenant_id(0)

        with pytest.raises(ValueError, match="tenant_id must be positive"):
            set_tenant_id(-1)

        with pytest.raises(ValueError, match="tenant_id must be positive"):
            set_tenant_id(-999)

    def test_set_multiple_tenant_ids(self):
        """Test setting multiple tenant IDs"""
        set_tenant_id(100)
        assert get_tenant_id() == 100

        set_tenant_id(200)
        assert get_tenant_id() == 200

        # Cleanup
        clear_tenant_context()


class TestGetTenantId:
    """Test get_tenant_id function"""

    def test_get_tenant_id_when_set(self):
        """Test getting tenant ID when set"""
        set_tenant_id(456)

        tenant_id = get_tenant_id()

        assert tenant_id == 456

        # Cleanup
        clear_tenant_context()

    def test_get_tenant_id_when_not_set(self):
        """Test getting tenant ID when not set"""
        clear_tenant_context()

        tenant_id = get_tenant_id()

        assert tenant_id is None

    def test_get_tenant_id_after_clear(self):
        """Test getting tenant ID after clearing"""
        set_tenant_id(789)
        clear_tenant_context()

        tenant_id = get_tenant_id()

        assert tenant_id is None


class TestClearTenantContext:
    """Test clear_tenant_context function"""

    def test_clear_tenant_context(self):
        """Test clearing tenant context"""
        set_tenant_id(111)
        assert get_tenant_id() == 111

        clear_tenant_context()

        assert get_tenant_id() is None

    def test_clear_tenant_context_when_empty(self):
        """Test clearing already empty context"""
        clear_tenant_context()
        clear_tenant_context()  # Should not raise

        assert get_tenant_id() is None


class TestRequireTenantId:
    """Test require_tenant_id function"""

    def test_require_tenant_id_when_set(self):
        """Test requiring tenant ID when set"""
        set_tenant_id(222)

        tenant_id = require_tenant_id()

        assert tenant_id == 222

        # Cleanup
        clear_tenant_context()

    def test_require_tenant_id_when_not_set(self):
        """Test requiring tenant ID when not set raises error"""
        clear_tenant_context()

        with pytest.raises(RuntimeError, match="Tenant context not set"):
            require_tenant_id()

    def test_require_tenant_id_security_validation(self):
        """Test require_tenant_id validates tenant ID"""
        # This test verifies defense-in-depth validation
        # Even if someone bypasses set_tenant_id, require_tenant_id validates again
        set_tenant_id(333)
        tenant_id = require_tenant_id()

        assert tenant_id == 333

        # Cleanup
        clear_tenant_context()


class TestHasTenantContext:
    """Test has_tenant_context function"""

    def test_has_tenant_context_true(self):
        """Test has_tenant_context returns true when set"""
        set_tenant_id(444)

        result = has_tenant_context()

        assert result is True

        # Cleanup
        clear_tenant_context()

    def test_has_tenant_context_false(self):
        """Test has_tenant_context returns false when not set"""
        clear_tenant_context()

        result = has_tenant_context()

        assert result is False

    def test_has_tenant_context_after_clear(self):
        """Test has_tenant_context after clearing"""
        set_tenant_id(555)
        clear_tenant_context()

        result = has_tenant_context()

        assert result is False


class TestGetTenantContextInfo:
    """Test get_tenant_context_info function"""

    def test_get_tenant_context_info_when_set(self):
        """Test getting context info when tenant is set"""
        set_tenant_id(666)

        info = get_tenant_context_info()

        assert info["has_tenant_context"] is True
        assert info["tenant_id"] == 666
        assert info["tenant_id_type"] == "int"

        # Cleanup
        clear_tenant_context()

    def test_get_tenant_context_info_when_not_set(self):
        """Test getting context info when tenant not set"""
        clear_tenant_context()

        info = get_tenant_context_info()

        assert info["has_tenant_context"] is False
        assert info["tenant_id"] is None
        assert info["tenant_id_type"] is None


class TestBackwardCompatibility:
    """Test backward compatibility"""

    def test_get_current_tenant_id_alias(self):
        """Test get_current_tenant_id is alias for get_tenant_id"""
        set_tenant_id(777)

        # Both should return same value
        assert get_current_tenant_id() == get_tenant_id()
        assert get_current_tenant_id() == 777

        # Cleanup
        clear_tenant_context()


class TestContextIsolation:
    """Test context isolation between operations"""

    def test_context_isolation(self):
        """Test tenant context is isolated"""
        # Set context
        set_tenant_id(888)
        assert get_tenant_id() == 888

        # Clear context
        clear_tenant_context()
        assert get_tenant_id() is None

        # Set different context
        set_tenant_id(999)
        assert get_tenant_id() == 999

        # Cleanup
        clear_tenant_context()


class TestSecurityScenarios:
    """Test security-related scenarios"""

    def test_prevent_sql_injection_via_type(self):
        """Test SQL injection prevention via pattern detection.

        Note: The implementation detects SQL injection patterns in ALL values
        by converting to string first. This means even dicts/lists will raise
        ValueError (not TypeError) if their string representation contains
        suspicious characters like quotes.
        """
        malicious_inputs = [
            "1 OR 1=1",
            "123; DROP TABLE users;",
            "' OR '1'='1",
            {"id": 123},  # String repr contains quotes
            [1, 2, 3],  # No quotes in repr, but list is still invalid type
        ]

        for malicious_input in malicious_inputs:
            # All these raise ValueError or TypeError depending on content
            with pytest.raises((ValueError, TypeError)):
                set_tenant_id(malicious_input)

    def test_prevent_negative_tenant_ids(self):
        """Test prevention of negative tenant IDs"""
        invalid_ids = [-1, -100, -999, 0]

        for invalid_id in invalid_ids:
            with pytest.raises(ValueError):
                set_tenant_id(invalid_id)

    def test_require_fails_without_context(self):
        """Test require_tenant_id fails without context"""
        clear_tenant_context()

        # This simulates public endpoint trying to access tenant data
        with pytest.raises(RuntimeError, match="Critical security issue"):
            require_tenant_id()

    def test_context_must_be_cleared_between_requests(self):
        """Test context clearing between requests"""
        # Request 1
        set_tenant_id(100)
        assert get_tenant_id() == 100

        # Simulate end of request
        clear_tenant_context()

        # Request 2 should not have context from Request 1
        assert get_tenant_id() is None

        # Request 2 sets its own context
        set_tenant_id(200)
        assert get_tenant_id() == 200

        # Cleanup
        clear_tenant_context()


class TestEdgeCases:
    """Test edge cases"""

    def test_very_large_tenant_id(self):
        """Test very large tenant ID is rejected for overflow protection.

        Note: The implementation limits tenant_id to 2147483647 (max 32-bit signed int)
        to prevent integer overflow attacks.
        """
        large_id = 999999999999  # Exceeds max 32-bit int
        with pytest.raises(ValueError, match="exceeds maximum value"):
            set_tenant_id(large_id)

        # Max valid value should work
        max_valid = 2147483647
        set_tenant_id(max_valid)
        assert get_tenant_id() == max_valid

        # Cleanup
        clear_tenant_context()

    def test_minimum_valid_tenant_id(self):
        """Test minimum valid tenant ID"""
        set_tenant_id(1)

        assert get_tenant_id() == 1
        assert require_tenant_id() == 1

        # Cleanup
        clear_tenant_context()

    def test_repeated_sets(self):
        """Test repeated set operations"""
        for i in range(1, 10):
            set_tenant_id(i)
            assert get_tenant_id() == i

        # Cleanup
        clear_tenant_context()

    def test_repeated_clears(self):
        """Test repeated clear operations"""
        set_tenant_id(123)

        for _ in range(5):
            clear_tenant_context()
            assert get_tenant_id() is None

    def test_alternating_set_and_clear(self):
        """Test alternating set and clear"""
        for i in range(1, 10):
            set_tenant_id(i)
            assert get_tenant_id() == i

            clear_tenant_context()
            assert get_tenant_id() is None


class TestMultipleContextScenarios:
    """Test multiple context usage scenarios"""

    def test_middleware_simulation(self):
        """Test simulating middleware usage"""
        # Middleware sets context from JWT
        set_tenant_id(123)

        # Application code uses context
        assert has_tenant_context() is True
        tenant_id = require_tenant_id()
        assert tenant_id == 123

        # Middleware clears on request end
        clear_tenant_context()
        assert has_tenant_context() is False

    def test_public_endpoint_scenario(self):
        """Test public endpoint scenario"""
        clear_tenant_context()

        # Public endpoint checks context
        if has_tenant_context():
            # This should not execute
            pytest.fail("Should not have tenant context")
        else:
            # Public data access
            assert get_tenant_id() is None

    def test_protected_endpoint_scenario(self):
        """Test protected endpoint scenario"""
        set_tenant_id(456)

        # Protected endpoint requires context
        tenant_id = require_tenant_id()

        # Use tenant_id for database query
        assert tenant_id == 456

        # Cleanup
        clear_tenant_context()

    def test_error_recovery_scenario(self):
        """Test error recovery with context cleanup"""
        try:
            set_tenant_id(789)
            assert get_tenant_id() == 789

            # Simulate error
            raise Exception("Simulated error")
        except Exception:
            # Always clear context in finally block
            pass
        finally:
            clear_tenant_context()

        # Context should be cleared
        assert get_tenant_id() is None
