"""Tests for security audit service."""

import pytest

from src.core.security.security_audit_service import _extract_count_row


class TestExtractCountRow:
    """Test _extract_count_row helper function."""

    @pytest.mark.unit
    def test_extract_count_row_with_valid_data(self):
        """_extract_count_row must extract key and count from tuple."""
        row = ("critical", 5)
        key, val = _extract_count_row(row)

        assert key == "critical"
        assert val == 5

    @pytest.mark.unit
    def test_extract_count_row_handles_none_key(self):
        """_extract_count_row must handle None key as empty string."""
        row = (None, 10)
        key, val = _extract_count_row(row)

        assert key == ""
        assert val == 10

    @pytest.mark.unit
    def test_extract_count_row_handles_missing_count(self):
        """_extract_count_row must handle missing count as 0."""
        row = ("warning",)
        key, val = _extract_count_row(row)

        assert key == "warning"
        assert val == 0

    @pytest.mark.unit
    def test_extract_count_row_handles_both_missing(self):
        """_extract_count_row must handle both missing as empty string and 0."""
        row = ()
        key, val = _extract_count_row(row)

        assert key == ""
        assert val == 0

    @pytest.mark.unit
    def test_extract_count_row_converts_types_correctly(self):
        """_extract_count_row must convert key to string and count to int."""
        row = (ThreatLevel, 42)  # arbitrary non-string, non-int
        key, val = _extract_count_row(row)

        assert isinstance(key, str)
        assert isinstance(val, int)


class ThreatLevel:
    """Mock threat level for testing type conversion."""

    def __str__(self):
        return "mock_level"
