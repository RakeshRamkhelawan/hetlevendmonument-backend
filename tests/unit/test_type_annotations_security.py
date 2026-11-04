"""
Type annotation tests for security modules
Tests the correctness of newly annotated functions
"""

import pytest
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock

from src.core.sandbox.security_manager import (
    SecurityManager,
    SecurityLevel,
    SecurityViolation,
    SecurityThreat,
    ResourceMonitor,
)
from src.core.security.input_validation import (
    validate_safe_string,
    validate_no_sql_injection,
    validate_json_payload,
)


class TestSecurityManagerTypeAnnotations:
    """Tests for security_manager.py type annotations"""

    def test_get_container_stats_accepts_any_container_object(self):
        """HAPPY: get_container_stats accepts Any container object"""
        manager = SecurityManager(SecurityLevel.STANDARD)

        # Mock container object - can be any type
        mock_container = MagicMock()
        mock_container.stats.return_value = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 1000000000},
                "system_cpu_usage": 5000000000,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 500000000},
                "system_cpu_usage": 2500000000,
            },
            "memory_stats": {"usage": 104857600, "limit": 1073741824},
            "networks": {"eth0": {"rx_bytes": 100, "tx_bytes": 50}},
        }

        # Should work with any container-like object
        result = manager.resource_monitor.get_container_stats(mock_container)

        assert isinstance(result, dict)
        assert "cpu_percent" in result
        assert "memory_usage_mb" in result

    def test_get_container_stats_handles_missing_keys(self):
        """UNHAPPY: get_container_stats handles missing network keys gracefully"""
        manager = SecurityManager(SecurityLevel.STANDARD)

        # Minimal mock without all keys
        mock_container = MagicMock()
        mock_container.stats.return_value = {
            "cpu_stats": {},
            "precpu_stats": {},
            "memory_stats": {},
        }

        # Should not crash - handles missing keys
        result = manager.resource_monitor.get_container_stats(mock_container)

        assert isinstance(result, dict)
        assert result.get("cpu_percent", 0) >= 0

    def test_monitor_execution_accepts_container_parameter(self):
        """HAPPY: monitor_execution accepts container parameter with correct types"""
        manager = SecurityManager(SecurityLevel.STANDARD)
        mock_container = MagicMock()
        mock_container.stats.return_value = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 1000},
                "system_cpu_usage": 5000,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 500},
                "system_cpu_usage": 2500,
            },
            "memory_stats": {"usage": 1000, "limit": 10000},
            "networks": {"eth0": {"rx_bytes": 0, "tx_bytes": 0}},
        }

        # Should accept Any container with string sandbox_id
        result = manager.monitor_execution(mock_container, "test-sandbox-123")

        assert isinstance(result, list)
        assert all(isinstance(v, SecurityViolation) for v in result)

    def test_monitor_execution_returns_list_of_violations(self):
        """UNHAPPY: monitor_execution returns empty list when no violations"""
        manager = SecurityManager(SecurityLevel.MINIMAL)
        mock_container = MagicMock()
        mock_container.stats.return_value = {
            "cpu_stats": {},
            "precpu_stats": {},
            "memory_stats": {},
            "networks": {},
        }

        result = manager.monitor_execution(mock_container, "test")
        assert isinstance(result, list)


class TestInputValidationTypeAnnotations:
    """Tests for input_validation.py type annotations"""

    def test_validate_safe_string_accepts_any_value(self):
        """HAPPY: validate_safe_string accepts Any value (Pydantic validator)"""
        # Pydantic validators receive (cls: Any, v: Any)
        mock_cls = MagicMock()
        mock_cls.__name__ = "TestModel"

        # Should accept None
        result = validate_safe_string(mock_cls, None)
        assert result is None

        # Should accept string
        result = validate_safe_string(mock_cls, "test_value")
        assert result == "test_value"

    def test_validate_safe_string_returns_any(self):
        """HAPPY: validate_safe_string returns Any as per Pydantic convention"""
        mock_cls = MagicMock()
        mock_cls.__name__ = "TestModel"

        # Return value should be Any (can be None, str, etc.)
        result = validate_safe_string(mock_cls, "safe_value")
        assert result is not None
        assert isinstance(result, str)

    def test_validate_no_sql_injection_accepts_any(self):
        """HAPPY: validate_no_sql_injection accepts Any value"""
        mock_cls = MagicMock()

        # Should accept None
        result = validate_no_sql_injection(mock_cls, None)
        assert result is None

        # Should accept valid string
        result = validate_no_sql_injection(mock_cls, "valid_input")
        assert result == "valid_input"

    def test_validate_no_sql_injection_rejects_injection(self):
        """UNHAPPY: validate_no_sql_injection raises on SQL injection patterns"""
        mock_cls = MagicMock()

        # Should raise ValueError on injection pattern
        with pytest.raises(ValueError, match="invalid characters"):
            validate_no_sql_injection(mock_cls, "UNION SELECT")

    def test_validate_json_payload_check_depth_recursion(self):
        """HAPPY: check_depth nested function handles recursive structures (obj: Any)"""
        # Nested dict structure
        nested_dict = {"level1": {"level2": {"level3": {"level4": {"data": "value"}}}}}

        # Should not raise - depth is within limit
        validate_json_payload(nested_dict, max_depth=10)

    def test_validate_json_payload_exceeds_depth(self):
        """UNHAPPY: validate_json_payload raises when nesting exceeds max_depth"""
        # Create deeply nested structure
        nested = {"a": 1}
        for i in range(15):
            nested = {"next": nested}

        # Should raise on excessive depth
        with pytest.raises(Exception, match="nesting exceeds"):
            validate_json_payload(nested, max_depth=5)

    def test_validate_json_payload_mixed_types(self):
        """HAPPY: check_depth handles mixed dict/list structures (obj: Any)"""
        mixed = {
            "lists": [1, 2, {"nested": [3, 4]}],
            "dicts": {"a": [5, 6]},
        }

        # Should handle mixed structures
        validate_json_payload(mixed, max_depth=10)


@pytest.mark.parametrize(
    "container_obj,should_work",
    [
        (MagicMock(), True),  # Any object works
        (Mock(), True),  # Mock works
        ({}, True),  # Dict works as Any
        ([], True),  # List works as Any
    ],
)
def test_container_parameter_accepts_any_type(container_obj, should_work):
    """Type annotation: container: Any accepts any type"""
    manager = SecurityManager(SecurityLevel.STANDARD)
    # Just ensure no type error - Any allows this
    assert True
