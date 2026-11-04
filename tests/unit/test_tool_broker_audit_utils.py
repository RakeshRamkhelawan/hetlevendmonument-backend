"""Tests for tool audit logging utilities."""

import hashlib
import json
from datetime import datetime, timezone

import pytest

from src.core.tool_broker.audit_utils import (
    compute_audit_hash,
    compute_output_hash,
    sanitize_tool_output,
)


class TestComputeOutputHash:
    """Test output hash computation."""

    def test_dict_output_hash(self):
        """Test hashing a dict output."""
        output = {"status": "success", "data": [1, 2, 3]}
        hash1 = compute_output_hash(output)
        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA-256 hex length

    def test_dict_output_is_deterministic(self):
        """Test that same dict always produces same hash."""
        output = {"status": "success", "data": [1, 2, 3]}
        hash1 = compute_output_hash(output)
        hash2 = compute_output_hash(output)
        assert hash1 == hash2

    def test_list_output_hash(self):
        """Test hashing a list output."""
        output = [1, 2, 3, "a", "b"]
        hash1 = compute_output_hash(output)
        assert isinstance(hash1, str)
        assert len(hash1) == 64

    def test_string_output_hash(self):
        """Test hashing a string output."""
        output = "some result text"
        hash1 = compute_output_hash(output)
        assert isinstance(hash1, str)
        assert len(hash1) == 64

    def test_none_output_hash(self):
        """Test hashing None output."""
        hash1 = compute_output_hash(None)
        assert isinstance(hash1, str)
        assert len(hash1) == 64

    def test_different_outputs_different_hashes(self):
        """Test that different outputs produce different hashes."""
        output1 = {"status": "success"}
        output2 = {"status": "failed"}
        hash1 = compute_output_hash(output1)
        hash2 = compute_output_hash(output2)
        assert hash1 != hash2

    def test_non_serializable_fallback(self):
        """Test fallback to str() for non-serializable objects."""

        class CustomObject:
            def __str__(self):
                return "custom"

        obj = CustomObject()
        hash1 = compute_output_hash(obj)
        # Should use str() fallback
        assert isinstance(hash1, str)
        assert len(hash1) == 64


class TestComputeAuditHash:
    """Test audit hash computation for chain integrity."""

    def _make_timestamp(self) -> datetime:
        return datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)

    def test_audit_hash_computation(self):
        """Test basic audit hash computation."""
        ts = self._make_timestamp()
        audit_hash = compute_audit_hash(
            tenant_id=1,
            agent_id="test_agent",
            tool_name="local__read_file",
            timestamp=ts,
            status="success",
            output_hash="abc123",
            previous_hash=None,
        )
        assert isinstance(audit_hash, str)
        assert len(audit_hash) == 64

    def test_audit_hash_is_deterministic(self):
        """Test that same inputs produce same hash."""
        ts = self._make_timestamp()
        hash1 = compute_audit_hash(
            tenant_id=1,
            agent_id="test_agent",
            tool_name="local__read_file",
            timestamp=ts,
            status="success",
            output_hash="abc123",
            previous_hash=None,
        )
        hash2 = compute_audit_hash(
            tenant_id=1,
            agent_id="test_agent",
            tool_name="local__read_file",
            timestamp=ts,
            status="success",
            output_hash="abc123",
            previous_hash=None,
        )
        assert hash1 == hash2

    def test_audit_hash_includes_previous_hash(self):
        """Test that previous_hash is included in audit hash."""
        ts = self._make_timestamp()
        hash_with_prev = compute_audit_hash(
            tenant_id=1,
            agent_id="test_agent",
            tool_name="local__read_file",
            timestamp=ts,
            status="success",
            output_hash="abc123",
            previous_hash="prev_hash_123",
        )
        hash_with_genesis = compute_audit_hash(
            tenant_id=1,
            agent_id="test_agent",
            tool_name="local__read_file",
            timestamp=ts,
            status="success",
            output_hash="abc123",
            previous_hash=None,  # genesis
        )
        assert hash_with_prev != hash_with_genesis

    def test_audit_hash_tenant_isolation(self):
        """Test that different tenants produce different hashes."""
        ts = self._make_timestamp()
        hash1 = compute_audit_hash(
            tenant_id=1,
            agent_id="test_agent",
            tool_name="local__read_file",
            timestamp=ts,
            status="success",
            output_hash=None,
            previous_hash=None,
        )
        hash2 = compute_audit_hash(
            tenant_id=2,
            agent_id="test_agent",
            tool_name="local__read_file",
            timestamp=ts,
            status="success",
            output_hash=None,
            previous_hash=None,
        )
        assert hash1 != hash2


class TestSanitizeToolOutput:
    """Test output sanitization for PII removal."""

    def test_non_dict_output_unchanged(self):
        """Test that non-dict output is returned as-is."""
        assert sanitize_tool_output("text") == "text"
        assert sanitize_tool_output([1, 2, 3]) == [1, 2, 3]
        assert sanitize_tool_output(42) == 42

    def test_pii_keys_redacted(self):
        """Test that PII keys are redacted."""
        output = {
            "password": "secret123",
            "token": "abc123",
            "api_key": "key456",
            "safe_field": "safe_value",
        }
        sanitized = sanitize_tool_output(output)
        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["token"] == "[REDACTED]"
        assert sanitized["api_key"] == "[REDACTED]"
        assert sanitized["safe_field"] == "safe_value"

    def test_nested_dict_sanitized(self):
        """Test that nested dicts are also sanitized."""
        output = {
            "user": {
                "email": "user@example.com",
                "name": "Test User",
            }
        }
        sanitized = sanitize_tool_output(output)
        assert sanitized["user"]["email"] == "[REDACTED]"
        assert sanitized["user"]["name"] == "Test User"

    def test_case_insensitive_pii_detection(self):
        """Test that PII detection is case-insensitive."""
        output = {
            "Password": "secret",
            "API_KEY": "key",
            "SSN": "123-45-6789",
        }
        sanitized = sanitize_tool_output(output)
        assert sanitized["Password"] == "[REDACTED]"
        assert sanitized["API_KEY"] == "[REDACTED]"
        assert sanitized["SSN"] == "[REDACTED]"

    def test_phone_redaction(self):
        """Test that phone numbers are redacted."""
        output = {"phone": "+31612345678"}
        sanitized = sanitize_tool_output(output)
        assert sanitized["phone"] == "[REDACTED]"

    def test_email_redaction(self):
        """Test that email fields are redacted."""
        output = {"email": "user@example.com"}
        sanitized = sanitize_tool_output(output)
        assert sanitized["email"] == "[REDACTED]"
