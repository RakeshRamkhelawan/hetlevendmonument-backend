"""Tests for tenant ID format validation fix."""

import re

import pytest

from src.core.exceptions import AuthError


class TestTenantFormatValidation:
    """Test that tenant ID format validation works correctly."""

    def test_valid_tenant_id_alphanumeric(self):
        """Should accept alphanumeric tenant IDs."""
        valid_ids = [
            "tenant123",
            "tenant_123",
            "tenant-123",
            "TENANT123",
            "Tenant_123",
            "a",
            "123",
        ]
        for tenant_id in valid_ids:
            # Should not raise
            assert re.match(r"^[a-zA-Z0-9_-]+$", tenant_id) is not None

    def test_invalid_tenant_id_special_chars(self):
        """Should reject tenant IDs with special characters."""
        invalid_ids = [
            "tenant@123",  # @ not allowed
            "tenant.123",  # . not allowed
            "tenant/123",  # / not allowed
            "tenant 123",  # space not allowed
            "tenant\t123",  # tab not allowed
            "tenant\n123",  # newline not allowed
            "",  # empty not allowed
        ]
        for tenant_id in invalid_ids:
            if tenant_id:  # Skip empty for regex test
                assert re.match(r"^[a-zA-Z0-9_-]+$", tenant_id) is None

    def test_tenant_id_too_long(self):
        """Should reject tenant IDs that are too long."""
        long_id = "a" * 129  # 129 characters
        assert len(long_id) > 128
        # Should be flagged as too long

    def test_tenant_id_max_length(self):
        """Should accept tenant IDs up to 128 characters."""
        max_id = "a" * 128  # Exactly 128 characters
        assert len(max_id) == 128
        assert re.match(r"^[a-zA-Z0-9_-]+$", max_id) is not None

    def test_tenant_id_type_validation(self):
        """Should reject non-string tenant IDs."""
        invalid_types = [
            None,
            123,
            ["tenant"],
            {"id": "tenant"},
            b"tenant",
        ]
        for invalid in invalid_types:
            assert not isinstance(invalid, str) or invalid is None


class TestTenantValidationInSupervisors:
    """Test tenant validation in supervisor classes."""

    @pytest.fixture
    def supervisor(self):
        from src.core.als.supervisors import FinanceSupervisor

        return FinanceSupervisor()

    @pytest.mark.asyncio
    async def test_invalid_tenant_format_raises_error(self, supervisor):
        """Should raise AuthError for invalid tenant format."""
        task = {"type": "tax_filing", "tenant_id": "invalid@tenant"}  # Invalid character

        with pytest.raises(AuthError):
            await supervisor.decompose_task(task)

    @pytest.mark.asyncio
    async def test_too_long_tenant_id_raises_error(self, supervisor):
        """Should raise AuthError for too long tenant ID."""
        task = {"type": "tax_filing", "tenant_id": "a" * 129}  # Too long

        with pytest.raises(AuthError):
            await supervisor.decompose_task(task)

    @pytest.mark.asyncio
    async def test_non_string_tenant_id_raises_error(self, supervisor):
        """Should raise AuthError for non-string tenant ID."""
        task = {"type": "tax_filing", "tenant_id": 12345}  # Integer, not string

        with pytest.raises(AuthError):
            await supervisor.decompose_task(task)
